"""Workspace and filesystem guards for local MCP tools."""

from __future__ import annotations

import os
from pathlib import Path

from errors import ToolError


DEFAULT_ALLOWED_ROOTS = (
    Path("/home/mike/Projects"),
    Path("/srv/ai/workspaces"),
    Path("/mnt/ai-archive"),
    Path("/tmp"),
    Path("/var/tmp"),
)

_UNSAFE_PARTS = {".git", ".ssh", ".gnupg", ".qwen"}


def allowed_roots() -> tuple[Path, ...]:
    extra = os.environ.get("LOCAL_AI_ALLOWED_ROOTS", "").strip()
    if not extra:
        return DEFAULT_ALLOWED_ROOTS
    roots = [Path(item).expanduser() for item in extra.split(os.pathsep) if item.strip()]
    return tuple(path.resolve() for path in roots)


def resolve_workspace(workspace: str | Path | None) -> Path:
    raw = str(workspace or "").strip() or os.environ.get("AGENT_WORKSPACE", "").strip()
    if not raw:
        raise ToolError("workspace ist Pflicht. Nutze den Git- bzw. Qwen-Workspace-Pfad.")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ToolError(f"Workspace existiert nicht: {path}") from exc
    if not resolved.is_dir():
        raise ToolError(f"Workspace ist kein Verzeichnis: {resolved}")
    _assert_allowed(resolved)
    return resolved


def resolve_existing_file(path: str | Path, suffixes: set[str] | None = None) -> Path:
    resolved = _resolve(path, must_exist=True)
    if not resolved.is_file():
        raise ToolError(f"Datei nicht gefunden: {resolved}")
    _assert_suffix(resolved, suffixes)
    return resolved


def resolve_output_path(path: str | Path, suffixes: set[str] | None = None) -> Path:
    resolved = _resolve(path, must_exist=False)
    _assert_suffix(resolved, suffixes)
    parent = resolved.parent
    if not parent.exists():
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ToolError(f"Ausgabeverzeichnis konnte nicht angelegt werden: {parent}") from exc
    if not parent.is_dir():
        raise ToolError(f"Ausgabeverzeichnis ist ungültig: {parent}")
    _assert_allowed(parent)
    return resolved


def resolve_dir(path: str | Path, create: bool = False) -> Path:
    resolved = _resolve(path, must_exist=not create)
    if create:
        resolved.mkdir(parents=True, exist_ok=True)
    if not resolved.is_dir():
        raise ToolError(f"Verzeichnis nicht gefunden: {resolved}")
    return resolved


def _resolve(path: str | Path, *, must_exist: bool) -> Path:
    raw = str(path or "").strip()
    if not raw:
        raise ToolError("Pfad darf nicht leer sein.")
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    if must_exist:
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ToolError(f"Pfad nicht gefunden: {candidate}") from exc
    else:
        parent = candidate.parent
        if not parent.exists():
            resolved = candidate
        else:
            resolved = parent.resolve(strict=True) / candidate.name
    _assert_allowed(resolved if resolved.exists() else resolved.parent)
    _assert_safe_parts(resolved)
    return resolved


def _assert_allowed(path: Path) -> None:
    resolved = path.resolve() if path.exists() else path
    for root in allowed_roots():
        try:
            resolved.relative_to(root)
            return
        except ValueError:
            continue
    raise ToolError(f"Pfad liegt außerhalb der erlaubten Arbeitsbereiche: {resolved}")


def _assert_safe_parts(path: Path) -> None:
    if any(part in _UNSAFE_PARTS for part in path.parts):
        raise ToolError("Dieser Pfad ist für Agent-Tools gesperrt.")


def _assert_suffix(path: Path, suffixes: set[str] | None) -> None:
    if not suffixes:
        return
    suffix = path.suffix.lower()
    allowed = {item.lower() for item in suffixes}
    if suffix not in allowed:
        raise ToolError(f"Unerlaubte Dateiendung '{suffix}'. Erlaubt: {', '.join(sorted(allowed))}")
