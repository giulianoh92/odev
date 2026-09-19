---
name: odev
description: "Trigger when working in an Odoo project managed by the `odev` CLI: containers, module install/update, running tests, or shell/SQL/Python access into the stack. Matches a `.odev.yaml` or `odev.yaml` file, an `__manifest__.py`, a `docker-compose.yml` with an odoo service, the `ODEV_PROJECT` env var, or the user mentioning odev / their Odoo stack. Covers project resolution, MCP-vs-CLI selection, the odoo-shell transaction trap, the one-run test protocol, CSV module semantics, destructive-command guards, and exit codes."
---

# odev — Odoo dev stack workflow

`odev` is a per-project Docker stack for Odoo development. It exposes an MCP server
(`mcp__odev__*`, requires the `mcp` extra) alongside the bash CLI. Prefer MCP when both
work: it returns parsed structures instead of text you have to scrape.

Verified against repo HEAD at commit `3082712` on 2026-09-19. The `--tags` semantics and
the test protocol below reflect that commit's behavior, released as 0.10.0 — if the
installed package still reports an older version string, trust this document and the
source, not the version string.

## THE TRANSACTION TRAP (read this first)

**`odev py` and `mcp__odev__odev_py` DISCARD writes unless you commit explicitly.**

`odev py` is a thin wrapper: it pipes `print(<your expression>)` into
`odoo shell -d <db>` inside the `web` container. It adds no transaction handling, so
Odoo's own shell decides the outcome — and `odoo/cli/shell.py` (19.0) does this:

```python
cr.rollback()            # clears the transaction context_get() opened
self.console(local_vars) # <- your expression runs here
cr.rollback()            # <- DISCARDS everything you did not commit
```

Dry-run is therefore the DEFAULT and costs nothing. To persist, end with `env.cr.commit()`:

```python
# WRONG — the write is silently discarded when the shell exits
odev_py(expression="env['res.partner'].create({'name': 'Test'})")

# RIGHT — explicit commit
odev_py(expression="(env['res.partner'].create({'name': 'Test'}), env.cr.commit())")
```

**odev's own docs contradict this and are wrong.** `README.md`, the `odev py --help` text,
and the generated `claude-md.j2` project template all claim side effects "se commitean" and
tell you to call `env.cr.rollback()` for a dry-run. That is inverted. Trust the Odoo source
above, not those three. (Confirmed 2026-07-27, re-confirmed 2026-09-19 against odoo/odoo 19.0.)

`odev py` wraps its argument in `print(...)`, so it takes a **single expression**. No
statements, no assignments at top level, no `;` chaining — all syntax errors. Use a tuple
when you need two effects, as above.

## THE ONE-RUN TEST PROTOCOL (read this before running tests)

**Do not run the test battery three times.** The default failure pattern: run
`odev test` in summary mode, hit a failure, re-run with `--verbose` to read the
traceback, apply a fix, then re-run the whole battery to confirm. On a project with a
non-trivial test suite that is three full runs at 5-10 minutes each — and two of the
three are avoidable.

### The protocol

1. **Always run once, capturing both machine-readable and raw output:**

   ```
   odev test <modules> --json --save-log <scratchpad>/odev-test-<modules>-<timestamp>.log
   ```

2. **Diagnose from the JSON. Never re-run with `--verbose` to see a traceback.**
   The `failures[]` array already carries, per failure: `class`, `method`, `kind`
   (`FAIL` / `ERROR` / `LOADING_ERROR`), `message`, and `traceback` — the complete
   captured traceback: file, line number, the failing expression and the exception.

3. **Read the saved log only when `parse_failed` is `true`.** That is the one case
   where the JSON cannot tell you anything about the run, and the raw log is the
   fallback.

4. **After fixing, re-run only what failed — never the whole battery.**
   - One test: `odev test <module>:<Class>.<method>`
   - Several: the comma-OR form on `--tags` —
     `odev test <module> --tags ":<ClassA>.<test_x>,:<ClassB>.<test_y>"`

5. **Run the full battery one final time only when the fix could plausibly regress
   something outside its blast radius.** Not reflexively, on every fix.

### Why this is safe — the facts, not just the shortcut

- **`--save-log` writes every raw line Odoo emits, unconditionally.** In
  `_stream_and_collect` (`src/odev/commands/test.py`), the `echo` parameter — the one
  `--verbose` sets — only controls whether a line is *also* re-emitted live to stdout;
  the write to `save_log_path` happens regardless of `echo`. `--verbose` adds **nothing**
  to the saved file that a plain `--json --save-log` run does not already capture.
- **`--verbose` is mutually exclusive with `--json` / `--summary` / `--failures`
  (exit 2)**, because the raw stream is never parsed. The "quick `--verbose` re-run" was
  never a cheap add-on to the first run — it was always a second full battery, end to end.
- **The comma-OR semantics of `--test-tags`** — the exact mechanism that leaked into
  module prefixes and caused the bug fixed in 0.10.0 — is exactly the right tool for
  re-running N specific failed tests in a single pass, once you target it explicitly
  instead of letting odev auto-generate `/module` prefixes.

**Caveat on `--tags ":Class.method"`:** a spec with no tag component defaults to the
`standard` tag, which matches nearly every test, including `post_install` ones. A test
explicitly excluded from `standard` needs its own tag named explicitly, or a narrow
re-run using only `:Class.method` will silently skip it.

### Cost comparison

| Pattern | Runs | Rough cost |
|---|---|---|
| Old: summary → `--verbose` → full re-run | 3 full batteries | 15-30 min |
| New: one `--json --save-log` → N narrow re-runs → optional full re-run | 1 full + N narrow (seconds each) + at most 1 optional full | 5-10 min (+ optional 5-10 min) |

### Gotcha: an unimported test file runs zero tests, silently

Odoo only discovers test modules that are **imported** in the addon's
`tests/__init__.py` — Odoo's `get_test_modules` uses
`inspect.getmembers(mod, inspect.ismodule)`, and a submodule only becomes an attribute
of the package once something imports it. A `test_*.py` file that nobody imports
contributes **zero** tests, and the run reports success: no error, no warning, just a
smaller `total` than you expected.

Verified empirically: the same file ran 0 tests before its import line was added to
`tests/__init__.py`, and 2 after.

## Project resolution

Resolution order (`src/odev/core/resolver.py`), first match wins:

1. Explicit name — `--project/-p` flag, else `ODEV_PROJECT` env var (flag wins) → registry lookup.
2. **Inline walk** — walks up from cwd looking for **`.odev.yaml` only** (dot-prefixed).
3. Registry lookup by cwd containment. Multiple matches raise `ProyectoAmbiguoError` telling you to pass `--project`.
4. Legacy detection — `docker-compose.yml` + a `cli/` directory, no yaml at all. Fix with `odev migrate`.
5. Otherwise `ProyectoNoEncontradoError`.

Config filename: both `.odev.yaml` and `odev.yaml` are accepted once the directory is known,
with **`.odev.yaml` taking priority if both exist**. But the cwd walk in step 2 recognizes
**only the dot form** — a project carrying a bare `odev.yaml` in the cwd tree will NOT be
auto-discovered; it must be registered or targeted with `--project`/`ODEV_PROJECT`.

Global state lives under `~/.odev/`: `registry.yaml` (project registry, flock-guarded),
`projects/<name>/` (external-mode configs), `enterprise/<version>/` (shared enterprise addons).

`ODEV_PROJECT` lets an agent target a project without `cd`-ing — it is honored by every CLI
command and by the MCP server.

## MCP vs CLI selection

All 9 MCP tools resolve project context the same way the CLI does.

| Task | Use | Returns |
|---|---|---|
| Service state | `mcp__odev__odev_status` | `list[dict]` |
| Diagnostics | `mcp__odev__odev_doctor` | `dict` — version, checks[], summary, exit_code |
| SQL query | `mcp__odev__odev_sql` | `list[dict]` — **all values are strings** |
| Eval Python | `mcp__odev__odev_py` | `str`, banner stripped |
| Run tests | `mcp__odev__odev_test` | `dict` — TestResult with failures[] |
| Logs | `mcp__odev__odev_logs` | `list[dict]` — **snapshot only, never follows** |
| Installed modules | `mcp__odev__odev_modules` | `list[dict]` |
| Model introspection | `mcp__odev__odev_model_info` | `dict` — fields, inherits, relations |
| Command in container | `mcp__odev__odev_shell` | `dict` — stdout, stderr, returncode |

CLI-only (not exposed over MCP): lifecycle (`up`, `down`, `restart`), `init`, `adopt`,
`migrate`, `reconfigure`, `scaffold`, `reset-db`, `load-backup`, `context`, `tui`,
`self-update`, and the `db` / `projects` / `enterprise` subgroups. Also CLI-only:
`test --save-log <path>`, `sql --csv`, streaming `logs --follow`, interactive `shell`.

### MCP error shapes differ from the CLI

MCP tools have no exit codes. Failures surface as `ToolError` / `ResourceError`, and
`odev://modules/{name}/manifest` raises `ResourceNotFoundError` for an unknown module.

Do not port CLI error parsing to MCP. Concretely: `odev doctor --json` with no project
writes the literal `{"error": "no project context"}` to stderr and exits 1, but
`mcp__odev__odev_doctor` raises a `ToolError` reading `No odev project found: ...`.
Different shape, different channel.

Since the SDK 2.x migration every tool is wrapped so `ValueError`/`RuntimeError` reach you
with their real message (the PostgreSQL error line, "stack not running", docker's own text).
Any other exception type is an odev bug and arrives as a bare `Error executing tool <name>`
with detail only in the server log.

## Resources

| URI | Content |
|---|---|
| `odev://project/context` | Markdown: layout, Odoo version, modules (same as `odev context`) |
| `odev://project/config` | Parsed yaml config as JSON |
| `odev://db/schema` | `pg_dump --schema-only` |
| `odev://modules/{name}/manifest` | Parsed `__manifest__.py` |

Discover with `ListMcpResourcesTool`, fetch with `ReadMcpResourceTool`.

Prompts: `diagnose_failing_test`, `explain_module`, `generate_migration`.

## Output defaults changed in 0.7.0 (breaks pre-0.7 automation)

`test`, `update` and `addon-install` now emit the **compact parsed summary by default in
all cases**, TTY or not. The old raw interactive stream requires explicit `--verbose/-v`.

`--verbose` is mutually exclusive with `--json`, `--summary` and `--failures` → exit 2.
Raw streams cannot be parsed, so asking for both is rejected rather than guessed.

`test` also derives its exit code from the **parsed** result when the Odoo process exits 0.
Odoo 19 returns 0 from `--test-enable --stop-after-init` even with failing tests, so
checking only the process exit code is a false-positive trap that odev now closes for you.

## CSV module semantics

`test`, `update` and `addon-install` accept CSV in the module argument: `"sale,crm,stock"`.

This is **ONE Odoo invocation** (`-u sale,crm,stock`), not N sequential runs — a failure
anywhere fails the whole batch. Auto-generated `--test-tags` become `/sale,/crm,/stock`, so
failures stay attributable in the parsed result even though the process is unified.

Spaces are fine: each token is `.strip()`ed, so `"sale, crm"` parses correctly.

`all` is exclusive. Combining it with anything else (`"sale,all"`) exits 2.

### `--tags` replaces the auto-generated module prefix (fixed in 0.10.0)

Before 0.10.0, `--tags` was **appended** to the auto-generated `/module` prefixes:
`odev test sale --tags foo` emitted `--test-tags /sale,foo`. Odoo ORs comma-separated
specs (`_build_test_tags` in `src/odev/commands/test.py`, backed by
`odoo/tests/tag_selector.py`), so that ran the entire `sale` module and silently ignored
the filter — the flag looked like it worked but did nothing.

0.10.0 fixes this: passing `--tags` now **replaces** the auto-generated prefixes
entirely. The same command emits `--test-tags foo`, and `-u sale` alone does the module
scoping. If you need to filter within specific modules, write the full expression
yourself — odev no longer merges it with anything on your behalf.

### Test target shorthand

```
mcp__odev__odev_test(module="mymod:TestFoo.test_bar")
```

Expands to `--test-tags /mymod:TestFoo.test_bar`. Bare `"mymod"` still works. CSV combined
with a colon, and `all:Class`, are rejected outright with exit 2 rather than guessed.

**Combining the shorthand with `--tags` is also rejected, with exit 2.** Both define the
test filter — `mymod:TestFoo.test_bar --tags foo` would union them via the same OR
semantics described above, which is exactly the silent over-broad match 0.10.0 is trying
to eliminate. Pick one: the shorthand, or `--tags` with the complete expression.

## Destructive commands — the guards are NOT uniform

| Command | Destroys | Non-interactive guard |
|---|---|---|
| `odev down -v` / `--volumes` | DB + filestore volumes | **NONE — no prompt, no `--yes`. It just does it.** |
| `odev reset-db` | DB + volumes, reinit | `--yes/-y`, `--dry-run` |
| `odev load-backup <zip>` | overwrites DB | `--yes/-y`, `--dry-run` |
| `odev db restore <name>` | drops + recreates DB | `--yes/-y` |
| `odev db anonymize` | partner PII + **all user passwords → `admin`** | **NONE — no `--yes` exists.** Always prompts; only scriptable by piping `y`. |

`down -v` is the inverse trap of the others: the one that asks nothing is the one you reach
for casually. `db anonymize` is the opposite — it cannot be automated cleanly at all.

## Mutually exclusive flags (all exit 2)

- `test`/`update`/`addon-install`: `--verbose` vs `--json` / `--summary` / `--failures`
- `test`: the `module:Class.method` shorthand vs `--tags` — both would define the filter
- `sql`: `--json` vs `--csv`
- `logs`: `--json` vs `--follow`

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | project or runtime error — no project found, model absent from the ORM, enterprise version not imported |
| 2 | usage error — bad argument, unknown module, `all` mixed with names, conflicting flags |
| 3 | environment error — port busy, DB unavailable, Docker unavailable, stack down |

Exit 3 is not test-specific: `model-info` uses it when the stack is down, and `up` uses it
when a foreign process holds a configured port. `test` forces 3 defensively when output
contains "Address already in use" and parsing failed.

The 1-vs-2 split is "knowable upfront" vs "only knowable after querying the live system".
`model-info` on a nonexistent model is 1, not 2, because it took a live ORM query to find out.

## Discovery-first pattern

Before debugging or implementing, gather state instead of assuming it:

1. `mcp__odev__odev_doctor` — stack health. Failing? Fix the environment first.
2. `mcp__odev__odev_status` — services up, ports clear.
3. `ReadMcpResourceTool` on `odev://project/context` — module inventory and Odoo version.
4. `mcp__odev__odev_modules` — what is actually installed.
5. Unknown model? `mcp__odev__odev_model_info`.

## Reproducing production state locally

1. `odev load-backup /path/dump.zip` — auto-neutralizes crons and mail servers, resets admin/admin
2. `odev db anonymize` — PII scrub (interactive only)
3. `odev db snapshot pre-debug` — checkpoint
4. reproduce and iterate
5. `odev db restore pre-debug --yes` — roll back

## Caveats

- `odev up` may **silently restart `web`** mid-command: it fixes drifted dev-safety params
  (`report.url`, MailHog) once the DB is ready. Do not treat that restart as a fault.
- ORM and DB commands (`model-info`, `py`, `sql`, `model_info`) exec into the `web` container
  and require the stack to be **up**. Down stack surfaces as exit 3 or a `ToolError`, not exit 1.
- `odev_py` on models with 100+ fields returns single-line JSON. Do not pipe through `tail`.
- `odev_sql` values are all strings (psql text protocol). `CAST` in SQL when you need types.
- Module existence is validated against `paths.addons` from the yaml config before falling
  back to layout heuristics — bypass with `--no-validate` if a legitimate module is rejected.
