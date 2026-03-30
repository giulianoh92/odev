"""Punto de entrada principal del CLI odev.

Define la aplicacion Typer y registra todos los comandos disponibles.
Este es el modulo referenciado por el entry point del paquete:
    odev = "odev.main:app"
"""

from __future__ import annotations

import typer

from odev import __version__
from odev.commands import (
    context,
    db,
    doctor,
    down,
    install,
    load_backup,
    logs,
    migrate,
    reset_db,
    restart,
    scaffold,
    self_update,
    shell,
    status,
    test,
    tui,
    up,
    update,
)
from odev.commands.init import init as init_command

app = typer.Typer(
    name="odev",
    help="CLI para gestion de entornos de desarrollo Odoo.",
    no_args_is_help=True,
)

# --- Estado global para la opcion --project ---
_nombre_proyecto: str | None = None


def _version_callback(mostrar: bool) -> None:
    """Callback para el flag --version.

    Args:
        mostrar: Si True, imprime la version y termina la ejecucion.
    """
    if mostrar:
        typer.echo(f"odev {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    project: str = typer.Option(
        None,
        "--project",
        "-p",
        help="Nombre del proyecto (si hay ambigüedad).",
    ),
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Muestra la version de odev.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """CLI para gestion de entornos de desarrollo Odoo."""
    global _nombre_proyecto
    _nombre_proyecto = project


def obtener_nombre_proyecto() -> str | None:
    """Retorna el nombre de proyecto global si fue especificado via --project.

    Returns:
        Nombre del proyecto o None si no se especifico.
    """
    return _nombre_proyecto


# --- Registro de comandos ---
app.command()(init_command)
app.command(name="up")(up.up)
app.command(name="down")(down.down)
app.command(name="restart")(restart.restart)
app.command(name="status")(status.status)
app.command(name="logs")(logs.logs)
app.command(name="shell")(shell.shell)
app.command(name="test")(test.test)
app.command(name="scaffold")(scaffold.scaffold)
app.command(name="addon-install")(install.install)
app.command(name="update")(update.update)
app.command(name="reset-db")(reset_db.reset_db)
app.command(name="load-backup")(load_backup.load_backup)
app.command(name="context")(context.context)
app.command(name="tui")(tui.tui)
app.command(name="migrate")(migrate.migrate)
app.command(name="doctor")(doctor.doctor)
app.command(name="self-update")(self_update.self_update)

# --- Registro de subgrupos ---
app.add_typer(db.app, name="db")

# --- Comandos nuevos (a implementar en Batch 5) ---
try:
    from odev.commands.adopt import adopt
    app.command(name="adopt")(adopt)
except ImportError:
    pass

try:
    from odev.commands.projects import app as projects_app
    app.add_typer(projects_app, name="projects")
except ImportError:
    pass

try:
    from odev.commands.addons import app as addons_app
    app.add_typer(addons_app, name="addons", help="Manage shared addons across projects")
except ImportError:
    pass

if __name__ == "__main__":
    app()
