"""Comando 'load-backup': carga un backup de Odoo.sh en el entorno local.

Acepta un archivo .zip con un dump PostgreSQL y opcionalmente un filestore.
Reemplaza la base de datos actual, restaura el filestore, y opcionalmente
neutraliza la base de datos.
"""

import subprocess
import tempfile
import zipfile
from pathlib import Path

import typer

from odev.core.config import load_env
from odev.core.console import error, info, success, warning
from odev.core.docker import DockerCompose
from odev.core.paths import ProjectPaths


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
) -> None:
    """Carga un backup de Odoo.sh (o Database Manager) en el entorno local.

    Acepta un archivo .zip que contenga un dump de PostgreSQL y un
    directorio filestore opcional. Elimina la base de datos actual,
    restaura el dump, copia el filestore en el volumen de datos de Odoo,
    y opcionalmente neutraliza la base de datos para que no envie correos
    ni ejecute acciones programadas.
    """
    try:
        rutas = ProjectPaths()
    except FileNotFoundError:
        error("No se encontro un proyecto odev. Ejecuta 'odev init' para crear uno.")
        raise typer.Exit(1)

    valores_env = load_env(rutas.env_file)
    usuario_bd = valores_env.get("DB_USER", "odoo")
    nombre_bd = valores_env.get("DB_NAME", "odoo_db")

    dc = DockerCompose(rutas.root)

    # -- Validar backup -------------------------------------------------------
    if not zipfile.is_zipfile(backup):
        error("El archivo no es un archivo .zip valido.")
        raise typer.Exit(1)

    with zipfile.ZipFile(backup) as zf:
        nombres = zf.namelist()

    # Los backups de Odoo.sh contienen dump.sql en la raiz; Database Manager
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

    warning(f"Esto REEMPLAZARA la base de datos '{nombre_bd}' con el contenido del backup!")
    if not typer.confirm("Continuar?", default=False):
        info("Operacion cancelada.")
        raise typer.Exit()

    # -- Extraer a directorio temporal ----------------------------------------
    with tempfile.TemporaryDirectory(prefix="odev_backup_") as tmp:
        ruta_tmp = Path(tmp)
        info("Extrayendo backup...")
        with zipfile.ZipFile(backup) as zf:
            zf.extractall(ruta_tmp)

        archivo_dump = ruta_tmp / nombre_dump

        # -- Detener web + pgweb para liberar conexiones a la BD --------------
        info("Deteniendo servicios web y pgweb...")
        dc._run(["stop", "web", "pgweb"])

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
        datos_dump = archivo_dump.read_bytes()

        if es_formato_custom:
            dc.exec_cmd(
                "db",
                [
                    "pg_restore", "-U", usuario_bd, "-d", nombre_bd,
                    "--no-owner", "--no-acl", "--jobs=2",
                ],
                stdin_data=datos_dump,
            )
        else:
            dc.exec_cmd(
                "db",
                ["psql", "-U", usuario_bd, "-d", nombre_bd, "--quiet"],
                stdin_data=datos_dump,
            )

        success("Base de datos restaurada.")

        # -- Restaurar filestore ----------------------------------------------
        if tiene_filestore:
            info("Restaurando filestore...")
            directorio_filestore = ruta_tmp / "filestore"

            # Iniciar contenedor web brevemente para copiar archivos al volumen
            dc._run(["start", "web"])
            contenedor = dc.get_container_name("web")
            if not contenedor:
                warning("No se encontro el contenedor web — se omite la copia del filestore.")
            else:
                destino = f"/var/lib/odoo/filestore/{nombre_bd}"
                subprocess.run(
                    ["docker", "exec", "--user", "root", contenedor,
                     "rm", "-rf", destino],
                    check=False,
                )
                subprocess.run(
                    ["docker", "cp", str(directorio_filestore) + "/.",
                     f"{contenedor}:{destino}"],
                    check=True,
                )
                # Corregir permisos — docker cp crea archivos con el usuario del host
                subprocess.run(
                    ["docker", "exec", "--user", "root", contenedor,
                     "chown", "-R", "odoo:odoo", destino],
                    check=True,
                )
                success("Filestore restaurado.")
            dc._run(["stop", "web"])
        else:
            info("No hay filestore en el backup — se omite.")

    # -- Neutralizar ----------------------------------------------------------
    if neutralize:
        info("Neutralizando base de datos (desactivando crons, servidores de correo, etc.)...")
        dc._run(["start", "web"])
        dc.exec_cmd(
            "web",
            [
                "odoo", "neutralize",
                "--config=/etc/odoo/odoo.conf",
                "-d", nombre_bd,
            ],
            interactive=True,
        )
        success("Base de datos neutralizada.")

    # -- Resetear credenciales de admin ---------------------------------------
    info("Reseteando credenciales de admin (admin/admin)...")
    resultado_hash = dc.exec_cmd(
        "web",
        [
            "python3", "-c",
            "from passlib.context import CryptContext; "
            "print(CryptContext(['pbkdf2_sha512']).hash('admin'))",
        ],
    )
    hash_pw = resultado_hash.stdout.decode().strip()
    dc.exec_cmd(
        "db",
        ["psql", "-U", usuario_bd, "-d", nombre_bd, "-c",
         f"UPDATE res_users SET login = 'admin', password = '{hash_pw}' WHERE id = 2;"],
    )
    success("Credenciales de admin reseteadas: login=admin, password=admin")

    # -- Reiniciar todo -------------------------------------------------------
    info("Reiniciando servicios...")
    dc._run(["restart", "web", "pgweb"])

    puerto_web = valores_env.get("WEB_PORT", "8069")
    success(f"Backup cargado en '{nombre_bd}'. Acceder en http://localhost:{puerto_web}")
