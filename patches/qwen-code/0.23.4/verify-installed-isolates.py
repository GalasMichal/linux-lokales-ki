#!/usr/bin/env python3
"""Isolate select: and keyword cases against the installed ToolSearch helpers."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

TARGET = Path(
    os.environ.get(
        "QWEN_TOOLSEARCH_CHUNK",
        "/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/tool-search-XCEN7VXX.js",
    )
)
GIT_CHUNK = Path(
    os.environ.get(
        "QWEN_GIT_CHUNK",
        "/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/chunk-NXUZFW3G.js",
    )
)
REGISTRY = Path(
    os.environ.get(
        "QWEN_REGISTRY_CHUNK",
        "/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/chunk-DCRVSIK6.js",
    )
)
NODE = Path(
    os.environ.get(
        "QWEN_NODE",
        "/srv/ai/apps/qwen-code/lib/qwen-code/node/bin/node",
    )
)

HARNESS = r"""
function __name() {}
const source = process.env.QWEN_TOOLSEARCH_SOURCE;
const start = source.indexOf("function mcpShortNameForSelect");
const end = source.indexOf("function tokenize(");
if (start < 0 || end < 0 || end <= start) {
  throw new Error("installed helpers not found");
}
eval(source.slice(start, end));
const mode = process.env.QWEN_TOOLSEARCH_MODE;
if (mode === "select") {
  const names = JSON.parse(process.env.QWEN_TOOLSEARCH_NAMES);
  const lowerIndex = new Map();
  for (const name of names) lowerIndex.set(name.toLowerCase(), name);
  process.stdout.write(JSON.stringify(resolveSelectToolName(process.env.QWEN_TOOLSEARCH_QUERY, lowerIndex)));
} else {
  const allNames = JSON.parse(process.env.QWEN_TOOLSEARCH_NAMES);
  const deferred = JSON.parse(process.env.QWEN_TOOLSEARCH_DEFERRED);
  const ranked = rankKeywordTools(
    process.env.QWEN_TOOLSEARCH_QUERY,
    allNames,
    deferred,
    5
  );
  process.stdout.write(JSON.stringify(ranked));
}
"""

VISIBLE = [
    "read_file",
    "write_file",
    "tool_search",
    "mcp__local-tools__generate_image",
    "mcp__local-tools__memory_load",
    "mcp__local-tools__memory_update",
    "mcp__local-tools__pdf_create",
    "mcp__local-tools__pdf_read",
    "mcp__local-tools__pdf_render",
    "mcp__local-tools__pdf_vision_qa",
]
DEFERRED = ["zoom_image", "record_artifact", "web_fetch"]
ALL_NAMES = VISIBLE + DEFERRED


def run_node(env_extra: dict[str, str]) -> object:
    env = os.environ.copy()
    env["QWEN_TOOLSEARCH_SOURCE"] = TARGET.read_text(encoding="utf-8")
    env.update(env_extra)
    proc = subprocess.run(
        [str(NODE), "-e", HARNESS],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.stderr or proc.stdout or f"node exit {proc.returncode}")
    return json.loads(proc.stdout)


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    if "function collectKeywordCandidateNames(" not in text:
        print("FAIL installed chunk has no collectKeywordCandidateNames")
        return 1
    if "function resolveSelectToolName(" not in text:
        print("FAIL installed chunk has no resolveSelectToolName")
        return 1
    git_text = GIT_CHUNK.read_text(encoding="utf-8")
    if "linux-lokales-ki-omit-git-snapshot" not in git_text:
        print("FAIL installed git chunk still injects git snapshot")
        return 1
    print("PASS git snapshot omitted from system prompt")
    reg_text = REGISTRY.read_text(encoding="utf-8")
    if "resolveMcpShortToolName(" not in reg_text:
        print("FAIL installed registry chunk has no MCP short-name resolver")
        return 1
    print("PASS registry MCP short-name")
    failed = 0

    def check(label: str, got, expected) -> None:
        nonlocal failed
        ok = got == expected if not callable(expected) else expected(got)
        print(("PASS" if ok else "FAIL"), label, json.dumps(got, ensure_ascii=False))
        if not ok:
            print("  expected", expected)
            failed += 1

    for short, full in (
        ("generate_image", "mcp__local-tools__generate_image"),
        ("memory_load", "mcp__local-tools__memory_load"),
        ("pdf_create", "mcp__local-tools__pdf_create"),
        ("pdf_read", "mcp__local-tools__pdf_read"),
        ("pdf_render", "mcp__local-tools__pdf_render"),
        ("pdf_vision_qa", "mcp__local-tools__pdf_vision_qa"),
    ):
        check(
            f"select:{short}",
            run_node(
                {
                    "QWEN_TOOLSEARCH_MODE": "select",
                    "QWEN_TOOLSEARCH_QUERY": short,
                    "QWEN_TOOLSEARCH_NAMES": json.dumps(VISIBLE),
                }
            ),
            {"status": "ok", "name": full},
        )

    def contains_mcp(got) -> bool:
        return "mcp__local-tools__generate_image" in got

    def not_contains_mcp(got) -> bool:
        return "mcp__local-tools__generate_image" not in got

    common = {
        "QWEN_TOOLSEARCH_MODE": "keyword",
        "QWEN_TOOLSEARCH_NAMES": json.dumps(ALL_NAMES),
        "QWEN_TOOLSEARCH_DEFERRED": json.dumps(DEFERRED),
    }
    check("K1 image", run_node({**common, "QWEN_TOOLSEARCH_QUERY": "image"}), contains_mcp)
    check("K2 generate", run_node({**common, "QWEN_TOOLSEARCH_QUERY": "generate"}), contains_mcp)
    check(
        "K3 generate_image",
        run_node({**common, "QWEN_TOOLSEARCH_QUERY": "generate_image"}),
        contains_mcp,
    )
    check(
        "K4 database",
        run_node({**common, "QWEN_TOOLSEARCH_QUERY": "database"}),
        not_contains_mcp,
    )
    check(
        "K5 deferred zoom_image",
        run_node({**common, "QWEN_TOOLSEARCH_QUERY": "image"}),
        lambda got: "zoom_image" in got,
    )
    check(
        "K6 memory_load keyword",
        run_node({**common, "QWEN_TOOLSEARCH_QUERY": "memory_load"}),
        lambda got: "mcp__local-tools__memory_load" in got,
    )
    check(
        "K7 pdf_create keyword",
        run_node({**common, "QWEN_TOOLSEARCH_QUERY": "pdf_create"}),
        lambda got: "mcp__local-tools__pdf_create" in got,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
