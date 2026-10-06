from entries import Entry, parse_line


def test_empty_line_skipped_via_parse_text() -> None:
    from entries import parse_text

    rows = parse_text("\n\n")
    assert rows == []


def test_entry_dataclass_fields() -> None:
    row = Entry("x", "2026-01-01", 1)
    assert row.entry_id == "x"
    assert row.amount == 1
