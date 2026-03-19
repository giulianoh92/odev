"""Tests para odev.core.compat — deteccion de modo de operacion.

Verifica que detect_mode() identifique correctamente el modo PROJECT,
LEGACY y NONE segun los archivos presentes en el directorio.
"""

import pytest

from odev.core.compat import ProjectMode, detect_mode


class TestDetectMode:
    """Grupo de tests para la funcion detect_mode()."""

    def test_detecta_project_con_odev_yaml(self, tmp_path):
        """Detecta modo PROJECT cuando existe .odev.yaml."""
        (tmp_path / ".odev.yaml").write_text("odev_min_version: 0.1.0\n")

        modo, raiz = detect_mode(start=tmp_path)

        assert modo == ProjectMode.PROJECT
        assert raiz == tmp_path

    def test_detecta_legacy_con_docker_compose_y_cli(self, tmp_path):
        """Detecta modo LEGACY cuando existen docker-compose.yml + cli/main.py."""
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")
        cli_dir = tmp_path / "cli"
        cli_dir.mkdir()
        (cli_dir / "main.py").write_text("# viejo\n")

        modo, raiz = detect_mode(start=tmp_path)

        assert modo == ProjectMode.LEGACY
        assert raiz == tmp_path

    def test_detecta_project_con_docker_compose_sin_cli(self, tmp_path):
        """Detecta modo PROJECT cuando existe docker-compose.yml sin carpeta cli/."""
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")

        modo, raiz = detect_mode(start=tmp_path)

        assert modo == ProjectMode.PROJECT
        assert raiz == tmp_path

    def test_detecta_none_en_directorio_vacio(self, tmp_path):
        """Detecta modo NONE en un directorio vacio sin indicadores."""
        # Crear un subdirectorio aislado para evitar detectar archivos del sistema
        aislado = tmp_path / "aislado"
        aislado.mkdir()

        modo, raiz = detect_mode(start=aislado)

        assert modo == ProjectMode.NONE
        assert raiz is None

    def test_subdirectorio_encuentra_raiz_proyecto(self, tmp_path):
        """Recorre directorios hacia arriba para encontrar la raiz del proyecto."""
        (tmp_path / ".odev.yaml").write_text("odev_min_version: 0.1.0\n")
        subdirectorio = tmp_path / "addons" / "mi_modulo"
        subdirectorio.mkdir(parents=True)

        modo, raiz = detect_mode(start=subdirectorio)

        assert modo == ProjectMode.PROJECT
        assert raiz == tmp_path

    def test_odev_yaml_tiene_prioridad_sobre_legacy(self, tmp_path):
        """El archivo .odev.yaml gana sobre indicadores legacy."""
        # Crear ambos: .odev.yaml y docker-compose.yml + cli/
        (tmp_path / ".odev.yaml").write_text("odev_min_version: 0.1.0\n")
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")
        cli_dir = tmp_path / "cli"
        cli_dir.mkdir()
        (cli_dir / "main.py").write_text("# viejo\n")

        modo, raiz = detect_mode(start=tmp_path)

        assert modo == ProjectMode.PROJECT
        assert raiz == tmp_path

    def test_docker_compose_con_cli_incompleto_es_project(self, tmp_path):
        """Si existe cli/ pero sin main.py, el modo es PROJECT (no LEGACY)."""
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")
        cli_dir = tmp_path / "cli"
        cli_dir.mkdir()
        # cli/ existe pero no tiene main.py

        modo, raiz = detect_mode(start=tmp_path)

        assert modo == ProjectMode.PROJECT
        assert raiz == tmp_path

    def test_usa_cwd_cuando_start_es_none(self, tmp_path, monkeypatch):
        """Usa el directorio de trabajo actual cuando start=None."""
        (tmp_path / ".odev.yaml").write_text("odev_min_version: 0.1.0\n")
        monkeypatch.chdir(tmp_path)

        modo, raiz = detect_mode(start=None)

        assert modo == ProjectMode.PROJECT
        assert raiz == tmp_path

    @pytest.mark.parametrize(
        "modo_enum,valor_esperado",
        [
            (ProjectMode.PROJECT, "project"),
            (ProjectMode.LEGACY, "legacy"),
            (ProjectMode.NONE, "none"),
        ],
        ids=["project", "legacy", "none"],
    )
    def test_valores_enum_correctos(self, modo_enum, valor_esperado):
        """Verifica que los valores del enum ProjectMode sean correctos."""
        assert modo_enum.value == valor_esperado
