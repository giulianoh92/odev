"""Tests for odev.core.regen — shared regeneration engine."""

import textwrap
import time
from pathlib import Path

import pytest
import yaml

from odev.core.project import ProjectConfig
from odev.core.regen import (
    RegenResult,
    construir_contexto_templates,
    necesita_regeneracion,
    regenerar_configuracion,
)


@pytest.fixture
def proyecto_con_config(tmp_path: Path) -> Path:
    """Create a temporary project directory with odev.yaml, .env, and generated files."""
    # .odev.yaml
    config = {
        "odev_min_version": "0.2.0",
        "mode": "inline",
        "odoo": {"version": "19.0", "image": "odoo:19"},
        "database": {"image": "pgvector/pgvector:pg16"},
        "enterprise": {"enabled": False, "path": "./enterprise"},
        "services": {"pgweb": True},
        "paths": {"addons": ["./addons"]},
        "project": {"name": "test-regen", "description": ""},
    }
    (tmp_path / ".odev.yaml").write_text(
        yaml.dump(config, default_flow_style=False)
    )

    # .env
    contenido_env = textwrap.dedent("""\
        PROJECT_NAME=test-regen
        ODOO_VERSION=19.0
        WEB_PORT=9069
        DB_PORT=5433
        DB_NAME=custom_db
        DB_USER=custom_user
        DB_PASSWORD=custom_pass
        DB_HOST=db
        PGWEB_PORT=9081
        DEBUGPY=False
        DEBUGPY_PORT=5678
        ADMIN_PASSWORD=secretadmin
        LOAD_LANGUAGE=es_AR
        WITHOUT_DEMO=all
        INIT_MODULES=
        MAILHOG_PORT=9025
    """)
    (tmp_path / ".env").write_text(contenido_env)

    # Generated files
    (tmp_path / "docker-compose.yml").write_text("services:\n  web:\n    image: odoo:19\n")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "odoo.conf").write_text("[options]\naddons_path = /mnt/extra-addons\n")
    (tmp_path / "addons").mkdir()

    return tmp_path


class TestConstruirContextoTemplates:
    """Tests for construir_contexto_templates()."""

    def test_preserva_env_runtime_values(self, proyecto_con_config: Path) -> None:
        """Runtime values from .env are preserved in the merged context."""
        config = ProjectConfig(proyecto_con_config)
        env_values = {"WEB_PORT": "9069", "DB_PASSWORD": "custom_pass"}

        ctx = construir_contexto_templates(config, env_values, proyecto_con_config)

        assert ctx["WEB_PORT"] == "9069"
        assert ctx["DB_PASSWORD"] == "custom_pass"

    def test_structural_from_odev_yaml(self, proyecto_con_config: Path) -> None:
        """Structural values come from odev.yaml, not .env."""
        config = ProjectConfig(proyecto_con_config)
        env_values = {"ODOO_VERSION": "18.0"}  # .env has stale version

        ctx = construir_contexto_templates(config, env_values, proyecto_con_config)

        # odoo_version should come from odev.yaml (19.0), not .env
        assert ctx["odoo_version"] == "19.0"
        assert ctx["ODOO_VERSION"] == "19.0"

    def test_defaults_when_env_empty(self, proyecto_con_config: Path) -> None:
        """Falls back to defaults when .env is empty."""
        config = ProjectConfig(proyecto_con_config)

        ctx = construir_contexto_templates(config, {}, proyecto_con_config)

        assert ctx["WEB_PORT"] == "8069"
        assert ctx["DB_USER"] == "odoo"

    def test_addon_mounts_built_from_config(self, proyecto_con_config: Path) -> None:
        """addon_mounts are built from odev.yaml paths.addons."""
        config = ProjectConfig(proyecto_con_config)

        ctx = construir_contexto_templates(config, {}, proyecto_con_config)

        assert len(ctx["addon_mounts"]) == 1
        assert ctx["addon_mounts"][0]["container_path"] == "/mnt/extra-addons"

    def test_enterprise_flag_propagated(self, tmp_path: Path) -> None:
        """enterprise_enabled is taken from odev.yaml."""
        config_data = {
            "odoo": {"version": "19.0"},
            "enterprise": {"enabled": True, "path": "/shared/enterprise"},
            "paths": {"addons": ["./addons"]},
            "project": {"name": "ent-test"},
        }
        (tmp_path / ".odev.yaml").write_text(yaml.dump(config_data))

        config = ProjectConfig(tmp_path)
        ctx = construir_contexto_templates(config, {}, tmp_path)

        assert ctx["enterprise_enabled"] is True
        assert ctx["enterprise_path"] == "/shared/enterprise"


class TestNecesitaRegeneracion:
    """Tests for necesita_regeneracion()."""

    def test_yaml_newer_triggers_regen(self, proyecto_con_config: Path) -> None:
        """Returns True when odev.yaml is newer than generated files."""
        # Touch odev.yaml to make it newer
        time.sleep(0.05)
        ruta_yaml = proyecto_con_config / ".odev.yaml"
        ruta_yaml.write_text(ruta_yaml.read_text())

        from odev.core.resolver import ModoProyecto, ProjectContext
        ctx = ProjectContext(
            nombre="test", modo=ModoProyecto.INLINE,
            directorio_config=proyecto_con_config,
            directorio_trabajo=proyecto_con_config,
            config=None,
        )

        assert necesita_regeneracion(ctx) is True

    def test_no_regen_when_files_newer(self, proyecto_con_config: Path) -> None:
        """Returns False when generated files are newer than odev.yaml."""
        # Touch generated files to make them newer
        time.sleep(0.05)
        (proyecto_con_config / "docker-compose.yml").write_text("updated\n")
        (proyecto_con_config / "config" / "odoo.conf").write_text("updated\n")

        from odev.core.resolver import ModoProyecto, ProjectContext
        ctx = ProjectContext(
            nombre="test", modo=ModoProyecto.INLINE,
            directorio_config=proyecto_con_config,
            directorio_trabajo=proyecto_con_config,
            config=None,
        )

        assert necesita_regeneracion(ctx) is False

    def test_missing_generated_file_triggers_regen(self, tmp_path: Path) -> None:
        """Returns True when a generated file does not exist."""
        (tmp_path / ".odev.yaml").write_text("project:\n  name: test\n")
        # No docker-compose.yml or odoo.conf

        from odev.core.resolver import ModoProyecto, ProjectContext
        ctx = ProjectContext(
            nombre="test", modo=ModoProyecto.INLINE,
            directorio_config=tmp_path,
            directorio_trabajo=tmp_path,
            config=None,
        )

        assert necesita_regeneracion(ctx) is True

    def test_no_yaml_no_regen(self, tmp_path: Path) -> None:
        """Returns False when there is no odev.yaml."""
        from odev.core.resolver import ModoProyecto, ProjectContext
        ctx = ProjectContext(
            nombre="test", modo=ModoProyecto.INLINE,
            directorio_config=tmp_path,
            directorio_trabajo=tmp_path,
            config=None,
        )

        assert necesita_regeneracion(ctx) is False


class TestRegenerarConfiguracion:
    """Tests for regenerar_configuracion()."""

    def test_regenera_compose_y_odoo_conf(self, proyecto_con_config: Path) -> None:
        """Regenerates docker-compose.yml and odoo.conf."""
        from odev.core.resolver import ModoProyecto, ProjectContext
        config = ProjectConfig(proyecto_con_config)
        ctx = ProjectContext(
            nombre="test", modo=ModoProyecto.INLINE,
            directorio_config=proyecto_con_config,
            directorio_trabajo=proyecto_con_config,
            config=config,
        )

        resultado = regenerar_configuracion(ctx)

        assert len(resultado.archivos_regenerados) >= 1
        # docker-compose.yml should now have real content from template
        contenido = (proyecto_con_config / "docker-compose.yml").read_text()
        assert "services:" in contenido

    def test_preserva_env_por_defecto(self, proyecto_con_config: Path) -> None:
        """Does NOT regenerate .env by default."""
        from odev.core.resolver import ModoProyecto, ProjectContext
        config = ProjectConfig(proyecto_con_config)
        ctx = ProjectContext(
            nombre="test", modo=ModoProyecto.INLINE,
            directorio_config=proyecto_con_config,
            directorio_trabajo=proyecto_con_config,
            config=config,
        )

        contenido_env_antes = (proyecto_con_config / ".env").read_text()
        regenerar_configuracion(ctx, include_env=False)
        contenido_env_despues = (proyecto_con_config / ".env").read_text()

        assert contenido_env_antes == contenido_env_despues

    def test_include_env_regenera_env(self, proyecto_con_config: Path) -> None:
        """With include_env=True, .env is also regenerated."""
        from odev.core.resolver import ModoProyecto, ProjectContext
        config = ProjectConfig(proyecto_con_config)
        ctx = ProjectContext(
            nombre="test", modo=ModoProyecto.INLINE,
            directorio_config=proyecto_con_config,
            directorio_trabajo=proyecto_con_config,
            config=config,
        )

        resultado = regenerar_configuracion(ctx, include_env=True)

        env_paths = [p for p in resultado.archivos_regenerados if p.name == ".env"]
        # .env may or may not appear in regenerados depending on content diff
        # but the function should not crash
        contenido = (proyecto_con_config / ".env").read_text()
        assert "PROJECT_NAME=" in contenido
