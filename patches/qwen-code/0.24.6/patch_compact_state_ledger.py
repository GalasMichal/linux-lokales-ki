#!/usr/bin/env python3
"""Qwen Code 0.24.6 compact state ledger (minified anchors).

Inserts a runtime-built tool ledger and shrinks a large successful tool
result after auto-compact. Requires Registry patch already applied.
"""
from __future__ import annotations

import sys
from pathlib import Path

MARKER = "linux-lokales-ki-compact-state-ledger"
REGISTRY_MARKER = "resolveMcpShortToolName("
SNIPPET = Path(__file__).with_name("compact-state-ledger.js")

OLD_FUNCTIONS = "function postProcessSummary(rawSummary){"
NEW_FUNCTIONS = SNIPPET.read_text(encoding="utf-8") + "\nfunction postProcessSummary(rawSummary){"

OLD_CAPTURE = "if(exactRoute||isHardTier&&!shouldForceFromHard){"
NEW_CAPTURE = "const compactStateHistoryBefore=this.getHistoryShallow(true);if(exactRoute||isHardTier&&!shouldForceFromHard){"

OLD_ESTIMATE = "const localPromptTokensAfterCompression=shouldForceFromHard?estimatePromptTokens("
NEW_ESTIMATE = (
    "if(compressionInfo&&compressionInfo.compressionStatus===1 /* COMPRESSED */){"
    "const compactStateBeforeShrink=userContent;"
    "const compactStateEntries=mergeCompactStateEntries("
    "parsePriorCompactStateLedger(compactStateHistoryBefore),"
    "scanCompactStatePairs([...compactStateHistoryBefore,userContent])"
    ");"
    "userContent=applyCompactStateLedger(this.history,userContent,compactStateEntries);"
    "const compactStateSaved=Math.max(0,"
    "estimateContentTokens([compactStateBeforeShrink],imageTokenEstimate)-estimateContentTokens([userContent],imageTokenEstimate)"
    ");"
    "if(compactStateSaved>0&&compressionInfo.newTokenCount>=hard){"
    "compressionInfo.newTokenCount=Math.max(0,compressionInfo.newTokenCount-compactStateSaved);"
    "this.setLastPromptTokenCount(compressionInfo.newTokenCount,true)"
    "}"
    "}"
    "const localPromptTokensAfterCompression=shouldForceFromHard?estimatePromptTokens("
)


def _once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"ABBRUCH: {label} nicht eindeutig ({count} Treffer).")
    return text.replace(old, new, 1)


def apply_text(text: str) -> str:
    if REGISTRY_MARKER not in text:
        raise SystemExit("ABBRUCH: Registry-Patch fehlt. Ledger stoppt.")
    if MARKER in text and "function applyCompactStateLedger(" in text and "compactStateHistoryBefore" in text:
        return text
    if MARKER in text:
        raise SystemExit("ABBRUCH: Ledger-Marker ohne vollständige Einfügung.")
    text = _once(text, OLD_FUNCTIONS, NEW_FUNCTIONS, "postProcessSummary")
    text = _once(text, OLD_CAPTURE, NEW_CAPTURE, "Compact-Vorgeschichte")
    text = _once(text, OLD_ESTIMATE, NEW_ESTIMATE, "Token-Schätzung nach Compact")
    if text.count(MARKER) < 1 or "function applyCompactStateLedger(" not in text:
        raise SystemExit("ABBRUCH: Ledger nach dem Patch unvollständig.")
    if REGISTRY_MARKER not in text:
        raise SystemExit("ABBRUCH: Registry-Marker nach dem Patch weg.")
    return text


def rollback_text(text: str) -> str:
    if REGISTRY_MARKER not in text:
        raise SystemExit("ABBRUCH: Registry-Patch fehlt. Rollback stoppt.")
    if MARKER not in text:
        raise SystemExit("ABBRUCH: Ledger-Marker fehlt. Nichts zurückgesetzt.")
    text = _once(text, NEW_FUNCTIONS, OLD_FUNCTIONS, "Rollback Funktionen")
    text = _once(text, NEW_CAPTURE, OLD_CAPTURE, "Rollback Vorgeschichte")
    text = _once(text, NEW_ESTIMATE, OLD_ESTIMATE, "Rollback Token-Schätzung")
    if MARKER in text or "compactStateHistoryBefore" in text:
        raise SystemExit("ABBRUCH: Ledger-Rollback unvollständig.")
    if REGISTRY_MARKER not in text:
        raise SystemExit("ABBRUCH: Registry-Marker nach Rollback weg.")
    return text


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: patch_compact_state_ledger.py apply|rollback <file>", file=sys.stderr)
        return 2
    action, target = sys.argv[1], Path(sys.argv[2])
    text = target.read_text(encoding="utf-8")
    if action == "apply":
        new = apply_text(text)
        status = "already" if new == text else "applied"
    elif action == "rollback":
        new = rollback_text(text)
        status = "rolled-back"
    else:
        print(f"ABBRUCH: unbekannte Aktion {action}", file=sys.stderr)
        return 2
    if new != text:
        target.write_text(new, encoding="utf-8")
    print(status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
