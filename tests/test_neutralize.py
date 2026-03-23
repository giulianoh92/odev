"""Tests para odev.core.neutralize — funciones de neutralizacion de BD.

Verifica que las funciones de neutralizacion ejecuten los comandos
correctos contra los contenedores Docker, usando mocks para evitar
interaccion real con Docker.
"""

from unittest.mock import MagicMock, call, patch

import pytest

from odev.core.neutralize import (
    _validar_nombre_bd,
    _validar_puerto,
    configurar_parametros_desarrollo,
    neutralizar_base_datos,
    resetear_credenciales_admin,
)


@pytest.fixture
def dc_mock():
    """Crea un mock de DockerCompose para tests de neutralizacion."""
    mock = MagicMock()
    mock.exec_cmd.return_value = MagicMock(
        stdout=b"$pbkdf2-sha512$hash_simulado\n",
        returncode=0,
    )
    return mock


class TestNeutralizarBaseDatos:
    """Grupo de tests para neutralizar_base_datos()."""

    def test_ejecuta_odoo_neutralize(self, dc_mock):
        """Ejecuta 'odoo neutralize' en el contenedor web."""
        neutralizar_base_datos(dc_mock, "odoo_db", "odoo")

        dc_mock.exec_cmd.assert_called_once_with(
            "web",
            [
                "odoo", "neutralize",
                "--config=/etc/odoo/odoo.conf",
                "-d", "odoo_db",
            ],
            interactive=True,
        )

    def test_usa_nombre_bd_correcto(self, dc_mock):
        """Usa el nombre de base de datos proporcionado."""
        neutralizar_base_datos(dc_mock, "mi_base_custom", "usuario_custom")

        args = dc_mock.exec_cmd.call_args
        comando = args[0][1]  # segundo argumento posicional (command list)
        assert "-d" in comando
        idx = comando.index("-d")
        assert comando[idx + 1] == "mi_base_custom"


class TestResetearCredencialesAdmin:
    """Grupo de tests para resetear_credenciales_admin()."""

    def test_genera_hash_y_actualiza_usuario(self, dc_mock):
        """Genera un hash de password y actualiza el usuario admin (id=2)."""
        resetear_credenciales_admin(dc_mock, "odoo_db", "odoo")

        assert dc_mock.exec_cmd.call_count == 2

        # Primera llamada: generar hash con passlib
        primera_llamada = dc_mock.exec_cmd.call_args_list[0]
        assert primera_llamada[0][0] == "web"
        assert "python3" in primera_llamada[0][1]

        # Segunda llamada: UPDATE en psql
        segunda_llamada = dc_mock.exec_cmd.call_args_list[1]
        assert segunda_llamada[0][0] == "db"
        comando_psql = segunda_llamada[0][1]
        assert "psql" in comando_psql
        assert "-U" in comando_psql
        assert "odoo" in comando_psql
        assert "-d" in comando_psql
        assert "odoo_db" in comando_psql
        # Verificar que el SQL actualiza res_users donde id = 2
        sql_arg = comando_psql[-1]
        assert "UPDATE res_users" in sql_arg
        assert "id = 2" in sql_arg

    def test_usa_hash_generado_en_update(self, dc_mock):
        """El hash generado por passlib se usa en el UPDATE SQL."""
        hash_esperado = "$pbkdf2-sha512$hash_simulado"
        dc_mock.exec_cmd.return_value = MagicMock(
            stdout=f"{hash_esperado}\n".encode(),
        )

        resetear_credenciales_admin(dc_mock, "odoo_db", "odoo")

        segunda_llamada = dc_mock.exec_cmd.call_args_list[1]
        sql_arg = segunda_llamada[0][1][-1]
        assert hash_esperado in sql_arg


class TestConfigurarParametrosDesarrollo:
    """Grupo de tests para configurar_parametros_desarrollo()."""

    def test_ejecuta_sql_con_parametros_correctos(self, dc_mock):
        """Ejecuta SQL para configurar web.base.url, report.url y web.base.url.freeze."""
        configurar_parametros_desarrollo(dc_mock, "odoo_db", "odoo", "8069")

        dc_mock.exec_cmd.assert_called_once()
        llamada = dc_mock.exec_cmd.call_args
        assert llamada[0][0] == "db"

        comando = llamada[0][1]
        assert "psql" in comando
        assert "-U" in comando
        assert "odoo" in comando
        assert "-d" in comando
        assert "odoo_db" in comando

        sql = comando[-1]
        assert "web.base.url" in sql
        assert "report.url" in sql
        assert "web.base.url.freeze" in sql
        assert "http://localhost:8069" in sql

    def test_usa_puerto_personalizado(self, dc_mock):
        """Usa el puerto web proporcionado en la URL local."""
        configurar_parametros_desarrollo(dc_mock, "odoo_db", "odoo", "9090")

        sql = dc_mock.exec_cmd.call_args[0][1][-1]
        assert "http://localhost:9090" in sql

    def test_puerto_por_defecto_es_8069(self, dc_mock):
        """El puerto por defecto es 8069 si no se especifica."""
        configurar_parametros_desarrollo(dc_mock, "odoo_db", "odoo")

        sql = dc_mock.exec_cmd.call_args[0][1][-1]
        assert "http://localhost:8069" in sql

    def test_sql_usa_upsert(self, dc_mock):
        """El SQL usa INSERT ... ON CONFLICT para ser idempotente."""
        configurar_parametros_desarrollo(dc_mock, "odoo_db", "odoo")

        sql = dc_mock.exec_cmd.call_args[0][1][-1]
        assert "INSERT INTO ir_config_parameter" in sql
        assert "ON CONFLICT" in sql
        assert "DO UPDATE" in sql


class TestValidarNombreBd:
    """Tests para la validacion de nombres de base de datos."""

    def test_nombre_valido_simple(self):
        """Acepta nombres alfanumericos simples."""
        _validar_nombre_bd("odoo_db")

    def test_nombre_valido_con_guiones(self):
        """Acepta nombres con guiones."""
        _validar_nombre_bd("mi-base-datos")

    def test_nombre_valido_con_puntos(self):
        """Acepta nombres con puntos."""
        _validar_nombre_bd("odoo_14.0")

    def test_rechaza_nombre_con_comillas(self):
        """Rechaza nombres con comillas simples (prevencion de SQL injection)."""
        with pytest.raises(ValueError, match="invalido"):
            _validar_nombre_bd("odoo'; DROP TABLE users; --")

    def test_rechaza_nombre_con_espacios(self):
        """Rechaza nombres con espacios."""
        with pytest.raises(ValueError, match="invalido"):
            _validar_nombre_bd("mi base datos")

    def test_rechaza_nombre_vacio(self):
        """Rechaza nombres vacios."""
        with pytest.raises(ValueError, match="invalido"):
            _validar_nombre_bd("")

    def test_rechaza_nombre_con_punto_y_coma(self):
        """Rechaza nombres con punto y coma."""
        with pytest.raises(ValueError, match="invalido"):
            _validar_nombre_bd("odoo;malicious")


class TestValidarPuerto:
    """Tests para la validacion de puertos."""

    def test_puerto_valido(self):
        """Acepta puertos numericos validos."""
        _validar_puerto("8069")

    def test_puerto_minimo(self):
        """Acepta puerto 1 (minimo)."""
        _validar_puerto("1")

    def test_puerto_maximo(self):
        """Acepta puerto 65535 (maximo)."""
        _validar_puerto("65535")

    def test_rechaza_puerto_no_numerico(self):
        """Rechaza puertos con caracteres no numericos."""
        with pytest.raises(ValueError, match="invalido"):
            _validar_puerto("8069; DROP TABLE")

    def test_rechaza_puerto_cero(self):
        """Rechaza puerto 0."""
        with pytest.raises(ValueError, match="fuera de rango"):
            _validar_puerto("0")

    def test_rechaza_puerto_mayor_a_65535(self):
        """Rechaza puertos mayores a 65535."""
        with pytest.raises(ValueError, match="fuera de rango"):
            _validar_puerto("70000")

    def test_rechaza_puerto_vacio(self):
        """Rechaza puertos vacios."""
        with pytest.raises(ValueError, match="invalido"):
            _validar_puerto("")


class TestNeutralizarConInputInvalido:
    """Tests que verifican que las funciones rechazan input invalido."""

    def test_neutralizar_rechaza_nombre_bd_invalido(self, dc_mock):
        """neutralizar_base_datos rechaza nombres de BD con caracteres peligrosos."""
        with pytest.raises(ValueError, match="invalido"):
            neutralizar_base_datos(dc_mock, "db'; DROP TABLE--", "odoo")

    def test_resetear_rechaza_nombre_bd_invalido(self, dc_mock):
        """resetear_credenciales_admin rechaza nombres de BD invalidos."""
        with pytest.raises(ValueError, match="invalido"):
            resetear_credenciales_admin(dc_mock, "db'; DROP TABLE--", "odoo")

    def test_configurar_rechaza_puerto_invalido(self, dc_mock):
        """configurar_parametros_desarrollo rechaza puertos no numericos."""
        with pytest.raises(ValueError, match="invalido"):
            configurar_parametros_desarrollo(dc_mock, "odoo_db", "odoo", "8069; DROP")
