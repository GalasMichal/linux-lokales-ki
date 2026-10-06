#!/usr/bin/env bash
# Fair 64K vs 80K QUALITY comparison — same current fixtures, 5 runs × 6 suites.
# Append-only OUT. Does not overwrite post64k / 20261002 raw data.
# No productive cutover. No poweroff. FAST stays 32K.
set -euo pipefail
REPO='/home/mike/Projects/Linux Lokales KI'
OUT="$REPO/benchmarks/context-boundary-fair-64vs80-20261003"
PY="$REPO/benchmarks/context_boundary_discovery.py"
export CBD_OUT="$OUT"
export CBD_FAMILY=quality
LOG="$OUT/orchestrator-fair.log"
mkdir -p "$OUT"
exec >>"$LOG" 2>&1

echo "=== FAIR 64vs80 START $(date -Iseconds) ==="
echo "CBD_OUT=$CBD_OUT same fixtures. Productive stays 64K until explicit cutover. NO POWEROFF."

write_status() {
  python3 - <<'PY'
import json, time
from collections import defaultdict
from pathlib import Path
base = Path("/home/mike/Projects/Linux Lokales KI/benchmarks/context-boundary-fair-64vs80-20261003")
rows = []
p = base / "results.jsonl"
if p.is_file():
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
by = defaultdict(lambda: {"n": 0, "pass": 0, "fail": 0, "drift": 0, "elapsed": []})
for r in rows:
    k = (r["suite"], r["num_ctx"])
    by[k]["n"] += 1
    by[k]["pass" if r.get("pass") else "fail"] += 1
    if r.get("drift"):
        by[k]["drift"] += 1
    by[k]["elapsed"].append(r.get("elapsed_s") or 0)
suites = ["tool_chain", "compact", "knowledge", "supervisor", "coding", "multi_hop"]
ctxs = [65536, 81920]
lines = [
    "# Fair 64K vs 80K — STATUS",
    "",
    f"Updated: {time.strftime('%Y-%m-%d %H:%M:%S %z')}. Runs={len(rows)}.",
    "Same current fixtures (multi-file coding + multi_hop). 5 runs / suite / ctx.",
    "Productive local-quality stays **65536** until a later cutover decision.",
    "Keep-awake: systemd-inhibit pc-keepawake (separate).",
    "",
    "| Context | Tool | Compact | KB | Supervisor | Coding | MultiHop | Drift |",
    "|---|---|---|---|---|---|---|---|",
]
for c in ctxs:
    cells = []
    drift = 0
    for s in suites:
        v = by.get((s, c))
        if not v:
            cells.append("—")
        else:
            cells.append(f"{v['pass']}/{v['n']}")
            drift += v["drift"]
    lines.append(f"| {c} | " + " | ".join(cells) + f" | {drift} |")
if rows:
    last = rows[-1]
    lines += [
        "",
        f"Last: {last.get('suite')} ctx={last.get('num_ctx')} r={last.get('run_id')} "
        f"pass={last.get('pass')} elapsed={last.get('elapsed_s')} @ {last.get('ts')}",
    ]
(base / "STATUS.md").write_text("\n".join(lines) + "\n")
print("STATUS refreshed", len(rows))
PY
}

write_eval() {
  python3 - <<'PY'
import json
from collections import defaultdict
from pathlib import Path
base = Path("/home/mike/Projects/Linux Lokales KI/benchmarks/context-boundary-fair-64vs80-20261003")
rows = [json.loads(l) for l in (base / "results.jsonl").read_text().splitlines() if l.strip()]
suites = ["tool_chain", "compact", "knowledge", "supervisor", "coding", "multi_hop"]
by = defaultdict(list)
for r in rows:
    by[(r["suite"], r["num_ctx"])].append(r)
def slot(suite, ctx):
    xs = by.get((suite, ctx), [])
    return {
        "n": len(xs),
        "pass": sum(1 for r in xs if r.get("pass")),
        "drift": sum(1 for r in xs if r.get("drift")),
        "fails": [
            {
                "run_id": r.get("run_id"),
                "reasons": r.get("fail_reasons"),
                "categories": r.get("categories"),
                "elapsed_s": r.get("elapsed_s"),
            }
            for r in xs if not r.get("pass")
        ],
        "avg_s": round(sum(r.get("elapsed_s") or 0 for r in xs) / len(xs), 1) if xs else None,
    }
matrix = {str(c): {s: slot(s, c) for s in suites} for c in (65536, 81920)}
def reliable(ctx):
    cells = matrix[str(ctx)]
    return all(v["n"] >= 5 and v["pass"] == v["n"] and v["drift"] == 0 for v in cells.values())
eval_doc = {
    "updated": __import__("time").strftime("%Y-%m-%dT%H:%M:%S%z"),
    "total_runs": len(rows),
    "pass": sum(1 for r in rows if r.get("pass")),
    "fail": sum(1 for r in rows if not r.get("pass")),
    "matrix": matrix,
    "reliable_64k": reliable(65536),
    "reliable_80k": reliable(81920),
    "cutover_candidate_80k": reliable(81920) and reliable(65536),
    "note": "Cutover only if 80K is fully reliable AND at least as reliable as 64K. Script does not cut over.",
}
(base / "EVAL.json").write_text(json.dumps(eval_doc, indent=2, ensure_ascii=False) + "\n")
print("EVAL", json.dumps({k: eval_doc[k] for k in ("total_runs","pass","fail","reliable_64k","reliable_80k","cutover_candidate_80k")}))
PY
}

gate() {
  ollama show local-quality --modelfile | grep -qE 'num_ctx 65536|num_ctx 16384|num_ctx 81920' || {
    echo "ABBRUCH: local-quality num_ctx unexpected"; exit 1;
  }
  ollama show local-fast --modelfile | grep -q 'num_ctx 32768' || {
    echo "ABBRUCH: local-fast not 32768"; exit 1;
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
  CBD_OUT="$OUT" CBD_FAMILY=quality python3 "$PY" --suite "$suite" --ctx "$ctx" --runs "$runs" --start-run "$start" \
    | tee -a "$OUT/run-${tag}.log"
  write_status
  echo "=== END $tag $(date -Iseconds) ==="
}

write_status

for ctx in 65536 81920; do
  echo "=== PHASE ctx=$ctx $(date -Iseconds) ==="
  for s in tool_chain compact knowledge supervisor coding multi_hop; do
    run_suite "$s" "$ctx" 5 1
  done
done

python3 - <<'PY'
import json, os, importlib.util
from pathlib import Path
os.environ["CBD_OUT"] = "/home/mike/Projects/Linux Lokales KI/benchmarks/context-boundary-fair-64vs80-20261003"
os.environ["CBD_FAMILY"] = "quality"
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
PY

write_status
write_eval

echo "=== FAIR 64vs80 END $(date -Iseconds) ==="
echo "NO CUTOVER IN THIS SCRIPT. NO POWEROFF."
