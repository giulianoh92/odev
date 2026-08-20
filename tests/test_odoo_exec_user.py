"""Tests: every Odoo process runs as the `odoo` user, never as root.

The container starts as root so the entrypoint can apt-install git and
pip-install addon requirements, then drops to `odoo` via setpriv before
exec'ing the server. Any `docker compose exec` therefore lands as ROOT,
and an Odoo run under it creates filestore shards owned by root that the
long-lived server (running as `odoo`) can no longer write into — assets
bundles stop being archived and reports print unstyled.

So: commands that run Odoo must pass `user=USUARIO_ODOO`.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from odev.core.docker import USUARIO_ODOO, DockerCompose

_DEFAULT_ENV = {"DB_NAME": "odoo_db", "DB_USER": "odoo"}


def _make_contexto(tmp_path) -> MagicMock:
    ctx = MagicMock()
    ctx.directorio_config = tmp_path
    ctx.nombre = "test-project"
    ctx.config = MagicMock()
    ctx.config.rutas_addons = None
    return ctx


def _indice_servicio(cmd: list[str], servicio: str) -> int:
    """Posicion del nombre de servicio dentro del comando docker compose."""
    return cmd.index(servicio)


class TestUsuarioOdooConstante:
    """La constante existe y nombra al usuario de la imagen oficial."""

    def test_constante_es_odoo(self):
        """El usuario no-root de la imagen odoo:* se llama 'odoo'."""
        assert USUARIO_ODOO == "odoo"


class TestDockerComposeAceptaUsuario:
    """Los metodos exec_* aceptan `user` y lo traducen a `--user`."""

    @pytest.fixture
    def dc(self, tmp_path):
        """Instancia de DockerCompose con deteccion mockeada."""
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0)
            return DockerCompose(project_root=tmp_path)

    def test_exec_cmd_sin_user_no_agrega_flag(self, dc):
        """Sin `user` el comando queda igual que antes (compatibilidad)."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=b"")
            dc.exec_cmd("web", ["ls"])

        cmd = mock_run.call_args[0][0]
        assert "--user" not in cmd

    def test_exec_cmd_con_user_agrega_flag_antes_del_servicio(self, dc):
        """`--user odoo` va antes del servicio, como exige docker compose exec."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=b"")
            dc.exec_cmd("web", ["odoo", "-i", "base"], user=USUARIO_ODOO)

        cmd = mock_run.call_args[0][0]
        assert "--user" in cmd
        assert cmd[cmd.index("--user") + 1] == "odoo"
        assert cmd.index("--user") < _indice_servicio(cmd, "web")

    def test_exec_capture_con_user(self, dc):
        """exec_capture propaga `user` manteniendo -T."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
            dc.exec_capture("web", ["odoo", "-u", "base"], user=USUARIO_ODOO)

        cmd = mock_run.call_args[0][0]
        assert "-T" in cmd
        assert cmd[cmd.index("--user") + 1] == "odoo"
        assert cmd.index("--user") < _indice_servicio(cmd, "web")

    def test_exec_cmd_stream_con_user(self, dc):
        """exec_cmd_stream propaga `user` al Popen."""
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock()
            dc.exec_cmd_stream("web", ["odoo", "--test-enable"], user=USUARIO_ODOO)

        cmd = mock_popen.call_args[0][0]
        assert cmd[cmd.index("--user") + 1] == "odoo"
        assert cmd.index("--user") < _indice_servicio(cmd, "web")

    def test_exec_cmd_file_con_user(self, dc, tmp_path):
        """exec_cmd_file propaga `user`."""
        archivo = tmp_path / "dump.sql"
        archivo.write_bytes(b"SELECT 1;")
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value.communicate.return_value = (b"", b"")
            mock_popen.return_value.returncode = 0
            dc.exec_cmd_file("web", ["odoo", "shell"], archivo, user=USUARIO_ODOO)

        cmd = mock_popen.call_args[0][0]
        assert cmd[cmd.index("--user") + 1] == "odoo"
        assert cmd.index("--user") < _indice_servicio(cmd, "web")

    def test_rechaza_usuario_con_caracteres_invalidos(self, dc):
        """Un `user` con metacaracteres es rechazado, no interpolado."""
        with pytest.raises(ValueError, match="[Uu]suario"):
            dc.exec_cmd("web", ["ls"], user="odoo; rm -rf /")


class TestInstallYUpdateCorrenComoOdoo:
    """addon-install y update: el Odoo que escribe el filestore no es root."""

    def test_ejecutar_odoo_compacto_usa_usuario_odoo(self):
        """El camino compacto (default) pasa user=odoo a exec_capture."""
        from odev.commands._helpers import ejecutar_odoo_compacto

        dc = MagicMock()
        dc.exec_capture.return_value = (b"Modules loaded.\n", b"", 0)

        ejecutar_odoo_compacto(dc, "web", ["odoo", "-i", "base"], cantidad_modulos=1)

        assert dc.exec_capture.call_args.kwargs.get("user") == USUARIO_ODOO


class TestPyYModelInfoCorrenComoOdoo:
    """odoo shell tambien escribe el filestore (assets, attachments)."""

    def test_execute_py_usa_usuario_odoo(self, tmp_path):
        """_execute_py corre `odoo shell` como odoo."""
        from odev.commands.py import _execute_py

        mock_result = MagicMock(stdout=b"odoo: db>\n42\n", stderr=b"", returncode=0)
        dc = MagicMock()
        dc.exec_cmd.return_value = mock_result

        ctx = _make_contexto(tmp_path)
        with (
            patch("odev.commands.py.obtener_docker", return_value=dc),
            patch("odev.commands.py.obtener_rutas") as mock_rutas,
            patch("odev.commands.py.load_env", return_value=_DEFAULT_ENV),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            _execute_py(ctx, "21+21")

        assert dc.exec_cmd.call_args.kwargs.get("user") == USUARIO_ODOO


class TestNeutralizeCorreComoOdoo:
    """`odoo neutralize` escribe en la base y en el filestore."""

    def test_neutralizar_base_datos_usa_usuario_odoo(self):
        """neutralizar_base_datos pasa user=odoo."""
        from odev.core.neutralize import neutralizar_base_datos

        dc = MagicMock()
        neutralizar_base_datos(dc, "odoo_db", "odoo")

        assert dc.exec_cmd.call_args.kwargs.get("user") == USUARIO_ODOO
