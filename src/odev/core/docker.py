"""Wrapper de docker compose con soporte para multiples proyectos.

Encapsula la interaccion con Docker Compose, detectando automaticamente
si usar 'docker compose' (v2) o 'docker-compose' (v1 legacy). Cada
instancia opera sobre un project_root especifico, eliminando el patron
instancia unica global del viejo docker.py.

Cambio clave: Se elimina la instancia unica global `dc = DockerCompose()` que se
evaluaba al importar. Ahora cada comando instancia su propio
DockerCompose con el project_root correcto.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from odev.core.resolver import ProjectContext


class DockerCompose:
    """Wrapper de docker compose con soporte para multiples proyectos.

    Atributos:
        _cmd: Comando base detectado (['docker', 'compose'] o ['docker-compose']).
        _project_root: Directorio raiz del proyecto donde se ejecutan los comandos.
    """

    _PATRON_SERVICIO = re.compile(r"^[a-zA-Z0-9_-]+$")

    def __init__(self, project_root: Path | None = None) -> None:
        """Inicializa el wrapper de Docker Compose.

        Argumentos:
            project_root: Directorio raiz del proyecto. Si es None, se detecta
                         automaticamente usando detect_mode().

        Lanza:
            RuntimeError: Si no se encuentra Docker ni docker-compose instalado.
        """
        self._cmd = self._detect_command()
        # Si no se pasa project_root, se detecta automaticamente
        if project_root is None:
            from odev.core.compat import detect_mode

            _, project_root = detect_mode()
        if project_root is None:
            raise RuntimeError(
                "No se pudo detectar el directorio del proyecto. "
                "Ejecuta 'odev init' para crear un proyecto o 'odev adopt' para adoptar uno existente."
            )
        self._project_root = project_root
        self._project_name: str | None = None

    @classmethod
    def from_context(cls, contexto: ProjectContext) -> DockerCompose:
        """Crea una instancia de DockerCompose desde un ProjectContext.

        Para proyectos EXTERNAL, establece el nombre del proyecto Docker
        Compose para garantizar aislamiento de volumenes entre proyectos.

        Argumentos:
            contexto: Contexto del proyecto resuelto.

        Retorna:
            Instancia de DockerCompose configurada segun el contexto.
        """
        from odev.core.resolver import ModoProyecto

        instancia = cls(contexto.directorio_config)
        if contexto.modo == ModoProyecto.EXTERNAL:
            instancia._project_name = contexto.nombre
        return instancia

    @staticmethod
    def _detect_command() -> list[str]:
        """Detecta si usar 'docker compose' (v2) o 'docker-compose' (v1).

        Retorna:
            Lista con el comando base a usar.

        Lanza:
            RuntimeError: Si no se encuentra ninguna version de docker compose.
        """
        if shutil.which("docker"):
            resultado = subprocess.run(
                ["docker", "compose", "version"],
                capture_output=True,
                text=True,
            )
            if resultado.returncode == 0:
                return ["docker", "compose"]
        if shutil.which("docker-compose"):
            return ["docker-compose"]
        raise RuntimeError(
            "No se encontro 'docker compose' ni 'docker-compose'. "
            "Por favor instala Docker."
        )

    def _run(
        self,
        args: list[str],
        capture: bool = False,
        check: bool = True,
        input_data: bytes | None = None,
    ) -> subprocess.CompletedProcess:
        """Ejecuta un comando de docker compose.

        Argumentos:
            args: Argumentos para docker compose (ej. ['up', '-d']).
            capture: Si True, captura stdout y stderr.
            check: Si True, lanza excepcion si el comando falla.
            input_data: Datos para enviar por stdin al proceso.

        Retorna:
            Resultado de la ejecucion del subproceso.
        """
        cmd = [*self._cmd]
        if self._project_name:
            cmd.extend(["-p", self._project_name])
        cmd.extend(args)
        return subprocess.run(
            cmd,
            cwd=self._project_root,
            capture_output=capture,
            check=check,
            input=input_data,
        )

    def _exec(
        self,
        args: list[str],
        interactive: bool = False,
    ) -> subprocess.CompletedProcess:
        """Ejecuta un comando, opcionalmente de forma interactiva.

        Para comandos interactivos (como logs -f o shell), se usa
        subprocess.run sin captura para permitir la interaccion del usuario.

        Argumentos:
            args: Argumentos para docker compose.
            interactive: Si True, permite interaccion directa del usuario.

        Retorna:
            Resultado de la ejecucion del subproceso.
        """
        cmd = [*self._cmd]
        if self._project_name:
            cmd.extend(["-p", self._project_name])
        cmd.extend(args)
        if interactive:
            sys.stdout.flush()
            sys.stderr.flush()
            return subprocess.run(cmd, cwd=self._project_root)
        return subprocess.run(cmd, cwd=self._project_root, check=True)

    def up(self, build: bool = False, watch: bool = False) -> None:
        """Levanta los servicios de docker compose en modo detached.

        Argumentos:
            build: Si True, reconstruye las imagenes antes de levantar.
            watch: Si True, activa el modo watch para recarga en caliente.
        """
        args = ["up", "-d"]
        if build:
            args.append("--build")
        if watch:
            args.append("--watch")
        self._run(args)

    def down(self, volumes: bool = False) -> None:
        """Detiene y elimina los contenedores del proyecto.

        Argumentos:
            volumes: Si True, tambien elimina los volumenes asociados.
        """
        args = ["down"]
        if volumes:
            args.append("-v")
        self._run(args)

    def stop(self) -> None:
        """Detiene los contenedores sin eliminarlos."""
        self._run(["stop"])

    def restart(self, service: str = "web") -> None:
        """Reinicia un servicio especifico.

        Argumentos:
            service: Nombre del servicio a reiniciar (por defecto 'web').
        """
        self._run(["restart", service])

    def ps(self, format_json: bool = False) -> str:
        """Lista el estado de los servicios.

        Argumentos:
            format_json: Si True, retorna la salida en formato JSON.

        Retorna:
            Salida del comando docker compose ps como string.
        """
        args = ["ps"]
        if format_json:
            args.extend(["--format", "json"])
        resultado = self._run(args, capture=True)
        return resultado.stdout.decode() if resultado.stdout else ""

    def ps_parsed(self) -> list[dict]:
        """Retorna el estado de los servicios como lista de diccionarios.

        Parsea la salida JSON de docker compose ps, manejando tanto
        la salida como un array JSON como objetos JSON por linea.

        Retorna:
            Lista de diccionarios con la informacion de cada servicio.
        """
        salida_cruda = self.ps(format_json=True).strip()
        if not salida_cruda:
            return []
        try:
            return json.loads(salida_cruda)
        except json.JSONDecodeError:
            # docker compose puede emitir un objeto JSON por linea
            resultados = []
            for linea in salida_cruda.splitlines():
                linea = linea.strip()
                if linea:
                    try:
                        resultados.append(json.loads(linea))
                    except json.JSONDecodeError:
                        continue
            return resultados

    def logs(self, service: str | None = None, follow: bool = True, tail: int = 100) -> None:
        """Muestra los logs de los servicios.

        Argumentos:
            service: Servicio especifico del cual ver logs. Si es None, muestra todos.
            follow: Si True, sigue los logs en tiempo real.
            tail: Numero de lineas a mostrar desde el final.
        """
        args = ["logs"]
        if follow:
            args.append("-f")
        args.extend(["--tail", str(tail)])
        if service:
            args.append(service)
        self._exec(args, interactive=True)

    def exec_cmd(
        self,
        service: str,
        command: list[str],
        interactive: bool = False,
        stdin_data: bytes | None = None,
    ) -> subprocess.CompletedProcess:
        """Ejecuta un comando dentro de un contenedor en ejecucion.

        Argumentos:
            service: Nombre del servicio donde ejecutar el comando.
            command: Comando y sus argumentos a ejecutar.
            interactive: Si True, permite interaccion directa del usuario.
            stdin_data: Datos para enviar por stdin al contenedor.

        Retorna:
            Resultado de la ejecucion del subproceso.
        """
        if not self._PATRON_SERVICIO.match(service):
            raise ValueError(
                f"Nombre de servicio invalido: '{service}'. "
                "Solo se permiten letras, numeros, guiones y guiones bajos."
            )
        args = ["exec"]
        if stdin_data is not None:
            args.append("-T")
        args.extend([service, *command])
        if interactive:
            return self._exec(args, interactive=True)
        return self._run(args, capture=True, input_data=stdin_data)

    def get_container_name(self, service: str) -> str | None:
        """Busca dinamicamente el nombre del contenedor para un servicio.

        Argumentos:
            service: Nombre del servicio cuyo contenedor se busca.

        Retorna:
            Nombre del contenedor o None si no se encuentra.
        """
        resultado = self._run(["ps", "-q", service], capture=True, check=False)
        container_id = resultado.stdout.decode().strip() if resultado.stdout else ""
        if not container_id:
            return None
        inspeccion = subprocess.run(
            ["docker", "inspect", "--format", "{{.Name}}", container_id],
            capture_output=True,
            text=True,
        )
        return inspeccion.stdout.strip().lstrip("/") if inspeccion.returncode == 0 else None
