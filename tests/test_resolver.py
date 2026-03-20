"""Tests para la resolucion unificada de proyectos odev.

Valida las estrategias de resolucion: inline (.odev.yaml walk-up),
external (registro global), legacy (docker-compose.yml + cli/),
prioridad entre estrategias, y manejo de errores.
"""

import pytest
import yaml
from pathlib import Path

from odev.core.resolver import (
    resolver_proyecto,
    ModoProyecto,
    ProjectContext,
    ProyectoNoEncontradoError,
    ProyectoAmbiguoError,
)
from odev.core.registry import Registry, RegistryEntry


@pytest.fixture
def clean_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirige las constantes del registry a un directorio temporal limpio.

    Retorna el tmp_path base para reutilizar en los tests.
    """
    import odev.core.registry as reg_mod

    odev_home = tmp_path / ".odev"
    monkeypatch.setattr(reg_mod, "ODEV_HOME", odev_home)
    monkeypatch.setattr(reg_mod, "REGISTRY_PATH", odev_home / "registry.yaml")
    monkeypatch.setattr(reg_mod, "PROJECTS_DIR", odev_home / "projects")
    return tmp_path


def _crear_odev_yaml(directorio: Path, nombre: str, version: str = "19.0") -> Path:
    """Helper: crea un .odev.yaml minimo en el directorio dado."""
    config = {
        "project": {"name": nombre},
        "odoo": {"version": version},
        "paths": {"addons": ["./addons"]},
    }
    ruta = directorio / ".odev.yaml"
    ruta.write_text(yaml.dump(config, default_flow_style=False, allow_unicode=True))
    return ruta


class TestResolverProyecto:
    """Tests para resolver_proyecto()."""

    def test_inline_detection(self, clean_registry: Path, tmp_path: Path) -> None:
        """Detecta proyecto inline por presencia de .odev.yaml."""
        project_dir = tmp_path / "mi-inline"
        project_dir.mkdir()
        _crear_odev_yaml(project_dir, "test-inline")
        (project_dir / "addons").mkdir()

        ctx = resolver_proyecto(cwd=project_dir)

        assert ctx.modo == ModoProyecto.INLINE
        assert ctx.nombre == "test-inline"

    def test_inline_walkup(self, clean_registry: Path, tmp_path: Path) -> None:
        """Encuentra .odev.yaml subiendo por el arbol de directorios."""
        project_dir = tmp_path / "mi-inline"
        project_dir.mkdir()
        _crear_odev_yaml(project_dir, "walkup-test")
        (project_dir / "addons").mkdir()

        sub = project_dir / "addons" / "mi_modulo" / "models"
        sub.mkdir(parents=True)

        ctx = resolver_proyecto(cwd=sub)

        assert ctx.modo == ModoProyecto.INLINE
        assert ctx.nombre == "walkup-test"

    def test_external_detection(self, clean_registry: Path) -> None:
        """Detecta proyecto external via registro global."""
        work_dir = clean_registry / "repos" / "mi-proyecto"
        work_dir.mkdir(parents=True)
        config_dir = clean_registry / ".odev" / "projects" / "mi-proyecto"
        config_dir.mkdir(parents=True)

        _crear_odev_yaml(config_dir, "mi-proyecto", version="18.0")

        reg = Registry()
        reg.registrar(
            RegistryEntry(
                nombre="mi-proyecto",
                directorio_trabajo=work_dir,
                directorio_config=config_dir,
                modo="external",
                version_odoo="18.0",
                fecha_creacion="2026-03-20",
            )
        )

        ctx = resolver_proyecto(cwd=work_dir)

        assert ctx.modo == ModoProyecto.EXTERNAL
        assert ctx.nombre == "mi-proyecto"

    def test_no_encontrado(self, clean_registry: Path, tmp_path: Path) -> None:
        """Lanza ProyectoNoEncontradoError si no hay proyecto."""
        empty = tmp_path / "vacio"
        empty.mkdir()

        with pytest.raises(ProyectoNoEncontradoError):
            resolver_proyecto(cwd=empty)

    def test_inline_prioridad_sobre_external(
        self, clean_registry: Path, tmp_path: Path
    ) -> None:
        """INLINE tiene prioridad sobre EXTERNAL."""
        project_dir = tmp_path / "dual"
        project_dir.mkdir()
        _crear_odev_yaml(project_dir, "inline-wins")
        (project_dir / "addons").mkdir()

        # Registrar el mismo directorio como external
        reg = Registry()
        config_dir = clean_registry / ".odev" / "projects" / "ext"
        config_dir.mkdir(parents=True)
        reg.registrar(
            RegistryEntry(
                nombre="external-test",
                directorio_trabajo=project_dir,
                directorio_config=config_dir,
                modo="external",
                version_odoo="18.0",
                fecha_creacion="2026-03-20",
            )
        )

        ctx = resolver_proyecto(cwd=project_dir)

        assert ctx.modo == ModoProyecto.INLINE
        assert ctx.nombre == "inline-wins"

    def test_nombre_explicito_encontrado(self, clean_registry: Path) -> None:
        """Busca por nombre explicito en el registro."""
        work_dir = clean_registry / "repos" / "named"
        work_dir.mkdir(parents=True)
        config_dir = clean_registry / ".odev" / "projects" / "named"
        config_dir.mkdir(parents=True)
        _crear_odev_yaml(config_dir, "named", version="18.0")

        reg = Registry()
        reg.registrar(
            RegistryEntry(
                nombre="named",
                directorio_trabajo=work_dir,
                directorio_config=config_dir,
                modo="external",
                version_odoo="18.0",
                fecha_creacion="2026-03-20",
            )
        )

        ctx = resolver_proyecto(nombre_proyecto="named")

        assert ctx.nombre == "named"

    def test_nombre_explicito_no_encontrado(
        self, clean_registry: Path, tmp_path: Path
    ) -> None:
        """Lanza error si el nombre explicito no esta en el registro."""
        with pytest.raises(ProyectoNoEncontradoError):
            resolver_proyecto(cwd=tmp_path, nombre_proyecto="fantasma")

    def test_legacy_detection(self, clean_registry: Path, tmp_path: Path) -> None:
        """Detecta proyecto legacy (docker-compose.yml + cli/)."""
        legacy_dir = tmp_path / "legacy"
        legacy_dir.mkdir()
        (legacy_dir / "docker-compose.yml").write_text(
            "version: '3'\nservices:\n  web:\n    image: odoo:17\n"
        )
        cli_dir = legacy_dir / "cli"
        cli_dir.mkdir()
        (cli_dir / "main.py").write_text("# cli viejo")

        ctx = resolver_proyecto(cwd=legacy_dir)

        assert ctx.modo == ModoProyecto.LEGACY
        assert ctx.config is None
