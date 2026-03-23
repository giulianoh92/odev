"""Comando 'migrate': migra un proyecto legacy al formato de proyecto independiente.

Detecta si el directorio actual usa la estructura vieja (donde el repo de la
herramienta ES el proyecto) y lo convierte al nuevo formato con .odev.yaml,
.gitignore actualizado y archivos faltantes generados.

Flujo:
1. Detecta modo con detect_mode()
2. Si ya es PROJECT -> no-op informativo
3. Si es NONE -> error claro
4. Si es LEGACY -> ejecuta migracion completa
"""

from pathlib import Path

import typer
import yaml

from odev import __version__
from odev.core.compat import ProjectMode, detect_mode
from odev.core.config import load_env
from odev.core.console import error, info, success, warning


def migrate() -> None:
    """Migra un proyecto legacy al formato de proyecto independiente.

    Lee la configuracion existente del .env, crea .odev.yaml,
    actualiza .gitignore (remueve addons/ de las exclusiones),
    genera archivos faltantes (.env.example, CLAUDE.md, etc.)
    y muestra instrucciones para los pasos manuales restantes.
    """
    modo, raiz = detect_mode()

    if modo == ProjectMode.PROJECT:
        info("Este directorio ya es un proyecto odev. No se requiere migracion.")
        raise typer.Exit()

    if modo == ProjectMode.NONE:
        error("No se detecto ningun proyecto odev ni estructura legacy.")
        info("Ejecuta 'odev init' para crear un proyecto nuevo.")
        raise typer.Exit(1)

    # modo == LEGACY
    if raiz is None:
        error("Error inesperado: modo LEGACY detectado sin directorio raiz.")
        raise typer.Exit(1)

    info(f"Detectada estructura legacy en: {raiz}")
    info("Se procedera a migrar al formato de proyecto independiente.")

    # 1. Leer configuracion existente del .env
    ruta_env = raiz / ".env"
    valores_env = load_env(ruta_env) if ruta_env.exists() else {}
    nombre_proyecto = valores_env.get("PROJECT_NAME") or valores_env.get(
        "COMPOSE_PROJECT_NAME"
    ) or raiz.name

    # 2. Crear .odev.yaml
    _crear_odev_yaml(raiz, valores_env, nombre_proyecto)

    # 3. Verificar si addons/ tiene contenido y notificar
    _verificar_addons(raiz)

    # 4. Actualizar .gitignore
    _actualizar_gitignore(raiz)

    # 5. Generar archivos faltantes
    _generar_archivos_faltantes(raiz, valores_env, nombre_proyecto)

    # 6. Generar .env.example si no existe
    _generar_env_example(raiz, valores_env)

    # Resumen final
    success("Migracion completada.")
    info("Proximos pasos recomendados:")
    info("  1. Revisa los cambios con 'git diff'")
    info("  2. Ejecuta: git add .odev.yaml")
    directorio_addons = raiz / "addons"
    if directorio_addons.exists() and any(directorio_addons.iterdir()):
        info("  3. Ejecuta: git add addons/")
    info("  4. Haz commit: git commit -m 'feat: migrar a formato de proyecto independiente'")


def _crear_odev_yaml(raiz: Path, valores_env: dict, nombre_proyecto: str) -> None:
    """Crea el archivo .odev.yaml con la configuracion del proyecto.

    Args:
        raiz: Directorio raiz del proyecto.
        valores_env: Valores leidos del .env existente.
        nombre_proyecto: Nombre del proyecto a usar en la configuracion.
    """
    ruta_yaml = raiz / ".odev.yaml"
    if ruta_yaml.exists():
        warning(f"El archivo {ruta_yaml} ya existe. Se omite la creacion.")
        return

    # Verificar si enterprise tiene contenido
    directorio_enterprise = raiz / "enterprise"
    enterprise_habilitado = False
    if directorio_enterprise.exists():
        try:
            enterprise_habilitado = any(directorio_enterprise.iterdir())
        except PermissionError:
            enterprise_habilitado = False

    configuracion = {
        "odev_min_version": __version__,
        "odoo": {
            "version": valores_env.get("ODOO_VERSION", "19.0"),
            "image": valores_env.get("ODOO_IMAGE", "odoo:19"),
        },
        "database": {
            "image": valores_env.get("DB_IMAGE", "pgvector/pgvector:pg16"),
        },
        "enterprise": {
            "enabled": enterprise_habilitado,
            "path": "./enterprise",
        },
        "services": {
            "pgweb": True,
        },
        "paths": {
            "addons": "./addons",
            "config": "./config",
            "snapshots": "./snapshots",
            "logs": "./logs",
            "docs": "./docs",
        },
        "project": {
            "name": nombre_proyecto,
            "description": "",
        },
        "sdd": {
            "enabled": True,
            "language": "es",
        },
    }

    ruta_yaml.write_text(
        yaml.dump(configuracion, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    success(f"Creado: {ruta_yaml}")


def _verificar_addons(raiz: Path) -> None:
    """Verifica si addons/ tiene modulos y notifica al usuario.

    Args:
        raiz: Directorio raiz del proyecto.
    """
    directorio_addons = raiz / "addons"
    if not directorio_addons.exists():
        return

    cantidad_modulos = _contar_modulos(directorio_addons)
    if cantidad_modulos > 0:
        warning(f"addons/ tiene contenido ({cantidad_modulos} modulo(s)).")
        info("IMPORTANTE: En la nueva estructura, addons/ se trackea en git.")
        info("Debes:")
        info("  1. Verificar que 'addons/' fue removido de .gitignore (hecho automaticamente)")
        info("  2. Ejecutar: git add addons/")
        info("  3. Hacer commit de los modulos")


def _contar_modulos(directorio_addons: Path) -> int:
    """Cuenta la cantidad de modulos Odoo en el directorio addons.

    Un modulo se identifica por tener un archivo __manifest__.py.

    Args:
        directorio_addons: Ruta al directorio addons/.

    Returns:
        Cantidad de modulos encontrados.
    """
    cantidad = 0
    if not directorio_addons.is_dir():
        return 0
    for subdirectorio in directorio_addons.iterdir():
        if subdirectorio.is_dir() and (subdirectorio / "__manifest__.py").exists():
            cantidad += 1
    return cantidad


def _actualizar_gitignore(raiz: Path) -> None:
    """Actualiza .gitignore para remover addons/ de las exclusiones.

    Lee el .gitignore existente, remueve lineas que ignoren addons/
    y agrega entradas faltantes del nuevo formato de proyecto.

    Args:
        raiz: Directorio raiz del proyecto.
    """
    ruta_gitignore = raiz / ".gitignore"
    if not ruta_gitignore.exists():
        info(".gitignore no encontrado. Se creara uno nuevo.")
        _escribir_gitignore_nuevo(ruta_gitignore)
        success("Creado: .gitignore")
        return

    contenido_original = ruta_gitignore.read_text(encoding="utf-8")
    lineas = contenido_original.splitlines()
    lineas_filtradas = []
    linea_addons_removida = False

    for linea in lineas:
        linea_limpia = linea.strip()
        # Remover lineas que ignoran addons/ (con o sin slash final)
        if linea_limpia in ("addons/", "addons", "/addons/", "/addons"):
            linea_addons_removida = True
            continue
        lineas_filtradas.append(linea)

    # Agregar entradas faltantes del nuevo formato
    contenido_actual = "\n".join(lineas_filtradas)
    entradas_necesarias = {
        "config/odoo.conf": "# Configuracion generada (se regenera desde .env)\nconfig/odoo.conf",
        "PROJECT_CONTEXT.md": "# Auto-generado por odev context\nPROJECT_CONTEXT.md",
    }

    lineas_a_agregar = []
    for patron, bloque in entradas_necesarias.items():
        if patron not in contenido_actual:
            lineas_a_agregar.append(bloque)

    if lineas_a_agregar:
        lineas_filtradas.append("")  # Linea en blanco separadora
        lineas_filtradas.extend(lineas_a_agregar)

    contenido_nuevo = "\n".join(lineas_filtradas)
    if not contenido_nuevo.endswith("\n"):
        contenido_nuevo += "\n"

    ruta_gitignore.write_text(contenido_nuevo, encoding="utf-8")

    if linea_addons_removida:
        success("Actualizado: .gitignore (removida exclusion de addons/)")
    else:
        success("Actualizado: .gitignore (entradas del nuevo formato agregadas)")


def _escribir_gitignore_nuevo(ruta: Path) -> None:
    """Escribe un .gitignore nuevo con el formato de proyecto.

    Args:
        ruta: Ruta donde crear el archivo .gitignore.
    """
    contenido = """\
# Python
__pycache__/
*.pyc
*.pyo
*.egg-info/
dist/
build/
.venv/

# Entorno (secretos locales - NO trackear)
.env

# Addons enterprise (propiedad de Odoo SA - NO trackear)
enterprise/

# Configuracion generada (se regenera desde .env)
config/odoo.conf

# Logs
logs/*
!logs/.gitkeep
*.log

# Snapshots de base de datos (pesados, locales)
snapshots/*
!snapshots/.gitkeep

# Auto-generado por odev context
PROJECT_CONTEXT.md

# IDE
.vscode/
.idea/

# Secretos y configuracion local
keys.json
.mcp.json

# Asistentes de IA (configuracion local del usuario)
.claude

# Node
node_modules/
"""
    ruta.write_text(contenido, encoding="utf-8")


def _generar_archivos_faltantes(
    raiz: Path, valores_env: dict, nombre_proyecto: str
) -> None:
    """Genera archivos que falten en el proyecto migrado.

    Crea CLAUDE.md, docs/.gitkeep y otros archivos que son parte
    del nuevo formato de proyecto pero no existian en el legacy.

    Args:
        raiz: Directorio raiz del proyecto.
        valores_env: Valores del .env para personalizar los archivos.
        nombre_proyecto: Nombre del proyecto.
    """
    version_odoo = valores_env.get("ODOO_VERSION", "19.0")

    # Crear CLAUDE.md si no existe
    ruta_claude_md = raiz / "CLAUDE.md"
    if not ruta_claude_md.exists():
        contenido_claude = f"""\
# {nombre_proyecto} - Instrucciones para Agentes IA

## Contexto del Proyecto
- **Proyecto**: {nombre_proyecto}
- **Version de Odoo**: {version_odoo}
- **Descripcion**: Proyecto Odoo

## Pipeline SDD (Flujo de Desarrollo)

Todas las tareas deben seguir este flujo secuencial:

1. **Explorador**: Analizar codigo actual y contexto.
2. **Requerimientos (Spec)**: Crear `docs/spec.md` con alcance y reglas de negocio.
3. **Arquitectura (Design)**: Crear `docs/design.md` con solucion tecnica.
4. **APROBACION HUMANA**: Pedir aprobacion de spec y design.
5. **Planificador de Tareas**: Crear `docs/task.md` con checklist de tareas atomicas.
6. **APROBACION HUMANA**: Pedir aprobacion del plan.
7. **Implementador**: Escribir codigo basado en el plan aprobado.
8. **Verificador**: Validar que el codigo cumple la especificacion.
9. **Archivador**: Guardar decisiones y limpiar artefactos temporales.

## Contexto Tecnico
- **Framework**: Odoo {version_odoo} / Python 3.10+
- **ORM**: Preferir procesamiento en lote (`write`, `create_multi`).
- **UI**: En Odoo 19+ usar `<list>` en lugar de `<tree>`.
- **Idioma**: Codigo semantico en espanol. Cadenas UI traducibles con `_()`.

## Estructura del Proyecto
```
addons/              # Modulos Odoo del proyecto
config/              # Configuracion de Odoo (generada)
docs/                # Artefactos SDD (spec, design, task)
snapshots/           # Snapshots de la BD (ignorados por git)
docker-compose.yml   # Servicios Docker
.odev.yaml           # Configuracion del proyecto
```

## Comandos Utiles
```bash
odev up              # Levantar entorno
odev scaffold <mod>  # Crear modulo nuevo
odev update <mod>    # Actualizar modulo
odev test <mod>      # Ejecutar tests
odev context         # Generar PROJECT_CONTEXT.md
```
"""
        ruta_claude_md.write_text(contenido_claude, encoding="utf-8")
        success(f"Creado: {ruta_claude_md}")

    # Crear directorios con .gitkeep si no existen
    directorios_con_gitkeep = ["docs", "snapshots", "logs"]
    for nombre_dir in directorios_con_gitkeep:
        ruta_dir = raiz / nombre_dir
        ruta_dir.mkdir(parents=True, exist_ok=True)
        ruta_gitkeep = ruta_dir / ".gitkeep"
        if not ruta_gitkeep.exists():
            ruta_gitkeep.touch()
            success(f"Creado: {ruta_gitkeep}")


def _generar_env_example(raiz: Path, valores_env: dict) -> None:
    """Genera .env.example desde los valores actuales del .env.

    Reemplaza los valores sensibles (contraseñas) con marcadores de posicion
    para que sirva como template compartible con el equipo.

    Args:
        raiz: Directorio raiz del proyecto.
        valores_env: Valores del .env actual.
    """
    ruta_example = raiz / ".env.example"
    if ruta_example.exists():
        info(".env.example ya existe. Se omite la generacion.")
        return

    if not valores_env:
        info("No se encontro .env. Se omite la generacion de .env.example.")
        return

    # Claves cuyos valores se reemplazan con marcadores de posicion
    claves_sensibles = {
        "DB_PASSWORD": "tu_password_aqui",
        "ADMIN_PASSWORD": "tu_admin_password_aqui",
    }

    lineas = [
        "# ==========================================",
        "# Configuracion del Entorno de Desarrollo Odoo",
        "# ==========================================",
        "# Copia este archivo como .env y ajusta los valores.",
        f"# Proyecto: {valores_env.get('PROJECT_NAME', valores_env.get('COMPOSE_PROJECT_NAME', 'mi-proyecto'))}",
        "",
    ]

    for clave, valor in valores_env.items():
        if valor is None:
            valor = ""
        if clave in claves_sensibles:
            lineas.append(f"{clave}={claves_sensibles[clave]}")
        else:
            lineas.append(f"{clave}={valor}")

    contenido = "\n".join(lineas) + "\n"
    ruta_example.write_text(contenido, encoding="utf-8")
    success(f"Creado: {ruta_example}")
