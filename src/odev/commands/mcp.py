"""odev mcp serve — expose odev as an MCP server.

Provides a FastMCP server with 9 tools, 4 resources, and 3 prompts
that wrap the odev _execute_* helper layer. All imports of the optional
`mcp` package are lazy (inside function bodies) so this module is safely
importable even when `mcp` is not installed.

Install the optional extra: pipx install --force 'odev[mcp]'
"""

from __future__ import annotations

import logging
import sys

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


def _import_fastmcp():
    """Lazy import. Returns FastMCP class or aborts with exit 2 + install hint."""
    try:
        from mcp.server.fastmcp import FastMCP  # noqa: PLC0415

        return FastMCP
    except ImportError:
        sys.stderr.write(
            "ERROR: 'mcp' package not installed.\n"
            "Install with: pipx install --force 'odev[mcp]'\n"
            "Or: pip install 'mcp>=1.0.0'\n"
        )
        raise typer.Exit(2)


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
    FastMCP = _import_fastmcp()
    _configure_stderr_logging()  # critical: no stdout pollution on stdio transport
    server = _build_server(FastMCP)
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


def _build_server(FastMCP):
    """Construct and configure the FastMCP server instance."""
    mcp = FastMCP("odev")
    _register_tools(mcp)
    _register_resources(mcp)
    _register_prompts(mcp)
    return mcp


# ---------------------------------------------------------------------------
# Context resolution (MCP-safe — raises ValueError, not typer.Exit)
# ---------------------------------------------------------------------------


def _resolve_contexto():
    """Obtiene el contexto del proyecto; lanza ValueError si no se resuelve.

    Delega la resolucion del nombre a `obtener_nombre_proyecto`, que respeta
    en orden: (1) flag --project, (2) variable de entorno ODEV_PROJECT.
    Si ambos faltan, `resolver_proyecto` aplica estrategias cwd-walk.

    MCP-safe: no lanza typer.Exit; solo ValueError para que el framework MCP
    devuelva un error estructurado al cliente.
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


def _register_tools(mcp) -> None:
    """Register 9 MCP tools wrapping the _execute_* helper layer."""
    from odev.commands.doctor import _execute_doctor  # noqa: PLC0415
    from odev.commands.logs import _execute_logs  # noqa: PLC0415
    from odev.commands.model_info import _execute_model_info  # noqa: PLC0415
    from odev.commands.modules import _execute_modules  # noqa: PLC0415
    from odev.commands.py import _execute_py  # noqa: PLC0415
    from odev.commands.shell import _execute_shell  # noqa: PLC0415
    from odev.commands.sql import _execute_sql  # noqa: PLC0415
    from odev.commands.status import _execute_status  # noqa: PLC0415
    from odev.commands.test import _execute_test  # noqa: PLC0415

    @mcp.tool()
    def odev_status() -> list[dict]:
        """Get docker-compose service status."""
        return _execute_status(_resolve_contexto())

    @mcp.tool()
    def odev_shell(service: str, command: str) -> dict:
        """Run a shell command inside a service container."""
        return _execute_shell(_resolve_contexto(), service, command)

    @mcp.tool()
    def odev_sql(query: str) -> list[dict]:
        """Execute SELECT against the Odoo DB; returns rows as dicts."""
        return _execute_sql(_resolve_contexto(), query)

    @mcp.tool()
    def odev_py(expression: str) -> str:
        """Evaluate Python expression in odoo shell (banner-stripped)."""
        return _execute_py(_resolve_contexto(), expression)

    @mcp.tool()
    def odev_test(module: str, tags: str | None = None) -> dict:
        """Run Odoo tests for one or more modules (CSV)."""
        return _execute_test(_resolve_contexto(), module, tags=tags)

    @mcp.tool()
    def odev_logs(service: str, tail: int = 200) -> list[dict]:
        """Read recent service logs (parsed)."""
        return _execute_logs(_resolve_contexto(), service, tail)

    @mcp.tool()
    def odev_doctor() -> dict:
        """Run environment diagnostics; returns CheckResult dict."""
        return _execute_doctor(_resolve_contexto())

    @mcp.tool()
    def odev_model_info(model: str) -> dict:
        """Inspect an Odoo model's fields, inheritance, and methods."""
        return _execute_model_info(_resolve_contexto(), model)

    @mcp.tool()
    def odev_modules() -> list[dict]:
        """List installed Odoo modules with state and version."""
        return _execute_modules(_resolve_contexto())


# ---------------------------------------------------------------------------
# Resources (4)
# ---------------------------------------------------------------------------


def _register_resources(mcp) -> None:
    """Register 4 MCP resources."""

    @mcp.resource("odev://project/context")
    def project_context() -> str:
        """Current project context as markdown (equivalent to odev context)."""
        from odev.commands.context import _execute_context  # noqa: PLC0415

        return _execute_context(_resolve_contexto())

    @mcp.resource("odev://project/config")
    def project_config() -> str:
        """Parsed .odev.yaml contents as JSON."""
        import json  # noqa: PLC0415

        from odev.core.project import ProjectConfig  # noqa: PLC0415

        contexto = _resolve_contexto()
        cfg = ProjectConfig(contexto.directorio_config)
        return json.dumps(cfg.to_dict(), indent=2, ensure_ascii=False)

    @mcp.resource("odev://db/schema")
    def db_schema() -> str:
        """pg_dump --schema-only of the project database."""
        return _execute_db_schema(_resolve_contexto())

    @mcp.resource("odev://modules/{name}/manifest")
    def module_manifest(name: str) -> str:
        """Parsed __manifest__.py of a module as JSON."""
        import json  # noqa: PLC0415

        from odev.commands.context import _parsear_manifiesto  # noqa: PLC0415

        contexto = _resolve_contexto()
        path = _find_manifest(contexto, name)
        if path is None:
            raise ValueError(f"Module '{name}' not found in addons paths.")
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


def _register_prompts(mcp) -> None:
    """Register 3 MCP prompt templates."""

    @mcp.prompt()
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

    @mcp.prompt()
    def explain_module(module_name: str) -> str:
        """Explain an Odoo module's purpose, dependencies, and structure."""
        return (
            f"Explain the Odoo module '{module_name}'.\n\n"
            "Steps:\n"
            f"1. Fetch odev://modules/{module_name}/manifest to read declared metadata.\n"
            "2. Summarise: purpose, declared dependencies, data files, key models, views.\n"
            "3. Flag any unusual hooks (post-init, uninstall) or external deps."
        )

    @mcp.prompt()
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
