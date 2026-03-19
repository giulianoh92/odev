"""Comando 'up': levanta el entorno de desarrollo Odoo.

Inicia los servicios de Docker Compose en modo detached.
Auto-regenera odoo.conf si el .env es mas reciente que la
configuracion existente.
"""

import os
import platform
import stat

import typer

from odev.core.config import generate_odoo_conf, load_env
from odev.core.console import error, info, success
from odev.core.docker import DockerCompose
from odev.core.paths import ProjectPaths


def _asegurar_directorio_logs(rutas: ProjectPaths) -> None:
    """Asegura que el directorio de logs exista y sea escribible por los contenedores.

    Crea el directorio si no existe y ajusta permisos POSIX para que
    los procesos dentro de los contenedores puedan escribir logs.

    Args:
        rutas: Instancia de ProjectPaths del proyecto actual.
    """
    directorio_logs = rutas.logs_dir
    directorio_logs.mkdir(exist_ok=True)
    if platform.system() != "Windows":
        permisos_actuales = directorio_logs.stat().st_mode
        permisos_deseados = permisos_actuales | stat.S_IWOTH | stat.S_IXOTH  # o+wx
        if permisos_actuales != permisos_deseados:
            os.chmod(directorio_logs, permisos_deseados)


def up(
    build: bool = typer.Option(False, "--build", help="Reconstruir imagenes antes de iniciar."),
    watch: bool = typer.Option(False, "--watch", help="Activar modo watch de docker compose."),
) -> None:
    """Levanta el entorno de desarrollo Odoo.

    Detecta el proyecto actual, verifica que exista el archivo .env,
    auto-regenera odoo.conf si es necesario, y ejecuta docker compose up.
    """
    try:
        rutas = ProjectPaths()
    except FileNotFoundError:
        error("No se encontro un proyecto odev. Ejecuta 'odev init' para crear uno.")
        raise typer.Exit(1)

    if not rutas.env_file.exists():
        error("No se encontro el archivo .env. Ejecuta 'odev init' primero.")
        raise typer.Exit(1)

    valores_env = load_env(rutas.env_file)

    # Auto-regenerar odoo.conf si el .env es mas reciente
    archivo_odoo_conf = rutas.config_dir / "odoo.conf"
    if not archivo_odoo_conf.exists() or rutas.env_file.stat().st_mtime > archivo_odoo_conf.stat().st_mtime:
        generate_odoo_conf(valores_env, rutas.config_dir)
        info("Se regenero config/odoo.conf desde .env")

    _asegurar_directorio_logs(rutas)

    info("Iniciando entorno...")
    dc = DockerCompose(rutas.root)
    dc.up(build=build, watch=watch)

    puerto_web = valores_env.get("WEB_PORT", "8069")
    puerto_pgweb = valores_env.get("PGWEB_PORT", "8081")
    success("Entorno iniciado correctamente.")
    info(f"  Odoo:  http://localhost:{puerto_web}")
    info(f"  pgweb: http://localhost:{puerto_pgweb}")
