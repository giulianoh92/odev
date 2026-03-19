"""Panel de estado de servicios Docker.

Muestra una tabla con el estado actual de los contenedores Docker Compose
del proyecto, actualizandose automaticamente cada 3 segundos mediante
polling.

Cambio clave respecto al viejo status_panel.py: Se instancia
DockerCompose(paths.root) en lugar de importar el singleton 'dc'.
"""

from textual.widgets import DataTable, Static

from odev.core.docker import DockerCompose
from odev.core.paths import ProjectPaths


class StatusPanel(Static):
    """Panel de estado de servicios que consulta docker compose ps periodicamente.

    Muestra una DataTable con tres columnas: Servicio, Estado y Salud.
    Se refresca automaticamente cada 3 segundos y puede refrescarse
    manualmente llamando a refresh_status().
    """

    def compose(self):
        """Compone el widget con una tabla de datos para mostrar el estado.

        Yields:
            DataTable configurada con las columnas de estado.
        """
        yield DataTable(id="status-table")

    def on_mount(self) -> None:
        """Inicializa la tabla con columnas y configura el refresco periodico.

        Agrega las columnas 'Servicio', 'Estado' y 'Salud', realiza una
        consulta inicial y programa un intervalo de 3 segundos para
        actualizaciones automaticas.
        """
        tabla = self.query_one("#status-table", DataTable)
        tabla.add_columns("Servicio", "Estado", "Salud")
        self.refresh_status()
        self.set_interval(3.0, self.refresh_status)

    def refresh_status(self) -> None:
        """Lanza un worker asincrono para actualizar la tabla de estado."""
        self.run_worker(self._actualizar_tabla())

    async def _actualizar_tabla(self) -> None:
        """Worker asincrono que consulta Docker y actualiza las filas de la tabla.

        Intenta obtener el estado de los servicios via DockerCompose.ps_parsed().
        Maneja errores de conexion y el caso de que no haya servicios activos.
        """
        tabla = self.query_one("#status-table", DataTable)
        tabla.clear()

        try:
            rutas = ProjectPaths()
            dc = DockerCompose(rutas.root)
            servicios = dc.ps_parsed()
        except FileNotFoundError:
            tabla.add_row("?", "error", "no se encontro proyecto")
            return
        except Exception:
            tabla.add_row("?", "error", "no se pudo contactar docker")
            return

        if not servicios:
            tabla.add_row("-", "sin servicios", "-")
            return

        for svc in servicios:
            nombre = svc.get("Service", svc.get("Name", "?"))
            estado = svc.get("State", "?")
            salud = svc.get("Health", svc.get("Status", ""))
            tabla.add_row(nombre, estado, str(salud))
