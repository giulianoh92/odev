"""Subgrupo de comandos 'db': operaciones de snapshots y anonimizacion.

Implementa los subcomandos:
  - odev db snapshot <nombre>: crea un snapshot de la base de datos.
  - odev db restore <nombre>: restaura un snapshot.
  - odev db list: lista los snapshots disponibles.
  - odev db anonymize: anonimiza datos personales en la base de datos.
"""

from datetime import datetime
from pathlib import Path

import typer
from rich.table import Table

from odev.commands._helpers import obtener_docker, obtener_rutas, requerir_proyecto
from odev.core.config import load_env
from odev.core.console import console, error, info, success, warning
from odev.core.paths import ProjectPaths, get_sql_templates_dir
from odev.core.resolver import ProjectContext

app = typer.Typer(no_args_is_help=True, help="Operaciones de base de datos (snapshots, anonimizacion).")


def _obtener_info_bd() -> tuple[str, str, ProjectPaths, ProjectContext]:
    """Obtiene la informacion de conexion a la base de datos y las rutas del proyecto.

    Returns:
        Tupla con (usuario_bd, nombre_bd, rutas_proyecto, contexto).

    Raises:
        SystemExit: Si no se encuentra un proyecto odev.
    """
    from odev.main import obtener_nombre_proyecto
    contexto = requerir_proyecto(obtener_nombre_proyecto())
    rutas = obtener_rutas(contexto)

    valores_env = load_env(rutas.env_file)
    return valores_env.get("DB_USER", "odoo"), valores_env.get("DB_NAME", "odoo_db"), rutas, contexto


@app.command()
def snapshot(
    name: str = typer.Argument(..., help="Nombre para el snapshot."),
) -> None:
    """Crea un snapshot de la base de datos (pg_dump).

    Genera un dump en formato custom de PostgreSQL y lo guarda
    en el directorio snapshots/ del proyecto con timestamp.
    """
    usuario_bd, nombre_bd, rutas, contexto = _obtener_info_bd()
    rutas.snapshots_dir.mkdir(parents=True, exist_ok=True)

    dc = obtener_docker(contexto)

    marca_tiempo = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_archivo = f"{name}_{marca_tiempo}.dump"
    ruta_archivo = rutas.snapshots_dir / nombre_archivo

    info(f"Creando snapshot de '{nombre_bd}'...")
    resultado = dc.exec_cmd(
        "db",
        ["pg_dump", "-U", usuario_bd, "-d", nombre_bd, "--format=custom"],
        stdin_data=None,
    )

    if resultado.stdout:
        ruta_archivo.write_bytes(resultado.stdout)
        tamano_mb = ruta_archivo.stat().st_size / (1024 * 1024)
        success(f"Snapshot guardado: {ruta_archivo.name} ({tamano_mb:.1f} MB)")
    else:
        error("El snapshot fallo — no se recibieron datos de pg_dump.")
        raise typer.Exit(1)


@app.command()
def restore(
    name: str = typer.Argument(..., help="Nombre o prefijo del snapshot a restaurar."),
) -> None:
    """Restaura la base de datos desde un snapshot.

    Busca el snapshot por nombre exacto o por prefijo, detiene el
    servicio web, reemplaza la base de datos, y reinicia el servicio.
    """
    usuario_bd, nombre_bd, rutas, contexto = _obtener_info_bd()

    # Buscar archivo de snapshot (coincidencia exacta o por prefijo)
    ruta_archivo = _buscar_snapshot(name, rutas.snapshots_dir)
    if not ruta_archivo:
        error(f"No se encontro ningun snapshot que coincida con '{name}'.")
        raise typer.Exit(1)

    dc = obtener_docker(contexto)

    warning(f"Esto REEMPLAZARA la base de datos '{nombre_bd}' con el snapshot: {ruta_archivo.name}")
    confirmacion = typer.confirm("Continuar?", default=False)
    if not confirmacion:
        info("Operacion cancelada.")
        raise typer.Exit()

    info("Deteniendo servicio web...")
    dc._run(["stop", "web"])

    info(f"Eliminando base de datos '{nombre_bd}'...")
    dc.exec_cmd("db", ["dropdb", "-U", usuario_bd, "--if-exists", nombre_bd])

    info(f"Creando base de datos '{nombre_bd}'...")
    dc.exec_cmd("db", ["createdb", "-U", usuario_bd, nombre_bd])

    info("Restaurando desde snapshot...")
    datos_dump = ruta_archivo.read_bytes()
    dc.exec_cmd(
        "db",
        ["pg_restore", "-U", usuario_bd, "-d", nombre_bd, "--no-owner", "--no-acl"],
        stdin_data=datos_dump,
    )

    info("Iniciando servicio web...")
    dc._run(["start", "web"])

    success(f"Base de datos restaurada desde: {ruta_archivo.name}")


@app.command("list")
def list_snapshots() -> None:
    """Lista los snapshots de base de datos disponibles.

    Muestra una tabla con nombre, fecha y tamano de cada snapshot
    encontrado en el directorio snapshots/ del proyecto.
    """
    from odev.main import obtener_nombre_proyecto
    contexto = requerir_proyecto(obtener_nombre_proyecto())
    rutas = obtener_rutas(contexto)

    rutas.snapshots_dir.mkdir(parents=True, exist_ok=True)
    dumps = sorted(
        rutas.snapshots_dir.glob("*.dump"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not dumps:
        info("No se encontraron snapshots.")
        return

    tabla = Table(title="Snapshots de Base de Datos")
    tabla.add_column("Nombre", style="cyan")
    tabla.add_column("Fecha", style="dim")
    tabla.add_column("Tamano", justify="right")

    for dump in dumps:
        estadisticas = dump.stat()
        fecha = datetime.fromtimestamp(estadisticas.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        tamano_mb = estadisticas.st_size / (1024 * 1024)
        tabla.add_row(dump.stem, fecha, f"{tamano_mb:.1f} MB")

    console.print(tabla)


@app.command()
def anonymize() -> None:
    """Anonimiza datos personales en la base de datos.

    Ejecuta un script SQL que reemplaza nombres, emails, telefonos y
    direcciones de partners con datos ficticios, y resetea las passwords
    de todos los usuarios a 'admin'.
    """
    usuario_bd, nombre_bd, rutas, contexto = _obtener_info_bd()

    dc = obtener_docker(contexto)

    warning("Esto anonimizara los datos de partners y reseteara las passwords de usuarios!")
    confirmacion = typer.confirm("Continuar?", default=False)
    if not confirmacion:
        info("Operacion cancelada.")
        raise typer.Exit()

    archivo_sql = get_sql_templates_dir() / "anonymize.sql"
    if not archivo_sql.exists():
        error(f"No se encontro el script de anonimizacion: {archivo_sql}")
        raise typer.Exit(1)

    datos_sql = archivo_sql.read_bytes()
    info("Ejecutando anonimizacion...")
    dc.exec_cmd("db", ["psql", "-U", usuario_bd, "-d", nombre_bd], stdin_data=datos_sql)

    success("Base de datos anonimizada. Todas las passwords de usuarios se cambiaron a 'admin'.")


def _buscar_snapshot(nombre: str, directorio_snapshots: Path) -> Path | None:
    """Busca un snapshot por nombre exacto, extension o prefijo.

    Args:
        nombre: Nombre, nombre con extension, o prefijo a buscar.
        directorio_snapshots: Directorio donde buscar los snapshots.

    Returns:
        Ruta al snapshot encontrado o None si no hay coincidencia.
    """
    directorio_snapshots.mkdir(parents=True, exist_ok=True)

    # Coincidencia exacta
    exacto = directorio_snapshots / nombre
    if exacto.exists():
        return exacto

    # Con extension .dump
    con_extension = directorio_snapshots / f"{nombre}.dump"
    if con_extension.exists():
        return con_extension

    # Coincidencia por prefijo (retorna el mas reciente)
    coincidencias = sorted(
        directorio_snapshots.glob(f"{nombre}*.dump"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return coincidencias[0] if coincidencias else None
