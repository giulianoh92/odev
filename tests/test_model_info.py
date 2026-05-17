"""Tests para odev.commands.model_info — introspeccion de modelos Odoo.

Spec C3: model-info <model> emite JSON con schema de modelo, campos e inherits.

Los tests cubren:
  C3-S1  happy path — schema valido, model correcto, fields no-vacio
  C3-S2  model no encontrado -> exit 1 + stderr JSON
  C3-S3  stack down -> exit 3
  C3-S4  no project context -> exit 1
  C3-S5  modelo con 100+ fields -> JSON single-line valido
  C3-S6  --pretty -> JSON indentado
  C3-S7  inherits populated -> inherits lista no-vacia
"""

import io
import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest
import typer

# ── Helpers ───────────────────────────────────────────────────────────────────

# Simulated Odoo shell banner lines
_BANNER = (
    b"2024-01-01 00:00:00,000 1 INFO db odoo.modules: Loading module sale\n"
    b"2024-01-01 00:00:01,000 1 INFO db odoo.modules: Modules loaded.\n"
    b"odoo: db>\n"
)

def _make_model_payload(model="res.partner", inherits=None, n_fields=3):
    """Build a minimal model payload dict."""
    fields = [
        {"name": f"field_{i}", "type": "char", "required": False, "relation": None}
        for i in range(n_fields)
    ]
    return {
        "model": model,
        "description": f"Test model {model}",
        "inherits": inherits or [],
        "fields": fields,
    }


def _run_model_info(model="res.partner", pretty=False, patches=()):
    """Invoke model_info() capturing stdout, stderr, and exit code."""
    from odev.commands.model_info import model_info

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    exit_code = 0

    with patch("sys.stdout", stdout_buf), patch("sys.stderr", stderr_buf):
        for p in patches:
            p.start()
        try:
            model_info(model=model, pretty=pretty)
        except (SystemExit, typer.Exit) as e:
            exit_code = e.code if isinstance(e, SystemExit) else e.exit_code
        finally:
            for p in patches:
                p.stop()

    return stdout_buf.getvalue(), stderr_buf.getvalue(), exit_code


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestModelInfo:
    """Tests for C3: model-info command."""

    @pytest.fixture
    def mock_context(self, tmp_path):
        """Provide mock project context and DockerCompose."""
        mock_ctx = MagicMock()
        mock_dc = MagicMock()

        ctx_patch = patch("odev.commands.model_info.requerir_proyecto", return_value=mock_ctx)
        dc_patch = patch("odev.commands.model_info.obtener_docker", return_value=mock_dc)
        # obtener_nombre_proyecto is imported lazily inside model_info() from odev.main
        nombre_patch = patch("odev.main.obtener_nombre_proyecto", return_value=None)

        return mock_dc, [ctx_patch, dc_patch, nombre_patch]

    def test_c3_s1_happy_path_schema_valid(self, mock_context):
        """C3-S1: known model -> valid schema, model field correct, fields non-empty."""
        mock_dc, base_patches = mock_context
        payload = _make_model_payload("res.partner", n_fields=5)
        raw_stdout = _BANNER + (json.dumps(payload) + "\n").encode()

        mock_dc.exec_cmd.return_value = MagicMock(
            returncode=0,
            stdout=raw_stdout,
            stderr=b"",
        )

        out, _, exit_code = _run_model_info(model="res.partner", patches=base_patches)

        assert exit_code == 0
        data = json.loads(out.strip())
        assert data["model"] == "res.partner"
        assert "description" in data
        assert "inherits" in data
        assert isinstance(data["fields"], list)
        assert len(data["fields"]) > 0

    def test_c3_s2_model_not_found_exit_1(self, mock_context):
        """C3-S2: model not found -> exit 1, stderr has JSON error."""
        mock_dc, base_patches = mock_context
        err_payload = {"error": "Model not found: nonexistent.model"}
        mock_dc.exec_cmd.return_value = MagicMock(
            returncode=1,
            stdout=_BANNER,
            stderr=json.dumps(err_payload).encode() + b"\n",
        )

        _, stderr, exit_code = _run_model_info(model="nonexistent.model", patches=base_patches)

        assert exit_code == 1
        err_data = json.loads(stderr.strip())
        assert "error" in err_data
        assert "not found" in err_data["error"].lower() or "Model" in err_data["error"]

    def test_c3_s3_stack_down_exit_3(self, mock_context):
        """C3-S3: stack not running -> exit 3."""
        mock_dc, base_patches = mock_context
        mock_dc.exec_cmd.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["docker", "compose", "exec"], stderr=b"Cannot connect"
        )

        _, _, exit_code = _run_model_info(model="res.partner", patches=base_patches)

        assert exit_code == 3

    def test_c3_s4_no_project_context_exit_1(self):
        """C3-S4: no project context -> exit 1 (requerir_proyecto raises SystemExit)."""
        no_proj_patch = patch(
            "odev.commands.model_info.requerir_proyecto",
            side_effect=SystemExit(1),
        )
        # obtener_nombre_proyecto is imported lazily inside model_info() from odev.main
        nombre_patch = patch("odev.main.obtener_nombre_proyecto", return_value=None)

        _, _, exit_code = _run_model_info(
            model="res.partner", patches=[no_proj_patch, nombre_patch]
        )

        assert exit_code == 1

    def test_c3_s7_inherits_populated(self, mock_context):
        """C3-S7: field with inherits -> inherits list is non-empty."""
        mock_dc, base_patches = mock_context
        payload = _make_model_payload("mail.thread", inherits=["base", "mail.message"])
        raw_stdout = _BANNER + (json.dumps(payload) + "\n").encode()
        mock_dc.exec_cmd.return_value = MagicMock(
            returncode=0, stdout=raw_stdout, stderr=b""
        )

        out, _, exit_code = _run_model_info(model="mail.thread", patches=base_patches)

        assert exit_code == 0
        data = json.loads(out.strip())
        assert isinstance(data["inherits"], list)
        assert len(data["inherits"]) >= 1

    def test_c3_s6_pretty_flag_indented_json(self, mock_context):
        """C3-S6: --pretty -> stdout is indented JSON (2-space indent)."""
        mock_dc, base_patches = mock_context
        payload = _make_model_payload("res.partner")
        raw_stdout = _BANNER + (json.dumps(payload) + "\n").encode()
        mock_dc.exec_cmd.return_value = MagicMock(
            returncode=0, stdout=raw_stdout, stderr=b""
        )

        out, _, exit_code = _run_model_info(
            model="res.partner", pretty=True, patches=base_patches
        )

        assert exit_code == 0
        # Indented JSON has newlines
        assert "\n" in out.strip()
        # Still valid JSON with same schema
        data = json.loads(out)
        assert data["model"] == "res.partner"

    def test_c3_s5_large_model_single_line(self, mock_context):
        """C3-S5: model with 100+ fields -> single-line valid JSON, no truncation."""
        mock_dc, base_patches = mock_context
        payload = _make_model_payload("account.move", n_fields=120)
        raw_stdout = _BANNER + (json.dumps(payload) + "\n").encode()
        mock_dc.exec_cmd.return_value = MagicMock(
            returncode=0, stdout=raw_stdout, stderr=b""
        )

        out, _, exit_code = _run_model_info(model="account.move", patches=base_patches)

        assert exit_code == 0
        # Single line (no newlines in the content)
        lines = [ln for ln in out.splitlines() if ln.strip()]
        assert len(lines) == 1, f"Expected single-line JSON, got {len(lines)} lines"
        data = json.loads(lines[0])
        assert len(data["fields"]) == 120
