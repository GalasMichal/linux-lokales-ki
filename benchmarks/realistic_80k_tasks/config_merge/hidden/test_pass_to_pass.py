from defaults import DEFAULTS
from validate import ALLOWED


def test_defaults_table_present() -> None:
    assert set(DEFAULTS) == {"host", "port", "debug"}
    assert ALLOWED == {"host", "port", "debug"}
