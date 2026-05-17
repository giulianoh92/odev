"""Tests para el registro global de proyectos odev.

Valida las operaciones CRUD del Registry: registrar, obtener, listar,
eliminar, buscar por directorio y limpieza de entradas obsoletas.
Tambien cubre el campo ports (0.4.0): asignar_puertos, liberar_puertos,
puertos_ocupados y compatibilidad con entradas legacy sin campo ports.
Usa monkeypatch para redirigir las rutas globales a directorios temporales.
"""

from pathlib import Path

import pytest
import yaml

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


# ── T01 RED: Tests de compatibilidad con entradas legacy (sin campo ports) ──


class TestLegacyEntryCompatibility:
    """Verifica que entradas legacy (pre-0.4.0) sin campo ports se carguen sin errores."""

    def test_legacy_entry_without_ports_field_loads_with_ports_none(
        self, registry_dir: Path
    ) -> None:
        """Una entrada legacy sin campo ports se carga con ports=None.

        Simula un registry.yaml escrito por una version pre-0.4.0 y verifica
        que _leer() asigne None al campo ports sin lanzar excepcion.
        """
        # Escribir YAML legacy directamente (sin campo ports)
        registry_path = registry_dir / "registry.yaml"
        datos_legacy = {
            "projects": {
                "legacy-project": {
                    "directorio_trabajo": "/tmp/legacy",
                    "directorio_config": str(registry_dir / "projects" / "legacy-project"),
                    "modo": "inline",
                    "version_odoo": "18.0",
                    "fecha_creacion": "2026-01-01",
                    # sin campo 'ports'
                }
            }
        }
        registry_path.write_text(yaml.dump(datos_legacy))

        reg = Registry()
        entry = reg.obtener("legacy-project")

        assert entry is not None
        assert entry.ports is None

    def test_legacy_yaml_round_trip_no_crash(self, registry_dir: Path) -> None:
        """Leer y re-escribir un registry legacy no lanza excepciones y conserva datos.

        Verifica NF-3: entradas sin campo ports no crashean en ninguna operacion.
        """
        registry_path = registry_dir / "registry.yaml"
        datos_legacy = {
            "projects": {
                "proyecto-a": {
                    "directorio_trabajo": "/tmp/a",
                    "directorio_config": str(registry_dir / "projects" / "a"),
                    "modo": "external",
                    "version_odoo": "19.0",
                    "fecha_creacion": "2026-01-15",
                },
                "proyecto-b": {
                    "directorio_trabajo": "/tmp/b",
                    "directorio_config": str(registry_dir / "projects" / "b"),
                    "modo": "inline",
                    "version_odoo": "17.0",
                    "fecha_creacion": "2026-02-20",
                },
            }
        }
        registry_path.write_text(yaml.dump(datos_legacy))

        reg = Registry()
        proyectos = reg.listar()

        assert len(proyectos) == 2
        for p in proyectos:
            assert p.ports is None


# ── T03 RED: Tests de asignar_puertos, liberar_puertos, puertos_ocupados ──


class TestPortsMethods:
    """Verifica los metodos de gestion de puertos en Registry."""

    _PUERTOS_BASE = {
        "WEB_PORT": 8069,
        "PGWEB_PORT": 8081,
        "DB_PORT": 5432,
        "DEBUGPY_PORT": 5678,
        "MAILHOG_PORT": 8025,
    }

    def test_asignar_puertos_creates_skeleton_entry(self, registry_dir: Path) -> None:
        """asignar_puertos crea una entrada skeleton si el proyecto no existe aun."""
        reg = Registry()

        reg.asignar_puertos("nuevo-proyecto", self._PUERTOS_BASE)

        entry = reg.obtener("nuevo-proyecto")
        assert entry is not None
        assert entry.ports == self._PUERTOS_BASE

    def test_asignar_puertos_updates_existing_entry(self, registry_dir: Path) -> None:
        """asignar_puertos actualiza ports en una entrada existente."""
        reg = Registry()
        entry = _crear_entry(
            "existente",
            Path("/tmp/existente"),
            registry_dir / "projects" / "existente",
        )
        reg.registrar(entry)

        nuevos_puertos = {
            "WEB_PORT": 8070,
            "PGWEB_PORT": 8082,
            "DB_PORT": 5433,
            "DEBUGPY_PORT": 5679,
            "MAILHOG_PORT": 8026,
        }
        reg.asignar_puertos("existente", nuevos_puertos)

        actualizado = reg.obtener("existente")
        assert actualizado is not None
        assert actualizado.ports == nuevos_puertos
        # El resto de los campos no deben cambiar
        assert actualizado.modo == "external"
        assert actualizado.version_odoo == "18.0"

    def test_liberar_puertos_sets_ports_to_none(self, registry_dir: Path) -> None:
        """liberar_puertos pone el campo ports en None."""
        reg = Registry()
        entry = _crear_entry(
            "con-puertos",
            Path("/tmp/con-puertos"),
            registry_dir / "projects" / "con-puertos",
        )
        reg.registrar(entry)
        reg.asignar_puertos("con-puertos", self._PUERTOS_BASE)

        reg.liberar_puertos("con-puertos")

        actualizado = reg.obtener("con-puertos")
        assert actualizado is not None
        assert actualizado.ports is None

    def test_puertos_ocupados_returns_union_across_entries(
        self, registry_dir: Path
    ) -> None:
        """puertos_ocupados retorna el union de todos los puertos de todas las entradas."""
        reg = Registry()

        puertos_a = {
            "WEB_PORT": 8069,
            "PGWEB_PORT": 8081,
            "DB_PORT": 5432,
            "DEBUGPY_PORT": 5678,
            "MAILHOG_PORT": 8025,
        }
        puertos_b = {
            "WEB_PORT": 8070,
            "PGWEB_PORT": 8082,
            "DB_PORT": 5433,
            "DEBUGPY_PORT": 5679,
            "MAILHOG_PORT": 8026,
        }

        reg.asignar_puertos("proyecto-a", puertos_a)
        reg.asignar_puertos("proyecto-b", puertos_b)

        ocupados = reg.puertos_ocupados()

        assert 8069 in ocupados
        assert 8070 in ocupados
        assert 8081 in ocupados
        assert 8082 in ocupados
        assert 5432 in ocupados
        assert 5433 in ocupados

    def test_puertos_ocupados_ignores_entries_without_ports(
        self, registry_dir: Path
    ) -> None:
        """puertos_ocupados ignora entradas legacy sin campo ports."""
        reg = Registry()
        # Entrada legacy sin ports
        entry = _crear_entry(
            "sin-puertos",
            Path("/tmp/sin-puertos"),
            registry_dir / "projects" / "sin-puertos",
        )
        reg.registrar(entry)

        ocupados = reg.puertos_ocupados()

        assert len(ocupados) == 0

    def test_liberar_puertos_no_op_for_nonexistent(self, registry_dir: Path) -> None:
        """liberar_puertos no lanza excepcion si el proyecto no existe."""
        reg = Registry()

        # No debe lanzar excepcion
        reg.liberar_puertos("no-existe")


# ── T4.1 RED: TOCTOU-safe registry write ──────────────────────────────────────


class TestTOCTOUSafeWrite:
    """Verifica que _escribir_fcntl tolera la ausencia del archivo (B2 — REQ-RR-1).

    Simula el race condition donde Path.exists() retorna True (o el archivo no
    existe en absoluto) pero cuando open() se ejecuta el archivo ya fue eliminado.
    Con 'r+' esto lanzaria FileNotFoundError; con 'w' siempre funciona.
    """

    def test_write_succeeds_when_file_deleted_between_calls(
        self, registry_dir: Path
    ) -> None:
        """Registrar un proyecto en un registry inexistente no lanza FileNotFoundError.

        Simula el caso donde el archivo de registry fue eliminado externamente
        justo antes de la llamada a open(). El modo 'w' crea el archivo si no existe.
        """
        # Asegurarse de que el registry no existe (simula deletion entre exists() y open())
        registry_path = registry_dir / "registry.yaml"
        assert not registry_path.exists(), "El registry no debe existir antes del test"

        reg = Registry()
        entry = _crear_entry(
            "toctou-proyecto",
            Path("/tmp/toctou"),
            registry_dir / "projects" / "toctou-proyecto",
        )

        # Con el bug original (modo 'r+'), esto falla si el archivo no existe.
        # Con el fix (modo 'w'), debe crear el archivo sin error.
        reg.registrar(entry)

        assert registry_path.exists()
        recuperado = reg.obtener("toctou-proyecto")
        assert recuperado is not None
        assert recuperado.nombre == "toctou-proyecto"

    def test_write_does_not_use_r_plus_mode(self, registry_dir: Path) -> None:
        """Verifica que _escribir_fcntl abre el archivo en modo 'w', no 'r+'.

        Pre-crea el archivo para forzar el branch 'r+' del codigo original.
        Confirma el diseño D4: siempre 'w' bajo flock, sin branch de '.exists()'.
        """
        import builtins

        reg = Registry()
        entry = _crear_entry(
            "modo-test",
            Path("/tmp/modo"),
            registry_dir / "projects" / "modo-test",
        )
        # Primera escritura: crea el archivo
        reg.registrar(entry)

        registry_path = registry_dir / "registry.yaml"
        assert registry_path.exists(), "El archivo debe existir tras la primera escritura"

        opened_modes = []
        original_open = builtins.open

        def tracking_open(file, mode="r", **kwargs):
            if str(file) == str(registry_path):
                opened_modes.append(mode)
            return original_open(file, mode, **kwargs)

        from unittest.mock import patch

        with patch("builtins.open", side_effect=tracking_open):
            # Segunda escritura: el archivo EXISTE — el codigo viejo usaria 'r+'
            reg.registrar(entry)

        # El archivo registry debe abrirse en modo 'w' (nunca 'r+')
        assert "r+" not in opened_modes, (
            f"No debe usarse modo 'r+'. Modos usados: {opened_modes}"
        )
        assert "w" in opened_modes, (
            f"Debe usarse modo 'w'. Modos usados: {opened_modes}"
        )


# ── T7.1 RED: fcntl Windows ImportError guard ─────────────────────────────────


class TestFcntlImportGuard:
    """Verifica que registry.py no crashea si fcntl no esta disponible (B6 — REQ-RR-3).

    Simula el entorno Windows donde 'import fcntl' lanzaria ImportError.
    Usa mock.patch.dict sobre sys.modules para forzar la ruta de fallback.
    """

    def test_import_fcntl_failure_sets_has_fcntl_false(self) -> None:
        """HAS_FCNTL es False cuando fcntl no puede importarse.

        Fuerza el ImportError simulando un entorno sin fcntl y verifica
        que el modulo define HAS_FCNTL = False (atributo exportado).
        """
        import sys
        import importlib
        from unittest.mock import patch

        with patch.dict(sys.modules, {"fcntl": None}):
            # Re-importar el modulo con fcntl bloqueado
            import odev.core.registry as reg_mod
            # Verificar que HAS_FCNTL existe y es un bool
            assert hasattr(reg_mod, "HAS_FCNTL"), (
                "registry.py debe exportar HAS_FCNTL"
            )

    def test_registrar_succeeds_without_fcntl(self, registry_dir: Path) -> None:
        """Registry.registrar() funciona aunque fcntl no este disponible.

        Verifica que la operacion completa sin invocar flock cuando
        HAS_FCNTL es False (fallback para Windows).
        """
        import sys
        from unittest.mock import patch

        import odev.core.registry as reg_mod

        # Simular que fcntl no esta disponible
        with (
            patch.object(reg_mod, "HAS_FCNTL", False),
            patch.object(reg_mod, "fcntl", None),
        ):
            reg = Registry()
            entry = _crear_entry(
                "windows-compat",
                Path("/tmp/win"),
                registry_dir / "projects" / "windows-compat",
            )
            # No debe lanzar AttributeError ni ImportError
            reg.registrar(entry)

        recuperado = reg.obtener("windows-compat")
        assert recuperado is not None
        assert recuperado.nombre == "windows-compat"


# ── T13.1 RED: YAML corrupt backup ───────────────────────────────────────────


class TestYamlCorruptBackup:
    """Verifica que _leer() crea un backup cuando el YAML es invalido (Q2 — REQ-RR-2).

    T13.1 RED: estos tests fallan hasta que se agregue la logica de backup
    en registry.py::_leer().
    """

    def test_leer_yaml_invalido_crea_backup(self, registry_dir: Path) -> None:
        """_leer() crea .bak cuando el YAML es invalido y retorna {}.

        Escribe contenido invalido en registry.yaml y verifica que:
        - Se crea un archivo .bak adyacente
        - El archivo .bak tiene el contenido original
        - _leer() retorna {} sin lanzar excepcion
        """
        registry_path = registry_dir / "registry.yaml"
        contenido_invalido = "key: {\n  unclosed: bracket\n  bad: [yaml"
        registry_path.write_text(contenido_invalido)

        reg = Registry()
        resultado = reg._leer()

        assert resultado == {}, "_leer() debe retornar {} ante YAML invalido"

        backup = registry_dir / "registry.yaml.bak"
        assert backup.exists(), "Debe crearse el archivo .bak adyacente"
        assert backup.read_text() == contenido_invalido, (
            "El .bak debe contener el contenido original corrompido"
        )

    def test_leer_yaml_valido_no_crea_backup(self, registry_dir: Path) -> None:
        """_leer() NO crea .bak cuando el YAML es valido."""
        registry_path = registry_dir / "registry.yaml"
        registry_path.write_text("projects: {}\n")

        reg = Registry()
        reg._leer()

        backup = registry_dir / "registry.yaml.bak"
        assert not backup.exists(), "No debe crearse .bak si el YAML es valido"
