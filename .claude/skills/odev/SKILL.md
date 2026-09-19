---
name: odev
description: "Trigger: odev CLI/MCP, .odev.yaml/odev.yaml, __manifest__.py, docker-compose Odoo, ODEV_PROJECT. For MCP-vs-CLI, safe writes, destructive guards, one-run tests."
license: MIT
metadata:
  author: Giuliano
  version: "1.0.0"
---

## Activation Contract

Load when working in an Odoo project managed by `odev` (CLI or MCP): a
`.odev.yaml`/`odev.yaml`, an `__manifest__.py`, a `docker-compose.yml` with
an odoo service, `ODEV_PROJECT`, or an explicit mention of odev/the stack.

## Hard Rules

- Never report a `py`/`odev_py` write as persisted without `--commit`/
  `commit=True`. `odoo shell` rolls back on close; the write-detection
  warning has false negatives, so its absence proves nothing.
- Never run `down -v`, `reset-db`, `load-backup`, `db restore`, or `db
  anonymize` without deliberately choosing to destroy data — read the
  warning; use `-y/--yes` or `--dry-run` on purpose, not by reflex.
- Never treat a green test run as proof. Check `total` in the JSON, not
  only `failed`/`errors` — zero tests also exits 0.

## Decision Gates

| Situation | Use |
|---|---|
| Fits one of 9 MCP tools/4 resources | MCP — parsed output, translated errors |
| Lifecycle, `tui`, `--verbose`, `--save-log`, `--csv`, `--follow`, `projects`/`enterprise` | CLI only |
| ORM write via `py`/`odev_py` | Decide commit intent first |
| Running tests | One-run protocol, always |
| Destructive command | Confirm or `--yes`; `--dry-run` if unsure |

## Execution Steps

1. Resolve the project: `--project`/`ODEV_PROJECT`, else upward
   `.odev.yaml`/`odev.yaml` walk, else registry, else legacy detection.
2. Pick MCP or CLI per Decision Gates.
3. Before an ORM write, decide persistence intent; pass `--commit`/
   `commit=True` accordingly.
4. For tests, follow `testing.md`'s one-run protocol, not summary →
   verbose → full-rerun.
5. For destructive commands, read the warning before passing `--yes`.
6. On an unexpected result, check `troubleshooting.md` before concluding
   the tool is broken.

## Output Contract

Report the exact command/tool call, its exit code or `warning`/`error`
field, and whether a write committed. For tests, report
`total`/`passed`/`failed`/`errors` from the JSON, not a log impression.

## References

- `references/commands.md` — command surface, exit codes, rejected flag
  combinations, destructive-command table, project resolution.
- `references/testing.md` — one-run test protocol, `--tags` semantics.
- `references/troubleshooting.md` — symptom/cause/check/fix; `doctor` checks.
- `references/mcp.md` — 9 tools, 4 resources, 3 prompts, error translation.
