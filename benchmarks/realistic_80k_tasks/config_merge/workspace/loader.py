import json
from pathlib import Path

from defaults import DEFAULTS
from validate import validate


def load_file(path: str) -> dict:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    # BUG: mutates the shared DEFAULTS dict
    DEFAULTS.update(raw)
    return DEFAULTS


def load_with_env(path: str, env: dict[str, str]) -> dict:
    data = load_file(path)
    # BUG: no type coercion, unknown keys accepted, env dumped as strings
    data.update(env)
    return validate(data)
