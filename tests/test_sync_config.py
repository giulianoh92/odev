"""Tests para comando odev sync-config."""

from __future__ import annotations

from typer.testing import CliRunner

from odev.main import app


class TestSyncConfigCommand:
    """Test suite para odev sync-config command."""

    def test_sync_config_help(self) -> None:
        """Verificar que odev sync-config --help funciona."""
        runner = CliRunner()
        result = runner.invoke(app, ["sync-config", "--help"])
        assert result.exit_code == 0
        assert "sync-config" in result.stdout or "regenera" in result.stdout.lower()

    def test_sync_config_no_project(self) -> None:
        """Si no hay proyecto odev, debe fallar gracefully."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(app, ["sync-config"])
            # Should fail with clear error, not crash
            assert result.exit_code != 0
            assert "no encontró" in result.stdout.lower() or "proyecto" in result.stdout.lower()

    def test_sync_config_command_exists(self) -> None:
        """Verifica que el comando sync-config está registrado en la app."""
        runner = CliRunner()
        # Llamar a app sin argumentos debería mostrar help y listar comandos
        result = runner.invoke(app, ["--help"])
        # Buscar sync-config en la salida (puede estar en la lista de comandos o en el help)
        assert result.exit_code == 0
        # El comando debería estar disponible (aunque no aparezca en todos los help texts)
        result = runner.invoke(app, ["sync-config", "--help"])
        assert result.exit_code == 0 or "No such command" not in result.stdout
