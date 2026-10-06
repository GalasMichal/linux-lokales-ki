import json
from pathlib import Path

from defaults import DEFAULTS
from loader import load_with_env


def test_env_overrides_file_and_coerces_port(tmp_path: Path) -> None:
    cfg = tmp_path / "app.json"
    cfg.write_text(json.dumps({"host": "10.0.0.2", "port": 7000}), encoding="utf-8")
    data = load_with_env(str(cfg), {"port": "9000"})
    assert data["host"] == "10.0.0.2"
    assert data["port"] == 9000
    assert data["debug"] is False
    assert DEFAULTS["port"] == 8080
    assert DEFAULTS["host"] == "127.0.0.1"


def test_unknown_key_rejected(tmp_path: Path) -> None:
    cfg = tmp_path / "app.json"
    cfg.write_text(json.dumps({"host": "10.0.0.2", "extra": True}), encoding="utf-8")
    raised = False
    try:
        load_with_env(str(cfg), {})
    except ValueError:
        raised = True
    assert raised
