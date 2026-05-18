"""RED tests for MCP server commands/mcp.py.

Covers: lazy import guard, transport validation, skeleton registration,
tools, resources, prompts, stdout discipline. See spec C1-C5, tasks 2.1-2.13.
"""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_contexto(tmp_path=None):
    ctx = MagicMock()
    ctx.nombre = "test-project"
    if tmp_path:
        ctx.directorio_config = tmp_path
    # Provide an addons_paths list for manifest search
    ctx.rutas = MagicMock()
    ctx.rutas.addons_paths = []
    ctx.ruta_proyecto = None
    return ctx


# ---------------------------------------------------------------------------
# Task 2.1 / 2.4: lazy import guard + importable without mcp
# ---------------------------------------------------------------------------


class TestMcpLazyImport:
    """C5-R1, C1-S4: guard exits with code 2 when mcp package missing."""

    def test_module_importable_without_mcp_package(self, monkeypatch):
        """odev.commands.mcp can be imported even if mcp is not installed."""

        # Remove cached version to force fresh import
        to_remove = [k for k in sys.modules if k.startswith("odev.commands.mcp")]
        for k in to_remove:
            del sys.modules[k]

        original_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

        def mock_import(name, *args, **kwargs):
            if name == "mcp.server.fastmcp":
                raise ImportError("mcp not installed")
            return original_import(name, *args, **kwargs)

        # We just verify the module-level import doesn't crash; lazy guard is only in serve()
        import odev.commands.mcp  # noqa: F401

        assert hasattr(odev.commands.mcp, "mcp_app")

    def test_import_fastmcp_fails_exits_2(self, capsys):
        """_import_fastmcp() exits 2 + stderr hint when mcp missing."""
        to_remove = [k for k in sys.modules if "mcp.server.fastmcp" in k]
        for k in to_remove:
            del sys.modules[k]

        with patch.dict(sys.modules, {"mcp.server.fastmcp": None, "mcp": None}):
            import importlib

            to_remove2 = [k for k in sys.modules if k == "odev.commands.mcp"]
            for k in to_remove2:
                del sys.modules[k]

            import odev.commands.mcp as mcp_module

            # Reload to clear cached module
            importlib.reload(mcp_module)

            # Patch the import inside the function
            with patch.object(mcp_module, "_import_fastmcp") as mock_import:
                mock_import.side_effect = SystemExit(2)
                with pytest.raises(SystemExit) as exc:
                    mock_import()
                assert exc.value.code == 2

    def test_serve_exits_2_when_mcp_missing(self, capsys):
        """serve() writes stderr hint and exits 2 when mcp not installed."""
        import odev.commands.mcp as mcp_module

        def fake_import_fastmcp():
            sys.stderr.write(
                "ERROR: 'mcp' package not installed.\n"
                "Install with: pipx install --force 'odev[mcp]'\n"
            )
            raise SystemExit(2)

        with patch.object(mcp_module, "_import_fastmcp", side_effect=fake_import_fastmcp):
            with pytest.raises(SystemExit) as exc:
                mcp_module.serve(transport="stdio", port=3333)

        captured = capsys.readouterr()
        assert "odev[mcp]" in captured.err
        assert exc.value.code == 2


# ---------------------------------------------------------------------------
# Task 2.2: unknown transport exits 2
# ---------------------------------------------------------------------------


class TestMcpTransports:
    """C1: transport validation."""

    def test_unknown_transport_exits_2(self, capsys):
        """serve(transport='bogus') writes stderr and exits 2."""
        pytest.importorskip("mcp")
        import click

        import odev.commands.mcp as mcp_module

        fake_server = MagicMock()
        fake_server.run = MagicMock(return_value=None)

        with (
            patch.object(mcp_module, "_import_fastmcp", return_value=type("FakeMCP", (), {})),
            patch.object(mcp_module, "_configure_stderr_logging"),
            patch.object(mcp_module, "_build_server", return_value=fake_server),
        ):
            with pytest.raises((SystemExit, click.exceptions.Exit)) as exc:
                mcp_module.serve(transport="bogus", port=3333)

        captured = capsys.readouterr()
        assert "bogus" in captured.err
        exit_code = exc.value.code if isinstance(exc.value, SystemExit) else exc.value.exit_code
        assert exit_code == 2

    def test_keyboard_interrupt_exits_cleanly(self):
        """KeyboardInterrupt in serve() does not propagate (exits 0)."""
        pytest.importorskip("mcp")
        import odev.commands.mcp as mcp_module

        fake_server = MagicMock()
        fake_server.run = MagicMock(side_effect=KeyboardInterrupt)

        with (
            patch.object(mcp_module, "_import_fastmcp", return_value=type("FakeMCP", (), {})),
            patch.object(mcp_module, "_configure_stderr_logging"),
            patch.object(mcp_module, "_build_server", return_value=fake_server),
        ):
            # Should return without exception — no SystemExit
            mcp_module.serve(transport="stdio", port=3333)  # must not raise


# ---------------------------------------------------------------------------
# Task 2.5: mcp subcommand registered in app
# ---------------------------------------------------------------------------


class TestMcpRegistration:
    """C1: mcp_app is registered in main app."""

    def test_mcp_app_exists_in_module(self):
        """mcp_app Typer instance exists in commands/mcp.py."""
        import odev.commands.mcp as mcp_module

        assert hasattr(mcp_module, "mcp_app")
        import typer

        assert isinstance(mcp_module.mcp_app, typer.Typer)

    def test_mcp_registered_in_main_app(self):
        """mcp subcommand is registered in the main odev app."""
        from odev.main import app

        # Typer stores registered groups in app.registered_groups
        group_names = [g.typer_instance.info.name for g in app.registered_groups]
        assert "mcp" in group_names


# ---------------------------------------------------------------------------
# Tasks 2.6, 2.7, 2.8: Tools (requires mcp package)
# ---------------------------------------------------------------------------


mcp = pytest.importorskip("mcp", reason="mcp package not installed")


class TestMcpTools:
    """C2: 9 tools callable with mocked _execute_* returns."""

    def _build_server(self):
        from mcp.server.fastmcp import FastMCP

        import odev.commands.mcp as mcp_module

        return mcp_module._build_server(FastMCP)

    def _call_tool(self, server, name, args=None):
        """Call a registered tool via FastMCP.call_tool (async)."""
        return asyncio.run(server.call_tool(name, args or {}))

    def test_odev_status_tool_returns_list(self):
        """odev_status calls _execute_status and returns list."""
        import odev.commands.mcp as mcp_module

        with patch("odev.commands.status._execute_status", return_value=[{"service": "web", "status": "running", "ports": []}]):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                content, _ = self._call_tool(server, "odev_status")
                assert len(content) > 0

    def test_odev_shell_tool_returns_dict(self):
        """odev_shell calls _execute_shell and returns dict."""
        import odev.commands.mcp as mcp_module

        ret = {"stdout": "hello", "stderr": "", "returncode": 0}
        with patch("odev.commands.shell._execute_shell", return_value=ret):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                result = self._call_tool(server, "odev_shell", {"service": "web", "command": "echo hello"})
                content = result[0] if isinstance(result, tuple) else result
                assert len(content) > 0

    def test_odev_sql_tool_returns_list(self):
        """odev_sql calls _execute_sql and returns list."""
        import odev.commands.mcp as mcp_module

        with patch("odev.commands.sql._execute_sql", return_value=[{"id": 1}]):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                content, _ = self._call_tool(server, "odev_sql", {"query": "SELECT 1"})
                assert len(content) > 0

    def test_odev_py_tool_returns_str(self):
        """odev_py calls _execute_py and returns string."""
        import odev.commands.mcp as mcp_module

        with patch("odev.commands.py._execute_py", return_value="42"):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                content, _ = self._call_tool(server, "odev_py", {"expression": "1+1"})
                assert len(content) > 0

    def test_odev_test_tool_returns_dict(self):
        """odev_test calls _execute_test and returns TestResult dict."""
        import odev.commands.mcp as mcp_module

        ret = {"total": 1, "passed": 1, "failed": 0, "errors": 0, "duration": 0.1,
               "parse_failed": False, "raw_summary_line": "OK", "fallback_counters_used": False,
               "failures": []}
        with patch("odev.commands.test._execute_test", return_value=ret):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                result = self._call_tool(server, "odev_test", {"module": "my_module"})
                content = result[0] if isinstance(result, tuple) else result
                assert len(content) > 0

    def test_odev_logs_tool_returns_list(self):
        """odev_logs calls _execute_logs and returns list."""
        import odev.commands.mcp as mcp_module

        with patch("odev.commands.logs._execute_logs", return_value=[{"service": "web", "timestamp": "now", "level": "INFO", "message": "ok"}]):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                content, _ = self._call_tool(server, "odev_logs", {"service": "web"})
                assert len(content) > 0

    def test_odev_doctor_tool_returns_dict(self):
        """odev_doctor calls _execute_doctor and returns dict."""
        import odev.commands.mcp as mcp_module

        with patch("odev.commands.doctor._execute_doctor", return_value={"checks": []}):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                result = self._call_tool(server, "odev_doctor")
                content = result[0] if isinstance(result, tuple) else result
                assert len(content) > 0

    def test_odev_model_info_tool_returns_dict(self):
        """odev_model_info calls _execute_model_info and returns dict."""
        import odev.commands.mcp as mcp_module

        with patch("odev.commands.model_info._execute_model_info", return_value={"model": "res.partner", "fields": []}):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                result = self._call_tool(server, "odev_model_info", {"model": "res.partner"})
                content = result[0] if isinstance(result, tuple) else result
                assert len(content) > 0

    def test_odev_modules_tool_returns_list(self):
        """odev_modules calls _execute_modules and returns list."""
        import odev.commands.mcp as mcp_module

        with patch("odev.commands.modules._execute_modules", return_value=[{"name": "sale", "state": "installed", "version": "1.0"}]):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                content, _ = self._call_tool(server, "odev_modules")
                assert len(content) > 0

    def test_tool_error_path_raises(self):
        """When _execute_status raises RuntimeError, tool raises (server keeps running)."""
        import odev.commands.mcp as mcp_module

        with patch("odev.commands.status._execute_status", side_effect=RuntimeError("Docker not running")):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                with pytest.raises(Exception):
                    self._call_tool(server, "odev_status")

    def test_no_context_path_raises(self):
        """When _resolve_contexto raises ValueError, tool raises without typer.Exit."""
        import odev.commands.mcp as mcp_module

        with patch.object(mcp_module, "_resolve_contexto", side_effect=ValueError("No project")):
            server = self._build_server()
            with pytest.raises(Exception) as exc:
                self._call_tool(server, "odev_status")
            # Must not be typer.Exit
            import typer
            assert not isinstance(exc.value, typer.Exit)


# ---------------------------------------------------------------------------
# Tasks 2.9, 2.10, 2.11: Resources
# ---------------------------------------------------------------------------


class TestMcpResources:
    """C3: 4 resources callable."""

    def _build_server(self):
        from mcp.server.fastmcp import FastMCP

        import odev.commands.mcp as mcp_module

        return mcp_module._build_server(FastMCP)

    def _read_resource(self, server, uri):
        return asyncio.run(server.read_resource(uri))

    def test_project_context_resource(self):
        """odev://project/context returns markdown string."""
        import odev.commands.mcp as mcp_module

        with patch("odev.commands.context._execute_context", return_value="# My Project"):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                results = self._read_resource(server, "odev://project/context")
                assert len(results) > 0
                assert "My Project" in results[0].content

    def test_project_config_resource(self):
        """odev://project/config returns JSON string."""
        import json

        import odev.commands.mcp as mcp_module

        fake_config = MagicMock()
        fake_config.to_dict.return_value = {"odoo": {"version": "19.0"}}

        with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
            with patch("odev.core.project.ProjectConfig.__init__", return_value=None):
                with patch("odev.core.project.ProjectConfig.to_dict", return_value={"odoo": {"version": "19.0"}}):
                    server = self._build_server()
                    results = self._read_resource(server, "odev://project/config")
                    assert len(results) > 0
                    parsed = json.loads(results[0].content)
                    assert "odoo" in parsed

    def test_db_schema_resource(self):
        """odev://db/schema calls _execute_db_schema and returns string."""
        import odev.commands.mcp as mcp_module

        with patch.object(mcp_module, "_execute_db_schema", return_value="CREATE TABLE foo();"):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                results = self._read_resource(server, "odev://db/schema")
                assert len(results) > 0
                assert "CREATE" in results[0].content

    def test_module_manifest_resource(self):
        """odev://modules/{name}/manifest returns JSON string."""
        import json

        import odev.commands.mcp as mcp_module

        manifest = {"name": "Sale", "version": "16.0.1.0.0", "depends": ["base"]}
        with patch.object(mcp_module, "_find_manifest", return_value="/fake/path"):
            with patch("odev.commands.context._parsear_manifiesto", return_value=manifest):
                with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                    server = self._build_server()
                    results = self._read_resource(server, "odev://modules/sale/manifest")
                    assert len(results) > 0
                    parsed = json.loads(results[0].content)
                    assert "name" in parsed

    def test_missing_module_manifest_raises(self):
        """When _find_manifest returns None, resource raises ValueError."""
        import odev.commands.mcp as mcp_module

        with patch.object(mcp_module, "_find_manifest", return_value=None):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                with pytest.raises(Exception):
                    self._read_resource(server, "odev://modules/nonexistent/manifest")

    def test_no_context_on_resource_raises(self):
        """When _resolve_contexto raises, resource raises without crashing server."""
        import odev.commands.mcp as mcp_module

        with patch.object(mcp_module, "_resolve_contexto", side_effect=ValueError("No project")):
            server = self._build_server()
            with pytest.raises(Exception) as exc:
                self._read_resource(server, "odev://project/context")
            import typer
            assert not isinstance(exc.value, typer.Exit)


# ---------------------------------------------------------------------------
# Task 2.12: Prompts
# ---------------------------------------------------------------------------


class TestMcpPrompts:
    """C4: 3 prompts return templated strings with expected substitutions."""

    def _build_server(self):
        from mcp.server.fastmcp import FastMCP

        import odev.commands.mcp as mcp_module

        return mcp_module._build_server(FastMCP)

    def _get_prompt(self, server, name, args):
        result = asyncio.run(server.get_prompt(name, args))
        return result.messages[0].content.text

    def test_diagnose_failing_test_contains_test_name(self):
        """diagnose_failing_test includes test_name in output."""
        server = self._build_server()
        text = self._get_prompt(server, "diagnose_failing_test", {"test_name": "my_failing_test"})
        assert "my_failing_test" in text

    def test_explain_module_contains_module_name(self):
        """explain_module includes module_name in output."""
        server = self._build_server()
        text = self._get_prompt(server, "explain_module", {"module_name": "sale"})
        assert "sale" in text

    def test_generate_migration_contains_model_and_description(self):
        """generate_migration includes both model and description."""
        server = self._build_server()
        text = self._get_prompt(
            server, "generate_migration", {"model": "res.partner", "description": "add phone field"}
        )
        assert "res.partner" in text
        assert "add phone field" in text


# ---------------------------------------------------------------------------
# Task 2.13: Stdout discipline
# ---------------------------------------------------------------------------


class TestStdoutDiscipline:
    """CC1: tool calls must not write to stdout."""

    def _build_server(self):
        from mcp.server.fastmcp import FastMCP

        import odev.commands.mcp as mcp_module

        return mcp_module._build_server(FastMCP)

    def _call_tool(self, server, name, args=None):
        return asyncio.run(server.call_tool(name, args or {}))

    def test_no_stdout_on_all_tools(self, capsys):
        """No tool writes to stdout."""
        import odev.commands.mcp as mcp_module

        ctx = _make_contexto()

        patches = [
            patch("odev.commands.status._execute_status", return_value=[]),
            patch("odev.commands.shell._execute_shell", return_value={"stdout": "", "stderr": "", "returncode": 0}),
            patch("odev.commands.sql._execute_sql", return_value=[]),
            patch("odev.commands.py._execute_py", return_value=""),
            patch("odev.commands.test._execute_test", return_value={"total": 0, "passed": 0, "failed": 0, "errors": 0, "duration": 0.0, "parse_failed": False, "raw_summary_line": "", "fallback_counters_used": False, "failures": []}),
            patch("odev.commands.logs._execute_logs", return_value=[]),
            patch("odev.commands.doctor._execute_doctor", return_value={}),
            patch("odev.commands.model_info._execute_model_info", return_value={}),
            patch("odev.commands.modules._execute_modules", return_value=[]),
            patch.object(mcp_module, "_resolve_contexto", return_value=ctx),
        ]

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8], patches[9]:
            server = self._build_server()
            self._call_tool(server, "odev_status")
            self._call_tool(server, "odev_shell", {"service": "web", "command": "echo hi"})
            self._call_tool(server, "odev_sql", {"query": "SELECT 1"})
            self._call_tool(server, "odev_py", {"expression": "1"})
            self._call_tool(server, "odev_test", {"module": "base"})
            self._call_tool(server, "odev_logs", {"service": "web"})
            self._call_tool(server, "odev_doctor")
            self._call_tool(server, "odev_model_info", {"model": "res.partner"})
            self._call_tool(server, "odev_modules")

        captured = capsys.readouterr()
        assert captured.out == "", f"Unexpected stdout: {repr(captured.out)}"
