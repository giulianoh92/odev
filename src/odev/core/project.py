"""Carga y validacion de la configuracion de proyecto (.odev.yaml).

Este modulo se encarga de leer, parsear y validar el archivo de
configuracion del proyecto. Tambien verifica la compatibilidad
de version entre el CLI instalado y la version minima requerida
por el proyecto.
"""

import logging
from pathlib import Path

import yaml
from packaging.version import Version

from odev import __version__
from odev.core.console import warning

logger = logging.getLogger(__name__)


# Valores por defecto para un proyecto nuevo
_CONFIGURACION_POR_DEFECTO: dict = {
    "odev_min_version": "0.1.0",
    "odoo": {
        "version": "19.0",
        "image": "odoo:19",
    },
    "database": {
        "image": "pgvector/pgvector:pg16",
    },
    "enterprise": {
        "enabled": False,
        "path": "./enterprise",
    },
    "services": {
        "pgweb": True,
    },
    "paths": {
        "addons": ["./addons"],
        "config": "./config",
        "snapshots": "./snapshots",
        "logs": "./logs",
        "docs": "./docs",
    },
    "project": {
        "name": "",
        "description": "",
    },
    "sdd": {
        "enabled": True,
        "language": "es",
    },
}


_ESQUEMA_ODEV_YAML: dict[str, type | tuple[type, ...]] = {
    "odev_min_version": str,
    "odoo": dict,
    "database": dict,
    "enterprise": dict,
    "services": dict,
    "paths": dict,
    "project": dict,
}


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
        "addons": (list, str),
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


def _validar_esquema(datos: dict, ruta_archivo: Path) -> list[str]:
    """Valida la estructura del archivo .odev.yaml.

    Verifica:
    1. Claves desconocidas de primer nivel (comportamiento existente)
    2. Tipos incorrectos de primer nivel (comportamiento existente)
    3. Claves desconocidas dentro de cada seccion anidada (NUEVO)
    4. Tipos incorrectos en valores anidados (NUEVO)

    Todas las validaciones producen advertencias (no errores) para
    mantener compatibilidad hacia adelante.

    Argumentos:
        datos: Diccionario con los datos cargados del YAML.
        ruta_archivo: Ruta al archivo para mensajes de error.

    Retorna:
        Lista de advertencias encontradas (puede estar vacia).
    """
    advertencias = []
    claves_conocidas = set(_ESQUEMA_ODEV_YAML.keys()) | {"mode", "sdd"}

    # 1. Detectar claves desconocidas de primer nivel (posibles typos)
    for clave in datos:
        if clave not in claves_conocidas:
            advertencias.append(
                f"Clave desconocida '{clave}' en {ruta_archivo}. "
                "Posible error tipografico."
            )

    # 2. Validar tipos de primer nivel
    for clave, tipo_esperado in _ESQUEMA_ODEV_YAML.items():
        if clave in datos and not isinstance(datos[clave], tipo_esperado):
            advertencias.append(
                f"La clave '{clave}' en {ruta_archivo} deberia ser {tipo_esperado.__name__}, "
                f"pero es {type(datos[clave]).__name__}."
            )

    # 3. Validar claves y tipos dentro de secciones anidadas
    for seccion, esquema_seccion in _ESQUEMA_NESTED.items():
        if seccion not in datos or not isinstance(datos[seccion], dict):
            continue

        datos_seccion = datos[seccion]

        # Claves desconocidas dentro de la seccion
        for clave in datos_seccion:
            if clave not in esquema_seccion:
                advertencias.append(
                    f"Clave desconocida '{clave}' en seccion '{seccion}' "
                    f"de {ruta_archivo}. Posible error tipografico."
                )

        # Tipos incorrectos en valores de la seccion
        for clave, tipo_esperado in esquema_seccion.items():
            if clave not in datos_seccion:
                continue
            valor = datos_seccion[clave]
            if valor is None:
                # None (null en YAML) no es un tipo valido para ninguna clave
                if isinstance(tipo_esperado, tuple):
                    nombres_tipos = " o ".join(t.__name__ for t in tipo_esperado)
                else:
                    nombres_tipos = tipo_esperado.__name__
                advertencias.append(
                    f"'{seccion}.{clave}' deberia ser {nombres_tipos}, "
                    f"pero es NoneType."
                )
            elif isinstance(tipo_esperado, tuple):
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


class ProjectConfig:
    """Configuracion de un proyecto odev cargada desde .odev.yaml.

    Atributos:
        datos: Diccionario con toda la configuracion del proyecto.
        ruta_archivo: Ruta al archivo .odev.yaml cargado.
    """

    def __init__(self, ruta_proyecto: Path) -> None:
        """Carga la configuracion del proyecto desde .odev.yaml.

        Argumentos:
            ruta_proyecto: Directorio raiz del proyecto donde buscar .odev.yaml.

        Lanza:
            FileNotFoundError: Si no existe .odev.yaml en la ruta indicada.
        """
        # Soporte para ambos nombres de archivo:
        # - ".odev.yaml" (proyectos inline, dentro del directorio de trabajo)
        # - "odev.yaml"  (proyectos externos adoptados, en ~/.odev/projects/<nombre>/)
        ruta_con_punto = ruta_proyecto / ".odev.yaml"
        ruta_sin_punto = ruta_proyecto / "odev.yaml"
        if ruta_con_punto.exists():
            self.ruta_archivo = ruta_con_punto
        elif ruta_sin_punto.exists():
            self.ruta_archivo = ruta_sin_punto
        else:
            raise FileNotFoundError(
                f"No se encontro .odev.yaml ni odev.yaml en {ruta_proyecto}. "
                "Ejecuta 'odev init' para crear un proyecto."
            )
        with open(self.ruta_archivo, encoding="utf-8") as archivo:
            datos_crudos = yaml.safe_load(archivo) or {}
        # Validar esquema basico del YAML
        advertencias = _validar_esquema(datos_crudos, self.ruta_archivo)
        for adv in advertencias:
            warning(adv)
        # Mezclar con valores por defecto para garantizar estructura completa
        self.datos = _mezclar_profundo(_CONFIGURACION_POR_DEFECTO.copy(), datos_crudos)
        # Coercion paths.addons: string -> lista (compatibilidad con archivos viejos)
        rutas = self.datos.get("paths", {})
        if isinstance(rutas.get("addons"), str):
            rutas["addons"] = [rutas["addons"]]

    @property
    def version_minima(self) -> str:
        """Version minima de odev requerida por el proyecto."""
        return self.datos.get("odev_min_version", "0.1.0")

    @property
    def version_odoo(self) -> str:
        """Version de Odoo configurada para el proyecto."""
        return self.datos.get("odoo", {}).get("version", "19.0")

    @property
    def imagen_odoo(self) -> str:
        """Imagen Docker de Odoo configurada."""
        return self.datos.get("odoo", {}).get("image", "odoo:19")

    @property
    def imagen_db(self) -> str:
        """Imagen Docker de PostgreSQL configurada."""
        return self.datos.get("database", {}).get("image", "pgvector/pgvector:pg16")

    @property
    def enterprise_habilitado(self) -> bool:
        """Si los addons enterprise estan habilitados."""
        return self.datos.get("enterprise", {}).get("enabled", False)

    @property
    def ruta_enterprise(self) -> str:
        """Ruta al directorio de addons enterprise.

        Resolucion por prioridad:
        1. Si hay un path explicito en odev.yaml (distinto del default) -> usarlo.
        2. Si existe ~/.odev/enterprise/{version}/ -> usarlo como fallback.
        3. Caso contrario -> retornar el default "./enterprise".
        """
        ruta_configurada = self.datos.get("enterprise", {}).get("path", "./enterprise")

        # Si el usuario configuro un path explicito (distinto del default), respetar
        if ruta_configurada != "./enterprise":
            return ruta_configurada

        # Fallback: buscar en almacenamiento compartido
        from odev.core.registry import ENTERPRISE_DIR

        version = self.version_odoo
        ruta_compartida = ENTERPRISE_DIR / version
        if ruta_compartida.exists():
            return str(ruta_compartida)

        return ruta_configurada

    @property
    def nombre_proyecto(self) -> str:
        """Nombre del proyecto."""
        return self.datos.get("project", {}).get("name", "")

    @property
    def descripcion_proyecto(self) -> str:
        """Descripcion del proyecto."""
        return self.datos.get("project", {}).get("description", "")

    @property
    def pgweb_habilitado(self) -> bool:
        """Si el servicio pgweb esta habilitado."""
        return self.datos.get("services", {}).get("pgweb", True)

    @property
    def modo(self) -> str:
        """Modo del proyecto: 'inline' o 'external'."""
        return self.datos.get("mode", "inline")

    @property
    def rutas_addons(self) -> list[str]:
        """Lista de rutas a directorios de addons."""
        return self.datos.get("paths", {}).get("addons", ["./addons"])

    @property
    def directorio_trabajo(self) -> str | None:
        """Directorio de trabajo (solo para modo external)."""
        return self.datos.get("project", {}).get("working_dir")

    def verificar_compatibilidad_version(self) -> bool:
        """Verifica si la version del CLI satisface la version minima del proyecto.

        Muestra una advertencia si la version instalada es menor a la requerida.

        Retorna:
            True si la version es compatible, False si no lo es.
        """
        version_cli = Version(__version__)
        version_requerida = Version(self.version_minima)
        if version_cli < version_requerida:
            warning(
                f"Tu version de odev ({__version__}) es menor a la requerida "
                f"por este proyecto ({self.version_minima}).\n"
                "  Ejecuta: pip install --upgrade git+https://github.com/giulianoh92/odev.git"
            )
            return False
        return True


def _mezclar_profundo(base: dict, actualizacion: dict) -> dict:
    """Mezcla recursiva de dos diccionarios, priorizando los valores de actualizacion.

    Argumentos:
        base: Diccionario con valores por defecto.
        actualizacion: Diccionario con valores que sobreescriben los de base.

    Retorna:
        Diccionario resultante de la mezcla profunda.
    """
    resultado = base.copy()
    for clave, valor in actualizacion.items():
        if clave in resultado and isinstance(resultado[clave], dict) and isinstance(valor, dict):
            resultado[clave] = _mezclar_profundo(resultado[clave], valor)
        else:
            resultado[clave] = valor
    return resultado
