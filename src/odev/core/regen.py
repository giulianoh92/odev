"""Motor de regeneracion compartido para archivos de configuracion odev.

Lee odev.yaml y el .env existente, construye un contexto unificado de templates,
y re-renderiza docker-compose.yml y odoo.conf. Opcionalmente re-renderiza .env.

Usado por: commands/reconfigure.py, commands/up.py, commands/adopt.py.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from odev.core.config import (
    construir_addon_mounts,
    generate_odoo_conf,
    load_env,
    write_env,
)
from odev.core.console import info, success
from odev.core.paths import get_project_templates_dir
from odev.core.project import ProjectConfig
from odev.core.resolver import ProjectContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Resultado de la regeneracion
# ---------------------------------------------------------------------------


@dataclass
class RegenResult:
    """Resultado de una operacion de regeneracion.

    Atributos:
        archivos_regenerados: Archivos que fueron re-escritos con contenido diferente.
        archivos_sin_cambios: Archivos que no cambiaron respecto a su version anterior.
        advertencias: Lista de advertencias generadas durante la regeneracion.
    """

    archivos_regenerados: list[Path] = field(default_factory=list)
    archivos_sin_cambios: list[Path] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------------------


def _renderizar_template(nombre_template: str, destino: Path, valores: dict[str, Any]) -> None:
    """Renderiza un template Jinja2 y lo escribe en destino.

    Argumentos:
        nombre_template: Nombre del archivo template (ej. 'docker-compose.yml.j2').
        destino: Ruta donde escribir el resultado.
        valores: Diccionario de valores para el template.
    """
    from jinja2 import Environment, FileSystemLoader

    entorno = Environment(
        loader=FileSystemLoader(str(get_project_templates_dir())),
        keep_trailing_newline=True,
    )
    template = entorno.get_template(nombre_template)
    contenido = template.render(**valores)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(contenido)


def _extraer_tag_db(imagen_db: str) -> str:
    """Extrae el tag de version de PostgreSQL de la imagen de DB.

    Argumentos:
        imagen_db: Imagen Docker de la base de datos (ej. 'pgvector/pgvector:pg16').

    Retorna:
        Tag de version de PostgreSQL (ej. '16').
    """
    tag = imagen_db.rsplit(":", 1)[-1] if ":" in imagen_db else "16"
    return tag.removeprefix("pg")


def _extraer_env_values(valores: dict[str, Any]) -> dict[str, str]:
    """Extract UPPERCASE env keys from the merged context dict.

    Argumentos:
        valores: Diccionario completo de valores de template.

    Retorna:
        Diccionario filtrado con solo las variables de entorno.
    """
    claves_env = {
        "PROJECT_NAME", "ODOO_VERSION", "ODOO_IMAGE_TAG", "WEB_PORT",
        "PGWEB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD", "DB_IMAGE_TAG",
        "DB_PORT", "DB_HOST", "LOAD_LANGUAGE", "WITHOUT_DEMO", "DEBUGPY",
        "DEBUGPY_PORT", "ADMIN_PASSWORD", "INIT_MODULES", "MAILHOG_PORT",
    }
    return {k: str(v) for k, v in valores.items() if k in claves_env}


# ---------------------------------------------------------------------------
# Construccion de contexto de templates
# ---------------------------------------------------------------------------


def construir_contexto_templates(
    config: ProjectConfig,
    env_values: dict[str, str | None],
    directorio_config: Path,
    directorio_trabajo: Path | None = None,
) -> dict[str, Any]:
    """Construye el contexto unificado de templates desde odev.yaml + .env.

    Combina valores estructurales (de odev.yaml via ProjectConfig) con valores
    de runtime (del .env existente) para producir un dict que los templates
    Jinja2 pueden consumir.

    Argumentos:
        config: Configuracion del proyecto cargada desde .odev.yaml.
        env_values: Valores del .env existente (o dict vacio).
        directorio_config: Directorio donde viven los archivos de config.
        directorio_trabajo: Directorio de trabajo del proyecto (para resolver
            rutas relativas). Si es None, usa directorio_config.

    Retorna:
        Diccionario unificado con todas las claves necesarias para los templates.
    """
    dir_trabajo = directorio_trabajo or directorio_config

    def env_or(clave: str, default: str) -> str:
        """Retorna el valor del .env o el default si no existe."""
        valor = env_values.get(clave)
        return valor if valor is not None else default

    # Valores estructurales desde odev.yaml
    version_odoo = config.version_odoo
    tag_imagen_odoo = version_odoo.replace(".0", "")
    tag_imagen_db = _extraer_tag_db(config.imagen_db)

    enterprise_habilitado = config.enterprise_habilitado
    enterprise_path = config.ruta_enterprise

    # Addon mounts
    rutas_addons_str = config.rutas_addons
    addon_mounts = construir_addon_mounts(rutas_addons_str, directorio_config)

    nombre = config.nombre_proyecto or directorio_config.name
    modo = config.modo

    return {
        # --- Variables MAYUSCULAS (para env.j2, odoo.conf.j2) ---
        "PROJECT_NAME": env_or("PROJECT_NAME", nombre),
        "ODOO_VERSION": version_odoo,
        "ODOO_IMAGE_TAG": tag_imagen_odoo,
        "WEB_PORT": env_or("WEB_PORT", "8069"),
        "PGWEB_PORT": env_or("PGWEB_PORT", "8081"),
        "DB_NAME": env_or("DB_NAME", "odoo_db"),
        "DB_USER": env_or("DB_USER", "odoo"),
        "DB_PASSWORD": env_or("DB_PASSWORD", "odoo"),
        "DB_IMAGE_TAG": tag_imagen_db,
        "DB_PORT": env_or("DB_PORT", "5432"),
        "DB_HOST": env_or("DB_HOST", "db"),
        "LOAD_LANGUAGE": env_or("LOAD_LANGUAGE", "en_US"),
        "WITHOUT_DEMO": env_or("WITHOUT_DEMO", "all"),
        "DEBUGPY": env_or("DEBUGPY", "False"),
        "DEBUGPY_PORT": env_or("DEBUGPY_PORT", "5678"),
        "ADMIN_PASSWORD": env_or("ADMIN_PASSWORD", "admin"),
        "INIT_MODULES": env_or("INIT_MODULES", ""),
        "MAILHOG_PORT": env_or("MAILHOG_PORT", "8025"),
        # --- Variables snake_case (para odev.yaml.j2, docker-compose.yml.j2) ---
        "project_name": nombre,
        "project_mode": modo,
        "working_dir": str(dir_trabajo),
        "odoo_version": version_odoo,
        "odoo_image_tag": tag_imagen_odoo,
        "odoo_image": config.imagen_odoo,
        "db_image_tag": tag_imagen_db,
        "db_image": config.imagen_db,
        "enterprise_enabled": enterprise_habilitado,
        "enterprise_path": enterprise_path,
        "addon_mounts": addon_mounts,
        "addon_container_paths": [m["container_path"] for m in addon_mounts],
        "addon_dirs_container": [m["container_path"] for m in addon_mounts],
        "addons_paths_list": rutas_addons_str,
        "odev_min_version": config.version_minima,
        "services_pgweb": config.pgweb_habilitado,
        "services_mailhog": True,
        "project_description": config.descripcion_proyecto,
    }


# ---------------------------------------------------------------------------
# Verificacion de necesidad de regeneracion
# ---------------------------------------------------------------------------


def necesita_regeneracion(contexto: ProjectContext) -> bool:
    """Verifica si los archivos generados necesitan ser regenerados.

    Compara el mtime de .odev.yaml contra los archivos generados
    (docker-compose.yml, odoo.conf). Si .odev.yaml es mas nuevo que
    alguno de ellos, retorna True.

    Argumentos:
        contexto: Contexto del proyecto resuelto.

    Retorna:
        True si se necesita regenerar, False si todo esta actualizado.
    """
    dir_config = contexto.directorio_config
    ruta_yaml = dir_config / ".odev.yaml"

    if not ruta_yaml.exists():
        return False

    mtime_yaml = ruta_yaml.stat().st_mtime

    archivos_generados = [
        dir_config / "docker-compose.yml",
        dir_config / "config" / "odoo.conf",
    ]

    for archivo in archivos_generados:
        if not archivo.exists():
            return True
        if mtime_yaml > archivo.stat().st_mtime:
            return True

    return False


# ---------------------------------------------------------------------------
# Funcion principal de regeneracion
# ---------------------------------------------------------------------------


def regenerar_configuracion(
    contexto: ProjectContext,
    include_env: bool = False,
) -> RegenResult:
    """Re-lee odev.yaml + .env, re-renderiza docker-compose.yml y odoo.conf.

    Esta es la funcion central de regeneracion. Ejecuta:
    1. Carga ProjectConfig desde .odev.yaml
    2. Carga valores existentes del .env (si existe)
    3. Construye un contexto unificado de templates
    4. Renderiza docker-compose.yml y odoo.conf
    5. Opcionalmente renderiza .env si include_env=True

    Argumentos:
        contexto: Contexto del proyecto resuelto (provee paths y config).
        include_env: Si True, tambien regenera el .env. Por defecto False
            para preservar valores de runtime editados por el usuario
            (passwords, puertos).

    Retorna:
        RegenResult con listas de archivos regenerados y sin cambios.
    """
    resultado = RegenResult()
    dir_config = contexto.directorio_config

    # 1. Cargar configuracion
    config = ProjectConfig(dir_config)

    # 2. Cargar .env existente
    ruta_env = dir_config / ".env"
    env_values = load_env(ruta_env) if ruta_env.exists() else {}

    # 3. Construir contexto unificado
    dir_trabajo = contexto.directorio_trabajo
    valores = construir_contexto_templates(
        config, env_values, dir_config, dir_trabajo,
    )

    # 4. Renderizar docker-compose.yml
    ruta_compose = dir_config / "docker-compose.yml"
    contenido_anterior_compose = ruta_compose.read_text() if ruta_compose.exists() else ""
    _renderizar_template("docker-compose.yml.j2", ruta_compose, valores)
    if ruta_compose.read_text() != contenido_anterior_compose:
        resultado.archivos_regenerados.append(ruta_compose)
        success("docker-compose.yml (regenerado)")
    else:
        resultado.archivos_sin_cambios.append(ruta_compose)

    # 5. Renderizar odoo.conf
    ruta_odoo_conf = dir_config / "config" / "odoo.conf"
    contenido_anterior_conf = ruta_odoo_conf.read_text() if ruta_odoo_conf.exists() else ""

    addon_mounts = valores["addon_mounts"]
    generate_odoo_conf(
        env_values=_extraer_env_values(valores),
        config_dir=dir_config / "config",
        addon_mounts=addon_mounts,
        enterprise_enabled=valores["enterprise_enabled"],
    )

    if ruta_odoo_conf.exists():
        if ruta_odoo_conf.read_text() != contenido_anterior_conf:
            resultado.archivos_regenerados.append(ruta_odoo_conf)
            success("config/odoo.conf (regenerado)")
        else:
            resultado.archivos_sin_cambios.append(ruta_odoo_conf)

    # 6. Opcionalmente renderizar .env
    if include_env:
        contenido_anterior_env = ruta_env.read_text() if ruta_env.exists() else ""
        write_env(valores, dest=ruta_env)
        if ruta_env.read_text() != contenido_anterior_env:
            resultado.archivos_regenerados.append(ruta_env)
            success(".env (regenerado)")
        else:
            resultado.archivos_sin_cambios.append(ruta_env)

    return resultado
