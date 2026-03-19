"""Punto de entrada principal del CLI odev.

Define la aplicacion Typer y registra todos los comandos disponibles.
Este es el modulo referenciado por el entry point del paquete:
    odev = "odev.main:app"
"""

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

if __name__ == "__main__":
    app()
