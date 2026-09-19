# odev MCP server

`odev mcp serve` exposes an `MCPServer` (mcp SDK 2.x) over `stdio` (default)
or `http` (`--transport/-t`, `--port/-p`). Requires the `mcp` optional
extra: `pipx install --force 'odev[mcp]'` or `pip install 'mcp>=2,<3'`.

All 9 tools resolve project context exactly like the CLI: `--project`, then
`ODEV_PROJECT`, then the same upward-walk/registry/legacy resolution.

## Tools (9)

| Tool | Signature | Returns |
|---|---|---|
| `odev_status` | `()` | `list[dict]` — docker-compose service status |
| `odev_shell` | `(service: str, command: str)` | `dict` — `{stdout, stderr, returncode}` |
| `odev_sql` | `(query: str)` | `list[dict]` — rows; **all values are strings** (psql text protocol) |
| `odev_py` | `(expression: str, commit: bool = False)` | `dict` — `{result, committed, warning}` |
| `odev_test` | `(module: str, tags: str \| None = None)` | `dict` — TestResult shape, `failures[]` included |
| `odev_logs` | `(service: str, tail: int = 200)` | `list[dict]` — parsed log entries, snapshot only, never follows |
| `odev_doctor` | `()` | `dict` — `{version, checks: [...], summary, exit_code}` |
| `odev_model_info` | `(model: str)` | `dict` — `{model, description, inherits, fields}` |
| `odev_modules` | `()` | `list[dict]` — `{name, state, version}` |

`odev_py`'s `result` key holds the same banner-stripped string the tool
always returned; `committed` is `True` only when `commit=True` was passed;
`warning` is a string when the expression looks like a write
(`.create(`/`.write(`/`.unlink(`/`.copy(` present in the expression text)
and `commit` was not passed, otherwise `null`. This is a static text
heuristic, not a guarantee — a write hidden inside a business-method call is
not detected, and `commit=True` suppresses the warning unconditionally.

`odev_test` has no `--save-log`, `--no-validate`, or the CSV/shorthand exit-2
guards surfaced as typed errors — invalid combinations raise `ValueError`
and arrive as an operational error with the full message (see below), same
text as the CLI would print to stderr.

## Resources (4)

| URI | Content |
|---|---|
| `odev://project/context` | Markdown: layout, Odoo version, modules (same as `odev context`) |
| `odev://project/config` | Parsed `.odev.yaml`/`odev.yaml` as JSON |
| `odev://db/schema` | `pg_dump --schema-only` output |
| `odev://modules/{name}/manifest` | Parsed `__manifest__.py` as JSON; raises `ResourceNotFoundError` for an unknown module |

Discover with `ListMcpResourcesTool`, fetch with `ReadMcpResourceTool`.

## Prompts (3)

`diagnose_failing_test(test_name)`, `explain_module(module_name)`,
`generate_migration(model, description)` — each returns a text prompt
template; none executes anything itself.

## Error translation layer

MCP tools have no exit codes. A tool wrapper catches three operational
exception types raised by the underlying `_execute_*` layer —
`ValueError` (bad input), `RuntimeError` (unusable environment), and
`subprocess.CalledProcessError` (a docker/subprocess command that failed,
most commonly because the stack is down) — and re-raises them as
`ToolError`/`ResourceError` with the original message intact. A
`CalledProcessError` is translated to the fixed message "Stack not running
or DB unavailable" rather than its raw `str()`, which is just a command line
and a return code.

Any other exception type escaping `_execute_*` is a bug in odev, not an
operational failure: the SDK withholds its message from the client, the
caller sees a bare `Error executing tool <name>`, and the real detail stays
in the server log (stderr under stdio transport — logging is redirected
there so it never corrupts the JSON-RPC stream on stdout).

`_resolve_contexto()` never raises `typer.Exit`; an unresolved project
becomes a `ValueError` translated the same way as any other operational
failure, carrying the same message the CLI would print.

## MCP vs CLI

Prefer MCP when both work: it returns parsed structures instead of text to
scrape, and every tool's error path carries an actionable message instead of
a raw exit code. Use the CLI when the task needs a CLI-only command or flag
(see `commands.md`) — lifecycle commands, interactive shell, streaming logs,
`test --save-log`, `sql --csv`, or any of the `projects`/`enterprise`
subgroups — or when a human needs to watch a live, colored, interactive
stream (`--verbose`, `tui`).
