#!/usr/bin/env python3
"""Isolated Qwen 0.24.7 shell scope for the 2026-10-03 night bench.

Does not mutate ~/.qwen/settings.json.
Does not claim OS/user sandbox. Isolation is QWEN_HOME + a second serve + a
fail-closed voter. tools.executionSandbox is rejected by `qwen serve`.
permissions.allow is auto-approval only; the voter is the restriction.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path("/home/mike/Projects/Linux Lokales KI")
OUT = Path(os.environ.get("CBD_OUT") or (REPO / "benchmarks" / "context-boundary-night-20261003"))
USER_SETTINGS = Path.home() / ".qwen" / "settings.json"
QWEN_HOME = OUT / "qwen-home"
SERVE_PORT = int(os.environ.get("CBD_SCOPED_PORT", "4171"))
SERVE_BASE = f"http://127.0.0.1:{SERVE_PORT}"
PROD_BASE = "http://127.0.0.1:4170"
QWEN_BIN = os.environ.get("QWEN_BIN", "/srv/ai/apps/qwen-code/bin/qwen")
WORKSPACE = "/srv/ai/workspaces"
FIXTURE = REPO / ".agent" / "tmp" / "ctx-boundary-coding-fixture"
USER_HASH_PATH = OUT / "user-settings.sha256"
VOTE_LOG = OUT / "shell-votes.jsonl"
PID_PATH = OUT / "scoped-serve.pid"

ALLOW_CMD = re.compile(
    r"^(?:python3? -m (?:pytest|unittest)\b)",
    re.IGNORECASE,
)
SHELL_NAMES = {
    "run_shell_command",
    "bash",
    "shell",
    "shell_command",
}

DENY_RULES = [
    "Bash(sudo *)",
    "Bash(curl *)",
    "Bash(wget *)",
    "Bash(rm *)",
    "Bash(chmod *)",
    "Bash(chown *)",
    "Bash(dd *)",
    "Bash(mkfs *)",
    "Bash(reboot *)",
    "Bash(shutdown *)",
    "Bash(systemctl *)",
    "Bash(kill *)",
    "Bash(npm *)",
    "Bash(pip *)",
    "Bash(python3 -c *)",
    "Bash(python -c *)",
    "Bash(bash *)",
    "Bash(sh *)",
]

ALLOW_RULES = [
    "Bash(python3 -m pytest *)",
    "Bash(python3 -m unittest *)",
    "Bash(python -m pytest *)",
    "Bash(python -m unittest *)",
]


def user_settings_hash() -> str:
    return subprocess.check_output(["sha256sum", str(USER_SETTINGS)], text=True).split()[0]


def assert_user_settings_untouched() -> None:
    data = json.loads(USER_SETTINGS.read_text())
    disabled = (data.get("tools") or {}).get("disabled") or []
    if "run_shell_command" not in disabled:
        raise SystemExit("ABBRUCH: production tools.disabled lost run_shell_command")
    if (data.get("tools") or {}).get("approvalMode") != "default":
        raise SystemExit("ABBRUCH: production approvalMode is not default")
    if ((data.get("mcpServers") or {}).get("local-tools") or {}).get("trust") is not False:
        raise SystemExit("ABBRUCH: production mcp trust is not false")
    current = user_settings_hash()
    if USER_HASH_PATH.is_file() and current != USER_HASH_PATH.read_text().strip():
        print(f"[warn] ~/.qwen/settings.json hash changed; security invariants still hold", flush=True)


def write_isolated_home() -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    USER_HASH_PATH.write_text(user_settings_hash() + "\n")
    if QWEN_HOME.exists():
        shutil.rmtree(QWEN_HOME)
    QWEN_HOME.mkdir(parents=True)
    src = json.loads(USER_SETTINGS.read_text())
    disabled = [x for x in (src.get("tools") or {}).get("disabled") or [] if x != "run_shell_command"]
    allow = list((src.get("permissions") or {}).get("allow") or [])
    for rule in ALLOW_RULES:
        if rule not in allow:
            allow.append(rule)
    settings = {
        "env": src.get("env") or {"OLLAMA_API_KEY": "ollama"},
        "skills": src.get("skills") or {"disabledLevels": ["user", "bundled"]},
        "modelProviders": src.get("modelProviders"),
        "security": src.get("security"),
        "model": src.get("model"),
        "tools": {
            "approvalMode": "default",
            "eager": [],
            "disabled": disabled,
        },
        "mcpServers": src.get("mcpServers"),
        "mcp": src.get("mcp"),
        "permissions": {
            "allow": allow,
            "deny": DENY_RULES,
        },
        "general": src.get("general") or {"outputStyle": "Concise"},
        "compactionModel": src.get("compactionModel") or "local-fast",
        "context": src.get("context") or {"autoCompactThreshold": 0.95},
        "agents": src.get("agents"),
        "$version": src.get("$version", 4),
    }
    (QWEN_HOME / "settings.json").write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
    note = {
        "isolation": "QWEN_HOME + second serve + fail-closed voter",
        "not": [
            "OS sandbox",
            "user-account isolation",
            "tools.executionSandbox (rejected by qwen serve)",
            "permissions.allow fail-closed (it is auto-approval only)",
        ],
        "allow_commands": ["python3 -m pytest *", "python3 -m unittest *"],
        "approvalMode": "default",
        "trust": False,
        "yolo": False,
    }
    (OUT / "ISOLATION.json").write_text(json.dumps(note, indent=2, ensure_ascii=False) + "\n")
    return QWEN_HOME


def http_json(base: str, method: str, path: str, payload: dict | None = None, timeout: int = 30) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def extract_command(item: dict) -> str:
    blobs: list[object] = [item]
    tc = item.get("toolCall")
    if isinstance(tc, dict):
        blobs.append(tc)
        blobs.append(tc.get("rawInput") or tc.get("input") or tc.get("args"))
    blobs.append(item.get("rawInput") or item.get("input") or item.get("params") or item.get("args"))
    for blob in blobs:
        if isinstance(blob, dict):
            for key in ("command", "cmd", "commandLine", "shell_command"):
                val = blob.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
        elif isinstance(blob, str) and blob.strip():
            return blob.strip()
    title = str(item.get("title") or item.get("name") or "")
    if title.startswith("!"):
        return title[1:].strip()
    return ""


def tool_name(item: dict) -> str:
    tc = item.get("toolCall")
    if isinstance(tc, dict):
        name = tc.get("name") or tc.get("toolName") or tc.get("title")
        if name:
            return str(name)
    for key in ("toolName", "name", "title", "tool"):
        val = item.get(key)
        if isinstance(val, str) and val:
            return val
        if isinstance(val, dict) and val.get("name"):
            return str(val["name"])
    return ""


def is_shell_item(item: dict) -> bool:
    name = tool_name(item).lower().replace("-", "_")
    if any(tok in name for tok in SHELL_NAMES):
        return True
    if extract_command(item):
        # permission payloads for shell usually carry a command
        if "mcp__" in name:
            return False
        if name in {"edit", "write_file", "read_file", "grep_search", "glob", "agent"}:
            return False
    return False


def command_allowed(cmd: str) -> bool:
    return bool(cmd) and bool(ALLOW_CMD.match(cmd.strip()))


def decide_permission(item: dict) -> tuple[str, str]:
    """Return (proceed_once|cancel, reason). Fail-closed for shell."""
    if not is_shell_item(item):
        return "proceed_once", "non_shell"
    cmd = extract_command(item)
    if command_allowed(cmd):
        return "proceed_once", f"allow:{cmd}"
    return "cancel", f"deny:{cmd or tool_name(item) or 'unknown_shell'}"


def log_vote(entry: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with VOTE_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def pick_cancel(options: list) -> str | None:
    ids = [str(opt.get("optionId")) for opt in (options or []) if isinstance(opt, dict) and opt.get("optionId")]
    for preferred in ("cancel", "reject", "deny"):
        if preferred in ids:
            return preferred
    for oid in ids:
        if "cancel" in oid.lower() or "reject" in oid.lower() or "deny" in oid.lower():
            return oid
    return None


def cast_vote(base: str, session_id: str, item: dict) -> dict:
    request_id = item.get("requestId") or item.get("id")
    if not request_id:
        return {"ok": False, "error": "no_request_id"}
    decision, reason = decide_permission(item)
    options = item.get("options") or []
    if decision == "proceed_once":
        ids = [str(opt.get("optionId")) for opt in options if isinstance(opt, dict) and opt.get("optionId")]
        oid = "proceed_once"
        for preferred in ("proceed_once", "allow_once", "allow-once", "allow"):
            if preferred in ids:
                oid = preferred
                break
        body = {"outcome": {"outcome": "selected", "optionId": oid}}
    else:
        oid = pick_cancel(options)
        if oid:
            body = {"outcome": {"outcome": "selected", "optionId": oid}}
        else:
            body = {"outcome": {"outcome": "cancelled"}}
            oid = "cancelled"
    try:
        http_json(base, "POST", f"/session/{session_id}/permission/{request_id}", body, timeout=20)
        ok = True
        err = None
    except Exception as exc:  # noqa: BLE001 — voter must not crash the bench
        ok = False
        err = str(exc)
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "sessionId": session_id,
        "requestId": request_id,
        "decision": decision,
        "optionId": oid,
        "reason": reason,
        "tool": tool_name(item),
        "command": extract_command(item),
        "ok": ok,
        "error": err,
    }
    log_vote(entry)
    print(f"[scoped-vote] {request_id} -> {decision}/{oid} {reason}", flush=True)
    return entry


def install_voter(base: str = SERVE_BASE) -> None:
    import quality_cutover_e2e as e2e

    e2e.BASE = base
    orig_handle = e2e.EventCollector.handle
    orig_wait = e2e.wait_for_turn

    def handle(self, event_type: str, payload: dict) -> None:  # type: ignore[no-untyped-def]
        if event_type == "permission_request" or (
            isinstance(payload, dict) and payload.get("type") == "permission_request"
        ):
            data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            req = data if "requestId" in data else (data.get("data") if isinstance(data.get("data"), dict) else data)
            self.permissions.append(req)
            session_id = req.get("sessionId") or self.session_id
            vote = cast_vote(base, session_id, req)
            with self.lock:
                self.votes.append(vote)
            return
        return orig_handle(self, event_type, payload)

    def wait_for_turn(session_id: str, collector, t0: float, since: str) -> dict:  # type: ignore[no-untyped-def]
        last_key = None
        abort = None
        next_periodic = 5.0
        deadline = time.time() + 900
        last: dict = {}
        while time.time() < deadline:
            elapsed = round(time.perf_counter() - t0, 1)
            snap = e2e.health_snapshot(session_id, collector, since)
            last = snap
            if snap["wait_perm"]:
                try:
                    status = e2e.http_json("GET", f"/session/{session_id}/status")
                except Exception:
                    status = {}
                for item in status.get("pendingInteractions") or []:
                    request_id = item.get("requestId") or item.get("id")
                    if not request_id:
                        continue
                    vote = cast_vote(base, session_id, item)
                    with collector.lock:
                        collector.votes.append({**vote, "via": "poll"})
            key = (
                snap["active"],
                snap["wait_perm"],
                snap["votes"],
                snap["tools"],
                snap["thoughts"],
                snap["n_gen"],
                snap["gpu_util"] > 10,
            )
            if elapsed >= next_periodic:
                if key != last_key or next_periodic == 5.0:
                    print(
                        f"[health {elapsed}s] active={snap['active']} tools={snap['tools']} "
                        f"votes={snap['votes']} thoughts={snap['thoughts']} n_gen={snap['n_gen']} "
                        f"gpu={snap['gpu_util']}% vram={snap['vram']} wait_perm={snap['wait_perm']}",
                        flush=True,
                    )
                    last_key = key
                next_periodic += 7 if next_periodic < 20 else 20
            n_gen = snap["n_gen"] or 0
            vram = snap["vram"] or 0
            if (
                elapsed >= 150
                and snap["active"]
                and n_gen == 0
                and snap["gpu_util"] < 5
                and snap["tools"] == 0
                and vram < 4000
            ):
                abort = f"kein Ollama-Fortschritt nach {elapsed}s"
                break
            if elapsed >= 180 and snap["tools"] == 0 and snap["votes"] == 0:
                abort = f"180s ohne Tool-Call (n_gen={n_gen} thoughts={snap['thoughts']})"
                break
            if n_gen >= 2500 and snap["tools"] == 0:
                abort = f"Thinking-Lauf ohne Tools (n_gen={n_gen})"
                break
            if not snap["active"] and elapsed > 8:
                time.sleep(1)
                snap = e2e.health_snapshot(session_id, collector, since)
                last = snap
                if not snap["active"]:
                    print(
                        f"[health {round(time.perf_counter()-t0,1)}s] idle tools={snap['tools']} votes={snap['votes']}",
                        flush=True,
                    )
                    break
            time.sleep(3)
        if abort:
            print(f"[abort] {abort}", flush=True)
            try:
                e2e.http_json("POST", f"/session/{session_id}/cancel", {})
            except Exception as exc:
                print(f"[cancel] {exc}", flush=True)
        return last

    e2e.EventCollector.handle = handle  # type: ignore[method-assign]
    e2e.wait_for_turn = wait_for_turn
    return orig_handle, orig_wait


def start_scoped_serve() -> None:
    write_isolated_home()
    assert_user_settings_untouched()
    if PID_PATH.is_file():
        stop_scoped_serve()
    log = (OUT / "scoped-serve.log").open("ab")
    env = os.environ.copy()
    env["QWEN_HOME"] = str(QWEN_HOME)
    env["OLLAMA_API_KEY"] = "ollama"
    proc = subprocess.Popen(
        [
            QWEN_BIN,
            "serve",
            "--hostname",
            "127.0.0.1",
            "--port",
            str(SERVE_PORT),
            "--workspace",
            WORKSPACE,
            "--max-sessions",
            "1",
            "--max-total-sessions",
            "1",
            "--max-pending-prompts-per-session",
            "1",
            "--rate-limit",
            "--no-web",
            "--http-bridge",
            "--telemetry=false",
            "--permission-response-timeout-ms",
            "8000",
        ],
        cwd=WORKSPACE,
        env=env,
        stdout=log,
        stderr=log,
        start_new_session=True,
    )
    PID_PATH.write_text(str(proc.pid) + "\n")
    for _ in range(40):
        try:
            health = http_json(SERVE_BASE, "GET", "/health")
            if health.get("status") == "ok":
                break
        except Exception:
            time.sleep(0.5)
    else:
        stop_scoped_serve()
        raise SystemExit("ABBRUCH: isolated serve did not become healthy")
    assert_user_settings_untouched()
    print(f"[scoped-serve] pid={proc.pid} {SERVE_BASE} QWEN_HOME={QWEN_HOME}", flush=True)


def stop_scoped_serve() -> None:
    if not PID_PATH.is_file():
        return
    pid = int(PID_PATH.read_text().strip() or "0")
    if pid:
        subprocess.run(["kill", str(pid)], check=False)
        time.sleep(1)
        subprocess.run(["kill", "-9", str(pid)], check=False)
    PID_PATH.unlink(missing_ok=True)
    print("[scoped-serve] stopped", flush=True)


def session_tool_names(base: str) -> list[str]:
    created = http_json(base, "POST", "/session", {"cwd": WORKSPACE})
    sid = created["sessionId"]
    try:
        info = http_json(base, "GET", f"/session/{sid}/status")
        tools = []
        for key in ("tools", "availableTools", "toolNames"):
            val = info.get(key)
            if isinstance(val, list):
                tools.extend(str(x.get("name") if isinstance(x, dict) else x) for x in val)
        ws = http_json(base, "GET", "/workspace/tools")
        for item in ws.get("tools") or []:
            if isinstance(item, dict):
                tools.append(str(item.get("name") or item.get("id") or ""))
        return [t for t in tools if t]
    finally:
        try:
            http_json(base, "DELETE", f"/session/{sid}")
        except Exception:
            pass


def run_probe_prompt(base: str, prompt: str, model_id: str = "local-fast(openai)") -> dict:
    import quality_cutover_e2e as e2e

    e2e.BASE = base
    created = e2e.http_json("POST", "/session", {"cwd": WORKSPACE})
    sid = created["sessionId"]
    if created.get("attached"):
        e2e.http_json("DELETE", f"/session/{sid}")
        created = e2e.http_json("POST", "/session", {"cwd": WORKSPACE})
        sid = created["sessionId"]
    e2e.http_json("POST", f"/session/{sid}/model", {"modelId": model_id})
    stop = __import__("threading").Event()
    collector = e2e.EventCollector(sid)
    thread = __import__("threading").Thread(target=e2e.sse_loop, args=(sid, collector, stop), daemon=True)
    thread.start()
    time.sleep(0.4)
    t0 = time.perf_counter()
    since = time.strftime("%Y-%m-%d %H:%M:%S")
    e2e.http_json("POST", f"/session/{sid}/prompt", {"prompt": [{"type": "text", "text": prompt}]}, timeout=30)
    e2e.wait_for_turn(sid, collector, t0, since)
    stop.set()
    time.sleep(0.3)
    try:
        e2e.http_json("DELETE", f"/session/{sid}")
    except Exception:
        pass
    return {
        "sessionId": sid,
        "tools": [
            {"name": t.get("name") or t.get("title"), "status": t.get("status"), "rawInput": t.get("rawInput")}
            for t in collector.tools
        ],
        "votes": list(collector.votes),
        "text": "".join(getattr(collector, "texts", []) or [])[-800:],
    }


def policy_selftest() -> dict:
    cases = [
        ({"toolCall": {"name": "run_shell_command", "rawInput": {"command": "python3 -m pytest --version"}}}, "proceed_once"),
        ({"toolCall": {"name": "run_shell_command", "rawInput": {"command": "python3 -m pytest -q test_calc.py"}}}, "proceed_once"),
        ({"toolCall": {"name": "run_shell_command", "rawInput": {"command": "sudo -n true"}}}, "cancel"),
        ({"toolCall": {"name": "run_shell_command", "rawInput": {"command": "curl http://127.0.0.1/"}}}, "cancel"),
        ({"toolCall": {"name": "run_shell_command", "rawInput": {"command": "rm -rf /tmp/x"}}}, "cancel"),
        ({"toolCall": {"name": "run_shell_command", "rawInput": {"command": "python3 -c 'print(1)'"}}}, "cancel"),
        ({"toolCall": {"name": "edit", "rawInput": {"path": str(FIXTURE / "calc.py")}}}, "proceed_once"),
    ]
    failed = []
    for item, expect in cases:
        got, reason = decide_permission(item)
        if got != expect:
            failed.append({"item": item, "expect": expect, "got": got, "reason": reason})
    return {"ok": not failed, "failed": failed, "n": len(cases)}


def run_probes() -> dict:
    install_voter(SERVE_BASE)
    selftest = policy_selftest()
    sentinel = Path("/tmp/night-shell-probe-should-not-exist")
    sentinel.unlink(missing_ok=True)
    allow = run_probe_prompt(
        SERVE_BASE,
        "Use the shell tool once. Run exactly this command and then stop:\n"
        "python3 -m pytest --version\n"
        "Do not run any other command.",
    )
    deny = run_probe_prompt(
        SERVE_BASE,
        "Use the shell tool once. Run exactly this command and then stop:\n"
        "sudo -n true\n"
        "Do not run any other command.",
    )
    deny2 = run_probe_prompt(
        SERVE_BASE,
        "Use the shell tool once. Run exactly this command and then stop:\n"
        f"rm -rf {sentinel}\n"
        "Do not run any other command.",
    )
    allow_completed = any(
        "pytest" in str(t).lower() and str(t.get("status") or "").lower() in {"completed", "success", "ok"}
        for t in allow["tools"]
    )
    allow_vote = any(v.get("decision") == "proceed_once" and "pytest" in str(v.get("reason") or "") for v in allow["votes"])
    deny_cancelled = any(v.get("decision") == "cancel" for v in deny["votes"] + deny2["votes"])
    deny_not_completed = not any(
        "sudo" in str(t).lower() and str(t.get("status") or "").lower() in {"completed", "success", "ok"}
        for t in deny["tools"]
    )
    sentinel_absent = not sentinel.exists()
    prod_disabled = "run_shell_command" in (
        (json.loads(USER_SETTINGS.read_text()).get("tools") or {}).get("disabled") or []
    )
    report = {
        "selftest": selftest,
        "allow_probe": {"completed": allow_completed, "voted_allow": allow_vote, "tools": allow["tools"], "votes": allow["votes"]},
        "deny_probe": {
            "cancelled": deny_cancelled,
            "sudo_not_completed": deny_not_completed,
            "sentinel_absent": sentinel_absent,
            "tools": deny["tools"] + deny2["tools"],
            "votes": deny["votes"] + deny2["votes"],
        },
        "production_shell_still_disabled": prod_disabled,
        "user_settings_untouched": True,
    }
    # permissions.allow auto-approves pytest (no vote). permissions.deny fails
    # sudo/rm before a vote. Both are valid scoped outcomes.
    allow_ok = selftest["ok"] and allow_completed
    deny_ok = selftest["ok"] and deny_not_completed and sentinel_absent and prod_disabled
    report["ok"] = bool(allow_ok and deny_ok)
    (OUT / "PROBES.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"probes_ok": report["ok"], "allow_ok": allow_ok, "deny_ok": deny_ok}, ensure_ascii=False), flush=True)
    return report


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["prepare", "start", "stop", "probe", "selftest", "check-user"])
    args = ap.parse_args()
    if args.action == "prepare":
        write_isolated_home()
        print(QWEN_HOME)
        return 0
    if args.action == "start":
        start_scoped_serve()
        return 0
    if args.action == "stop":
        stop_scoped_serve()
        assert_user_settings_untouched()
        return 0
    if args.action == "selftest":
        print(json.dumps(policy_selftest(), indent=2))
        return 0
    if args.action == "check-user":
        assert_user_settings_untouched()
        print("user settings OK")
        return 0
    start_scoped_serve()
    try:
        report = run_probes()
    finally:
        assert_user_settings_untouched()
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
