#!/usr/bin/env python3
"""Qwen Code 0.24.2 compact-continuity prompt patch.

Adds one section inside the existing <state_snapshot> and changes the
resume trailer so a successful tool is not treated as still in flight.
Does not touch ToolSearch, the MCP registry, or the git-snapshot patch.
"""
from __future__ import annotations

import sys
from pathlib import Path

MARKER = "linux-lokales-ki-compact-continuity"
PROMPT_STOCK_SHA = "859c4a89149f02e271f73039bf4aa4d31eead0e08dd333d3a17f790bd754986c"
REGISTRY_MARKER = "resolveMcpShortToolName("

OLD_BEFORE_NEXT = "    <next_step>\n"
NEW_BEFORE_NEXT = """    <completed_tool_calls>
        <!-- Successful tool calls only. One short line each: tool, key input, success, artifact path or id. Do not paste full JSON. Leave this section empty of failed calls. -->
    </completed_tool_calls>

    <next_step>
"""

OLD_NEXT_END = "where you left off. -->"
NEW_NEXT_END = (
    "where you left off. "
    "Do not name a tool here when completed_tool_calls already lists it as success. "
    "A later call is allowed only when that result was an error or the user explicitly asked to run the tool again. -->"
)

OLD_PROMPT_TAIL = "</state_snapshot>\n`.trim();\n}"
NEW_PROMPT_TAIL = (
    "</state_snapshot>\n`.trim(); // linux-lokales-ki-compact-continuity\n}"
)

OLD_TRAILER = (
    'var RESUME_TRAILER = "Resume the prior task using the summary above. '
    "Continue from the last in-flight step; do not acknowledge the summary, "
    'do not re-introduce, do not greet the user again.";'
)
NEW_TRAILER = (
    'var RESUME_TRAILER = "Resume the prior task using the summary above. '
    "Continue only from the next_step in the snapshot. "
    "Do not repeat a tool listed under completed_tool_calls when that call succeeded. "
    "Repeat it only when the result was an error or the user explicitly asked to run it again. "
    "Do not acknowledge the summary, do not re-introduce, do not greet the user again.\"; "
    "// linux-lokales-ki-compact-continuity"
)


def _once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"ABBRUCH: {label} nicht eindeutig ({count} Treffer).")
    return text.replace(old, new, 1)


def apply_prompt_text(text: str) -> str:
    if MARKER in text:
        return text
    text = _once(text, OLD_BEFORE_NEXT, NEW_BEFORE_NEXT, "next_step-Anker")
    text = _once(text, OLD_NEXT_END, NEW_NEXT_END, "next_step-Ende")
    text = _once(text, OLD_PROMPT_TAIL, NEW_PROMPT_TAIL, "Prompt-Ende")
    if MARKER not in text or "<completed_tool_calls>" not in text:
        raise SystemExit("ABBRUCH: Compact-Marker nach Prompt-Patch fehlt.")
    return text


def rollback_prompt_text(text: str) -> str:
    if MARKER not in text:
        raise SystemExit("ABBRUCH: Compact-Marker im Prompt fehlt. Nichts zurückgesetzt.")
    text = _once(text, NEW_BEFORE_NEXT, OLD_BEFORE_NEXT, "Rollback next_step")
    text = _once(text, NEW_NEXT_END, OLD_NEXT_END, "Rollback next_step-Ende")
    text = _once(text, NEW_PROMPT_TAIL, OLD_PROMPT_TAIL, "Rollback Prompt-Ende")
    if MARKER in text or "<completed_tool_calls>" in text:
        raise SystemExit("ABBRUCH: Prompt-Rollback unvollständig.")
    return text


def apply_trailer_text(text: str) -> str:
    if REGISTRY_MARKER not in text:
        raise SystemExit("ABBRUCH: Registry-Patch fehlt. Compact-Patch stoppt.")
    if MARKER in text and NEW_TRAILER in text:
        return text
    if MARKER in text:
        raise SystemExit("ABBRUCH: Compact-Marker ohne bekannten Trailer.")
    return _once(text, OLD_TRAILER, NEW_TRAILER, "RESUME_TRAILER")


def rollback_trailer_text(text: str) -> str:
    if REGISTRY_MARKER not in text:
        raise SystemExit("ABBRUCH: Registry-Patch fehlt. Rollback stoppt.")
    if MARKER not in text:
        raise SystemExit("ABBRUCH: Compact-Marker im Trailer fehlt. Nichts zurückgesetzt.")
    text = _once(text, NEW_TRAILER, OLD_TRAILER, "Rollback Trailer")
    if MARKER in text:
        raise SystemExit("ABBRUCH: Trailer-Rollback unvollständig.")
    if REGISTRY_MARKER not in text:
        raise SystemExit("ABBRUCH: Registry-Marker nach Rollback weg.")
    return text


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "usage: patch_compact_continuity.py "
            "apply-prompt|rollback-prompt|apply-trailer|rollback-trailer <file>",
            file=sys.stderr,
        )
        return 2
    action, target = sys.argv[1], Path(sys.argv[2])
    text = target.read_text(encoding="utf-8")
    if action == "apply-prompt":
        new = apply_prompt_text(text)
        status = "already" if new == text else "applied"
    elif action == "rollback-prompt":
        new = rollback_prompt_text(text)
        status = "rolled-back"
    elif action == "apply-trailer":
        new = apply_trailer_text(text)
        status = "already" if new == text else "applied"
    elif action == "rollback-trailer":
        new = rollback_trailer_text(text)
        status = "rolled-back"
    else:
        print(f"ABBRUCH: unbekannte Aktion {action}", file=sys.stderr)
        return 2
    if new != text:
        _write(target, new)
    print(status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
