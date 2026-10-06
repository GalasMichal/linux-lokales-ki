from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    entry_id: str
    day: str
    amount: int


def parse_line(line: str) -> Entry:
    # BUG: splits on comma, so real '|' rows break
    parts = [p.strip() for p in line.split(",")]
    if len(parts) != 3:
        raise ValueError("bad line")
    return Entry(parts[0], parts[1], int(parts[2]))


def parse_text(text: str) -> list[Entry]:
    rows = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        rows.append(parse_line(raw))
    return rows
