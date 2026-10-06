import ast
from pathlib import Path

from defaults import DEFAULTS


FORBIDDEN = {"requests", "httpx", "numpy", "pandas", "docker"}


def test_defaults_survive_load(tmp_path: Path) -> None:
    import json

    from loader import load_with_env

    cfg = tmp_path / "app.json"
    cfg.write_text(json.dumps({"host": "10.0.0.9"}), encoding="utf-8")
    try:
        load_with_env(str(cfg), {"port": "9000"})
    except ValueError:
        pass
    assert DEFAULTS["host"] == "127.0.0.1"
    assert DEFAULTS["port"] == 8080
    assert DEFAULTS["debug"] is False


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
