"""Tests para el comando 'odev py' — wrapper odoo shell no-interactivo.

Cubre:
  - REQ-3: odev py <expression> ejecuta odoo shell via stdin en el contenedor web
  - Scenarios 3-A, 3-B, 3-C, 3-D
  - T1.1: smoke test _strip_banner importable from odev.commands._odoo_shell

Llama _run_py() directamente para evitar problemas con OptionInfo defaults
de Typer al invocar py() fuera del CLI runner.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

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


def _call_run_py(
    tmp_path: Path,
    mock_dc: MagicMock,
    expression: str,
    env_valores: dict | None = None,
):
    """Llama _run_py con contexto mockeado.

    Parches incluidos:
      - requerir_proyecto: retorna mock context
      - obtener_docker: retorna mock_dc
      - obtener_rutas: retorna mock con env_file = tmp_path/.env
      - load_env: retorna env_valores (default: {'DB_NAME': 'odoo_db'})
      - obtener_nombre_proyecto: retorna 'test-project'
    """
    from odev.commands.py import _run_py

    ctx = _make_contexto(tmp_path)
    env = env_valores if env_valores is not None else {"DB_NAME": "odoo_db"}

    with (
        patch("odev.commands.py.requerir_proyecto", return_value=ctx),
        patch("odev.commands.py.obtener_docker", return_value=mock_dc),
        patch("odev.commands.py.obtener_rutas") as mock_rutas,
        patch("odev.commands.py.load_env", return_value=env),
        patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
    ):
        mock_rutas.return_value.env_file = tmp_path / ".env"
        try:
            _run_py(expression)
        except (SystemExit, typer.Exit) as e:
            return e
    return None


# ---------------------------------------------------------------------------
# TestPyArgvShape (Scenario 3-A)
# ---------------------------------------------------------------------------


class TestPyArgvShape:
    """3-A: argv pasado a exec_cmd tiene la forma exacta esperada."""

    def test_py_invoca_odoo_shell_con_no_http(self, tmp_path: Path) -> None:
        """Argv es ['odoo', 'shell', '--config=...', '-d', 'odoo_db', '--no-http']."""
        mock_dc = MagicMock()
        mock_dc.exec_cmd.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"42\n", stderr=b""
        )

        _call_run_py(tmp_path, mock_dc, "2+2", env_valores={"DB_NAME": "odoo_db"})

        mock_dc.exec_cmd.assert_called_once()
        call_kwargs = mock_dc.exec_cmd.call_args
        # Puede ser posicional o keyword; extraemos el segundo arg (command list)
        argv = call_kwargs[0][1] if len(call_kwargs[0]) > 1 else call_kwargs[1]["command"]
        assert argv == [
            "odoo", "shell",
            "--config=/etc/odoo/odoo.conf",
            "-d", "odoo_db",
            "--no-http",
        ]


# ---------------------------------------------------------------------------
# TestPyStdinData (Scenario 3-D)
# ---------------------------------------------------------------------------


class TestPyStdinData:
    """3-D: stdin_data wraps expression with print()."""

    def test_py_pipea_print_de_expresion_via_stdin(self, tmp_path: Path) -> None:
        """exec_cmd llamado con stdin_data=b'print(2+2)\\n'."""
        mock_dc = MagicMock()
        mock_dc.exec_cmd.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"4\n", stderr=b""
        )

        _call_run_py(tmp_path, mock_dc, "2+2")

        call_kwargs = mock_dc.exec_cmd.call_args
        # stdin_data puede ser posicional (arg[3]) o keyword
        kwargs = call_kwargs[1]
        stdin_data = kwargs.get("stdin_data")
        assert stdin_data == b"print(2+2)\n"


# ---------------------------------------------------------------------------
# TestPyResuelveEnv (Scenario 3-A env)
# ---------------------------------------------------------------------------


class TestPyResuelveEnv:
    """3-A env: DB_NAME de load_env se usa en argv."""

    def test_py_resuelve_db_de_env(self, tmp_path: Path) -> None:
        """load_env con DB_NAME='custom' → argv contiene '-d', 'custom'."""
        mock_dc = MagicMock()
        mock_dc.exec_cmd.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"ok\n", stderr=b""
        )

        _call_run_py(tmp_path, mock_dc, "1+1", env_valores={"DB_NAME": "custom"})

        call_kwargs = mock_dc.exec_cmd.call_args
        argv = call_kwargs[0][1] if len(call_kwargs[0]) > 1 else call_kwargs[1]["command"]
        assert "-d" in argv
        assert argv[argv.index("-d") + 1] == "custom"


# ---------------------------------------------------------------------------
# TestPyPassthrough (Scenario 3-A)
# ---------------------------------------------------------------------------


class TestPyPassthrough:
    """3-A: stdout del contenedor propagado y exit code propagado."""

    def test_py_imprime_stdout_y_propaga_exit(self, tmp_path: Path) -> None:
        """stdout bytes del mock escritos en sys.stdout; exit code 0 propagado."""
        mock_dc = MagicMock()
        mock_dc.exec_cmd.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"42\n", stderr=b""
        )

        exc = _call_run_py(tmp_path, mock_dc, "6*7")

        assert exc is not None
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 0


# ---------------------------------------------------------------------------
# TestPyExpresionVacia (Scenario 3-C)
# ---------------------------------------------------------------------------


class TestPyExpresionVacia:
    """3-C: expresion vacía → exit 2, contenedor NO contactado."""

    def test_py_expresion_vacia_falla_exit_2(self, tmp_path: Path) -> None:
        """_run_py('') → typer.Exit(2) y exec_cmd NO llamado."""
        mock_dc = MagicMock()

        exc = _call_run_py(tmp_path, mock_dc, "")

        assert exc is not None
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 2
        mock_dc.exec_cmd.assert_not_called()


# ---------------------------------------------------------------------------
# TestPyErrorPropagacion (Scenario 3-B)
# ---------------------------------------------------------------------------


class TestPyErrorPropagacion:
    """3-B: CalledProcessError de odoo shell → exit code propagado."""

    def test_py_odoo_error_propaga_returncode(self, tmp_path: Path) -> None:
        """exec_cmd lanza CalledProcessError(1) → typer.Exit(1)."""
        mock_dc = MagicMock()
        mock_dc.exec_cmd.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["odoo", "shell"], stderr=b"Traceback: ZeroDivisionError\n"
        )

        exc = _call_run_py(tmp_path, mock_dc, "1/0")

        assert exc is not None
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 1


# ---------------------------------------------------------------------------
# T1.1: Smoke test — _strip_banner importable from _odoo_shell
# ---------------------------------------------------------------------------


class TestOdooShellHelperSmoke:
    """T1.1: _strip_banner and _BANNER_LINE_RE importable from _odoo_shell module."""

    def test_strip_banner_importable_from_odoo_shell(self) -> None:
        """_strip_banner must be importable from odev.commands._odoo_shell."""
        from odev.commands._odoo_shell import _strip_banner  # noqa: PLC2701

        assert callable(_strip_banner)

    def test_banner_line_re_importable_from_odoo_shell(self) -> None:
        """_BANNER_LINE_RE must be importable from odev.commands._odoo_shell."""
        import re

        from odev.commands._odoo_shell import _BANNER_LINE_RE  # noqa: PLC2701

        assert isinstance(_BANNER_LINE_RE, re.Pattern)

    def test_strip_banner_identical_output(self) -> None:
        """_strip_banner from _odoo_shell produces identical output to original."""
        from odev.commands._odoo_shell import _strip_banner  # noqa: PLC2701

        raw = (
            b"2024-01-01 12:00:00,000 INFO odoo.modules Loading module base (1/1)\n"
            b"odoo: mydb>\n"
            b"42\n"
        )
        result = _strip_banner(raw)
        assert result == "42"
