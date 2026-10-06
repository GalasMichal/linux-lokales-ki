#!/usr/bin/env bash
# Sequential download of the three allowed Qwen-Image-2.1 files. No overwrite.
set -euo pipefail

META="${1:-}"
LOGDIR="${2:-}"
if [[ -z "$META" || ! -f "$META" ]]; then
  printf '%s\n' "usage: download-qwen-image-21.sh official-files.json LOGDIR"
  exit 2
fi
mkdir -p "$LOGDIR"
python3 - "$META" "$LOGDIR" <<'PY'
from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

meta_path = Path(sys.argv[1])
logdir = Path(sys.argv[2])
spec = json.loads(meta_path.read_text())
log = logdir / "download.log"
manifest = logdir / "download-manifest.json"
results = []

def log_line(msg: str) -> None:
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    line = f"{stamp} {msg}"
    print(line, flush=True)
    with log.open("a") as handle:
        handle.write(line + "\n")

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def check_safetensors(path: Path) -> str:
    with path.open("rb") as handle:
        head = handle.read(16)
    if head.startswith(b"<!DOCTYPE") or head.startswith(b"<html") or head.startswith(b"version https://git-lfs"):
        raise SystemExit(f"FAIL {path.name}: HTML oder LFS-Pointer")
    if len(head) < 8:
        raise SystemExit(f"FAIL {path.name}: Datei zu klein")
    header_len = struct.unpack("<Q", head[:8])[0]
    if header_len < 8 or header_len > 100_000_000:
        raise SystemExit(f"FAIL {path.name}: Safetensors-Headerlänge {header_len}")
    with path.open("rb") as handle:
        handle.seek(8)
        raw = handle.read(min(header_len, 4096))
    if b'"__metadata__"' not in raw and b'"dtype"' not in raw and not raw.startswith(b"{"):
        raise SystemExit(f"FAIL {path.name}: kein Safetensors-JSON-Header")
    return "safetensors"

def free_gb(path: str) -> float:
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize / (1024**3)

for item in spec["files"]:
    dest = Path(item["dest"])
    part = dest.with_suffix(dest.suffix + ".part")
    url = f"https://huggingface.co/{spec['repo']}/resolve/main/{item['remote']}"
    want_size = int(item["size"])
    want_sha = item["sha256"]
    log_line(f"BEGIN {item['name']} want={want_size} free_gb={free_gb('/srv/ai'):.1f}")
    if dest.exists():
        got_size = dest.stat().st_size
        got_sha = sha256_file(dest)
        if got_size == want_size and got_sha == want_sha:
            kind = check_safetensors(dest)
            log_line(f"REUSE {item['name']} sha={got_sha} kind={kind}")
            results.append({**item, "status": "reused", "sha256_got": got_sha})
            continue
        raise SystemExit(
            f"FAIL {dest} existiert, stimmt aber nicht (size {got_size}/{want_size} sha {got_sha}/{want_sha}). Nicht überschreiben."
        )
    if free_gb("/srv/ai") < 25:
        raise SystemExit(f"FAIL weniger als 25 GB frei vor {item['name']}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "curl", "-fL", "-C", "-", "--retry", "8", "--retry-delay", "5",
        "--retry-all-errors", "--silent", "--show-error",
        "-A", "linux-lokales-ki-qwen-image-21",
        "--output", str(part),
        url,
    ]
    log_line(f"CURL start {item['name']}")
    proc = subprocess.Popen(cmd)
    last_size = -1
    stall = 0
    while proc.poll() is None:
        time.sleep(15)
        size = part.stat().st_size if part.exists() else 0
        log_line(f"PROGRESS {item['name']} bytes={size} pct={100.0*size/want_size:.1f} free_gb={free_gb('/srv/ai'):.1f}")
        if size == last_size:
            stall += 1
            if stall >= 8:
                proc.kill()
                raise SystemExit(f"FAIL Download hängt: {item['name']} size unverändert {size}")
        else:
            stall = 0
        last_size = size
    if proc.returncode != 0:
        raise SystemExit(f"FAIL curl exit {proc.returncode} für {item['name']}")
    got_size = part.stat().st_size
    if got_size != want_size:
        raise SystemExit(f"FAIL Größe {got_size} != {want_size} für {item['name']}")
    got_sha = sha256_file(part)
    if got_sha != want_sha:
        bad = part.with_suffix(part.suffix + ".bad")
        part.rename(bad)
        raise SystemExit(f"FAIL SHA {got_sha} != {want_sha}. Belassen als {bad}")
    kind = check_safetensors(part)
    os.replace(part, dest)
    log_line(f"OK {item['name']} sha={got_sha} kind={kind} dest={dest}")
    results.append({**item, "status": "downloaded", "sha256_got": got_sha, "kind": kind})

summary = {
    "repo": spec["repo"],
    "revision": spec["revision"],
    "license": spec["license"],
    "results": results,
    "free_gb_after": round(free_gb("/srv/ai"), 2),
}
manifest.write_text(json.dumps(summary, indent=2) + "\n")
log_line(f"DONE files={len(results)} free_gb={summary['free_gb_after']}")
print(json.dumps(summary, indent=2))
PY
