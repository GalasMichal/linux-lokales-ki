import ast
from pathlib import Path

from entries import parse_line


FORBIDDEN = {"requests", "httpx", "numpy", "pandas", "docker"}


def test_invalid_line_raises() -> None:
    raised = False
    try:
        parse_line("not-a-row")
    except ValueError:
        raised = True
    assert raised


def test_iso_date_kept() -> None:
    row = parse_line("z9|2026-12-31|-3")
    assert row.day == "2026-12-31"
    assert row.amount == -3


def test_no_third_party_imports() -> None:
    root = Path.cwd()
    for path in root.glob("*.py"):
        if path.name.startswith("test_"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            for name in names:
                assert name not in FORBIDDEN
