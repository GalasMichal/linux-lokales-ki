"""On-demand CPU MoE consult via llama-cli (no daemon, no systemd)."""

from __future__ import annotations

import atexit
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from errors import ToolError

LLAMA_CLI = Path("/srv/ai/apps/llama.cpp-0.5.0/llama-cli")
GGUF_PATH = Path(
    "/srv/ai/models/gguf/qwen3-coder-30b-a3b/"
    "Qwen3-Coder-30B-A3B-Instruct-Q4_K_S.gguf"
)
CACHE_DIR = Path("/srv/ai/cache/moe_consult")
LOCK_PATH = CACHE_DIR / "moe_consult.lock"

# Hard floor: refuse start when free RAM is critically low (kB).
MIN_MEM_AVAILABLE_KB = 8_000_000  # 8 GiB
# Soft warning threshold (still allowed).
WARN_MEM_AVAILABLE_KB = 12_000_000  # 12 GiB

DEFAULT_THREADS = 16
DEFAULT_CTX = 4096
DEFAULT_TIMEOUT_S = 300
MAX_TIMEOUT_S = 420
MAX_CONTEXT_CHARS = 12_000
MAX_TASK_CHARS = 6_000

ALLOWED_ROLES = frozenset(
    {"planner", "reviewer", "architect", "supervisor", "second_opinion"}
)

ROLE_DEFAULT_TOKENS: dict[str, int] = {
    "planner": 512,
    "reviewer": 640,
    "architect": 640,
    "supervisor": 512,
    "second_opinion": 384,
}

ROLE_SYSTEM: dict[str, str] = {
    "planner": (
        "You are a concise planning specialist. Propose a short, ordered plan. "
        "No shell. No YOLO. Prefer smallest safe change. Second opinion only."
    ),
    "reviewer": (
        "You are a concise code/review QA specialist. List risks, missing checks, "
        "and acceptance gaps. Second opinion only — not authoritative."
    ),
    "architect": (
        "You are a concise architecture specialist. Tradeoffs and smallest-safe path. "
        "Platform-neutral unless forced. Second opinion only."
    ),
    "supervisor": (
        "You are a concise supervisor. Decompose work, name risks, suggest which "
        "role should act next. Second opinion only — main agent decides."
    ),
    "second_opinion": (
        "You are a concise second opinion. Challenge assumptions briefly. "
        "Do not claim authority over the main agent."
    ),
}

_active_proc: subprocess.Popen[str] | None = None


def _cleanup_active() -> None:
    global _active_proc
    proc = _active_proc
    if proc is None:
        return
    _kill_tree(proc)
    _active_proc = None


atexit.register(_cleanup_active)


def _meminfo() -> dict[str, int]:
    out: dict[str, int] = {}
    with open("/proc/meminfo", encoding="utf-8") as fh:
        for line in fh:
            key, _, rest = line.partition(":")
            num = rest.strip().split()[0]
            try:
                out[key] = int(num)
            except ValueError:
                continue
    return out


def _resource_snapshot() -> dict[str, Any]:
    info = _meminfo()
    swap_total = info.get("SwapTotal", 0)
    swap_free = info.get("SwapFree", 0)
    return {
        "mem_available_kb": info.get("MemAvailable", 0),
        "mem_total_kb": info.get("MemTotal", 0),
        "swap_used_kb": max(0, swap_total - swap_free),
        "swap_free_kb": swap_free,
        "swap_total_kb": swap_total,
    }


def _find_moe_procs() -> list[dict[str, Any]]:
    """Find our on-demand llama.cpp MoE processes (not Ollama's llama-server)."""
    found: list[dict[str, Any]] = []
    our_roots = (
        "/srv/ai/apps/llama.cpp",
        str(GGUF_PATH.parent),
        "qwen3-coder-30b-a3b",
    )
    try:
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            try:
                exe = os.readlink(entry / "exe")
            except (OSError, PermissionError):
                continue
            exe_name = Path(exe).name
            if exe_name not in {"llama-cli", "llama-server"}:
                continue
            try:
                cmdline = (entry / "cmdline").read_bytes().replace(b"\x00", b" ").decode(
                    "utf-8", errors="replace"
                )
            except (OSError, PermissionError):
                cmdline = ""
            blob = f"{exe} {cmdline}"
            if not any(marker in blob for marker in our_roots):
                continue
            found.append({"pid": pid, "exe": exe, "cmdline": cmdline[:400]})
    except OSError:
        pass
    return found


def _kill_tree(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.terminate()
        except Exception:
            pass
    deadline = time.time() + 8
    while time.time() < deadline:
        if proc.poll() is not None:
            return
        time.sleep(0.2)
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except Exception:
            pass
    try:
        proc.wait(timeout=5)
    except Exception:
        pass


def _read_lock() -> dict[str, Any] | None:
    if not LOCK_PATH.is_file():
        return None
    try:
        data = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    pid = data.get("pid")
    if isinstance(pid, int) and Path(f"/proc/{pid}").exists():
        return data
    try:
        LOCK_PATH.unlink(missing_ok=True)
    except OSError:
        pass
    return None


def _write_lock(pid: int) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": pid,
        "started_at": time.time(),
        "gguf": str(GGUF_PATH),
    }
    LOCK_PATH.write_text(json.dumps(payload), encoding="utf-8")


def _clear_lock() -> None:
    try:
        LOCK_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def _clamp_tokens(role: str, max_tokens: int | None) -> int:
    default = ROLE_DEFAULT_TOKENS.get(role, 384)
    if max_tokens is None:
        return default
    try:
        n = int(max_tokens)
    except (TypeError, ValueError) as exc:
        raise ToolError(f"max_tokens must be an integer, got {max_tokens!r}") from exc
    return max(64, min(768, n))


def _build_user_prompt(task: str, context: str) -> str:
    parts = ["TASK:", task.strip()]
    ctx = (context or "").strip()
    if ctx:
        parts.extend(["", "CONTEXT:", ctx[:MAX_CONTEXT_CHARS]])
    parts.extend(
        [
            "",
            "Reply in compact bullets. Second opinion only; main agent verifies.",
        ]
    )
    return "\n".join(parts)


def _extract_answer(stdout: str, user_prompt: str = "") -> str:
    """Strip llama-cli spinner/banner; keep model answer (same approach as MoE benches)."""
    import re

    raw = stdout or ""
    parts = re.split(r"\n> ", raw, maxsplit=1)
    if len(parts) == 2:
        body = parts[1]
        prompt = (user_prompt or "").strip()
        if prompt:
            # Multi-line prompts are fully echoed after "> "; strip that echo.
            # Tolerate minor trailing whitespace differences.
            stripped = body.lstrip("\n")
            if stripped.startswith(prompt):
                body = stripped[len(prompt) :].lstrip("\n")
            else:
                # Fallback: drop first line only (single-line prompts).
                lines = body.split("\n", 1)
                body = lines[1] if len(lines) == 2 else body
        else:
            lines = body.split("\n", 1)
            body = lines[1] if len(lines) == 2 else body
        body = re.split(r"\n\[\s*Prompt:", body)[0].strip()
        body = re.split(r"\nExiting", body)[0].strip()
        return body

    text = raw.replace("\x08", "")
    text = re.sub(r"(?is)^.*?Loading model\.\.\.\s*[|/\-\s]*", "", text, count=1)
    text = re.split(r"\n\[\s*Prompt:", text)[0].strip()
    text = re.split(r"\nExiting", text)[0].strip()
    if "available commands:" in text.lower():
        return ""
    return text.strip()


def _clamp_timeout(timeout_s: int | None) -> int:
    if timeout_s is None:
        return DEFAULT_TIMEOUT_S
    try:
        n = int(timeout_s)
    except (TypeError, ValueError) as exc:
        raise ToolError(f"timeout_s must be an integer, got {timeout_s!r}") from exc
    # Explicit short timeouts are allowed for cleanup tests; floor is 2s.
    return max(2, min(MAX_TIMEOUT_S, n))


def moe_consult(
    task: str,
    role: str = "second_opinion",
    context: str = "",
    max_tokens: int | None = None,
    timeout_s: int | None = None,
) -> dict[str, Any]:
    """Run one on-demand CPU MoE consult and always tear the process down."""
    global _active_proc

    started = time.time()
    role_norm = (role or "second_opinion").strip().lower()
    if role_norm not in ALLOWED_ROLES:
        raise ToolError(
            f"role must be one of {sorted(ALLOWED_ROLES)}, got {role!r}"
        )

    task_s = (task or "").strip()
    if not task_s:
        raise ToolError("task must be non-empty")
    if len(task_s) > MAX_TASK_CHARS:
        raise ToolError(f"task too long (max {MAX_TASK_CHARS} chars)")

    n_predict = _clamp_tokens(role_norm, max_tokens)
    timeout = _clamp_timeout(timeout_s)

    if not LLAMA_CLI.is_file():
        raise ToolError(f"llama-cli missing: {LLAMA_CLI}")
    if not GGUF_PATH.is_file():
        raise ToolError(f"GGUF missing: {GGUF_PATH}")

    before = _resource_snapshot()
    existing = _find_moe_procs()
    lock = _read_lock()
    if lock or existing:
        raise ToolError(
            "MoE already running — refuse second parallel consult. "
            f"lock={lock} procs={existing}"
        )

    if before["mem_available_kb"] < MIN_MEM_AVAILABLE_KB:
        raise ToolError(
            "MemAvailable too low for CPU MoE "
            f"({before['mem_available_kb']} kB < {MIN_MEM_AVAILABLE_KB} kB). "
            "Free RAM or retry later."
        )

    warn_low_ram = before["mem_available_kb"] < WARN_MEM_AVAILABLE_KB
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    prompt_path = CACHE_DIR / f"prompt-{os.getpid()}-{int(started)}.txt"
    user_prompt_text = _build_user_prompt(task_s, context or "")
    prompt_path.write_text(user_prompt_text, encoding="utf-8")

    env = os.environ.copy()
    lib_dir = LLAMA_CLI.resolve().parent / "llama-b11146"
    if lib_dir.is_dir():
        prev = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = f"{lib_dir}:{prev}" if prev else str(lib_dir)

    cmd = [
        str(LLAMA_CLI),
        "-m",
        str(GGUF_PATH),
        "-ngl",
        "0",
        "-t",
        str(DEFAULT_THREADS),
        "-c",
        str(DEFAULT_CTX),
        "-n",
        str(n_predict),
        "--temp",
        "0.2",
        "--jinja",
        "--reasoning",
        "off",
        "-st",
        "--no-display-prompt",
        "-sys",
        ROLE_SYSTEM[role_norm],
        "-f",
        str(prompt_path),
    ]

    rc = -1
    stdout = ""
    stderr = ""
    timed_out = False
    killed = False
    answer = ""
    after: dict[str, Any] = {}
    leftover: list[dict[str, Any]] = []

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            start_new_session=True,
        )
        _active_proc = proc
        _write_lock(proc.pid)
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            rc = proc.returncode if proc.returncode is not None else -1
        except subprocess.TimeoutExpired:
            timed_out = True
            killed = True
            _kill_tree(proc)
            try:
                stdout, stderr = proc.communicate(timeout=10)
            except Exception:
                stdout, stderr = "", ""
            rc = proc.returncode if proc.returncode is not None else -9
    finally:
        _active_proc = None
        _clear_lock()
        try:
            prompt_path.unlink(missing_ok=True)
        except OSError:
            pass
        # Extra sweep: any leftover matching procs.
        leftover = _find_moe_procs()
        for item in leftover:
            pid = item.get("pid")
            if isinstance(pid, int):
                try:
                    os.kill(pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError, OSError):
                    pass
        if leftover:
            time.sleep(1.0)
            for item in _find_moe_procs():
                pid = item.get("pid")
                if isinstance(pid, int):
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError, OSError):
                        pass
        leftover = _find_moe_procs()
        after = _resource_snapshot()

    answer = _extract_answer(stdout, user_prompt=user_prompt_text)
    ended = time.time()
    result: dict[str, Any] = {
        "ok": bool(answer) and not timed_out and rc == 0 and not leftover,
        "role": role_norm,
        "answer": answer,
        "second_opinion_only": True,
        "authority": "advisory",
        "hint": (
            "CPU-MoE is a second opinion only. Verify against code/tests before applying."
        ),
        "runtime": {
            "started_at": started,
            "ended_at": ended,
            "elapsed_s": round(ended - started, 3),
            "rc": rc,
            "timed_out": timed_out,
            "killed": killed,
            "n_predict": n_predict,
            "threads": DEFAULT_THREADS,
            "ctx": DEFAULT_CTX,
            "ngl": 0,
            "timeout_s": timeout,
            "model": str(GGUF_PATH),
            "cli": str(LLAMA_CLI),
        },
        "resources": {
            "before": before,
            "after": after,
            "warn_low_ram": warn_low_ram,
            "leftover_procs": leftover,
            "lock_cleared": not LOCK_PATH.exists(),
        },
    }
    if timed_out:
        result["ok"] = False
        result["error"] = f"MoE consult timed out after {timeout}s; process killed"
    elif leftover:
        result["ok"] = False
        result["error"] = f"MoE leftover process after cleanup: {leftover}"
    elif rc != 0 and not answer:
        err = (stderr or "").strip()[-800:]
        result["ok"] = False
        result["error"] = f"llama-cli failed rc={rc}: {err or 'no stderr'}"
    elif not answer:
        result["ok"] = False
        result["error"] = "MoE returned empty answer"
        if stderr:
            result["stderr_tail"] = stderr.strip()[-500:]
    return result
