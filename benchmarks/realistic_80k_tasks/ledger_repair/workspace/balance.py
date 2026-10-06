from entries import Entry


def balance(rows: list[Entry]) -> int:
    # BUG: ignores negative amounts
    return sum(abs(row.amount) for row in rows)
