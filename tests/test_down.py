"""Tests para odev.commands.down — detener y eliminar contenedores.

Cubre:
- Q5: flag --dry-run (preview sin ejecutar Docker)
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _hacer_mocks_base(tmp_path: Path):
    """Construye los mocks comunes para contexto y docker."""
    ctx = MagicMock()
    ctx.nombre = "test-project"

    dc = MagicMock()

    return ctx, dc


class TestDownDryRun:
    """Q5 — verifica que --dry-run imprime intenciones sin ejecutar Docker."""

    def test_dry_run_no_ejecuta_down(self, tmp_path: Path) -> None:
        """Con --dry-run: dc.down NO debe ser llamado."""
        ctx, dc = _hacer_mocks_base(tmp_path)

        with (
            patch("odev.commands.down.requerir_proyecto", return_value=ctx),
            patch("odev.commands.down.obtener_docker", return_value=dc),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
        ):
            from odev.commands.down import down

            down(volumes=False, dry_run=True)

        dc.down.assert_not_called()

    def test_dry_run_muestra_mensaje_de_intencion(self, tmp_path: Path) -> None:
        """Con --dry-run: se emite al menos un mensaje de informacion."""
        ctx, dc = _hacer_mocks_base(tmp_path)

        with (
            patch("odev.commands.down.requerir_proyecto", return_value=ctx),
            patch("odev.commands.down.obtener_docker", return_value=dc),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("odev.commands.down.info") as mock_info,
        ):
            from odev.commands.down import down

            down(volumes=False, dry_run=True)

        assert mock_info.called, "Se esperaba al menos un info() con el mensaje de intencion"

    def test_dry_run_con_volumes_menciona_volumenes(self, tmp_path: Path) -> None:
        """Con --dry-run --volumes: el mensaje menciona volumenes."""
        ctx, dc = _hacer_mocks_base(tmp_path)

        with (
            patch("odev.commands.down.requerir_proyecto", return_value=ctx),
            patch("odev.commands.down.obtener_docker", return_value=dc),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("odev.commands.down.info") as mock_info,
        ):
            from odev.commands.down import down

            down(volumes=True, dry_run=True)

        all_msgs = " ".join(str(c) for c in mock_info.call_args_list)
        assert "volumen" in all_msgs.lower() or "-v" in all_msgs

    def test_dry_run_sin_volumes_no_menciona_volumenes(self, tmp_path: Path) -> None:
        """Con --dry-run sin --volumes: el mensaje NO menciona volumenes."""
        ctx, dc = _hacer_mocks_base(tmp_path)

        with (
            patch("odev.commands.down.requerir_proyecto", return_value=ctx),
            patch("odev.commands.down.obtener_docker", return_value=dc),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("odev.commands.down.info") as mock_info,
        ):
            from odev.commands.down import down

            down(volumes=False, dry_run=True)

        all_msgs = " ".join(str(c) for c in mock_info.call_args_list)
        assert "volumen" not in all_msgs.lower()

    def test_down_normal_sin_dry_run_ejecuta_down(self, tmp_path: Path) -> None:
        """Sin --dry-run: dc.down si debe ser llamado (comportamiento existente)."""
        ctx, dc = _hacer_mocks_base(tmp_path)

        with (
            patch("odev.commands.down.requerir_proyecto", return_value=ctx),
            patch("odev.commands.down.obtener_docker", return_value=dc),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("odev.commands.down.success"),
        ):
            from odev.commands.down import down

            down(volumes=False, dry_run=False)

        dc.down.assert_called_once()


class TestDownVolumesGuard:
    """U4 — guarda uniforme: warning + confirm solo cuando se pasa -v/--volumes.

    Espeja la guarda de reset_db/load_backup: plain 'odev down' (sin -v) no
    destruye datos persistentes y por eso no debe pedir confirmacion.
    """

    def test_sin_volumes_no_pide_confirmacion(self, tmp_path: Path) -> None:
        """odev down sin -v no debe invocar typer.confirm ni mostrar warning."""
        ctx, dc = _hacer_mocks_base(tmp_path)

        with (
            patch("odev.commands.down.requerir_proyecto", return_value=ctx),
            patch("odev.commands.down.obtener_docker", return_value=dc),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("typer.confirm") as mock_confirm,
            patch("odev.commands.down.warning") as mock_warning,
            patch("odev.commands.down.success"),
        ):
            from odev.commands.down import down

            down(volumes=False, yes=False, dry_run=False)

        mock_confirm.assert_not_called()
        mock_warning.assert_not_called()
        dc.down.assert_called_once_with(volumes=False)

    def test_con_volumes_pide_confirmacion(self, tmp_path: Path) -> None:
        """odev down -v debe invocar typer.confirm si no se pasa --yes."""
        ctx, dc = _hacer_mocks_base(tmp_path)

        with (
            patch("odev.commands.down.requerir_proyecto", return_value=ctx),
            patch("odev.commands.down.obtener_docker", return_value=dc),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("typer.confirm", return_value=True) as mock_confirm,
            patch("odev.commands.down.success"),
        ):
            from odev.commands.down import down

            down(volumes=True, yes=False, dry_run=False)

        mock_confirm.assert_called_once()
        dc.down.assert_called_once_with(volumes=True)

    def test_con_volumes_confirmacion_rechazada_cancela(self, tmp_path: Path) -> None:
        """Si el usuario rechaza la confirmacion, no se ejecuta dc.down."""
        import typer

        ctx, dc = _hacer_mocks_base(tmp_path)

        with (
            patch("odev.commands.down.requerir_proyecto", return_value=ctx),
            patch("odev.commands.down.obtener_docker", return_value=dc),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("typer.confirm", return_value=False),
        ):
            from odev.commands.down import down

            with pytest.raises(typer.Exit):
                down(volumes=True, yes=False, dry_run=False)

        dc.down.assert_not_called()

    def test_con_volumes_y_yes_saltea_confirmacion(self, tmp_path: Path) -> None:
        """-y/--yes saltea el prompt y ejecuta la destruccion directamente."""
        ctx, dc = _hacer_mocks_base(tmp_path)

        with (
            patch("odev.commands.down.requerir_proyecto", return_value=ctx),
            patch("odev.commands.down.obtener_docker", return_value=dc),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("typer.confirm") as mock_confirm,
            patch("odev.commands.down.success"),
        ):
            from odev.commands.down import down

            down(volumes=True, yes=True, dry_run=False)

        mock_confirm.assert_not_called()
        dc.down.assert_called_once_with(volumes=True)

    def test_dry_run_con_volumes_no_ejecuta_ni_confirma(self, tmp_path: Path) -> None:
        """--dry-run con -v no debe llamar typer.confirm ni dc.down — no destruye nada."""
        ctx, dc = _hacer_mocks_base(tmp_path)

        with (
            patch("odev.commands.down.requerir_proyecto", return_value=ctx),
            patch("odev.commands.down.obtener_docker", return_value=dc),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("typer.confirm") as mock_confirm,
        ):
            from odev.commands.down import down

            down(volumes=True, yes=False, dry_run=True)

        mock_confirm.assert_not_called()
        dc.down.assert_not_called()

    def test_con_volumes_warning_nombra_proyecto(self, tmp_path: Path) -> None:
        """El warning debe nombrar el proyecto y lo que se va a destruir."""
        ctx, dc = _hacer_mocks_base(tmp_path)

        with (
            patch("odev.commands.down.requerir_proyecto", return_value=ctx),
            patch("odev.commands.down.obtener_docker", return_value=dc),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("typer.confirm", return_value=True),
            patch("odev.commands.down.success"),
            patch("odev.commands.down.warning") as mock_warning,
        ):
            from odev.commands.down import down

            down(volumes=True, yes=False, dry_run=False)

        mock_warning.assert_called_once()
        mensaje = mock_warning.call_args[0][0]
        assert "test-project" in mensaje
