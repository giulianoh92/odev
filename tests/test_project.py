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

    def test_ruta_enterprise_from_config(self, tmp_path):
        """ruta_enterprise returns the value from enterprise.path in odev.yaml."""
        config = {
            "enterprise": {"enabled": True, "path": "/shared/enterprise"},
        }
        (tmp_path / ".odev.yaml").write_text(
            yaml.dump(config, default_flow_style=False),
            encoding="utf-8",
        )

        pc = ProjectConfig(tmp_path)

        assert pc.ruta_enterprise == "/shared/enterprise"

    def test_ruta_enterprise_default(self, tmp_path):
        """ruta_enterprise defaults to './enterprise' when not set."""
        config = {"project": {"name": "minimal"}}
        (tmp_path / ".odev.yaml").write_text(
            yaml.dump(config, default_flow_style=False),
            encoding="utf-8",
        )

        pc = ProjectConfig(tmp_path)

        assert pc.ruta_enterprise == "./enterprise"


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


class TestValidarEsquemaNested:
    """Tests para la validacion anidada de esquema en _validar_esquema."""

    def test_typo_in_nested_key_produces_warning(self, tmp_path):
        """Un typo en una clave anidada (ej. enterprise.enbled) produce warning."""
        config = {"enterprise": {"enbled": True}}
        (tmp_path / ".odev.yaml").write_text(yaml.dump(config))

        with patch("odev.core.project.warning") as mock_warning:
            pc = ProjectConfig(tmp_path)

        # Debe haber al menos un warning sobre la clave desconocida 'enbled'
        calls = [str(c) for c in mock_warning.call_args_list]
        assert any("enbled" in c and "enterprise" in c for c in calls)
        # El typo fue ignorado, el default se aplico
        assert pc.enterprise_habilitado is False

    def test_wrong_type_in_nested_value_produces_warning(self, tmp_path):
        """Un tipo incorrecto (ej. enterprise.enabled: 'yes') produce warning."""
        config = {"enterprise": {"enabled": "yes"}}
        (tmp_path / ".odev.yaml").write_text(yaml.dump(config))

        with patch("odev.core.project.warning") as mock_warning:
            ProjectConfig(tmp_path)

        # Al menos un warning mencionando 'bool'
        calls = [str(c) for c in mock_warning.call_args_list]
        assert any("bool" in c for c in calls)

    def test_valid_nested_config_no_warnings(self, tmp_path):
        """Una configuracion valida completa no produce warnings."""
        config = {
            "odoo": {"version": "19.0", "image": "odoo:19"},
            "enterprise": {"enabled": True, "path": "./enterprise"},
        }
        (tmp_path / ".odev.yaml").write_text(yaml.dump(config))

        with patch("odev.core.project.warning") as mock_warning:
            ProjectConfig(tmp_path)

        mock_warning.assert_not_called()

    def test_paths_addons_accepts_list_and_string(self, tmp_path):
        """No produce warning para paths.addons como lista ni como string."""
        # Caso 1: lista (tipo primario)
        config_list = {"paths": {"addons": ["./addons", "./extra"]}}
        (tmp_path / ".odev.yaml").write_text(yaml.dump(config_list))

        with patch("odev.core.project.warning") as mock_warning:
            ProjectConfig(tmp_path)

        mock_warning.assert_not_called()

        # Caso 2: string (tipo alternativo, coercionado despues)
        config_str = {"paths": {"addons": "./addons"}}
        (tmp_path / ".odev.yaml").write_text(yaml.dump(config_str))

        with patch("odev.core.project.warning") as mock_warning:
            ProjectConfig(tmp_path)

        mock_warning.assert_not_called()

    def test_none_value_produces_warning(self, tmp_path):
        """Un valor null (None) produce warning de tipo."""
        config = {"enterprise": {"path": None}}
        (tmp_path / ".odev.yaml").write_text(yaml.dump(config))

        with patch("odev.core.project.warning") as mock_warning:
            ProjectConfig(tmp_path)

        calls = [str(c) for c in mock_warning.call_args_list]
        assert any("NoneType" in c for c in calls)

    def test_paths_addons_int_produces_warning(self, tmp_path):
        """paths.addons: 42 (int) produce warning mencionando list o str."""
        config = {"paths": {"addons": 42}}
        (tmp_path / ".odev.yaml").write_text(yaml.dump(config))

        with patch("odev.core.project.warning") as mock_warning:
            ProjectConfig(tmp_path)

        calls = [str(c) for c in mock_warning.call_args_list]
        assert any("list" in c and "str" in c and "int" in c for c in calls)

    def test_unknown_toplevel_keys_still_produce_warnings(self, tmp_path):
        """Las claves desconocidas de primer nivel siguen produciendo warnings."""
        config = {"clave_inventada": "valor"}
        (tmp_path / ".odev.yaml").write_text(yaml.dump(config))

        with patch("odev.core.project.warning") as mock_warning:
            ProjectConfig(tmp_path)

        calls = [str(c) for c in mock_warning.call_args_list]
        assert any("clave_inventada" in c for c in calls)

    def test_project_loads_normally_with_warnings(self, tmp_path):
        """El proyecto se carga normalmente incluso con warnings."""
        config = {
            "enterprise": {"enbled": True, "enabled": "yes"},
            "odoo": {"version": "18.0", "vresion": "typo"},
        }
        (tmp_path / ".odev.yaml").write_text(yaml.dump(config))

        with patch("odev.core.project.warning"):
            pc = ProjectConfig(tmp_path)

        # El proyecto carga y opera normalmente a pesar de los warnings
        assert pc.version_odoo == "18.0"
        # "yes" se mantiene como valor (mezcla prioriza lo del usuario),
        # la validacion solo advierte, no corrige
        assert pc.enterprise_habilitado == "yes"
