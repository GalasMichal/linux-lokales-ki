# Issue: ledger parser and totals are wrong

The cash ledger drops lines, ignores negative amounts, and the report does not match the balance.

Work only in this directory:
{workspace}

## Visible tests (must pass)

```
python3 -m pytest -q test_visible.py
```

Those tests currently fail. Fix the code so they pass.

## MUST requirements (do not drop these)

1. Lines are `ID|YYYY-MM-DD|amount` with ISO dates. Invalid lines raise `ValueError`.
2. Never drop existing entry ids from parse or report.
3. Debits are negative, credits are positive. Balance may be negative.
4. `report_totals` must match `balance()`.
5. Do not add third-party packages.

Do not edit files outside this directory. Stop when the visible tests pass and the MUST items still hold.
