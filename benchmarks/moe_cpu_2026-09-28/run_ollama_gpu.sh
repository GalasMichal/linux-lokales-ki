#!/usr/bin/env bash
# Run one Ollama GPU (local-fast) inference with metrics.
# Args: <label> <prompt_file> [num_predict]
set -euo pipefail
REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
BENCH="$REPO/benchmarks/moe_cpu_2026-09-28"
LABEL="$1"
PROMPT_FILE="$2"
NPRED="${3:-256}"
MODEL="${4:-local-fast}"

mkdir -p "$BENCH"/{responses,metrics,logs}
chmod +x "$BENCH/sample_resources.sh" 2>/dev/null || true

BASE="$BENCH/metrics/${LABEL}-baseline.txt"
{
  date -Is
  free -h
  nvidia-smi --query-gpu=memory.used,utilization.gpu,temperature.gpu --format=csv
  curl -sS http://127.0.0.1:11434/api/ps || true
} >"$BASE"

"$BENCH/sample_resources.sh" "$BENCH/metrics" "$LABEL" 1 &
SAMP_PID=$!
cleanup() { kill "$SAMP_PID" 2>/dev/null || true; }
trap cleanup EXIT

PROMPT=$(cat "$PROMPT_FILE")
RESP="$BENCH/responses/${LABEL}.txt"
JSON="$BENCH/metrics/${LABEL}.json"
RAW="$BENCH/logs/${LABEL}.raw.json"

START=$(date +%s.%N)
python3 - <<PY >"$RAW"
import json, urllib.request
payload = {
  "model": "$MODEL",
  "prompt": open("$PROMPT_FILE").read(),
  "stream": False,
  "think": False,
  "options": {"num_predict": int("$NPRED"), "temperature": 0.2, "seed": 42},
}
req = urllib.request.Request(
  "http://127.0.0.1:11434/api/generate",
  data=json.dumps(payload).encode(),
  headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=600) as r:
  print(r.read().decode())
PY
END=$(date +%s.%N)
WALL=$(python3 -c "print(round(float('$END')-float('$START'),3))")

python3 - <<PY
import json, pathlib
raw = json.loads(pathlib.Path("$RAW").read_text())
resp = raw.get("response") or ""
pathlib.Path("$RESP").write_text(resp)
# durations are nanoseconds in ollama
def ns_to_s(v):
  return None if v is None else round(v/1e9, 4)
def tps(count, dur_ns):
  if not count or not dur_ns: return None
  return round(count / (dur_ns/1e9), 3)
metrics = {
  "label": "$LABEL",
  "runtime": "ollama",
  "model": "$MODEL",
  "n_predict": int("$NPRED"),
  "wall_s": float("$WALL"),
  "response_chars": len(resp),
  "response_preview": resp[:500],
  "load_duration_s": ns_to_s(raw.get("load_duration")),
  "prompt_eval_count": raw.get("prompt_eval_count"),
  "prompt_eval_duration_s": ns_to_s(raw.get("prompt_eval_duration")),
  "prompt_tps": tps(raw.get("prompt_eval_count"), raw.get("prompt_eval_duration")),
  "eval_count": raw.get("eval_count"),
  "eval_duration_s": ns_to_s(raw.get("eval_duration")),
  "eval_tps": tps(raw.get("eval_count"), raw.get("eval_duration")),
  "total_duration_s": ns_to_s(raw.get("total_duration")),
  "done_reason": raw.get("done_reason"),
}
csv = pathlib.Path("$BENCH/metrics/$LABEL-resources.csv")
if csv.exists():
  rows = [r.strip().split(",") for r in csv.read_text().splitlines()[1:] if r.strip()]
  if rows:
    mem = [float(r[1]) for r in rows]
    swap = [float(r[3]) for r in rows]
    cpu = [float(r[5]) for r in rows]
    vram = [float(r[6]) for r in rows]
    gpu = [float(r[7]) for r in rows]
    metrics.update({
      "ram_peak_mb": max(mem),
      "swap_peak_mb": max(swap),
      "cpu_peak_pct": max(cpu),
      "vram_peak_mb": max(vram),
      "vram_min_mb": min(vram),
      "gpu_util_peak": max(gpu),
    })
pathlib.Path("$JSON").write_text(json.dumps(metrics, indent=2))
print(json.dumps(metrics, indent=2))
PY

cleanup
trap - EXIT
# unload model after to free VRAM for next
curl -sS http://127.0.0.1:11434/api/generate -d "{\"model\":\"$MODEL\",\"keep_alive\":0,\"prompt\":\"\"}" >/dev/null || true
