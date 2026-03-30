"""Subgrupo de comandos 'enterprise': gestionar addons enterprise compartidos.

Implementa los subcomandos:
  - odev enterprise import: importa addons enterprise al almacenamiento compartido.
  - odev enterprise path: muestra la ruta al enterprise compartido para scripting.
  - odev enterprise status: muestra versiones enterprise disponibles y proyectos vinculados.
  - odev enterprise link: vincula el proyecto actual al enterprise compartido.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import typer
import yaml
from rich.table import Table

from odev.commands._helpers import requerir_proyecto
from odev.core.console import console, error, info, success, warning
from odev.core.regen import regenerar_configuracion
from odev.core.registry import ENTERPRISE_DIR, Registry

app = typer.Typer(
    no_args_is_help=True,
    help="Gestionar addons enterprise compartidos de Odoo.",
)


def _version_dir(version: str) -> Path:
    """Retorna el directorio enterprise compartido para una version de Odoo.

    Argumentos:
        version: Version de Odoo (ej. "19.0", "18.0").

    Retorna:
        Path a ~/.odev/enterprise/{version}/.
    """
    return ENTERPRISE_DIR / version


def _contar_modulos(directorio: Path) -> int:
    """Cuenta modulos Odoo en un directorio (subdirs con __manifest__.py).

    Argumentos:
        directorio: Directorio donde buscar modulos.

    Retorna:
        Cantidad de modulos encontrados. 0 si el directorio no existe.
    """
    if not directorio.is_dir():
        return 0
    return sum(
        1
        for d in directorio.iterdir()
        if d.is_dir() and (d / "__manifest__.py").exists()
    )


def _tamano_directorio(directorio: Path) -> float:
    """Calcula el tamano total de un directorio en MB.

    Argumentos:
        directorio: Directorio a medir.

    Retorna:
        Tamano total en MB. 0.0 si el directorio no existe.
    """
    if not directorio.is_dir():
        return 0.0
    total = sum(f.stat().st_size for f in directorio.rglob("*") if f.is_file())
    return total / (1024 * 1024)


@app.command(name="import")
def enterprise_import(
    version: str = typer.Argument(
        ...,
        help="Version de Odoo (ej. 19.0, 18.0).",
    ),
    path: Path = typer.Argument(
        ...,
        help="Ruta al directorio de addons enterprise.",
        exists=True,
        file_okay=False,
    ),
    copy: bool = typer.Option(
        False,
        "--copy",
        help="Copiar archivos en vez de crear symlink (para portabilidad).",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Sobreescribir version enterprise existente.",
    ),
) -> None:
    """Importar addons enterprise al almacenamiento compartido (~/.odev/enterprise/<version>/).

    Por defecto crea un symlink para eficiencia de disco. Usar --copy para
    crear una copia independiente (necesario para CI o si el origen puede moverse).
    """
    destino = _version_dir(version)

    if destino.exists() or destino.is_symlink():
        if not force:
            error(
                f"Ya existen addons enterprise para {version} en {destino}. "
                "Usa --force para sobreescribir."
            )
            raise typer.Exit(1)
        # Limpiar existente
        if destino.is_symlink():
            destino.unlink()
        else:
            shutil.rmtree(destino)
        warning(f"Se elimino enterprise {version} existente.")

    ENTERPRISE_DIR.mkdir(parents=True, exist_ok=True)

    source_resolved = path.resolve()
    n_modulos = _contar_modulos(source_resolved)

    if n_modulos == 0:
        warning(f"No se encontraron modulos Odoo en {source_resolved}. Continuando de todas formas.")

    if copy:
        info(f"Copiando addons enterprise a {destino}...")
        shutil.copytree(source_resolved, destino)
    else:
        info(f"Creando symlink de addons enterprise en {destino}...")
        destino.symlink_to(source_resolved)

    success(f"Enterprise {version}: {n_modulos} modulos almacenados en {destino}")


@app.command(name="path")
def enterprise_path(
    version: str = typer.Argument(
        ...,
        help="Version de Odoo (ej. 19.0).",
    ),
) -> None:
    """Muestra la ruta al enterprise compartido para una version (para scripting).

    Imprime la ruta sin formato Rich para facilitar uso en scripts.
    Sale con codigo 1 si no existe enterprise para esa version.
    """
    destino = _version_dir(version)
    if not destino.exists():
        raise typer.Exit(1)
    # Imprimir ruta cruda para scripting (sin formato Rich)
    typer.echo(str(destino.resolve()))


@app.command(name="status")
def enterprise_status() -> None:
    """Muestra versiones enterprise disponibles y proyectos vinculados."""
    if not ENTERPRISE_DIR.exists():
        info("No se encontraron addons enterprise compartidos.")
        info(f"Importar con: odev enterprise import <version> <ruta>")
        return

    table = Table(title="Addons Enterprise Compartidos")
    table.add_column("Version", style="bold")
    table.add_column("Modulos", justify="right")
    table.add_column("Ruta")
    table.add_column("Tipo")

    versiones = sorted(ENTERPRISE_DIR.iterdir()) if ENTERPRISE_DIR.is_dir() else []
    version_entries = [
        e for e in versiones if e.is_dir() or e.is_symlink()
    ]

    if not version_entries:
        info("No se encontraron versiones enterprise compartidas.")
        return

    for entrada in version_entries:
        n_modulos = _contar_modulos(entrada)
        tipo = "symlink" if entrada.is_symlink() else "copy"
        ruta_real = str(entrada.resolve()) if entrada.is_symlink() else str(entrada)
        table.add_row(entrada.name, str(n_modulos), ruta_real, tipo)

    console.print(table)

    # Mostrar estado enterprise de los proyectos registrados
    registro = Registry()
    proyectos = registro.listar()
    if proyectos:
        info("\nEstado enterprise de los proyectos:")
        for proyecto in proyectos:
            from odev.core.project import ProjectConfig

            try:
                config = ProjectConfig(proyecto.directorio_config)
                if config.enterprise_habilitado:
                    info(f"  {proyecto.nombre}: enterprise={config.ruta_enterprise}")
                else:
                    info(f"  {proyecto.nombre}: enterprise deshabilitado")
            except FileNotFoundError:
                info(f"  {proyecto.nombre}: sin odev.yaml")


@app.command(name="link")
def enterprise_link(
    version: str = typer.Option(
        None,
        "--version",
        help="Version de Odoo a vincular (por defecto: version del proyecto).",
    ),
) -> None:
    """Vincula el proyecto actual al enterprise compartido.

    Actualiza odev.yaml con enterprise.enabled=true y la ruta al enterprise
    compartido, luego regenera docker-compose.yml y odoo.conf.
    """
    from odev.main import obtener_nombre_proyecto

    contexto = requerir_proyecto(obtener_nombre_proyecto())

    if contexto.config is None:
        error("El proyecto no tiene configuracion odev.yaml.")
        raise typer.Exit(1)

    # Resolver version
    if version is None:
        version = contexto.config.version_odoo

    destino = _version_dir(version)
    if not destino.exists():
        error(
            f"No hay addons enterprise compartidos para {version}. "
            f"Importar primero: odev enterprise import {version} /ruta/a/enterprise/"
        )
        raise SystemExit(1)

    # Actualizar odev.yaml (usar la ruta exacta que cargo ProjectConfig)
    ruta_yaml = contexto.config.ruta_archivo
    with open(ruta_yaml, encoding="utf-8") as f:
        datos = yaml.safe_load(f) or {}

    datos.setdefault("enterprise", {})
    datos["enterprise"]["enabled"] = True
    datos["enterprise"]["path"] = str(destino.resolve())

    with open(ruta_yaml, "w", encoding="utf-8") as f:
        yaml.dump(datos, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    success(f"odev.yaml actualizado: enterprise.enabled=true, path={destino}")

    # Regenerar configuracion (delega al motor de regeneracion P1)
    resultado = regenerar_configuracion(contexto)
    if resultado.archivos_regenerados:
        info(f"Se regeneraron {len(resultado.archivos_regenerados)} archivo(s) de configuracion.")
