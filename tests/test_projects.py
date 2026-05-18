"""Tests para odev.commands.projects — listado de proyectos.

Verifica el subcomando 'list', el callback bare 'odev projects', y el flag --json.
Cubre: backward-compat del callback, subcommand explicito, JSON vacio, JSON con entradas,
y la regresion de la superficie dual (callback + subcommand emiten la misma forma JSON).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

if TYPE_CHECKING:
    pass


runner = CliRunner()


def _make_entry(
    nombre: str = "sis-odoo",
    trabajo: str = "/work/sis-odoo",
    config: str = "/work/sis-odoo",
    modo: str = "external",
    version_odoo: str = "18.0",
    ports: dict | None = None,
) -> MagicMock:
    """Construye un RegistryEntry mock con los atributos necesarios."""
    entry = MagicMock()
    entry.nombre = nombre
    entry.directorio_trabajo = Path(trabajo)
    entry.directorio_config = Path(config)
    entry.modo = modo
    entry.version_odoo = version_odoo
    entry.ports = ports
    return entry


class TestProjectsBareLists:
    """test_projects_bare_still_lists — el callback bare sigue listando en tabla Rich."""

    def test_projects_bare_still_lists(self, tmp_path):
        """odev projects (sin subcomando) renderiza tabla Rich y termina con exit 0."""
        from odev.commands.projects import app

        entry = _make_entry(trabajo=str(tmp_path), config=str(tmp_path))
        with patch("odev.commands.projects.Registry") as mock_reg:
            mock_reg.return_value.listar.return_value = [entry]
            result = runner.invoke(app, [])

        assert result.exit_code == 0, f"stderr: {result.stderr!r}"
        # La tabla Rich debe mostrar el nombre del proyecto
        assert "sis-odoo" in result.output


class TestProjectsListSubcommand:
    """test_projects_list_subcommand_exists — el subcommand 'list' existe y lista."""

    def test_list_subcommand_exists_and_lists(self, tmp_path):
        """odev projects list produce la misma tabla Rich y exit 0."""
        from odev.commands.projects import app

        entry = _make_entry(trabajo=str(tmp_path), config=str(tmp_path))
        with patch("odev.commands.projects.Registry") as mock_reg:
            mock_reg.return_value.listar.return_value = [entry]
            result = runner.invoke(app, ["list"])

        assert result.exit_code == 0, f"output: {result.output!r}"
        assert "sis-odoo" in result.output


class TestProjectsListJsonEmpty:
    """test_projects_list_json_empty — --json con registro vacio emite {\"projects\": []}."""

    def test_list_json_empty_registry(self):
        """odev projects list --json con registro vacio emite JSON correcto."""
        from odev.commands.projects import app

        with patch("odev.commands.projects.Registry") as mock_reg:
            mock_reg.return_value.listar.return_value = []
            result = runner.invoke(app, ["list", "--json"])

        assert result.exit_code == 0, f"output: {result.output!r}"
        data = json.loads(result.output.strip())
        assert data == {"projects": []}


class TestProjectsListJsonWithEntries:
    """test_projects_list_json_with_entries — JSON schema con entradas reales."""

    def test_list_json_with_two_entries(self, tmp_path):
        """odev projects list --json con 2 entradas: schema name/path/modo/odoo_version/puerto_odoo."""
        from odev.commands.projects import app

        work1 = tmp_path / "proj-a"
        work1.mkdir()
        cfg1 = tmp_path / "cfg-a"
        cfg1.mkdir()
        entry1 = _make_entry(
            nombre="proj-a",
            trabajo=str(work1),
            config=str(cfg1),
            modo="external",
            version_odoo="18.0",
            ports={"WEB_PORT": 8069},
        )

        work2 = tmp_path / "proj-b"
        cfg2 = tmp_path / "cfg-b"
        # No crear los dirs — legacy entry (ports=None, directorio no existe)
        entry2 = _make_entry(
            nombre="proj-b",
            trabajo=str(work2),
            config=str(cfg2),
            modo="inline",
            version_odoo="17.0",
            ports=None,
        )

        with patch("odev.commands.projects.Registry") as mock_reg:
            mock_reg.return_value.listar.return_value = [entry1, entry2]
            result = runner.invoke(app, ["list", "--json"])

        assert result.exit_code == 0, f"output: {result.output!r}"
        data = json.loads(result.output.strip())
        assert "projects" in data
        assert len(data["projects"]) == 2

        # Verificar schema de la primera entrada
        p_a = next(p for p in data["projects"] if p["name"] == "proj-a")
        assert p_a["modo"] == "external"
        assert p_a["odoo_version"] == "18.0"
        assert p_a["path"] == str(work1)
        assert p_a["puerto_odoo"] == 8069
        assert "directorio_trabajo" in p_a
        assert "directorio_config" in p_a
        assert "exists" in p_a

        # Segunda entrada: puerto_odoo debe ser null
        p_b = next(p for p in data["projects"] if p["name"] == "proj-b")
        assert p_b["puerto_odoo"] is None

    def test_list_json_schema_required_fields(self, tmp_path):
        """Todos los campos requeridos por el spec estan presentes en cada entrada JSON."""
        from odev.commands.projects import app

        work = tmp_path / "my-proj"
        work.mkdir()
        entry = _make_entry(
            nombre="my-proj",
            trabajo=str(work),
            config=str(work),
            modo="external",
            version_odoo="18.0",
            ports={"WEB_PORT": 8069},
        )

        with patch("odev.commands.projects.Registry") as mock_reg:
            mock_reg.return_value.listar.return_value = [entry]
            result = runner.invoke(app, ["list", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output.strip())
        entry_data = data["projects"][0]
        required_fields = {"name", "path", "modo", "odoo_version", "puerto_odoo",
                           "directorio_trabajo", "directorio_config", "exists"}
        for field in required_fields:
            assert field in entry_data, f"Campo requerido faltante: {field!r}"


class TestProjectsBareJsonAlsoWorks:
    """test_projects_bare_json_also_works — callback path con --json emite misma forma."""

    def test_bare_json_callback(self, tmp_path):
        """odev projects --json (callback path) emite JSON identico al subcomando list."""
        from odev.commands.projects import app

        work = tmp_path / "sis-odoo"
        work.mkdir()
        entry = _make_entry(
            nombre="sis-odoo",
            trabajo=str(work),
            config=str(work),
            modo="external",
            version_odoo="18.0",
            ports={"WEB_PORT": 8069},
        )

        with patch("odev.commands.projects.Registry") as mock_reg:
            mock_reg.return_value.listar.return_value = [entry]
            result = runner.invoke(app, ["--json"])

        assert result.exit_code == 0, f"output: {result.output!r}"
        data = json.loads(result.output.strip())
        assert "projects" in data
        assert data["projects"][0]["name"] == "sis-odoo"
