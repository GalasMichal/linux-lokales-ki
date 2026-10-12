#!/usr/bin/env bash
# Install Piper CLI + medium voices for kinder-spiele narrator langs (CPU ONNX).
set -euo pipefail

PIPER_VERSION="${PIPER_VERSION:-2023.11.14-2}"
PIPER_ROOT="${PIPER_ROOT:-/srv/ai/apps/piper}"
VOICE_ROOT="${VOICE_ROOT:-/srv/ai/models/piper/voices}"
HF_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main"

declare -A VOICES=(
  [de]="de/de_DE/thorsten/medium/de_DE-thorsten-medium"
  [en]="en/en_US/lessac/medium/en_US-lessac-medium"
  [pl]="pl/pl_PL/gosia/medium/pl_PL-gosia-medium"
  [es]="es/es_ES/davefx/medium/es_ES-davefx-medium"
  [fr]="fr/fr_FR/siwis/medium/fr_FR-siwis-medium"
  [tr]="tr/tr_TR/dfki/medium/tr_TR-dfki-medium"
)

mkdir -p "$PIPER_ROOT" "$VOICE_ROOT"

if [[ ! -x "$PIPER_ROOT/piper/piper" ]]; then
  tmp="$(mktemp -d)"
  curl -fsSL -o "$tmp/piper.tgz" \
    "https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_linux_x86_64.tar.gz"
  tar -xzf "$tmp/piper.tgz" -C "$tmp"
  rm -rf "$PIPER_ROOT/piper"
  mv "$tmp/piper" "$PIPER_ROOT/piper"
  rm -rf "$tmp"
  echo "Piper ${PIPER_VERSION} -> ${PIPER_ROOT}/piper"
fi

download_voice() {
  local lang="$1" rel="$2"
  local dir="$VOICE_ROOT/$lang"
  mkdir -p "$dir"
  local base="$rel"
  if [[ ! -f "$dir/$(basename "$base").onnx" ]]; then
    curl -fsSL -o "$dir/$(basename "$base").onnx" "$HF_BASE/${rel}.onnx"
    curl -fsSL -o "$dir/$(basename "$base").onnx.json" "$HF_BASE/${rel}.onnx.json"
    echo "voice $lang: $(basename "$base")"
  else
    echo "voice $lang: already present"
  fi
}

for lang in "${!VOICES[@]}"; do
  download_voice "$lang" "${VOICES[$lang]}"
done

echo "Piper: $PIPER_ROOT/piper/piper"
echo "Voices: $VOICE_ROOT/{de,en,pl,es,fr,tr}"
