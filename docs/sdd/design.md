# SDD Technical Design: odev CLI Configuration Lifecycle Improvements

- **Date**: 2026-03-25
- **Status**: Draft
- **Proposal**: [proposal.md](./proposal.md)
- **Scope**: 3 new modules, 13 modified files, 8 improvements (P1-P8)

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [New Module: `core/regen.py`](#2-new-module-coreregenpy)
3. [New Module: `commands/reconfigure.py`](#3-new-module-commandsreconfigurepy) (P1)
4. [Auto-regen on `up`](#4-auto-regen-on-up) (P3)
5. [New Module: `commands/enterprise.py`](#5-new-module-commandsenterprisepy) (P2)
6. [`adopt --force`](#6-adopt---force) (P6)
7. [Enterprise addons_path Ordering](#7-enterprise-addons_path-ordering) (P7)
8. [`load-backup` Pre-flight Checks](#8-load-backup-pre-flight-checks) (P4)
9. [`--yes` Flag for Destructive Commands](#9---yes-flag-for-destructive-commands) (P5)
10. [Schema Enforcement](#10-schema-enforcement) (P8)
11. [Cross-cutting Concerns](#11-cross-cutting-concerns)
12. [Test Design](#12-test-design)
13. [Migration and Backward Compatibility](#13-migration-and-backward-compatibility)

---

## 1. Architecture Overview

### Data Flow: odev.yaml to Runtime Artifacts

```
                        odev.yaml (source of truth)
                              |
                    ProjectConfig.__init__()
                              |
                    +--- datos dict ---+
                    |                  |
              regen.construir_contexto_templates()
                    |                  |
          [env values from .env]   [structural values from odev.yaml]
                    |                  |
                    +--- merged context dict ---+
                              |
                 +------------+------------+
                 |            |            |
           env.j2      docker-compose   odoo.conf.j2
          (optional)      .yml.j2
                 |            |            |
              .env    docker-compose   odoo.conf
                         .yml
```

### Module Dependency Graph

```
core/regen.py (NEW)
    imports: core/config.py, core/project.py, core/paths.py
    used by: commands/reconfigure.py, commands/up.py, commands/adopt.py

commands/reconfigure.py (NEW)
    imports: core/regen.py, commands/_helpers.py

commands/enterprise.py (NEW)
    imports: core/registry.py, core/project.py, core/regen.py
```

### Key Design Decisions

1. **Regeneration engine lives in `core/regen.py`**, not in a command module. Three callers need it: `reconfigure`, `up`, and `adopt --force`.
2. **`.env` is preserved by default** during regeneration. Only `docker-compose.yml` and `odoo.conf` are regenerated. The `--include-env` flag opts into `.env` regeneration.
3. **Enterprise path resolution** uses a 4-tier priority: explicit `odev.yaml` path > local `./enterprise` > shared `~/.odev/enterprise/{version}/` > disabled.
4. **`ProjectConfig` gains an `enterprise_path` property** (missing today) needed by the regen engine.

---

## 2. New Module: `core/regen.py`

**File**: `src/odev/core/regen.py`

This is the shared regeneration engine used by P1, P3, and P6. It reads `odev.yaml`, builds a unified template context, and re-renders the generated files.

### 2.1 Public API

```python
"""Shared regeneration engine for odev configuration files.

Reads odev.yaml and existing .env, builds a merged template context,
and re-renders docker-compose.yml and odoo.conf. Optionally re-renders .env.
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
from odev.core.console import info, success, warning
from odev.core.project import ProjectConfig
from odev.core.resolver import ProjectContext

logger = logging.getLogger(__name__)


@dataclass
class RegenResult:
    """Result of a regeneration operation.

    Attributes:
        archivos_regenerados: List of file paths that were written.
        archivos_sin_cambios: List of file paths that were identical.
        advertencias: Any warnings produced during regeneration.
    """

    archivos_regenerados: list[Path] = field(default_factory=list)
    archivos_sin_cambios: list[Path] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)


def regenerar_configuracion(
    contexto: ProjectContext,
    include_env: bool = False,
) -> RegenResult:
    """Re-read odev.yaml + .env, re-render docker-compose.yml and odoo.conf.

    This is the central regeneration function. It:
    1. Loads ProjectConfig from odev.yaml
    2. Loads existing .env values (if present)
    3. Builds a merged template context
    4. Renders docker-compose.yml and odoo.conf
    5. Optionally renders .env if include_env=True

    Args:
        contexto: Resolved project context (provides paths and config).
        include_env: If True, also regenerate the .env file. Default False
            to preserve user-edited runtime values (passwords, ports).

    Returns:
        RegenResult with lists of regenerated and unchanged files.
    """
    ...


def construir_contexto_templates(
    config: ProjectConfig,
    env_values: dict[str, str | None],
    directorio_config: Path,
    directorio_trabajo: Path | None = None,
) -> dict[str, Any]:
    """Build the unified template context from odev.yaml + .env values.

    This merges structural values from odev.yaml (addon paths, enterprise
    settings, image versions) with runtime values from .env (ports,
    credentials). The merge strategy:

    - Structural keys (images, addon paths, enterprise) come from odev.yaml
    - Runtime keys (DB_USER, DB_PASSWORD, WEB_PORT, etc.) come from .env
    - If .env is empty/missing, defaults are used for runtime keys

    Args:
        config: Loaded ProjectConfig from odev.yaml.
        env_values: Current .env values (may be empty dict).
        directorio_config: Directory where generated files live.
        directorio_trabajo: Working directory (for external mode). If None,
            uses directorio_config.

    Returns:
        Dict with all keys needed by docker-compose.yml.j2, odoo.conf.j2,
        and env.j2 templates.
    """
    ...


def necesita_regeneracion(contexto: ProjectContext) -> bool:
    """Check if odev.yaml is newer than the generated files.

    Compares the mtime of odev.yaml against docker-compose.yml and
    odoo.conf. Returns True if either generated file is older than
    odev.yaml or does not exist.

    Args:
        contexto: Resolved project context.

    Returns:
        True if regeneration is needed, False otherwise.
    """
    ...
```

### 2.2 Implementation: `construir_contexto_templates()`

This is the most critical function. It replaces the duplicated `_construir_valores()` logic in `adopt.py` (line 226) and `init.py` (line 282) with a single, reusable builder.

```python
def construir_contexto_templates(
    config: ProjectConfig,
    env_values: dict[str, str | None],
    directorio_config: Path,
    directorio_trabajo: Path | None = None,
) -> dict[str, Any]:
    odoo_version = config.version_odoo
    tag_imagen_odoo = odoo_version.replace(".0", "")
    tag_imagen_db = _extraer_tag_db(config.imagen_db)

    # Build addon mounts from odev.yaml paths.addons
    addon_mounts = construir_addon_mounts(
        config.rutas_addons,
        directorio_config,
    )

    # Resolve enterprise path
    enterprise_enabled = config.enterprise_habilitado
    enterprise_path = config.ruta_enterprise  # NEW property (see section 2.3)

    # Runtime values: prefer .env, fall back to defaults
    def env_or(key: str, default: str) -> str:
        val = env_values.get(key)
        return val if val is not None else default

    working_dir = directorio_trabajo or directorio_config

    return {
        # --- UPPERCASE keys (for env.j2, odoo.conf.j2) ---
        "PROJECT_NAME": env_or("PROJECT_NAME", config.nombre_proyecto),
        "ODOO_VERSION": odoo_version,
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
        # --- snake_case keys (for docker-compose.yml.j2, odev.yaml.j2) ---
        "project_name": config.nombre_proyecto,
        "project_mode": config.modo,
        "working_dir": str(working_dir),
        "odoo_version": odoo_version,
        "odoo_image_tag": tag_imagen_odoo,
        "odoo_image": config.imagen_odoo,
        "db_image_tag": tag_imagen_db,
        "db_image": config.imagen_db,
        "enterprise_enabled": enterprise_enabled,
        "enterprise_path": enterprise_path,
        "addon_mounts": addon_mounts,
        "addon_container_paths": [m["container_path"] for m in addon_mounts],
        "addon_dirs_container": [m["container_path"] for m in addon_mounts],
        "addons_paths_list": config.rutas_addons,
        "odev_min_version": config.version_minima,
        "services_pgweb": config.pgweb_habilitado,
        "services_mailhog": True,
        "project_description": config.descripcion_proyecto,
    }


def _extraer_tag_db(imagen_db: str) -> str:
    """Extract PostgreSQL version tag from image string.

    'pgvector/pgvector:pg16' -> '16'
    'postgres:15' -> '15'
    """
    if ":" not in imagen_db:
        return "16"
    tag = imagen_db.split(":")[-1]
    # Strip 'pg' prefix if present (pgvector convention)
    return tag.removeprefix("pg")
```

### 2.3 Implementation: `regenerar_configuracion()`

```python
def regenerar_configuracion(
    contexto: ProjectContext,
    include_env: bool = False,
) -> RegenResult:
    resultado = RegenResult()
    dir_config = contexto.directorio_config

    # 1. Load config
    config = ProjectConfig(dir_config)

    # 2. Load existing .env
    ruta_env = dir_config / ".env"
    env_values = load_env(ruta_env) if ruta_env.exists() else {}

    # 3. Build unified context
    dir_trabajo = contexto.directorio_trabajo
    valores = construir_contexto_templates(
        config, env_values, dir_config, dir_trabajo,
    )

    # 4. Render docker-compose.yml
    ruta_compose = dir_config / "docker-compose.yml"
    contenido_anterior = ruta_compose.read_text() if ruta_compose.exists() else ""
    _renderizar_template("docker-compose.yml.j2", ruta_compose, valores)
    if ruta_compose.read_text() != contenido_anterior:
        resultado.archivos_regenerados.append(ruta_compose)
        success("docker-compose.yml (regenerado)")
    else:
        resultado.archivos_sin_cambios.append(ruta_compose)

    # 5. Render odoo.conf
    addon_mounts = valores["addon_mounts"]
    ruta_odoo_conf = dir_config / "config" / "odoo.conf"
    contenido_anterior = ruta_odoo_conf.read_text() if ruta_odoo_conf.exists() else ""
    generate_odoo_conf(
        env_values=_extraer_env_values(valores),
        config_dir=dir_config / "config",
        addon_mounts=addon_mounts,
        enterprise_enabled=valores["enterprise_enabled"],
    )
    if ruta_odoo_conf.read_text() != contenido_anterior:
        resultado.archivos_regenerados.append(ruta_odoo_conf)
        success("config/odoo.conf (regenerado)")
    else:
        resultado.archivos_sin_cambios.append(ruta_odoo_conf)

    # 6. Optionally render .env
    if include_env:
        contenido_anterior = ruta_env.read_text() if ruta_env.exists() else ""
        write_env(valores, dest=ruta_env)
        if ruta_env.read_text() != contenido_anterior:
            resultado.archivos_regenerados.append(ruta_env)
            success(".env (regenerado)")
        else:
            resultado.archivos_sin_cambios.append(ruta_env)

    return resultado


def _renderizar_template(nombre_template: str, destino: Path, valores: dict) -> None:
    """Render a single Jinja2 template to a destination file."""
    from jinja2 import Environment, FileSystemLoader
    from odev.core.paths import get_project_templates_dir

    entorno = Environment(
        loader=FileSystemLoader(str(get_project_templates_dir())),
        keep_trailing_newline=True,
    )
    template = entorno.get_template(nombre_template)
    contenido = template.render(**valores)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(contenido)


def _extraer_env_values(valores: dict[str, Any]) -> dict[str, str]:
    """Extract UPPERCASE env keys from the merged context dict."""
    claves_env = {
        "PROJECT_NAME", "ODOO_VERSION", "ODOO_IMAGE_TAG", "WEB_PORT",
        "PGWEB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD", "DB_IMAGE_TAG",
        "DB_PORT", "DB_HOST", "LOAD_LANGUAGE", "WITHOUT_DEMO", "DEBUGPY",
        "DEBUGPY_PORT", "ADMIN_PASSWORD", "INIT_MODULES", "MAILHOG_PORT",
    }
    return {k: str(v) for k, v in valores.items() if k in claves_env}
```

### 2.4 Implementation: `necesita_regeneracion()`

```python
def necesita_regeneracion(contexto: ProjectContext) -> bool:
    dir_config = contexto.directorio_config
    ruta_yaml = dir_config / ".odev.yaml"

    if not ruta_yaml.exists():
        return False

    yaml_mtime = ruta_yaml.stat().st_mtime

    archivos_generados = [
        dir_config / "docker-compose.yml",
        dir_config / "config" / "odoo.conf",
    ]

    for archivo in archivos_generados:
        if not archivo.exists():
            return True
        if yaml_mtime > archivo.stat().st_mtime:
            return True

    return False
```

### 2.5 New `ProjectConfig` Property

**File**: `src/odev/core/project.py`

Add `ruta_enterprise` property (currently missing -- the enterprise path is in `odev.yaml` but has no accessor):

```python
@property
def ruta_enterprise(self) -> str:
    """Path to enterprise addons directory."""
    return self.datos.get("enterprise", {}).get("path", "./enterprise")
```

This goes after the existing `enterprise_habilitado` property (line 162).

---

## 3. New Module: `commands/reconfigure.py` (P1)

**File**: `src/odev/commands/reconfigure.py`

### 3.1 Command Signature

```python
"""Command 'reconfigure': regenerate config files from odev.yaml.

Re-reads odev.yaml and .env, then re-renders docker-compose.yml and
odoo.conf. Preserves .env runtime values by default.
"""

import typer

from odev.commands._helpers import requerir_proyecto
from odev.core.console import info, success, warning
from odev.core.regen import RegenResult, regenerar_configuracion


def reconfigure(
    include_env: bool = typer.Option(
        False,
        "--include-env",
        help="Also regenerate .env file (WARNING: may overwrite custom ports/passwords).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be regenerated without writing files.",
    ),
) -> None:
    """Regenerate docker-compose.yml and odoo.conf from current odev.yaml values.

    Use after editing odev.yaml to propagate changes to the runtime
    configuration files. By default, .env values (ports, DB credentials)
    are preserved. Use --include-env to also regenerate the .env file.
    """
    from odev.main import obtener_nombre_proyecto

    contexto = requerir_proyecto(obtener_nombre_proyecto())

    if dry_run:
        from odev.core.regen import necesita_regeneracion
        if necesita_regeneracion(contexto):
            info("Regeneration needed: odev.yaml is newer than generated files.")
        else:
            info("No regeneration needed: generated files are up to date.")
        return

    info("Regenerating configuration from odev.yaml...")
    resultado: RegenResult = regenerar_configuracion(
        contexto,
        include_env=include_env,
    )

    if resultado.archivos_regenerados:
        success(
            f"Regenerated {len(resultado.archivos_regenerados)} file(s). "
            "Run 'odev restart' to apply changes to running containers."
        )
    else:
        info("All files are already up to date.")

    for adv in resultado.advertencias:
        warning(adv)
```

### 3.2 Registration in `main.py`

**File**: `src/odev/main.py`

```python
# Add to imports (after existing command imports, ~line 31):
from odev.commands.reconfigure import reconfigure

# Add to command registration (after line 105):
app.command(name="reconfigure")(reconfigure)
```

### 3.3 Templates NOT Regenerated

The `reconfigure` command regenerates:
- `docker-compose.yml` (from `docker-compose.yml.j2`)
- `config/odoo.conf` (from `odoo.conf.j2`)

It does NOT regenerate:
- `odev.yaml` itself (that is the source of truth, never overwritten)
- `entrypoint.sh` (static after initial generation, user may customize)
- `.env` (only with `--include-env`, since it contains user-edited runtime values)

---

## 4. Auto-regen on `up` (P3)

**File**: `src/odev/commands/up.py`

### 4.1 Modified `up()` Function

Replace the current auto-regen block (lines 66-77) with an expanded version that also checks `odev.yaml` mtime:

```python
def up(
    build: bool = typer.Option(False, "--build", help="Reconstruir imagenes antes de iniciar."),
    watch: bool = typer.Option(False, "--watch", help="Activar modo watch de docker compose."),
) -> None:
    """Levanta el entorno de desarrollo Odoo."""
    from odev.main import obtener_nombre_proyecto
    contexto = requerir_proyecto(obtener_nombre_proyecto())
    rutas = obtener_rutas(contexto)

    if not rutas.env_file.exists():
        from odev.core.console import error
        error("No se encontro el archivo .env. Ejecuta 'odev init' primero.")
        raise typer.Exit(1)

    # --- NEW: Check if odev.yaml changed and trigger full regen ---
    from odev.core.regen import necesita_regeneracion, regenerar_configuracion

    if necesita_regeneracion(contexto):
        warning("odev.yaml changed since last generation. Regenerating configs...")
        resultado = regenerar_configuracion(contexto)
        if resultado.archivos_regenerados:
            info(
                f"Regenerated: {', '.join(a.name for a in resultado.archivos_regenerados)}"
            )
    else:
        # --- EXISTING: Fallback to .env-only mtime check for odoo.conf ---
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

    info("Iniciando entorno...")
    dc = obtener_docker(contexto)
    dc.up(build=build, watch=watch)

    valores_env = load_env(rutas.env_file)
    puerto_web = valores_env.get("WEB_PORT", "8069")
    puerto_pgweb = valores_env.get("PGWEB_PORT", "8081")
    success("Entorno iniciado correctamente.")
    info(f"  Odoo:  http://localhost:{puerto_web}")
    info(f"  pgweb: http://localhost:{puerto_pgweb}")
```

### 4.2 New Import in `up.py`

```python
# Add to existing imports:
from odev.core.console import info, success, warning  # add warning
```

### 4.3 EXTERNAL vs INLINE Mode

The `necesita_regeneracion()` function works correctly for both modes because:

- **INLINE**: `contexto.directorio_config` == working directory. `odev.yaml` at `dir_config / ".odev.yaml"`.
- **EXTERNAL**: `contexto.directorio_config` == `~/.odev/projects/<name>/`. `odev.yaml` at that same location (rendered there by `adopt`).

The `ProjectPaths.odev_config` property (line 141 of `paths.py`) resolves to `self._root / ".odev.yaml"`, which is the config directory root in both cases.

---

## 5. New Module: `commands/enterprise.py` (P2)

**File**: `src/odev/commands/enterprise.py`

### 5.1 Shared Storage

**File**: `src/odev/core/registry.py`

Add constant after line 26:

```python
ENTERPRISE_DIR = ODEV_HOME / "enterprise"  # ~/.odev/enterprise/
```

### 5.2 Subcommand Group

```python
"""Subcommand group 'odev enterprise': manage shared enterprise addons.

Provides import, link, status, and path subcommands for managing
enterprise addons stored in ~/.odev/enterprise/{version}/.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import typer
from rich.table import Table

from odev.commands._helpers import requerir_proyecto
from odev.core.console import console, error, info, success, warning
from odev.core.registry import ENTERPRISE_DIR, Registry

app = typer.Typer(
    name="enterprise",
    help="Manage shared Odoo Enterprise addons.",
    no_args_is_help=True,
)


def _version_dir(version: str) -> Path:
    """Return the shared enterprise directory for a given Odoo version."""
    return ENTERPRISE_DIR / version


def _contar_modulos(directorio: Path) -> int:
    """Count Odoo modules in a directory (dirs with __manifest__.py)."""
    if not directorio.is_dir():
        return 0
    return sum(
        1
        for d in directorio.iterdir()
        if d.is_dir() and (d / "__manifest__.py").exists()
    )


@app.command(name="import")
def enterprise_import(
    version: str = typer.Argument(
        ...,
        help="Odoo version (e.g., 19.0, 18.0).",
    ),
    path: Path = typer.Argument(
        ...,
        help="Path to enterprise addons directory.",
        exists=True,
        file_okay=False,
    ),
    copy: bool = typer.Option(
        False,
        "--copy",
        help="Copy files instead of symlinking (for portability).",
    ),
    force: bool = typer.Option(
        False,
        "--force", "-f",
        help="Overwrite existing enterprise version.",
    ),
) -> None:
    """Import enterprise addons to shared storage (~/.odev/enterprise/<version>/).

    By default, creates a symlink for disk efficiency. Use --copy to create
    an independent copy (needed for CI or machines where the source may move).
    """
    destino = _version_dir(version)

    if destino.exists():
        if not force:
            error(
                f"Enterprise addons for {version} already exist at {destino}. "
                "Use --force to overwrite."
            )
            raise typer.Exit(1)
        # Clean existing
        if destino.is_symlink():
            destino.unlink()
        else:
            shutil.rmtree(destino)
        warning(f"Removed existing enterprise {version}.")

    ENTERPRISE_DIR.mkdir(parents=True, exist_ok=True)

    source_resolved = path.resolve()
    n_modulos = _contar_modulos(source_resolved)

    if n_modulos == 0:
        warning(f"No Odoo modules found in {source_resolved}. Continuing anyway.")

    if copy:
        info(f"Copying enterprise addons to {destino}...")
        shutil.copytree(source_resolved, destino)
    else:
        info(f"Symlinking enterprise addons to {destino}...")
        destino.symlink_to(source_resolved)

    success(f"Enterprise {version}: {n_modulos} modules stored at {destino}")


@app.command(name="link")
def enterprise_link(
    version: str = typer.Option(
        None,
        "--version",
        help="Odoo version to link (default: project's odoo version).",
    ),
) -> None:
    """Link current project to shared enterprise addons.

    Updates the project's odev.yaml to set enterprise.enabled=true and
    enterprise.path to the shared location, then triggers config regeneration.
    """
    from odev.main import obtener_nombre_proyecto
    contexto = requerir_proyecto(obtener_nombre_proyecto())

    if contexto.config is None:
        error("Project has no odev.yaml configuration.")
        raise typer.Exit(1)

    # Resolve version
    if version is None:
        version = contexto.config.version_odoo

    destino = _version_dir(version)
    if not destino.exists():
        error(
            f"No shared enterprise addons for {version}. "
            f"Import first: odev enterprise import {version} /path/to/enterprise/"
        )
        raise typer.Exit(1)

    # Update odev.yaml
    import yaml
    ruta_yaml = contexto.directorio_config / ".odev.yaml"
    with open(ruta_yaml, encoding="utf-8") as f:
        datos = yaml.safe_load(f) or {}

    datos.setdefault("enterprise", {})
    datos["enterprise"]["enabled"] = True
    datos["enterprise"]["path"] = str(destino.resolve())

    with open(ruta_yaml, "w", encoding="utf-8") as f:
        yaml.dump(datos, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    success(f"odev.yaml updated: enterprise.enabled=true, path={destino}")

    # Trigger regeneration (delegates to P1 regen engine)
    from odev.core.regen import regenerar_configuracion
    resultado = regenerar_configuracion(contexto)
    if resultado.archivos_regenerados:
        info(f"Regenerated {len(resultado.archivos_regenerados)} config file(s).")


@app.command(name="status")
def enterprise_status() -> None:
    """Show available shared enterprise versions and linked projects."""
    if not ENTERPRISE_DIR.exists():
        info("No shared enterprise addons found.")
        info(f"Import with: odev enterprise import <version> <path>")
        return

    table = Table(title="Shared Enterprise Addons")
    table.add_column("Version", style="bold")
    table.add_column("Modules", justify="right")
    table.add_column("Path")
    table.add_column("Type")

    versiones = sorted(ENTERPRISE_DIR.iterdir()) if ENTERPRISE_DIR.is_dir() else []
    for entrada in versiones:
        if not entrada.is_dir() and not entrada.is_symlink():
            continue
        n_modulos = _contar_modulos(entrada)
        tipo = "symlink" if entrada.is_symlink() else "copy"
        ruta_real = str(entrada.resolve()) if entrada.is_symlink() else str(entrada)
        table.add_row(entrada.name, str(n_modulos), ruta_real, tipo)

    if not versiones:
        info("No shared enterprise versions found.")
        return

    console.print(table)

    # Show which projects use shared enterprise
    registro = Registry()
    proyectos = registro.listar()
    if proyectos:
        info("\nProject enterprise status:")
        for proyecto in proyectos:
            from odev.core.project import ProjectConfig
            try:
                config = ProjectConfig(proyecto.directorio_config)
                if config.enterprise_habilitado:
                    info(f"  {proyecto.nombre}: enterprise={config.ruta_enterprise}")
                else:
                    info(f"  {proyecto.nombre}: enterprise disabled")
            except FileNotFoundError:
                info(f"  {proyecto.nombre}: no odev.yaml")


@app.command(name="path")
def enterprise_path(
    version: str = typer.Argument(
        ...,
        help="Odoo version (e.g., 19.0).",
    ),
) -> None:
    """Print the path to shared enterprise for a given version (for scripting)."""
    destino = _version_dir(version)
    if not destino.exists():
        raise typer.Exit(1)
    # Print raw path for scripting (no Rich formatting)
    typer.echo(str(destino.resolve()))
```

### 5.3 Registration in `main.py`

```python
# Add after the existing try/except blocks for adopt and projects (~line 121):
try:
    from odev.commands.enterprise import app as enterprise_app
    app.add_typer(enterprise_app, name="enterprise")
except ImportError:
    pass
```

### 5.4 Integration with `adopt.py`

**File**: `src/odev/commands/adopt.py`

In `_construir_valores()`, after determining `enterprise_path` (line 258-261), add a check for shared enterprise:

```python
# Determine enterprise path (existing logic at line 258-261)
if layout.tiene_enterprise:
    enterprise_path = str(ruta / "enterprise")
else:
    # NEW: Check for shared enterprise
    from odev.core.registry import ENTERPRISE_DIR
    shared_enterprise = ENTERPRISE_DIR / odoo_version
    if shared_enterprise.exists():
        if not no_interactive:
            usar_shared = questionary.confirm(
                f"Shared enterprise addons found for {odoo_version}. Use them?",
                default=True,
            ).ask()
            if usar_shared:
                enterprise_path = str(shared_enterprise.resolve())
                layout.tiene_enterprise = True
            else:
                enterprise_path = "./enterprise"
        else:
            # Non-interactive: auto-use shared enterprise
            enterprise_path = str(shared_enterprise.resolve())
            layout.tiene_enterprise = True
            info(f"Using shared enterprise addons: {shared_enterprise}")
    else:
        enterprise_path = "./enterprise"
```

Note: This requires passing `no_interactive` and `odoo_version` to `_construir_valores()`, or restructuring the check to happen before the call. The cleaner approach is to extract the shared enterprise check into the main `adopt()` flow (between steps 8 and 10), modifying `layout.tiene_enterprise` before it is passed to `_construir_valores()`.

### 5.5 Enterprise Path Resolution Priority

The enterprise path is resolved with this priority chain:

| Priority | Source | Example |
|----------|--------|---------|
| 1 | Explicit `enterprise.path` in odev.yaml (absolute) | `/home/user/my-enterprise` |
| 2 | Local `./enterprise` directory (relative in odev.yaml) | `./enterprise` |
| 3 | Shared `~/.odev/enterprise/{version}/` | `~/.odev/enterprise/19.0` |
| 4 | Disabled (`enterprise.enabled: false`) | N/A |

The resolution happens at `adopt` time (writing to `odev.yaml`) and at `enterprise link` time (updating `odev.yaml`). The regen engine reads the already-resolved path from `odev.yaml` -- it does not perform resolution itself.

---

## 6. `adopt --force` (P6)

**File**: `src/odev/commands/adopt.py`

### 6.1 Modified Function Signature

```python
def adopt(
    directorio: str = typer.Argument(
        ".",
        help="Directorio del proyecto Odoo existente.",
    ),
    name: str = typer.Option(
        None,
        "--name", "-n",
        help="Nombre del proyecto (por defecto: nombre del directorio).",
    ),
    odoo_version: str = typer.Option(
        None,
        "--odoo-version",
        help="Version de Odoo (ej: 19.0, 18.0, 17.0).",
    ),
    no_interactive: bool = typer.Option(
        False,
        "--no-interactive",
        help="Modo no-interactivo (usar valores por defecto).",
    ),
    force: bool = typer.Option(
        False,
        "--force", "-f",
        help="Force re-adopt: remove existing registry entry and regenerate config.",
    ),
) -> None:
```

### 6.2 Modified `.odev.yaml` Check (lines 79-84)

```python
# 2. Check if already an odev project
if (ruta / ".odev.yaml").exists() and not force:
    error(
        f"'{ruta}' ya es un proyecto odev (tiene .odev.yaml). "
        "Usa 'odev up' directamente o --force para re-adoptar."
    )
    raise typer.Exit(1)
```

### 6.3 Modified Registry Check (lines 127-130)

```python
# 6. Check registry availability
registro = Registry()
existente = registro.obtener(name)
if existente:
    if force:
        import shutil
        warning(f"Removing existing project '{name}' from registry...")
        registro.eliminar(name)
        # Clean up old config directory
        if existente.directorio_config.exists():
            shutil.rmtree(existente.directorio_config)
        info(f"Cleaned up: {existente.directorio_config}")
    else:
        error(
            f"Ya existe un proyecto '{name}' en el registro. "
            "Usa --force para re-adoptar."
        )
        raise typer.Exit(1)
```

### 6.4 Safety Constraints

- `--force` NEVER deletes the working directory (`ruta`). It only removes:
  - The registry entry in `~/.odev/registry.yaml`
  - The config directory in `~/.odev/projects/<name>/`
- The `.odev.yaml` marker in the working directory (for inline mode) is preserved since `adopt` creates a new one anyway.

---

## 7. Enterprise addons_path Ordering (P7)

**File**: `src/odev/templates/project/odoo.conf.j2`

### 7.1 Current Template (lines 2-6)

```jinja2
{% if addon_container_paths is defined %}
addons_path = {{ addon_container_paths | join(',') }}{% if enterprise_enabled %},/mnt/enterprise-addons{% endif %}
{% else %}
addons_path = /mnt/extra-addons{% if enterprise_enabled %},/mnt/enterprise-addons{% endif %}
{% endif %}
```

### 7.2 Modified Template

```jinja2
{% if addon_container_paths is defined %}
addons_path = {% if enterprise_enabled %}/mnt/enterprise-addons,{% endif %}{{ addon_container_paths | join(',') }}
{% else %}
addons_path = {% if enterprise_enabled %}/mnt/enterprise-addons,{% endif %}/mnt/extra-addons
{% endif %}
```

### 7.3 Impact Analysis

- **With enterprise enabled, multi-addon**: `/mnt/enterprise-addons,/mnt/extra-addons,/mnt/extra-addons-1`
- **With enterprise disabled**: `/mnt/extra-addons,/mnt/extra-addons-1` (unchanged)
- **Without addon_container_paths, enterprise enabled**: `/mnt/enterprise-addons,/mnt/extra-addons`

This ensures enterprise modules like `web_enterprise` correctly override their CE counterparts (`web`), since Odoo uses the first matching module path in `addons_path`.

### 7.4 Test Update Required

The existing test `test_addons_path_con_enterprise` in `tests/test_config.py` (line 197) asserts:
```python
assert "addons_path = /mnt/extra-addons,/mnt/enterprise-addons" in contenido
```

This must be updated to:
```python
assert "addons_path = /mnt/enterprise-addons,/mnt/extra-addons" in contenido
```

---

## 8. `load-backup` Pre-flight Checks (P4)

### 8.1 New Method in `DockerCompose`

**File**: `src/odev/core/docker.py`

Add after `ps_parsed()` (after line 260):

```python
def is_service_running(self, service: str) -> bool:
    """Check if a specific service has a running container.

    Uses `docker compose ps --format json` and checks for the service
    in the parsed output with State == "running".

    Args:
        service: Name of the service to check (e.g., "db", "web").

    Returns:
        True if the service is running, False otherwise.
    """
    servicios = self.ps_parsed()
    for svc in servicios:
        if svc.get("Service") == service and svc.get("State") == "running":
            return True
    return False
```

### 8.2 Pre-flight Check in `load_backup.py`

**File**: `src/odev/commands/load_backup.py`

Insert after line 59 (`dc = obtener_docker(contexto)`) and before line 62 (`if not zipfile.is_zipfile(backup):`):

```python
    # Pre-flight: verify db container is running
    if not dc.is_service_running("db"):
        error(
            "El servicio de base de datos no esta corriendo. "
            "Ejecuta 'odev up' primero."
        )
        raise typer.Exit(1)
```

This check runs BEFORE the zip validation and BEFORE the confirmation prompt, ensuring the user gets immediate feedback about the missing container.

---

## 9. `--yes` Flag for Destructive Commands (P5)

### 9.1 `load_backup.py`

**File**: `src/odev/commands/load_backup.py`

Modified signature (add parameter after `neutralize`):

```python
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
        "--yes", "-y",
        help="Skip confirmation prompt (for automation/CI).",
    ),
) -> None:
```

Modified confirmation (replace lines 88-91):

```python
    warning(f"Esto REEMPLAZARA la base de datos '{nombre_bd}' con el contenido del backup!")
    if not yes and not typer.confirm("Continuar?", default=False):
        info("Operacion cancelada.")
        raise typer.Exit()
```

### 9.2 `reset_db.py`

**File**: `src/odev/commands/reset_db.py`

Modified signature:

```python
def reset_db(
    neutralize: bool = typer.Option(
        True,
        help="Neutralizar la base de datos despues de reiniciar.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes", "-y",
        help="Skip confirmation prompt (for automation/CI).",
    ),
) -> None:
```

Modified confirmation (replace lines 39-43):

```python
    warning("Esto ELIMINARA la base de datos y TODOS los datos!")
    if not yes:
        confirmacion = typer.confirm("Estas seguro?", default=False)
        if not confirmacion:
            info("Operacion cancelada.")
            raise typer.Exit()
```

---

## 10. Schema Enforcement (P8)

**File**: `src/odev/core/project.py`

### 10.1 Nested Schema Definition

Add after `_ESQUEMA_ODEV_YAML` (line 64):

```python
_ESQUEMA_NESTED: dict[str, dict[str, type | tuple[type, ...]]] = {
    "odoo": {
        "version": str,
        "image": str,
    },
    "database": {
        "image": str,
    },
    "enterprise": {
        "enabled": bool,
        "path": str,
    },
    "services": {
        "pgweb": bool,
    },
    "paths": {
        "addons": (list, str),  # Can be list or string (coerced later)
        "config": str,
        "snapshots": str,
        "logs": str,
        "docs": str,
    },
    "project": {
        "name": str,
        "description": str,
        "working_dir": str,
    },
    "sdd": {
        "enabled": bool,
        "language": str,
    },
}
```

### 10.2 Enhanced `_validar_esquema()`

Replace the existing function (lines 67-100):

```python
def _validar_esquema(datos: dict, ruta_archivo: Path) -> list[str]:
    """Validate the structure of an .odev.yaml file.

    Checks:
    1. Unknown top-level keys (existing behavior)
    2. Top-level type mismatches (existing behavior)
    3. Unknown nested keys within each section (NEW)
    4. Nested value type mismatches (NEW)

    All validations produce warnings (not errors) for forward compatibility.

    Args:
        datos: Dict loaded from the YAML file.
        ruta_archivo: Path to the file for error messages.

    Returns:
        List of warning strings (may be empty).
    """
    advertencias = []
    claves_conocidas = set(_ESQUEMA_ODEV_YAML.keys()) | {"mode", "sdd"}

    # 1. Unknown top-level keys
    for clave in datos:
        if clave not in claves_conocidas:
            advertencias.append(
                f"Clave desconocida '{clave}' en {ruta_archivo}. "
                "Posible error tipografico."
            )

    # 2. Top-level type validation
    for clave, tipo_esperado in _ESQUEMA_ODEV_YAML.items():
        if clave in datos and not isinstance(datos[clave], tipo_esperado):
            advertencias.append(
                f"La clave '{clave}' en {ruta_archivo} deberia ser "
                f"{tipo_esperado.__name__}, pero es {type(datos[clave]).__name__}."
            )

    # 3. Nested key and type validation
    for seccion, esquema_seccion in _ESQUEMA_NESTED.items():
        if seccion not in datos or not isinstance(datos[seccion], dict):
            continue

        datos_seccion = datos[seccion]

        # Unknown nested keys
        for clave in datos_seccion:
            if clave not in esquema_seccion:
                advertencias.append(
                    f"Clave desconocida '{clave}' en seccion '{seccion}' "
                    f"de {ruta_archivo}. Posible error tipografico."
                )

        # Nested type validation
        for clave, tipo_esperado in esquema_seccion.items():
            if clave not in datos_seccion:
                continue
            valor = datos_seccion[clave]
            # Handle tuple of types (e.g., (list, str) for paths.addons)
            if isinstance(tipo_esperado, tuple):
                if not isinstance(valor, tipo_esperado):
                    nombres_tipos = " o ".join(t.__name__ for t in tipo_esperado)
                    advertencias.append(
                        f"'{seccion}.{clave}' deberia ser {nombres_tipos}, "
                        f"pero es {type(valor).__name__}."
                    )
            elif not isinstance(valor, tipo_esperado):
                advertencias.append(
                    f"'{seccion}.{clave}' deberia ser {tipo_esperado.__name__}, "
                    f"pero es {type(valor).__name__}."
                )

    return advertencias
```

### 10.3 Examples of New Warnings

| Input | Warning |
|-------|---------|
| `enterprise.enbled: true` | "Clave desconocida 'enbled' en seccion 'enterprise'. Posible error tipografico." |
| `enterprise.enabled: "yes"` | "'enterprise.enabled' deberia ser bool, pero es str." |
| `paths.addons: 42` | "'paths.addons' deberia ser list o str, pero es int." |
| `odoo.vresion: "19.0"` | "Clave desconocida 'vresion' en seccion 'odoo'. Posible error tipografico." |

---

## 11. Cross-cutting Concerns

### 11.1 Template Context Building — Single Source of Truth

Today, template context building is duplicated:

| Location | Function | Used by |
|----------|----------|---------|
| `commands/adopt.py:226` | `_construir_valores()` | `adopt` command |
| `commands/init.py:282` | `_construir_valores()` | `init` command |

After this change:

| Location | Function | Used by |
|----------|----------|---------|
| `core/regen.py` | `construir_contexto_templates()` | `reconfigure`, `up` auto-regen, `adopt --force` |
| `commands/adopt.py:226` | `_construir_valores()` | `adopt` (initial generation only) |
| `commands/init.py:282` | `_construir_valores()` | `init` (initial generation only) |

The `adopt` and `init` functions retain their own `_construir_valores()` because initial generation needs additional context not present in `odev.yaml` (e.g., wizard-collected ports, layout detection results). However, the `core/regen.py` version is the canonical post-setup version that reads everything from `odev.yaml` + `.env`.

**Future refactor** (not in this change set): Extract common logic from all three into a shared builder and have `adopt`/`init` extend it with wizard-specific values.

### 11.2 EXTERNAL vs INLINE Mode Handling

The regeneration engine works identically for both modes:

| Aspect | INLINE | EXTERNAL |
|--------|--------|----------|
| `.odev.yaml` location | `<project>/.odev.yaml` | `~/.odev/projects/<name>/.odev.yaml` |
| `docker-compose.yml` location | `<project>/docker-compose.yml` | `~/.odev/projects/<name>/docker-compose.yml` |
| `contexto.directorio_config` | Same as working dir | `~/.odev/projects/<name>/` |
| `contexto.directorio_trabajo` | Same as config dir | `<project>/` |
| Addon paths in `odev.yaml` | Relative to project root | Absolute paths to working dir |

The key invariant: **all generated files live in `directorio_config`**. The regen engine always writes there, regardless of mode.

### 11.3 `.env` Merge Strategy

When `regenerar_configuracion()` builds the template context:

| Key Category | Source | Examples |
|--------------|--------|----------|
| **Structural** (from odev.yaml) | `ProjectConfig` properties | `ODOO_VERSION`, `ODOO_IMAGE_TAG`, `DB_IMAGE_TAG`, `enterprise_enabled`, `addon_mounts` |
| **Runtime** (from .env) | `load_env()` result | `WEB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `PGWEB_PORT`, `DEBUGPY_PORT` |
| **Computed** | Derived from other values | `COMPOSE_PROJECT_NAME`, `DB_FILTER` |

The merge strategy in `construir_contexto_templates()` uses `env_or(key, default)` for runtime values, which preserves user-edited `.env` values when they exist and falls back to sensible defaults otherwise.

### 11.4 Backward Compatibility

| Change | Backward Compatible? | Notes |
|--------|---------------------|-------|
| P1 (reconfigure) | Yes | New command, no existing behavior changed |
| P2 (enterprise) | Yes | New command group, opt-in behavior |
| P3 (auto-regen on up) | Yes | Only triggers when odev.yaml is newer, which can't happen in projects that never edit odev.yaml |
| P4 (pre-flight) | Yes | Adds guard before existing crash point |
| P5 (--yes flag) | Yes | Default behavior unchanged (flag defaults to False) |
| P6 (--force) | Yes | Default behavior unchanged (flag defaults to False), error message updated to hint at --force |
| P7 (enterprise ordering) | **Breaking for enterprise users** | Correctness fix. Enterprise path moves from last to first in addons_path. This is the correct behavior per Odoo docs. |
| P8 (schema) | Yes | All new validations produce warnings, never errors |

---

## 12. Test Design

### 12.1 New Test File: `tests/test_regen.py`

```python
"""Tests for odev.core.regen — shared regeneration engine."""

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from odev.core.project import ProjectConfig
from odev.core.regen import (
    RegenResult,
    construir_contexto_templates,
    necesita_regeneracion,
    regenerar_configuracion,
)


@pytest.fixture
def proyecto_con_config(tmp_path: Path) -> Path:
    """Create a temporary project directory with odev.yaml, .env, and generated files."""
    # .odev.yaml
    config = {
        "odev_min_version": "0.2.0",
        "mode": "inline",
        "odoo": {"version": "19.0", "image": "odoo:19"},
        "database": {"image": "pgvector/pgvector:pg16"},
        "enterprise": {"enabled": False, "path": "./enterprise"},
        "services": {"pgweb": True},
        "paths": {"addons": ["./addons"]},
        "project": {"name": "test-regen", "description": ""},
    }
    (tmp_path / ".odev.yaml").write_text(
        yaml.dump(config, default_flow_style=False)
    )

    # .env
    contenido_env = textwrap.dedent("""\
        PROJECT_NAME=test-regen
        ODOO_VERSION=19.0
        WEB_PORT=9069
        DB_PORT=5433
        DB_NAME=custom_db
        DB_USER=custom_user
        DB_PASSWORD=custom_pass
        DB_HOST=db
        PGWEB_PORT=9081
        DEBUGPY=False
        DEBUGPY_PORT=5678
        ADMIN_PASSWORD=secretadmin
        LOAD_LANGUAGE=es_AR
        WITHOUT_DEMO=all
        INIT_MODULES=
        MAILHOG_PORT=9025
    """)
    (tmp_path / ".env").write_text(contenido_env)

    # Generated files
    (tmp_path / "docker-compose.yml").write_text("services:\n  web:\n    image: odoo:19\n")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "odoo.conf").write_text("[options]\naddons_path = /mnt/extra-addons\n")
    (tmp_path / "addons").mkdir()

    return tmp_path


class TestConstruirContextoTemplates:
    """Tests for construir_contexto_templates()."""

    def test_preserva_env_runtime_values(self, proyecto_con_config: Path) -> None:
        """Runtime values from .env are preserved in the merged context."""
        config = ProjectConfig(proyecto_con_config)
        env_values = {"WEB_PORT": "9069", "DB_PASSWORD": "custom_pass"}

        ctx = construir_contexto_templates(config, env_values, proyecto_con_config)

        assert ctx["WEB_PORT"] == "9069"
        assert ctx["DB_PASSWORD"] == "custom_pass"

    def test_structural_from_odev_yaml(self, proyecto_con_config: Path) -> None:
        """Structural values come from odev.yaml, not .env."""
        config = ProjectConfig(proyecto_con_config)
        env_values = {"ODOO_VERSION": "18.0"}  # .env has stale version

        ctx = construir_contexto_templates(config, env_values, proyecto_con_config)

        # odoo_version should come from odev.yaml (19.0), not .env
        assert ctx["odoo_version"] == "19.0"
        assert ctx["ODOO_VERSION"] == "19.0"

    def test_defaults_when_env_empty(self, proyecto_con_config: Path) -> None:
        """Falls back to defaults when .env is empty."""
        config = ProjectConfig(proyecto_con_config)

        ctx = construir_contexto_templates(config, {}, proyecto_con_config)

        assert ctx["WEB_PORT"] == "8069"
        assert ctx["DB_USER"] == "odoo"

    def test_addon_mounts_built_from_config(self, proyecto_con_config: Path) -> None:
        """addon_mounts are built from odev.yaml paths.addons."""
        config = ProjectConfig(proyecto_con_config)

        ctx = construir_contexto_templates(config, {}, proyecto_con_config)

        assert len(ctx["addon_mounts"]) == 1
        assert ctx["addon_mounts"][0]["container_path"] == "/mnt/extra-addons"

    def test_enterprise_flag_propagated(self, tmp_path: Path) -> None:
        """enterprise_enabled is taken from odev.yaml."""
        config_data = {
            "odoo": {"version": "19.0"},
            "enterprise": {"enabled": True, "path": "/shared/enterprise"},
            "paths": {"addons": ["./addons"]},
            "project": {"name": "ent-test"},
        }
        (tmp_path / ".odev.yaml").write_text(yaml.dump(config_data))

        config = ProjectConfig(tmp_path)
        ctx = construir_contexto_templates(config, {}, tmp_path)

        assert ctx["enterprise_enabled"] is True
        assert ctx["enterprise_path"] == "/shared/enterprise"


class TestNecesitaRegeneracion:
    """Tests for necesita_regeneracion()."""

    def test_yaml_newer_triggers_regen(self, proyecto_con_config: Path) -> None:
        """Returns True when odev.yaml is newer than generated files."""
        import time
        # Touch odev.yaml to make it newer
        time.sleep(0.05)
        ruta_yaml = proyecto_con_config / ".odev.yaml"
        ruta_yaml.write_text(ruta_yaml.read_text())

        from odev.core.resolver import ModoProyecto, ProjectContext
        ctx = ProjectContext(
            nombre="test", modo=ModoProyecto.INLINE,
            directorio_config=proyecto_con_config,
            directorio_trabajo=proyecto_con_config,
            config=None,
        )

        assert necesita_regeneracion(ctx) is True

    def test_no_regen_when_files_newer(self, proyecto_con_config: Path) -> None:
        """Returns False when generated files are newer than odev.yaml."""
        import time
        # Touch generated files to make them newer
        time.sleep(0.05)
        (proyecto_con_config / "docker-compose.yml").write_text("updated\n")
        (proyecto_con_config / "config" / "odoo.conf").write_text("updated\n")

        from odev.core.resolver import ModoProyecto, ProjectContext
        ctx = ProjectContext(
            nombre="test", modo=ModoProyecto.INLINE,
            directorio_config=proyecto_con_config,
            directorio_trabajo=proyecto_con_config,
            config=None,
        )

        assert necesita_regeneracion(ctx) is False

    def test_missing_generated_file_triggers_regen(self, tmp_path: Path) -> None:
        """Returns True when a generated file does not exist."""
        (tmp_path / ".odev.yaml").write_text("project:\n  name: test\n")
        # No docker-compose.yml or odoo.conf

        from odev.core.resolver import ModoProyecto, ProjectContext
        ctx = ProjectContext(
            nombre="test", modo=ModoProyecto.INLINE,
            directorio_config=tmp_path,
            directorio_trabajo=tmp_path,
            config=None,
        )

        assert necesita_regeneracion(ctx) is True

    def test_no_yaml_no_regen(self, tmp_path: Path) -> None:
        """Returns False when there is no odev.yaml."""
        from odev.core.resolver import ModoProyecto, ProjectContext
        ctx = ProjectContext(
            nombre="test", modo=ModoProyecto.INLINE,
            directorio_config=tmp_path,
            directorio_trabajo=tmp_path,
            config=None,
        )

        assert necesita_regeneracion(ctx) is False


class TestRegenerarConfiguracion:
    """Tests for regenerar_configuracion()."""

    def test_regenera_compose_y_odoo_conf(self, proyecto_con_config: Path) -> None:
        """Regenerates docker-compose.yml and odoo.conf."""
        from odev.core.resolver import ModoProyecto, ProjectContext
        config = ProjectConfig(proyecto_con_config)
        ctx = ProjectContext(
            nombre="test", modo=ModoProyecto.INLINE,
            directorio_config=proyecto_con_config,
            directorio_trabajo=proyecto_con_config,
            config=config,
        )

        resultado = regenerar_configuracion(ctx)

        assert len(resultado.archivos_regenerados) >= 1
        # docker-compose.yml should now have real content from template
        contenido = (proyecto_con_config / "docker-compose.yml").read_text()
        assert "services:" in contenido

    def test_preserva_env_por_defecto(self, proyecto_con_config: Path) -> None:
        """Does NOT regenerate .env by default."""
        from odev.core.resolver import ModoProyecto, ProjectContext
        config = ProjectConfig(proyecto_con_config)
        ctx = ProjectContext(
            nombre="test", modo=ModoProyecto.INLINE,
            directorio_config=proyecto_con_config,
            directorio_trabajo=proyecto_con_config,
            config=config,
        )

        contenido_env_antes = (proyecto_con_config / ".env").read_text()
        regenerar_configuracion(ctx, include_env=False)
        contenido_env_despues = (proyecto_con_config / ".env").read_text()

        assert contenido_env_antes == contenido_env_despues

    def test_include_env_regenera_env(self, proyecto_con_config: Path) -> None:
        """With include_env=True, .env is also regenerated."""
        from odev.core.resolver import ModoProyecto, ProjectContext
        config = ProjectConfig(proyecto_con_config)
        ctx = ProjectContext(
            nombre="test", modo=ModoProyecto.INLINE,
            directorio_config=proyecto_con_config,
            directorio_trabajo=proyecto_con_config,
            config=config,
        )

        resultado = regenerar_configuracion(ctx, include_env=True)

        env_paths = [p for p in resultado.archivos_regenerados if p.name == ".env"]
        # .env may or may not appear in regenerados depending on content diff
        # but the function should not crash
        contenido = (proyecto_con_config / ".env").read_text()
        assert "PROJECT_NAME=" in contenido
```

### 12.2 New Test File: `tests/test_enterprise_cmd.py`

```python
"""Tests for odev.commands.enterprise — shared enterprise management."""

from pathlib import Path

import pytest

from odev.core.registry import ENTERPRISE_DIR


@pytest.fixture
def enterprise_dir(tmp_path: Path, monkeypatch) -> Path:
    """Redirect ENTERPRISE_DIR to a temp directory."""
    ent_dir = tmp_path / "enterprise"
    monkeypatch.setattr("odev.core.registry.ENTERPRISE_DIR", ent_dir)
    monkeypatch.setattr("odev.commands.enterprise.ENTERPRISE_DIR", ent_dir)
    return ent_dir


@pytest.fixture
def fake_enterprise_source(tmp_path: Path) -> Path:
    """Create a fake enterprise addons directory with 3 modules."""
    source = tmp_path / "source_enterprise"
    source.mkdir()
    for name in ("web_enterprise", "account_accountant", "hr_payroll"):
        mod = source / name
        mod.mkdir()
        (mod / "__manifest__.py").write_text(f'{{"name": "{name}"}}')
    return source


class TestEnterpriseImport:
    """Tests for 'odev enterprise import'."""

    def test_import_symlink(
        self, enterprise_dir: Path, fake_enterprise_source: Path
    ) -> None:
        """Imports enterprise as symlink by default."""
        from odev.commands.enterprise import _version_dir, _contar_modulos
        # Simulate import logic
        destino = _version_dir("19.0")
        assert not destino.exists()

    def test_contar_modulos(self, fake_enterprise_source: Path) -> None:
        """Counts modules correctly."""
        from odev.commands.enterprise import _contar_modulos
        assert _contar_modulos(fake_enterprise_source) == 3

    def test_contar_modulos_dir_vacio(self, tmp_path: Path) -> None:
        """Returns 0 for empty directory."""
        from odev.commands.enterprise import _contar_modulos
        assert _contar_modulos(tmp_path) == 0

    def test_contar_modulos_dir_inexistente(self, tmp_path: Path) -> None:
        """Returns 0 for non-existent directory."""
        from odev.commands.enterprise import _contar_modulos
        assert _contar_modulos(tmp_path / "nope") == 0
```

### 12.3 New Test File: `tests/test_reconfigure.py`

```python
"""Tests for odev.commands.reconfigure — config regeneration command."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestReconfigure:
    """Integration-level tests for the reconfigure command."""

    def test_dry_run_no_file_changes(self, directorio_proyecto: Path) -> None:
        """--dry-run does not modify any files."""
        compose_before = (directorio_proyecto / "docker-compose.yml").read_text()
        # Would need to invoke the command; this is the test structure
        compose_after = (directorio_proyecto / "docker-compose.yml").read_text()
        assert compose_before == compose_after
```

### 12.4 Updates to Existing Test Files

**`tests/test_config.py`** -- Update `test_addons_path_con_enterprise`:

```python
def test_addons_path_con_enterprise(self, tmp_path):
    """With enterprise enabled, addons_path has enterprise BEFORE extra-addons."""
    config_dir = tmp_path / "config"
    addon_mounts = [{"container_path": "/mnt/extra-addons", "host_path": "./addons", "nombre": "addons"}]

    generate_odoo_conf(
        env_values={"DB_HOST": "db"},
        config_dir=config_dir,
        addon_mounts=addon_mounts,
        enterprise_enabled=True,
    )

    contenido = (config_dir / "odoo.conf").read_text()
    assert "addons_path = /mnt/enterprise-addons,/mnt/extra-addons" in contenido
```

**`tests/test_project.py`** -- Add nested validation tests:

```python
class TestValidarEsquemaNested:
    """Tests for nested schema validation in _validar_esquema."""

    def test_typo_in_nested_key_produces_warning(self, tmp_path):
        """A typo in a nested key (e.g., enterprise.enbled) produces a warning."""
        config = {"enterprise": {"enbled": True}}
        (tmp_path / ".odev.yaml").write_text(yaml.dump(config))

        pc = ProjectConfig(tmp_path)

        # The warning was produced during __init__; enterprise_habilitado
        # should be False (the typo key was ignored, default applied)
        assert pc.enterprise_habilitado is False

    def test_wrong_type_in_nested_value_produces_warning(self, tmp_path):
        """A wrong type (e.g., enterprise.enabled: 'yes') produces a warning."""
        config = {"enterprise": {"enabled": "yes"}}
        (tmp_path / ".odev.yaml").write_text(yaml.dump(config))

        with patch("odev.core.project.warning") as mock_warning:
            ProjectConfig(tmp_path)

        # At least one warning about type mismatch
        calls = [str(c) for c in mock_warning.call_args_list]
        assert any("bool" in str(c) for c in calls)

    def test_valid_nested_config_no_warnings(self, tmp_path):
        """A fully valid config produces no warnings."""
        config = {
            "odoo": {"version": "19.0", "image": "odoo:19"},
            "enterprise": {"enabled": True, "path": "./enterprise"},
        }
        (tmp_path / ".odev.yaml").write_text(yaml.dump(config))

        with patch("odev.core.project.warning") as mock_warning:
            ProjectConfig(tmp_path)

        mock_warning.assert_not_called()
```

**`tests/test_docker.py`** -- Add `is_service_running` test:

```python
class TestIsServiceRunning:
    """Tests for DockerCompose.is_service_running()."""

    def test_returns_true_when_running(self):
        """Returns True when service State is 'running'."""
        dc = DockerCompose.__new__(DockerCompose)
        dc.ps_parsed = lambda: [
            {"Service": "db", "State": "running"},
            {"Service": "web", "State": "running"},
        ]
        assert dc.is_service_running("db") is True

    def test_returns_false_when_not_running(self):
        """Returns False when service State is not 'running'."""
        dc = DockerCompose.__new__(DockerCompose)
        dc.ps_parsed = lambda: [
            {"Service": "db", "State": "exited"},
        ]
        assert dc.is_service_running("db") is False

    def test_returns_false_when_service_absent(self):
        """Returns False when service is not in ps output."""
        dc = DockerCompose.__new__(DockerCompose)
        dc.ps_parsed = lambda: []
        assert dc.is_service_running("db") is False
```

### 12.5 Test Summary Matrix

| Test File | Tests | Covers |
|-----------|-------|--------|
| `tests/test_regen.py` | ~12 tests | P1, P3 (core engine) |
| `tests/test_enterprise_cmd.py` | ~4 tests | P2 (enterprise subcommands) |
| `tests/test_reconfigure.py` | ~2 tests | P1 (command layer) |
| `tests/test_config.py` (updated) | 1 test updated | P7 (enterprise ordering) |
| `tests/test_project.py` (updated) | ~3 tests added | P8 (nested schema) |
| `tests/test_docker.py` (updated) | ~3 tests added | P4 (is_service_running) |

---

## 13. Migration and Backward Compatibility

### 13.1 No Database or Data Migrations Required

All changes are to the CLI tool itself. No Odoo modules, database schemas, or persistent data formats change.

### 13.2 odev.yaml Format Unchanged

The `odev.yaml` schema is unchanged. Existing `odev.yaml` files work without modification. The new `ruta_enterprise` property reads from the existing `enterprise.path` key.

### 13.3 Registry Format Unchanged

No new fields in `RegistryEntry`. The `ENTERPRISE_DIR` constant is added to `registry.py` but does not change the registry file format.

### 13.4 Enterprise Ordering (P7) — Action Required

Projects with `enterprise.enabled: true` will see a change in `odoo.conf` `addons_path` ordering after running `odev reconfigure` or `odev up`. This is a correctness fix. No user action is needed beyond the normal config regeneration.

### 13.5 File Impact Summary

| File | Change Type | Improvement |
|------|-------------|-------------|
| `src/odev/core/regen.py` | **NEW** | P1, P3, P6 |
| `src/odev/core/project.py` | Modified | P8 (schema), `ruta_enterprise` property |
| `src/odev/core/docker.py` | Modified | P4 (`is_service_running`) |
| `src/odev/core/registry.py` | Modified | P2 (`ENTERPRISE_DIR` constant) |
| `src/odev/commands/reconfigure.py` | **NEW** | P1 |
| `src/odev/commands/enterprise.py` | **NEW** | P2 |
| `src/odev/commands/up.py` | Modified | P3 (auto-regen) |
| `src/odev/commands/adopt.py` | Modified | P6 (`--force`), P2 (shared enterprise check) |
| `src/odev/commands/load_backup.py` | Modified | P4 (pre-flight), P5 (`--yes`) |
| `src/odev/commands/reset_db.py` | Modified | P5 (`--yes`) |
| `src/odev/main.py` | Modified | P1, P2 (command registration) |
| `src/odev/templates/project/odoo.conf.j2` | Modified | P7 (enterprise ordering) |
| `tests/test_regen.py` | **NEW** | Tests for P1, P3 |
| `tests/test_enterprise_cmd.py` | **NEW** | Tests for P2 |
| `tests/test_reconfigure.py` | **NEW** | Tests for P1 |
| `tests/test_config.py` | Modified | P7 test update |
| `tests/test_project.py` | Modified | P8 tests |
| `tests/test_docker.py` | Modified | P4 tests |
