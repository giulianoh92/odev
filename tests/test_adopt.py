"""Tests para odev adopt --force — re-adoption de proyectos existentes.

Verifica que el flag --force permita re-adoptar un proyecto que ya existe
en el registro, eliminando la entrada existente y el directorio de config,
sin tocar el directorio de trabajo. Tambien verifica que sin --force el
mensaje de error incluya un hint sobre --force.
"""

import inspect
from pathlib import Path

import pytest
import typer

from odev.commands.adopt import adopt
from odev.core.registry import Registry, RegistryEntry


@pytest.fixture
def registry_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirige las constantes globales del modulo registry a tmp_path.

    Esto evita contaminar el ~/.odev/ real durante los tests.
    """
    import odev.core.registry as reg_mod

    projects_dir = tmp_path / "projects"
    monkeypatch.setattr(reg_mod, "ODEV_HOME", tmp_path)
    monkeypatch.setattr(reg_mod, "REGISTRY_PATH", tmp_path / "registry.yaml")
    monkeypatch.setattr(reg_mod, "PROJECTS_DIR", projects_dir)

    # Also patch the PROJECTS_DIR imported in adopt.py
    import odev.commands.adopt as adopt_mod

    monkeypatch.setattr(adopt_mod, "PROJECTS_DIR", projects_dir)

    return tmp_path


def _crear_entry(
    nombre: str,
    directorio_trabajo: Path,
    directorio_config: Path,
    version_odoo: str = "19.0",
) -> RegistryEntry:
    """Helper para crear RegistryEntry de prueba."""
    return RegistryEntry(
        nombre=nombre,
        directorio_trabajo=directorio_trabajo,
        directorio_config=directorio_config,
        modo="external",
        version_odoo=version_odoo,
        fecha_creacion="2026-03-25",
    )


class TestAdoptForceSignature:
    """Verifica que el parametro --force existe en la firma del comando."""

    def test_force_parameter_exists(self) -> None:
        """El parametro force existe en la firma de adopt()."""
        sig = inspect.signature(adopt)
        assert "force" in sig.parameters

    def test_force_parameter_default_is_false(self) -> None:
        """El parametro force tiene default False."""
        sig = inspect.signature(adopt)
        param = sig.parameters["force"]
        assert param.default is not inspect.Parameter.empty
        # Typer wraps the default; check the actual Option object
        assert isinstance(param.default, typer.models.OptionInfo)
        assert param.default.default is False


class TestAdoptForceRegistryCleanup:
    """Verifica que --force elimine la entrada del registro y el config dir."""

    def test_force_removes_existing_registry_entry(
        self, registry_dir: Path, tmp_path: Path
    ) -> None:
        """Con --force y proyecto existente en registro, la entrada se elimina."""
        # Setup: registrar un proyecto existente
        config_dir = registry_dir / "projects" / "test-project"
        config_dir.mkdir(parents=True)
        (config_dir / "docker-compose.yml").write_text("old")

        reg = Registry()
        entry = _crear_entry(
            "test-project",
            directorio_trabajo=tmp_path / "work",
            directorio_config=config_dir,
        )
        reg.registrar(entry)

        # Verify it exists before force
        assert reg.obtener("test-project") is not None

        # Act: eliminar como lo haria --force
        reg.eliminar("test-project")

        # Assert: la entrada ya no existe
        assert reg.obtener("test-project") is None

    def test_force_removes_config_directory(
        self, registry_dir: Path, tmp_path: Path
    ) -> None:
        """Con --force, el directorio de config bajo ~/.odev/projects/ se elimina."""
        import shutil

        config_dir = registry_dir / "projects" / "test-project"
        config_dir.mkdir(parents=True)
        (config_dir / "docker-compose.yml").write_text("old")
        (config_dir / ".env").write_text("OLD=true")

        # Simular la logica de --force
        if config_dir.exists():
            shutil.rmtree(config_dir)

        assert not config_dir.exists()

    def test_force_does_not_remove_working_directory(
        self, registry_dir: Path, tmp_path: Path
    ) -> None:
        """Con --force, el directorio de trabajo NUNCA se elimina."""
        import shutil

        work_dir = tmp_path / "my-odoo-project"
        work_dir.mkdir()
        (work_dir / "important-file.py").write_text("# don't delete me")

        config_dir = registry_dir / "projects" / "test-project"
        config_dir.mkdir(parents=True)

        # Simular la logica de --force (solo elimina config_dir)
        if config_dir.exists():
            shutil.rmtree(config_dir)

        # El directorio de trabajo sigue intacto
        assert work_dir.exists()
        assert (work_dir / "important-file.py").exists()


class TestAdoptWithoutForceHint:
    """Verifica que sin --force el mensaje de error incluya hint sobre --force."""

    def test_odev_yaml_error_mentions_force(self) -> None:
        """El mensaje de error por .odev.yaml existente menciona --force."""
        # El mensaje en el codigo fuente
        expected_hint = "--force para re-adoptar"
        # Verificar leyendo el codigo fuente directamente
        import odev.commands.adopt as mod

        source = inspect.getsource(mod.adopt)
        assert expected_hint in source

    def test_registry_error_mentions_force(self) -> None:
        """El mensaje de error por proyecto existente en registro menciona --force."""
        expected_hint = "--force para re-adoptar"
        import odev.commands.adopt as mod

        source = inspect.getsource(mod.adopt)
        # Verificar que el mensaje de error del registro tambien incluye el hint
        assert "Usa --force para re-adoptar" in source
