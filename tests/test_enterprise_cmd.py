"""Tests para los comandos enterprise (import, path).

Valida la logica de conteo de modulos, creacion de symlinks/copias,
sobreescritura con --force, y el subcomando path.
Usa monkeypatch para redirigir ENTERPRISE_DIR a directorios temporales.
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from odev.commands.enterprise import _contar_modulos, _version_dir
from odev.main import app

runner = CliRunner()


@pytest.fixture
def enterprise_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirige ENTERPRISE_DIR a un directorio temporal.

    Evita contaminar el ~/.odev/ real durante los tests.
    """
    import odev.commands.enterprise as ent_mod
    import odev.core.registry as reg_mod

    fake_enterprise = tmp_path / "enterprise"
    monkeypatch.setattr(reg_mod, "ENTERPRISE_DIR", fake_enterprise)
    monkeypatch.setattr(ent_mod, "ENTERPRISE_DIR", fake_enterprise)
    return fake_enterprise


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    """Crea un directorio fuente con modulos Odoo simulados.

    Retorna:
        Path al directorio fuente con 3 modulos fake.
    """
    fuente = tmp_path / "enterprise_source"
    fuente.mkdir()
    for nombre in ["module_a", "module_b", "module_c"]:
        mod_dir = fuente / nombre
        mod_dir.mkdir()
        (mod_dir / "__manifest__.py").write_text("{}")
    return fuente


class TestContarModulos:
    """Tests para la funcion _contar_modulos."""

    def test_contar_modulos(self, source_dir: Path) -> None:
        """Cuenta correctamente modulos con __manifest__.py."""
        assert _contar_modulos(source_dir) == 3

    def test_contar_modulos_dir_vacio(self, tmp_path: Path) -> None:
        """Directorio vacio retorna 0."""
        dir_vacio = tmp_path / "vacio"
        dir_vacio.mkdir()
        assert _contar_modulos(dir_vacio) == 0

    def test_contar_modulos_dir_inexistente(self, tmp_path: Path) -> None:
        """Directorio inexistente retorna 0."""
        assert _contar_modulos(tmp_path / "no_existe") == 0

    def test_contar_modulos_ignora_archivos(self, tmp_path: Path) -> None:
        """Archivos sueltos (no directorios) no se cuentan como modulos."""
        dir_con_archivos = tmp_path / "mixto"
        dir_con_archivos.mkdir()
        (dir_con_archivos / "archivo.txt").write_text("no soy modulo")
        mod = dir_con_archivos / "modulo_real"
        mod.mkdir()
        (mod / "__manifest__.py").write_text("{}")
        assert _contar_modulos(dir_con_archivos) == 1

    def test_contar_modulos_ignora_dirs_sin_manifest(self, tmp_path: Path) -> None:
        """Directorios sin __manifest__.py no se cuentan."""
        directorio = tmp_path / "sin_manifest"
        directorio.mkdir()
        (directorio / "no_modulo").mkdir()
        (directorio / "no_modulo" / "models.py").write_text("")
        assert _contar_modulos(directorio) == 0


class TestVersionDir:
    """Tests para la funcion _version_dir."""

    def test_version_dir(self, enterprise_dir: Path) -> None:
        """Retorna la ruta correcta para una version."""
        resultado = _version_dir("19.0")
        assert resultado == enterprise_dir / "19.0"


class TestEnterpriseImport:
    """Tests para el subcomando enterprise import."""

    def test_import_creates_symlink(
        self, enterprise_dir: Path, source_dir: Path
    ) -> None:
        """Import sin --copy crea un symlink."""
        result = runner.invoke(app, ["enterprise", "import", "19.0", str(source_dir)])

        assert result.exit_code == 0
        destino = enterprise_dir / "19.0"
        assert destino.is_symlink()
        assert destino.resolve() == source_dir.resolve()

    def test_import_copy_creates_directory(
        self, enterprise_dir: Path, source_dir: Path
    ) -> None:
        """Import con --copy crea una copia real del directorio."""
        result = runner.invoke(
            app, ["enterprise", "import", "19.0", str(source_dir), "--copy"]
        )

        assert result.exit_code == 0
        destino = enterprise_dir / "19.0"
        assert destino.is_dir()
        assert not destino.is_symlink()
        # Verificar que los modulos se copiaron
        assert (destino / "module_a" / "__manifest__.py").exists()

    def test_import_force_overwrites(
        self, enterprise_dir: Path, source_dir: Path
    ) -> None:
        """Import con --force sobreescribe una version existente."""
        # Crear version inicial
        enterprise_dir.mkdir(parents=True, exist_ok=True)
        destino = enterprise_dir / "19.0"
        destino.symlink_to(source_dir.resolve())
        assert destino.is_symlink()

        # Re-importar con --force --copy
        result = runner.invoke(
            app,
            ["enterprise", "import", "19.0", str(source_dir), "--force", "--copy"],
        )

        assert result.exit_code == 0
        assert destino.is_dir()
        assert not destino.is_symlink()

    def test_import_sin_force_falla_si_existe(
        self, enterprise_dir: Path, source_dir: Path
    ) -> None:
        """Import sin --force falla si ya existe la version."""
        enterprise_dir.mkdir(parents=True, exist_ok=True)
        destino = enterprise_dir / "19.0"
        destino.symlink_to(source_dir.resolve())

        result = runner.invoke(app, ["enterprise", "import", "19.0", str(source_dir)])

        assert result.exit_code == 1

    def test_import_source_vacio_muestra_warning(
        self, enterprise_dir: Path, tmp_path: Path
    ) -> None:
        """Import desde directorio vacio muestra advertencia pero continua."""
        dir_vacio = tmp_path / "vacio"
        dir_vacio.mkdir()

        result = runner.invoke(app, ["enterprise", "import", "19.0", str(dir_vacio)])

        assert result.exit_code == 0
        assert "No se encontraron modulos" in result.output


class TestEnterprisePath:
    """Tests para el subcomando enterprise path."""

    def test_path_existente(
        self, enterprise_dir: Path, source_dir: Path
    ) -> None:
        """Path retorna la ruta cuando la version existe."""
        enterprise_dir.mkdir(parents=True, exist_ok=True)
        destino = enterprise_dir / "19.0"
        destino.symlink_to(source_dir.resolve())

        result = runner.invoke(app, ["enterprise", "path", "19.0"])

        assert result.exit_code == 0
        # La salida debe contener la ruta resuelta
        assert str(source_dir.resolve()) in result.output.strip()

    def test_path_inexistente_sale_con_1(self, enterprise_dir: Path) -> None:
        """Path sale con codigo 1 si la version no existe."""
        result = runner.invoke(app, ["enterprise", "path", "18.0"])

        assert result.exit_code == 1


class TestRutaEnterpriseFallback:
    """Tests para el fallback de ruta_enterprise en ProjectConfig."""

    def test_fallback_a_compartido(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Si no hay path explicito y existe compartido, lo usa."""
        import yaml

        import odev.core.registry as reg_mod

        fake_enterprise = tmp_path / "odev_enterprise"
        monkeypatch.setattr(reg_mod, "ENTERPRISE_DIR", fake_enterprise)

        # Crear enterprise compartido para 19.0
        enterprise_19 = fake_enterprise / "19.0"
        enterprise_19.mkdir(parents=True)

        # Crear .odev.yaml con path default
        config_data = {
            "odoo": {"version": "19.0", "image": "odoo:19"},
            "enterprise": {"enabled": False, "path": "./enterprise"},
        }
        ruta_yaml = tmp_path / ".odev.yaml"
        ruta_yaml.write_text(yaml.dump(config_data), encoding="utf-8")

        from odev.core.project import ProjectConfig

        config = ProjectConfig(tmp_path)
        assert config.ruta_enterprise == str(enterprise_19)

    def test_path_explicito_tiene_prioridad(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Si hay path explicito en odev.yaml, no usa el fallback."""
        import yaml

        import odev.core.registry as reg_mod

        fake_enterprise = tmp_path / "odev_enterprise"
        monkeypatch.setattr(reg_mod, "ENTERPRISE_DIR", fake_enterprise)

        # Crear enterprise compartido para 19.0
        enterprise_19 = fake_enterprise / "19.0"
        enterprise_19.mkdir(parents=True)

        # Crear .odev.yaml con path explicito
        ruta_custom = "/opt/odoo/enterprise"
        config_data = {
            "odoo": {"version": "19.0", "image": "odoo:19"},
            "enterprise": {"enabled": True, "path": ruta_custom},
        }
        ruta_yaml = tmp_path / ".odev.yaml"
        ruta_yaml.write_text(yaml.dump(config_data), encoding="utf-8")

        from odev.core.project import ProjectConfig

        config = ProjectConfig(tmp_path)
        assert config.ruta_enterprise == ruta_custom

    def test_sin_compartido_retorna_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Si no hay path explicito ni compartido, retorna el default."""
        import yaml

        import odev.core.registry as reg_mod

        fake_enterprise = tmp_path / "odev_enterprise_vacio"
        monkeypatch.setattr(reg_mod, "ENTERPRISE_DIR", fake_enterprise)

        config_data = {
            "odoo": {"version": "19.0", "image": "odoo:19"},
            "enterprise": {"enabled": False, "path": "./enterprise"},
        }
        ruta_yaml = tmp_path / ".odev.yaml"
        ruta_yaml.write_text(yaml.dump(config_data), encoding="utf-8")

        from odev.core.project import ProjectConfig

        config = ProjectConfig(tmp_path)
        assert config.ruta_enterprise == "./enterprise"
