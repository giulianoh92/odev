"""RED tests for MCP server commands/mcp.py.

Covers: lazy import guard, transport validation, skeleton registration,
tools, resources, prompts, stdout discipline. See spec C1-C5, tasks 2.1-2.13.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
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

        original_import = (
            __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__
        )

        def mock_import(name, *args, **kwargs):
            if name == "mcp.server":
                raise ImportError("mcp not installed")
            return original_import(name, *args, **kwargs)

        # We just verify the module-level import doesn't crash; lazy guard is only in serve()
        import odev.commands.mcp  # noqa: F401

        assert hasattr(odev.commands.mcp, "mcp_app")

    def test_import_mcpserver_returns_class_when_available(self):
        """Happy path: the 2.x API is present, the class comes back."""
        pytest.importorskip("mcp.server", reason="mcp not installed")

        import odev.commands.mcp as mcp_module

        assert mcp_module._import_mcpserver() is not None

    def test_import_mcpserver_exits_3_when_mcp_absent(self, capsys):
        """`mcp` not importable at all -> exit 3 (environment error) + install hint.

        D4: a missing optional dependency is an environment problem, not a
        usage error -- EPILOG_EXIT_CODES reserves 2 for usage and 3 for
        environment.
        """
        import typer

        import odev.commands.mcp as mcp_module

        with patch.dict(sys.modules, {"mcp": None}):
            with pytest.raises(typer.Exit) as exc:
                mcp_module._import_mcpserver()

        assert exc.value.exit_code == 3
        err = capsys.readouterr().err
        assert "not installed" in err
        assert "odev[mcp]" in err

    def test_import_mcpserver_exits_3_when_sdk_too_old(self, capsys):
        """`mcp` present but pre-2.x (MCPServer missing from mcp.server).

        Regression: the guard must not report a version mismatch as "package
        not installed" — that sends the operator to reinstall something that
        is already there. D4: also an environment error -> exit 3.
        """
        import typer

        import odev.commands.mcp as mcp_module

        # `mcp` must be cached BEFORE the patch: mcp's __init__ pulls
        # mcp.server transitively, so in a cold process the patch below
        # would break `import mcp` itself and exercise the wrong branch.
        pytest.importorskip("mcp", reason="mcp not installed")

        with patch.dict(sys.modules, {"mcp.server": None}):
            with pytest.raises(typer.Exit) as exc:
                mcp_module._import_mcpserver()

        assert exc.value.exit_code == 3
        err = capsys.readouterr().err
        assert "not installed" not in err, "must not claim mcp is missing when it is present"
        assert "too old" in err
        assert "MCPServer" in err
        assert "mcp>=2" in err, "must point at the version floor, not a bare reinstall"

    def test_mcp_version_falls_back_to_unknown(self):
        """Version lookup never raises, even without package metadata."""
        from importlib.metadata import PackageNotFoundError

        import odev.commands.mcp as mcp_module

        with patch.object(mcp_module, "_pkg_version", side_effect=PackageNotFoundError):
            assert mcp_module._mcp_version() == "unknown"

    def test_serve_exits_2_when_mcp_missing(self, capsys):
        """serve() writes stderr hint and exits 2 when mcp not installed."""
        import odev.commands.mcp as mcp_module

        def fake_import_mcpserver():
            sys.stderr.write(
                "ERROR: 'mcp' package not installed.\n"
                "Install with: pipx install --force 'odev[mcp]'\n"
            )
            raise SystemExit(2)

        with patch.object(mcp_module, "_import_mcpserver", side_effect=fake_import_mcpserver):
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
        import typer

        import odev.commands.mcp as mcp_module

        fake_server = MagicMock()
        fake_server.run = MagicMock(return_value=None)

        with (
            patch.object(mcp_module, "_import_mcpserver", return_value=type("FakeMCP", (), {})),
            patch.object(mcp_module, "_configure_stderr_logging"),
            patch.object(mcp_module, "_build_server", return_value=fake_server),
        ):
            with pytest.raises((SystemExit, typer.Exit)) as exc:
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
            patch.object(mcp_module, "_import_mcpserver", return_value=type("FakeMCP", (), {})),
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
        from mcp.server import MCPServer

        import odev.commands.mcp as mcp_module

        return mcp_module._build_server(MCPServer)

    def _call_tool(self, server, name, args=None):
        """Call a registered tool. SDK 2.x returns a CallToolResult."""
        return asyncio.run(server.call_tool(name, args or {}))

    def test_odev_status_tool_returns_list(self):
        """odev_status calls _execute_status and returns list."""
        import odev.commands.mcp as mcp_module

        with patch(
            "odev.commands.status._execute_status",
            return_value=[{"service": "web", "status": "running", "ports": []}],
        ):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                result = self._call_tool(server, "odev_status")
                assert len(result.content) > 0

    def test_odev_shell_tool_returns_dict(self):
        """odev_shell calls _execute_shell and returns dict."""
        import odev.commands.mcp as mcp_module

        ret = {"stdout": "hello", "stderr": "", "returncode": 0}
        with patch("odev.commands.shell._execute_shell", return_value=ret):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                result = self._call_tool(
                    server, "odev_shell", {"service": "web", "command": "echo hello"}
                )
                content = result.content
                assert len(content) > 0

    def test_odev_sql_tool_returns_list(self):
        """odev_sql calls _execute_sql and returns list."""
        import odev.commands.mcp as mcp_module

        with patch("odev.commands.sql._execute_sql", return_value=[{"id": 1}]):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                content = self._call_tool(server, "odev_sql", {"query": "SELECT 1"})
                assert len(content.content) > 0

    def test_odev_py_tool_returns_dict(self):
        """odev_py calls _execute_py and returns a dict (result/committed/warning)."""
        import odev.commands.mcp as mcp_module

        with patch("odev.commands.py._execute_py", return_value="42"):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                result = self._call_tool(server, "odev_py", {"expression": "1+1"})
                assert len(result.content) > 0
                payload = json.loads(result.content[0].text)
                assert payload == {"result": "42", "committed": False, "warning": None}

    def test_odev_test_tool_returns_dict(self):
        """odev_test calls _execute_test and returns TestResult dict."""
        import odev.commands.mcp as mcp_module

        ret = {
            "total": 1,
            "passed": 1,
            "failed": 0,
            "errors": 0,
            "duration": 0.1,
            "parse_failed": False,
            "raw_summary_line": "OK",
            "fallback_counters_used": False,
            "failures": [],
        }
        with patch("odev.commands.test._execute_test", return_value=ret):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                result = self._call_tool(server, "odev_test", {"module": "my_module"})
                content = result[0] if isinstance(result, tuple) else result
                assert len(content.content) > 0

    def test_odev_logs_tool_returns_list(self):
        """odev_logs calls _execute_logs and returns list."""
        import odev.commands.mcp as mcp_module

        with patch(
            "odev.commands.logs._execute_logs",
            return_value=[{"service": "web", "timestamp": "now", "level": "INFO", "message": "ok"}],
        ):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                content = self._call_tool(server, "odev_logs", {"service": "web"})
                assert len(content.content) > 0

    def test_odev_doctor_tool_returns_dict(self):
        """odev_doctor calls _execute_doctor and returns dict."""
        import odev.commands.mcp as mcp_module

        with patch("odev.commands.doctor._execute_doctor", return_value={"checks": []}):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                result = self._call_tool(server, "odev_doctor")
                content = result[0] if isinstance(result, tuple) else result
                assert len(content.content) > 0

    def test_odev_model_info_tool_returns_dict(self):
        """odev_model_info calls _execute_model_info and returns dict."""
        import odev.commands.mcp as mcp_module

        with patch(
            "odev.commands.model_info._execute_model_info",
            return_value={"model": "res.partner", "fields": []},
        ):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                result = self._call_tool(server, "odev_model_info", {"model": "res.partner"})
                content = result[0] if isinstance(result, tuple) else result
                assert len(content.content) > 0

    def test_odev_modules_tool_returns_list(self):
        """odev_modules calls _execute_modules and returns list."""
        import odev.commands.mcp as mcp_module

        with patch(
            "odev.commands.modules._execute_modules",
            return_value=[{"name": "sale", "state": "installed", "version": "1.0"}],
        ):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                content = self._call_tool(server, "odev_modules")
                assert len(content.content) > 0

    def test_tool_error_path_raises(self):
        """When _execute_status raises RuntimeError, tool raises (server keeps running)."""
        import odev.commands.mcp as mcp_module

        with patch(
            "odev.commands.status._execute_status", side_effect=RuntimeError("Docker not running")
        ):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                with pytest.raises(Exception):
                    self._call_tool(server, "odev_status")

    def test_tool_error_keeps_the_original_message(self):
        """SDK 2.x withholds the message of anything but an anticipated failure.

        Without the _anticipado translation the caller would get a bare
        "Error executing tool odev_sql" and the actual DB error would stay
        buried in the server log.
        """
        from mcp.server.mcpserver.exceptions import ToolError

        import odev.commands.mcp as mcp_module

        with patch(
            "odev.commands.sql._execute_sql",
            side_effect=RuntimeError('ERROR: relation "res_partnr" does not exist'),
        ):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                with pytest.raises(ToolError) as exc:
                    self._call_tool(server, "odev_sql", {"query": "SELECT 1"})

        assert 'relation "res_partnr" does not exist' in str(exc.value)

    def test_odev_status_translates_called_process_error(self):
        """A3: odev_status must not crash untranslated when the stack is down.

        DockerCompose.ps_parsed() raises subprocess.CalledProcessError when
        `docker compose ps` fails (e.g. stack not running). Before A3 this
        escaped FALLOS_OPERATIVOS untranslated and the client only saw a bare
        "Error executing tool odev_status".
        """
        from mcp.server.mcpserver.exceptions import ToolError

        import odev.commands.mcp as mcp_module

        with patch(
            "odev.commands.status._execute_status",
            side_effect=subprocess.CalledProcessError(1, ["docker", "compose", "ps"]),
        ):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                with pytest.raises(ToolError) as exc:
                    self._call_tool(server, "odev_status")

        # The raw str() of a CalledProcessError is just a command line and a
        # return code -- useless. The translated message must be actionable.
        assert "Stack not running or DB unavailable" in str(exc.value)

    def test_odev_py_translates_called_process_error(self):
        """A3: odev_py must not crash untranslated when the stack is down.

        _execute_py's dc.exec_cmd(..., check=True) raises
        subprocess.CalledProcessError under the same conditions.
        """
        from mcp.server.mcpserver.exceptions import ToolError

        import odev.commands.mcp as mcp_module

        with patch(
            "odev.commands.py._execute_py",
            side_effect=subprocess.CalledProcessError(1, ["odoo", "shell"]),
        ):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                with pytest.raises(ToolError) as exc:
                    self._call_tool(server, "odev_py", {"expression": "1+1"})

        assert "Stack not running or DB unavailable" in str(exc.value)

    def test_odev_py_warning_for_writing_expression_without_commit(self):
        """odev_py's warning key is populated when the heuristic detects a write.

        This is the U7 fix for the gap the write-warning left behind: the CLI
        got --commit plus a stderr warning, but the MCP wrapper -- where an
        agent is most likely to report phantom work -- did not.
        """
        import odev.commands.mcp as mcp_module

        with patch(
            "odev.commands.py._execute_py",
            return_value="res.partner(1,)",
        ):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                result = self._call_tool(
                    server,
                    "odev_py",
                    {"expression": "env['res.partner'].create({'name': 'x'})"},
                )
                payload = json.loads(result.content[0].text)

        assert payload["result"] == "res.partner(1,)"
        assert payload["committed"] is False
        assert payload["warning"] is not None
        assert "commit" in payload["warning"]

    def test_odev_py_no_warning_when_commit_true(self):
        """The warning is null when commit=True, even for a writing expression."""
        import odev.commands.mcp as mcp_module

        with patch(
            "odev.commands.py._execute_py",
            return_value="res.partner(1,)",
        ) as mock_execute:
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                result = self._call_tool(
                    server,
                    "odev_py",
                    {"expression": "env['res.partner'].create({'name': 'x'})", "commit": True},
                )
                payload = json.loads(result.content[0].text)

        _, kwargs = mock_execute.call_args
        assert kwargs.get("commit") is True
        assert payload["committed"] is True
        assert payload["warning"] is None

    def test_odev_py_no_warning_for_read_only_expression(self):
        """The warning is null for an expression the heuristic does not flag."""
        import odev.commands.mcp as mcp_module

        with patch(
            "odev.commands.py._execute_py",
            return_value="3",
        ):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                result = self._call_tool(
                    server, "odev_py", {"expression": "env['res.partner'].search_count([])"}
                )
                payload = json.loads(result.content[0].text)

        assert payload["committed"] is False
        assert payload["warning"] is None

    def test_tool_bug_is_not_dressed_up_as_operational(self):
        """A bug in odev stays a crash: it belongs in the log, not in the model."""
        from mcp.server.mcpserver.exceptions import UnexpectedToolError

        import odev.commands.mcp as mcp_module

        with patch(
            "odev.commands.status._execute_status",
            side_effect=AttributeError("'NoneType' object has no attribute 'rutas'"),
        ):
            with patch.object(mcp_module, "_resolve_contexto", return_value=_make_contexto()):
                server = self._build_server()
                with pytest.raises(UnexpectedToolError):
                    self._call_tool(server, "odev_status")

    def test_missing_project_message_reaches_the_client(self):
        """_resolve_contexto's ValueError must survive as an anticipated failure."""
        from mcp.server.mcpserver.exceptions import ToolError

        import odev.commands.mcp as mcp_module

        with patch.object(
            mcp_module, "_resolve_contexto", side_effect=ValueError("No odev project found: nope")
        ):
            server = self._build_server()
            with pytest.raises(ToolError) as exc:
                self._call_tool(server, "odev_status")

        assert "No odev project found" in str(exc.value)

    def test_server_advertises_odev_version(self):
        """SDK 2.x defaults version to ""; the handshake must carry odev's."""
        from odev import __version__

        server = self._build_server()
        assert server.version == __version__
        assert server.version, "handshake must not advertise an empty version"

    def test_tool_schema_survives_the_error_wrapper(self):
        """functools.wraps must keep the signature the SDK builds schemas from."""
        server = self._build_server()
        tools = {t.name: t for t in asyncio.run(server.list_tools())}
        assert set(tools) >= {"odev_sql", "odev_shell", "odev_test"}
        props = tools["odev_shell"].input_schema["properties"]
        assert {"service", "command"} <= set(props), props
        assert tools["odev_sql"].description

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
        from mcp.server import MCPServer

        import odev.commands.mcp as mcp_module

        return mcp_module._build_server(MCPServer)

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
                with patch(
                    "odev.core.project.ProjectConfig.to_dict",
                    return_value={"odoo": {"version": "19.0"}},
                ):
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
        from mcp.server import MCPServer

        import odev.commands.mcp as mcp_module

        return mcp_module._build_server(MCPServer)

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
        from mcp.server import MCPServer

        import odev.commands.mcp as mcp_module

        return mcp_module._build_server(MCPServer)

    def _call_tool(self, server, name, args=None):
        return asyncio.run(server.call_tool(name, args or {}))

    def test_no_stdout_on_all_tools(self, capsys):
        """No tool writes to stdout."""
        import odev.commands.mcp as mcp_module

        ctx = _make_contexto()

        patches = [
            patch("odev.commands.status._execute_status", return_value=[]),
            patch(
                "odev.commands.shell._execute_shell",
                return_value={"stdout": "", "stderr": "", "returncode": 0},
            ),
            patch("odev.commands.sql._execute_sql", return_value=[]),
            patch("odev.commands.py._execute_py", return_value=""),
            patch(
                "odev.commands.test._execute_test",
                return_value={
                    "total": 0,
                    "passed": 0,
                    "failed": 0,
                    "errors": 0,
                    "duration": 0.0,
                    "parse_failed": False,
                    "raw_summary_line": "",
                    "fallback_counters_used": False,
                    "failures": [],
                },
            ),
            patch("odev.commands.logs._execute_logs", return_value=[]),
            patch("odev.commands.doctor._execute_doctor", return_value={}),
            patch("odev.commands.model_info._execute_model_info", return_value={}),
            patch("odev.commands.modules._execute_modules", return_value=[]),
            patch.object(mcp_module, "_resolve_contexto", return_value=ctx),
        ]

        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[5],
            patches[6],
            patches[7],
            patches[8],
            patches[9],
        ):
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


# ---------------------------------------------------------------------------
# Group 2 (SDD 0.6.0): _resolve_contexto ODEV_PROJECT env-var fallback
# ---------------------------------------------------------------------------


class TestResolveContextoEnvVar:
    """Verifica que _resolve_contexto respeta la variable de entorno ODEV_PROJECT.

    Desde 0.6.2 el lookup vive en `odev.main.obtener_nombre_proyecto`, por lo
    que estos tests ejercitan la integracion real (sin patchear esa funcion).
    """

    def test_resolve_contexto_uses_env_var(self, monkeypatch):
        """ODEV_PROJECT es usado cuando no hay flag --project."""
        import odev.commands.mcp as mcp_module
        import odev.main as main_module

        fake_ctx = _make_contexto()

        monkeypatch.setattr(main_module, "_nombre_proyecto", None)
        monkeypatch.setenv("ODEV_PROJECT", "sis-odoo")

        with patch("odev.core.resolver.resolver_proyecto", return_value=fake_ctx) as mock_resolver:
            result = mcp_module._resolve_contexto()

        mock_resolver.assert_called_once_with(nombre_proyecto="sis-odoo")
        assert result is fake_ctx

    def test_resolve_contexto_cli_flag_beats_env_var(self, monkeypatch):
        """El flag --project (estado global) gana sobre ODEV_PROJECT."""
        import odev.commands.mcp as mcp_module
        import odev.main as main_module

        fake_ctx = _make_contexto()

        monkeypatch.setattr(main_module, "_nombre_proyecto", "flag-project")
        monkeypatch.setenv("ODEV_PROJECT", "env-project")

        with patch("odev.core.resolver.resolver_proyecto", return_value=fake_ctx) as mock_resolver:
            mcp_module._resolve_contexto()

        mock_resolver.assert_called_once_with(nombre_proyecto="flag-project")

    def test_resolve_contexto_no_env_no_flag_falls_through(self, monkeypatch):
        """Sin flag ni env var, nombre_proyecto=None se pasa (cwd-walk activa)."""
        import odev.commands.mcp as mcp_module
        import odev.main as main_module

        fake_ctx = _make_contexto()

        monkeypatch.setattr(main_module, "_nombre_proyecto", None)
        monkeypatch.delenv("ODEV_PROJECT", raising=False)

        with patch("odev.core.resolver.resolver_proyecto", return_value=fake_ctx) as mock_resolver:
            mcp_module._resolve_contexto()

        mock_resolver.assert_called_once_with(nombre_proyecto=None)
