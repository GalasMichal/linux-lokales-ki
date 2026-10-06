#!/usr/bin/env bash
# Clone official ComfyUI v0.37.0 next to 0.33.0. Does not change the live unit or the 0.33 venv.
set -euo pipefail

OLD_TREE="/srv/ai/apps/ComfyUI"
NEW_TREE="/srv/ai/apps/ComfyUI-0.37.0"
WANT_TAG="v0.37.0"
WANT_COMMIT="73c9bad4d21e7addbe1d13bc92eee0f1431b017d"

if [[ -e "$NEW_TREE" ]]; then
  got="$(git -C "$NEW_TREE" rev-parse HEAD 2>/dev/null || true)"
  if [[ "$got" == "$WANT_COMMIT" && -f "$NEW_TREE/main.py" && -f "$NEW_TREE/extra_model_paths.yaml" ]]; then
    printf 'OK   Isolierter Tree liegt schon: %s (%s)\n' "$NEW_TREE" "$WANT_TAG"
    exit 0
  fi
  printf 'ABBRUCH: %s existiert und ist nicht der erwartete %s-Commit.\n' "$NEW_TREE" "$WANT_TAG"
  exit 1
fi
if [[ ! -d "$OLD_TREE/.git" ]]; then
  printf '%s\n' "ABBRUCH: Quell-Tree fehlt."
  exit 1
fi

printf '%s\n' "Fetch $WANT_TAG"
if ! git -C "$OLD_TREE" rev-parse --verify "refs/tags/$WANT_TAG" >/dev/null 2>&1; then
  git -C "$OLD_TREE" fetch origin "refs/tags/$WANT_TAG:refs/tags/$WANT_TAG"
fi
git clone --branch "$WANT_TAG" --single-branch "$OLD_TREE" "$NEW_TREE"
got="$(git -C "$NEW_TREE" rev-parse HEAD)"
if [[ "$got" != "$WANT_COMMIT" ]]; then
  printf 'ABBRUCH: Clone-Commit %s, erwartet %s. Lösche Tree.\n' "$got" "$WANT_COMMIT"
  rm -rf "$NEW_TREE"
  exit 1
fi
version="$(python3 -c "import tomllib; print(tomllib.load(open('$NEW_TREE/pyproject.toml','rb'))['project']['version'])")"
if [[ "$version" != "0.37.0" ]]; then
  printf 'ABBRUCH: pyproject version=%s\n' "$version"
  rm -rf "$NEW_TREE"
  exit 1
fi
cp -a "$OLD_TREE/extra_model_paths.yaml" "$NEW_TREE/extra_model_paths.yaml"
mkdir -p "$NEW_TREE/output" "$NEW_TREE/input" "$NEW_TREE/temp"
printf 'OK   %s commit %s\n' "$NEW_TREE" "$got"
