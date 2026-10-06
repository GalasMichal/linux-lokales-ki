from balance import balance
from entries import parse_text
from report import report_lines, report_totals


SAMPLE = "a1|2026-10-01|100\na2|2026-10-02|-40\n"


def test_parse_pipe_rows_and_signed_balance() -> None:
    rows = parse_text(SAMPLE)
    assert [r.entry_id for r in rows] == ["a1", "a2"]
    assert balance(rows) == 60


def test_report_keeps_ids_and_matches_balance() -> None:
    rows = parse_text(SAMPLE)
    text = "\n".join(report_lines(rows))
    assert "a1" in text
    assert "a2" in text
    assert report_totals(rows) == balance(rows) == 60
