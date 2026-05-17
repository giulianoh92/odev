"""Comando 'up': levanta el entorno de desarrollo Odoo.

Inicia los servicios de Docker Compose en modo detached.
Auto-regenera odoo.conf si el .env es mas reciente que la
configuracion existente.
"""

import os
import platform
import stat

import typer

from odev.commands._helpers import obtener_docker, obtener_rutas, requerir_proyecto
from odev.core.config import construir_addon_mounts, generate_odoo_conf, load_env
from odev.core.console import error, info, success, warning
from odev.core.paths import ProjectPaths
from odev.core.preflight import verificar_puertos_pre_up
from odev.core.registry import Registry


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
    from odev.main import obtener_nombre_proyecto
    contexto = requerir_proyecto(obtener_nombre_proyecto())
    rutas = obtener_rutas(contexto)

    if not rutas.env_file.exists():
        from odev.core.console import error
        error("No se encontro el archivo .env. Ejecuta 'odev init' primero.")
        raise typer.Exit(1)

    # --- Check if odev.yaml changed and trigger full regen ---
    from odev.core.regen import necesita_regeneracion, regenerar_configuracion

    if necesita_regeneracion(contexto):
        warning("odev.yaml changed since last generation. Regenerating configs...")
        resultado = regenerar_configuracion(contexto)
        if resultado.archivos_regenerados:
            info(
                f"Regenerated: {', '.join(a.name for a in resultado.archivos_regenerados)}"
            )
    else:
        # --- Fallback to .env-only mtime check for odoo.conf ---
        valores_env = load_env(rutas.env_file)
        addon_mounts = None
        if contexto.config and contexto.config.rutas_addons:
            addon_mounts = construir_addon_mounts(
                contexto.config.rutas_addons,
                contexto.directorio_config,
            )
        enterprise_enabled = bool(
            contexto.config and contexto.config.enterprise_habilitado
        )
        archivo_odoo_conf = rutas.config_dir / "odoo.conf"
        if (
            not archivo_odoo_conf.exists()
            or rutas.env_file.stat().st_mtime > archivo_odoo_conf.stat().st_mtime
        ):
            generate_odoo_conf(
                valores_env, rutas.config_dir,
                addon_mounts=addon_mounts,
                enterprise_enabled=enterprise_enabled,
            )
            info("Se regenero config/odoo.conf desde .env")

    _asegurar_directorio_logs(rutas)

    # --- Pre-flight de puertos ---
    _preflight_puertos(contexto, rutas)

    info("Iniciando entorno...")
    dc = obtener_docker(contexto)
    dc.up(build=build, watch=watch)

    valores_env = load_env(rutas.env_file)
    puerto_web = valores_env.get("WEB_PORT", "8069")
    puerto_pgweb = valores_env.get("PGWEB_PORT", "8081")
    success("Entorno iniciado correctamente.")
    info(f"  Odoo:  http://localhost:{puerto_web}")
    info(f"  pgweb: http://localhost:{puerto_pgweb}")


# ── Preflight helper ──────────────────────────────────────────────────────────


_CLAVES_PREFLIGHT = ("WEB_PORT", "DB_PORT", "PGWEB_PORT", "DEBUGPY_PORT", "MAILHOG_PORT")


def _preflight_puertos(contexto, rutas: ProjectPaths) -> None:
    """Verifica la disponibilidad de los puertos antes de iniciar docker compose.

    Lee el .env del proyecto, extrae los puertos conocidos, y clasifica cada
    uno como libre, propio o foraneo. Si hay al menos un puerto foraneo,
    imprime la tabla de conflictos y sale con codigo 3.

    Argumentos:
        contexto: Contexto del proyecto resuelto (tiene atributo nombre).
        rutas: Rutas del proyecto (se usa env_file).

    Lanza:
        typer.Exit(3): Si alguno de los puertos esta ocupado por un proceso ajeno.
    """
    valores_env = load_env(rutas.env_file)

    puertos: dict[str, int] = {}
    for clave in _CLAVES_PREFLIGHT:
        valor = valores_env.get(clave)
        if valor is None:
            continue
        try:
            puertos[clave] = int(valor)
        except (ValueError, TypeError):
            continue

    if not puertos:
        return

    dc = obtener_docker(contexto)
    registry = Registry()
    resultado = verificar_puertos_pre_up(contexto, dc, registry, puertos)

    # Emitir warns para contenedores propios corriendo
    for status in resultado.warnings:
        warning(
            f"WARN: puerto {status.puerto} ({status.nombre}) ya usado "
            f"por este proyecto — docker compose reutilizara"
        )

    # Fallar si hay puertos foraneos
    if resultado.has_fail:
        for status in resultado.fails:
            if status.propietario:
                error(
                    f"puerto {status.puerto} ({status.nombre}) "
                    f"usado por proyecto {status.propietario}"
                )
            else:
                error(
                    f"puerto {status.puerto} ({status.nombre}) "
                    f"en uso por proceso ajeno"
                )
        raise typer.Exit(3)
