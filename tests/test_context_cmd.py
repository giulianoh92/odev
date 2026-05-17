"""Tests para odev context --json --quiet — salida JSON para agentes.

Cubre:
  - C5-1: quiet JSON tiene claves requeridas (project_name, odoo_version, addons_paths)
  - C5-2: --json suprime Rich (capsys no muestra decoraciones Rich)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import typer


def _make_contexto(tmp_path: Path, nombre: str = "test-project") -> MagicMock:
    """Crea un ProjectContext mock con directorio temporal."""
    ctx = MagicMock()
    ctx.directorio_config = tmp_path
    ctx.nombre = nombre
    ctx.config = MagicMock()
    ctx.config.rutas_addons = ["./addons"]
    return ctx


# ---------------------------------------------------------------------------
# TestContextJson (Spec C5-1 / C5-2)
# ---------------------------------------------------------------------------


class TestContextJson:
    """Salida --json --quiet del comando context."""

    def test_json_tiene_claves_requeridas(self, tmp_path: Path, capsys) -> None:
        """C5-1: stdout es JSON con project_name, odoo_version, addons_paths al menos."""
        from odev.commands.context import context

        ctx = _make_contexto(tmp_path)
        env = {
            "ODOO_VERSION": "17.0",
            "DB_NAME": "mydb",
            "DB_HOST": "db",
            "DB_PORT": "5432",
        }

        with (
            patch("odev.commands.context.requerir_proyecto", return_value=ctx),
            patch("odev.commands.context.obtener_rutas") as mock_rutas,
            patch("odev.commands.context.load_env", return_value=env),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            mock_rutas.return_value.addons_dirs = [tmp_path / "addons"]
            try:
                context(json_output=True, quiet=True)
            except (SystemExit, typer.Exit):
                pass

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "project_name" in data
        assert "odoo_version" in data
        assert "addons_paths" in data
        assert isinstance(data["addons_paths"], list)

    def test_json_suprime_rich(self, tmp_path: Path, capsys) -> None:
        """C5-2: con --json, stdout no contiene decoraciones Rich (sin [bold], sin tablas)."""
        from odev.commands.context import context

        ctx = _make_contexto(tmp_path)
        env = {
            "ODOO_VERSION": "16.0",
            "DB_NAME": "testdb",
            "DB_HOST": "db",
            "DB_PORT": "5432",
        }

        with (
            patch("odev.commands.context.requerir_proyecto", return_value=ctx),
            patch("odev.commands.context.obtener_rutas") as mock_rutas,
            patch("odev.commands.context.load_env", return_value=env),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            mock_rutas.return_value.addons_dirs = [tmp_path / "addons"]
            try:
                context(json_output=True, quiet=True)
            except (SystemExit, typer.Exit):
                pass

        captured = capsys.readouterr()
        # stdout debe ser JSON puro, sin markdown ni markup Rich
        out = captured.out.strip()
        assert out.startswith("{") or out.startswith("["), f"stdout no es JSON: {out!r}"
        # No debe tener markup Rich tipo [bold] o ###
        assert "[bold]" not in out
        assert "###" not in out
