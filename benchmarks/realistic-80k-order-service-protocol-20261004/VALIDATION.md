# order_service 80K protocol validation (2026-10-04)

Not comparable to `realistic-80k-20261004` without reading `MANIFEST.json`.

## Prompt delta

- Base: same `issue.md` fixture and hidden MUST tests.
- Added: `PROTOCOL_WORKFLOW_v1.md` (tool_search, checklist, self-check, MUST reminder).

## Results

- Valid runs: 3 (target 3)
- Invalid runs: 0
- Full task success (resolved): 2/3
- MUST violations (valid runs): 1
- Tool/protocol on valid runs: 0

### Valid runs

- slot 1 run_id=1 class=pass resolved=True visible=True musts=True tools_failed=1
- slot 2 run_id=2 class=must_loss resolved=False visible=True musts=False tools_failed=1
- slot 3 run_id=3 class=pass resolved=True visible=True musts=True tools_failed=0

**Recommendation:** Stay 64K prod; 80K remains candidate (protocol validation did not clear MUST)
