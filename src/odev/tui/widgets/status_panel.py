"""Panel de estado de servicios Docker.

Muestra una tabla con el estado actual de los contenedores Docker Compose
del proyecto, actualizandose automaticamente cada 3 segundos mediante
polling. Emite el mensaje ServiceSelected cuando el usuario selecciona
una fila de la tabla.

Cambio clave respecto al viejo status_panel.py: Se instancia
DockerCompose(paths.root) en lugar de importar el singleton 'dc'.
Ademas se agrego cursor interactivo por fila y emision de mensajes
ServiceSelected para integracion con LogViewer.
"""

from textual.message import Message
from textual.widgets import DataTable, Static

from odev.core.docker import DockerCompose
from odev.core.paths import ProjectPaths


class StatusPanel(Static):
    """Panel de estado de servicios que consulta docker compose ps periodicamente.

    Muestra una DataTable con tres columnas: Servicio, Estado y Salud.
    Se refresca automaticamente cada 3 segundos y puede refrescarse
    manualmente llamando a refresh_status(). Cuando el usuario selecciona
    una fila con Enter, emite ServiceSelected con el nombre del servicio.

    Messages:
        ServiceSelected: Emitido cuando el usuario selecciona un servicio.
    """

    class ServiceSelected(Message):
        """Mensaje emitido cuando el usuario selecciona un servicio en la tabla.

        Attributes:
            service: Nombre del servicio Docker Compose seleccionado.
        """

        def __init__(self, service: str) -> None:
            """Inicializa el mensaje con el nombre del servicio.

            Argumentos:
                service: Nombre del servicio seleccionado.
            """
            self.service = service
            super().__init__()

    def compose(self):
        """Compone el widget con una tabla de datos para mostrar el estado.

        Yields:
            DataTable configurada con cursor por fila y columnas de estado.
        """
        yield DataTable(id="status-table", cursor_type="row")

    def on_mount(self) -> None:
        """Inicializa la tabla con columnas y configura el refresco periodico.

        Agrega las columnas 'Servicio', 'Estado' y 'Salud', realiza una
        consulta inicial y programa un intervalo de 3 segundos para
        actualizaciones automaticas.
        """
        self._tabla = self.query_one("#status-table", DataTable)
        self._tabla.add_columns("Servicio", "Estado", "Salud")
        self._nombres_servicios: list[str] = []
        self.refresh_status()
        self.set_interval(3.0, self.refresh_status)

    def refresh_status(self) -> None:
        """Lanza un worker asincrono para actualizar la tabla de estado."""
        self.run_worker(self._actualizar_tabla())

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Emite ServiceSelected cuando el usuario selecciona una fila.

        Argumentos:
            event: Evento de seleccion de fila de la DataTable.
        """
        indice = event.cursor_row
        if 0 <= indice < len(self._nombres_servicios):
            nombre_servicio = self._nombres_servicios[indice]
            self.post_message(self.ServiceSelected(nombre_servicio))

    def get_service_names(self) -> list[str]:
        """Retorna la lista de nombres de servicios del ultimo sondeo.

        Retorna:
            Lista de strings con los nombres de servicios Docker activos.
        """
        return list(self._nombres_servicios)

    async def _actualizar_tabla(self) -> None:
        """Worker asincrono que consulta Docker y actualiza las filas de la tabla.

        Intenta obtener el estado de los servicios via DockerCompose.ps_parsed().
        Maneja errores de conexion y el caso de que no haya servicios activos.
        Actualiza _nombres_servicios con los nombres obtenidos.
        """
        self._tabla.clear()
        self._nombres_servicios = []

        try:
            rutas = ProjectPaths()
            dc = DockerCompose(rutas.root)
            servicios = dc.ps_parsed()
        except FileNotFoundError:
            self._tabla.add_row("?", "error", "no se encontro proyecto")
            return
        except Exception:
            self._tabla.add_row("?", "error", "no se pudo contactar docker")
            return

        if not servicios:
            self._tabla.add_row("-", "sin servicios", "-")
            return

        for svc in servicios:
            nombre = svc.get("Service", svc.get("Name", "?"))
            estado = svc.get("State", "?")
            salud = svc.get("Health", svc.get("Status", ""))
            self._tabla.add_row(nombre, estado, str(salud))
            self._nombres_servicios.append(nombre)
