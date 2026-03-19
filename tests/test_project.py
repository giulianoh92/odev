"""Tests para odev.core.project — carga y validacion de .odev.yaml.

Verifica que ProjectConfig cargue la configuracion correctamente,
aplique valores por defecto, verifique compatibilidad de version
y maneje errores de archivos faltantes.
"""

from unittest.mock import patch

import pytest
import yaml

from odev.core.project import ProjectConfig, _mezclar_profundo


class TestProjectConfig:
    """Grupo de tests para la clase ProjectConfig."""

    def test_carga_yaml_valido(self, tmp_path):
        """Carga un .odev.yaml valido y lee sus propiedades correctamente."""
        config = {
            "odev_min_version": "0.2.0",
            "odoo": {"version": "18.0", "image": "odoo:18"},
            "database": {"image": "postgres:15"},
            "enterprise": {"enabled": True, "path": "./enterprise"},
            "services": {"pgweb": False},
            "project": {"name": "mi-proyecto", "description": "Un proyecto de prueba"},
        }
        (tmp_path / ".odev.yaml").write_text(
            yaml.dump(config, default_flow_style=False),
            encoding="utf-8",
        )

        pc = ProjectConfig(tmp_path)

        assert pc.version_minima == "0.2.0"
        assert pc.version_odoo == "18.0"
        assert pc.imagen_odoo == "odoo:18"
        assert pc.imagen_db == "postgres:15"
        assert pc.enterprise_habilitado is True
        assert pc.pgweb_habilitado is False
        assert pc.nombre_proyecto == "mi-proyecto"
        assert pc.descripcion_proyecto == "Un proyecto de prueba"

    def test_aplica_valores_por_defecto_para_claves_faltantes(self, tmp_path):
        """Rellena con valores por defecto las claves no presentes en el yaml."""
        # YAML minimo, sin la mayoria de claves
        config = {"project": {"name": "minimal"}}
        (tmp_path / ".odev.yaml").write_text(
            yaml.dump(config, default_flow_style=False),
            encoding="utf-8",
        )

        pc = ProjectConfig(tmp_path)

        # Deben existir los valores por defecto
        assert pc.version_minima == "0.1.0"
        assert pc.version_odoo == "19.0"
        assert pc.imagen_odoo == "odoo:19"
        assert pc.imagen_db == "pgvector/pgvector:pg16"
        assert pc.enterprise_habilitado is False
        assert pc.pgweb_habilitado is True
        assert pc.nombre_proyecto == "minimal"

    def test_lanza_error_si_no_existe_yaml(self, tmp_path):
        """Lanza FileNotFoundError si .odev.yaml no existe."""
        with pytest.raises(FileNotFoundError, match="No se encontro .odev.yaml"):
            ProjectConfig(tmp_path)

    def test_maneja_yaml_vacio_gracefully(self, tmp_path):
        """Maneja un .odev.yaml vacio retornando todos los valores por defecto."""
        (tmp_path / ".odev.yaml").write_text("", encoding="utf-8")

        pc = ProjectConfig(tmp_path)

        # Todos los valores deben ser los por defecto
        assert pc.version_minima == "0.1.0"
        assert pc.version_odoo == "19.0"

    def test_version_compatible_retorna_true(self, tmp_path):
        """Retorna True cuando la version del CLI es >= la requerida."""
        config = {"odev_min_version": "0.1.0"}
        (tmp_path / ".odev.yaml").write_text(
            yaml.dump(config, default_flow_style=False),
            encoding="utf-8",
        )

        pc = ProjectConfig(tmp_path)

        # odev.__version__ es 0.1.0, y min es 0.1.0 => compatible
        with patch("odev.core.project.__version__", "0.1.0"):
            assert pc.verificar_compatibilidad_version() is True

    def test_version_incompatible_retorna_false_y_warn(self, tmp_path):
        """Retorna False y muestra warning cuando la version del CLI es menor."""
        config = {"odev_min_version": "99.0.0"}
        (tmp_path / ".odev.yaml").write_text(
            yaml.dump(config, default_flow_style=False),
            encoding="utf-8",
        )

        pc = ProjectConfig(tmp_path)

        with patch("odev.core.project.warning") as mock_warning:
            resultado = pc.verificar_compatibilidad_version()

        assert resultado is False
        mock_warning.assert_called_once()
        # Verificar que el mensaje contiene informacion util
        mensaje = mock_warning.call_args[0][0]
        assert "99.0.0" in mensaje

    def test_ruta_archivo_es_correcta(self, tmp_path):
        """La ruta al archivo .odev.yaml se almacena correctamente."""
        (tmp_path / ".odev.yaml").write_text("project:\n  name: test\n")

        pc = ProjectConfig(tmp_path)

        assert pc.ruta_archivo == tmp_path / ".odev.yaml"


class TestMezclarProfundo:
    """Grupo de tests para la funcion auxiliar _mezclar_profundo()."""

    def test_mezcla_dicts_anidados(self):
        """Mezcla correctamente diccionarios anidados."""
        base = {"a": {"x": 1, "y": 2}, "b": 3}
        actualizacion = {"a": {"y": 99, "z": 100}}

        resultado = _mezclar_profundo(base, actualizacion)

        assert resultado == {"a": {"x": 1, "y": 99, "z": 100}, "b": 3}

    def test_actualizacion_tiene_prioridad(self):
        """Los valores de actualizacion sobreescriben los de base."""
        base = {"clave": "original"}
        actualizacion = {"clave": "nuevo"}

        resultado = _mezclar_profundo(base, actualizacion)

        assert resultado["clave"] == "nuevo"

    def test_no_modifica_diccionario_original(self):
        """No modifica los diccionarios de entrada."""
        base = {"a": {"x": 1}}
        actualizacion = {"a": {"y": 2}}

        _mezclar_profundo(base, actualizacion)

        assert base == {"a": {"x": 1}}
