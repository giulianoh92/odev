"""Motor de deteccion de layout de repositorio Odoo.

Analiza la estructura de un directorio para determinar que tipo de
repositorio Odoo contiene (modulo unico, multi-addon, Odoo.sh, etc.)
y recopila informacion sobre las rutas de addons, presencia de
enterprise y submodulos git.
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


# Directorios que se omiten al escanear subdirectorios
_DIRS_IGNORADOS = frozenset({
    "__pycache__",
    "node_modules",
    ".git",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "egg-info",
})

# Nombres de modulos conocidos de Odoo Enterprise para deteccion heuristica
_MODULOS_ENTERPRISE_CONOCIDOS = frozenset({
    "account_accountant",
    "account_reports",
    "hr_payroll",
    "planning",
    "helpdesk",
    "quality_control",
    "sign",
    "studio",
    "web_enterprise",
    "web_studio",
    "mrp_workorder",
    "sale_subscription",
    "appointment",
    "knowledge",
    "documents",
    "industry_fsm",
    "social",
    "marketing_automation",
})


class TipoRepo(str, Enum):
    """Tipo de layout de repositorio Odoo detectado."""

    MODULO_UNICO = "modulo_unico"      # Modulo unico (raiz tiene __manifest__.py)
    MULTI_ADDON = "multi_addon"        # Multiples modulos en la raiz (repo plano)
    ODOOSH = "odoosh"                  # Repo Odoo.sh con submodulos git
    ODOO_FUENTE = "odoo_fuente"        # Codigo fuente completo de Odoo (fuera de alcance)
    DESCONOCIDO = "desconocido"        # Layout no reconocido


@dataclass
class RepoLayout:
    """Resultado del analisis de layout de un repositorio Odoo.

    Attributes:
        tipo: Tipo de layout detectado.
        rutas_addons: Directorios que contienen modulos Odoo.
        tiene_enterprise: Si se detecto un directorio enterprise.
        tiene_submodulos: Si existe un archivo .gitmodules.
        ruta_raiz: Directorio raiz escaneado.
        modulos_encontrados: Cantidad total de modulos encontrados.
    """

    tipo: TipoRepo
    rutas_addons: list[Path] = field(default_factory=list)
    tiene_enterprise: bool = False
    tiene_submodulos: bool = False
    ruta_raiz: Path = field(default_factory=Path)
    modulos_encontrados: int = 0


def detectar_layout(ruta: Path) -> RepoLayout:
    """Detecta el tipo de layout de un repositorio Odoo.

    Analiza la estructura de directorios usando heuristicas ordenadas
    para determinar si se trata de un modulo unico, un repo multi-addon,
    un repo Odoo.sh con submodulos, o el codigo fuente completo de Odoo.

    Algoritmo:
        1. Verifica si es el codigo fuente de Odoo (odoo-bin en raiz).
        2. Verifica si la raiz es un modulo unico (__manifest__.py).
        3. Escanea subdirectorios inmediatos buscando modulos.
        4. Parsea .gitmodules para encontrar submodulos y sus addons.
        5. Clasifica segun los hallazgos.

    Args:
        ruta: Directorio raiz del repositorio a analizar.

    Returns:
        RepoLayout con el resultado del analisis.
    """
    ruta = ruta.resolve()

    # 1. Verificar si es el codigo fuente completo de Odoo
    if (ruta / "odoo-bin").exists():
        return RepoLayout(
            tipo=TipoRepo.ODOO_FUENTE,
            ruta_raiz=ruta,
        )

    # 2. Verificar si la raiz es un modulo unico
    if _es_modulo_odoo(ruta):
        return RepoLayout(
            tipo=TipoRepo.MODULO_UNICO,
            rutas_addons=[ruta.parent],
            tiene_enterprise=False,
            tiene_submodulos=False,
            ruta_raiz=ruta,
            modulos_encontrados=1,
        )

    # 3. Escanear subdirectorios inmediatos de la raiz
    modulos_raiz = _buscar_modulos_en(ruta)

    # 4. Verificar .gitmodules y escanear submodulos
    tiene_submodulos = (ruta / ".gitmodules").is_file()
    rutas_submodulos: list[Path] = []
    modulos_submodulos: list[Path] = []

    if tiene_submodulos:
        rutas_submodulos = _parsear_gitmodules(ruta)
        for ruta_submodulo in rutas_submodulos:
            ruta_absoluta = ruta / ruta_submodulo
            if ruta_absoluta.is_dir():
                encontrados = _buscar_modulos_en(ruta_absoluta)
                modulos_submodulos.extend(encontrados)

    # 5. Recopilar rutas de addons (directorios que CONTIENEN modulos)
    rutas_addons: list[Path] = []
    _rutas_addons_vistas: set[Path] = set()

    # Agregar directorio raiz si contiene modulos
    if modulos_raiz:
        ruta_resuelta = ruta.resolve()
        if ruta_resuelta not in _rutas_addons_vistas:
            rutas_addons.append(ruta)
            _rutas_addons_vistas.add(ruta_resuelta)

    # Agregar directorios de submodulos que contienen modulos
    for ruta_submodulo in rutas_submodulos:
        ruta_absoluta = (ruta / ruta_submodulo).resolve()
        if ruta_absoluta.is_dir() and ruta_absoluta not in _rutas_addons_vistas:
            modulos_en_sub = _buscar_modulos_en(ruta_absoluta)
            if modulos_en_sub:
                rutas_addons.append(ruta / ruta_submodulo)
                _rutas_addons_vistas.add(ruta_absoluta)

    total_modulos = len(modulos_raiz) + len(modulos_submodulos)
    tiene_enterprise = _detectar_enterprise(ruta)

    # 6. Clasificar
    tiene_submodulos_con_addons = bool(modulos_submodulos)

    if tiene_submodulos and tiene_submodulos_con_addons:
        tipo = TipoRepo.ODOOSH
    elif modulos_raiz or modulos_submodulos:
        tipo = TipoRepo.MULTI_ADDON
    else:
        tipo = TipoRepo.DESCONOCIDO

    return RepoLayout(
        tipo=tipo,
        rutas_addons=rutas_addons,
        tiene_enterprise=tiene_enterprise,
        tiene_submodulos=tiene_submodulos,
        ruta_raiz=ruta,
        modulos_encontrados=total_modulos,
    )


# ---------------------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------------------


def _es_modulo_odoo(ruta: Path) -> bool:
    """Verifica si un directorio es un modulo Odoo.

    Comprueba la existencia de __manifest__.py (Odoo 10+) o
    __openerp__.py (versiones anteriores).

    Args:
        ruta: Directorio a verificar.

    Returns:
        True si el directorio contiene un manifiesto de modulo Odoo.
    """
    if not ruta.is_dir():
        return False
    return (ruta / "__manifest__.py").is_file() or (ruta / "__openerp__.py").is_file()


def _buscar_modulos_en(directorio: Path) -> list[Path]:
    """Busca modulos Odoo en los subdirectorios inmediatos de un directorio.

    Solo escanea un nivel de profundidad. Omite directorios ocultos
    (que empiezan con '.') y directorios conocidos que no son modulos.

    Args:
        directorio: Directorio donde buscar modulos.

    Returns:
        Lista de rutas a los directorios de modulos encontrados.
    """
    modulos: list[Path] = []

    if not directorio.is_dir():
        return modulos

    try:
        entradas = sorted(directorio.iterdir())
    except PermissionError:
        return modulos

    for entrada in entradas:
        # Omitir archivos, directorios ocultos y directorios ignorados
        if not entrada.is_dir():
            continue
        nombre = entrada.name
        if nombre.startswith("."):
            continue
        if nombre in _DIRS_IGNORADOS:
            continue

        if _es_modulo_odoo(entrada):
            modulos.append(entrada)

    return modulos


def _parsear_gitmodules(ruta: Path) -> list[Path]:
    """Parsea el archivo .gitmodules y extrae las rutas de los submodulos.

    El formato de .gitmodules es similar a INI, con secciones del tipo
    [submodule "nombre"] y una clave 'path' que indica la ruta relativa
    del submodulo respecto a la raiz del repositorio.

    Args:
        ruta: Directorio raiz del repositorio (donde esta .gitmodules).

    Returns:
        Lista de rutas relativas (como Path) de los submodulos encontrados.
    """
    archivo_gitmodules = ruta / ".gitmodules"

    if not archivo_gitmodules.is_file():
        return []

    parser = configparser.ConfigParser()

    try:
        parser.read(str(archivo_gitmodules), encoding="utf-8")
    except configparser.Error:
        return []

    rutas: list[Path] = []
    for seccion in parser.sections():
        if parser.has_option(seccion, "path"):
            valor_ruta = parser.get(seccion, "path").strip()
            if valor_ruta:
                rutas.append(Path(valor_ruta))

    return rutas


def _detectar_enterprise(ruta: Path) -> bool:
    """Detecta si el repositorio contiene addons de Odoo Enterprise.

    Verifica dos condiciones:
    1. Existe un directorio 'enterprise/' en la raiz.
    2. Algun subdirectorio inmediato de la raiz tiene un nombre que
       coincide con modulos conocidos de Enterprise.

    Args:
        ruta: Directorio raiz del repositorio.

    Returns:
        True si se detecta la presencia de addons enterprise.
    """
    # Verificar directorio enterprise/ explicitamente
    dir_enterprise = ruta / "enterprise"
    if dir_enterprise.is_dir():
        # Confirmar que contiene al menos un modulo
        if _buscar_modulos_en(dir_enterprise):
            return True

    # Verificar por nombres de modulos enterprise conocidos
    try:
        for entrada in ruta.iterdir():
            if not entrada.is_dir():
                continue
            if entrada.name in _MODULOS_ENTERPRISE_CONOCIDOS:
                if _es_modulo_odoo(entrada):
                    return True
    except PermissionError:
        pass

    return False
