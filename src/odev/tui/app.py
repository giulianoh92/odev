"""Aplicacion principal TUI basada en Textual para el entorno de desarrollo Odoo.

Proporciona un dashboard interactivo en terminal que permite monitorear
el estado de los servicios Docker, ver logs en tiempo real y ejecutar
acciones comunes (up, down, restart, shell, context) mediante atajos
de teclado.

Cambio clave respecto al viejo app.py: Se usa DockerCompose(paths.root)
en lugar del singleton 'dc', y ProjectPaths() en lugar de constantes
globales. Se agrego soporte para paleta de comandos (Ctrl+P), pantalla
de ayuda (?), notificaciones en todas las acciones y el panel de info
de proyecto (ProjectInfoPanel) en lugar de ActionsBar.
"""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.widgets import Footer, Header

from odev.core.config import load_env
from odev.core.docker import DockerCompose
from odev.core.paths import ProjectPaths
from odev.tui.commands import OdevCommandProvider
from odev.tui.screens.help_screen import HelpScreen
from odev.tui.widgets.log_viewer import LogViewer
from odev.tui.widgets.project_info import ProjectInfoPanel
from odev.tui.widgets.status_panel import StatusPanel


class OdooDevApp(App):
    """Aplicacion TUI de Textual para el entorno de desarrollo Odoo.

    Muestra un panel de estado de servicios, un panel de informacion
    del proyecto y un visor de logs en tiempo real. Se comunica con
    Docker Compose a traves del wrapper DockerCompose.

    Attributes:
        CSS_PATH: Ruta relativa al archivo de estilos TCSS.
        TITLE: Titulo por defecto de la aplicacion.
        SUB_TITLE: Subtitulo por defecto.
        BINDINGS: Atajos de teclado disponibles en la interfaz.
        COMMANDS: Proveedores de comandos para la paleta (Ctrl+P).
    """

    CSS_PATH = "styles/app.tcss"

    TITLE = "odev"
    SUB_TITLE = "Entorno de Desarrollo Odoo"

    BINDINGS = [
        Binding("u", "action_up", "Levantar", show=True),
        Binding("d", "action_down", "Detener", show=True),
        Binding("r", "action_restart", "Reiniciar", show=True),
        Binding("s", "action_shell", "Shell", show=True),
        Binding("c", "action_context", "Contexto", show=True),
        Binding("q", "quit", "Salir", show=True),
        Binding("?", "action_help", "Ayuda", show=True),
    ]

    COMMANDS = App.COMMANDS | {OdevCommandProvider}

    def compose(self) -> ComposeResult:
        """Compone el layout principal de la TUI.

        Lee la configuracion del proyecto para mostrar el nombre y la version
        de Odoo en el titulo, y monta los tres paneles principales:
        StatusPanel, ProjectInfoPanel y LogViewer.

        Yields:
            Widgets que conforman la interfaz: Header, paneles y Footer.
        """
        try:
            rutas = ProjectPaths()
            env = load_env(rutas.env_file)
        except FileNotFoundError:
            env = {}

        proyecto = env.get("PROJECT_NAME", "odoo-project")
        version = env.get("ODOO_VERSION", "19.0")

        yield Header()
        yield Horizontal(
            StatusPanel(id="status-panel"),
            ProjectInfoPanel(id="project-info"),
            id="top-row",
        )
        yield Container(
            LogViewer(id="log-viewer"),
            id="bottom-row",
        )
        yield Footer()

        self.title = f"odev — {proyecto}"
        self.sub_title = f"Odoo {version}"

    def on_status_panel_service_selected(self, event: StatusPanel.ServiceSelected) -> None:
        """Redirige la seleccion de servicio al LogViewer.

        Argumentos:
            event: Mensaje ServiceSelected emitido por el StatusPanel.
        """
        try:
            visor = self.query_one("#log-viewer", LogViewer)
            panel = self.query_one("#status-panel", StatusPanel)
            visor.set_servicios_disponibles(panel.get_service_names())
            visor.switch_service(event.service)
        except Exception:
            pass

    def action_up(self) -> None:
        """Ejecuta la accion de levantar los servicios (docker compose up)."""
        self.notify("Levantando servicios...", severity="information")
        self._run_docker_action("up")

    def action_down(self) -> None:
        """Ejecuta la accion de detener los servicios (docker compose stop)."""
        self.notify("Deteniendo servicios...", severity="information")
        self._run_docker_action("down")

    def action_restart(self) -> None:
        """Ejecuta la accion de reiniciar el servicio web."""
        self.notify("Reiniciando servicio web...", severity="information")
        self._run_docker_action("restart")

    def action_shell(self) -> None:
        """Sale de la TUI con codigo 42 para indicar que se debe abrir un shell.

        El codigo de retorno 42 es una convencion que el comando 'tui'
        interpreta para lanzar un shell interactivo externamente.
        """
        self.notify("Abriendo shell...", severity="information")
        self.app.exit(return_code=42)

    def action_context(self) -> None:
        """Ejecuta la generacion del archivo PROJECT_CONTEXT.md."""
        self.notify("Generando contexto del proyecto...", severity="information")
        self._run_docker_action("context")

    def action_help(self) -> None:
        """Muestra la pantalla modal de ayuda con los atajos de teclado."""
        self.push_screen(HelpScreen())

    def _run_docker_action(self, action: str) -> None:
        """Lanza un worker asincrono para ejecutar la accion Docker solicitada.

        Argumentos:
            action: Nombre de la accion a ejecutar ('up', 'down', 'restart', 'context').
        """
        self.run_worker(self._docker_worker(action))

    async def _docker_worker(self, action: str) -> None:
        """Worker asincrono que ejecuta acciones de Docker Compose.

        Instancia DockerCompose con las rutas del proyecto actual y
        ejecuta la accion correspondiente. Tras completar, refresca
        el panel de estado. Notifica al usuario si ocurre algun error.

        Argumentos:
            action: Nombre de la accion a ejecutar.
        """
        try:
            rutas = ProjectPaths()
        except FileNotFoundError:
            self.notify("No se encontro el proyecto odev", severity="error")
            return

        dc = DockerCompose(rutas.root)
        panel_estado = self.query_one("#status-panel", StatusPanel)

        try:
            match action:
                case "up":
                    dc.up()
                    self.notify("Servicios levantados correctamente", severity="information")
                case "down":
                    dc.stop()
                    self.notify("Servicios detenidos correctamente", severity="information")
                case "restart":
                    dc.restart("web")
                    self.notify("Servicio web reiniciado", severity="information")
                case "context":
                    from odev.commands.context import context

                    context()
                    self.notify("Contexto generado correctamente", severity="information")
        except Exception as exc:
            self.notify(f"Error al ejecutar '{action}': {exc}", severity="error")

        panel_estado.refresh_status()
