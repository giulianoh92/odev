"""Registro global de proyectos odev en ~/.odev/registry.yaml.

Gestiona un archivo YAML centralizado que almacena la informacion de todos
los proyectos odev conocidos por el sistema. Permite registrar, buscar,
listar y eliminar proyectos, con soporte para bloqueo de archivo en escritura
para manejar acceso concurrente.
"""

from __future__ import annotations

import fcntl
import logging
import threading
from dataclasses import asdict, dataclass, fields
from datetime import date
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Lock de proceso para serializar escrituras concurrentes entre threads.
# fcntl.flock coordina entre procesos; este threading.Lock coordina entre threads
# del mismo proceso (fcntl no es seguro entre threads que comparten el mismo fd).
_REGISTRY_THREAD_LOCK = threading.Lock()

# --- Rutas del registro global ---

ODEV_HOME = Path.home() / ".odev"
REGISTRY_PATH = ODEV_HOME / "registry.yaml"
PROJECTS_DIR = ODEV_HOME / "projects"
ENTERPRISE_DIR = ODEV_HOME / "enterprise"  # ~/.odev/enterprise/


@dataclass
class RegistryEntry:
    """Entrada de un proyecto en el registro global.

    Atributos:
        nombre: Nombre del proyecto (clave unica en el registro).
        directorio_trabajo: Directorio donde vive el codigo del proyecto.
        directorio_config: Directorio donde odev guarda sus archivos de config.
        modo: Modo de operacion, "inline" o "external".
        version_odoo: Version de Odoo del proyecto (ej. "18.0").
        fecha_creacion: Fecha de creacion en formato ISO (ej. "2026-03-20").
        ports: Puertos asignados al proyecto (None para entradas legacy pre-0.4.0).
    """

    nombre: str
    directorio_trabajo: Path
    directorio_config: Path
    modo: str
    version_odoo: str
    fecha_creacion: str
    ports: dict[str, int] | None = None


class Registry:
    """Gestiona el registro de proyectos odev en ~/.odev/registry.yaml.

    El registro es un archivo YAML centralizado que permite al CLI
    conocer todos los proyectos existentes sin depender de que el
    usuario este parado en el directorio correcto.
    """

    def __init__(self) -> None:
        """Inicializa el registro, creando los directorios necesarios."""
        self._asegurar_directorio()

    def _asegurar_directorio(self) -> None:
        """Crea ~/.odev/ y projects/ si no existen."""
        ODEV_HOME.mkdir(parents=True, exist_ok=True)
        PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

    def _leer(self) -> dict[str, RegistryEntry]:
        """Lee el registry.yaml y retorna un dict nombre -> RegistryEntry.

        Retorna:
            Diccionario con las entradas del registro. Retorna dict vacio
            si el archivo no existe, esta vacio o contiene YAML invalido.
        """
        if not REGISTRY_PATH.exists():
            return {}

        try:
            with open(REGISTRY_PATH, encoding="utf-8") as archivo:
                datos = yaml.safe_load(archivo)
        except (yaml.YAMLError, OSError) as e:
            logger.warning("Error al leer el registro %s: %s", REGISTRY_PATH, e)
            return {}

        if not isinstance(datos, dict):
            return {}

        proyectos = datos.get("projects")
        if not isinstance(proyectos, dict):
            return {}

        campos_validos = {campo.name for campo in fields(RegistryEntry)}
        resultado: dict[str, RegistryEntry] = {}
        for nombre, valores in proyectos.items():
            if not isinstance(valores, dict):
                logger.warning("Entrada invalida para proyecto '%s', se omite.", nombre)
                continue
            try:
                # Filtrar solo campos conocidos para tolerar datos extra
                datos_filtrados = {
                    k: v for k, v in valores.items() if k in campos_validos
                }
                datos_filtrados["nombre"] = nombre
                # Convertir rutas de string a Path
                for campo_ruta in ("directorio_trabajo", "directorio_config"):
                    if campo_ruta in datos_filtrados and isinstance(
                        datos_filtrados[campo_ruta], str
                    ):
                        datos_filtrados[campo_ruta] = Path(datos_filtrados[campo_ruta])
                resultado[nombre] = RegistryEntry(**datos_filtrados)
            except (TypeError, ValueError) as e:
                logger.warning(
                    "No se pudo cargar el proyecto '%s': %s", nombre, e
                )
                continue

        return resultado

    def _escribir_fcntl(self, entries: dict[str, RegistryEntry]) -> None:
        """Escribe el registry.yaml adquiriendo solo fcntl.flock (sin thread lock).

        Metodo interno que se usa cuando el thread lock ya esta adquirido
        por el llamador (ej: allocate_ports). Adquiere solo fcntl.flock
        para coordinacion multi-proceso.

        Argumentos:
            entries: Diccionario nombre -> RegistryEntry a persistir.
        """
        self._asegurar_directorio()

        proyectos: dict[str, dict] = {}
        for nombre, entry in entries.items():
            datos = asdict(entry)
            datos.pop("nombre", None)
            # Convertir Path a string para serializar
            for clave, valor in datos.items():
                if isinstance(valor, Path):
                    datos[clave] = str(valor)
            proyectos[nombre] = datos

        contenido = {"projects": proyectos}

        modo = "r+" if REGISTRY_PATH.exists() else "w"
        with open(REGISTRY_PATH, modo, encoding="utf-8") as archivo:
            fcntl.flock(archivo, fcntl.LOCK_EX)
            try:
                archivo.seek(0)
                archivo.truncate()
                yaml.dump(
                    contenido,
                    archivo,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                )
            finally:
                fcntl.flock(archivo, fcntl.LOCK_UN)

    def _escribir(self, entries: dict[str, RegistryEntry]) -> None:
        """Escribe el registry.yaml con bloqueo de archivo y de thread.

        Adquiere primero el threading.Lock (para serializar threads del mismo
        proceso) y luego fcntl.flock(LOCK_EX) (para serializar procesos distintos)
        antes de truncar y escribir el archivo.

        Argumentos:
            entries: Diccionario nombre -> RegistryEntry a persistir.
        """
        with _REGISTRY_THREAD_LOCK:
            self._escribir_fcntl(entries)

    def registrar(self, entry: RegistryEntry) -> None:
        """Agrega o actualiza un proyecto en el registro.

        Argumentos:
            entry: Entrada del proyecto a registrar. Si ya existe una
                   entrada con el mismo nombre, se sobreescribe.
        """
        entries = self._leer()
        entries[entry.nombre] = entry
        self._escribir(entries)
        logger.info("Proyecto '%s' registrado en el registro global.", entry.nombre)

    def eliminar(self, nombre: str) -> bool:
        """Elimina un proyecto del registro.

        Argumentos:
            nombre: Nombre del proyecto a eliminar.

        Retorna:
            True si el proyecto existia y fue eliminado, False si no existia.
        """
        entries = self._leer()
        if nombre not in entries:
            return False
        del entries[nombre]
        self._escribir(entries)
        logger.info("Proyecto '%s' eliminado del registro global.", nombre)
        return True

    def obtener(self, nombre: str) -> RegistryEntry | None:
        """Obtiene un proyecto por nombre.

        Argumentos:
            nombre: Nombre del proyecto a buscar.

        Retorna:
            La entrada del proyecto si existe, None si no.
        """
        entries = self._leer()
        return entries.get(nombre)

    def listar(self) -> list[RegistryEntry]:
        """Lista todos los proyectos registrados.

        Retorna:
            Lista de todas las entradas del registro, ordenadas por nombre.
        """
        entries = self._leer()
        return sorted(entries.values(), key=lambda e: e.nombre)

    def buscar_por_directorio(self, directorio: Path) -> list[RegistryEntry]:
        """Busca proyectos cuyo directorio_trabajo contiene el directorio dado.

        Usa coincidencia por prefijo: si el directorio dado es un subdirectorio
        (o el mismo directorio) que el directorio_trabajo de un proyecto,
        se considera una coincidencia. Resuelve symlinks y normaliza las rutas
        antes de comparar.

        Argumentos:
            directorio: Directorio a buscar (tipicamente el cwd actual).

        Retorna:
            Lista de entradas que coinciden. El llamador maneja la ambiguedad
            si hay multiples resultados.
        """
        directorio_resuelto = directorio.resolve()
        entries = self._leer()
        coincidencias: list[RegistryEntry] = []

        for entry in entries.values():
            trabajo_resuelto = entry.directorio_trabajo.resolve()
            # Verificar si el directorio dado esta dentro del directorio de trabajo
            # o es exactamente el mismo
            try:
                directorio_resuelto.relative_to(trabajo_resuelto)
                coincidencias.append(entry)
            except ValueError:
                continue

        return coincidencias

    def _asignar_puertos_bajo_lock(self, nombre: str, ports: dict[str, int]) -> None:
        """Reclama puertos asumiendo que _REGISTRY_THREAD_LOCK ya fue adquirido.

        Metodo interno para uso exclusivo de allocate_ports(). No adquiere
        el thread lock para evitar deadlock. Usa _escribir_fcntl directamente.

        Argumentos:
            nombre: Nombre del proyecto al que asignar los puertos.
            ports: Diccionario {nombre_variable: numero_puerto} a reclamar.
        """
        entries = self._leer()
        if nombre in entries:
            entries[nombre].ports = ports
        else:
            entries[nombre] = RegistryEntry(
                nombre=nombre,
                directorio_trabajo=Path("/__claiming__"),
                directorio_config=Path("/__claiming__"),
                modo="claiming",
                version_odoo="",
                fecha_creacion=date.today().isoformat(),
                ports=ports,
            )
        self._escribir_fcntl(entries)
        logger.debug(
            "Puertos %s asignados al proyecto '%s' (bajo lock).",
            list(ports.keys()),
            nombre,
        )

    def asignar_puertos(self, nombre: str, ports: dict[str, int]) -> None:
        """Reclama un conjunto de puertos para un proyecto en el registro.

        Si el proyecto ya existe, actualiza su campo ports. Si no existe,
        crea una entrada skeleton que el wizard completara luego via registrar().
        La escritura es atomica gracias a fcntl.flock en _escribir().

        Argumentos:
            nombre: Nombre del proyecto al que asignar los puertos.
            ports: Diccionario {nombre_variable: numero_puerto} a reclamar.
        """
        entries = self._leer()
        if nombre in entries:
            entries[nombre].ports = ports
        else:
            # Entrada skeleton: el wizard la completara con registrar()
            entries[nombre] = RegistryEntry(
                nombre=nombre,
                directorio_trabajo=Path("/__claiming__"),
                directorio_config=Path("/__claiming__"),
                modo="claiming",
                version_odoo="",
                fecha_creacion=date.today().isoformat(),
                ports=ports,
            )
        self._escribir(entries)
        logger.debug("Puertos %s asignados al proyecto '%s'.", list(ports.keys()), nombre)

    def liberar_puertos(self, nombre: str) -> None:
        """Libera los puertos reclamados por un proyecto, seteando ports=None.

        Argumentos:
            nombre: Nombre del proyecto cuyos puertos se liberan.
        """
        entries = self._leer()
        if nombre not in entries:
            return
        if entries[nombre].ports is not None:
            entries[nombre].ports = None
            self._escribir(entries)
            logger.debug("Puertos liberados para el proyecto '%s'.", nombre)

    def puertos_ocupados(self) -> set[int]:
        """Retorna el conjunto de todos los puertos reclamados en el registro.

        Considera todas las entradas con campo ports no nulo.

        Retorna:
            Conjunto de enteros con todos los numeros de puerto reclamados.
        """
        entries = self._leer()
        ocupados: set[int] = set()
        for entry in entries.values():
            if entry.ports:
                ocupados.update(entry.ports.values())
        return ocupados

    def limpiar_obsoletos(self) -> list[str]:
        """Elimina entradas cuyo directorio_trabajo ya no existe.

        Retorna:
            Lista de nombres de proyectos eliminados.
        """
        entries = self._leer()
        eliminados: list[str] = []

        for nombre, entry in list(entries.items()):
            if not entry.directorio_trabajo.exists():
                del entries[nombre]
                eliminados.append(nombre)
                logger.info(
                    "Proyecto '%s' eliminado (directorio %s ya no existe).",
                    nombre,
                    entry.directorio_trabajo,
                )

        if eliminados:
            self._escribir(entries)

        return eliminados
