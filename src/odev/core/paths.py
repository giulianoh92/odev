"""Resolucion de rutas del proyecto y del paquete instalado.

Proporciona la clase ProjectPaths para acceder a las rutas del proyecto
actual de forma dinamica, y funciones para acceder a los templates
bundled en el paquete pip via importlib.resources.

Cambio clave respecto al viejo paths.py: se elimina el patron de
constantes globales (PROJECT_ROOT, ADDONS_DIR, etc.) que se evaluaban
al importar. Ahora ProjectPaths es una clase que se instancia bajo
demanda, lo que permite multiples proyectos en un mismo proceso.
"""

from importlib import resources
from pathlib import Path

from odev.core.compat import ProjectMode, detect_mode


class ProjectPaths:
    """Rutas del proyecto actual, resueltas dinamicamente segun el modo.

    Se instancia pasando una ruta explícita o detectando automaticamente
    el proyecto recorriendo el arbol de directorios desde el cwd.

    Attributes:
        mode: Modo de operacion detectado (PROJECT, LEGACY, NONE).
        root: Ruta raiz del proyecto detectado.
    """

    def __init__(
        self,
        project_root: Path | None = None,
        addon_paths: list[str] | None = None,
    ) -> None:
        """Inicializa las rutas del proyecto.

        Args:
            project_root: Ruta explicita a la raiz del proyecto. Si es None,
                         se detecta automaticamente con detect_mode().
            addon_paths: Lista de rutas a directorios de addons. Si es None,
                        se carga desde ProjectConfig al acceder a addons_dirs.

        Raises:
            FileNotFoundError: Si no se encuentra un proyecto y no se paso
                              ruta explicita.
        """
        if project_root:
            self._root = project_root
            self._mode = ProjectMode.PROJECT
        else:
            self._mode, root = detect_mode()
            if root is None:
                raise FileNotFoundError(
                    "No se encontro un proyecto odev. "
                    "Ejecuta 'odev init' para crear uno o navega al directorio del proyecto."
                )
            self._root = root
        self._addon_paths = addon_paths

    @property
    def mode(self) -> ProjectMode:
        """Modo de operacion del proyecto detectado."""
        return self._mode

    @property
    def root(self) -> Path:
        """Directorio raiz del proyecto."""
        return self._root

    @property
    def addons_dirs(self) -> list[Path]:
        """Lista de directorios de addons del proyecto."""
        if self._addon_paths is not None:
            rutas = self._addon_paths
        else:
            try:
                from odev.core.project import ProjectConfig

                config = ProjectConfig(self._root)
                rutas = config.rutas_addons
            except FileNotFoundError:
                rutas = ["./addons"]
        return [self._resolver_ruta(r) for r in rutas]

    @property
    def addons_dir(self) -> Path:
        """Directorio principal de addons (el primero de la lista)."""
        dirs = self.addons_dirs
        return dirs[0] if dirs else self._root / "addons"

    def _resolver_ruta(self, ruta: str) -> Path:
        """Resuelve una ruta relativa contra el root del proyecto, o devuelve absoluta."""
        p = Path(ruta)
        if p.is_absolute():
            return p
        return self._root / p

    @property
    def enterprise_dir(self) -> Path:
        """Directorio de addons enterprise."""
        return self._root / "enterprise"

    @property
    def config_dir(self) -> Path:
        """Directorio de configuracion (odoo.conf, etc.)."""
        return self._root / "config"

    @property
    def snapshots_dir(self) -> Path:
        """Directorio de snapshots de base de datos."""
        return self._root / "snapshots"

    @property
    def logs_dir(self) -> Path:
        """Directorio de logs."""
        return self._root / "logs"

    @property
    def docs_dir(self) -> Path:
        """Directorio de documentacion y artefactos SDD."""
        return self._root / "docs"

    @property
    def env_file(self) -> Path:
        """Ruta al archivo .env del proyecto."""
        return self._root / ".env"

    @property
    def env_example(self) -> Path:
        """Ruta al archivo .env.example del proyecto."""
        return self._root / ".env.example"

    @property
    def docker_compose_file(self) -> Path:
        """Ruta al archivo docker-compose.yml del proyecto."""
        return self._root / "docker-compose.yml"

    @property
    def odev_config(self) -> Path:
        """Ruta al archivo de configuracion .odev.yaml del proyecto."""
        return self._root / ".odev.yaml"


# --- Funciones de acceso a templates del paquete (NO del proyecto) ---


def get_templates_dir() -> Path:
    """Retorna la ruta al directorio de templates del paquete instalado.

    Usa importlib.resources para localizar los templates bundled,
    lo que funciona tanto en instalaciones normales como editables.

    Returns:
        Path al directorio templates/ del paquete odev.
    """
    return Path(str(resources.files("odev") / "templates"))


def get_project_templates_dir() -> Path:
    """Retorna la ruta a templates de proyecto (docker-compose, env, etc.).

    Returns:
        Path al directorio templates/project/ del paquete odev.
    """
    return get_templates_dir() / "project"


def get_module_template_dir() -> Path:
    """Retorna la ruta al template de modulo para scaffold.

    Returns:
        Path al directorio templates/module/ del paquete odev.
    """
    return get_templates_dir() / "module"


def get_sql_templates_dir() -> Path:
    """Retorna la ruta a templates SQL (anonymize, etc.).

    Returns:
        Path al directorio templates/sql/ del paquete odev.
    """
    return get_templates_dir() / "sql"
