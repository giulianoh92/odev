"""Tests para odev.core.paths — resolucion de rutas del proyecto y templates.

Verifica que ProjectPaths resuelva correctamente las rutas relativas
al directorio raiz del proyecto, y que las funciones de templates
retornen directorios existentes con los archivos esperados.
"""

import pytest

from odev.core.compat import ProjectMode
from odev.core.paths import (
    ProjectPaths,
    get_module_template_dir,
    get_project_templates_dir,
    get_sql_templates_dir,
    get_templates_dir,
)


class TestProjectPaths:
    """Grupo de tests para la clase ProjectPaths."""

    def test_propiedades_retornan_rutas_correctas(self, tmp_path):
        """Todas las propiedades retornan rutas relativas a la raiz correctamente."""
        rutas = ProjectPaths(project_root=tmp_path)

        assert rutas.root == tmp_path
        assert rutas.addons_dir == tmp_path / "addons"
        assert rutas.enterprise_dir == tmp_path / "enterprise"
        assert rutas.config_dir == tmp_path / "config"
        assert rutas.snapshots_dir == tmp_path / "snapshots"
        assert rutas.logs_dir == tmp_path / "logs"
        assert rutas.docs_dir == tmp_path / "docs"
        assert rutas.env_file == tmp_path / ".env"
        assert rutas.env_example == tmp_path / ".env.example"
        assert rutas.docker_compose_file == tmp_path / "docker-compose.yml"
        assert rutas.odev_config == tmp_path / ".odev.yaml"

    def test_modo_es_project_con_raiz_explicita(self, tmp_path):
        """Cuando se pasa project_root explicito, el modo siempre es PROJECT."""
        rutas = ProjectPaths(project_root=tmp_path)

        assert rutas.mode == ProjectMode.PROJECT

    def test_lanza_error_sin_proyecto(self, tmp_path, monkeypatch):
        """Lanza FileNotFoundError cuando no se encuentra proyecto ni se pasa raiz."""
        # Crear un directorio aislado sin indicadores de proyecto
        aislado = tmp_path / "aislado"
        aislado.mkdir()
        monkeypatch.chdir(aislado)

        with pytest.raises(FileNotFoundError, match="No se encontro un proyecto odev"):
            ProjectPaths()

    def test_deteccion_automatica_con_odev_yaml(self, tmp_path, monkeypatch):
        """Detecta automaticamente el proyecto cuando existe .odev.yaml."""
        (tmp_path / ".odev.yaml").write_text("odev_min_version: 0.1.0\n")
        monkeypatch.chdir(tmp_path)

        rutas = ProjectPaths()

        assert rutas.root == tmp_path
        assert rutas.mode == ProjectMode.PROJECT

    def test_raiz_explicita_acepta_directorio_cualquiera(self, tmp_path):
        """El parametro project_root funciona con cualquier directorio."""
        subdirectorio = tmp_path / "custom" / "project"
        subdirectorio.mkdir(parents=True)

        rutas = ProjectPaths(project_root=subdirectorio)

        assert rutas.root == subdirectorio
        assert rutas.addons_dir == subdirectorio / "addons"


class TestTemplatePaths:
    """Grupo de tests para las funciones de acceso a templates del paquete."""

    def test_get_templates_dir_existe(self):
        """get_templates_dir() retorna un directorio existente."""
        directorio = get_templates_dir()

        assert directorio.exists()
        assert directorio.is_dir()

    def test_get_module_template_dir_contiene_archivos_esperados(self):
        """El template de modulo contiene __manifest__.py y __init__.py."""
        directorio = get_module_template_dir()

        assert directorio.exists()
        assert (directorio / "__manifest__.py").exists()
        assert (directorio / "__init__.py").exists()
        assert (directorio / "models").is_dir()

    def test_get_project_templates_dir_contiene_j2(self):
        """El directorio de templates de proyecto contiene archivos .j2."""
        directorio = get_project_templates_dir()

        assert directorio.exists()
        archivos_j2 = list(directorio.glob("*.j2"))
        assert len(archivos_j2) > 0, "Debe haber al menos un template .j2"

    def test_get_project_templates_dir_contiene_templates_clave(self):
        """Los templates clave del proyecto estan presentes."""
        directorio = get_project_templates_dir()

        templates_esperados = [
            "docker-compose.yml.j2",
            "env.j2",
            "odoo.conf.j2",
            "odev.yaml.j2",
            "gitignore.j2",
            "entrypoint.sh.j2",
        ]
        for nombre in templates_esperados:
            assert (directorio / nombre).exists(), f"Falta template: {nombre}"

    def test_get_sql_templates_dir_retorna_path(self):
        """get_sql_templates_dir() retorna un path valido (puede no existir en desarrollo)."""
        directorio = get_sql_templates_dir()

        # Solo verificamos que retorna un Path, no que exista necesariamente
        assert directorio.name == "sql"
        assert directorio.parent == get_templates_dir()
