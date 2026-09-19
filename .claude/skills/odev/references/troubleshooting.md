# Troubleshooting

Format: symptom, cause, check, fix.

## Stack not running

**Symptom.** ORM/DB commands (`py`, `sql`, `model-info`, and the `db`
subgroup) fail instead of doing anything useful. Over the CLI this is exit
3, with the message on stderr. Over MCP, `odev_py` and `odev_status` (and
any other tool hitting a `docker compose exec` failure) surface as an
operational error reading `Stack not running or DB unavailable`, not a
crash — `subprocess.CalledProcessError` is one of the translated exception
types.

**Check.** `odev status` or `odev_status` — service list, look for `web`/
`db` not `Up`.

**Fix.** `odev up`.

## Database not yet created after `up`

**Symptom.** Right after `odev up` returns, `report.url` is missing and no
MailHog server is configured: PDF reports render without CSS, and outgoing
mail doesn't route to MailHog.

**Cause.** `docker compose up` returns as soon as containers start, but
Odoo creates the database schema seconds (or minutes, if the entrypoint is
still installing addon requirements) later. `up` waits for the database to
exist before deciding whether to write `report.url`/mail-server config; if
that wait times out, it warns instead of silently leaving the project
misconfigured.

**Check.** The warning `up` prints when the wait times out; `odev doctor`'s
`odoo-conf`/`env` checks.

**Fix.** Re-run `odev up` once Odoo has finished creating the database — it
re-applies the missing configuration and restarts `web` if anything
changed.

## Module not on the addons path

**Symptom.** `addon-install`, `update`, or `test` exits 2 with "Modulos no
encontrados: `<name>`", even though the module directory exists on disk.

**Cause.** Module existence is validated against `paths.addons` from the
project's yaml config when present (source of truth: it's what generates
the container mounts); it falls back to layout heuristics only when that
config is absent or empty. A module living outside every configured addons
path, or under a layout the heuristics don't recognize, is rejected even
though the running container might actually see it.

**Check.** Compare the module's real path against `paths.addons` in
`.odev.yaml`/`odev.yaml`, or `odev context --json` for the resolved addons
paths.

**Fix.** Add the correct path to `paths.addons`, or pass `--no-validate` to
bypass the check for a module you've confirmed is genuinely reachable
inside the container.

## Port conflicts

**Symptom.** `odev up` refuses to start (exit 3), naming a port and, when
known, the project that owns it.

**Check/diagnosis.** Both `odev up`'s preflight and `odev doctor`'s ports
check use the same classification (`classify_bound_port`, via
`verificar_puertos_pre_up`): a bound port is `free`, `own_running` (this
project's own container — never a failure), `foreign_known` (another
registered project — hint: `odev --project <name> down`), or
`foreign_unknown` (hint: `lsof -i :<port>` to identify the process). The
practical difference is *when* each runs: `up`'s preflight blocks startup
before touching docker compose; `doctor`'s check only reports status
on-demand, non-blocking, for a stack that may or may not currently be up.

**Fix.** Free the port (stop the owning project or process), or reassign
the port in `.env` and `reconfigure`.

## Filestore permission errors

**Symptom.** `ir_attachment._file_write` raises `PermissionError`, or
`/web/assets/*` returns 500 and the UI is blank.

**Cause.** The long-lived Odoo server inside the `web` container runs as
the unprivileged `odoo` user, not root. Any command that writes into the
filestore must run as that same user to avoid leaving root-owned files
behind. `addon-install`, `update`, `test`, `py`, and `model-info` already
run as `odoo`; `shell` and `tui` intentionally still enter as root (useful
for debugging), so a manual write performed from an interactive `shell`
session can leave root-owned filestore entries that the server can no
longer write to.

**Check.** File ownership under the project's filestore directory.

**Fix.** Avoid writing into the filestore from a root `shell` session;
prefer `odev py`/`odev_py` or `addon-install`/`update` for anything that
touches ORM attachments.

## Root-owned files you cannot delete

**Symptom.** `rm -rf <project>` fails with permission denied on `.pyc` files
under `addons/*/__pycache__`, even though the project directory belongs to you.

**Cause.** The Odoo process runs as root until the entrypoint's `setpriv` drop,
so any bytecode it wrote onto the bind-mounted `addons/` directory landed as
`root:root`. Projects created from odev 0.13.0 on set
`PYTHONDONTWRITEBYTECODE=1` on the `web` service and never write it; `odev up`
regenerates the compose file, so an existing project picks it up on its next
start without being recreated.

**Check.** `ls -l addons/*/__pycache__`.

**Fix.** Delete the leftovers with container privileges rather than `sudo`:
`docker run --rm -v "$PWD:/w" alpine sh -c 'find /w -name __pycache__ -prune -exec rm -rf {} +'`.

## PDF reports without styles

**Symptom.** QWeb PDF reports render with no CSS — layout looks broken,
but the HTML preview in the browser looks fine.

**Cause.** `wkhtmltopdf` fetches the report's CSS bundle over HTTP using
`report.url`, a system parameter pointing at the container's *internal*
port. If that parameter is missing or stale (see "Database not yet created
after `up`" above), the bundle fetch fails silently and the PDF renders
unstyled.

**Check.** `odev_sql` / `odev sql` — `SELECT value FROM ir_config_parameter
WHERE key = 'report.url'`.

**Fix.** Re-run `odev up` (it reasserts `report.url`), or `odev restart
web` after fixing the parameter by hand.

## MCP extra missing or on the wrong major

**Symptom.** `odev mcp serve` exits 3 immediately.

**Cause, distinguished by message.** odev probes `import mcp` first, then
`from mcp.server import MCPServer`, so the two failures get different
messages: `mcp` genuinely absent, or `mcp` installed but pre-2.x (SDK 1.x
exposed the server as `FastMCP` under `mcp.server.fastmcp`; odev needs the
2.x `MCPServer` under `mcp.server`).

**Check.** The exact stderr text — it already names which of the two
failed and what to do.

**Fix.** `pipx install --force 'odev[mcp]'`, or `pip install 'mcp>=2,<3'`.

## A test run reports zero tests

**Symptom.** `odev test <module>` exits 0, `failed: 0, errors: 0` — all
green — but nothing actually ran.

**Cause / check / fix.** See `testing.md`, "The zero-test warning and the
discovery lint". Read stderr for the warning naming the effective filter,
and check `total` in the JSON — never trust the exit code alone. The most
common cause is a `test_*.py` file that exists but isn't imported by its
package's `tests/__init__.py`; odev's own discovery lint flags this before
the run even starts.

## Writes that vanish

**Symptom.** `odev py`/`odev_py` runs an expression that calls
`.create(`/`.write(`/`.unlink(`/`.copy(`, returns a result that looks
correct, but the record is gone on the next query.

**Cause.** `odoo shell` rolls back the transaction on close unless
committed explicitly. Without `--commit`/`commit=True`, every write is
discarded no matter what the expression returned.

**Check.** The stderr warning odev emits before running an expression that
looks like a write and wasn't passed `--commit`/`commit=True` (a static
text heuristic — it has false negatives for a write hidden inside a
business-method call, so absence of the warning is not proof of safety).
Query the record again in a fresh `py`/`sql` call to confirm persistence.

**Fix.** Pass `--commit` (CLI) or `commit=True` (MCP) when the write is
intended to persist.

## Ambiguous or unresolvable project

**Symptom.** A command exits 1 with either "no project found" or "multiple
projects match `<cwd>`, use `--project <name>`".

**Cause.** No `.odev.yaml`/`odev.yaml` in the upward walk, no legacy layout,
and either zero or more than one registry entry contains the current
directory. See `commands.md` for the full resolution order.

**Check.** `odev projects list` (or `-j/--json`) to see every registered
project and its working directory.

**Fix.** Pass `--project <name>` explicitly, or set `ODEV_PROJECT`.

## What `odev doctor` checks

| Check | A failure means |
|---|---|
| `docker` | Docker CLI/daemon unreachable |
| `docker-compose` | `docker compose` plugin unavailable |
| `python` | Python interpreter/version issue |
| `proyecto` | No project resolved for the current context |
| `env` | Project's `.env` file missing |
| `compose-file` | `docker-compose.yml` missing or invalid for the project |
| `odoo-conf` | `config/odoo.conf` missing or out of sync with `.env` |
| `addons` | No addon modules found on any configured addons path |
| `puertos` | A configured port is held by another project or an unknown foreign process (see "Port conflicts" above; the project's own running containers never fail this check) |
| `registry-gc` | Stale registry entries need pruning |
| `version` | Installed odev version differs from what the project expects |
| `subcomandos` | An optional subcommand (`adopt`, `reconfigure`, `projects`, or `enterprise`) failed to import and is unavailable |

`odev doctor --json`/`odev_doctor` returns `{version, checks: [...], summary,
exit_code}`; the CLI's own process exit code is 1 if any check's status is
`fail`, 0 otherwise.
