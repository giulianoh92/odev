"""Comando 'tui': lanza el dashboard interactivo de Textual.

Inicia la aplicacion TUI que muestra el estado de los servicios Docker,
un visor de logs en tiempo real y permite ejecutar acciones comunes
mediante atajos de teclado.
"""

import typer

from odev.core.console import error


def tui() -> None:
    """Abre el dashboard interactivo TUI para monitorear el entorno de desarrollo.

    Lanza la aplicacion Textual con un panel de estado de servicios,
    barra de acciones rapidas y visor de logs en tiempo real.

    Si la TUI sale con codigo 42, se interpreta como una solicitud
    para abrir un shell interactivo en el contenedor web.
    """
    try:
        from odev.tui.app import OdooDevApp
    except ImportError:
        error(
            "Textual no esta instalado. Instala las dependencias TUI con: "
            "pip install 'odev[tui] @ git+https://github.com/giulianoh92/odev.git'"
        )
        raise typer.Exit(1)

    aplicacion = OdooDevApp()
    resultado = aplicacion.run()

    # Si la TUI sale con codigo 42, abrir shell interactivo
    if resultado == 42:
        from odev.core.docker import DockerCompose
        from odev.core.paths import ProjectPaths

        try:
            rutas = ProjectPaths()
            dc = DockerCompose(rutas.root)
            dc.exec_cmd("web", ["bash"], interactive=True)
        except FileNotFoundError:
            error("No se encontro un proyecto odev para abrir el shell.")
            raise typer.Exit(1)
