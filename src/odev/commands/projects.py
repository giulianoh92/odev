"""Gestion de proyectos odev registrados."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from odev.core.console import console, error, info, success, warning
from odev.core.registry import Registry

app = typer.Typer(help="Gestionar proyectos odev registrados.")


@app.callback(invoke_without_command=True)
def listar(ctx: typer.Context) -> None:
    """Lista todos los proyectos odev registrados."""
    if ctx.invoked_subcommand is not None:
        return

    registro = Registry()
    proyectos = registro.listar()

    if not proyectos:
        info("No hay proyectos registrados.")
        info("Usa 'odev init' para crear un proyecto o 'odev adopt' para adoptar uno existente.")
        return

    tabla = Table(title="Proyectos odev")
    tabla.add_column("Nombre", style="bold cyan")
    tabla.add_column("Modo", style="dim")
    tabla.add_column("Odoo", style="green")
    tabla.add_column("Directorio de trabajo")
    tabla.add_column("Config")
    tabla.add_column("Estado")

    for p in proyectos:
        # Verificar si el directorio de trabajo todavia existe
        existe = (
            Path(p.directorio_trabajo).exists()
            if isinstance(p.directorio_trabajo, str)
            else p.directorio_trabajo.exists()
        )
        estado = "[green]OK[/green]" if existe else "[red]no existe[/red]"

        tabla.add_row(
            p.nombre,
            p.modo,
            p.version_odoo,
            str(p.directorio_trabajo),
            str(p.directorio_config),
            estado,
        )

    console.print(tabla)


@app.command(name="remove")
def eliminar(
    nombre: str = typer.Argument(..., help="Nombre del proyecto a eliminar"),
    delete_config: bool = typer.Option(
        False, "--delete-config", help="Tambien eliminar archivos de configuracion"
    ),
    force: bool = typer.Option(False, "--force", "-f", help="No pedir confirmacion"),
) -> None:
    """Elimina un proyecto del registro de odev."""
    registro = Registry()
    entry = registro.obtener(nombre)

    if entry is None:
        error(f"No se encontro el proyecto '{nombre}' en el registro.")
        raise SystemExit(1)

    if not force:
        from rich.prompt import Confirm

        if not Confirm.ask(f"Eliminar proyecto '{nombre}' del registro?"):
            return

    registro.eliminar(nombre)
    success(f"Proyecto '{nombre}' eliminado del registro.")

    if delete_config and entry.modo == "external":
        import shutil

        config_dir = (
            Path(entry.directorio_config)
            if isinstance(entry.directorio_config, str)
            else entry.directorio_config
        )
        if config_dir.exists():
            if not force:
                from rich.prompt import Confirm

                if not Confirm.ask(
                    f"Eliminar directorio de configuracion '{config_dir}'?"
                ):
                    return
            shutil.rmtree(config_dir)
            success(f"Directorio de configuracion eliminado: {config_dir}")
    elif delete_config and entry.modo == "inline":
        warning(
            "No se eliminan archivos de configuracion para proyectos inline "
            "(estan dentro del proyecto)."
        )


@app.command(name="clean")
def limpiar() -> None:
    """Elimina del registro proyectos cuyos directorios ya no existen."""
    registro = Registry()
    eliminados = registro.limpiar_obsoletos()

    if eliminados:
        for nombre in eliminados:
            success(f"Eliminado proyecto obsoleto: {nombre}")
        info(f"Total eliminados: {len(eliminados)}")
    else:
        info("No se encontraron proyectos obsoletos.")
