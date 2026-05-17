"""Comando 'load-backup': carga un backup de Odoo.sh en el entorno local.

Acepta un archivo .zip con un dump PostgreSQL y opcionalmente un filestore.
Reemplaza la base de datos actual, restaura el filestore, y opcionalmente
neutraliza la base de datos.
"""

import re
import subprocess
import tempfile
import zipfile
from pathlib import Path

import typer

from odev.commands._helpers import obtener_docker, obtener_rutas, requerir_proyecto
from odev.core.config import load_env
from odev.core.console import error, info, success, warning
from odev.core.neutralize import (
    configurar_parametros_desarrollo,
    neutralizar_base_datos,
    resetear_credenciales_admin,
)

# Error codes for load-backup validation failures
LOAD_BACKUP_UNSAFE_MEMBER = "LOAD_BACKUP_UNSAFE_MEMBER"
LOAD_BACKUP_INVALID_DB_NAME = "LOAD_BACKUP_INVALID_DB_NAME"


def _validar_miembros_zip(zf: zipfile.ZipFile, destino: Path) -> None:
    """Valida que todos los miembros del ZIP esten dentro del directorio destino.

    Itera todos los miembros del archivo ZIP y verifica que su ruta resuelta
    sea un subdirectorio (o el mismo directorio) del destino. Rechaza cualquier
    intento de path traversal (../../, rutas absolutas, etc.).

    Argumentos:
        zf: El objeto ZipFile abierto a validar.
        destino: El directorio de extraccion destino (Path absoluto).

    Raises:
        typer.BadParameter: Si algun miembro tiene una ruta que escapa al destino.
            El mensaje incluye el codigo LOAD_BACKUP_UNSAFE_MEMBER.
    """
    destino_resuelto = destino.resolve()
    for miembro in zf.infolist():
        nombre = miembro.filename
        # Early-exit: rutas absolutas o con componentes '..' son siempre inseguras
        if nombre.startswith("/") or ".." in Path(nombre).parts:
            raise typer.BadParameter(
                f"{LOAD_BACKUP_UNSAFE_MEMBER}: '{nombre}' escapa al directorio de extraccion."
            )
        ruta_final = (destino / nombre).resolve()
        try:
            ruta_final.relative_to(destino_resuelto)
        except ValueError:
            raise typer.BadParameter(
                f"{LOAD_BACKUP_UNSAFE_MEMBER}: '{nombre}' escapa al directorio de extraccion."
            )


def load_backup(
    backup: Path = typer.Argument(
        ...,
        help="Ruta al backup de Odoo (.zip con dump.sql + filestore/).",
        exists=True,
        readable=True,
    ),
    neutralize: bool = typer.Option(
        True,
        help="Neutralizar la base de datos (desactivar crons, correo, etc.).",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt (for automation/CI).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Previsualizar operaciones sin ejecutarlas.",
    ),
) -> None:
    """Carga un backup de Odoo.sh (o el Gestor de Base de Datos) en el entorno local.

    Acepta un archivo .zip que contenga un dump de PostgreSQL y un
    directorio filestore opcional. Elimina la base de datos actual,
    restaura el dump, copia el filestore en el volumen de datos de Odoo,
    y opcionalmente neutraliza la base de datos para que no envie correos
    ni ejecute acciones programadas.
    """
    from odev.main import obtener_nombre_proyecto

    contexto = requerir_proyecto(obtener_nombre_proyecto())
    rutas = obtener_rutas(contexto)

    valores_env = load_env(rutas.env_file)
    usuario_bd = valores_env.get("DB_USER", "odoo")
    nombre_bd = valores_env.get("DB_NAME", "odoo_db")

    # Validar nombre de BD con regex estricto (REQ-LB-2 / S2).
    # Acepta solo identificadores PostgreSQL simples: [a-zA-Z_][a-zA-Z0-9_]*
    # Rechaza puntos, guiones, digitos al inicio y caracteres especiales.
    # TODO 1.0: migrate to psycopg2.sql.Identifier for full parameterization
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", nombre_bd):
        error(
            f"{LOAD_BACKUP_INVALID_DB_NAME}: Nombre de base de datos invalido: '{nombre_bd}'. "
            "Solo se permiten letras, digitos y guion bajo, comenzando con letra o guion bajo."
        )
        raise typer.Exit(1)

    dc = obtener_docker(contexto)

    # Pre-flight: verify db container is running
    if not dc.is_service_running("db"):
        error("El servicio de base de datos no esta corriendo. Ejecuta 'odev up' primero.")
        raise typer.Exit(1)

    # -- Validar backup -------------------------------------------------------
    if not zipfile.is_zipfile(backup):
        error("El archivo no es un archivo .zip valido.")
        raise typer.Exit(1)

    with zipfile.ZipFile(backup) as zf:
        nombres = zf.namelist()

    # Los backups de Odoo.sh contienen dump.sql en la raiz; el Gestor de Base de Datos
    # puede usar dump.sql o un dump en formato custom.
    nombre_dump = None
    for candidato in ("dump.sql", "dump.dump"):
        if candidato in nombres:
            nombre_dump = candidato
            break
    if not nombre_dump:
        error("No se encontro dump.sql ni dump.dump dentro del .zip.")
        raise typer.Exit(1)

    tiene_filestore = any(n.startswith("filestore/") for n in nombres)
    es_formato_custom = nombre_dump.endswith(".dump")

    tamano_mb = backup.stat().st_size / (1024 * 1024)
    info(f"Backup: {backup.name} ({tamano_mb:.1f} MB)")
    info(f"  Dump: {nombre_dump} ({'custom' if es_formato_custom else 'SQL'})")
    info(f"  Filestore: {'si' if tiene_filestore else 'no'}")

    if dry_run:
        info("Modo --dry-run: no se ejecutara ninguna operacion.")
        info(f"  Se restauraria dump: {nombre_dump}")
        info(f"  Sobre base de datos: {nombre_bd}")
        info(f"  Filestore: {'se copiaria' if tiene_filestore else 'no hay filestore'}")
        if neutralize:
            info("  Se ejecutaria neutralize despues de la restauracion.")
        return

    warning(f"Esto REEMPLAZARA la base de datos '{nombre_bd}' con el contenido del backup!")
    if not yes and not typer.confirm("Continuar?", default=False):
        info("Operacion cancelada.")
        raise typer.Exit()

    # -- Extraer a directorio temporal ----------------------------------------
    with tempfile.TemporaryDirectory(prefix="odev_backup_") as tmp:
        ruta_tmp = Path(tmp)
        info("Extrayendo backup...")
        with zipfile.ZipFile(backup) as zf:
            _validar_miembros_zip(zf, ruta_tmp)
            zf.extractall(ruta_tmp)

        archivo_dump = ruta_tmp / nombre_dump

        # -- Detener web + pgweb para liberar conexiones a la BD --------------
        info("Deteniendo servicios web y pgweb...")
        dc.stop("web", "pgweb")

        # Terminar conexiones restantes a la base de datos
        sql_terminar = (
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{nombre_bd}' AND pid <> pg_backend_pid();"
        ).encode()
        dc.exec_cmd(
            "db",
            ["psql", "-U", usuario_bd, "-d", "postgres", "--quiet"],
            stdin_data=sql_terminar,
        )

        info(f"Eliminando base de datos '{nombre_bd}'...")
        dc.exec_cmd("db", ["dropdb", "-U", usuario_bd, "--if-exists", nombre_bd])

        info(f"Creando base de datos '{nombre_bd}'...")
        dc.exec_cmd("db", ["createdb", "-U", usuario_bd, "-O", usuario_bd, nombre_bd])

        # -- Restaurar dump ---------------------------------------------------
        info("Restaurando base de datos (esto puede tomar un rato)...")

        if es_formato_custom:
            dc.exec_cmd_file(
                "db",
                [
                    "pg_restore",
                    "-U",
                    usuario_bd,
                    "-d",
                    nombre_bd,
                    "--no-owner",
                    "--no-acl",
                    "--jobs=2",
                ],
                stdin_file=archivo_dump,
            )
        else:
            dc.exec_cmd_file(
                "db",
                ["psql", "-U", usuario_bd, "-d", nombre_bd, "--quiet"],
                stdin_file=archivo_dump,
            )

        success("Base de datos restaurada.")

        # -- Restaurar filestore ----------------------------------------------
        if tiene_filestore:
            info("Restaurando filestore...")
            directorio_filestore = ruta_tmp / "filestore"

            # Iniciar contenedor web brevemente para copiar archivos al volumen
            dc.start("web")
            contenedor = dc.get_container_name("web")
            if not contenedor:
                warning("No se encontro el contenedor web — se omite la copia del filestore.")
            else:
                destino = f"/var/lib/odoo/filestore/{nombre_bd}"
                subprocess.run(
                    ["docker", "exec", "--user", "root", contenedor, "rm", "-rf", destino],
                    check=False,
                )
                # Crear directorio destino — en contenedores frescos no existe aún
                subprocess.run(
                    ["docker", "exec", "--user", "root", contenedor, "mkdir", "-p", destino],
                    check=True,
                )
                subprocess.run(
                    ["docker", "cp", str(directorio_filestore) + "/.", f"{contenedor}:{destino}"],
                    check=True,
                )
                # Corregir permisos — docker cp crea archivos con el usuario del host
                subprocess.run(
                    [
                        "docker",
                        "exec",
                        "--user",
                        "root",
                        contenedor,
                        "chown",
                        "-R",
                        "odoo:odoo",
                        destino,
                    ],
                    check=True,
                )
                success("Filestore restaurado.")
            dc.stop("web")
        else:
            info("No hay filestore en el backup — se omite.")

    # -- Asegurar que el contenedor web este corriendo -----------------------
    dc.start("web")

    # -- Neutralizar ----------------------------------------------------------
    if neutralize:
        neutralizar_base_datos(dc, nombre_bd, usuario_bd)

    # -- Resetear credenciales de admin ---------------------------------------
    resetear_credenciales_admin(dc, nombre_bd, usuario_bd)

    # -- Configurar parametros de desarrollo ----------------------------------
    puerto_web = valores_env.get("WEB_PORT", "8069")
    configurar_parametros_desarrollo(dc, nombre_bd, usuario_bd, puerto_web)

    # -- Reiniciar todo -------------------------------------------------------
    info("Reiniciando servicios...")
    dc.up(services=["web", "pgweb"])

    success(f"Backup cargado en '{nombre_bd}'. Acceder en http://localhost:{puerto_web}")
