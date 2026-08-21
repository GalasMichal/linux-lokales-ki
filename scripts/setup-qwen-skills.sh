#!/usr/bin/env bash
# Link repo skills/ into .qwen/skills/ with relative symlinks.
# Idempotent. No sudo. Does not write ~/.qwen/settings.json.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$REPO_ROOT/skills"
LINK_DIR="$REPO_ROOT/.qwen/skills"
MODE="install"

usage() {
  cat <<'EOF'
Usage: scripts/setup-qwen-skills.sh [--check|--uninstall|--help]

  (default)   Create or repair relative symlinks .qwen/skills/<name> -> ../../skills/<name>
  --check     Verify source files, links, and SKILL.md frontmatter. Exit 1 on errors.
  --uninstall Remove only links that point into this repo's skills/ directory.
  --help      Show this help.

Does not change ~/.qwen/settings.json or Ollama.
EOF
}

relative_target() {
  # From .qwen/skills/<name> the source is always ../../skills/<name>
  printf '%s\n' "../../skills/$1"
}

is_our_link() {
  local link_path="$1"
  [[ -L "$link_path" ]] || return 1
  local target
  target="$(readlink -- "$link_path")"
  [[ "$target" == "../../skills/"* ]] || return 1
  return 0
}

frontmatter_ok() {
  local skill_md="$1"
  python3 - "$skill_md" <<'PY'
import re, sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
match = re.match(r"^---\n([\s\S]*?)\n---(?:\n|$)", text)
if not match:
    print(f"FAIL {path}: missing YAML frontmatter")
    sys.exit(1)
block = match.group(1)
has_name = re.search(r"^name:\s*\S", block, re.M)
has_desc = re.search(r"^description:\s*\S", block, re.M) or re.search(
    r"^description:\s*>\s*$", block, re.M
)
if not has_name:
    print(f"FAIL {path}: missing name")
    sys.exit(1)
if not has_desc:
    print(f"FAIL {path}: missing description")
    sys.exit(1)
print(f"OK   frontmatter {path}")
PY
}

list_skill_names() {
  local name
  if [[ ! -d "$SOURCE_DIR" ]]; then
    return 0
  fi
  find "$SOURCE_DIR" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | LC_ALL=C sort | while read -r name; do
    if [[ -f "$SOURCE_DIR/$name/SKILL.md" ]]; then
      printf '%s\n' "$name"
    fi
  done
}

cmd_install() {
  if [[ ! -d "$SOURCE_DIR" ]]; then
    printf '%s\n' "ABBRUCH: Quelle fehlt: $SOURCE_DIR"
    exit 1
  fi
  mkdir -p "$LINK_DIR"
  local name expected current
  local created=0 repaired=0 kept=0 skipped=0
  while read -r name; do
    [[ -n "$name" ]] || continue
    expected="$(relative_target "$name")"
    local link_path="$LINK_DIR/$name"
    if [[ -L "$link_path" ]]; then
      current="$(readlink -- "$link_path")"
      if [[ "$current" == "$expected" ]]; then
        printf '%s\n' "OK     $name  $current"
        kept=$((kept + 1))
        continue
      fi
      printf '%s\n' "REPAIR $name  $current -> $expected"
      ln -sfn -- "$expected" "$link_path"
      repaired=$((repaired + 1))
      continue
    fi
    if [[ -e "$link_path" ]]; then
      printf '%s\n' "SKIP   $name  existiert und ist kein Symlink: $link_path"
      skipped=$((skipped + 1))
      continue
    fi
    ln -s -- "$expected" "$link_path"
    printf '%s\n' "LINK   $name  -> $expected"
    created=$((created + 1))
  done < <(list_skill_names)
  printf '%s\n' "Fertig: neu=$created repariert=$repaired unverändert=$kept übersprungen=$skipped"
}

cmd_uninstall() {
  if [[ ! -d "$LINK_DIR" ]]; then
    printf '%s\n' "Nichts zu entfernen: $LINK_DIR fehlt."
    return 0
  fi
  local removed=0 skipped=0
  local entry
  for entry in "$LINK_DIR"/*; do
    [[ -e "$entry" || -L "$entry" ]] || continue
    local name
    name="$(basename -- "$entry")"
    if is_our_link "$entry"; then
      rm -- "$entry"
      printf '%s\n' "UNLINK $name"
      removed=$((removed + 1))
    else
      printf '%s\n' "KEEP   $name  (kein Repo-Link)"
      skipped=$((skipped + 1))
    fi
  done
  printf '%s\n' "Fertig: entfernt=$removed belassen=$skipped"
}

cmd_check() {
  local errors=0
  local name
  if [[ ! -d "$SOURCE_DIR" ]]; then
    printf '%s\n' "FAIL Quelle fehlt: $SOURCE_DIR"
    return 1
  fi
  while read -r name; do
    [[ -n "$name" ]] || continue
    local skill_md="$SOURCE_DIR/$name/SKILL.md"
    if ! frontmatter_ok "$skill_md"; then
      errors=$((errors + 1))
    fi
    if grep -Eiq 'composer-2\.5|claude-opus|cursor-grok|~/.cursor/|Task tool|AskQuestion' "$skill_md"; then
      printf '%s\n' "FAIL $name: Cursor-spezifische Reste in SKILL.md"
      errors=$((errors + 1))
    else
      printf '%s\n' "OK   portable $name"
    fi
    local link_path="$LINK_DIR/$name"
    local expected
    expected="$(relative_target "$name")"
    if [[ ! -L "$link_path" ]]; then
      printf '%s\n' "FAIL Link fehlt: $link_path"
      errors=$((errors + 1))
      continue
    fi
    local current
    current="$(readlink -- "$link_path")"
    if [[ "$current" != "$expected" ]]; then
      printf '%s\n' "FAIL $name: Link $current, erwartet $expected"
      errors=$((errors + 1))
      continue
    fi
    if [[ ! -f "$link_path/SKILL.md" ]]; then
      printf '%s\n' "FAIL $name: Ziel SKILL.md nicht lesbar"
      errors=$((errors + 1))
      continue
    fi
    printf '%s\n' "OK   link $name -> $current"
  done < <(list_skill_names)
  if [[ "$errors" -ne 0 ]]; then
    printf '%s\n' "CHECK FAIL ($errors Fehler)"
    return 1
  fi
  printf '%s\n' "CHECK PASS"
  return 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check) MODE="check"; shift ;;
    --uninstall) MODE="uninstall"; shift ;;
    --help|-h) usage; exit 0 ;;
    *)
      printf '%s\n' "Unbekanntes Argument: $1"
      usage
      exit 2
      ;;
  esac
done

case "$MODE" in
  install) cmd_install ;;
  uninstall) cmd_uninstall ;;
  check) cmd_check ;;
esac
