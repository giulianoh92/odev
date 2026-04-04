"""Tests para el motor de deteccion de layout de repositorio Odoo.

Valida que ``detectar_layout`` clasifique correctamente distintas
estructuras de directorios: modulo unico, multi-addon, Odoo.sh con
submodulos, codigo fuente de Odoo y layouts desconocidos.
"""

import pytest
from pathlib import Path

from odev.core.detect import detectar_layout, TipoRepo


class TestDetectarLayout:
    """Tests para detectar_layout()."""

    def test_modulo_unico(self, tmp_path: Path) -> None:
        """Directorio con __manifest__.py en la raiz es MODULO_UNICO."""
        (tmp_path / "__manifest__.py").write_text("{'name': 'Test'}")
        (tmp_path / "models").mkdir()

        layout = detectar_layout(tmp_path)

        assert layout.tipo == TipoRepo.MODULO_UNICO
        assert layout.modulos_encontrados == 1
        assert not layout.tiene_enterprise
        assert not layout.tiene_submodulos

    def test_multi_addon(self, tmp_path: Path) -> None:
        """Multiples subdirectorios con __manifest__.py es MULTI_ADDON."""
        for name in ["mod_a", "mod_b", "mod_c"]:
            mod = tmp_path / name
            mod.mkdir()
            (mod / "__manifest__.py").write_text(f"{{'name': '{name}'}}")

        layout = detectar_layout(tmp_path)

        assert layout.tipo == TipoRepo.MULTI_ADDON
        assert layout.modulos_encontrados == 3
        assert len(layout.rutas_addons) == 1  # root is the addon dir

    def test_odoosh_con_submodulos(self, tmp_path: Path) -> None:
        """Repo con .gitmodules y submodulos que contienen addons es ODOOSH."""
        # Modulos propios en raiz
        mod = tmp_path / "mi_modulo"
        mod.mkdir()
        (mod / "__manifest__.py").write_text("{'name': 'mi_modulo'}")

        # Submodulo con modulos
        sub = tmp_path / "oca-web"
        sub.mkdir()
        sub_mod = sub / "web_responsive"
        sub_mod.mkdir()
        (sub_mod / "__manifest__.py").write_text("{'name': 'web_responsive'}")

        # .gitmodules (formato INI)
        (tmp_path / ".gitmodules").write_text(
            '[submodule "oca-web"]\n'
            "\tpath = oca-web\n"
            "\turl = https://github.com/OCA/web.git\n"
        )

        layout = detectar_layout(tmp_path)

        assert layout.tipo == TipoRepo.ODOOSH
        assert layout.tiene_submodulos
        assert layout.modulos_encontrados >= 2
        assert len(layout.rutas_addons) >= 2  # root + submodule

    def test_odoo_fuente(self, tmp_path: Path) -> None:
        """Directorio con odoo-bin es ODOO_FUENTE."""
        (tmp_path / "odoo-bin").write_text("#!/usr/bin/env python3")

        layout = detectar_layout(tmp_path)

        assert layout.tipo == TipoRepo.ODOO_FUENTE

    def test_desconocido(self, tmp_path: Path) -> None:
        """Directorio vacio es DESCONOCIDO."""
        layout = detectar_layout(tmp_path)

        assert layout.tipo == TipoRepo.DESCONOCIDO
        assert layout.modulos_encontrados == 0

    def test_ignora_directorios_ocultos(self, tmp_path: Path) -> None:
        """No escanea .git, __pycache__, node_modules."""
        for name in [".git", "__pycache__", "node_modules"]:
            d = tmp_path / name
            d.mkdir()
            (d / "__manifest__.py").write_text("{'name': 'hidden'}")

        layout = detectar_layout(tmp_path)

        assert layout.tipo == TipoRepo.DESCONOCIDO
        assert layout.modulos_encontrados == 0

    def test_enterprise_detection(self, tmp_path: Path) -> None:
        """Detecta directorio enterprise/ con modulos."""
        ent = tmp_path / "enterprise"
        ent.mkdir()
        (ent / "account_accountant").mkdir()
        (ent / "account_accountant" / "__manifest__.py").write_text(
            "{'name': 'accountant'}"
        )

        # Modulo propio para que no sea DESCONOCIDO
        mod = tmp_path / "mi_mod"
        mod.mkdir()
        (mod / "__manifest__.py").write_text("{'name': 'mi_mod'}")

        layout = detectar_layout(tmp_path)

        assert layout.tiene_enterprise

    def test_enterprise_por_nombre_conocido(self, tmp_path: Path) -> None:
        """Detecta enterprise por nombre de modulo conocido."""
        mod = tmp_path / "helpdesk"
        mod.mkdir()
        (mod / "__manifest__.py").write_text("{'name': 'helpdesk'}")

        layout = detectar_layout(tmp_path)

        assert layout.tiene_enterprise
        assert layout.modulos_encontrados == 1

    def test_modulo_unico_con_openerp(self, tmp_path: Path) -> None:
        """Directorio con __openerp__.py tambien es MODULO_UNICO."""
        (tmp_path / "__openerp__.py").write_text("{'name': 'Old Module'}")

        layout = detectar_layout(tmp_path)

        assert layout.tipo == TipoRepo.MODULO_UNICO
        assert layout.modulos_encontrados == 1

    def test_submodulo_sin_addons_no_es_odoosh(self, tmp_path: Path) -> None:
        """Repo con .gitmodules pero submodulos sin addons es MULTI_ADDON (no ODOOSH)."""
        # Modulo en raiz
        mod = tmp_path / "mi_modulo"
        mod.mkdir()
        (mod / "__manifest__.py").write_text("{'name': 'mi_modulo'}")

        # Submodulo vacio (sin modulos)
        sub = tmp_path / "lib-utils"
        sub.mkdir()
        (sub / "README.md").write_text("# Utils")

        (tmp_path / ".gitmodules").write_text(
            '[submodule "lib-utils"]\n'
            "\tpath = lib-utils\n"
            "\turl = https://github.com/example/utils.git\n"
        )

        layout = detectar_layout(tmp_path)

        assert layout.tipo == TipoRepo.MULTI_ADDON
        assert layout.tiene_submodulos

    def test_addons_subdirectorio_convencional(self, tmp_path: Path) -> None:
        """Modulos dentro de addons/ se detectan como MULTI_ADDON."""
        addons = tmp_path / "addons"
        addons.mkdir()
        for name in ["mod_a", "mod_b"]:
            mod = addons / name
            mod.mkdir()
            (mod / "__manifest__.py").write_text(f"{{'name': '{name}'}}")

        # Archivos extra en raiz (sin __manifest__.py)
        (tmp_path / "README.md").write_text("# Project")

        layout = detectar_layout(tmp_path)

        assert layout.tipo == TipoRepo.MULTI_ADDON
        assert layout.modulos_encontrados == 2
        assert len(layout.rutas_addons) == 1
        assert layout.rutas_addons[0].name == "addons"

    def test_custom_addons_subdirectorio(self, tmp_path: Path) -> None:
        """Modulos dentro de custom_addons/ se detectan correctamente."""
        custom = tmp_path / "custom_addons"
        custom.mkdir()
        mod = custom / "mi_modulo"
        mod.mkdir()
        (mod / "__manifest__.py").write_text("{'name': 'mi_modulo'}")

        layout = detectar_layout(tmp_path)

        assert layout.tipo == TipoRepo.MULTI_ADDON
        assert layout.modulos_encontrados == 1
        assert layout.rutas_addons[0].name == "custom_addons"

    def test_multiples_dirs_convencionales(self, tmp_path: Path) -> None:
        """Modulos en addons/ y custom/ se detectan ambos."""
        for dir_name in ["addons", "custom"]:
            d = tmp_path / dir_name
            d.mkdir()
            mod = d / f"mod_{dir_name}"
            mod.mkdir()
            (mod / "__manifest__.py").write_text(f"{{'name': 'mod_{dir_name}'}}")

        layout = detectar_layout(tmp_path)

        assert layout.tipo == TipoRepo.MULTI_ADDON
        assert layout.modulos_encontrados == 2
        assert len(layout.rutas_addons) == 2

    def test_modulos_raiz_priorizan_sobre_convencionales(self, tmp_path: Path) -> None:
        """Si hay modulos en raiz, no busca en subdirectorios convencionales."""
        # Modulo en raiz
        mod_raiz = tmp_path / "mod_raiz"
        mod_raiz.mkdir()
        (mod_raiz / "__manifest__.py").write_text("{'name': 'mod_raiz'}")

        # Modulo en addons/ (no deberia buscarse)
        addons = tmp_path / "addons"
        addons.mkdir()
        mod_addons = addons / "mod_addons"
        mod_addons.mkdir()
        (mod_addons / "__manifest__.py").write_text("{'name': 'mod_addons'}")

        layout = detectar_layout(tmp_path)

        assert layout.tipo == TipoRepo.MULTI_ADDON
        # Solo cuenta modulos de raiz (addons/ no se escanea si hay modulos en raiz)
        assert layout.modulos_encontrados == 1
        assert len(layout.rutas_addons) == 1
        assert layout.rutas_addons[0] == tmp_path

    def test_ruta_raiz_se_resuelve(self, tmp_path: Path) -> None:
        """La ruta_raiz del resultado esta resuelta (sin symlinks)."""
        (tmp_path / "__manifest__.py").write_text("{'name': 'Test'}")

        layout = detectar_layout(tmp_path)

        assert layout.ruta_raiz == tmp_path.resolve()
