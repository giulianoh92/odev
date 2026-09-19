# odev — complete command surface

Global options on every command: `--project/-p <name>` (also `ODEV_PROJECT` env
var, flag wins), `--version/-V`, `--debug` (DEBUG-level logging).

## Stream contract

stdout carries data only: command results, and the JSON emitted under `--json`.
Every error and warning goes to stderr, including the ones that reject an
argument before the command runs. Parse stdout without filtering it; read stderr
for diagnostics. Progress and success lines (`INFO`, `OK`) are on stdout and are
the only non-data text there — commands with `--json` do not emit them.

Under `--json`, a failure that prevents the command from producing any data at
all — no project resolved — produces exactly one machine-readable line on
stderr and nothing on stdout: `modules --json`, `status --json` and
`doctor --json` each emit exactly one JSON line on stderr in that case. That is
not the general rule, though: `test --json` with failing tests writes the full
JSON envelope to stdout as usual, and may also write a human diagnostic to
stderr alongside it (see the exit code contract below). Read stdout for the
JSON payload and stderr for diagnostics; do not assume the two are mutually
exclusive.

## Exit code contract

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Project or runtime error — no project found, model absent from the ORM, module already exists, enterprise version not imported |
| 2 | Usage error — bad argument, unknown module, `all` mixed with names, conflicting flags |
| 3 | Environment error — port busy, DB unavailable, Docker unavailable, stack down, `mcp` extra missing or incompatible |

`shell -c`, `sql` and `py` are transparent pass-throughs by design (same idea
as `docker exec`, documented in the README): whatever the underlying process
or query returns comes back as-is, raw process code included. Every other
command is an odev operation and honours this table instead of forwarding a
raw process code.

`test`, `addon-install` and `update` all run an Odoo process inside the
container and honour this table like every other odev operation: any failure
is 1. Odoo's own process return code is not forwarded as the exit code — it is
preserved elsewhere instead. `addon-install` and `update` have no `--json`, so
it only survives in the stderr message. `test` has `--json`, so it also
survives as `process_exit_code` in the JSON payload (see `testing.md`) on
every run, successful or not. A run that exits 0 but whose captured log
contains a traceback or a CRITICAL line is also 1 (same philosophy as `test`'s
`returncode_hint`).

`model-info` on a nonexistent model is 1, not 2: it took a live ORM query to
find out, so it's a runtime fact, not a usage mistake made upfront.

## Rejected flag combinations

| Command | Combination | Exit |
|---|---|---|
| `test` | `--verbose` with any of `--json`/`--summary`/`--failures` | 2 |
| `test` | `module:Class.method` shorthand with `--tags` | 2 |
| `test` | CSV module list with the `:Class.method` shorthand (e.g. `m1,m2:Foo`) | 2 |
| `test` | `all:Class` (shorthand on the `all` pseudo-module) | 2 |
| `test`, `update`, `addon-install` | `all` combined with named modules (e.g. `sale,all`) | 2 |
| `sql` | `--json` with `--csv` | 2 |
| `logs` | `--json` with `--follow` | 2 |

## Destructive commands

All five carry the same four guards: a warning naming what is destroyed,
an interactive confirmation, `-y/--yes` to skip it non-interactively, and
`--dry-run` to preview without acting. A non-interactive confirmation with no
`--yes` fails closed (`typer.confirm` raises `Abort` on non-interactive
stdin) — it never hangs waiting for input.

| Command | Destroys |
|---|---|
| `odev down -v` / `--volumes` | DB + filestore volumes. Plain `odev down` (no `-v`) is non-destructive: it only stops and removes containers, no prompt. |
| `odev reset-db` | DB + volumes, then reinitializes |
| `odev load-backup <zip>` | Overwrites DB + filestore |
| `odev db restore <name>` | Drops and recreates the DB |
| `odev db anonymize` | Partner PII + all user passwords, reset to `admin` |

## Commands

| Command | Args | Key options |
|---|---|---|
| `init [name]` | project name, or `.` for cwd | `--odoo-version/-v`, `--no-interactive` |
| `adopt [dir]` | existing Odoo repo dir (default `.`) | `--name/-n`, `--odoo-version`, `--no-interactive`, `--force/-f` |
| `migrate` | — | detects legacy layout, converts to `.odev.yaml` |
| `reconfigure` | — | `--include-env` (also regenerate `.env`), `--dry-run` |
| `up` | — | `--build`, `--watch` |
| `down` | — | `-v/--volumes` (destructive), `-y/--yes`, `--dry-run` |
| `restart [service]` | default `web` | — |
| `status` | — | `-j/--json` |
| `doctor` | — | `--json` |
| `logs <service>` | — | `--tail`, `--no-follow`, `--follow` (mutually exclusive with `--json`), `--json` |
| `shell [service]` | default `web` | `-c/--cmd <command>` (non-interactive; omit for interactive terminal) |
| `sql <query>` | raw SQL | `--csv`, `--json` (mutually exclusive) |
| `py <expression>` | one Python expression | `--commit` (persist ORM writes), `--keep-banner` |
| `modules` | — | `-j/--json` (default: human-readable table) |
| `model-info <model>` | technical model name | `--pretty` |
| `test <module>` | CSV or `all`, or `module:Class.method` | `--tags`, `--json`, `--save-log <path>`, `--verbose/-v`, `--summary/-s`, `--failures/-f`, `--no-validate` |
| `addon-install <module>` | CSV or `all` | `--no-validate`, `--verbose/-v` |
| `update <module>` | CSV or `all` | `--no-validate`, `--verbose/-v` |
| `scaffold <name>` | snake_case module name | — |
| `context` | — | `--json`, `--quiet/-q` |
| `reset-db` | — | `--neutralize/--no-neutralize` (default on), `-y/--yes`, `--dry-run` |
| `load-backup <zip>` | — | `--neutralize/--no-neutralize`, `-y/--yes`, `--dry-run` |
| `self-update` | — | `pip install --upgrade` against odev's own repo |
| `tui` | — | interactive Textual dashboard; exit code 42 from the TUI opens a shell |
| `db snapshot <name>` | — | `pg_dump --format=custom` to `snapshots/` |
| `db restore <name>` | exact name or prefix | `-y/--yes`, `--dry-run` (destructive) |
| `db list` | — | table of available snapshots |
| `db anonymize` | — | `-y/--yes`, `--dry-run` (destructive) |
| `projects` / `projects list` | — | `-j/--json` |
| `projects remove <name>` | — | `--delete-config`, `--force/-f` |
| `projects clean` | — | prunes stale registry entries |
| `enterprise import <version> <path>` | — | `--copy` (default: symlink), `--force/-f` |
| `enterprise path <version>` | — | prints raw path, exit 1 if not imported |
| `enterprise status` | — | table of imported versions + linked projects |
| `enterprise link` | — | `--version` (default: project's own) |
| `mcp serve` | — | `--transport/-t` (`stdio` default, `http`), `--port/-p` (http only) |

`adopt`, `reconfigure`, `projects`, `enterprise` register inside a
try/except `ImportError`: if the import fails, the subcommand is simply
absent (`odev adopt` reports "unknown command"). `odev doctor` reports any
subcommand that failed to load instead of leaving the degradation invisible.

CLI-only, no MCP equivalent: lifecycle (`up`, `down`, `restart`), `init`,
`adopt`, `migrate`, `reconfigure`, `scaffold`, `reset-db`, `load-backup`,
`tui`, `self-update`, the `projects` and `enterprise` subgroups, `test
--save-log`, `sql --csv`, streaming `logs --follow`, and interactive `shell`
(no `-c`). The `context` command's data is also reachable read-only through
the `odev://project/context` MCP resource, but the CLI command's own
`--json`/`--quiet` flags are CLI-only.

## Project resolution

Order (`src/odev/core/resolver.py`), first match wins:

1. Explicit name — `--project/-p` flag, else `ODEV_PROJECT` env var (flag
   wins) → looked up in the global registry. Not found → error.
2. **Inline walk** — walks up from cwd looking for a config file. Accepts
   both `.odev.yaml` and `odev.yaml` at each directory level; if both exist
   in the same directory, `.odev.yaml` wins.
3. **Registry lookup** by cwd containment. Multiple matches raise
   `ProyectoAmbiguoError` telling you to pass `--project`.
4. **Legacy detection** — `docker-compose.yml` + a `cli/` directory, no yaml
   at all. Fix with `odev migrate`.
5. Otherwise: not found.

Global state lives under `~/.odev/`: `registry.yaml` (project registry,
flock-guarded across processes), `projects/<name>/` (external-mode configs),
`enterprise/<version>/` (shared enterprise addons, symlinked into projects by
default).

Inline mode (`odev init`): the project's `.odev.yaml`/`odev.yaml` lives
inside the project directory itself, discovered by the upward walk; its
registry entry is best-effort and not required for resolution. External
mode (`odev adopt`): config lives under `~/.odev/projects/<name>/` instead
of in the project tree, so the project is found only via registry lookup by
cwd containment.

`ODEV_PROJECT` lets an agent target a project without `cd`-ing — every CLI
command and the MCP server honor it identically.
