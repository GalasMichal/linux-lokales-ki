# llama.cpp CPU Runtime — 2026-09-28

## Version

- Stable tag: **v0.5.0** (GitHub `ggml-org/llama.cpp`)
- Matching binary build: **b11146** (via `v0.5.0/nightly-tag.txt`)
- Reported: `version: 0.5.0-dev (build 11146, commit 7fe450e19)`
- Built with: GNU 11.4.0 for Linux x86_64

## Install path

- App root: `/srv/ai/apps/llama.cpp-0.5.0/`
- Binaries: `/srv/ai/apps/llama.cpp-0.5.0/llama-b11146/`
- Wrappers: `/srv/ai/apps/llama.cpp-0.5.0/llama-cli`, `…/llama-server` (set `LD_LIBRARY_PATH`)

## Download / Build

- **Art:** Official prebuilt Ubuntu x64 CPU package (kein Source-Build)
- **URL:** `https://github.com/ggml-org/llama.cpp/releases/download/b11146/llama-b11146-bin-ubuntu-x64.tar.gz`
- **Cache:** `/srv/ai/cache/llama.cpp-0.5.0/`
- **SHA256 (tar):** `c150306eb16b5ab696f76a8bdf810c35fd98a24e82158742e6fa28f420ff8410`
- **Compile Flags:** n/a (prebuilt). Package enthält nur `libggml-cpu-*` — **keine** `ggml-cuda` / CUDA-Libs.

## CPU-only Kommando

```bash
/srv/ai/apps/llama.cpp-0.5.0/llama-cli \
  -m /srv/ai/models/gguf/qwen3-coder-30b-a3b/<file>.gguf \
  -ngl 0 \
  -c 4096 \
  -n 128 \
  -p "Write a hello world in TypeScript."
```

Server:

```bash
/srv/ai/apps/llama.cpp-0.5.0/llama-server \
  -m /srv/ai/models/gguf/qwen3-coder-30b-a3b/<file>.gguf \
  -ngl 0 \
  --host 127.0.0.1 --port 8081 \
  -c 8192
```

## CPU-only Nachweis

- Package ohne CUDA-Libs (`libggml-cpu-*` only).
- Inferenz immer mit `-ngl 0`.
- Solo-Messungen: VRAM ~1.6–2.1 GB, GPU util niedrig.
- Parallel mit Ollama `local-fast`: VRAM steigt auf ~8.9 GB durch GPU-Agent, MoE bleibt CPU — siehe `benchmarks/moe_cpu_2026-09-28/RESULTS.md`.

## Empfohlene Runtime-Flags (Host)

```bash
/srv/ai/apps/llama.cpp-0.5.0/llama-cli \
  -m /srv/ai/models/gguf/qwen3-coder-30b-a3b/Qwen3-Coder-30B-A3B-Instruct-Q4_K_S.gguf \
  -ngl 0 -t 16 -c 4096 -n 256 \
  --jinja --reasoning off -st \
  -f prompt.txt
```

t=16 gewählt (besser als 24/32 auf i9-14900KF unter RAM-Druck).

## Rollback / Entfernung

```bash
rm -rf /srv/ai/apps/llama.cpp-0.5.0
# Cache optional behalten:
# rm -rf /srv/ai/cache/llama.cpp-0.5.0
```

Kein systemd-Service angelegt. Kein PATH-Global-Eintrag nötig.
