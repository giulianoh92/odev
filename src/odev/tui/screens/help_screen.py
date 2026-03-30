"""Pantalla de ayuda con todos los atajos de teclado disponibles.

Muestra un overlay modal con la tabla completa de keybindings
de la aplicacion. Se activa con la tecla '?' y se cierra con
Escape, 'q' o '?'.
"""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import DataTable, Label, Static


class HelpScreen(ModalScreen):
    """Pantalla modal que muestra todos los atajos de teclado disponibles.

    Se superpone sobre la aplicacion principal mostrando una tabla
    de keybindings organizada con descripcion de cada accion.

    Attributes:
        BINDINGS: Atajos para cerrar la pantalla de ayuda.
    """

    BINDINGS = [Binding("escape,q,?", "dismiss", "Cerrar")]

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }

    #help-container {
        width: 60;
        height: auto;
        border: solid $primary;
        padding: 1 2;
        background: $surface;
    }

    #help-titulo {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    #help-table {
        height: auto;
        margin-top: 1;
    }

    #help-footer {
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Compone la pantalla de ayuda con la tabla de atajos.

        Yields:
            Contenedor con titulo, tabla de keybindings y nota de cierre.
        """
        with Container(id="help-container"):
            yield Label("Atajos de Teclado — odev TUI", id="help-titulo")
            tabla = DataTable(id="help-table", show_cursor=False)
            tabla.add_columns("Tecla", "Accion", "Descripcion")
            tabla.add_rows([
                ("u", "Levantar", "docker compose up -d"),
                ("d", "Detener", "docker compose stop"),
                ("r", "Reiniciar", "Reiniciar servicio web"),
                ("s", "Shell", "Abrir shell interactivo"),
                ("c", "Contexto", "Generar PROJECT_CONTEXT.md"),
                ("q", "Salir", "Cerrar la aplicacion"),
                ("?", "Ayuda", "Mostrar esta pantalla"),
                ("Ctrl+P", "Paleta", "Abrir paleta de comandos"),
                ("Tab", "Servicio", "Ciclar servicio en logs"),
                ("Escape", "Cerrar", "Cerrar pantalla modal"),
            ])
            yield tabla
            yield Static("[dim]Presiona Escape, q o ? para cerrar[/]", id="help-footer")
