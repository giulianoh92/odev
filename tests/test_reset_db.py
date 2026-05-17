"""Tests para odev.commands.reset_db — reinicio de base de datos.

Verifica que el comando reset-db ejecute la secuencia correcta de
operaciones (down, up, neutralizacion) y que la funcion de espera
funcione correctamente.
"""

from unittest.mock import MagicMock, patch

import pytest
import typer

from odev.commands.reset_db import _esperar_base_datos_lista


class TestEsperarBaseDatosLista:
    """Grupo de tests para _esperar_base_datos_lista()."""

    def test_retorna_inmediatamente_si_tabla_existe(self):
        """Retorna inmediatamente cuando la tabla ir_config_parameter existe."""
        dc_mock = MagicMock()
        dc_mock.exec_cmd.return_value = MagicMock(stdout=b"t\n")

        _esperar_base_datos_lista(dc_mock, "odoo_db", "odoo", intentos=3, intervalo=0)

        # Solo deberia hacer una llamada a exec_cmd
        assert dc_mock.exec_cmd.call_count == 1

    @patch("time.sleep")
    def test_reintenta_hasta_que_tabla_exista(self, mock_sleep):
        """Reintenta varias veces hasta que la tabla exista."""
        dc_mock = MagicMock()
        # Primeras 2 veces no existe, tercera vez si
        dc_mock.exec_cmd.side_effect = [
            MagicMock(stdout=b"f\n"),
            MagicMock(stdout=b"f\n"),
            MagicMock(stdout=b"t\n"),
        ]

        _esperar_base_datos_lista(dc_mock, "odoo_db", "odoo", intentos=5, intervalo=1)

        assert dc_mock.exec_cmd.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("time.sleep")
    def test_lanza_exit_si_agota_intentos(self, mock_sleep):
        """Lanza typer.Exit(1) si se agotan todos los intentos."""
        dc_mock = MagicMock()
        dc_mock.exec_cmd.return_value = MagicMock(stdout=b"f\n")

        with pytest.raises(typer.Exit):
            _esperar_base_datos_lista(dc_mock, "odoo_db", "odoo", intentos=2, intervalo=0)

    @patch("time.sleep")
    def test_maneja_excepciones_de_exec_cmd(self, mock_sleep):
        """Maneja SubprocessError si el contenedor de BD no esta listo.

        Actualizado para usar subprocess.SubprocessError en lugar de Exception
        generico, acorde al expect narrowing de B5 (REQ-UX-1).
        """
        import subprocess as sp

        dc_mock = MagicMock()
        # Primera vez SubprocessError (contenedor no listo), segunda vez ok
        dc_mock.exec_cmd.side_effect = [
            sp.SubprocessError("Container not running"),
            MagicMock(stdout=b"t\n"),
        ]

        _esperar_base_datos_lista(dc_mock, "odoo_db", "odoo", intentos=3, intervalo=0)

        assert dc_mock.exec_cmd.call_count == 2

    @patch("time.sleep")
    def test_maneja_stdout_none(self, mock_sleep):
        """Maneja resultado con stdout None sin fallar."""
        dc_mock = MagicMock()
        dc_mock.exec_cmd.side_effect = [
            MagicMock(stdout=None),
            MagicMock(stdout=b"t\n"),
        ]

        _esperar_base_datos_lista(dc_mock, "odoo_db", "odoo", intentos=3, intervalo=0)

        assert dc_mock.exec_cmd.call_count == 2

    @patch("time.sleep")
    def test_type_error_no_es_silenciado(self, mock_sleep):
        """TypeError dentro del loop NO debe ser silenciado — solo SubprocessError/OSError.

        Verifica REQ-UX-1 (B5): el except debe ser estrecho. Un TypeError (bug de
        programacion) debe propagarse al llamador, no ser swallowed silenciosamente.
        """
        dc_mock = MagicMock()
        # TypeError no es SubprocessError ni OSError — debe propagarse
        dc_mock.exec_cmd.side_effect = TypeError("simulated programming error")

        with pytest.raises(TypeError):
            _esperar_base_datos_lista(dc_mock, "odoo_db", "odoo", intentos=2, intervalo=0)

    def test_consulta_sql_correcta(self):
        """Verifica que la consulta SQL busque ir_config_parameter."""
        dc_mock = MagicMock()
        dc_mock.exec_cmd.return_value = MagicMock(stdout=b"t\n")

        _esperar_base_datos_lista(dc_mock, "odoo_db", "odoo", intentos=1, intervalo=0)

        llamada = dc_mock.exec_cmd.call_args
        comando = llamada[0][1]
        assert "psql" in comando
        assert "-U" in comando
        assert "odoo" in comando
        assert "-d" in comando
        assert "odoo_db" in comando
        # Verificar que usa -tAc para salida limpia
        flag_sql = [c for c in comando if c.startswith("-tAc")]
        assert len(flag_sql) == 1
        # Verificar que la consulta SQL esta incluida
        sql = comando[-1]
        assert "ir_config_parameter" in sql
