# Issue: config loader ignores env and mutates defaults

Loading app config is wrong. Environment overrides do not win, unknown keys are accepted, and DEFAULTS is mutated.

Work only in this directory:
{workspace}

## Visible tests (must pass)

```
python3 -m pytest -q test_visible.py
```

Those tests currently fail. Fix the code so they pass.

## MUST requirements (do not drop these)

1. `DEFAULTS` must be unchanged after any load.
2. Unknown keys must raise `ValueError`.
3. Precedence: env overrides file, file overrides defaults.
4. `port` from env string `"9000"` must become int `9000`.
5. `load_file(path)` must keep working without env.
6. Do not add third-party packages.

Do not edit files outside this directory. Stop when the visible tests pass and the MUST items still hold.
