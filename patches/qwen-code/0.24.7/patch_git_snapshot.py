#!/usr/bin/env python3
"""Do not inject git status/commits/branch lists into Qwen's system prompt (0.24.7)."""
from __future__ import annotations

import sys
from pathlib import Path

MARKER = "linux-lokales-ki-omit-git-snapshot"
OLD = "function getRecentGitStatus(cwd){if(!isGitRepository(cwd))return null;try{"
NEW = (
    "function getRecentGitStatus(cwd){if(!isGitRepository(cwd))return null;"
    "return null;// linux-lokales-ki-omit-git-snapshot\ntry{"
)


def apply_text(text: str) -> str:
    if MARKER in text:
        return text
    count = text.count(OLD)
    if count != 1:
        raise SystemExit(f"ABBRUCH: getRecentGitStatus-Kopf nicht eindeutig ({count} Treffer).")
    return text.replace(OLD, NEW, 1)


def apply_patch(target: Path) -> str:
    text = target.read_text(encoding="utf-8")
    if MARKER in text:
        return "already"
    new = apply_text(text)
    if MARKER not in new:
        raise SystemExit("ABBRUCH: Git-Snapshot-Marker nach Patch fehlt.")
    target.write_text(new, encoding="utf-8")
    return "applied"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: patch_git_snapshot.py <chunk-L3A6AVZE.js>", file=sys.stderr)
        return 2
    print(apply_patch(Path(sys.argv[1])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
