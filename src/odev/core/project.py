"""Carga y validacion de la configuracion de proyecto (.odev.yaml).

Este modulo se encarga de leer, parsear y validar el archivo de
configuracion del proyecto. Tambien verifica la compatibilidad
de version entre el CLI instalado y la version minima requerida
por el proyecto.
"""

from pathlib import Path

import yaml
from packaging.version import Version

from odev import __version__
from odev.core.console import warning


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
        self.ruta_archivo = ruta_proyecto / ".odev.yaml"
        if not self.ruta_archivo.exists():
            raise FileNotFoundError(
                f"No se encontro .odev.yaml en {ruta_proyecto}. "
                "Ejecuta 'odev init' para crear un proyecto."
            )
        with open(self.ruta_archivo, encoding="utf-8") as archivo:
            datos_crudos = yaml.safe_load(archivo) or {}
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
