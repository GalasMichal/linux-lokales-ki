#!/usr/bin/env bash
# Resource sampler for MoE benchmarks. Samples every $INTERVAL seconds.
# Usage: sample_resources.sh <outdir> <label> [interval_sec]
set -euo pipefail
OUTDIR="$1"
LABEL="$2"
INTERVAL="${3:-2}"
mkdir -p "$OUTDIR"
CSV="$OUTDIR/${LABEL}-resources.csv"
echo "ts,mem_used_mb,mem_avail_mb,swap_used_mb,load1,cpu_pct,vram_used_mb,gpu_util" >"$CSV"
prev_idle=0; prev_total=0
while true; do
  ts=$(date +%s.%N)
  # mem
  read -r mem_used mem_avail swap_used < <(free -m | awk '
    /^Mem:/{u=$3; a=$7}
    /^Swap:/{s=$3}
    END{print u,a,s}')
  load1=$(awk '{print $1}' /proc/loadavg)
  # cpu% from /proc/stat
  read -r user nice system idle iowait irq softirq steal < <(awk '/^cpu /{print $2,$3,$4,$5,$6,$7,$8,$9}' /proc/stat)
  total=$((user+nice+system+idle+iowait+irq+softirq+steal))
  idle_all=$((idle+iowait))
  if (( prev_total > 0 )); then
    dt=$((total-prev_total)); di=$((idle_all-prev_idle))
    if (( dt > 0 )); then cpu_pct=$(python3 -c "print(round(100.0*(1-$di/$dt),1))"); else cpu_pct=0; fi
  else
    cpu_pct=0
  fi
  prev_total=$total; prev_idle=$idle_all
  read -r vram util < <(nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' ')
  vram=${vram:-0}; util=${util:-0}
  echo "$ts,$mem_used,$mem_avail,$swap_used,$load1,$cpu_pct,$vram,$util" >>"$CSV"
  sleep "$INTERVAL"
done
