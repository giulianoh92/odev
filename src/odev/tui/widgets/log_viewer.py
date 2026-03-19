"""Visor de logs en tiempo real del servicio web de Odoo.

Transmite los logs de docker compose logs en un widget RichLog de
Textual, permitiendo al usuario ver la salida del servidor en vivo.

Cambio clave respecto al viejo log_viewer.py: Se usa ProjectPaths()
para resolver el directorio raiz del proyecto en lugar de la constante
global PROJECT_ROOT.
"""

import asyncio
import subprocess

from textual.widgets import RichLog, Static

from odev.core.paths import ProjectPaths


class LogViewer(Static):
    """Visor de logs en vivo que transmite la salida de docker compose logs.

    Lanza un subproceso 'docker compose logs -f --tail 50 web' y
    transmite cada linea al widget RichLog. El proceso se termina
    automaticamente cuando el widget se desmonta.

    Attributes:
        _process: Referencia al subproceso de logs, o None si no esta activo.
    """

    def compose(self):
        """Compone el widget con un RichLog para mostrar los logs.

        Yields:
            RichLog configurado con highlight, markup y wrap activados.
        """
        yield RichLog(id="rich-log", highlight=True, markup=True, wrap=True)

    def on_mount(self) -> None:
        """Inicializa el proceso de streaming de logs al montar el widget.

        Establece la referencia al subproceso como None y lanza un worker
        asincrono para comenzar a transmitir los logs.
        """
        self._process: subprocess.Popen | None = None
        self.run_worker(self._transmitir_logs())

    async def _transmitir_logs(self) -> None:
        """Worker asincrono que transmite los logs de Docker al RichLog.

        Resuelve el directorio raiz del proyecto, lanza un subproceso
        de docker compose logs y lee cada linea de forma asincrona,
        escribiendola en el widget RichLog.

        Si no se encuentra el proyecto o Docker, muestra un mensaje
        de error en el visor de logs.
        """
        visor_logs = self.query_one("#rich-log", RichLog)

        try:
            rutas = ProjectPaths()
            directorio_proyecto = rutas.root
        except FileNotFoundError:
            visor_logs.write("[red]No se encontro un proyecto odev[/]")
            return

        try:
            self._process = subprocess.Popen(
                ["docker", "compose", "logs", "-f", "--tail", "50", "web"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=directorio_proyecto,
            )
        except FileNotFoundError:
            visor_logs.write("[red]docker compose no encontrado[/]")
            return

        loop = asyncio.get_event_loop()
        while self._process and self._process.poll() is None:
            linea = await loop.run_in_executor(None, self._process.stdout.readline)
            if linea:
                texto = linea.decode("utf-8", errors="replace").rstrip()
                visor_logs.write(texto)
            else:
                await asyncio.sleep(0.1)

    def on_unmount(self) -> None:
        """Termina el subproceso de logs al desmontar el widget.

        Verifica que el proceso exista y siga corriendo antes de
        enviar la senal de terminacion.
        """
        if self._process and self._process.poll() is None:
            self._process.terminate()
