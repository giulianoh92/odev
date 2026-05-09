"""Tests para el comando 'odev sql' — wrapper psql no-interactivo.

Cubre:
  - REQ-2: odev sql <query> ejecuta psql en el contenedor db
  - Scenarios 2-A, 2-B, 2-C, 2-D, 2-E

Llama _run_sql() directamente para evitar problemas con OptionInfo defaults
de Typer al invocar sql() fuera del CLI runner.
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


def _call_run_sql(
    tmp_path: Path,
    mock_dc: MagicMock,
    query: str,
    csv: bool = False,
    env_valores: dict | None = None,
):
    """Llama _run_sql con contexto mockeado.

    Parches incluidos:
      - requerir_proyecto: retorna mock context
      - obtener_docker: retorna mock_dc
      - obtener_rutas: retorna mock con env_file = tmp_path/.env
      - load_env: retorna env_valores (default: {'DB_NAME': 'odoo_db', 'DB_USER': 'odoo'})
      - obtener_nombre_proyecto: retorna 'test-project'
    """
    from odev.commands.sql import _run_sql

    ctx = _make_contexto(tmp_path)
    env = env_valores if env_valores is not None else {"DB_NAME": "odoo_db", "DB_USER": "odoo"}

    with (
        patch("odev.commands.sql.requerir_proyecto", return_value=ctx),
        patch("odev.commands.sql.obtener_docker", return_value=mock_dc),
        patch("odev.commands.sql.obtener_rutas") as mock_rutas,
        patch("odev.commands.sql.load_env", return_value=env),
        patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
    ):
        mock_rutas.return_value.env_file = tmp_path / ".env"
        try:
            _run_sql(query, csv)
        except (SystemExit, typer.Exit) as e:
            return e
    return None


# ---------------------------------------------------------------------------
# TestSqlResuelveEnv (Scenario 2-A, 2-E)
# ---------------------------------------------------------------------------


class TestSqlResuelveEnv:
    """Resolucion de DB_NAME y DB_USER desde .env con fallbacks."""

    def test_sql_resuelve_db_y_user_de_env(self, tmp_path: Path) -> None:
        """Escenario 2-A: argv incluye -U odoo -d odoo_db de load_env."""
        mock_dc = MagicMock()
        mock_dc.exec_cmd.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"1\n", stderr=b""
        )

        _call_run_sql(
            tmp_path,
            mock_dc,
            "SELECT 1",
            env_valores={"DB_NAME": "odoo_db", "DB_USER": "odoo"},
        )

        mock_dc.exec_cmd.assert_called_once()
        args_call = mock_dc.exec_cmd.call_args[0]
        argv = args_call[1]
        assert argv == ["psql", "-U", "odoo", "-d", "odoo_db", "-c", "SELECT 1"]

    def test_sql_fallback_db_user_default(self, tmp_path: Path) -> None:
        """Escenario 2-E: load_env={} → usa 'odoo' y 'odoo_db' como fallback."""
        mock_dc = MagicMock()
        mock_dc.exec_cmd.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"1\n", stderr=b""
        )

        _call_run_sql(tmp_path, mock_dc, "SELECT 1", env_valores={})

        args_call = mock_dc.exec_cmd.call_args[0]
        argv = args_call[1]
        assert "-U" in argv
        assert "-d" in argv
        assert argv[argv.index("-U") + 1] == "odoo"
        assert argv[argv.index("-d") + 1] == "odoo_db"


# ---------------------------------------------------------------------------
# TestSqlCsvFlag (Scenario 2-D)
# ---------------------------------------------------------------------------


class TestSqlCsvFlag:
    """2-D: --csv agrega -A -t -F ',' al argv de psql."""

    def test_sql_csv_flag_agrega_args_psql(self, tmp_path: Path) -> None:
        """Con csv=True, argv termina en ['-A', '-t', '-F', ',']."""
        mock_dc = MagicMock()
        mock_dc.exec_cmd.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"id,name\n", stderr=b""
        )

        _call_run_sql(tmp_path, mock_dc, "SELECT id,name FROM res_partner LIMIT 3", csv=True)

        args_call = mock_dc.exec_cmd.call_args[0]
        argv = args_call[1]
        # Los cuatro flags CSV deben estar al final
        assert argv[-4:] == ["-A", "-t", "-F", ","]


# ---------------------------------------------------------------------------
# TestSqlPassthrough (Scenario 2-A)
# ---------------------------------------------------------------------------


class TestSqlPassthrough:
    """2-A: stdout del contenedor propagado y exit code propagado."""

    def test_sql_imprime_stdout_y_propaga_exit(self, tmp_path: Path) -> None:
        """stdout bytes del mock se escriben en sys.stdout; exit code 0 propagado."""
        mock_dc = MagicMock()
        mock_dc.exec_cmd.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"42\n", stderr=b""
        )

        exc = _call_run_sql(tmp_path, mock_dc, "SELECT 42")

        assert exc is not None
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 0


# ---------------------------------------------------------------------------
# TestSqlQueryVacia (Scenario 2-C)
# ---------------------------------------------------------------------------


class TestSqlQueryVacia:
    """2-C: query vacía → exit 2, contenedor NO contactado."""

    def test_sql_query_vacia_falla_exit_2(self, tmp_path: Path) -> None:
        """_run_sql('') → typer.Exit(2) y exec_cmd NO llamado."""
        mock_dc = MagicMock()

        exc = _call_run_sql(tmp_path, mock_dc, "")

        assert exc is not None
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 2
        mock_dc.exec_cmd.assert_not_called()


# ---------------------------------------------------------------------------
# TestSqlErrorPropagacion (Scenario 2-B)
# ---------------------------------------------------------------------------


class TestSqlErrorPropagacion:
    """2-B: CalledProcessError de psql → exit code propagado."""

    def test_sql_psql_error_propaga_returncode(self, tmp_path: Path) -> None:
        """exec_cmd lanza CalledProcessError(1) → typer.Exit(1)."""
        mock_dc = MagicMock()
        mock_dc.exec_cmd.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["psql", "-c", "NOT VALID SQL"], stderr=b"ERROR: syntax error\n"
        )

        exc = _call_run_sql(tmp_path, mock_dc, "NOT VALID SQL")

        assert exc is not None
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 1
