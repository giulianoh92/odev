"""Tests para los comandos 'odev update' y 'odev addon-install' con CSV.

Cubre REQ-3 (update) y REQ-4 (addon-install):
  - backward compat single-module
  - CSV → una sola llamada Odoo con args comma-joined
  - 'all' mezclado con CSV → exit 2
  - modulo desconocido → exit 2
  - --no-validate → bypassa validacion

Desde 0.7.0 cubre ademas el modo compacto default (exec_capture + filtro
de log) y el flag --verbose que restaura el stream interactivo crudo.

Usa invocacion directa (sin CliRunner) siguiendo el patron de test_test_cmd.py.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import typer

# ---------------------------------------------------------------------------
# Fixtures de log Odoo (exec_capture entrega stderr; Odoo loguea a stderr)
# ---------------------------------------------------------------------------

_LOG_OK = b"""\
2026-07-03 10:00:00,001 1 INFO test_db odoo.modules.loading: loading 42 modules...
2026-07-03 10:00:01,100 1 INFO test_db odoo.modules.loading: Modules loaded.
"""

_LOG_WARNING = b"""\
2026-07-03 10:00:00,001 1 INFO test_db odoo.modules.loading: loading 42 modules...
2026-07-03 10:00:00,500 1 WARNING test_db odoo.models: sale.order: inconsistent 'compute_sudo' among fields
2026-07-03 10:00:01,100 1 INFO test_db odoo.modules.loading: Modules loaded.
"""

_LOG_TRACEBACK = b"""\
2026-07-03 10:00:00,001 1 INFO test_db odoo.modules.loading: loading 42 modules...
2026-07-03 10:00:00,800 1 ERROR test_db odoo.modules.registry: Failed to load registry
Traceback (most recent call last):
  File "/odoo/addons/my_mod/models/thing.py", line 12, in <module>
    class Thing(models.Model)
SyntaxError: expected ':'
"""

_CAPTURE_OK = (b"", _LOG_OK, 0)

# ---------------------------------------------------------------------------
# Helpers de test
# ---------------------------------------------------------------------------


def _make_contexto(tmp_path: Path) -> MagicMock:
    """Crea un ProjectContext mock con directorio temporal."""
    ctx = MagicMock()
    ctx.directorio_config = tmp_path
    ctx.nombre = "test-project"
    ctx.config = MagicMock()
    ctx.config.rutas_addons = None
    return ctx


def _call_update(
    tmp_path: Path,
    module: str,
    no_validate: bool = False,
    modulos_disponibles: set[str] | None = None,
    verbose: bool = False,
    capture: tuple[bytes, bytes, int] = _CAPTURE_OK,
):
    """Invoca el comando update con los args dados.

    Retorna (exception_or_none, mock_dc).
    """
    from odev.commands.update import update

    ctx = _make_contexto(tmp_path)
    mock_dc = MagicMock()
    mock_dc.exec_cmd = MagicMock()
    mock_dc.exec_capture = MagicMock(return_value=capture)
    mock_dc.restart = MagicMock()

    disponibles = modulos_disponibles if modulos_disponibles is not None else set()

    exc = None
    with (
        patch("odev.commands.update.requerir_proyecto", return_value=ctx),
        patch("odev.commands.update.obtener_docker", return_value=mock_dc),
        patch("odev.commands.update.obtener_rutas") as mock_rutas,
        patch("odev.commands.update.load_env", return_value={"DB_NAME": "test_db"}),
        patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
        patch("odev.commands._helpers.listar_modulos_disponibles", return_value=disponibles),
    ):
        mock_rutas.return_value.env_file = tmp_path / ".env"
        try:
            update(module=module, no_validate=no_validate, verbose=verbose)
        except (SystemExit, typer.Exit) as e:
            exc = e

    return exc, mock_dc


def _call_install(
    tmp_path: Path,
    module: str,
    no_validate: bool = False,
    modulos_disponibles: set[str] | None = None,
    verbose: bool = False,
    capture: tuple[bytes, bytes, int] = _CAPTURE_OK,
):
    """Invoca el comando install con los args dados."""
    from odev.commands.install import install

    ctx = _make_contexto(tmp_path)
    mock_dc = MagicMock()
    mock_dc.exec_cmd = MagicMock()
    mock_dc.exec_capture = MagicMock(return_value=capture)
    mock_dc.restart = MagicMock()

    disponibles = modulos_disponibles if modulos_disponibles is not None else set()

    exc = None
    with (
        patch("odev.commands.install.requerir_proyecto", return_value=ctx),
        patch("odev.commands.install.obtener_docker", return_value=mock_dc),
        patch("odev.commands.install.obtener_rutas") as mock_rutas,
        patch("odev.commands.install.load_env", return_value={"DB_NAME": "test_db"}),
        patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
        patch("odev.commands._helpers.listar_modulos_disponibles", return_value=disponibles),
    ):
        mock_rutas.return_value.env_file = tmp_path / ".env"
        try:
            install(module=module, no_validate=no_validate, verbose=verbose)
        except (SystemExit, typer.Exit) as e:
            exc = e

    return exc, mock_dc


def _exit_code(exc) -> int | None:
    if exc is None:
        return 0
    return exc.code if isinstance(exc, SystemExit) else exc.exit_code


# ---------------------------------------------------------------------------
# REQ-3: odev update — CSV support
# ---------------------------------------------------------------------------


class TestUpdateCSV:
    """REQ-3: update acepta CSV de modulos y genera invocacion Odoo unica."""

    def test_3a_single_module_backward_compat(self, tmp_path: Path) -> None:
        """3-A: 'odev update sale' → Odoo llamado con -u sale (identico a antes)."""
        exc, mock_dc = _call_update(tmp_path, "sale")

        assert _exit_code(exc) == 0
        mock_dc.exec_capture.assert_called_once()
        cmd = mock_dc.exec_capture.call_args[0][1]
        assert "-u" in cmd
        assert "sale" in cmd

    def test_3b_csv_genera_llamada_unica(self, tmp_path: Path) -> None:
        """3-B: 'odev update sale,crm' → Odoo llamado UNA SOLA vez con -u sale,crm."""
        exc, mock_dc = _call_update(tmp_path, "sale,crm")

        assert _exit_code(exc) == 0
        mock_dc.exec_capture.assert_called_once()
        cmd = mock_dc.exec_capture.call_args[0][1]
        assert "-u" in cmd
        idx_u = cmd.index("-u")
        assert cmd[idx_u + 1] == "sale,crm"

    def test_3b_csv_reinicia_web_una_sola_vez(self, tmp_path: Path) -> None:
        """3-B: CSV → dc.restart('web') llamado exactamente una vez."""
        exc, mock_dc = _call_update(tmp_path, "sale,crm")

        assert _exit_code(exc) == 0
        mock_dc.restart.assert_called_once_with("web")

    def test_3c_modulo_desconocido_exit_2(self, tmp_path: Path) -> None:
        """3-C: modulo no encontrado (disponibles conocidos) → exit 2, Odoo no llamado."""
        exc, mock_dc = _call_update(
            tmp_path,
            "ghost_mod",
            modulos_disponibles={"sale", "crm"},
        )

        assert _exit_code(exc) == 2
        mock_dc.exec_cmd.assert_not_called()
        mock_dc.exec_capture.assert_not_called()

    def test_3d_no_validate_bypassa(self, tmp_path: Path) -> None:
        """3-D: --no-validate omite validacion aunque modulo no exista."""
        exc, mock_dc = _call_update(
            tmp_path,
            "ghost_mod",
            no_validate=True,
            modulos_disponibles={"sale"},
        )

        assert _exit_code(exc) == 0
        mock_dc.exec_capture.assert_called_once()

    def test_3e_all_mezclado_con_csv_exit_2(self, tmp_path: Path) -> None:
        """3-E: 'odev update sale,all' → exit 2, Odoo no llamado."""
        exc, mock_dc = _call_update(tmp_path, "sale,all")

        assert _exit_code(exc) == 2
        mock_dc.exec_cmd.assert_not_called()
        mock_dc.exec_capture.assert_not_called()

    def test_all_solo_es_aceptado(self, tmp_path: Path) -> None:
        """'all' como token unico → Odoo llamado con -u all."""
        exc, mock_dc = _call_update(tmp_path, "all")

        assert _exit_code(exc) == 0
        mock_dc.exec_capture.assert_called_once()
        cmd = mock_dc.exec_capture.call_args[0][1]
        assert "all" in cmd


# ---------------------------------------------------------------------------
# REQ-4: odev addon-install — CSV support (mirror de REQ-3 con -i)
# ---------------------------------------------------------------------------


class TestAddonInstallCSV:
    """REQ-4: addon-install acepta CSV de modulos con -i flag."""

    def test_4a_single_module_backward_compat(self, tmp_path: Path) -> None:
        """4-A: 'odev addon-install sale' → Odoo llamado con -i sale."""
        exc, mock_dc = _call_install(tmp_path, "sale")

        assert _exit_code(exc) == 0
        mock_dc.exec_capture.assert_called_once()
        cmd = mock_dc.exec_capture.call_args[0][1]
        assert "-i" in cmd
        assert "sale" in cmd

    def test_4b_csv_genera_llamada_unica(self, tmp_path: Path) -> None:
        """4-B: 'odev addon-install sale,crm' → Odoo con -i sale,crm (una invocacion)."""
        exc, mock_dc = _call_install(tmp_path, "sale,crm")

        assert _exit_code(exc) == 0
        mock_dc.exec_capture.assert_called_once()
        cmd = mock_dc.exec_capture.call_args[0][1]
        assert "-i" in cmd
        idx_i = cmd.index("-i")
        assert cmd[idx_i + 1] == "sale,crm"

    def test_4c_modulo_desconocido_exit_2(self, tmp_path: Path) -> None:
        """4-C: addon-install con modulo inexistente → exit 2, Odoo no llamado."""
        exc, mock_dc = _call_install(
            tmp_path,
            "ghost_mod",
            modulos_disponibles={"sale"},
        )

        assert _exit_code(exc) == 2
        mock_dc.exec_cmd.assert_not_called()
        mock_dc.exec_capture.assert_not_called()

    def test_4d_all_mezclado_con_csv_exit_2(self, tmp_path: Path) -> None:
        """4-D: 'odev addon-install sale,all' → exit 2."""
        exc, mock_dc = _call_install(tmp_path, "sale,all")

        assert _exit_code(exc) == 2
        mock_dc.exec_cmd.assert_not_called()
        mock_dc.exec_capture.assert_not_called()

    def test_no_validate_bypassa(self, tmp_path: Path) -> None:
        """--no-validate bypassa validacion en addon-install."""
        exc, mock_dc = _call_install(
            tmp_path,
            "ghost_mod",
            no_validate=True,
            modulos_disponibles={"sale"},
        )

        assert _exit_code(exc) == 0
        mock_dc.exec_capture.assert_called_once()

    def test_usa_flag_i_no_u(self, tmp_path: Path) -> None:
        """addon-install usa -i, NO -u en el comando Odoo."""
        exc, mock_dc = _call_install(tmp_path, "my_mod,other_mod")

        assert _exit_code(exc) == 0
        cmd = mock_dc.exec_capture.call_args[0][1]
        assert "-i" in cmd
        assert "-u" not in cmd

# ---------------------------------------------------------------------------
# 0.7.0 — Modo compacto default en update
# ---------------------------------------------------------------------------


class TestUpdateCompactoDefault:
    """0.7.0: update sin flags captura el output y muestra solo lo relevante."""

    def test_default_captura_sin_interactivo(self, tmp_path: Path) -> None:
        """Sin --verbose, se usa exec_capture; exec_cmd interactivo NO se llama."""
        exc, mock_dc = _call_update(tmp_path, "sale")

        assert _exit_code(exc) == 0
        mock_dc.exec_capture.assert_called_once()
        mock_dc.exec_cmd.assert_not_called()

    def test_default_suprime_log_info(self, tmp_path: Path, capsys) -> None:
        """El log INFO crudo de Odoo no aparece en stdout."""
        exc, _ = _call_update(tmp_path, "sale")

        captured = capsys.readouterr()
        assert "loading 42 modules" not in captured.out

    def test_default_muestra_warnings(self, tmp_path: Path, capsys) -> None:
        """Las lineas WARNING del log si se muestran."""
        exc, _ = _call_update(tmp_path, "sale", capture=(b"", _LOG_WARNING, 0))

        assert _exit_code(exc) == 0
        captured = capsys.readouterr()
        assert "compute_sudo" in captured.out

    def test_default_muestra_success_y_resumen(self, tmp_path: Path, capsys) -> None:
        """Se muestran la linea de exito de Odoo y el resumen de una linea."""
        exc, _ = _call_update(tmp_path, "sale,crm")

        assert _exit_code(exc) == 0
        captured = capsys.readouterr()
        output = captured.out + captured.err
        assert "Modules loaded." in output
        assert "2 modulo(s)" in output

    def test_traceback_con_proceso_cero_sale_1(self, tmp_path: Path, capsys) -> None:
        """Traceback en el log + proceso exit 0 → exit 1 (misma filosofia que test)."""
        exc, _ = _call_update(tmp_path, "sale", capture=(b"", _LOG_TRACEBACK, 0))

        assert _exit_code(exc) == 1
        captured = capsys.readouterr()
        assert "Traceback (most recent call last):" in captured.out
        assert "SyntaxError" in captured.out

    def test_exit_code_proceso_propagado(self, tmp_path: Path) -> None:
        """Proceso Odoo exit 1 → update sale con 1 aunque el log este limpio."""
        exc, _ = _call_update(tmp_path, "sale", capture=(b"", _LOG_OK, 1))

        assert _exit_code(exc) == 1


class TestUpdateVerbose:
    """0.7.0: --verbose restaura el stream interactivo crudo en update."""

    def test_verbose_usa_exec_cmd_interactivo(self, tmp_path: Path) -> None:
        """--verbose → exec_cmd(interactive=True), sin captura ni filtro."""
        exc, mock_dc = _call_update(tmp_path, "sale", verbose=True)

        assert _exit_code(exc) == 0
        mock_dc.exec_cmd.assert_called_once()
        call_args = mock_dc.exec_cmd.call_args
        interactive_value = call_args[1].get("interactive") or (
            len(call_args[0]) > 2 and call_args[0][2]
        )
        assert interactive_value is True
        mock_dc.exec_capture.assert_not_called()


# ---------------------------------------------------------------------------
# 0.7.0 — Modo compacto default en addon-install
# ---------------------------------------------------------------------------


class TestInstallCompactoDefault:
    """0.7.0: addon-install sin flags captura y filtra igual que update."""

    def test_default_captura_sin_interactivo(self, tmp_path: Path) -> None:
        """Sin --verbose, addon-install usa exec_capture."""
        exc, mock_dc = _call_install(tmp_path, "sale")

        assert _exit_code(exc) == 0
        mock_dc.exec_capture.assert_called_once()
        mock_dc.exec_cmd.assert_not_called()

    def test_traceback_con_proceso_cero_sale_1(self, tmp_path: Path) -> None:
        """Traceback + proceso exit 0 → exit 1 en addon-install."""
        exc, _ = _call_install(tmp_path, "sale", capture=(b"", _LOG_TRACEBACK, 0))

        assert _exit_code(exc) == 1

    def test_verbose_usa_exec_cmd_interactivo(self, tmp_path: Path) -> None:
        """--verbose en addon-install → exec_cmd(interactive=True)."""
        exc, mock_dc = _call_install(tmp_path, "sale", verbose=True)

        assert _exit_code(exc) == 0
        mock_dc.exec_cmd.assert_called_once()
        mock_dc.exec_capture.assert_not_called()
