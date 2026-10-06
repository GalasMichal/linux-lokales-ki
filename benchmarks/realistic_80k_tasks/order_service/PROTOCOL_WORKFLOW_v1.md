## Validation workflow (protocol v1 — not the original bench prompt)

This run is a **protocol validation** for 80K `order_service`. Follow this process exactly.

### Before any file operation

1. Call **`tool_search`** (or the project's tool-discovery tool) to find the correct tool names and **exact parameter schemas**.
2. Only call tools with parameter names from those schemas (e.g. use `file_path` for read_file if the schema says `file_path`, not `path`).

### Before editing code

3. Write a short **checklist** covering every requirement in this issue: visible pytest behavior **and** every MUST item (signatures, ValueError rules, tax order, member price scope, stdlib-only).

### After editing

4. **Self-check:** For each checklist line, confirm the changed code still satisfies it.
5. Run `python3 -m pytest -q test_visible.py` in the workspace yourself; fix failures and re-run until green.

### Grading

- Hidden MUST tests are scored separately. **Passing visible tests alone is not success.**
- Do not edit files outside this directory. Do not ask the user questions.
