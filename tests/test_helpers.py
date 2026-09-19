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

    def test_1e_solo_comas_es_error(self) -> None:
        """1-E: solo comas → ValueError con mensaje 'Lista de modulos vacia'.

        A2/U1: las funciones compartidas lanzan ValueError, no typer.Exit;
        es la capa CLI la que decide convertir eso a stderr + exit 2.
        """
        from odev.commands._helpers import parsear_modulos_csv

        with pytest.raises(ValueError) as exc_info:
            parsear_modulos_csv(",,,,")

        assert str(exc_info.value) == "Lista de modulos vacia"

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

    def test_1g_all_mezclado_es_error(self) -> None:
        """1-G: 'mod1,all' → ValueError con mensaje sobre 'all' mezclado."""
        from odev.commands._helpers import parsear_modulos_csv

        with pytest.raises(ValueError) as exc_info:
            parsear_modulos_csv("mod1,all")

        assert "'all'" in str(exc_info.value) or "all" in str(exc_info.value).lower()

    def test_1g_all_primero_mezclado_es_error(self) -> None:
        """1-G (variante): 'all,mod1' tambien es error."""
        from odev.commands._helpers import parsear_modulos_csv

        with pytest.raises(ValueError) as exc_info:
            parsear_modulos_csv("all,mod1")

        assert "all" in str(exc_info.value).lower()

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
        from odev.commands._helpers import listar_modulos_disponibles
        from odev.core.detect import RepoLayout, TipoRepo

        fake_layout = RepoLayout(
            tipo=TipoRepo.DESCONOCIDO,
            rutas_addons=[],
            modulos_encontrados=0,
        )
        ctx = MagicMock()
        ctx.directorio_config = tmp_path
        ctx.config = None

        with patch("odev.commands._helpers.detectar_layout", return_value=fake_layout):
            resultado = listar_modulos_disponibles(ctx)

        assert resultado == set()

    def test_layout_con_modulos_retorna_nombres(self, tmp_path: Path) -> None:
        """Layout normal → set con nombres de modulos detectados."""
        from odev.commands._helpers import listar_modulos_disponibles
        from odev.core.detect import RepoLayout, TipoRepo

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
        ctx.config = None

        with patch("odev.commands._helpers.detectar_layout", return_value=fake_layout):
            resultado = listar_modulos_disponibles(ctx)

        assert resultado == {"mod_a", "mod_b", "mod_c"}

    def test_directorio_sin_manifest_ignorado(self, tmp_path: Path) -> None:
        """Directorios sin __manifest__.py no se incluyen en el set."""
        from odev.commands._helpers import listar_modulos_disponibles
        from odev.core.detect import RepoLayout, TipoRepo

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
        ctx.config = None

        with patch("odev.commands._helpers.detectar_layout", return_value=fake_layout):
            resultado = listar_modulos_disponibles(ctx)

        assert "modulo_real" in resultado
        assert "carpeta_sin_manifest" not in resultado


# ---------------------------------------------------------------------------
# resolver_addon_dir — U2 (A1-b): lint de descubrimiento de tests necesita
# el Path de un modulo puntual, no solo saber si el nombre existe.
# ---------------------------------------------------------------------------


class TestResolverAddonDir:
    """resolver_addon_dir reusa las mismas fuentes que listar_modulos_disponibles."""

    def test_encuentra_via_config(self, tmp_path: Path) -> None:
        """paths.addons de la config → devuelve el Path del modulo."""
        from odev.commands._helpers import resolver_addon_dir

        addon_dir = tmp_path / "addons"
        addon_dir.mkdir()
        (addon_dir / "mymod").mkdir()
        (addon_dir / "mymod" / "__manifest__.py").touch()

        ctx = MagicMock()
        ctx.directorio_config = tmp_path
        ctx.config.rutas_addons = ["./addons"]

        resultado = resolver_addon_dir("mymod", ctx)

        assert resultado == addon_dir / "mymod"

    def test_encuentra_via_heuristica_sin_config(self, tmp_path: Path) -> None:
        """Sin config, cae a detectar_layout — mismo fallback que listar_modulos_disponibles."""
        from odev.commands._helpers import resolver_addon_dir
        from odev.core.detect import RepoLayout, TipoRepo

        addon_dir = tmp_path / "addons"
        addon_dir.mkdir()
        (addon_dir / "mymod").mkdir()
        (addon_dir / "mymod" / "__manifest__.py").touch()

        ctx = MagicMock()
        ctx.directorio_config = tmp_path
        ctx.config = None

        fake_layout = RepoLayout(
            tipo=TipoRepo.MULTI_ADDON,
            rutas_addons=[addon_dir],
            modulos_encontrados=1,
        )
        with patch("odev.commands._helpers.detectar_layout", return_value=fake_layout):
            resultado = resolver_addon_dir("mymod", ctx)

        assert resultado == addon_dir / "mymod"

    def test_modulo_inexistente_retorna_none(self, tmp_path: Path) -> None:
        """Modulo que no existe en ninguna fuente → None, no una excepcion."""
        from odev.commands._helpers import resolver_addon_dir
        from odev.core.detect import RepoLayout, TipoRepo

        ctx = MagicMock()
        ctx.directorio_config = tmp_path
        ctx.config = None

        fake_layout = RepoLayout(
            tipo=TipoRepo.DESCONOCIDO,
            rutas_addons=[],
            modulos_encontrados=0,
        )
        with patch("odev.commands._helpers.detectar_layout", return_value=fake_layout):
            resultado = resolver_addon_dir("ghost_mod", ctx)

        assert resultado is None


# ---------------------------------------------------------------------------
# validar_modulos — REQ-2
# ---------------------------------------------------------------------------


class TestValidarModulos:
    """REQ-2: validacion por lotes de modulos contra addons-path."""

    def _make_ctx(self, tmp_path: Path) -> MagicMock:
        ctx = MagicMock()
        ctx.directorio_config = tmp_path
        ctx.config = None
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
        from odev.commands._helpers import validar_modulos
        from odev.core.detect import RepoLayout, TipoRepo

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

    def test_2b_un_modulo_faltante_exit_2(self, tmp_path: Path) -> None:
        """2-B: un modulo inexistente → ValueError y el mensaje nombra el modulo."""
        from odev.commands._helpers import validar_modulos
        from odev.core.detect import RepoLayout, TipoRepo

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
            with pytest.raises(ValueError) as exc_info:
                validar_modulos(["sale", "ghost_mod"], ctx, no_validate=False)

        assert "ghost_mod" in str(exc_info.value)

    def test_2c_multiples_faltantes_en_un_mensaje(self, tmp_path: Path) -> None:
        """2-C: varios faltantes → todos listados en un solo mensaje de error."""
        from odev.commands._helpers import validar_modulos
        from odev.core.detect import RepoLayout, TipoRepo

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
            with pytest.raises(ValueError) as exc_info:
                validar_modulos(["ghost1", "sale", "ghost2"], ctx, no_validate=False)

        # Ambos nombres deben aparecer en el mensaje
        mensaje = str(exc_info.value)
        assert "ghost1" in mensaje
        assert "ghost2" in mensaje

    def test_2a_todos_validos_no_error(self, tmp_path: Path) -> None:
        """2-A: todos los modulos existen → retorna None sin error."""
        from odev.commands._helpers import validar_modulos
        from odev.core.detect import RepoLayout, TipoRepo

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

    def test_mixto_builtin_presente_faltante(self, tmp_path: Path) -> None:
        """Mezcla builtin + presente + faltante → solo el faltante en error."""
        from odev.commands._helpers import validar_modulos
        from odev.core.detect import RepoLayout, TipoRepo

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
            with pytest.raises(ValueError) as exc_info:
                validar_modulos(
                    ["base", "my_module", "ghost_mod"],
                    ctx,
                    no_validate=False,
                )

        mensaje = str(exc_info.value)
        assert "ghost_mod" in mensaje
        assert "base" not in mensaje
        assert "my_module" not in mensaje


# ---------------------------------------------------------------------------
# A2/U1 — update y addon-install convierten el ValueError de las funciones
# compartidas en stderr + exit 2, sin cambiar el contrato observable.
# (La cobertura equivalente para 'test' vive en test_test_cmd.py.)
# ---------------------------------------------------------------------------


class TestValidatorsCliContractUpdateInstall:
    """A2: parsear_modulos_csv/validar_modulos lanzan ValueError; update y
    addon-install lo atrapan y lo presentan exactamente como antes.
    """

    def _make_ctx(self, tmp_path: Path) -> MagicMock:
        ctx = MagicMock()
        ctx.directorio_config = tmp_path
        ctx.nombre = "test-project"
        ctx.config = MagicMock()
        ctx.config.rutas_addons = None
        return ctx

    def _run_comando(
        self,
        comando,
        tmp_path: Path,
        module: str,
        modulos_disponibles: set[str],
    ):
        """Invoca `update` o `install` con requerir_proyecto/docker mockeados."""
        import typer

        modname = comando.__module__
        ctx = self._make_ctx(tmp_path)
        mock_dc = MagicMock()

        exc = None
        with (
            patch(f"{modname}.requerir_proyecto", return_value=ctx),
            patch(f"{modname}.obtener_docker", return_value=mock_dc),
            patch(f"{modname}.obtener_rutas") as mock_rutas,
            patch(f"{modname}.load_env", return_value={"DB_NAME": "test_db"}),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch(
                "odev.commands._helpers.listar_modulos_disponibles",
                return_value=modulos_disponibles,
            ),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            try:
                comando(module=module, no_validate=False, verbose=False)
            except (SystemExit, typer.Exit) as e:
                exc = e

        return exc, mock_dc

    @staticmethod
    def _exit_code(exc) -> int | None:
        if exc is None:
            return None
        return exc.code if isinstance(exc, SystemExit) else exc.exit_code

    def test_update_modulo_desconocido_stderr_y_exit_2(
        self, tmp_path: Path, capsys
    ) -> None:
        """update con modulo inexistente: mismo mensaje, mismo exit 2."""
        from odev.commands.update import update

        exc, mock_dc = self._run_comando(update, tmp_path, "ghost_mod", {"sale", "crm"})

        assert self._exit_code(exc) == 2
        captured = capsys.readouterr()
        assert "Modulos no encontrados: ghost_mod" in captured.err
        mock_dc.exec_capture.assert_not_called()

    def test_addon_install_modulo_desconocido_stderr_y_exit_2(
        self, tmp_path: Path, capsys
    ) -> None:
        """addon-install con modulo inexistente: mismo mensaje, mismo exit 2."""
        from odev.commands.install import install

        exc, mock_dc = self._run_comando(install, tmp_path, "ghost_mod", {"sale", "crm"})

        assert self._exit_code(exc) == 2
        captured = capsys.readouterr()
        assert "Modulos no encontrados: ghost_mod" in captured.err
        mock_dc.exec_capture.assert_not_called()

    def test_update_all_mezclado_stderr_y_exit_2(self, tmp_path: Path, capsys) -> None:
        """update 'sale,all': mismo mensaje sobre 'all', mismo exit 2."""
        from odev.commands.update import update

        exc, mock_dc = self._run_comando(update, tmp_path, "sale,all", set())

        assert self._exit_code(exc) == 2
        captured = capsys.readouterr()
        assert "'all' no puede combinarse con otros modulos" in captured.err
        mock_dc.exec_capture.assert_not_called()

    def test_addon_install_lista_vacia_stderr_y_exit_2(
        self, tmp_path: Path, capsys
    ) -> None:
        """addon-install con lista vacia: mismo mensaje, mismo exit 2."""
        from odev.commands.install import install

        exc, mock_dc = self._run_comando(install, tmp_path, ",,,,", set())

        assert self._exit_code(exc) == 2
        captured = capsys.readouterr()
        assert "Lista de modulos vacia" in captured.err
        mock_dc.exec_capture.assert_not_called()


# ---------------------------------------------------------------------------
# D11 — exit codes epilog smoke test (Spec C11-1 / C11-2)
# ---------------------------------------------------------------------------


class TestExitCodesEpilog:
    """D11: cada comando publico expone 'Codigos de salida' en su --help.

    Spec C11-1: help includes exit codes
    Spec C11-2: uniformity across all public commands
    Design D11: EPILOG_EXIT_CODES constant in _helpers.py
    """

    def test_epilog_exit_codes_constant_existe(self) -> None:
        """EPILOG_EXIT_CODES exportado desde _helpers.py."""
        from odev.commands._helpers import EPILOG_EXIT_CODES  # type: ignore[attr-defined]

        assert EPILOG_EXIT_CODES is not None
        assert "Codigos de salida" in EPILOG_EXIT_CODES
        assert "0" in EPILOG_EXIT_CODES
        assert "1" in EPILOG_EXIT_CODES
        assert "2" in EPILOG_EXIT_CODES
        assert "3" in EPILOG_EXIT_CODES

    def test_comandos_publicos_tienen_epilog(self) -> None:
        """Iterando el arbol Typer: cada comando registrado tiene 'Codigos de salida' en su help."""
        from typer.testing import CliRunner

        from odev.main import app

        runner = CliRunner()

        # Recopilar todos los comandos de primer nivel
        commands = [cmd.name for cmd in app.registered_commands if cmd.name is not None]
        # Tambien los subcomandos de db
        from odev.commands import db
        db_commands = [cmd.name for cmd in db.app.registered_commands if cmd.name is not None]

        missing_epilog = []

        for cmd_name in commands:
            result = runner.invoke(app, [cmd_name, "--help"])
            if "Codigos de salida" not in result.output:
                missing_epilog.append(f"odev {cmd_name}")

        for cmd_name in db_commands:
            result = runner.invoke(app, ["db", cmd_name, "--help"])
            if "Codigos de salida" not in result.output:
                missing_epilog.append(f"odev db {cmd_name}")

        assert missing_epilog == [], (
            f"Comandos sin 'Codigos de salida' en --help: {missing_epilog}"
        )


class TestNormalizarExitCodeOdoo:
    """T4 (pulido-final): 0 se mantiene, cualquier otro codigo de Odoo mapea a 1.

    'addon-install' y 'update' propagaban el codigo de proceso de Odoo tal
    cual (3, 137, lo que sea) en vez de respetar el contrato 0/1/2/3 que
    EPILOG_EXIT_CODES publica para el resto de los comandos.
    """

    def test_cero_se_mantiene(self) -> None:
        from odev.commands._helpers import normalizar_exit_code_odoo

        assert normalizar_exit_code_odoo(0) == 0

    @pytest.mark.parametrize("codigo", [1, 2, 3, 127, 137, 255])
    def test_no_cero_mapea_a_1(self, codigo: int) -> None:
        from odev.commands._helpers import normalizar_exit_code_odoo

        assert normalizar_exit_code_odoo(codigo) == 1


class TestListarModulosDisponiblesConfig:
    """paths.addons del .odev.yaml es la fuente de verdad para la validacion.

    Regresion del caso monorepo: modulos a dos niveles bajo directorios no
    convencionales (reswoy/reswoy-elog/<mod>) que detectar_layout solo
    encontraba via .gitmodules. Al des-submodularizar, la entrada desaparece
    de .gitmodules y la validacion dejaba de ver modulos que el container SI
    monta (los mounts se generan desde paths.addons).
    """

    def _ctx_con_config(self, tmp_path: Path, rutas: list[str]) -> MagicMock:
        ctx = MagicMock()
        ctx.directorio_config = tmp_path
        ctx.config.rutas_addons = rutas
        return ctx

    def test_config_encuentra_modulos_en_ruta_no_convencional(
        self, tmp_path: Path
    ) -> None:
        """Modulos bajo ruta declarada en config, invisible para heuristicas."""
        from odev.commands._helpers import listar_modulos_disponibles

        addon_dir = tmp_path / "reswoy" / "reswoy-elog"
        addon_dir.mkdir(parents=True)
        for nombre in ["purchase_workflow_app", "elog_config"]:
            (addon_dir / nombre).mkdir()
            (addon_dir / nombre / "__manifest__.py").touch()

        ctx = self._ctx_con_config(tmp_path, ["./reswoy/reswoy-elog"])

        resultado = listar_modulos_disponibles(ctx)

        assert resultado == {"purchase_workflow_app", "elog_config"}

    def test_config_ruta_absoluta_se_respeta(self, tmp_path: Path) -> None:
        """Rutas absolutas en paths.addons se usan tal cual."""
        from odev.commands._helpers import listar_modulos_disponibles

        addon_dir = tmp_path / "externo"
        addon_dir.mkdir()
        (addon_dir / "mod_x").mkdir()
        (addon_dir / "mod_x" / "__manifest__.py").touch()

        ctx = self._ctx_con_config(tmp_path / "proyecto", [str(addon_dir)])
        (tmp_path / "proyecto").mkdir()

        resultado = listar_modulos_disponibles(ctx)

        assert resultado == {"mod_x"}

    def test_config_sin_modulos_cae_a_heuristica(self, tmp_path: Path) -> None:
        """Rutas de config vacias/inexistentes → fallback a detectar_layout."""
        from odev.commands._helpers import listar_modulos_disponibles
        from odev.core.detect import RepoLayout, TipoRepo

        addon_dir = tmp_path / "addons"
        addon_dir.mkdir()
        (addon_dir / "mod_heuristico").mkdir()
        (addon_dir / "mod_heuristico" / "__manifest__.py").touch()

        fake_layout = RepoLayout(
            tipo=TipoRepo.MULTI_ADDON,
            rutas_addons=[addon_dir],
            modulos_encontrados=1,
        )
        ctx = self._ctx_con_config(tmp_path, ["./no-existe"])

        with patch(
            "odev.commands._helpers.detectar_layout", return_value=fake_layout
        ):
            resultado = listar_modulos_disponibles(ctx)

        assert resultado == {"mod_heuristico"}


# ---------------------------------------------------------------------------
# requerir_proyecto — el diagnostico no debe contaminar stdout
# ---------------------------------------------------------------------------


class TestRequerirProyectoEscribeAStderr:
    """requerir_proyecto lo llaman ~20 comandos, varios con --json.

    Escribir el diagnostico en stdout rompia el parseo de todos ellos: el
    consumidor recibia texto con codigos de color donde esperaba JSON, y
    explotaba con un error que no tenia nada que ver con la causa real.
    """

    def test_proyecto_no_encontrado_no_contamina_stdout(self, capsys) -> None:
        """El error de proyecto ausente sale por stderr, no por stdout."""
        import typer

        from odev.commands._helpers import requerir_proyecto
        from odev.core.resolver import ProyectoNoEncontradoError

        with patch(
            "odev.commands._helpers.resolver_proyecto",
            side_effect=ProyectoNoEncontradoError("no hay proyecto aca"),
        ):
            with pytest.raises(typer.Exit) as exc:
                requerir_proyecto()

        assert exc.value.exit_code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "no hay proyecto aca" in captured.err

    def test_proyecto_ambiguo_no_contamina_stdout(self, capsys) -> None:
        """La advertencia de ambiguedad sale por stderr, no por stdout."""
        import typer

        from odev.commands._helpers import requerir_proyecto
        from odev.core.resolver import ProyectoAmbiguoError

        with patch(
            "odev.commands._helpers.resolver_proyecto",
            side_effect=ProyectoAmbiguoError(Path("/tmp/x"), ["uno", "dos"]),
        ):
            with pytest.raises(typer.Exit) as exc:
                requerir_proyecto()

        assert exc.value.exit_code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "uno" in captured.err and "dos" in captured.err
