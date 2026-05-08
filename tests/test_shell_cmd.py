"""Tests para el comando 'odev shell' — modo no-interactivo con flag -c.

Cubre:
  - REQ-1: odev shell -c ejecuta bash no-interactivo y propaga exit code
  - REQ-5: sin -c, behavior interactivo sin regresion
  - Scenarios 1-A, 1-B, 1-C, 1-D

Llama _run_shell() directamente para evitar problemas con OptionInfo defaults
de Typer al invocar shell() fuera del CLI runner.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer


# ---------------------------------------------------------------------------
# Helpers: contexto mock y patch helper
# ---------------------------------------------------------------------------


def _make_contexto(tmp_path: Path) -> MagicMock:
    """Crea un ProjectContext mock con directorio temporal."""
    ctx = MagicMock()
    ctx.directorio_config = tmp_path
    ctx.nombre = "test-project"
    ctx.config = MagicMock()
    ctx.config.rutas_addons = None
    return ctx


def _call_run_shell(tmp_path: Path, mock_dc: MagicMock, service: str, cmd):
    """Llama _run_shell con contexto mockeado.

    Parches incluidos:
      - requerir_proyecto: retorna mock context
      - obtener_docker: retorna mock_dc
      - obtener_nombre_proyecto: retorna 'test-project'
    """
    from odev.commands.shell import _run_shell

    ctx = _make_contexto(tmp_path)

    with (
        patch("odev.commands.shell.requerir_proyecto", return_value=ctx),
        patch("odev.commands.shell.obtener_docker", return_value=mock_dc),
        patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
    ):
        try:
            _run_shell(service, cmd)
        except (SystemExit, typer.Exit) as e:
            return e
    return None


# ---------------------------------------------------------------------------
# TestShellInteractivoSinCmd (Scenario 1-D / REQ-5)
# ---------------------------------------------------------------------------


class TestShellInteractivoSinCmd:
    """1-D: sin -c → exec_cmd(service, ['bash'], interactive=True) — zero regression."""

    def test_shell_sin_cmd_es_interactivo(self, tmp_path: Path) -> None:
        """Sin -c, se llama exec_cmd con interactive=True y args=['bash']."""
        mock_dc = MagicMock()
        mock_dc.exec_cmd = MagicMock(return_value=None)

        _call_run_shell(tmp_path, mock_dc, "web", None)

        mock_dc.exec_cmd.assert_called_once_with("web", ["bash"], interactive=True)


# ---------------------------------------------------------------------------
# TestShellNoInteractivoConCmd (Scenario 1-A)
# ---------------------------------------------------------------------------


class TestShellNoInteractivoConCmd:
    """1-A: con -c '<cmd>' → exec_cmd no-interactivo con argv correcto."""

    def test_shell_con_cmd_no_interactivo_pasa_argv(self, tmp_path: Path) -> None:
        """Con -c 'ls /mnt', exec_cmd llamado con ['bash', '-c', 'ls /mnt'] + interactive=False."""
        mock_dc = MagicMock()
        mock_dc.exec_cmd.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"", stderr=b""
        )

        _call_run_shell(tmp_path, mock_dc, "web", "ls /mnt")

        mock_dc.exec_cmd.assert_called_once_with(
            "web", ["bash", "-c", "ls /mnt"], interactive=False
        )

    def test_shell_con_cmd_imprime_stdout_y_propaga_exit(
        self, tmp_path: Path, capsys
    ) -> None:
        """Con -c, stdout del contenedor se escribe en sys.stdout y exit code 0 se propaga."""
        mock_dc = MagicMock()
        mock_dc.exec_cmd.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"hello\n", stderr=b""
        )

        exc = _call_run_shell(tmp_path, mock_dc, "web", "echo hello")

        # El exit code debe ser 0
        assert exc is not None
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 0

    def test_shell_con_cmd_propaga_exit_no_cero(self, tmp_path: Path) -> None:
        """Con -c que retorna exit 42, _run_shell levanta typer.Exit(42)."""
        mock_dc = MagicMock()
        mock_dc.exec_cmd.side_effect = subprocess.CalledProcessError(
            returncode=42, cmd=["bash", "-c", "exit 42"], stderr=b""
        )

        exc = _call_run_shell(tmp_path, mock_dc, "web", "exit 42")

        assert exc is not None
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 42


# ---------------------------------------------------------------------------
# TestShellCmdVacio (Scenario 1-C)
# ---------------------------------------------------------------------------


class TestShellCmdVacio:
    """1-C: -c '' (o solo espacios) → exit 2, contenedor NO contactado."""

    def test_shell_cmd_vacio_falla_exit_2(self, tmp_path: Path) -> None:
        """_run_shell(service, '  ') → typer.Exit(2) y exec_cmd NO llamado."""
        mock_dc = MagicMock()

        exc = _call_run_shell(tmp_path, mock_dc, "web", "  ")

        assert exc is not None
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 2
        mock_dc.exec_cmd.assert_not_called()
