---
name: verify-work
description: >
  Validate completed implementation work. Use after implementing features,
  fixing bugs, or before marking tasks done. Run tests, check types, report
  pass/fail. Do not re-implement unless asked.
---

# Verify work

Skeptical check that work is actually done.

When invoked:

1. Identify what changed (git diff, recent edits, or the stated scope)
2. Run relevant tests or build commands if the project has them
3. Check linter/type errors on touched files
4. Verify the implementation matches the stated requirement
5. Report findings as pass/fail

## Report format

- **Passed**: what works and evidence (command output, file checks)
- **Failed / incomplete**: specific gaps with file paths
- **Untested**: what could not be verified and why

## Rules

- Do not implement fixes unless explicitly asked — verify first
- Prefer minimal commands (`npm test`, `ng build`, targeted grep)
- Be concise; only actionable gaps
- Do not call Cursor-only tools or model-routing tables
