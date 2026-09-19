"""odev mcp serve — expose odev as an MCP server.

Provides an MCPServer (mcp SDK 2.x) with 9 tools, 4 resources, and 3
prompts that wrap the odev _execute_* helper layer. All imports of the
optional `mcp` package are lazy (inside function bodies) so this module is
safely importable even when `mcp` is not installed.

Install the optional extra: pipx install --force 'odev[mcp]'
"""

from __future__ import annotations

import functools
import logging
import subprocess
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

import typer

from odev.commands._helpers import EPILOG_EXIT_CODES

mcp_app = typer.Typer(
    name="mcp",
    help="MCP server commands (requires `mcp` extra).",
    epilog=EPILOG_EXIT_CODES,
)


# ---------------------------------------------------------------------------
# Lazy import guard
# ---------------------------------------------------------------------------


def _mcp_version() -> str:
    """Installed `mcp` version, or "unknown" when metadata is unavailable."""
    try:
        return _pkg_version("mcp")
    except PackageNotFoundError:
        return "unknown"


def _import_mcpserver():
    """Lazy import of the MCPServer API (mcp SDK 2.x). Returns class or exits 3.

    The two failure modes need different fixes, so they get different
    messages. Reporting a version mismatch as "not installed" sends the
    operator to reinstall a package that is already there.

    D4: both failure modes are environment problems -- a missing or
    incompatible dependency, not a usage or project error -- so they exit
    3, matching EPILOG_EXIT_CODES.
    """
    try:
        import mcp  # noqa: F401, PLC0415
    except ImportError:
        sys.stderr.write(
            "ERROR: 'mcp' package not installed.\n"
            "Install with: pipx install --force 'odev[mcp]'\n"
            "Or: pip install 'mcp>=2,<3'\n"
        )
        raise typer.Exit(3) from None

    try:
        from mcp.server import MCPServer  # noqa: PLC0415
    except ImportError:
        sys.stderr.write(
            f"ERROR: 'mcp' {_mcp_version()} is installed but too old: "
            "'MCPServer' is missing from 'mcp.server'.\n"
            "odev needs the SDK 2.x API; 1.x exposed this server as FastMCP "
            "in 'mcp.server.fastmcp'.\n"
            "Reinstall the pinned extra: pipx install --force 'odev[mcp]'\n"
            "Or: pip install 'mcp>=2,<3'\n"
        )
        raise typer.Exit(3) from None

    return MCPServer


# ---------------------------------------------------------------------------
# Typer command
# ---------------------------------------------------------------------------


@mcp_app.command("serve", epilog=EPILOG_EXIT_CODES)
def serve(
    transport: str = typer.Option(
        "stdio",
        "--transport",
        "-t",
        help="Transport protocol: stdio (default) | http",
    ),
    port: int = typer.Option(
        3333,
        "--port",
        "-p",
        help="Port for http transport (ignored for stdio).",
    ),
) -> None:
    """Start MCP server (blocks until transport closes).

    Exposes odev operations as MCP tools, resources, and prompts.
    The `mcp` optional extra must be installed: pipx install 'odev[mcp]'
    """
    MCPServer = _import_mcpserver()
    _configure_stderr_logging()  # critical: no stdout pollution on stdio transport
    server = _build_server(MCPServer)
    try:
        if transport == "stdio":
            server.run()  # default stdio, blocks
        elif transport == "http":
            server.run(transport="streamable-http", port=port)
        else:
            sys.stderr.write(f"ERROR: unknown transport '{transport}'. Valid: stdio, http\n")
            raise typer.Exit(2)
    except KeyboardInterrupt:
        return  # clean SIGINT, exit 0


# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------


def _configure_stderr_logging() -> None:
    """Redirect Python logging to stderr.

    stdio transport uses stdout for JSON-RPC messages — any stray log line
    written to stdout corrupts the stream. This removes all stdout handlers
    and adds a single stderr handler before the server starts.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)


# ---------------------------------------------------------------------------
# Server builder
# ---------------------------------------------------------------------------


def _build_server(MCPServer):
    """Construct and configure the MCPServer instance.

    `version` is odev's, not the SDK's: it defaults to "" in SDK 2.x, so the
    handshake would otherwise advertise an empty server version.
    """
    from odev import __version__  # noqa: PLC0415

    server = MCPServer("odev", version=__version__)
    _register_tools(server)
    _register_resources(server)
    _register_prompts(server)
    return server


# ---------------------------------------------------------------------------
# Error translation
# ---------------------------------------------------------------------------

# How the _execute_* layer signals an operational failure: bad input
# (ValueError), an unusable environment (RuntimeError), or a docker/subprocess
# command that failed (CalledProcessError) -- e.g. the stack is not running.
# Anything else that escapes is a bug in odev, and the SDK is right to treat
# it as a crash.
FALLOS_OPERATIVOS = (ValueError, RuntimeError, subprocess.CalledProcessError)


def _anticipado(error_cls):
    """Re-raise operational failures as `error_cls` so the client sees them.

    The SDK forwards the message of an *anticipated* failure (ToolError,
    ResourceError) and withholds every other one: the model gets a bare
    "Error executing tool <name>" and the detail stays in the server log.
    Without this translation the whole _execute_* diagnostic surface — the
    offending SQL error line, "Stack not running or DB unavailable", docker's
    own messages — would be invisible to the caller.

    A crash still reaches the SDK untranslated, which is what we want: a bug
    in odev belongs in the log with its traceback, not in the model's context
    dressed up as an operational error.
    """

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except subprocess.CalledProcessError as exc:
                # A3: the raw str() of a CalledProcessError is a command line
                # and a return code -- it tells nobody anything. The most
                # common cause, by far, is that the stack is not running; the
                # same message _execute_model_info already uses for the same
                # case keeps the wording consistent across the tool surface.
                raise error_cls("Stack not running or DB unavailable") from exc
            except FALLOS_OPERATIVOS as exc:
                raise error_cls(str(exc)) from exc

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Context resolution (MCP-safe — raises ValueError, not typer.Exit)
# ---------------------------------------------------------------------------


def _resolve_contexto():
    """Obtiene el contexto del proyecto; lanza ValueError si no se resuelve.

    Delega la resolucion del nombre a `obtener_nombre_proyecto`, que respeta
    en orden: (1) flag --project, (2) variable de entorno ODEV_PROJECT.
    Si ambos faltan, `resolver_proyecto` aplica estrategias cwd-walk.

    MCP-safe: no lanza typer.Exit; solo ValueError, que `_anticipado`
    traduce a ToolError/ResourceError para que el mensaje llegue al cliente.
    """
    from odev.core.resolver import (  # noqa: PLC0415
        ProyectoAmbiguoError,
        ProyectoNoEncontradoError,
        resolver_proyecto,
    )
    from odev.main import obtener_nombre_proyecto  # noqa: PLC0415

    try:
        return resolver_proyecto(nombre_proyecto=obtener_nombre_proyecto())
    except (ProyectoNoEncontradoError, ProyectoAmbiguoError) as exc:
        raise ValueError(f"No odev project found: {exc}") from exc


# ---------------------------------------------------------------------------
# Tools (9)
# ---------------------------------------------------------------------------


def _register_tools(server) -> None:
    """Register 9 MCP tools wrapping the _execute_* helper layer."""
    from mcp.server.mcpserver.exceptions import ToolError  # noqa: PLC0415

    from odev.commands.doctor import _execute_doctor  # noqa: PLC0415
    from odev.commands.logs import _execute_logs  # noqa: PLC0415
    from odev.commands.model_info import _execute_model_info  # noqa: PLC0415
    from odev.commands.modules import _execute_modules  # noqa: PLC0415
    from odev.commands.py import (  # noqa: PLC0415
        _execute_py,
        _expresion_parece_escribir,
    )
    from odev.commands.shell import _execute_shell  # noqa: PLC0415
    from odev.commands.sql import _execute_sql  # noqa: PLC0415
    from odev.commands.status import _execute_status  # noqa: PLC0415
    from odev.commands.test import _execute_test  # noqa: PLC0415

    @server.tool()
    @_anticipado(ToolError)
    def odev_status() -> list[dict]:
        """Get docker-compose service status."""
        return _execute_status(_resolve_contexto())

    @server.tool()
    @_anticipado(ToolError)
    def odev_shell(service: str, command: str) -> dict:
        """Run a shell command inside a service container."""
        return _execute_shell(_resolve_contexto(), service, command)

    @server.tool()
    @_anticipado(ToolError)
    def odev_sql(query: str) -> list[dict]:
        """Execute SELECT against the Odoo DB; returns rows as dicts."""
        return _execute_sql(_resolve_contexto(), query)

    @server.tool()
    @_anticipado(ToolError)
    def odev_py(expression: str, commit: bool = False) -> dict:
        """Evaluate Python expression in odoo shell (banner-stripped).

        odoo shell rolls back on close: ORM writes (.create/.write/.unlink/
        .copy) are discarded unless commit=True. Returns a dict with three
        keys:

          result: the banner-stripped output of the expression (same value
            this tool returned before, now nested under a key).
          committed: True if commit=True was passed (the transaction was
            committed after evaluating the expression), False otherwise.
          warning: text warning when the expression looks like it writes
            and commit=False -- odoo shell will discard those changes on
            close -- otherwise null. This is a best-effort, static text
            heuristic over the expression (.create(/.write(/.unlink(/
            .copy(), not a guarantee: a write hidden inside a business
            method call is not detected.
        """
        result = _execute_py(_resolve_contexto(), expression, commit=commit)
        warning = None
        if not commit and _expresion_parece_escribir(expression):
            warning = (
                "La expresion parece escribir (.create/.write/.unlink/.copy) "
                "y no se paso commit=True. odoo shell hace rollback al "
                "cerrar: los cambios se van a descartar."
            )
        return {"result": result, "committed": commit, "warning": warning}

    @server.tool()
    @_anticipado(ToolError)
    def odev_test(module: str, tags: str | None = None) -> dict:
        """Run Odoo tests for one or more modules (CSV)."""
        return _execute_test(_resolve_contexto(), module, tags=tags)

    @server.tool()
    @_anticipado(ToolError)
    def odev_logs(service: str, tail: int = 200) -> list[dict]:
        """Read recent service logs (parsed)."""
        return _execute_logs(_resolve_contexto(), service, tail)

    @server.tool()
    @_anticipado(ToolError)
    def odev_doctor() -> dict:
        """Run environment diagnostics; returns CheckResult dict."""
        return _execute_doctor(_resolve_contexto())

    @server.tool()
    @_anticipado(ToolError)
    def odev_model_info(model: str) -> dict:
        """Inspect an Odoo model's fields, inheritance, and methods."""
        return _execute_model_info(_resolve_contexto(), model)

    @server.tool()
    @_anticipado(ToolError)
    def odev_modules() -> list[dict]:
        """List installed Odoo modules with state and version."""
        return _execute_modules(_resolve_contexto())


# ---------------------------------------------------------------------------
# Resources (4)
# ---------------------------------------------------------------------------


def _register_resources(server) -> None:
    """Register 4 MCP resources."""
    from mcp.server.mcpserver.exceptions import (  # noqa: PLC0415
        ResourceError,
        ResourceNotFoundError,
    )

    @server.resource("odev://project/context")
    @_anticipado(ResourceError)
    def project_context() -> str:
        """Current project context as markdown (equivalent to odev context)."""
        from odev.commands.context import _execute_context  # noqa: PLC0415

        return _execute_context(_resolve_contexto())

    @server.resource("odev://project/config")
    @_anticipado(ResourceError)
    def project_config() -> str:
        """Parsed .odev.yaml contents as JSON."""
        import json  # noqa: PLC0415

        from odev.core.project import ProjectConfig  # noqa: PLC0415

        contexto = _resolve_contexto()
        cfg = ProjectConfig(contexto.directorio_config)
        return json.dumps(cfg.to_dict(), indent=2, ensure_ascii=False)

    @server.resource("odev://db/schema")
    @_anticipado(ResourceError)
    def db_schema() -> str:
        """pg_dump --schema-only of the project database."""
        return _execute_db_schema(_resolve_contexto())

    @server.resource("odev://modules/{name}/manifest")
    @_anticipado(ResourceError)
    def module_manifest(name: str) -> str:
        """Parsed __manifest__.py of a module as JSON."""
        import json  # noqa: PLC0415

        from odev.commands.context import _parsear_manifiesto  # noqa: PLC0415

        contexto = _resolve_contexto()
        path = _find_manifest(contexto, name)
        if path is None:
            raise ResourceNotFoundError(f"Module '{name}' not found in addons paths.")
        return json.dumps(_parsear_manifiesto(path), indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Resource helpers
# ---------------------------------------------------------------------------


def _execute_db_schema(contexto) -> str:
    """Run pg_dump --schema-only and return the DDL as a string.

    Args:
        contexto: Resolved ProjectContext.

    Returns:
        UTF-8 decoded pg_dump output.

    Raises:
        RuntimeError: If pg_dump exits non-zero.
    """
    from odev.commands._helpers import obtener_docker  # noqa: PLC0415
    from odev.core.config import load_env  # noqa: PLC0415
    from odev.core.paths import ProjectPaths  # noqa: PLC0415

    rutas = ProjectPaths(contexto)
    valores_env = load_env(rutas.env_file)
    db_name = valores_env.get("DB_NAME", "odoo_db")
    db_user = valores_env.get("DB_USER", "odoo")

    dc = obtener_docker(contexto)
    stdout_bytes, _stderr_bytes, rc = dc.exec_capture(
        "db", ["pg_dump", "-U", db_user, "--schema-only", db_name]
    )
    if rc != 0:
        raise RuntimeError(f"pg_dump failed (rc={rc})")
    return stdout_bytes.decode("utf-8", errors="replace")


def _find_manifest(contexto, module_name: str):
    """Walk addons paths and return Path to __manifest__.py or None.

    Args:
        contexto: Resolved ProjectContext.
        module_name: Technical name of the Odoo module.

    Returns:
        Path to __manifest__.py, or None if not found.
    """
    from pathlib import Path  # noqa: PLC0415

    from odev.core.paths import ProjectPaths  # noqa: PLC0415

    rutas = ProjectPaths(contexto)
    for base in rutas.addons_dirs:
        candidate = Path(base) / module_name / "__manifest__.py"
        if candidate.exists():
            return candidate
    return None


# ---------------------------------------------------------------------------
# Prompts (3)
# ---------------------------------------------------------------------------


def _register_prompts(server) -> None:
    """Register 3 MCP prompt templates."""

    @server.prompt()
    def diagnose_failing_test(test_name: str) -> str:
        """Analyze a failing Odoo test and propose a fix."""
        return (
            f"Analyze the following failing Odoo test: {test_name}\n\n"
            "Steps:\n"
            "1. Read odev://project/context for project info.\n"
            "2. Call odev_test with the failing module and inspect the result.\n"
            "3. Identify root cause: fixture data, model state, missing dependency, or "
            "assertion error.\n"
            "4. Propose a fix and the smallest test that reproduces it."
        )

    @server.prompt()
    def explain_module(module_name: str) -> str:
        """Explain an Odoo module's purpose, dependencies, and structure."""
        return (
            f"Explain the Odoo module '{module_name}'.\n\n"
            "Steps:\n"
            f"1. Fetch odev://modules/{module_name}/manifest to read declared metadata.\n"
            "2. Summarise: purpose, declared dependencies, data files, key models, views.\n"
            "3. Flag any unusual hooks (post-init, uninstall) or external deps."
        )

    @server.prompt()
    def generate_migration(model: str, description: str) -> str:
        """Generate an Odoo ORM migration scaffold."""
        return (
            f"Generate an Odoo migration for model '{model}' that '{description}'.\n\n"
            "Deliver:\n"
            "1. The SQL ALTER (if schema change) or none.\n"
            "2. The migration file path (e.g. `migrations/<version>/post-migrate.py`).\n"
            "3. The Python `_post_init` / `post-migrate` hook for data backfill if needed.\n"
            "4. A rollback note."
        )
