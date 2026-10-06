#!/usr/bin/env python3
"""Restore Open WebUI DB from an image-tools backup. Does not touch Ollama aliases."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

WEBUI_DB = Path("/srv/ai/apps/open-webui/data/webui.db")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("backup_dir")
    args = parser.parse_args()
    src = Path(args.backup_dir) / "webui.db"
    if not src.is_file():
        raise SystemExit(f"Backup-Datenbank fehlt: {src}")
    shutil.copy2(src, WEBUI_DB)
    subprocess.check_call(["systemctl", "--user", "restart", "open-webui.service"])
    print(f"Wiederhergestellt: {src} → {WEBUI_DB}")


if __name__ == "__main__":
    sys.exit(main())
