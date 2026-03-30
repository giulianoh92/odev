"""Visor de logs en tiempo real con seleccion de servicio.

Transmite los logs de docker compose logs en un widget RichLog de
Textual, permitiendo al usuario ver la salida del servidor en vivo.
Soporta cambio de servicio via Tab o por seleccion en el StatusPanel.

Cambio clave respecto al viejo log_viewer.py: Se usa ProjectPaths()
para resolver el directorio raiz del proyecto en lugar de la constante
global PROJECT_ROOT. Ademas se agrego cambio de servicio con gestion
del ciclo de vida del subproceso.
"""

import asyncio
import subprocess

from textual.binding import Binding
from textual.reactive import reactive
from textual.widgets import Label, RichLog, Static

from odev.core.paths import ProjectPaths


class LogViewer(Static):
    """Visor de logs en vivo que transmite la salida de docker compose logs.

    Lanza un subproceso 'docker compose logs -f --tail 50 <servicio>' y
    transmite cada linea al widget RichLog. El proceso se termina
    automaticamente cuando el widget se desmonta o se cambia de servicio.

    Soporta cambio de servicio via Tab (cicla por servicios disponibles)
    o mediante el mensaje ServiceSelected emitido por StatusPanel.

    Attributes:
        _process: Referencia al subproceso de logs, o None si no esta activo.
        _servicios_disponibles: Lista de servicios conocidos del StatusPanel.
        current_service: Servicio actualmente seleccionado para los logs.
    """

    BINDINGS = [Binding("tab", "ciclar_servicio", "Cambiar servicio", show=True)]

    current_service: reactive[str] = reactive("web")

    def compose(self):
        """Compone el widget con una etiqueta de servicio y un RichLog.

        Yields:
            Label con el servicio activo y RichLog configurado.
        """
        yield Label(f"Servicio: {self.current_service}", id="service-label")
        yield RichLog(id="rich-log", highlight=True, markup=True, wrap=True)

    def on_mount(self) -> None:
        """Inicializa el proceso de streaming de logs al montar el widget."""
        self._process: subprocess.Popen | None = None
        self._servicios_disponibles: list[str] = ["web"]
        self.run_worker(self._transmitir_logs(self.current_service), exclusive=True)

    def watch_current_service(self, servicio: str) -> None:
        """Reacciona al cambio de servicio actualizando la etiqueta y el stream.

        Argumentos:
            servicio: Nombre del nuevo servicio seleccionado.
        """
        try:
            etiqueta = self.query_one("#service-label", Label)
            etiqueta.update(f"Servicio: {servicio}")
        except Exception:
            pass

    def action_ciclar_servicio(self) -> None:
        """Cicla al siguiente servicio disponible en la lista."""
        if len(self._servicios_disponibles) <= 1:
            return
        try:
            indice_actual = self._servicios_disponibles.index(self.current_service)
            siguiente = (indice_actual + 1) % len(self._servicios_disponibles)
        except ValueError:
            siguiente = 0
        self.switch_service(self._servicios_disponibles[siguiente])

    def switch_service(self, servicio: str) -> None:
        """Cambia el servicio monitoreado deteniendo el proceso actual.

        Detiene el subproceso activo de forma ordenada (terminate → wait →
        kill si es necesario) y lanza un nuevo worker para el nuevo servicio.

        Argumentos:
            servicio: Nombre del servicio Docker Compose a monitorear.
        """
        self._detener_stream()
        self.current_service = servicio
        try:
            visor_logs = self.query_one("#rich-log", RichLog)
            visor_logs.clear()
            visor_logs.write(f"[dim]Cambiando a servicio: {servicio}[/]")
        except Exception:
            pass
        self.run_worker(self._transmitir_logs(servicio), exclusive=True)

    def set_servicios_disponibles(self, servicios: list[str]) -> None:
        """Actualiza la lista de servicios disponibles para ciclar.

        Argumentos:
            servicios: Lista de nombres de servicios Docker Compose activos.
        """
        if servicios:
            self._servicios_disponibles = servicios

    def _detener_stream(self) -> None:
        """Termina el subproceso de logs activo de forma ordenada.

        Envia SIGTERM y espera hasta 2 segundos. Si el proceso no termina,
        envia SIGKILL. No hace nada si no hay proceso activo.
        """
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

    async def _transmitir_logs(self, servicio: str) -> None:
        """Worker asincrono que transmite los logs de Docker al RichLog.

        Resuelve el directorio raiz del proyecto, lanza un subproceso
        de docker compose logs y lee cada linea de forma asincrona,
        escribiendola en el widget RichLog.

        Si no se encuentra el proyecto o Docker, muestra un mensaje
        de error en el visor de logs.

        Argumentos:
            servicio: Nombre del servicio Docker Compose a monitorear.
        """
        try:
            visor_logs = self.query_one("#rich-log", RichLog)
        except Exception:
            return

        try:
            rutas = ProjectPaths()
            directorio_proyecto = rutas.root
        except FileNotFoundError:
            visor_logs.write("[red]No se encontro un proyecto odev[/]")
            return

        try:
            self._process = subprocess.Popen(
                ["docker", "compose", "logs", "-f", "--tail", "50", servicio],
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
        """Termina el subproceso de logs al desmontar el widget."""
        self._detener_stream()
