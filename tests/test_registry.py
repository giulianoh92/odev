"""Tests para el registro global de proyectos odev.

Valida las operaciones CRUD del Registry: registrar, obtener, listar,
eliminar, buscar por directorio y limpieza de entradas obsoletas.
Usa monkeypatch para redirigir las rutas globales a directorios temporales.
"""

import pytest
from pathlib import Path

from odev.core.registry import Registry, RegistryEntry


@pytest.fixture
def registry_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirige las constantes globales del modulo registry a tmp_path.

    Esto evita contaminar el ~/.odev/ real durante los tests.
    """
    import odev.core.registry as reg_mod

    monkeypatch.setattr(reg_mod, "ODEV_HOME", tmp_path)
    monkeypatch.setattr(reg_mod, "REGISTRY_PATH", tmp_path / "registry.yaml")
    monkeypatch.setattr(reg_mod, "PROJECTS_DIR", tmp_path / "projects")
    return tmp_path


def _crear_entry(
    nombre: str,
    directorio_trabajo: Path,
    directorio_config: Path,
    version_odoo: str = "18.0",
) -> RegistryEntry:
    """Helper para crear RegistryEntry de prueba."""
    return RegistryEntry(
        nombre=nombre,
        directorio_trabajo=directorio_trabajo,
        directorio_config=directorio_config,
        modo="external",
        version_odoo=version_odoo,
        fecha_creacion="2026-03-20",
    )


class TestRegistry:
    """Tests para la clase Registry."""

    def test_registrar_y_obtener(self, registry_dir: Path) -> None:
        """Registrar un proyecto y recuperarlo por nombre."""
        reg = Registry()
        entry = _crear_entry(
            "test-project",
            Path("/tmp/test"),
            registry_dir / "projects" / "test-project",
        )
        reg.registrar(entry)

        result = reg.obtener("test-project")

        assert result is not None
        assert result.nombre == "test-project"
        assert result.version_odoo == "18.0"

    def test_listar(self, registry_dir: Path) -> None:
        """Listar multiples proyectos registrados."""
        reg = Registry()
        for i in range(3):
            reg.registrar(
                _crear_entry(
                    f"project-{i}",
                    Path(f"/tmp/p{i}"),
                    registry_dir / "projects" / f"project-{i}",
                    version_odoo="19.0",
                )
            )

        proyectos = reg.listar()

        assert len(proyectos) == 3

    def test_listar_ordenado_por_nombre(self, registry_dir: Path) -> None:
        """Los proyectos se listan ordenados por nombre."""
        reg = Registry()
        for nombre in ["charlie", "alpha", "bravo"]:
            reg.registrar(
                _crear_entry(
                    nombre,
                    Path(f"/tmp/{nombre}"),
                    registry_dir / "projects" / nombre,
                )
            )

        nombres = [e.nombre for e in reg.listar()]

        assert nombres == ["alpha", "bravo", "charlie"]

    def test_eliminar(self, registry_dir: Path) -> None:
        """Eliminar un proyecto registrado."""
        reg = Registry()
        reg.registrar(
            _crear_entry(
                "to-delete",
                Path("/tmp/del"),
                registry_dir / "projects" / "to-delete",
            )
        )

        eliminado = reg.eliminar("to-delete")

        assert eliminado is True
        assert reg.obtener("to-delete") is None

    def test_eliminar_inexistente(self, registry_dir: Path) -> None:
        """Eliminar un proyecto que no existe retorna False."""
        reg = Registry()

        eliminado = reg.eliminar("no-existe")

        assert eliminado is False

    def test_buscar_por_directorio(self, registry_dir: Path, tmp_path: Path) -> None:
        """Buscar un proyecto por directorio de trabajo (prefix matching)."""
        reg = Registry()
        work_dir = tmp_path / "repos" / "mi-proyecto"
        work_dir.mkdir(parents=True)
        reg.registrar(
            _crear_entry(
                "mi-proyecto",
                work_dir,
                registry_dir / "projects" / "mi-proyecto",
            )
        )

        # Buscar desde subdirectorio
        sub_dir = work_dir / "modulo_a" / "models"
        sub_dir.mkdir(parents=True)
        results = reg.buscar_por_directorio(sub_dir)

        assert len(results) == 1
        assert results[0].nombre == "mi-proyecto"

    def test_buscar_por_directorio_exacto(
        self, registry_dir: Path, tmp_path: Path
    ) -> None:
        """Buscar con el directorio exacto de trabajo tambien matchea."""
        reg = Registry()
        work_dir = tmp_path / "repos" / "exact"
        work_dir.mkdir(parents=True)
        reg.registrar(
            _crear_entry(
                "exact-match",
                work_dir,
                registry_dir / "projects" / "exact-match",
            )
        )

        results = reg.buscar_por_directorio(work_dir)

        assert len(results) == 1

    def test_buscar_por_directorio_sin_match(self, registry_dir: Path) -> None:
        """Buscar en un directorio sin proyectos retorna lista vacia."""
        reg = Registry()

        results = reg.buscar_por_directorio(Path("/nada/que/ver"))

        assert results == []

    def test_limpiar_obsoletos(self, registry_dir: Path) -> None:
        """Limpiar proyectos cuyo directorio_trabajo ya no existe."""
        reg = Registry()
        reg.registrar(
            _crear_entry(
                "obsoleto",
                Path("/nonexistent/path/that/does/not/exist"),
                registry_dir / "projects" / "obsoleto",
            )
        )

        eliminados = reg.limpiar_obsoletos()

        assert "obsoleto" in eliminados
        assert reg.obtener("obsoleto") is None

    def test_limpiar_obsoletos_conserva_existentes(
        self, registry_dir: Path, tmp_path: Path
    ) -> None:
        """Limpiar obsoletos no elimina proyectos con directorios validos."""
        reg = Registry()
        work_dir = tmp_path / "valido"
        work_dir.mkdir()
        reg.registrar(
            _crear_entry(
                "valido",
                work_dir,
                registry_dir / "projects" / "valido",
            )
        )
        reg.registrar(
            _crear_entry(
                "obsoleto",
                Path("/nonexistent/path/xyz"),
                registry_dir / "projects" / "obsoleto",
            )
        )

        eliminados = reg.limpiar_obsoletos()

        assert "obsoleto" in eliminados
        assert reg.obtener("valido") is not None

    def test_registry_vacio(self, registry_dir: Path) -> None:
        """Un registry nuevo no tiene proyectos."""
        reg = Registry()

        assert reg.listar() == []
        assert reg.obtener("nada") is None

    def test_sobreescribir_proyecto_existente(self, registry_dir: Path) -> None:
        """Registrar un proyecto con el mismo nombre lo sobreescribe."""
        reg = Registry()
        reg.registrar(
            _crear_entry(
                "proyecto",
                Path("/tmp/v1"),
                registry_dir / "projects" / "proyecto",
                version_odoo="17.0",
            )
        )
        reg.registrar(
            _crear_entry(
                "proyecto",
                Path("/tmp/v2"),
                registry_dir / "projects" / "proyecto",
                version_odoo="18.0",
            )
        )

        result = reg.obtener("proyecto")

        assert result is not None
        assert result.version_odoo == "18.0"
        assert len(reg.listar()) == 1
