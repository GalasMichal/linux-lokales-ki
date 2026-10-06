from balance import balance
from entries import Entry


def report_lines(rows: list[Entry]) -> list[str]:
    # BUG: drops ids
    return [f"{row.day} {row.amount}" for row in rows]


def report_totals(rows: list[Entry]) -> int:
    return balance(rows)
