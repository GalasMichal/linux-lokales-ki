"""Qwen ToolSearch helpers: select-alias + visible MCP keyword candidates.

Mirrors the patch inserted into Qwen Code 0.23.4
``lib/chunks/tool-search-XCEN7VXX.js``. Keep in lockstep with
``tool-search-insert.js``.
"""

from __future__ import annotations

from typing import Any

SCORE_NAME_EXACT_BUILTIN = 10
SCORE_NAME_SUBSTR_BUILTIN = 5
SCORE_NAME_EXACT_MCP = 12
SCORE_NAME_SUBSTR_MCP = 6


def mcp_short_name_for_select(full_name: str) -> str | None:
    """Return the MCP server-tool suffix, or None if not ``mcp__server__tool``."""
    if not full_name.lower().startswith("mcp__"):
        return None
    rest = full_name[5:]
    sep = rest.find("__")
    if sep <= 0:
        return None
    short_name = rest[sep + 2 :]
    return short_name or None


def is_mcp_tool_name(name: str) -> bool:
    return mcp_short_name_for_select(name) is not None


def resolve_select_tool_name(requested: str, all_tool_names: list[str]) -> dict[str, Any]:
    """Exact match first; then unique MCP short-name alias; else missing/ambiguous."""
    lower_index: dict[str, str] = {}
    for real_name in all_tool_names:
        lower_index[real_name.lower()] = real_name

    want = requested.lower()
    exact = lower_index.get(want)
    if exact is not None:
        return {"status": "ok", "name": exact}

    matches: list[str] = []
    seen: set[str] = set()
    for real_name in lower_index.values():
        short_name = mcp_short_name_for_select(real_name)
        if short_name and short_name.lower() == want and real_name not in seen:
            seen.add(real_name)
            matches.append(real_name)

    if len(matches) == 1:
        return {"status": "ok", "name": matches[0]}
    if len(matches) > 1:
        matches.sort()
        return {
            "status": "ambiguous",
            "requested": requested,
            "candidates": matches,
        }
    return {"status": "missing", "requested": requested}


def format_ambiguous(result: dict[str, Any]) -> str:
    names = ", ".join(result["candidates"])
    return f'Ambiguous tool name "{result["requested"]}". Use one of: {names}'


def format_not_found(names: list[str]) -> str:
    return "Not found: " + ", ".join(names)


def collect_keyword_candidate_names(
    all_names: list[str], deferred_hidden_names: list[str]
) -> list[str]:
    """Deferred-hidden tools plus already-visible MCP tools. No extra builtins."""
    hidden = {name.lower() for name in deferred_hidden_names}
    out: list[str] = []
    seen: set[str] = set()
    for name in all_names:
        key = name.lower()
        if key in seen:
            continue
        if key in hidden or is_mcp_tool_name(name):
            seen.add(key)
            out.append(name)
    return out


def score_keyword_tool_name(name: str, terms: list[str]) -> int:
    """Name scoring aligned with Qwen scoreTool (name branch only)."""
    is_mcp = is_mcp_tool_name(name)
    name_lower = name.lower()
    total = 0
    for term in terms:
        if not term:
            continue
        if (
            name_lower == term
            or name_lower.endswith("_" + term)
            or name_lower.endswith("." + term)
        ):
            total += SCORE_NAME_EXACT_MCP if is_mcp else SCORE_NAME_EXACT_BUILTIN
        elif term in name_lower:
            total += SCORE_NAME_SUBSTR_MCP if is_mcp else SCORE_NAME_SUBSTR_BUILTIN
    return total


def rank_keyword_tools(
    query: str,
    all_names: list[str],
    deferred_hidden_names: list[str],
    max_results: int = 5,
) -> list[str]:
    terms = [t for t in query.lower().split() if len(t) >= 2]
    scored: list[tuple[int, str]] = []
    for name in collect_keyword_candidate_names(all_names, deferred_hidden_names):
        score = score_keyword_tool_name(name, terms)
        if score > 0:
            scored.append((score, name))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [name for _, name in scored[:max_results]]
