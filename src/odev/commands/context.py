"""Comando 'context': genera PROJECT_CONTEXT.md con analisis de modulos.

Escanea el directorio addons/ del proyecto, analiza los manifiestos
y la estructura de cada modulo usando ast (sin ejecutar codigo),
y genera un archivo de contexto Markdown detallado.

JSON schema (--json):
  {
    "project_name": str,
    "odoo_version": str,
    "addons_paths": [str],
    "modules_installed": [str],
    "db": {"name": str, "host": str, "port": int}
  }
"""

from __future__ import annotations

import ast
import json
import sys
from datetime import datetime
from pathlib import Path

import typer
from jinja2 import Environment, FileSystemLoader

from odev.commands._helpers import obtener_rutas, requerir_proyecto
from odev.core.config import load_env
from odev.core.console import success, warning
from odev.core.paths import get_templates_dir


def context(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emite JSON a stdout en lugar de generar PROJECT_CONTEXT.md.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suprime decoraciones Rich, spinners y progress. Util con --json.",
    ),
) -> None:
    """Genera PROJECT_CONTEXT.md a partir del analisis de los modulos en addons/.

    Escanea los modulos Odoo del proyecto, extrae informacion de sus
    manifiestos y estructura de codigo, y renderiza un documento de
    contexto completo para referencia.

    Con --json, emite un objeto JSON con informacion del proyecto sin crear archivo.
    Con --quiet, suprime decoraciones Rich.
    """
    from odev.main import obtener_nombre_proyecto

    contexto = requerir_proyecto(obtener_nombre_proyecto())
    rutas = obtener_rutas(contexto)

    valores_env = load_env(rutas.env_file)

    if json_output:
        # JSON mode: emite objeto estructurado sin generar archivo
        addons_paths = [str(d) for d in rutas.addons_dirs]
        modulos_nombres: list[str] = []
        for directorio_addons in rutas.addons_dirs:
            for info in _escanear_modulos(directorio_addons):
                nombre_tecnico = info.get("technical_name", info.get("name", ""))
                if nombre_tecnico:
                    modulos_nombres.append(nombre_tecnico)

        try:
            db_port = int(valores_env.get("DB_PORT", "5432"))
        except (ValueError, TypeError):
            db_port = 5432

        resultado = {
            "project_name": contexto.nombre,
            "odoo_version": valores_env.get("ODOO_VERSION", "N/A"),
            "addons_paths": addons_paths,
            "modules_installed": modulos_nombres,
            "db": {
                "name": valores_env.get("DB_NAME", "N/A"),
                "host": valores_env.get("DB_HOST", "db"),
                "port": db_port,
            },
        }
        sys.stdout.write(json.dumps(resultado) + "\n")
        raise typer.Exit(0)

    modulos = []
    for directorio_addons in rutas.addons_dirs:
        modulos.extend(_escanear_modulos(directorio_addons))

    if not modulos and not quiet:
        warning("No se encontraron modulos en addons/. PROJECT_CONTEXT.md sera minimo.")

    # Buscar template de contexto en el directorio de templates del paquete
    directorio_templates = get_templates_dir()
    entorno_jinja = Environment(
        loader=FileSystemLoader(str(directorio_templates)),
        keep_trailing_newline=True,
    )
    template = entorno_jinja.get_template("project_context.md.j2")

    salida = template.render(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        odoo_version=valores_env.get("ODOO_VERSION", "N/A"),
        db_name=valores_env.get("DB_NAME", "N/A"),
        modules=modulos,
    )

    destino = rutas.root / "PROJECT_CONTEXT.md"
    destino.write_text(salida)
    if not quiet:
        success(f"Generado {destino.name} con {len(modulos)} modulo(s).")


def _escanear_modulos(directorio_addons: Path) -> list[dict]:
    """Escanea el directorio addons buscando modulos Odoo usando ast (sin importar codigo).

    Args:
        directorio_addons: Ruta al directorio de addons del proyecto.

    Returns:
        Lista de diccionarios con informacion de cada modulo encontrado.
    """
    if not directorio_addons.exists():
        return []

    modulos = []
    for ruta_manifiesto in sorted(directorio_addons.glob("*/__manifest__.py")):
        directorio_modulo = ruta_manifiesto.parent
        info_modulo = _parsear_manifiesto(ruta_manifiesto)
        if info_modulo is None:
            continue

        info_modulo["technical_name"] = directorio_modulo.name
        info_modulo["models"] = _escanear_modelos(directorio_modulo / "models")
        info_modulo["model_count"] = len(info_modulo["models"])
        info_modulo["view_count"] = _contar_vistas_xml(directorio_modulo)
        info_modulo["test_count"] = _contar_tests(directorio_modulo)
        info_modulo["has_controllers"] = _tiene_controladores(directorio_modulo)
        info_modulo["report_count"] = _contar_reportes_xml(directorio_modulo)
        info_modulo["wizard_count"] = _contar_wizards(directorio_modulo)
        modulos.append(info_modulo)

    return modulos


def _parsear_manifiesto(ruta: Path) -> dict | None:
    """Parsea __manifest__.py usando ast.literal_eval (seguro, sin ejecucion).

    Args:
        ruta: Ruta al archivo __manifest__.py.

    Returns:
        Diccionario con informacion del manifiesto o None si no es valido.
    """
    try:
        contenido = ruta.read_text()
        manifiesto = ast.literal_eval(contenido)
        if not isinstance(manifiesto, dict):
            return None
        return {
            "name": manifiesto.get("name", ruta.parent.name),
            "summary": manifiesto.get("summary", ""),
            "version": manifiesto.get("version", ""),
            "depends": manifiesto.get("depends", []),
        }
    except (ValueError, SyntaxError):
        return None


def _escanear_modelos(directorio_modelos: Path) -> list[dict]:
    """Escanea archivos models/*.py buscando clases de modelos Odoo con ast.parse.

    Args:
        directorio_modelos: Ruta al directorio models/ del modulo.

    Returns:
        Lista de diccionarios con informacion de cada modelo encontrado.
    """
    if not directorio_modelos.exists():
        return []

    modelos = []
    for archivo_py in sorted(directorio_modelos.glob("*.py")):
        if archivo_py.name == "__init__.py":
            continue
        try:
            arbol = ast.parse(archivo_py.read_text())
        except SyntaxError:
            continue

        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.ClassDef):
                continue

            info_modelo = _extraer_info_modelo(nodo)
            if info_modelo:
                modelos.append(info_modelo)

    return modelos


def _extraer_info_modelo(nodo_clase: ast.ClassDef) -> dict | None:
    """Extrae _name, _inherit y definiciones de campos de un nodo de clase AST.

    Args:
        nodo_clase: Nodo AST de una definicion de clase.

    Returns:
        Diccionario con informacion del modelo o None si no es un modelo Odoo.
    """
    nombre_modelo = None
    herencia = None
    campos = []

    for item in nodo_clase.body:
        if isinstance(item, ast.Assign):
            for objetivo in item.targets:
                if isinstance(objetivo, ast.Name):
                    if objetivo.id == "_name" and isinstance(item.value, ast.Constant):
                        nombre_modelo = item.value.value
                    elif objetivo.id == "_inherit" and isinstance(item.value, ast.Constant):
                        herencia = item.value.value

                    # Verificar si la asignacion es un campo (llamada a fields.Xxx)
                    if isinstance(item.value, ast.Call):
                        tipo_campo = _obtener_tipo_campo(item.value)
                        if tipo_campo:
                            campos.append(f"{objetivo.id} ({tipo_campo})")

    if not nombre_modelo and not herencia:
        return None

    return {
        "name": nombre_modelo or herencia or nodo_clase.name,
        "inherit": herencia,
        "fields": campos,
    }


def _obtener_tipo_campo(nodo_llamada: ast.Call) -> str | None:
    """Extrae el tipo de campo de una llamada fields.Xxx().

    Args:
        nodo_llamada: Nodo AST de una llamada a funcion.

    Returns:
        Nombre del tipo de campo (Char, Integer, etc.) o None.
    """
    func = nodo_llamada.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        if func.value.id == "fields":
            return func.attr
    return None


def _contar_vistas_xml(directorio_modulo: Path) -> int:
    """Cuenta registros ir.ui.view en archivos views/*.xml.

    Args:
        directorio_modulo: Directorio raiz del modulo.

    Returns:
        Cantidad de vistas encontradas.
    """
    cantidad = 0
    directorio_vistas = directorio_modulo / "views"
    if not directorio_vistas.exists():
        return 0
    for archivo_xml in directorio_vistas.glob("*.xml"):
        try:
            contenido = archivo_xml.read_text()
            cantidad += contenido.count('model="ir.ui.view"')
        except OSError:
            continue
    return cantidad


def _contar_reportes_xml(directorio_modulo: Path) -> int:
    """Cuenta registros ir.actions.report en todos los archivos *.xml del modulo.

    Args:
        directorio_modulo: Directorio raiz del modulo.

    Returns:
        Cantidad de reportes encontrados.
    """
    cantidad = 0
    for archivo_xml in directorio_modulo.rglob("*.xml"):
        try:
            contenido = archivo_xml.read_text()
            cantidad += contenido.count('model="ir.actions.report"')
        except OSError:
            continue
    return cantidad


def _contar_tests(directorio_modulo: Path) -> int:
    """Cuenta metodos de test (def test_*) en archivos tests/*.py.

    Args:
        directorio_modulo: Directorio raiz del modulo.

    Returns:
        Cantidad de metodos de test encontrados.
    """
    cantidad = 0
    directorio_tests = directorio_modulo / "tests"
    if not directorio_tests.exists():
        return 0
    for archivo_py in directorio_tests.glob("*.py"):
        if archivo_py.name == "__init__.py":
            continue
        try:
            arbol = ast.parse(archivo_py.read_text())
        except SyntaxError:
            continue
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.FunctionDef) and nodo.name.startswith("test_"):
                cantidad += 1
    return cantidad


def _tiene_controladores(directorio_modulo: Path) -> bool:
    """Retorna True si controllers/ tiene archivos .py ademas de __init__.py.

    Args:
        directorio_modulo: Directorio raiz del modulo.

    Returns:
        True si hay controladores definidos.
    """
    directorio_controladores = directorio_modulo / "controllers"
    if not directorio_controladores.exists():
        return False
    return any(f for f in directorio_controladores.glob("*.py") if f.name != "__init__.py")


def _contar_wizards(directorio_modulo: Path) -> int:
    """Cuenta clases TransientModel en directorios wizards/ o wizard/.

    Args:
        directorio_modulo: Directorio raiz del modulo.

    Returns:
        Cantidad de wizards encontrados.
    """
    cantidad = 0
    for nombre_dir_wizard in ("wizards", "wizard"):
        directorio_wizard = directorio_modulo / nombre_dir_wizard
        if not directorio_wizard.exists():
            continue
        for archivo_py in directorio_wizard.glob("*.py"):
            if archivo_py.name == "__init__.py":
                continue
            try:
                arbol = ast.parse(archivo_py.read_text())
            except SyntaxError:
                continue
            for nodo in ast.walk(arbol):
                if isinstance(nodo, ast.ClassDef):
                    for base in nodo.bases:
                        if isinstance(base, ast.Attribute) and base.attr == "TransientModel":
                            cantidad += 1
                        elif isinstance(base, ast.Name) and base.id == "TransientModel":
                            cantidad += 1
    return cantidad
