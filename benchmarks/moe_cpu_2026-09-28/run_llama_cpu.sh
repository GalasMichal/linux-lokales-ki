#!/usr/bin/env bash
# Run one llama.cpp CPU inference with metrics.
# Args: <label> <prompt_file> [threads] [ctx] [n_predict]
set -euo pipefail
REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
BENCH="$REPO/benchmarks/moe_cpu_2026-09-28"
LLAMA=/srv/ai/apps/llama.cpp-0.5.0/llama-cli
MODEL=/srv/ai/models/gguf/qwen3-coder-30b-a3b/Qwen3-Coder-30B-A3B-Instruct-Q4_K_S.gguf
LABEL="$1"
PROMPT_FILE="$2"
THREADS="${3:-24}"
CTX="${4:-4096}"
NPRED="${5:-256}"

mkdir -p "$BENCH"/{responses,metrics,logs}
chmod +x "$BENCH/sample_resources.sh" 2>/dev/null || true

# baseline
BASE="$BENCH/metrics/${LABEL}-baseline.txt"
{
  date -Is
  free -h
  nvidia-smi --query-gpu=memory.used,utilization.gpu,temperature.gpu --format=csv
  cat /proc/loadavg
} >"$BASE"

# start sampler
"$BENCH/sample_resources.sh" "$BENCH/metrics" "$LABEL" 1 &
SAMP_PID=$!
cleanup() { kill "$SAMP_PID" 2>/dev/null || true; }
trap cleanup EXIT

LOG="$BENCH/logs/${LABEL}.log"
RESP="$BENCH/responses/${LABEL}.txt"
JSON="$BENCH/metrics/${LABEL}.json"

START=$(date +%s.%N)
# -ngl 0 CPU-only; jinja chat template; single-turn; reasoning off for speed/clarity
# Capture stdout+stderr together for timing lines printed by llama-cli
set +e
"$LLAMA" \
  -m "$MODEL" \
  -ngl 0 \
  -t "$THREADS" \
  -c "$CTX" \
  -n "$NPRED" \
  --temp 0.2 \
  --seed 42 \
  --jinja \
  --reasoning off \
  -st \
  --no-display-prompt \
  -sys "You are a concise senior TypeScript/OpenLayers engineer. Answer in German unless code must stay English." \
  -f "$PROMPT_FILE" \
  >"$RESP.raw" 2>&1
RC=$?
set -e
cp "$RESP.raw" "$LOG"
# Strip spinner/banner; keep answer + timing line
python3 - <<PY
from pathlib import Path
import re
raw = Path("$RESP.raw").read_text(errors="replace")
Path("$LOG").write_text(raw)
speed = re.search(r"\[\s*Prompt:\s*([\d.,]+)\s*t/s\s*\|\s*Generation:\s*([\d.,]+)\s*t/s\s*\]", raw)
parts = re.split(r"\n> ", raw, maxsplit=1)
if len(parts) == 2:
    body = parts[1]
    # first line is echoed user prompt; remainder is model answer (+ timing)
    lines = body.split("\n", 1)
    ans_body = lines[1] if len(lines) == 2 else body
    ans_body = re.split(r"\n\[\s*Prompt:", ans_body)[0].strip()
    ans_body = re.split(r"\nExiting", ans_body)[0].strip()
else:
    ans_body = raw
Path("$RESP").write_text(ans_body + ("\n" + speed.group(0) if speed else "") + "\n")
PY
END=$(date +%s.%N)
WALL=$(python3 -c "print(round(float('$END')-float('$START'),3))")

# parse llama.cpp timing from stderr log
python3 - <<PY
import re, json, pathlib
log = pathlib.Path("$LOG").read_text(errors="replace")
resp = pathlib.Path("$RESP").read_text(errors="replace")
metrics = {
  "label": "$LABEL",
  "runtime": "llama.cpp",
  "model": "Qwen3-Coder-30B-A3B-Instruct-Q4_K_S",
  "threads": int("$THREADS"),
  "ctx": int("$CTX"),
  "n_predict": int("$NPRED"),
  "wall_s": float("$WALL"),
  "rc": int("$RC"),
  "response_chars": len(resp),
  "response_preview": resp[:500],
}
# common llama.cpp patterns + DE locale decimals
def to_float(s):
  return float(s.replace(",", "."))
m = re.search(r"Prompt:\s*([\d.,]+)\s*t/s\s*\|\s*Generation:\s*([\d.,]+)\s*t/s", log)
if m:
  metrics["prompt_tps"] = to_float(m.group(1))
  metrics["eval_tps"] = to_float(m.group(2))
# also search response file
resp_txt = pathlib.Path("$RESP").read_text(errors="replace")
m2 = re.search(r"Prompt:\s*([\d.,]+)\s*t/s\s*\|\s*Generation:\s*([\d.,]+)\s*t/s", resp_txt)
if m2:
  metrics["prompt_tps"] = to_float(m2.group(1))
  metrics["eval_tps"] = to_float(m2.group(2))
# extract clean answer preview (no spinner)
clean = re.split(r"\[\s*Prompt:", resp_txt)[0].strip()
# drop banner leftovers
if "TypeScript" in clean or len(clean) < 5000:
  metrics["response_preview"] = clean[:800]
  metrics["response_chars"] = len(clean)
patterns = {
  "load_time_ms": r"llama_model_loader:.*?load time.*?=?\s*([\d.]+)\s*ms|load time\s*=\s*([\d.]+)\s*ms|llama_model_load.*?([\d.]+) ms",
  "prompt_ms": r"prompt eval time\s*=\s*([\d.]+)\s*ms",
  "prompt_tokens": r"prompt eval time.*?/\s*(\d+)\s*tokens",
  "eval_ms": r"eval time\s*=\s*([\d.]+)\s*ms\s*/",
  "eval_tokens": r"eval time.*?/\s*(\d+)\s*runs",
  "total_ms": r"total time\s*=\s*([\d.]+)\s*ms",
}
for k, pat in patterns.items():
  m = re.search(pat, log, re.I | re.S)
  if m:
    g = next(x for x in m.groups() if x)
    metrics[k] = float(g) if "." in g else int(g)

# resource peaks from csv
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
      "ram_min_mb": min(mem),
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
exit "$RC"
