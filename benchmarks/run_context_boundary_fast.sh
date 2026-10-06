#!/usr/bin/env bash
# FAST (local-fast / Qwen3.5 9B) Context Boundary Discovery.
# Additive bench aliases only. Does NOT change productive local-fast (32768).
set -euo pipefail
REPO='/home/mike/Projects/Linux Lokales KI'
OUT="$REPO/benchmarks/context-boundary-fast-20261003"
PY="$REPO/benchmarks/context_boundary_discovery.py"
export CBD_OUT="$OUT"
export CBD_FAMILY=fast
LOG="$OUT/orchestrator-fast.log"
mkdir -p "$OUT"
exec >>"$LOG" 2>&1

echo "=== FAST BOUNDARY START $(date -Iseconds) ==="
echo "CBD_FAMILY=fast CBD_OUT=$OUT — NO cutover on local-fast"

gate() {
  ollama show local-fast --modelfile | grep -q 'num_ctx 32768' || {
    echo "ABBRUCH: local-fast not 32768"; exit 1;
  }
  ollama show local-quality --modelfile | grep -q 'num_ctx 16384' || {
    echo "ABBRUCH: local-quality not 16384"; exit 1;
  }
  curl -sf http://127.0.0.1:4170/health >/dev/null || systemctl --user start qwen-code-web.service
  for i in $(seq 1 40); do curl -sf http://127.0.0.1:4170/health >/dev/null && break; sleep 1; done
}

run_suite() {
  local suite="$1"
  local ctx="$2"
  local runs="$3"
  local start="${4:-1}"
  local tag="${suite}-ctx${ctx}-r${start}n${runs}"
  gate
  echo "=== RUN $tag $(date -Iseconds) ==="
  CBD_OUT="$OUT" CBD_FAMILY=fast python3 "$PY" --suite "$suite" --ctx "$ctx" --runs "$runs" --start-run "$start" \
    | tee -a "$OUT/run-${tag}.log"
  echo "=== END $tag $(date -Iseconds) ==="
}

# Baseline + climb tool_chain
run_suite tool_chain 32768 5 1
run_suite tool_chain 49152 5 1
run_suite tool_chain 65536 5 1
run_suite tool_chain 81920 5 1
run_suite tool_chain 98304 5 1

# Suites at baseline 32K and best-looking higher (64K then 80K)
for suite in compact knowledge supervisor coding; do
  run_suite "$suite" 32768 3 1
  run_suite "$suite" 65536 3 1
done
for suite in compact coding; do
  run_suite "$suite" 81920 3 1
  run_suite "$suite" 98304 3 1
done

python3 - <<'PY'
import json, os, importlib.util
from pathlib import Path
os.environ["CBD_OUT"] = "/home/mike/Projects/Linux Lokales KI/benchmarks/context-boundary-fast-20261003"
os.environ["CBD_FAMILY"] = "fast"
spec = importlib.util.spec_from_file_location(
    "cbd",
    "/home/mike/Projects/Linux Lokales KI/benchmarks/context_boundary_discovery.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print(mod.summarize())
p = Path.home() / ".qwen" / "settings.json"
d = json.loads(p.read_text())
d["model"]["name"] = "local-fast"
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
print("restored model.name=local-fast")
import subprocess
assert "num_ctx 32768" in subprocess.check_output(["ollama","show","local-fast","--modelfile"], text=True)
assert "num_ctx 16384" in subprocess.check_output(["ollama","show","local-quality","--modelfile"], text=True)
print("productive aliases untouched")
PY

python3 - <<'PY'
import json
from collections import defaultdict
from pathlib import Path
base=Path("/home/mike/Projects/Linux Lokales KI/benchmarks/context-boundary-fast-20261003")
rows=[json.loads(l) for l in (base/"results.jsonl").read_text().splitlines() if l.strip()]
by=defaultdict(lambda:{"n":0,"pass":0,"fail":0,"drift":0})
for r in rows:
    k=(r["suite"],r["num_ctx"]); by[k]["n"]+=1
    by[k]["pass" if r.get("pass") else "fail"]+=1
    if r.get("drift"): by[k]["drift"]+=1
suites=["tool_chain","compact","knowledge","supervisor","coding"]
ctxs=[32768,49152,65536,81920,98304]
lines=["# FAST Context Boundary — STATUS", "", f"Runs={len(rows)}. **Kein Cutover local-fast.**", "",
"| Context | Tool | Compact | KB | Supervisor | Coding | Drift |","|---|---|---|---|---|---|---|"]
for c in ctxs:
    cells=[]; d=0
    for s in suites:
        v=by.get((s,c))
        if not v: cells.append("—")
        else:
            cells.append(f"{v['pass']}/{v['n']}"); d+=v["drift"]
    lines.append(f"| {c} | "+" | ".join(cells)+f" | {d} |")
(base/"STATUS.md").write_text("\n".join(lines)+"\n")
(base/"REPORT.md").write_text("\n".join(lines)+"\n")
print("STATUS written")
PY

echo "=== FAST BOUNDARY END $(date -Iseconds) ==="
echo "NO CUTOVER. local-fast stays 32768. local-quality stays 16384."
