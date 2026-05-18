"""Gestion de proyectos odev registrados."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from rich.table import Table

from odev.core.console import console, error, info, success, warning
from odev.core.registry import Registry, RegistryEntry

app = typer.Typer(help="Gestionar proyectos odev registrados.")


def _render_json(proyectos: list[RegistryEntry]) -> str:
    """Serializa la lista de proyectos al esquema JSON documentado.

    Esquema por entrada:
        name (str), path (str), modo (str), odoo_version (str),
        puerto_odoo (int | null), directorio_trabajo (str),
        directorio_config (str), exists (bool).

    Args:
        proyectos: Lista de RegistryEntry del registro.

    Returns:
        JSON serializado con newline final.
    """
    payload = {
        "projects": [
            {
                "name": p.nombre,
                "path": str(p.directorio_trabajo),
                "modo": p.modo,
                "odoo_version": p.version_odoo,
                "puerto_odoo": (p.ports or {}).get("WEB_PORT"),
                "directorio_trabajo": str(p.directorio_trabajo),
                "directorio_config": str(p.directorio_config),
                "exists": (
                    Path(p.directorio_trabajo).exists()
                    if isinstance(p.directorio_trabajo, str)
                    else p.directorio_trabajo.exists()
                ),
            }
            for p in proyectos
        ]
    }
    return json.dumps(payload) + "\n"


def _listar_impl(json_output: bool) -> None:
    """Implementacion compartida del listado de proyectos.

    Delegada tanto por el callback (bare 'odev projects') como por
    el subcomando 'odev projects list'. Fuente unica de verdad.

    Args:
        json_output: Si True, emite JSON a stdout. Si False, tabla Rich.
    """
    registro = Registry()
    proyectos = registro.listar()

    if json_output:
        sys.stdout.write(_render_json(proyectos))
        return

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


@app.callback(invoke_without_command=True)
def listar(
    ctx: typer.Context,
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Emite la lista de proyectos como JSON.",
    ),
) -> None:
    """Lista todos los proyectos odev registrados."""
    if ctx.invoked_subcommand is not None:
        return
    _listar_impl(json_output=json_output)


@app.command(name="list")
def list_proyectos(
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Emite la lista de proyectos como JSON.",
    ),
) -> None:
    """Lista todos los proyectos odev registrados."""
    _listar_impl(json_output=json_output)


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

                if not Confirm.ask(f"Eliminar directorio de configuracion '{config_dir}'?"):
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
