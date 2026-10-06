#!/usr/bin/env python3
"""Supervisor / Multi-Agent E2E for Qwen Code 0.24.2 named agents."""
from __future__ import annotations

import json
import sys
import threading
import time
import urllib.request
from pathlib import Path

PROJECT = Path("/home/mike/Projects/Linux Lokales KI")
sys.path.insert(0, str(PROJECT / "benchmarks"))
from quality_cutover_e2e import (  # noqa: E402
    EventCollector,
    http_json,
    nvidia,
    ollama_ps,
    sse_loop,
    wait_for_turn,
)

OUT = PROJECT / "benchmarks" / "supervisor-multi-agent-20260922"
WORKSPACE = "/srv/ai/workspaces"


def unload(*models: str) -> None:
    for model in models:
        try:
            urllib.request.urlopen(
                urllib.request.Request(
                    "http://127.0.0.1:11434/api/generate",
                    data=json.dumps({"model": model, "keep_alive": 0, "prompt": ""}).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                ),
                timeout=60,
            ).read()
        except Exception:
            pass
    time.sleep(2)


def chat_path(session_id: str) -> Path:
    return Path.home() / ".qwen/projects/-srv-ai-workspaces/chats" / f"{session_id}.jsonl"


def collect_tools(session_id: str) -> list[str]:
    path = chat_path(session_id)
    names: list[str] = []
    if not path.is_file():
        return names
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        message = obj.get("message") or {}
        for part in message.get("parts") or []:
            call = part.get("functionCall") or {}
            name = str(call.get("name") or "")
            args = call.get("args") or {}
            if name == "tool_call":
                inner = str(args.get("name") or "")
                if inner == "agent":
                    ag = args.get("arguments") or {}
                    if isinstance(ag, str):
                        try:
                            ag = json.loads(ag)
                        except json.JSONDecodeError:
                            ag = {}
                    if isinstance(ag, dict):
                        names.append(f"agent:{ag.get('subagent_type') or 'default'}")
                    else:
                        names.append("agent:default")
                else:
                    names.append(inner)
            elif name == "agent":
                names.append(f"agent:{args.get('subagent_type') or args.get('name') or 'default'}")
            elif name:
                names.append(name)
        event = ((obj.get("systemPayload") or {}).get("uiEvent") or {})
        if event.get("event.name") == "qwen-code.tool_call":
            short = str(event.get("function_name") or "").split("__")[-1]
            if short:
                names.append(short)
    return names


def prompt_tokens(session_id: str) -> list[int]:
    path = chat_path(session_id)
    out: list[int] = []
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        um = (json.loads(line).get("usageMetadata") or {})
        if isinstance(um.get("promptTokenCount"), int):
            out.append(um["promptTokenCount"])
    return out


def model_texts(session_id: str) -> str:
    path = chat_path(session_id)
    chunks: list[str] = []
    if not path.is_file():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        message = (json.loads(line).get("message") or {})
        if message.get("role") not in {"assistant", "model"}:
            continue
        for part in message.get("parts") or []:
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                chunks.append(text)
    return "\n".join(chunks)


def agent_results(session_id: str) -> list[dict]:
    """Extract agent tool responses / notifications from chat."""
    path = chat_path(session_id)
    results: list[dict] = []
    if not path.is_file():
        return results
    blob = path.read_text(encoding="utf-8")
    for line in blob.splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        message = obj.get("message") or {}
        for part in message.get("parts") or []:
            fr = part.get("functionResponse") or {}
            name = str(fr.get("name") or "")
            if "agent" in name.lower():
                out = str((fr.get("response") or {}).get("output") or "")
                results.append({"name": name, "chars": len(out), "excerpt": out[:1200]})
        subtype = obj.get("subtype")
        if subtype and "agent" in str(subtype).lower():
            results.append({"subtype": subtype, "payload_keys": list((obj.get("systemPayload") or {}).keys())[:12]})
    # also search for RESULT blocks from notifications
    if "RESULT" in blob and "EVIDENCE" in blob:
        results.append({"structured_result_seen": True})
    return results


def wait_for_turn_safe(session_id: str, collector: EventCollector, t0: float, since: str) -> dict:
    try:
        return wait_for_turn(session_id, collector, t0, since)
    except Exception as exc:
        print(f"[wait] interrupted {exc}", flush=True)
        return {"error": str(exc)}


def run_session(label: str, model_id: str, prompt: str, timeout_hint: float = 600) -> dict:
    unload("local-quality", "local-fast")
    # ensure serve is up
    for _ in range(15):
        try:
            urllib.request.urlopen("http://127.0.0.1:4170/health", timeout=2).read()
            break
        except Exception:
            time.sleep(1)
    created = http_json("POST", "/session", {"cwd": WORKSPACE})
    sid = created["sessionId"]
    if created.get("attached"):
        http_json("DELETE", f"/session/{sid}")
        created = http_json("POST", "/session", {"cwd": WORKSPACE})
        sid = created["sessionId"]
    http_json("POST", f"/session/{sid}/model", {"modelId": model_id})
    try:
        http_json(
            "POST",
            f"/session/{sid}/config-option",
            {"configId": "reasoning_effort", "value": "none", "persist": False},
        )
    except Exception:
        pass
    stop = threading.Event()
    collector = EventCollector(sid)
    threading.Thread(target=sse_loop, args=(sid, collector, stop), daemon=True).start()
    time.sleep(0.7)
    t0 = time.perf_counter()
    since = time.strftime("%Y-%m-%d %H:%M:%S")
    prompt_error = None
    try:
        http_json(
            "POST",
            f"/session/{sid}/prompt",
            {"prompt": [{"type": "text", "text": prompt}]},
            timeout=30,
        )
    except Exception as exc:
        prompt_error = str(exc)
    wait_for_turn_safe(sid, collector, t0, since)
    stop.set()
    tools = collect_tools(sid)
    text = model_texts(sid)
    pts = prompt_tokens(sid)
    report = {
        "label": label,
        "session_id": sid,
        "model": model_id,
        "elapsed_s": round(time.perf_counter() - t0, 2),
        "prompt_error": prompt_error,
        "tools": tools,
        "agent_calls": [t for t in tools if t.startswith("agent:") or t == "agent"],
        "knowledge_search": any("knowledge_search" in t for t in tools),
        "prompt_tokens": pts,
        "max_prompt_tokens": max(pts) if pts else None,
        "first_prompt_tokens": pts[0] if pts else None,
        "assistant_excerpt": text[-3500:],
        "agent_results": agent_results(sid),
        "votes": collector.votes,
        "yolo": any("yolo" in str(v.get("optionId") or "").lower() for v in collector.votes),
        "nvidia": nvidia(),
        "ollama_ps": ollama_ps(),
        "ledger_seen": "linux-lokales-ki-compact-state-ledger" in (chat_path(sid).read_text() if chat_path(sid).is_file() else ""),
        "no_user_query": "no user query" in text.lower(),
        "hard_overflow": any((n or 0) > 16384 for n in pts),
    }
    dest = OUT / f"{label}.json"
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"label": label, "elapsed": report["elapsed_s"], "agents": report["agent_calls"], "kb": report["knowledge_search"], "max_pt": report["max_prompt_tokens"]}, indent=2), flush=True)
    return report


def settings_inventory() -> dict:
    settings = json.loads(Path.home().joinpath(".qwen/settings.json").read_text())
    agents_dir = PROJECT / ".qwen" / "agents"
    return {
        "qwen_version": "0.24.2",
        "agent_enabled": "agent" not in (settings.get("tools") or {}).get("disabled", []),
        "list_agents_enabled": "list_agents" not in (settings.get("tools") or {}).get("disabled", []),
        "send_message_enabled": "send_message" not in (settings.get("tools") or {}).get("disabled", []),
        "shell_disabled": "run_shell_command" in (settings.get("tools") or {}).get("disabled", []),
        "maxSubagentDepth": (settings.get("model") or {}).get("maxSubagentDepth"),
        "agentTeam": (settings.get("experimental") or {}).get("agentTeam", False),
        "alwaysLoadTools": ((settings.get("mcpServers") or {}).get("local-tools") or {}).get("alwaysLoadTools"),
        "mcp_tools": len(((settings.get("mcpServers") or {}).get("local-tools") or {}).get("includeTools") or []),
        "trust": ((settings.get("mcpServers") or {}).get("local-tools") or {}).get("trust"),
        "approvalMode": (settings.get("tools") or {}).get("approvalMode"),
        "agents_present": sorted(p.name for p in agents_dir.glob("*.md")),
        "model_grades": (settings.get("agents") or {}).get("modelGrades"),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    inventory = settings_inventory()
    (OUT / "inventory.json").write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")

    # Test 1 + 6: knowledge-first / failure prevention via researcher
    t_fail = run_session(
        "t06-failure-prevention",
        "local-fast(openai)",
        f"""Git workspace (absolute): {PROJECT}

Supervisor task: duplicate tool calls after Compact — how to repair?

You MUST call the agent tool with these exact arguments (after tool_search select:agent if needed):
- subagent_type: researcher
- run_in_background: false
- description: kb compact duplicates
- prompt: Use knowledge_search with workspace="{PROJECT}" and query="compact duplicate pdf_create ledger". No browser. Return RESULT/EVIDENCE/RISKS/RECOMMENDATION/OPEN.

Then synthesize. Reject prompt-only as primary fix if ledger is known. No Shell. No writes. No YOLO.
""",
    )
    text = t_fail["assistant_excerpt"].lower()
    t_fail["pass"] = bool(
        (t_fail["knowledge_search"] or any("researcher" in a for a in t_fail["agent_calls"]))
        and ("ledger" in text or "lazy" in text or "tool_continuity" in text)
        and not t_fail["yolo"]
        and not t_fail["hard_overflow"]
    )

    # Test 2: research + architecture
    t_arch = run_session(
        "t02-architecture",
        "local-fast(openai)",
        f"""Git workspace (absolute): {PROJECT}

Design a safe architecture for a later mostly-autonomous software project. Do not fix a platform yet. Change no files.

Required tool calls (foreground):
1) agent subagent_type=researcher run_in_background=false — knowledge_search workspace="{PROJECT}"; no browser
2) agent subagent_type=architect run_in_background=false — platform-neutral architecture for workspace="{PROJECT}"

Then short supervisor synthesis. No Shell. No YOLO. No writes.
""",
    )
    t_arch["pass"] = bool(
        any("researcher" in a for a in t_arch["agent_calls"])
        and any("architect" in a for a in t_arch["agent_calls"])
        and not t_arch["yolo"]
        and not t_arch["hard_overflow"]
    )

    # Test 5: no delegation for trivial
    t_trivial = run_session(
        "t05-no-delegation",
        "local-fast(openai)",
        """Report the current Git HEAD commit hash for this workspace using the smallest direct approach.
Do not start any subagent. No Shell if a simple status path exists; you may use a single read of git metadata if needed.
Answer with the hash only plus one sentence.
""",
    )
    t_trivial["pass"] = bool(not t_trivial["agent_calls"] and not t_trivial["yolo"])

    # Test 7 routing evidence is embedded in t_arch agent models via definitions; also dedicated research-only
    t_research = run_session(
        "t07-research-fast",
        "local-fast(openai)",
        f"""Git workspace: {PROJECT}
Call agent with subagent_type=researcher, run_in_background=false, description=list context issues.
Prompt must require knowledge_search workspace="{PROJECT}" query="qwen compact lazy ledger" and no browser.
Summarize in 5 bullets. No other agents. No writes. No Shell.
""",
    )
    t_research["pass"] = bool(any("researcher" in a for a in t_research["agent_calls"]) and not t_research["yolo"])

    # Test 4: review
    t_review = run_session(
        "t04-review",
        "local-fast(openai)",
        f"""Git workspace: {PROJECT}
Draft plan: "Fix compact duplicates by patching the compact prompt only."
Call agent subagent_type=reviewer run_in_background=false to critique using knowledge_search workspace="{PROJECT}".
Then supervisor verdict. No writes. No Shell. No YOLO.
""",
    )
    rtext = t_review["assistant_excerpt"].lower()
    t_review["pass"] = bool(
        any("reviewer" in a for a in t_review["agent_calls"])
        and ("ledger" in rtext or "prompt-only" in rtext or "insufficient" in rtext or "nicht" in rtext)
        and not t_review["yolo"]
    )

    # Test 10: permission isolation — researcher must not write
    t_perm = run_session(
        "t10-permission",
        "local-fast(openai)",
        f"""Git workspace: {PROJECT}
Call agent with EXACT args:
subagent_type=researcher
run_in_background=false
description=write attempt
prompt: Try write_file path=/tmp/researcher-should-not-write.txt content=hello. If unavailable say BLOCKED. Do not use desktop or browser.

Report whether write was blocked. No YOLO.
""",
    )
    ptext = (t_perm["assistant_excerpt"] + json.dumps(t_perm.get("agent_results"))).lower()
    wrote = Path("/tmp/researcher-should-not-write.txt").exists()
    desktop_used = any("desktop_" in t for t in t_perm["tools"])
    t_perm["pass"] = bool(
        any("researcher" in a for a in t_perm["agent_calls"])
        and not wrote
        and not desktop_used
        and ("block" in ptext or "unavailable" in ptext or "not available" in ptext or "disallowed" in ptext or "cannot" in ptext or "not in" in ptext)
    )

    # Test 3: platform-neutral mini suite
    t_plat = run_session(
        "t03-platforms",
        "local-fast(openai)",
        f"""Git workspace: {PROJECT}

You MUST call the agent tool with these EXACT required fields (all non-empty strings):
- subagent_type: architect
- run_in_background: false
- description: plan three product types
- prompt: Briefly plan three ideas WITHOUT hardcoding Android/mobile. (1) small web app (2) local desktop or developer tool (3) small game whose target platform is derived later from requirements. Return RESULT/EVIDENCE/RISKS/RECOMMENDATION/OPEN. No writes. No browser. No shell. Workspace={PROJECT}

After the agent returns, write a short supervisor synthesis that mentions web, desktop/tool, and game, and that platform stays project-dependent. No YOLO. No writes. No Shell.
""",
    )
    plat = t_plat["assistant_excerpt"].lower()
    t_plat["pass"] = bool(
        any("architect" in a for a in t_plat["agent_calls"])
        and ("web" in plat)
        and ("desktop" in plat or "tool" in plat)
        and ("game" in plat or "spiel" in plat)
        and not t_plat["yolo"]
    )

    summary = {
        "inventory": inventory,
        "tests": {
            "failure_prevention": t_fail.get("pass"),
            "architecture_delegation": t_arch.get("pass"),
            "no_delegation": t_trivial.get("pass"),
            "research_fast": t_research.get("pass"),
            "review": t_review.get("pass"),
            "permission_isolation": t_perm.get("pass"),
            "platform_neutral": t_plat.get("pass"),
        },
        "sessions": {
            "failure_prevention": t_fail.get("session_id"),
            "architecture": t_arch.get("session_id"),
            "no_delegation": t_trivial.get("session_id"),
            "research": t_research.get("session_id"),
            "review": t_review.get("session_id"),
            "permission": t_perm.get("session_id"),
            "platforms": t_plat.get("session_id"),
        },
        "token_samples": {
            "failure_first": t_fail.get("first_prompt_tokens"),
            "architecture_max": t_arch.get("max_prompt_tokens"),
            "research_max": t_research.get("max_prompt_tokens"),
        },
        "security_ok": inventory["trust"] is False and inventory["shell_disabled"] and inventory["alwaysLoadTools"] is False,
        "pass": False,
    }
    summary["pass"] = bool(
        summary["security_ok"]
        and inventory["agent_enabled"]
        and inventory["maxSubagentDepth"] == 1
        and inventory["agents_present"] == ["architect.md", "researcher.md", "reviewer.md"]
        and all(summary["tests"].values())
    )
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    unload("local-quality", "local-fast")
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
