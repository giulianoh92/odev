"""Tests para odev.core.docker — wrapper de Docker Compose.

Verifica la deteccion de la version de Docker Compose, la construccion
de comandos y la ejecucion con subprocess mockeado.
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from odev.core.docker import DockerCompose


class TestDetectCommand:
    """Grupo de tests para la deteccion del comando docker compose."""

    def test_detecta_docker_compose_v2(self):
        """Detecta 'docker compose' (v2) cuando esta disponible."""
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0)

            cmd = DockerCompose._detect_command()

        assert cmd == ["docker", "compose"]

    def test_fallback_a_docker_compose_v1(self):
        """Usa 'docker-compose' (v1) cuando v2 no esta disponible."""

        def mock_which(nombre):
            """Simula que docker existe pero docker compose v2 falla."""
            if nombre == "docker":
                return "/usr/bin/docker"
            if nombre == "docker-compose":
                return "/usr/local/bin/docker-compose"
            return None

        with (
            patch("shutil.which", side_effect=mock_which),
            patch("subprocess.run") as mock_run,
        ):
            # docker compose version falla
            mock_run.return_value = MagicMock(returncode=1)

            cmd = DockerCompose._detect_command()

        assert cmd == ["docker-compose"]

    def test_lanza_error_sin_docker(self):
        """Lanza RuntimeError si no hay docker ni docker-compose instalado."""
        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="No se encontro"):
                DockerCompose._detect_command()


class TestDockerComposeRun:
    """Grupo de tests para la ejecucion de comandos con DockerCompose."""

    @pytest.fixture
    def dc(self, tmp_path):
        """Crea una instancia de DockerCompose con mocks."""
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0)
            instancia = DockerCompose(project_root=tmp_path)
        return instancia

    def test_run_usa_cwd_correcto(self, dc, tmp_path):
        """El metodo _run ejecuta comandos con cwd=project_root."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            dc._run(["ps"])

        mock_run.assert_called_once()
        kwargs = mock_run.call_args
        assert kwargs[1]["cwd"] == tmp_path

    def test_up_construye_comando_correcto(self, dc):
        """El metodo up() construye el comando 'up -d' correctamente."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            dc.up()

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "up" in cmd
        assert "-d" in cmd

    def test_up_con_build_agrega_flag(self, dc):
        """El metodo up(build=True) agrega --build al comando."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            dc.up(build=True)

        cmd = mock_run.call_args[0][0]
        assert "--build" in cmd

    def test_up_con_watch_agrega_flag(self, dc):
        """El metodo up(watch=True) agrega --watch al comando."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            dc.up(watch=True)

        cmd = mock_run.call_args[0][0]
        assert "--watch" in cmd

    def test_down_sin_volumes(self, dc):
        """El metodo down() ejecuta 'down' sin -v por defecto."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            dc.down()

        cmd = mock_run.call_args[0][0]
        assert "down" in cmd
        assert "-v" not in cmd

    def test_down_con_volumes(self, dc):
        """El metodo down(volumes=True) agrega -v al comando."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            dc.down(volumes=True)

        cmd = mock_run.call_args[0][0]
        assert "-v" in cmd

    def test_restart_servicio_por_defecto(self, dc):
        """El metodo restart() reinicia 'web' por defecto."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            dc.restart()

        cmd = mock_run.call_args[0][0]
        assert "restart" in cmd
        assert "web" in cmd

    def test_restart_servicio_especifico(self, dc):
        """El metodo restart(service='db') reinicia el servicio indicado."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            dc.restart(service="db")

        cmd = mock_run.call_args[0][0]
        assert "restart" in cmd
        assert "db" in cmd

    def test_ps_retorna_salida(self, dc):
        """El metodo ps() retorna la salida del comando como string."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=b"NAME  STATUS\nweb   running\n",
            )

            resultado = dc.ps()

        assert "web" in resultado
        assert "running" in resultado

    def test_ps_formato_json(self, dc):
        """El metodo ps(format_json=True) agrega --format json."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=b'[{"Name": "web"}]',
            )

            dc.ps(format_json=True)

        cmd = mock_run.call_args[0][0]
        assert "--format" in cmd
        assert "json" in cmd

    def test_stop_ejecuta_comando(self, dc):
        """El metodo stop() ejecuta 'stop'."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            dc.stop()

        cmd = mock_run.call_args[0][0]
        assert "stop" in cmd


class TestDockerComposePsParsed:
    """Grupo de tests para el parseo de la salida JSON de ps."""

    @pytest.fixture
    def dc(self, tmp_path):
        """Crea una instancia de DockerCompose mockeada."""
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0)
            instancia = DockerCompose(project_root=tmp_path)
        return instancia

    def test_parsea_json_array(self, dc):
        """Parsea correctamente una salida JSON como array."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=b'[{"Name": "web", "State": "running"}, {"Name": "db", "State": "running"}]',
            )

            resultado = dc.ps_parsed()

        assert len(resultado) == 2
        assert resultado[0]["Name"] == "web"

    def test_parsea_json_por_linea(self, dc):
        """Parsea correctamente objetos JSON, uno por linea."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=b'{"Name": "web"}\n{"Name": "db"}\n',
            )

            resultado = dc.ps_parsed()

        assert len(resultado) == 2

    def test_retorna_lista_vacia_sin_salida(self, dc):
        """Retorna lista vacia cuando no hay salida."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=b"",
            )

            resultado = dc.ps_parsed()

        assert resultado == []


class TestIsServiceRunning:
    """Tests for DockerCompose.is_service_running()."""

    def test_returns_true_when_running(self):
        """Returns True when service State is 'running'."""
        dc = DockerCompose.__new__(DockerCompose)
        dc.ps_parsed = lambda: [
            {"Service": "db", "State": "running"},
            {"Service": "web", "State": "running"},
        ]
        assert dc.is_service_running("db") is True

    def test_returns_false_when_not_running(self):
        """Returns False when service State is not 'running'."""
        dc = DockerCompose.__new__(DockerCompose)
        dc.ps_parsed = lambda: [
            {"Service": "db", "State": "exited"},
        ]
        assert dc.is_service_running("db") is False

    def test_returns_false_when_service_absent(self):
        """Returns False when service is not in ps output."""
        dc = DockerCompose.__new__(DockerCompose)
        dc.ps_parsed = lambda: []
        assert dc.is_service_running("db") is False


class TestDockerComposeInit:
    """Grupo de tests para la inicializacion de DockerCompose."""

    def test_detecta_project_root_automaticamente(self, tmp_path, monkeypatch):
        """Detecta la raiz del proyecto automaticamente si no se pasa."""
        (tmp_path / ".odev.yaml").write_text("odev_min_version: 0.1.0\n")
        monkeypatch.chdir(tmp_path)

        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0)
            dc = DockerCompose()

        assert dc._project_root == tmp_path


class TestExecCmdValidation:
    """Tests para la validacion de parametros en exec_cmd."""

    @pytest.fixture
    def dc(self, tmp_path):
        """Crea una instancia de DockerCompose mockeada."""
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0)
            instancia = DockerCompose(project_root=tmp_path)
        return instancia

    def test_rechaza_servicio_con_caracteres_invalidos(self, dc):
        """Rechaza nombres de servicio con caracteres peligrosos."""
        with pytest.raises(ValueError, match="invalido"):
            dc.exec_cmd("web; rm -rf /", ["ls"])

    def test_acepta_servicio_valido(self, dc):
        """Acepta nombres de servicio alfanumericos con guiones."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=b"")
            dc.exec_cmd("web", ["ls"])

    def test_acepta_servicio_con_guion_bajo(self, dc):
        """Acepta nombres de servicio con guion bajo."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=b"")
            dc.exec_cmd("my_service", ["ls"])


class TestDockerComposeInitNone:
    """Tests para la validacion de project_root None."""

    def test_lanza_error_si_project_root_es_none(self):
        """Lanza RuntimeError si no se puede detectar el directorio del proyecto."""
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("subprocess.run") as mock_run,
            patch("odev.core.compat.detect_mode", return_value=(None, None)),
        ):
            mock_run.return_value = MagicMock(returncode=0)
            with pytest.raises(RuntimeError, match="No se pudo detectar"):
                DockerCompose()


class TestExecCmdStream:
    """Tests para DockerCompose.exec_cmd_stream() — streaming via Popen."""

    @pytest.fixture
    def dc(self, tmp_path):
        """Crea una instancia de DockerCompose con mocks."""
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0)
            instancia = DockerCompose(project_root=tmp_path)
        return instancia

    def test_construye_comando_con_exec_servicio(self, dc, tmp_path):
        """exec_cmd_stream incluye 'exec <service>' y el comando en el cmd list."""
        mock_popen = MagicMock()
        mock_popen.stdout = MagicMock()
        mock_popen.returncode = 0

        with patch("subprocess.Popen", return_value=mock_popen) as mock_popen_cls:
            result = dc.exec_cmd_stream("web", ["odoo", "--test-enable"])

        call_args = mock_popen_cls.call_args
        cmd = call_args[0][0]
        assert "exec" in cmd
        assert "web" in cmd
        assert "odoo" in cmd
        assert "--test-enable" in cmd
        assert result is mock_popen

    def test_retorna_popen_con_stdout_pipe(self, dc, tmp_path):
        """exec_cmd_stream retorna un Popen con stdout=PIPE y stderr=STDOUT."""
        mock_popen = MagicMock()

        with patch("subprocess.Popen", return_value=mock_popen) as mock_popen_cls:
            dc.exec_cmd_stream("web", ["ls"])

        call_kwargs = mock_popen_cls.call_args[1]
        assert call_kwargs["stdout"] == subprocess.PIPE
        assert call_kwargs["stderr"] == subprocess.STDOUT

    def test_incluye_project_name_cuando_esta_configurado(self, dc, tmp_path):
        """exec_cmd_stream incluye '-p <project_name>' cuando _project_name está configurado."""
        dc._project_name = "mi-proyecto"
        mock_popen = MagicMock()

        with patch("subprocess.Popen", return_value=mock_popen) as mock_popen_cls:
            dc.exec_cmd_stream("web", ["ls"])

        cmd = mock_popen_cls.call_args[0][0]
        assert "-p" in cmd
        idx = cmd.index("-p")
        assert cmd[idx + 1] == "mi-proyecto"

    def test_rechaza_servicio_invalido(self, dc):
        """exec_cmd_stream rechaza nombres de servicio con caracteres peligrosos."""
        with pytest.raises(ValueError, match="invalido"):
            dc.exec_cmd_stream("web; rm -rf /", ["ls"])

    def test_usa_cwd_correcto(self, dc, tmp_path):
        """exec_cmd_stream ejecuta Popen con cwd=project_root."""
        mock_popen = MagicMock()

        with patch("subprocess.Popen", return_value=mock_popen) as mock_popen_cls:
            dc.exec_cmd_stream("web", ["ls"])

        call_kwargs = mock_popen_cls.call_args[1]
        assert call_kwargs["cwd"] == tmp_path


class TestExecCmdFile:
    """Tests para DockerCompose.exec_cmd_file() — stdin streaming desde archivo."""

    @pytest.fixture
    def dc(self, tmp_path):
        """Crea una instancia de DockerCompose con mocks."""
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0)
            instancia = DockerCompose(project_root=tmp_path)
        return instancia

    def test_streams_stdin_from_file(self, dc, tmp_path):
        """Popen es llamado con stdin=file handle y communicate() invocado."""
        dump_file = tmp_path / "dump.sql"
        dump_file.write_bytes(b"SELECT 1;")

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = (b"", b"")

        with patch("odev.core.docker.subprocess.Popen", return_value=mock_proc) as mock_popen:
            result = dc.exec_cmd_file("db", ["psql", "-U", "odoo"], stdin_file=dump_file)

        call_kwargs = mock_popen.call_args[1]
        cmd = mock_popen.call_args[0][0]

        # Popen llamado con exec -T db psql -U odoo en el cmd
        assert "exec" in cmd
        assert "-T" in cmd
        assert "db" in cmd
        assert "psql" in cmd

        # stdin debe ser un file object (no bytes)
        assert hasattr(call_kwargs["stdin"], "read")

        # communicate() debe haber sido invocado
        mock_proc.communicate.assert_called_once()

        # Retorna CompletedProcess con returncode correcto
        assert isinstance(result, subprocess.CompletedProcess)
        assert result.returncode == 0

    def test_returncode_nonzero_propagado_sin_excepcion(self, dc, tmp_path):
        """Un returncode != 0 se propaga en CompletedProcess sin lanzar excepcion."""
        dump_file = tmp_path / "dump.sql"
        dump_file.write_bytes(b"SELECT 1;")

        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate.return_value = (b"", b"ERROR: relation does not exist")

        with patch("odev.core.docker.subprocess.Popen", return_value=mock_proc):
            result = dc.exec_cmd_file("db", ["psql"], stdin_file=dump_file)

        assert result.returncode == 1
        assert not isinstance(result, Exception)

    def test_file_not_found_antes_de_popen(self, dc, tmp_path):
        """FileNotFoundError si el archivo no existe — antes de lanzar Popen."""
        ruta_inexistente = tmp_path / "no_existe.sql"

        with pytest.raises(FileNotFoundError):
            dc.exec_cmd_file("db", ["psql"], stdin_file=ruta_inexistente)

    def test_rechaza_servicio_invalido(self, dc, tmp_path):
        """ValueError para nombres de servicio con caracteres invalidos."""
        dump_file = tmp_path / "dump.sql"
        dump_file.write_bytes(b"x")

        with pytest.raises(ValueError, match="invalido"):
            dc.exec_cmd_file("web; rm -rf /", ["ls"], stdin_file=dump_file)

    def test_incluye_project_name_cuando_configurado(self, dc, tmp_path):
        """El cmd incluye '-p <project_name>' cuando _project_name esta configurado."""
        dc._project_name = "mi-proyecto"
        dump_file = tmp_path / "dump.sql"
        dump_file.write_bytes(b"x")

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = (b"", b"")

        with patch("odev.core.docker.subprocess.Popen", return_value=mock_proc) as mock_popen:
            dc.exec_cmd_file("db", ["psql"], stdin_file=dump_file)

        cmd = mock_popen.call_args[0][0]
        assert "-p" in cmd
        idx = cmd.index("-p")
        assert cmd[idx + 1] == "mi-proyecto"

    def test_usa_cwd_correcto(self, dc, tmp_path):
        """exec_cmd_file ejecuta Popen con cwd=project_root."""
        dump_file = tmp_path / "dump.sql"
        dump_file.write_bytes(b"x")

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = (b"", b"")

        with patch("odev.core.docker.subprocess.Popen", return_value=mock_proc) as mock_popen:
            dc.exec_cmd_file("db", ["psql"], stdin_file=dump_file)

        call_kwargs = mock_popen.call_args[1]
        assert call_kwargs["cwd"] == tmp_path


class TestExecCapture:
    """Tests para DockerCompose.exec_capture() — captura de stdout/stderr sin TTY.

    Spec C1-1 / C1-2 / C1-3 / C1-4.
    """

    @pytest.fixture
    def dc(self, tmp_path):
        """Crea una instancia de DockerCompose mockeada."""
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0)
            instancia = DockerCompose(project_root=tmp_path)
        return instancia

    def test_happy_path_retorna_tupla_stdout(self, dc):
        """exec_capture retorna (stdout_bytes, stderr_bytes, returncode) en caso exitoso.

        Spec C1-1: happy path — valid service and command.
        """
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=b"Odoo 17.0\n",
                stderr=b"",
            )
            resultado = dc.exec_capture("web", ["odoo", "--version"])

        stdout, stderr, rc = resultado
        assert rc == 0
        assert b"Odoo" in stdout
        assert isinstance(stdout, bytes)
        assert isinstance(stderr, bytes)

    def test_codigo_no_cero_no_lanza_excepcion(self, dc):
        """exec_capture no lanza excepcion en codigo de salida no cero.

        Spec C1-2: non-zero exit code — caller receives tuple, no raise.
        """
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout=b"", stderr=b"")
            stdout, stderr, rc = dc.exec_capture("web", ["false"])

        assert rc != 0

    def test_stderr_capturado_independientemente(self, dc):
        """exec_capture devuelve stderr separado de stdout.

        Spec C1-3: command produces stderr output.
        """
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=b"",
                stderr=b"error message\n",
            )
            stdout, stderr, rc = dc.exec_capture("web", ["bash", "-c", "echo err >&2"])

        assert b"error message" in stderr
        assert stdout == b""

    def test_servicio_invalido_lanza_valueerror(self, dc):
        """exec_capture lanza ValueError para servicios con nombre invalido.

        Spec C1-4: invalid service name raises error consistent with exec_cmd.
        """
        with pytest.raises(ValueError, match="invalido"):
            dc.exec_capture("bad service!", ["ls"])
