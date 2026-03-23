"""Comando `odev init` — crea un nuevo proyecto Odoo o inicializa el directorio actual.

Ejecuta un wizard interactivo (o usa valores por defecto con --no-interactive)
para recopilar la configuracion del proyecto, renderiza todos los templates
Jinja2 del paquete, crea la estructura de directorios y opcionalmente
inicializa un repositorio git.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import questionary
import typer

from odev import __version__
from odev.commands._wizards import (
    MAPEO_VERSION_PG,
    VERSIONES_ODOO,
    preguntar_configuracion_base,
    renderizar_templates,
    valores_configuracion_por_defecto,
)
from odev.core.config import construir_addon_mounts
from odev.core.console import error, info, success, warning
from odev.core.ports import sugerir_puertos

# -- Constantes ----------------------------------------------------------------

# Archivos que SIEMPRE se regeneran aunque ya existan
_ARCHIVOS_REGENERABLES: set[str] = {".env.example", "config/odoo.conf"}

# Mapa de template -> ruta destino relativa al proyecto
_MAPA_TEMPLATES: list[tuple[str, str]] = [
    ("docker-compose.yml.j2", "docker-compose.yml"),
    ("entrypoint.sh.j2", "entrypoint.sh"),
    ("env.j2", ".env"),
    ("env.example.j2", ".env.example"),
    ("odoo.conf.j2", "config/odoo.conf"),
    ("gitignore.j2", ".gitignore"),
    ("odev.yaml.j2", ".odev.yaml"),
    ("pre-commit-config.yaml.j2", ".pre-commit-config.yaml"),
    ("pylintrc.j2", ".pylintrc"),
    ("claude-md.j2", "CLAUDE.md"),
    ("pyproject-project.toml.j2", "pyproject.toml"),
]

# Directorios que se crean con .gitkeep
_DIRECTORIOS_PROYECTO: list[str] = [
    "addons",
    "enterprise",
    "config",
    "snapshots",
    "logs",
    "docs",
]


# -- Comando principal ----------------------------------------------------------


def init(
    name: str = typer.Argument(
        None,
        help="Nombre del proyecto o '.' para directorio actual.",
    ),
    odoo_version: str = typer.Option(
        None,
        "--odoo-version",
        "-v",
        help="Version de Odoo (19.0, 18.0, 17.0).",
    ),
    no_interactive: bool = typer.Option(
        False,
        "--no-interactive",
        help="Usa valores por defecto sin preguntar.",
    ),
) -> None:
    """Crea un nuevo proyecto Odoo o inicializa el directorio actual."""

    # 1. Determinar directorio destino ----------------------------------------
    directorio_destino, nombre_proyecto = _resolver_destino(name)

    # 2. Verificar si ya existe un proyecto ------------------------------------
    if (directorio_destino / ".odev.yaml").exists():
        warning("Ya existe un proyecto odev en este directorio.")
        if no_interactive:
            info("Regenerando archivos de configuracion (.env.example, config/odoo.conf)...")
        else:
            regenerar = questionary.confirm(
                "Regenerar archivos de configuracion?",
                default=False,
            ).ask()
            if not regenerar:
                raise typer.Exit()

    # 3. Recopilar valores del proyecto ----------------------------------------
    if no_interactive:
        valores = _valores_por_defecto(nombre_proyecto, odoo_version or "19.0")
    else:
        valores = _wizard_interactivo(nombre_proyecto, odoo_version)

    # 4. Crear directorio si no existe -----------------------------------------
    directorio_destino.mkdir(parents=True, exist_ok=True)

    # 5. Generar archivos desde templates --------------------------------------
    info(f"Creando proyecto en {directorio_destino}...")
    _renderizar_archivos_proyecto(directorio_destino, valores)

    # 6. Crear directorios con .gitkeep ----------------------------------------
    _crear_directorios_proyecto(directorio_destino)

    # 7. Hacer entrypoint.sh ejecutable ----------------------------------------
    ruta_entrypoint = directorio_destino / "entrypoint.sh"
    if ruta_entrypoint.exists():
        os.chmod(ruta_entrypoint, 0o755)
        success("entrypoint.sh marcado como ejecutable")

    # 8. Inicializar git si fue solicitado y no existe -------------------------
    inicializar_git = valores.get("inicializar_git", False)
    if inicializar_git and not (directorio_destino / ".git").exists():
        _inicializar_repositorio_git(directorio_destino)

    # 9. Registrar en el registro global ----------------------------------------
    try:
        from datetime import date

        from odev.core.registry import Registry, RegistryEntry

        registro = Registry()
        entry = RegistryEntry(
            nombre=nombre_proyecto,
            directorio_trabajo=directorio_destino.resolve(),
            directorio_config=directorio_destino.resolve(),
            modo="inline",
            version_odoo=valores.get("odoo_version", "19.0"),
            fecha_creacion=date.today().isoformat(),
        )
        registro.registrar(entry)
    except Exception:
        pass  # El registro es opcional para proyectos inline, no falla init

    # 10. Mensaje final --------------------------------------------------------
    _mostrar_resumen_final(nombre_proyecto, directorio_destino, valores)


# -- Wizard interactivo --------------------------------------------------------


def _wizard_interactivo(
    nombre_proyecto_default: str,
    version_odoo_cli: str | None,
) -> dict[str, Any]:
    """Ejecuta el wizard interactivo para recopilar la configuracion del proyecto.

    Args:
        nombre_proyecto_default: Nombre sugerido para el proyecto.
        version_odoo_cli: Version de Odoo pasada por CLI (None si no se paso).

    Returns:
        Diccionario con todos los valores necesarios para renderizar templates.
    """
    info("Bienvenido al asistente de configuracion de odev.\n")

    # 1. Preguntas especificas de init: nombre del proyecto
    nombre_proyecto = questionary.text(
        "Nombre del proyecto:",
        default=nombre_proyecto_default,
        validate=lambda val: len(val.strip()) > 0 or "El nombre del proyecto no puede estar vacio",
    ).ask()
    if nombre_proyecto is None:
        raise typer.Exit()

    # 2. Preguntas especificas de init: version de Odoo
    if version_odoo_cli and version_odoo_cli in VERSIONES_ODOO:
        version_odoo = version_odoo_cli
    else:
        version_odoo = questionary.select(
            "Version de Odoo:",
            choices=VERSIONES_ODOO,
            default="19.0",
        ).ask()
        if version_odoo is None:
            raise typer.Exit()

    # 3. Obtener puertos sugeridos
    puertos_sugeridos = sugerir_puertos()

    # 4. Preguntas de configuracion base (compartidas con adopt)
    config_base = preguntar_configuracion_base(puertos_sugeridos)

    # 5. Preguntas especificas de init: enterprise, CI, git
    habilitar_enterprise = questionary.confirm(
        "Habilitar enterprise addons?",
        default=False,
    ).ask()
    if habilitar_enterprise is None:
        raise typer.Exit()

    generar_ci = questionary.confirm(
        "Generar workflow de GitHub Actions para CI?",
        default=True,
    ).ask()
    if generar_ci is None:
        raise typer.Exit()

    inicializar_git = questionary.confirm(
        "Inicializar repositorio git?",
        default=True,
    ).ask()
    if inicializar_git is None:
        raise typer.Exit()

    # 6. Combinar todo en _construir_valores()
    return _construir_valores(
        nombre_proyecto=nombre_proyecto,
        version_odoo=version_odoo,
        puerto_web=config_base["web_port"],
        puerto_pgweb=config_base["pgweb_port"],
        nombre_db=config_base["db_name"],
        usuario_db=config_base["db_user"],
        password_db=config_base["db_password"],
        idioma=config_base["idioma"],
        sin_demo=config_base["sin_demo"],
        habilitar_debugpy=config_base["habilitar_debugpy"],
        habilitar_enterprise=habilitar_enterprise,
        habilitar_pgweb=config_base["habilitar_pgweb"],
        generar_ci=generar_ci,
        inicializar_git=inicializar_git,
        puerto_db=str(puertos_sugeridos["DB_PORT"]),
        puerto_debugpy=str(puertos_sugeridos["DEBUGPY_PORT"]),
        puerto_mailhog=str(puertos_sugeridos["MAILHOG_PORT"]),
    )


# -- Valores por defecto (modo no-interactivo) ---------------------------------


def _valores_por_defecto(
    nombre_proyecto: str,
    version_odoo: str,
) -> dict[str, Any]:
    """Genera valores por defecto para el modo no-interactivo.

    Args:
        nombre_proyecto: Nombre del proyecto.
        version_odoo: Version de Odoo seleccionada.

    Returns:
        Diccionario con valores por defecto para renderizar templates.
    """
    puertos_sugeridos = sugerir_puertos()
    config_base = valores_configuracion_por_defecto(puertos_sugeridos)

    return _construir_valores(
        nombre_proyecto=nombre_proyecto,
        version_odoo=version_odoo,
        puerto_web=config_base["web_port"],
        puerto_pgweb=config_base["pgweb_port"],
        nombre_db=config_base["db_name"],
        usuario_db=config_base["db_user"],
        password_db=config_base["db_password"],
        idioma=config_base["idioma"],
        sin_demo=config_base["sin_demo"],
        habilitar_debugpy=config_base["habilitar_debugpy"],
        habilitar_enterprise=False,
        habilitar_pgweb=config_base["habilitar_pgweb"],
        generar_ci=True,
        inicializar_git=True,
        puerto_db=str(puertos_sugeridos["DB_PORT"]),
        puerto_debugpy=str(puertos_sugeridos["DEBUGPY_PORT"]),
        puerto_mailhog=str(puertos_sugeridos["MAILHOG_PORT"]),
    )


# -- Construccion del diccionario de valores ------------------------------------


def _construir_valores(
    *,
    nombre_proyecto: str,
    version_odoo: str,
    puerto_web: str,
    puerto_pgweb: str,
    nombre_db: str,
    usuario_db: str,
    password_db: str,
    idioma: str,
    sin_demo: str,
    habilitar_debugpy: bool,
    habilitar_enterprise: bool,
    habilitar_pgweb: bool,
    generar_ci: bool,
    inicializar_git: bool,
    puerto_db: str,
    puerto_debugpy: str,
    puerto_mailhog: str = "8025",
) -> dict[str, Any]:
    """Construye el diccionario unificado de valores para templates.

    Contiene tanto las variables en formato MAYUSCULAS (para env.j2 / env.example.j2
    / odoo.conf.j2) como las variables en formato snake_case (para docker-compose.yml.j2,
    odev.yaml.j2, claude-md.j2, etc.).

    Args:
        Todos los parametros corresponden a las respuestas del wizard.

    Returns:
        Diccionario con todas las claves necesarias para renderizar cada template.
    """
    tag_imagen_odoo = version_odoo.replace(".0", "")
    tag_imagen_db = MAPEO_VERSION_PG.get(version_odoo, "16")

    return {
        # --- Variables MAYUSCULAS (para env.j2, env.example.j2, odoo.conf.j2) ---
        "PROJECT_NAME": nombre_proyecto,
        "ODOO_VERSION": version_odoo,
        "ODOO_IMAGE_TAG": tag_imagen_odoo,
        "WEB_PORT": puerto_web,
        "PGWEB_PORT": puerto_pgweb,
        "DB_NAME": nombre_db,
        "DB_USER": usuario_db,
        "DB_PASSWORD": password_db,
        "DB_IMAGE_TAG": tag_imagen_db,
        "DB_PORT": puerto_db,
        "DB_HOST": "db",
        "LOAD_LANGUAGE": idioma,
        "WITHOUT_DEMO": sin_demo,
        "DEBUGPY": "True" if habilitar_debugpy else "False",
        "DEBUGPY_PORT": puerto_debugpy,
        "ADMIN_PASSWORD": "admin",
        "INIT_MODULES": "",
        "MAILHOG_PORT": puerto_mailhog,
        # --- Variables snake_case (para odev.yaml.j2, docker-compose.yml.j2, etc.) ---
        "project_name": nombre_proyecto,
        "odoo_version": version_odoo,
        "odoo_image_tag": tag_imagen_odoo,
        "db_image_tag": tag_imagen_db,
        "enterprise_enabled": habilitar_enterprise,
        "services_pgweb": habilitar_pgweb,
        "services_mailhog": True,
        "odev_version": __version__,
        "project_description": "",
        # --- Variables de addon mounts para templates dinamicos ---
        "addon_mounts": construir_addon_mounts(["./addons"], Path(".")),
        "addon_container_paths": [
            m["container_path"]
            for m in construir_addon_mounts(["./addons"], Path("."))
        ],
        "addon_dirs_container": [
            m["container_path"]
            for m in construir_addon_mounts(["./addons"], Path("."))
        ],
        "addons_paths_list": ["./addons"],
        "project_mode": "inline",
        "odev_min_version": __version__,
        # --- Flags de control (no se pasan a templates, solo a la logica) ---
        "generar_ci": generar_ci,
        "inicializar_git": inicializar_git,
    }


# -- Renderizado de archivos ---------------------------------------------------


def _renderizar_archivos_proyecto(
    directorio_destino: Path,
    valores: dict[str, Any],
) -> None:
    """Renderiza todos los templates Jinja2 y los escribe en el directorio destino.

    No sobreescribe archivos existentes excepto los definidos en
    _ARCHIVOS_REGENERABLES (.env.example y config/odoo.conf).

    Args:
        directorio_destino: Directorio raiz del proyecto donde escribir.
        valores: Diccionario de valores para renderizar los templates.
    """
    renderizar_templates(
        directorio_destino,
        valores,
        _MAPA_TEMPLATES,
        archivos_regenerables=_ARCHIVOS_REGENERABLES,
    )

    # GitHub Actions CI (opcional, no esta en _MAPA_TEMPLATES porque es condicional)
    if valores.get("generar_ci", False):
        _generar_github_ci(directorio_destino, valores)


def _generar_github_ci(directorio_destino: Path, valores: dict[str, Any]) -> None:
    """Genera el workflow de GitHub Actions para CI del proyecto.

    Crea el archivo .github/workflows/ci.yml con un pipeline basico
    de linting y testing para addons de Odoo.

    Args:
        directorio_destino: Directorio raiz del proyecto.
        valores: Diccionario de valores del proyecto.
    """
    ruta_ci = directorio_destino / ".github" / "workflows" / "ci.yml"
    if ruta_ci.exists():
        warning("Archivo existente, se omite: .github/workflows/ci.yml")
        return

    ruta_ci.parent.mkdir(parents=True, exist_ok=True)

    contenido_ci = f"""name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install ruff
      - name: Ruff linting
        run: ruff check addons/
      - name: Ruff verificar formato
        run: ruff format --check addons/

  test:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4
      - name: Copiar .env.example a .env
        run: cp .env.example .env
      - name: Levantar entorno
        run: |
          docker compose up -d --wait
          timeout 120 bash -c 'until docker compose exec web curl -sf http://localhost:8069/web/health; do sleep 5; done'
      - name: Instalar modulos
        run: |
          MODULES=$(ls addons/ | tr '\\n' ',' | sed 's/,$//')
          if [ -n "$MODULES" ]; then
            docker compose exec web odoo -i "$MODULES" -d {valores.get("DB_NAME", "odoo_db")} --stop-after-init
          fi
      - name: Ejecutar tests
        run: |
          MODULES=$(ls addons/ | tr '\\n' ',' | sed 's/,$//')
          if [ -n "$MODULES" ]; then
            docker compose exec web odoo --test-enable --stop-after-init -d {valores.get("DB_NAME", "odoo_db")} -u "$MODULES"
          fi
      - name: Limpieza
        if: always()
        run: docker compose down -v
"""
    ruta_ci.write_text(contenido_ci)
    success(".github/workflows/ci.yml")


# -- Creacion de directorios ---------------------------------------------------


def _crear_directorios_proyecto(directorio_destino: Path) -> None:
    """Crea los directorios del proyecto con archivos .gitkeep.

    No sobreescribe .gitkeep existentes.

    Args:
        directorio_destino: Directorio raiz del proyecto.
    """
    for nombre_directorio in _DIRECTORIOS_PROYECTO:
        ruta_directorio = directorio_destino / nombre_directorio
        ruta_directorio.mkdir(parents=True, exist_ok=True)
        ruta_gitkeep = ruta_directorio / ".gitkeep"
        if not ruta_gitkeep.exists():
            ruta_gitkeep.touch()
            success(f"{nombre_directorio}/.gitkeep")


# -- Inicializacion de git -----------------------------------------------------


def _inicializar_repositorio_git(directorio_destino: Path) -> None:
    """Inicializa un repositorio git con un commit inicial.

    Ejecuta git init, git add . y git commit en el directorio del proyecto.

    Args:
        directorio_destino: Directorio raiz del proyecto.
    """
    try:
        subprocess.run(
            ["git", "init"],
            cwd=directorio_destino,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "add", "."],
            cwd=directorio_destino,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "feat: proyecto Odoo inicializado con odev"],
            cwd=directorio_destino,
            check=True,
            capture_output=True,
        )
        success("Repositorio git inicializado")
    except FileNotFoundError:
        warning("git no esta instalado. Se omite la inicializacion del repositorio.")
    except subprocess.CalledProcessError as exc:
        warning(f"Error al inicializar git: {exc}")


# -- Utilidades ----------------------------------------------------------------


def _resolver_destino(name: str | None) -> tuple[Path, str]:
    """Determina el directorio destino y nombre del proyecto.

    Args:
        name: Nombre pasado como argumento al comando. Puede ser None, '.'
              o un nombre de directorio.

    Returns:
        Tupla (directorio_destino, nombre_proyecto).
    """
    if name is None or name == ".":
        directorio_destino = Path.cwd()
        nombre_proyecto = directorio_destino.name
    else:
        ruta = Path(name)
        if ruta.is_absolute():
            directorio_destino = ruta
        else:
            directorio_destino = Path.cwd() / name
        nombre_proyecto = directorio_destino.name
    return directorio_destino, nombre_proyecto


def _mostrar_resumen_final(
    nombre_proyecto: str,
    directorio_destino: Path,
    valores: dict[str, Any],
) -> None:
    """Muestra el resumen de la creacion del proyecto y los proximos pasos.

    Args:
        nombre_proyecto: Nombre del proyecto creado.
        directorio_destino: Ruta al directorio del proyecto.
        valores: Diccionario de valores del proyecto.
    """
    puerto_web = valores.get("WEB_PORT", "8069")

    success(f"\nProyecto '{nombre_proyecto}' creado exitosamente!")
    info("Proximos pasos:")

    # Solo sugerir cd si no es el directorio actual
    if directorio_destino != Path.cwd():
        info(f"  cd {directorio_destino.name}")

    info("  odev up")
    info(f"  Abrir http://localhost:{puerto_web}")
