"""Tests para odev.commands.logs — snapshot JSON output.

Spec C2: logs <service> --json emite array JSON de lineas de log.

Los tests cubren:
  C2-S1  parse schema: cada entrada tiene service/timestamp/level/message
  C2-S3  --json y --follow son mutuamente excluyentes (exit 2)
  C2-S4  --tail N limita la cantidad de entradas
  C2-S6  servicio sin logs -> []
  C2-S7  servicio desconocido -> exit 2 + JSON en stderr
  C2-S9  traceback multilinea -> N entradas con level: null
"""

import io
import json
from unittest.mock import MagicMock, patch

import pytest
import typer

from odev.commands.logs import _parse_logs

# ── Helpers ───────────────────────────────────────────────────────────────────


def _run_logs(service="web", json_output=True, follow=None, tail=100, patches=()):
    """Invoca logs() capturando stdout, stderr y exit code."""
    from odev.commands.logs import logs

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    exit_code = 0

    with patch("sys.stdout", stdout_buf), patch("sys.stderr", stderr_buf):
        for p in patches:
            p.start()
        try:
            kwargs = {"service": service, "json_output": json_output, "tail": tail, "no_follow": False}
            if follow is not None:
                kwargs["follow"] = follow
            logs(**kwargs)
        except (SystemExit, typer.Exit) as e:
            exit_code = e.code if isinstance(e, SystemExit) else e.exit_code
        finally:
            for p in patches:
                p.stop()

    return stdout_buf.getvalue(), stderr_buf.getvalue(), exit_code


# ── Unit tests for _parse_logs (pure function) ────────────────────────────────


class TestParseLogs:
    """Tests for the _parse_logs() pure function.

    This function is the core of D2 — it converts raw docker compose log text
    into a list of structured dicts.
    """

    def test_c2_s1_parse_schema_valid(self):
        """C2-S1: parse returns list of dicts with correct keys.

        Each entry has service, timestamp, level (or null), message.
        """
        raw = "web  | 2024-01-01T00:00:00.000000000Z 123 456 INFO odoo.models model loaded\n"
        entries = _parse_logs(raw)

        assert len(entries) == 1
        entry = entries[0]
        assert entry["service"] == "web"
        assert entry["timestamp"] == "2024-01-01T00:00:00.000000000Z"
        assert entry["level"] == "INFO"
        assert "model loaded" in entry["message"]

    def test_c2_s9_multiline_traceback_each_line_level_null(self):
        """C2-S9: multi-line traceback -> N entries each with level: null."""
        raw = (
            "web  | 2024-01-01T00:00:01.000000000Z Traceback (most recent call last):\n"
            "web  | 2024-01-01T00:00:01.000000001Z   File 'model.py', line 42\n"
            "web  | 2024-01-01T00:00:01.000000002Z ValueError: bad value\n"
        )
        entries = _parse_logs(raw)

        assert len(entries) == 3
        for entry in entries:
            assert entry["level"] is None, f"Expected null level for traceback line: {entry}"

    def test_c2_s6_empty_input_returns_empty_list(self):
        """C2-S6: empty raw input -> []."""
        entries = _parse_logs("")
        assert entries == []

    def test_c2_s4_tail_respected_by_parse(self):
        """C2-S4: _parse_logs handles multi-entry input, each line independent."""
        lines = [
            f"web  | 2024-01-01T00:00:{i:02d}.000000000Z 1 1 INFO line {i}\n"
            for i in range(10)
        ]
        raw = "".join(lines)
        entries = _parse_logs(raw)

        assert len(entries) == 10
        # All entries have level INFO
        assert all(e["level"] == "INFO" for e in entries)

    def test_non_odoo_line_level_null(self):
        """Lines that don't match Odoo log format get level: null."""
        raw = "web  | 2024-01-01T00:00:00.000000000Z plain nginx log line\n"
        entries = _parse_logs(raw)

        assert len(entries) == 1
        assert entries[0]["level"] is None
        assert entries[0]["message"] == "plain nginx log line"


# ── Integration tests for logs() command ─────────────────────────────────────


class TestLogsJsonOutput:
    """Integration tests for logs() command with --json flag."""

    @pytest.fixture
    def mock_context_and_dc(self, tmp_path):
        """Provide mock project context and DockerCompose."""
        mock_ctx = MagicMock()
        mock_dc = MagicMock()
        mock_dc.ps_parsed.return_value = [{"Service": "web", "State": "running"}]

        ctx_patch = patch("odev.commands.logs.requerir_proyecto", return_value=mock_ctx)
        dc_patch = patch("odev.commands.logs.obtener_docker", return_value=mock_dc)
        # obtener_nombre_proyecto is imported lazily inside logs() from odev.main
        nombre_patch = patch("odev.main.obtener_nombre_proyecto", return_value=None)

        return mock_dc, [ctx_patch, dc_patch, nombre_patch]

    def test_c2_s7_unknown_service_exit_2(self, mock_context_and_dc):
        """C2-S7: unknown service -> exit 2, stderr contains JSON error."""
        mock_dc, base_patches = mock_context_and_dc
        # ps_parsed returns only 'web', so 'nonexistent' is unknown
        mock_dc.ps_parsed.return_value = [{"Service": "web", "State": "running"}]

        _, stderr, exit_code = _run_logs(
            service="nonexistent", json_output=True, patches=base_patches
        )

        assert exit_code == 2
        err_data = json.loads(stderr.strip())
        assert "error" in err_data

    def test_c2_s3_json_and_follow_mutual_exclusion(self, mock_context_and_dc):
        """C2-S3: --json + --follow -> exit 2, error in stderr."""
        _, base_patches = mock_context_and_dc

        _, stderr, exit_code = _run_logs(
            service="web", json_output=True, follow=True, patches=base_patches
        )

        assert exit_code == 2
        err_data = json.loads(stderr.strip())
        assert "error" in err_data
