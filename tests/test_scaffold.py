"""Tests para odev.commands.scaffold — creacion de modulos Odoo.

Verifica que scaffold cree la estructura de modulo correctamente,
reemplace placeholders, rechace nombres invalidos y directorios
existentes.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
import typer

from odev.commands.scaffold import _reemplazar_en_arbol, scaffold


class TestReemplazarEnArbol:
    """Grupo de tests para la funcion _reemplazar_en_arbol()."""

    def test_reemplaza_contenido_en_archivos(self, tmp_path):
        """Reemplaza el placeholder en el contenido de los archivos."""
        archivo = tmp_path / "test.py"
        archivo.write_text("from __module_name__ import models\n")

        _reemplazar_en_arbol(tmp_path, "__module_name__", "mi_modulo")

        assert archivo.read_text() == "from mi_modulo import models\n"

    def test_renombra_archivos_con_placeholder(self, tmp_path):
        """Renombra archivos que contienen el placeholder en su nombre."""
        archivo = tmp_path / "__module_name__.py"
        archivo.write_text("# contenido\n")

        _reemplazar_en_arbol(tmp_path, "__module_name__", "ventas")

        assert not (tmp_path / "__module_name__.py").exists()
        assert (tmp_path / "ventas.py").exists()
        assert (tmp_path / "ventas.py").read_text() == "# contenido\n"

    def test_renombra_directorios_con_placeholder(self, tmp_path):
        """Renombra directorios que contienen el placeholder."""
        directorio = tmp_path / "__module_name__"
        directorio.mkdir()
        (directorio / "archivo.py").write_text("# dentro\n")

        _reemplazar_en_arbol(tmp_path, "__module_name__", "inventario")

        assert not (tmp_path / "__module_name__").exists()
        assert (tmp_path / "inventario").is_dir()
        assert (tmp_path / "inventario" / "archivo.py").exists()

    def test_estructura_completa_con_subdirectorios(self, tmp_path):
        """Reemplaza en toda la estructura de subdirectorios."""
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "__module_name__.py").write_text("class __module_name__(Model):\n    pass\n")
        (tmp_path / "__init__.py").write_text("from . import __module_name__\n")

        _reemplazar_en_arbol(tmp_path, "__module_name__", "facturacion")

        assert (models_dir / "facturacion.py").exists()
        contenido = (models_dir / "facturacion.py").read_text()
        assert "class facturacion(Model):" in contenido
        assert "__init__.py" in [f.name for f in tmp_path.iterdir()]
        init_contenido = (tmp_path / "__init__.py").read_text()
        assert "from . import facturacion" in init_contenido

    def test_ignora_archivos_binarios(self, tmp_path):
        """Ignora archivos binarios que causan UnicodeDecodeError."""
        archivo_binario = tmp_path / "imagen.png"
        archivo_binario.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        # No debe lanzar excepcion
        _reemplazar_en_arbol(tmp_path, "__module_name__", "modulo")


class TestScaffoldValidacion:
    """Grupo de tests para la validacion de nombres de modulos."""

    @pytest.mark.parametrize(
        "nombre_invalido",
        [
            "Mi-Modulo",
            "MODULO",
            "123modulo",
            "modulo con espacios",
            "modulo-con-guiones",
            "Modulo",
            "_privado",
        ],
        ids=[
            "con-guiones-y-mayusculas",
            "todo-mayusculas",
            "empieza-con-numero",
            "con-espacios",
            "con-guiones-medios",
            "empieza-mayuscula",
            "empieza-guion-bajo",
        ],
    )
    def test_rechaza_nombres_no_snake_case(self, nombre_invalido):
        """Rechaza nombres de modulo que no son snake_case."""
        with pytest.raises(typer.Exit):
            scaffold(name=nombre_invalido)

    @pytest.mark.parametrize(
        "nombre_valido",
        [
            "mi_modulo",
            "ventas",
            "contabilidad_ar",
            "a",
            "modulo123",
            "m1_m2",
        ],
        ids=[
            "snake-case-normal",
            "una-palabra",
            "con-guion-bajo",
            "letra-sola",
            "con-numeros",
            "corto-con-numeros",
        ],
    )
    def test_acepta_nombres_snake_case_validos(self, nombre_valido, tmp_path, monkeypatch):
        """Acepta nombres validos en snake_case (verificando solo la validacion)."""
        # Mockear ProjectPaths para que falle despues de la validacion
        # Esto verifica que la validacion del nombre paso exitosamente
        (tmp_path / ".odev.yaml").write_text("odev_min_version: 0.1.0\n")
        monkeypatch.chdir(tmp_path)

        # El modulo template puede no existir; lo que nos interesa es que
        # la validacion del nombre NO lance error
        with patch("odev.commands.scaffold.get_module_template_dir") as mock_template:
            mock_template.return_value = tmp_path / "templates" / "module"
            (mock_template.return_value).mkdir(parents=True)
            # El directorio destino tampoco debe existir
            # Crear el directorio addons para que shutil.copytree funcione
            (tmp_path / "addons").mkdir(exist_ok=True)
            try:
                scaffold(name=nombre_valido)
            except typer.Exit as e:
                # Exit con code 1 es error de validacion; code 0 o None es ok
                if e.exit_code == 1:
                    pytest.fail(f"Nombre '{nombre_valido}' fue rechazado incorrectamente")

    def test_rechaza_directorio_existente(self, tmp_path, monkeypatch):
        """Rechaza crear un modulo si el directorio ya existe."""
        (tmp_path / ".odev.yaml").write_text("odev_min_version: 0.1.0\n")
        monkeypatch.chdir(tmp_path)

        # Crear el directorio del modulo
        addons_dir = tmp_path / "addons"
        addons_dir.mkdir()
        (addons_dir / "mi_modulo").mkdir()

        with patch("odev.commands.scaffold.get_module_template_dir") as mock_template:
            mock_template.return_value = tmp_path / "templates" / "module"
            (mock_template.return_value).mkdir(parents=True)

            with pytest.raises(typer.Exit) as exc_info:
                scaffold(name="mi_modulo")

            assert exc_info.value.exit_code == 1
