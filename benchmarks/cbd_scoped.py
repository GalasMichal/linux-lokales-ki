#!/usr/bin/env python3
"""Run context_boundary_discovery against the isolated serve with a fail-closed shell voter."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path("/home/mike/Projects/Linux Lokales KI")
sys.path.insert(0, str(REPO / "benchmarks"))

os.environ.setdefault("CBD_SERVE", "http://127.0.0.1:4171")
SERVE = os.environ["CBD_SERVE"]

import night_scoped_shell as scoped  # noqa: E402
import quality_cutover_e2e as e2e  # noqa: E402

e2e.BASE = SERVE
scoped.install_voter(SERVE)

import context_boundary_discovery as cbd  # noqa: E402


def vote_pending(session_id: str, collector) -> None:  # type: ignore[no-untyped-def]
    try:
        status = e2e.http_json("GET", f"/session/{session_id}/status")
    except Exception:
        return
    for item in status.get("pendingInteractions") or []:
        request_id = item.get("requestId") or item.get("id")
        if not request_id:
            continue
        vote = scoped.cast_vote(SERVE, session_id, item)
        collector.votes.append(vote)


cbd.vote_pending = vote_pending

if __name__ == "__main__":
    scoped.assert_user_settings_untouched()
    raise SystemExit(cbd.main())
