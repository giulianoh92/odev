"""Panel de informacion del proyecto Odoo activo.

Muestra el nombre del proyecto, la version de Odoo, los puertos
configurados y si el modo enterprise esta activo. Lee la configuracion
desde el archivo .env del proyecto via load_env().
"""

from textual.widgets import Static

from odev.core.config import load_env
from odev.core.paths import ProjectPaths


class ProjectInfoPanel(Static):
    """Panel estatico que muestra la informacion clave del proyecto Odoo.

    Lee el archivo .env del proyecto al montarse y renderiza el nombre
    del proyecto, la version de Odoo, el puerto HTTP, el puerto de
    longpolling y si el modo enterprise esta activado.

    Usa valores por defecto descriptivos cuando alguna variable no
    esta definida en el .env.
    """

    def on_mount(self) -> None:
        """Carga la configuracion del proyecto y actualiza el panel al montar."""
        self._actualizar_info()

    def _actualizar_info(self) -> None:
        """Lee el .env y compone el markup con la informacion del proyecto."""
        try:
            rutas = ProjectPaths()
            env = load_env(rutas.env_file)
        except FileNotFoundError:
            env = {}

        nombre = env.get("PROJECT_NAME") or "odoo-project"
        version = env.get("ODOO_VERSION") or "19.0"
        puerto_http = env.get("PORT_HTTP") or env.get("HTTP_PORT") or "8069"
        puerto_longpoll = env.get("PORT_LONGPOLL") or env.get("LONGPOLL_PORT") or "8072"
        enterprise = env.get("ENTERPRISE", "").lower() in ("1", "true", "yes", "on")

        modo_enterprise = "[green]Enterprise[/]" if enterprise else "[dim]Community[/]"

        contenido = (
            f"[bold]{nombre}[/]\n\n"
            f"[cyan]Odoo[/] {version}\n"
            f"[cyan]HTTP[/] :{puerto_http}  "
            f"[cyan]Poll[/] :{puerto_longpoll}\n"
            f"[cyan]Modo[/] {modo_enterprise}"
        )

        self.update(contenido)
