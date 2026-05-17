"""Tests para odev status --json — salida JSON para agentes.

Cubre:
  - C4-1: JSON array of service objects with service/status/ports keys
  - C4-2: empty stack → []
  - C4-3: no project context → stderr JSON error + exit 1

Llama status() directamente via Typer runner o mockeando internos.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import typer


def _make_contexto(tmp_path: Path) -> MagicMock:
    """Crea un ProjectContext mock con directorio temporal."""
    ctx = MagicMock()
    ctx.directorio_config = tmp_path
    ctx.nombre = "test-project"
    ctx.modo = MagicMock()
    ctx.modo.value = "standard"
    ctx.config = MagicMock()
    ctx.config.rutas_addons = None
    return ctx


# ---------------------------------------------------------------------------
# TestStatusJson (Spec C4-1 / C4-2 / C4-3)
# ---------------------------------------------------------------------------


class TestStatusJson:
    """Salida --json del comando status."""

    def test_json_output_contiene_claves_requeridas(self, tmp_path: Path, capsys) -> None:
        """C4-1: stdout es JSON array con service, status, ports por objeto."""
        from odev.commands.status import status

        servicios = [
            {"Service": "web", "State": "running", "Publishers": [{"PublishedPort": 8069, "TargetPort": 8069}]},
            {"Service": "db", "State": "running", "Publishers": []},
        ]
        ctx = _make_contexto(tmp_path)
        mock_dc = MagicMock()
        mock_dc.ps_parsed.return_value = servicios

        with (
            patch("odev.commands.status.requerir_proyecto", return_value=ctx),
            patch("odev.commands.status.obtener_docker", return_value=mock_dc),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
        ):
            try:
                status(json_output=True)
            except (SystemExit, typer.Exit):
                pass

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) == 2
        for item in data:
            assert "service" in item
            assert "status" in item
            assert "ports" in item

    def test_json_empty_stack(self, tmp_path: Path, capsys) -> None:
        """C4-2: stack down → stdout es [] y exit code 0."""
        from odev.commands.status import status

        ctx = _make_contexto(tmp_path)
        mock_dc = MagicMock()
        mock_dc.ps_parsed.return_value = []

        with (
            patch("odev.commands.status.requerir_proyecto", return_value=ctx),
            patch("odev.commands.status.obtener_docker", return_value=mock_dc),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
        ):
            exc = None
            try:
                status(json_output=True)
            except (SystemExit, typer.Exit) as e:
                exc = e

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data == []
        if exc is not None:
            code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
            assert code == 0

    def test_json_no_project_escribe_error_en_stderr_y_exit_1(
        self, tmp_path: Path, capsys
    ) -> None:
        """C4-3: sin proyecto → stderr JSON con key 'error' y exit 1."""
        from odev.commands.status import status
        from odev.core.resolver import ProyectoNoEncontradoError

        with (
            patch(
                "odev.commands.status.requerir_proyecto",
                side_effect=ProyectoNoEncontradoError("no project"),
            ),
            patch("odev.main.obtener_nombre_proyecto", return_value=None),
        ):
            exc = None
            try:
                status(json_output=True)
            except (SystemExit, typer.Exit) as e:
                exc = e

        assert exc is not None
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 1
        captured = capsys.readouterr()
        err_data = json.loads(captured.err)
        assert "error" in err_data
