# Release approval gate (mg-games / kinder-spiele)

**Order matters:**

1. **Visual review gate** — No UI/layout/CSS/scale/website change is finished without the checklist in [visual-review-gate.md](https://github.com/GalasMichal/kinder-spiele/blob/master/docs/agent/visual-review-gate.md).
2. **Visual review A–Z** — Every **visible** fix gets a **separate** review agent after implementation; **PASS** before coordinator tells Mike the fix is ready ([visual-review-az.md](https://github.com/GalasMichal/kinder-spiele/blob/master/docs/agent/visual-review-az.md)).
3. **Mike OK (release / sign-off)** — Agents own builds, emulator/browser QA, and normal repo hygiene on Vollstrecker. Do **not** treat a task as “released” or ask Mike to verify until steps 1–2 pass. **Store/play release**, version bumps meant for production, or **push/deploy when Mike said to wait** only after he explicitly approves.

**FAIL** at any step → back to implementation; do not skip to Mike.

**Canonical index:** [AGENT-CONTEXT.md](https://github.com/GalasMichal/kinder-spiele/blob/master/docs/agent/AGENT-CONTEXT.md)
