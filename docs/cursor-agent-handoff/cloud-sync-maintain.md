# Cloud sync — maintain agent docs (stub)

**Edit source:** mg-games Project store (`preferences.md`, `workflows/`, `docs/`).

**Cloud read path:** commit mirror in [kinder-spiele `docs/agent/`](https://github.com/GalasMichal/kinder-spiele/tree/master/docs/agent) + Cursor Project Context + User Rules.

**On Vollstrecker after store changes:**

```bash
~/Projects/kinder-spiele/tools/sync-agent-docs.sh
# review docs/agent/, update AGENT-CONTEXT.md if needed, commit + push kinder-spiele
```

Full checklist: Project store `docs/cloud-sync-maintain.md` (same path under `bc-14f20dd9-…/files/docs/`).

**This folder** (`docs/cursor-agent-handoff/`) is the pointer from **linux-lokales-ki** so Qwen Code and local stack agents discover game workflows without hunting the Cursor store.
