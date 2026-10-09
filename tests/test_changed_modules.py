"""Tests de odev.core.changed_modules: deteccion de modulos tocados por el diff.

Usan repositorios git reales en tmp_path: el comportamiento que importa
(merge-base, staged vs unstaged, untracked vs ignorados, gitlinks) es el de
git mismo, y un mock de su salida no probaria nada de eso.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from odev.core.changed_modules import (
    DeteccionCambios,
    consulta_dependientes_directos,
    dependientes_directos_instalados,
    detectar_modulos_cambiados,
    mapear_a_modulos,
)

# ---------------------------------------------------------------------------
# Helpers: repositorio git aislado de la config del usuario
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _git_aislado(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Aisla git de la config global/system del usuario (firma, hooks, etc.)."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig-vacio"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "odev-tests")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "odev-tests@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "odev-tests")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "odev-tests@example.com")
    # Que git nunca suba por encima de tmp_path buscando un repo.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))


def _git(repo: Path, *args: str) -> str:
    resultado = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return resultado.stdout.strip()


def _escribir(repo: Path, ruta: str, contenido: str = "x = 1\n") -> Path:
    archivo = repo / ruta
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(contenido, encoding="utf-8")
    return archivo


def _modulo(repo: Path, ruta_dir: str) -> None:
    """Crea un modulo minimo (manifest + models/__init__.py)."""
    _escribir(repo, f"{ruta_dir}/__manifest__.py", "{'name': 'x'}\n")
    _escribir(repo, f"{ruta_dir}/models/__init__.py", "")


def _commit(repo: Path, mensaje: str = "commit") -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", mensaje)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Repo con dos modulos commiteados en addons/ y un archivo suelto."""
    raiz = tmp_path / "proyecto"
    raiz.mkdir()
    _git(raiz, "init", "-q", "-b", "main")
    _modulo(raiz, "addons/mod_a")
    _modulo(raiz, "addons/mod_b")
    _escribir(raiz, "README.md", "proyecto\n")
    _escribir(raiz, ".gitignore", "*.log\n")
    _commit(raiz, "inicial")
    return raiz


def _nombres(deteccion: DeteccionCambios) -> list[str]:
    return [m.nombre for m in deteccion.modulos]


# ---------------------------------------------------------------------------
# Archivos cambiados: committed, staged, unstaged, untracked, ignorados
# ---------------------------------------------------------------------------


class TestArchivosCambiados:
    """Que cambios cuentan y cuales no."""

    def test_sin_cambios_no_detecta_nada(self, repo: Path) -> None:
        deteccion = detectar_modulos_cambiados(repo)
        assert deteccion.modulos == []
        assert deteccion.advertencias == []

    def test_cambio_sin_stagear_detecta_el_modulo(self, repo: Path) -> None:
        _escribir(repo, "addons/mod_a/models/__init__.py", "from . import foo\n")
        assert _nombres(detectar_modulos_cambiados(repo)) == ["mod_a"]

    def test_cambio_stageado_detecta_el_modulo(self, repo: Path) -> None:
        _escribir(repo, "addons/mod_b/models/__init__.py", "from . import bar\n")
        _git(repo, "add", "addons/mod_b/models/__init__.py")
        assert _nombres(detectar_modulos_cambiados(repo)) == ["mod_b"]

    def test_archivo_untracked_detecta_el_modulo(self, repo: Path) -> None:
        _escribir(repo, "addons/mod_a/models/nuevo.py")
        assert _nombres(detectar_modulos_cambiados(repo)) == ["mod_a"]

    def test_archivo_ignorado_no_cuenta(self, repo: Path) -> None:
        _escribir(repo, "addons/mod_a/debug.log", "ruido\n")
        assert detectar_modulos_cambiados(repo).modulos == []

    def test_archivo_fuera_de_modulos_se_ignora(self, repo: Path) -> None:
        _escribir(repo, "README.md", "otro texto\n")
        _escribir(repo, "scripts/deploy.sh", "echo hola\n")
        deteccion = detectar_modulos_cambiados(repo)
        assert deteccion.modulos == []
        assert deteccion.advertencias == []

    def test_base_head_excluye_lo_ya_commiteado(self, repo: Path) -> None:
        """--base default (HEAD): solo trabajo sin commitear."""
        _escribir(repo, "addons/mod_a/models/foo.py")
        _commit(repo, "toca mod_a")
        assert detectar_modulos_cambiados(repo, base="HEAD").modulos == []

    def test_base_rama_incluye_commits_desde_el_merge_base(self, repo: Path) -> None:
        """Con --base main desde una rama: commits propios + working tree."""
        _git(repo, "checkout", "-q", "-b", "feature")
        _escribir(repo, "addons/mod_a/models/foo.py")
        _commit(repo, "toca mod_a en la rama")
        _escribir(repo, "addons/mod_b/models/__init__.py", "# sin commitear\n")

        assert _nombres(detectar_modulos_cambiados(repo, base="main")) == ["mod_a", "mod_b"]

    def test_base_usa_merge_base_y_no_la_punta_de_la_base(self, repo: Path) -> None:
        """Commits nuevos en main despues del fork no cuentan como cambios propios."""
        _git(repo, "checkout", "-q", "-b", "feature")
        _escribir(repo, "addons/mod_a/models/foo.py")
        _commit(repo, "toca mod_a en la rama")

        _git(repo, "checkout", "-q", "main")
        _escribir(repo, "addons/mod_b/models/bar.py")
        _commit(repo, "toca mod_b en main")
        _git(repo, "checkout", "-q", "feature")

        assert _nombres(detectar_modulos_cambiados(repo, base="main")) == ["mod_a"]

    def test_modulo_nuevo_sin_trackear_se_detecta(self, repo: Path) -> None:
        _modulo(repo, "addons/mod_nuevo")
        assert _nombres(detectar_modulos_cambiados(repo)) == ["mod_nuevo"]

    def test_resultado_deduplicado_y_ordenado(self, repo: Path) -> None:
        _escribir(repo, "addons/mod_b/models/x.py")
        _escribir(repo, "addons/mod_b/models/y.py")
        _escribir(repo, "addons/mod_a/models/z.py")
        assert _nombres(detectar_modulos_cambiados(repo)) == ["mod_a", "mod_b"]

    def test_directorio_del_modulo_es_absoluto(self, repo: Path) -> None:
        _escribir(repo, "addons/mod_a/models/z.py")
        (modulo,) = detectar_modulos_cambiados(repo).modulos
        assert modulo.directorio == (repo / "addons" / "mod_a").resolve()

    def test_desde_un_subdirectorio_mapea_contra_la_raiz_del_repo(self, repo: Path) -> None:
        """Las rutas se resuelven contra --show-toplevel, no contra el cwd."""
        _escribir(repo, "addons/mod_a/models/z.py")
        _escribir(repo, "addons/mod_b/models/__init__.py", "# cambio\n")
        assert _nombres(detectar_modulos_cambiados(repo / "addons" / "mod_a")) == [
            "mod_a",
            "mod_b",
        ]


# ---------------------------------------------------------------------------
# Mapeo ruta -> modulo
# ---------------------------------------------------------------------------


class TestMapeo:
    """El ancestro mas cercano con __manifest__.py, sin pasar de la raiz."""

    def test_modulo_anidado_gana_el_mas_cercano(self, repo: Path) -> None:
        """Un modulo dentro de otro directorio-modulo: manda el mas cercano."""
        _modulo(repo, "addons/mod_a/vendored/mod_interno")
        _commit(repo, "modulo anidado")
        _escribir(repo, "addons/mod_a/vendored/mod_interno/models/__init__.py", "# x\n")
        assert _nombres(detectar_modulos_cambiados(repo)) == ["mod_interno"]

    def test_archivo_profundo_sube_hasta_el_modulo(self, repo: Path) -> None:
        _escribir(repo, "addons/mod_a/static/src/js/deep/widget.js", "// js\n")
        assert _nombres(detectar_modulos_cambiados(repo)) == ["mod_a"]

    def test_raiz_del_repo_como_modulo_unico(self, tmp_path: Path) -> None:
        """Layout modulo_unico: el manifest esta en la raiz del repo."""
        raiz = tmp_path / "mod_unico"
        raiz.mkdir()
        _git(raiz, "init", "-q", "-b", "main")
        _modulo(raiz, ".")
        _commit(raiz)
        _escribir(raiz, "models/__init__.py", "# cambio\n")

        assert _nombres(detectar_modulos_cambiados(raiz)) == ["mod_unico"]

    def test_mapear_a_modulos_es_independiente_de_git(self, tmp_path: Path) -> None:
        """La funcion de mapeo solo mira el arbol en disco."""
        _modulo(tmp_path, "addons/mod_x")
        modulos, advertencias = mapear_a_modulos(
            tmp_path,
            ["addons/mod_x/models/a.py", "otro/archivo.txt"],
            manifiestos_eliminados=set(),
        )
        assert [(m.nombre, m.directorio) for m in modulos] == [
            ("mod_x", (tmp_path / "addons" / "mod_x").resolve())
        ]
        assert advertencias == []


# ---------------------------------------------------------------------------
# Modulos eliminados y submodulos
# ---------------------------------------------------------------------------


class TestEliminadosYSubmodulos:
    """Casos que no se pueden testear y se avisan por advertencia."""

    def test_modulo_eliminado_se_omite_con_advertencia(self, repo: Path) -> None:
        _git(repo, "rm", "-q", "-r", "addons/mod_b")
        deteccion = detectar_modulos_cambiados(repo)

        assert deteccion.modulos == []
        assert len(deteccion.advertencias) == 1
        assert "mod_b" in deteccion.advertencias[0]
        assert "__manifest__.py" in deteccion.advertencias[0]

    def test_modulo_eliminado_sin_stagear_tambien_se_omite(self, repo: Path) -> None:
        """Borrado del disco sin git rm: el diff contra el working tree lo ve."""
        import shutil

        shutil.rmtree(repo / "addons" / "mod_a")
        deteccion = detectar_modulos_cambiados(repo)

        assert deteccion.modulos == []
        assert len(deteccion.advertencias) == 1
        assert "mod_a" in deteccion.advertencias[0]

    def test_manifest_eliminado_con_resto_del_modulo_presente(self, repo: Path) -> None:
        (repo / "addons" / "mod_a" / "__manifest__.py").unlink()
        _escribir(repo, "addons/mod_a/models/__init__.py", "# cambio\n")
        deteccion = detectar_modulos_cambiados(repo)

        assert deteccion.modulos == []
        assert len(deteccion.advertencias) == 1
        assert "mod_a" in deteccion.advertencias[0]

    def test_gitlink_cambiado_advierte_con_su_ruta(self, repo: Path) -> None:
        """Un submodulo (gitlink) cambiado se avisa; sus modulos no se detectan."""
        interno = repo / "vendor" / "oca"
        interno.mkdir(parents=True)
        _git(interno, "init", "-q", "-b", "main")
        _modulo(interno, "mod_oca")
        _commit(interno, "inicial interno")
        _git(repo, "add", "vendor/oca")

        deteccion = detectar_modulos_cambiados(repo)

        assert deteccion.modulos == []
        assert len(deteccion.advertencias) == 1
        assert "vendor/oca" in deteccion.advertencias[0]
        assert "submodulo" in deteccion.advertencias[0]

    def test_gitlink_no_tapa_modulos_normales(self, repo: Path) -> None:
        interno = repo / "vendor" / "oca"
        interno.mkdir(parents=True)
        _git(interno, "init", "-q", "-b", "main")
        _modulo(interno, "mod_oca")
        _commit(interno, "inicial interno")
        _git(repo, "add", "vendor/oca")
        _escribir(repo, "addons/mod_a/models/z.py")

        deteccion = detectar_modulos_cambiados(repo)

        assert _nombres(deteccion) == ["mod_a"]
        assert any("vendor/oca" in a for a in deteccion.advertencias)

    def test_repo_anidado_sin_trackear_advierte(self, repo: Path) -> None:
        """Un repo git anidado sin agregar: git no lista su contenido."""
        interno = repo / "vendor" / "suelto"
        interno.mkdir(parents=True)
        _git(interno, "init", "-q", "-b", "main")
        _modulo(interno, "mod_suelto")
        _commit(interno, "inicial interno")

        deteccion = detectar_modulos_cambiados(repo)

        assert deteccion.modulos == []
        assert len(deteccion.advertencias) == 1
        assert "vendor/suelto" in deteccion.advertencias[0]


# ---------------------------------------------------------------------------
# Repo sin commits (HEAD sin nacer)
# ---------------------------------------------------------------------------


@pytest.fixture
def repo_sin_commits(tmp_path: Path) -> Path:
    """Repo recien inicializado: HEAD apunta a una rama sin commits."""
    raiz = tmp_path / "nuevo"
    raiz.mkdir()
    _git(raiz, "init", "-q", "-b", "main")
    _escribir(raiz, ".gitignore", "*.log\n")
    return raiz


class TestRepoSinCommits:
    """Con la base implicita, un HEAD sin nacer compara contra el arbol vacio."""

    def test_modulo_untracked_se_detecta(self, repo_sin_commits: Path) -> None:
        _modulo(repo_sin_commits, "addons/mod_x")
        _escribir(repo_sin_commits, "addons/mod_ignorado/debug.log", "ruido\n")
        deteccion = detectar_modulos_cambiados(repo_sin_commits)
        assert _nombres(deteccion) == ["mod_x"]
        assert deteccion.advertencias == []

    def test_modulo_stageado_se_detecta(self, repo_sin_commits: Path) -> None:
        _modulo(repo_sin_commits, "addons/mod_y")
        _git(repo_sin_commits, "add", "addons/mod_y")
        assert _nombres(detectar_modulos_cambiados(repo_sin_commits)) == ["mod_y"]

    def test_sin_cambios_no_detecta_nada(self, repo_sin_commits: Path) -> None:
        assert detectar_modulos_cambiados(repo_sin_commits).modulos == []

    def test_head_explicito_sigue_siendo_ref_invalida(self, repo_sin_commits: Path) -> None:
        """Solo la base implicita cae al arbol vacio; un --base HEAD pedido no."""
        _modulo(repo_sin_commits, "addons/mod_x")
        with pytest.raises(ValueError, match="'HEAD'"):
            detectar_modulos_cambiados(repo_sin_commits, base="HEAD")

    def test_base_explicita_invalida_sigue_siendo_value_error(self, repo_sin_commits: Path) -> None:
        with pytest.raises(ValueError, match="no-existe"):
            detectar_modulos_cambiados(repo_sin_commits, base="no-existe")


# ---------------------------------------------------------------------------
# Errores: ref invalida (uso) y entorno sin git (entorno)
# ---------------------------------------------------------------------------


class TestErrores:
    """ValueError para entrada invalida, RuntimeError para entorno inutilizable."""

    def test_ref_invalida_levanta_value_error(self, repo: Path) -> None:
        with pytest.raises(ValueError, match="no-existe"):
            detectar_modulos_cambiados(repo, base="no-existe")

    def test_ref_que_parece_opcion_levanta_value_error(self, repo: Path) -> None:
        """Una ref con '-' inicial no debe llegar a git como opcion."""
        with pytest.raises(ValueError, match="--output"):
            detectar_modulos_cambiados(repo, base="--output=/tmp/x")

    def test_ref_vacia_levanta_value_error(self, repo: Path) -> None:
        with pytest.raises(ValueError):
            detectar_modulos_cambiados(repo, base="  ")

    def test_directorio_fuera_de_un_repo_levanta_runtime_error(self, tmp_path: Path) -> None:
        sin_git = tmp_path / "sin_git"
        sin_git.mkdir()
        with pytest.raises(RuntimeError, match="repositorio git"):
            detectar_modulos_cambiados(sin_git)

    def test_git_ausente_levanta_runtime_error(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _sin_git(*args, **kwargs):
            raise FileNotFoundError(2, "No such file or directory", "git")

        monkeypatch.setattr("odev.core.changed_modules.subprocess.run", _sin_git)
        with pytest.raises(RuntimeError, match="git"):
            detectar_modulos_cambiados(repo)


# ---------------------------------------------------------------------------
# Dependientes directos instalados (--with-dependents)
# ---------------------------------------------------------------------------


class TestDependientesDirectos:
    """La consulta corre por el ejecutor SQL inyectado; aca va mockeado."""

    def test_seleccion_vacia_no_consulta(self) -> None:
        llamadas: list[str] = []

        def _ejecutar(consulta: str) -> list[dict]:
            llamadas.append(consulta)
            return []

        assert dependientes_directos_instalados([], _ejecutar) == []
        assert llamadas == []

    def test_consulta_filtra_dependencias_directas_instaladas(self) -> None:
        consulta = consulta_dependientes_directos(["mod_b", "mod_a"])
        assert "ir_module_module_dependency" in consulta
        assert "ir_module_module" in consulta
        assert "state = 'installed'" in consulta
        assert "IN ('mod_a', 'mod_b')" in consulta

    def test_nombres_con_comilla_se_escapan(self) -> None:
        consulta = consulta_dependientes_directos(["o'reilly"])
        assert "IN ('o''reilly')" in consulta
        assert "'o'reilly'" not in consulta

    def test_devuelve_nombres_deduplicados_y_ordenados(self) -> None:
        def _ejecutar(consulta: str) -> list[dict]:
            return [{"name": "mod_z"}, {"name": "mod_c"}, {"name": "mod_z"}, {"name": ""}]

        assert dependientes_directos_instalados(["mod_a"], _ejecutar) == ["mod_c", "mod_z"]

    def test_pasa_la_consulta_al_ejecutor(self) -> None:
        recibidas: list[str] = []

        def _ejecutar(consulta: str) -> list[dict]:
            recibidas.append(consulta)
            return []

        dependientes_directos_instalados(["mod_a"], _ejecutar)
        assert recibidas == [consulta_dependientes_directos(["mod_a"])]

    def test_error_del_ejecutor_se_propaga(self) -> None:
        def _ejecutar(consulta: str) -> list[dict]:
            raise RuntimeError("could not connect to server")

        with pytest.raises(RuntimeError, match="could not connect"):
            dependientes_directos_instalados(["mod_a"], _ejecutar)
