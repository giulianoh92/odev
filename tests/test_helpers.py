"""Tests unitarios para helpers compartidos de comandos odev.

Cubre:
  - parsear_modulos_csv (REQ-1 — escenarios 1-A a 1-G)
  - listar_modulos_disponibles (REQ-8)
  - validar_modulos (REQ-2 — escenarios 2-A a 2-E)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer


# ---------------------------------------------------------------------------
# parsear_modulos_csv — REQ-1
# ---------------------------------------------------------------------------


class TestParsearModulosCsv:
    """REQ-1: parsing y normalizacion de CSV de modulos."""

    def test_1a_modulo_unico(self) -> None:
        """1-A: token unico retorna lista de un elemento (backward compat)."""
        from odev.commands._helpers import parsear_modulos_csv

        resultado = parsear_modulos_csv("mod1")
        assert resultado == ["mod1"]

    def test_1b_csv_con_espacios(self) -> None:
        """1-B: CSV con espacios alrededor devuelve lista sin espacios."""
        from odev.commands._helpers import parsear_modulos_csv

        resultado = parsear_modulos_csv("mod1, mod2 , mod3")
        assert resultado == ["mod1", "mod2", "mod3"]

    def test_1c_deduplicacion(self) -> None:
        """1-C: duplicados eliminados silenciosamente, preservando orden."""
        from odev.commands._helpers import parsear_modulos_csv

        resultado = parsear_modulos_csv("mod1,mod2,mod1")
        assert resultado == ["mod1", "mod2"]

    def test_1d_trailing_comma(self) -> None:
        """1-D: coma final produce parte vacia que se descarta."""
        from odev.commands._helpers import parsear_modulos_csv

        resultado = parsear_modulos_csv("mod1,")
        assert resultado == ["mod1"]

    def test_1e_solo_comas_es_error(self, capsys) -> None:
        """1-E: solo comas → Exit(2) y mensaje 'Lista de modulos vacia'."""
        from odev.commands._helpers import parsear_modulos_csv

        with pytest.raises((SystemExit, typer.Exit)) as exc_info:
            parsear_modulos_csv(",,,,")

        exc = exc_info.value
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 2
        captured = capsys.readouterr()
        assert "Lista de modulos vacia" in captured.err

    def test_1f_all_solo_es_aceptado(self) -> None:
        """1-F: 'all' como token unico retorna ['all'] sin error."""
        from odev.commands._helpers import parsear_modulos_csv

        resultado = parsear_modulos_csv("all")
        assert resultado == ["all"]

    def test_1f_all_con_espacios_es_aceptado(self) -> None:
        """1-F (variante): ' all ' (con espacios) retorna ['all']."""
        from odev.commands._helpers import parsear_modulos_csv

        resultado = parsear_modulos_csv(" all ")
        assert resultado == ["all"]

    def test_1g_all_mezclado_es_error(self, capsys) -> None:
        """1-G: 'mod1,all' → Exit(2) y mensaje sobre 'all' mezclado."""
        from odev.commands._helpers import parsear_modulos_csv

        with pytest.raises((SystemExit, typer.Exit)) as exc_info:
            parsear_modulos_csv("mod1,all")

        exc = exc_info.value
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 2
        captured = capsys.readouterr()
        assert "'all'" in captured.err or "all" in captured.err.lower()

    def test_1g_all_primero_mezclado_es_error(self, capsys) -> None:
        """1-G (variante): 'all,mod1' también es error."""
        from odev.commands._helpers import parsear_modulos_csv

        with pytest.raises((SystemExit, typer.Exit)) as exc_info:
            parsear_modulos_csv("all,mod1")

        exc = exc_info.value
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 2

    def test_csv_tres_modulos(self) -> None:
        """Triangulacion: CSV con 3 modulos sin espacios."""
        from odev.commands._helpers import parsear_modulos_csv

        resultado = parsear_modulos_csv("a,b,c")
        assert resultado == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# listar_modulos_disponibles — REQ-8
# ---------------------------------------------------------------------------


class TestListarModulosDisponibles:
    """REQ-8: listar_modulos_disponibles retorna set de nombres de modulos."""

    def test_layout_desconocido_retorna_set_vacio(self, tmp_path: Path) -> None:
        """Layout con modulos_encontrados==0 → set vacio (fallback)."""
        from odev.core.detect import RepoLayout, TipoRepo
        from odev.commands._helpers import listar_modulos_disponibles

        fake_layout = RepoLayout(
            tipo=TipoRepo.DESCONOCIDO,
            rutas_addons=[],
            modulos_encontrados=0,
        )
        ctx = MagicMock()
        ctx.directorio_config = tmp_path

        with patch("odev.commands._helpers.detectar_layout", return_value=fake_layout):
            resultado = listar_modulos_disponibles(ctx)

        assert resultado == set()

    def test_layout_con_modulos_retorna_nombres(self, tmp_path: Path) -> None:
        """Layout normal → set con nombres de modulos detectados."""
        from odev.core.detect import RepoLayout, TipoRepo
        from odev.commands._helpers import listar_modulos_disponibles

        addon_dir = tmp_path / "addons"
        addon_dir.mkdir()
        for nombre in ["mod_a", "mod_b", "mod_c"]:
            (addon_dir / nombre).mkdir()
            (addon_dir / nombre / "__manifest__.py").touch()

        fake_layout = RepoLayout(
            tipo=TipoRepo.MULTI_ADDON,
            rutas_addons=[addon_dir],
            modulos_encontrados=3,
        )
        ctx = MagicMock()
        ctx.directorio_config = tmp_path

        with patch("odev.commands._helpers.detectar_layout", return_value=fake_layout):
            resultado = listar_modulos_disponibles(ctx)

        assert resultado == {"mod_a", "mod_b", "mod_c"}

    def test_directorio_sin_manifest_ignorado(self, tmp_path: Path) -> None:
        """Directorios sin __manifest__.py no se incluyen en el set."""
        from odev.core.detect import RepoLayout, TipoRepo
        from odev.commands._helpers import listar_modulos_disponibles

        addon_dir = tmp_path / "addons"
        addon_dir.mkdir()
        (addon_dir / "modulo_real").mkdir()
        (addon_dir / "modulo_real" / "__manifest__.py").touch()
        (addon_dir / "carpeta_sin_manifest").mkdir()

        fake_layout = RepoLayout(
            tipo=TipoRepo.MULTI_ADDON,
            rutas_addons=[addon_dir],
            modulos_encontrados=1,
        )
        ctx = MagicMock()
        ctx.directorio_config = tmp_path

        with patch("odev.commands._helpers.detectar_layout", return_value=fake_layout):
            resultado = listar_modulos_disponibles(ctx)

        assert "modulo_real" in resultado
        assert "carpeta_sin_manifest" not in resultado


# ---------------------------------------------------------------------------
# validar_modulos — REQ-2
# ---------------------------------------------------------------------------


class TestValidarModulos:
    """REQ-2: validacion por lotes de modulos contra addons-path."""

    def _make_ctx(self, tmp_path: Path) -> MagicMock:
        ctx = MagicMock()
        ctx.directorio_config = tmp_path
        ctx.config = MagicMock()
        ctx.config.rutas_addons = None
        return ctx

    def test_2a_all_bypass(self, tmp_path: Path) -> None:
        """2-A: ['all'] → retorna None sin validar (bypass total)."""
        from odev.commands._helpers import validar_modulos

        ctx = self._make_ctx(tmp_path)
        # no_validate=False pero 'all' debe hacer bypass
        with patch("odev.commands._helpers.detectar_layout") as mock_detect:
            validar_modulos(["all"], ctx, no_validate=False)
            mock_detect.assert_not_called()

    def test_2a_no_validate_bypass(self, tmp_path: Path) -> None:
        """2-D: no_validate=True → retorna sin tocar disco."""
        from odev.commands._helpers import validar_modulos

        ctx = self._make_ctx(tmp_path)
        with patch("odev.commands._helpers.detectar_layout") as mock_detect:
            validar_modulos(["ghost_mod"], ctx, no_validate=True)
            mock_detect.assert_not_called()

    def test_disponibles_vacios_bypass(self, tmp_path: Path) -> None:
        """Layout desconocido (disponibles==set()) → no lanza error."""
        from odev.core.detect import RepoLayout, TipoRepo
        from odev.commands._helpers import validar_modulos

        ctx = self._make_ctx(tmp_path)
        fake_layout = RepoLayout(
            tipo=TipoRepo.DESCONOCIDO,
            rutas_addons=[],
            modulos_encontrados=0,
        )
        with patch("odev.commands._helpers.detectar_layout", return_value=fake_layout):
            validar_modulos(["ghost_mod"], ctx, no_validate=False)
        # No debe haber raise

    def test_2e_builtin_bypass(self, tmp_path: Path) -> None:
        """2-E: modulo builtin ('base') → no llama detectar_layout."""
        from odev.commands._helpers import validar_modulos

        ctx = self._make_ctx(tmp_path)
        with patch("odev.commands._helpers.detectar_layout") as mock_detect:
            validar_modulos(["base"], ctx, no_validate=False)
            mock_detect.assert_not_called()

    def test_2b_un_modulo_faltante_exit_2(self, tmp_path: Path, capsys) -> None:
        """2-B: un modulo inexistente → Exit(2) y stderr menciona el nombre."""
        from odev.core.detect import RepoLayout, TipoRepo
        from odev.commands._helpers import validar_modulos

        ctx = self._make_ctx(tmp_path)
        addon_dir = tmp_path / "addons"
        addon_dir.mkdir()
        (addon_dir / "sale").mkdir()
        (addon_dir / "sale" / "__manifest__.py").touch()

        fake_layout = RepoLayout(
            tipo=TipoRepo.MULTI_ADDON,
            rutas_addons=[addon_dir],
            modulos_encontrados=1,
        )

        with patch("odev.commands._helpers.detectar_layout", return_value=fake_layout):
            with pytest.raises((SystemExit, typer.Exit)) as exc_info:
                validar_modulos(["sale", "ghost_mod"], ctx, no_validate=False)

        exc = exc_info.value
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 2
        captured = capsys.readouterr()
        assert "ghost_mod" in captured.err

    def test_2c_multiples_faltantes_en_un_mensaje(self, tmp_path: Path, capsys) -> None:
        """2-C: varios faltantes → todos listados en un solo mensaje de error."""
        from odev.core.detect import RepoLayout, TipoRepo
        from odev.commands._helpers import validar_modulos

        ctx = self._make_ctx(tmp_path)
        addon_dir = tmp_path / "addons"
        addon_dir.mkdir()
        (addon_dir / "sale").mkdir()
        (addon_dir / "sale" / "__manifest__.py").touch()

        fake_layout = RepoLayout(
            tipo=TipoRepo.MULTI_ADDON,
            rutas_addons=[addon_dir],
            modulos_encontrados=1,
        )

        with patch("odev.commands._helpers.detectar_layout", return_value=fake_layout):
            with pytest.raises((SystemExit, typer.Exit)) as exc_info:
                validar_modulos(["ghost1", "sale", "ghost2"], ctx, no_validate=False)

        exc = exc_info.value
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 2
        captured = capsys.readouterr()
        # Ambos nombres deben aparecer en el stderr
        assert "ghost1" in captured.err
        assert "ghost2" in captured.err

    def test_2a_todos_validos_no_error(self, tmp_path: Path) -> None:
        """2-A: todos los modulos existen → retorna None sin error."""
        from odev.core.detect import RepoLayout, TipoRepo
        from odev.commands._helpers import validar_modulos

        ctx = self._make_ctx(tmp_path)
        addon_dir = tmp_path / "addons"
        addon_dir.mkdir()
        for nombre in ["sale", "crm"]:
            (addon_dir / nombre).mkdir()
            (addon_dir / nombre / "__manifest__.py").touch()

        fake_layout = RepoLayout(
            tipo=TipoRepo.MULTI_ADDON,
            rutas_addons=[addon_dir],
            modulos_encontrados=2,
        )

        with patch("odev.commands._helpers.detectar_layout", return_value=fake_layout):
            validar_modulos(["sale", "crm"], ctx, no_validate=False)
        # No debe haber raise

    def test_mixto_builtin_presente_faltante(self, tmp_path: Path, capsys) -> None:
        """Mezcla builtin + presente + faltante → solo el faltante en error."""
        from odev.core.detect import RepoLayout, TipoRepo
        from odev.commands._helpers import validar_modulos

        ctx = self._make_ctx(tmp_path)
        addon_dir = tmp_path / "addons"
        addon_dir.mkdir()
        (addon_dir / "my_module").mkdir()
        (addon_dir / "my_module" / "__manifest__.py").touch()

        fake_layout = RepoLayout(
            tipo=TipoRepo.MULTI_ADDON,
            rutas_addons=[addon_dir],
            modulos_encontrados=1,
        )

        with patch("odev.commands._helpers.detectar_layout", return_value=fake_layout):
            with pytest.raises((SystemExit, typer.Exit)) as exc_info:
                validar_modulos(
                    ["base", "my_module", "ghost_mod"],
                    ctx,
                    no_validate=False,
                )

        exc = exc_info.value
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 2
        captured = capsys.readouterr()
        assert "ghost_mod" in captured.err
        assert "base" not in captured.err
        assert "my_module" not in captured.err
