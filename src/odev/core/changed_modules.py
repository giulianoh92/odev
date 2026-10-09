"""Deteccion de los modulos Odoo tocados por el diff de git.

Soporte de 'odev test --changed': a partir de los archivos que difieren
entre merge-base(<base>, HEAD) y el working tree (commiteado, stageado y sin
stagear), mas los untracked que git no ignora, resuelve que modulos Odoo
quedaron tocados. Los submodulos git cambiados se recorren con la misma
logica, contra el commit que el superproyecto registraba en la base, y
recursivamente para los anidados. Para --with-dependents arma ademas la consulta de los
modulos instalados que dependen directamente de esa seleccion.

Sin dependencias de la CLI: senaliza con excepciones de dominio y devuelve
las advertencias como datos, para que cada frontend decida como
presentarlas. ValueError para una referencia invalida (error de uso),
RuntimeError cuando git no esta disponible o el directorio no esta dentro de
un repositorio (error de entorno).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable

_MANIFEST = "__manifest__.py"

# Modos de la salida --raw de git diff: gitlink (submodulo) y entrada ausente.
_MODO_GITLINK = "160000"
_MODO_AUSENTE = "000000"


@dataclass(frozen=True)
class ModuloDetectado:
    """Un modulo Odoo tocado por el diff.

    Atributos:
        nombre:     Nombre tecnico (nombre del directorio del modulo).
        directorio: Ruta absoluta y resuelta del directorio del modulo.
    """

    nombre: str
    directorio: Path


@dataclass
class DeteccionCambios:
    """Resultado de la deteccion.

    Atributos:
        modulos:      Modulos detectados, sin duplicados, ordenados por nombre.
        advertencias: Cambios que no se pudieron mapear a un modulo testeable
                      (modulos eliminados, submodulos sin checkout, sin el
                      commit de la base o eliminados, repos anidados).
    """

    modulos: list[ModuloDetectado] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Gitlink:
    """Un submodulo cambiado que sigue presente en el working tree.

    Atributos:
        ruta:         Ruta del submodulo, relativa a la raiz de su repo.
        commit_viejo: Commit que el repo registraba para el submodulo en el
                      punto de comparacion, o None si ahi no existia.
    """

    ruta: str
    commit_viejo: str | None


@dataclass
class _CambiosGit:
    """Salida cruda de git ya clasificada (rutas relativas a la raiz)."""

    rutas: list[str] = field(default_factory=list)
    gitlinks: list[_Gitlink] = field(default_factory=list)
    submodulos_eliminados: list[str] = field(default_factory=list)
    repos_anidados: list[str] = field(default_factory=list)
    manifiestos_eliminados: set[str] = field(default_factory=set)


def _git(directorio: Path, *args: str) -> subprocess.CompletedProcess:
    """Ejecuta git en `directorio` capturando la salida en bytes.

    Raises:
        RuntimeError: si git no esta instalado o no esta en el PATH.
    """
    try:
        return subprocess.run(
            ["git", "-C", str(directorio), *args],
            capture_output=True,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "git no esta disponible en el PATH: --changed lo necesita para "
            "detectar los modulos cambiados."
        ) from exc


def _stderr(resultado: subprocess.CompletedProcess) -> str:
    """Primera linea de stderr de git, para incluirla en un mensaje."""
    lineas = os.fsdecode(resultado.stderr or b"").strip().splitlines()
    return lineas[0] if lineas else ""


def raiz_repositorio(directorio: Path) -> Path:
    """Devuelve la raiz del repositorio git que contiene `directorio`.

    Argumentos:
        directorio: Directorio del proyecto (o cualquiera dentro del repo).

    Retorna:
        Ruta absoluta de `git rev-parse --show-toplevel`.

    Raises:
        RuntimeError: si git no esta disponible o el directorio no esta
            dentro de un repositorio git.
    """
    resultado = _git(directorio, "rev-parse", "--show-toplevel")
    if resultado.returncode != 0:
        detalle = _stderr(resultado)
        raise RuntimeError(
            f"'{directorio}' no esta dentro de un repositorio git: --changed "
            "necesita git para detectar los modulos cambiados."
            + (f" ({detalle})" if detalle else "")
        )
    return Path(os.fsdecode(resultado.stdout).strip()).resolve()


def _arbol_vacio(raiz: Path) -> str:
    """Hash del arbol vacio en el formato de objetos del repo.

    Se calcula en vez de fijarlo: un repo sha256 no usa el mismo hash que uno
    sha1. git conoce el arbol vacio aunque no este escrito en el repo.
    """
    resultado = _git(raiz, "hash-object", "-t", "tree", "--stdin")
    if resultado.returncode != 0:
        raise RuntimeError(f"git hash-object fallo: {_stderr(resultado)}")
    return os.fsdecode(resultado.stdout).strip()


def _resolver_merge_base(raiz: Path, base: str | None) -> str:
    """Resuelve el punto de comparacion: merge-base(<base>, HEAD).

    `base` None es la base implicita, HEAD. Si HEAD todavia no tiene commits
    (repo recien inicializado) no hay merge-base posible, y se compara contra
    el arbol vacio: todo lo stageado y lo untracked cuenta como cambiado. Una
    base explicita, incluso 'HEAD', no tiene ese fallback: si no resuelve, es
    un error de uso.

    Raises:
        ValueError: si la referencia explicita es vacia, parece una opcion de
            git, no existe, o no tiene ancestro comun con HEAD.
    """
    if base is None:
        head = _git(raiz, "rev-parse", "--verify", "--quiet", "HEAD^{commit}")
        if head.returncode != 0:
            return _arbol_vacio(raiz)
        base = "HEAD"

    if not base.strip():
        raise ValueError("--base necesita una referencia git (rama, tag o commit).")
    if base.startswith("-"):
        # Una ref con '-' inicial llegaria a git como opcion, no como ref.
        raise ValueError(f"Referencia git invalida para --base: '{base}'.")

    verificado = _git(raiz, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}")
    if verificado.returncode != 0:
        raise ValueError(
            f"Referencia git invalida para --base: '{base}' no resuelve a un "
            "commit en este repositorio."
        )
    sha_base = os.fsdecode(verificado.stdout).strip()

    merge_base = _git(raiz, "merge-base", sha_base, "HEAD")
    if merge_base.returncode != 0:
        raise ValueError(
            f"No se pudo calcular el merge-base entre '{base}' y HEAD: "
            "no tienen un ancestro comun (o HEAD no tiene commits)."
        )
    return os.fsdecode(merge_base.stdout).strip()


def _listar_cambios(raiz: Path, merge_base: str) -> _CambiosGit:
    """Lista lo que cambio entre `merge_base` y el working tree.

    `merge_base` es un commit, o el arbol vacio en un repo sin commits.

    `git diff --raw <commit>` compara el commit contra el working tree, asi
    que cubre lo commiteado despues del merge-base, lo stageado y lo sin
    stagear en una sola pasada. --no-renames separa un rename en baja + alta:
    los dos lados cuentan como tocados. --ignore-submodules=none hace que un
    submodulo con cambios sin commitear o untracked cuente como cambiado
    aunque .gitmodules o la config digan 'ignore'. --no-abbrev deja el sha
    completo del gitlink viejo, que es el punto de comparacion dentro del
    submodulo. Los untracked no ignorados salen de
    `git ls-files --others --exclude-standard`.

    Raises:
        RuntimeError: si git falla de una forma que no es de uso.
    """
    cambios = _CambiosGit()

    diff = _git(
        raiz,
        "diff",
        "--raw",
        "-z",
        "--no-renames",
        "--no-abbrev",
        "--ignore-submodules=none",
        merge_base,
    )
    if diff.returncode != 0:
        raise RuntimeError(f"git diff fallo: {_stderr(diff)}")

    # Formato -z: ':<modo_src> <modo_dst> <sha_src> <sha_dst> <estado>\0<ruta>\0'
    tokens = diff.stdout.split(b"\0")
    i = 0
    while i + 1 < len(tokens):
        meta = os.fsdecode(tokens[i])
        ruta = os.fsdecode(tokens[i + 1])
        i += 2
        if not meta.startswith(":"):
            continue
        campos = meta[1:].split()
        modo_src, modo_dst, sha_src, estado = campos[0], campos[1], campos[2], campos[-1]
        src_es_gitlink = modo_src == _MODO_GITLINK
        dst_es_gitlink = modo_dst == _MODO_GITLINK
        if src_es_gitlink or dst_es_gitlink:
            if dst_es_gitlink:
                cambios.gitlinks.append(_Gitlink(ruta, sha_src if src_es_gitlink else None))
            else:
                cambios.submodulos_eliminados.append(ruta)
            # Cambio de tipo (archivo <-> gitlink): el lado que es archivo
            # comun tambien cuenta como ruta tocada.
            lado_archivo = modo_dst if src_es_gitlink else modo_src
            if not (src_es_gitlink and dst_es_gitlink) and lado_archivo != _MODO_AUSENTE:
                cambios.rutas.append(ruta)
            continue
        if estado.startswith("D") and PurePosixPath(ruta).name == _MANIFEST:
            cambios.manifiestos_eliminados.add(str(PurePosixPath(ruta).parent))
        cambios.rutas.append(ruta)

    untracked = _git(raiz, "ls-files", "--others", "--exclude-standard", "-z")
    if untracked.returncode != 0:
        raise RuntimeError(f"git ls-files fallo: {_stderr(untracked)}")
    for crudo in untracked.stdout.split(b"\0"):
        if not crudo:
            continue
        ruta = os.fsdecode(crudo)
        # git no recorre un repo anidado sin trackear: lo lista como 'dir/'.
        if ruta.endswith("/"):
            cambios.repos_anidados.append(ruta.rstrip("/"))
        else:
            cambios.rutas.append(ruta)

    return cambios


def mapear_a_modulos(
    raiz: Path,
    rutas: Iterable[str],
    manifiestos_eliminados: set[str],
    prefijo: str = "",
) -> tuple[list[ModuloDetectado], list[str]]:
    """Mapea rutas relativas a la raiz del repo al modulo que las contiene.

    Cada ruta se asigna al ancestro mas cercano que tiene __manifest__.py en
    disco, sin subir mas alla de `raiz` (la raiz misma cuenta: layout de
    modulo unico). Una ruta sin modulo se ignora. Si en el camino aparece un
    directorio cuyo __manifest__.py figura como eliminado en el diff, el
    modulo se omite con una advertencia: ya no existe, no hay que testear.

    Argumentos:
        raiz:                   Raiz del repositorio git.
        rutas:                  Rutas relativas a `raiz`, en formato posix.
        manifiestos_eliminados: Directorios (relativos, posix) cuyo
                                __manifest__.py el diff da como eliminado.
        prefijo:                Ruta de `raiz` dentro del repo de mas arriba
                                ('subs/ext/'), solo para los mensajes.

    Retorna:
        Tupla (modulos sin duplicados ordenados por nombre, advertencias).
    """
    raiz = raiz.resolve()
    encontrados: dict[Path, ModuloDetectado] = {}
    eliminados: set[str] = set()

    for ruta in rutas:
        directorio = PurePosixPath(ruta).parent
        while True:
            rel = str(directorio)
            if (raiz / rel / _MANIFEST).is_file():
                absoluto = (raiz / rel).resolve()
                if absoluto not in encontrados:
                    encontrados[absoluto] = ModuloDetectado(absoluto.name, absoluto)
                break
            if rel in manifiestos_eliminados:
                eliminados.add(rel)
                break
            if rel == ".":
                break
            directorio = directorio.parent

    advertencias = [
        f"modulo '{(raiz / rel).name}' ({_ruta_visible(prefijo, rel)}) eliminado: "
        f"su {_MANIFEST} ya no existe, se omite."
        for rel in sorted(eliminados)
    ]
    modulos = sorted(encontrados.values(), key=lambda m: (m.nombre, str(m.directorio)))
    return modulos, advertencias


def _ruta_visible(prefijo: str, rel: str) -> str:
    """Ruta relativa al repo de mas arriba, para los mensajes."""
    if rel == ".":
        return prefijo.rstrip("/") or "."
    return f"{prefijo}{rel}"


def _raiz_submodulo(raiz: Path, ruta: str) -> Path | None:
    """Raiz del checkout del submodulo en `ruta`, o None si no tiene checkout.

    Un submodulo sin inicializar deja un directorio vacio (o ninguno), y git
    lo resuelve como parte del repo de arriba: por eso se compara el
    toplevel con el propio directorio.
    """
    directorio = (raiz / ruta).resolve()
    if not directorio.is_dir():
        return None
    resultado = _git(directorio, "rev-parse", "--show-toplevel")
    if resultado.returncode != 0:
        return None
    toplevel = Path(os.fsdecode(resultado.stdout).strip()).resolve()
    return toplevel if toplevel == directorio else None


def _existe_commit(raiz: Path, sha: str) -> bool:
    """True si el commit esta en el object store del repo."""
    return _git(raiz, "cat-file", "-e", f"{sha}^{{commit}}").returncode == 0


def _detectar_en_repo(
    raiz: Path,
    punto: str,
    prefijo: str,
    encontrados: dict[Path, ModuloDetectado],
    advertencias: list[str],
) -> None:
    """Detecta los modulos tocados en un repo y recorre sus submodulos.

    La misma rutina sirve para el superproyecto y para cada submodulo
    cambiado: dentro del submodulo, el punto de comparacion es el commit que
    el repo de arriba registraba en el suyo (el arbol vacio si ahi no
    existia), y el mapeo a modulos no sube mas alla de la raiz del
    submodulo. Los submodulos que no se pueden recorrer (sin checkout, sin
    el commit de la base, o con git fallando adentro) quedan como
    advertencia; nunca cortan la deteccion. Un fallo de git en el repo de
    mas arriba si se propaga: ese es el que eligio el usuario.

    Argumentos:
        raiz:         Raiz del repo (superproyecto o checkout del submodulo).
        punto:        Commit (o arbol vacio) contra el que se compara.
        prefijo:      Ruta de `raiz` dentro del superproyecto, con '/' final.
        encontrados:  Acumulador de modulos por directorio absoluto.
        advertencias: Acumulador de advertencias.
    """
    cambios = _listar_cambios(raiz, punto)

    modulos, avisos = mapear_a_modulos(
        raiz, cambios.rutas, cambios.manifiestos_eliminados, prefijo=prefijo
    )
    for modulo in modulos:
        encontrados.setdefault(modulo.directorio, modulo)
    advertencias.extend(avisos)

    advertencias.extend(
        f"submodulo git '{prefijo}{ruta}' eliminado: sus modulos no se testean."
        for ruta in sorted(cambios.submodulos_eliminados)
    )

    for gitlink in sorted(cambios.gitlinks, key=lambda g: g.ruta):
        visible = f"{prefijo}{gitlink.ruta}"
        raiz_sub = _raiz_submodulo(raiz, gitlink.ruta)
        if raiz_sub is None:
            advertencias.append(
                f"submodulo git '{visible}' cambiado pero sin checkout: sus modulos "
                f"no se detectan. Inicializalo con 'git submodule update --init {visible}'."
            )
            continue
        if gitlink.commit_viejo is not None and not _existe_commit(raiz_sub, gitlink.commit_viejo):
            advertencias.append(
                f"submodulo git '{visible}': el commit {gitlink.commit_viejo[:12]} "
                "registrado en la base no esta en su object store, sus modulos no se "
                f"detectan. Traelo con 'git -C {visible} fetch'."
            )
            continue
        try:
            punto_sub = (
                gitlink.commit_viejo if gitlink.commit_viejo is not None else _arbol_vacio(raiz_sub)
            )
            _detectar_en_repo(raiz_sub, punto_sub, f"{visible}/", encontrados, advertencias)
        except RuntimeError as exc:
            # Un submodulo ilegible (repo corrupto, permisos) no corta la
            # deteccion: _listar_cambios falla antes de acumular nada de ese
            # submodulo, y los anidados se protegen en su propio nivel.
            advertencias.append(
                f"submodulo git '{visible}' no se pudo leer ({exc}): sus modulos no se detectan."
            )

    advertencias.extend(
        f"repositorio git anidado '{prefijo}{ruta}' sin trackear: --changed no "
        "recorre repos anidados, sus modulos no se detectan."
        for ruta in sorted(cambios.repos_anidados)
    )


def detectar_modulos_cambiados(directorio: Path, base: str | None = None) -> DeteccionCambios:
    """Detecta los modulos Odoo tocados respecto de merge-base(<base>, HEAD).

    Los submodulos cambiados se recorren (ver _detectar_en_repo); sus
    modulos se devuelven como los del superproyecto.

    Argumentos:
        directorio: Directorio del proyecto; git corre contra el repositorio
                    que lo contiene y las rutas se mapean contra su raiz.
        base:       Referencia git explicita, o None (default) para la base
                    implicita HEAD: solo trabajo sin commitear. En un repo sin
                    commits la base implicita es el arbol vacio.

    Retorna:
        DeteccionCambios con los modulos y las advertencias.

    Raises:
        ValueError: si una `base` explicita no es una referencia valida.
        RuntimeError: si git no esta disponible o `directorio` no esta dentro
            de un repositorio git.
    """
    raiz = raiz_repositorio(directorio)
    merge_base = _resolver_merge_base(raiz, base)

    encontrados: dict[Path, ModuloDetectado] = {}
    advertencias: list[str] = []
    _detectar_en_repo(raiz, merge_base, "", encontrados, advertencias)

    modulos = sorted(encontrados.values(), key=lambda m: (m.nombre, str(m.directorio)))
    return DeteccionCambios(modulos=modulos, advertencias=advertencias)


def _literal_sql(valor: str) -> str:
    """Literal de texto SQL: comillas simples, con las internas duplicadas.

    Con standard_conforming_strings (default desde PostgreSQL 9.1) la barra
    invertida es literal, asi que duplicar la comilla alcanza.
    """
    return "'" + valor.replace("'", "''") + "'"


def consulta_dependientes_directos(modulos: Iterable[str]) -> str:
    """Arma la consulta de los modulos instalados que dependen de `modulos`.

    Solo dependencias directas: ir_module_module_dependency.name es el
    modulo requerido y module_id el que lo requiere. Los dependientes
    transitivos quedan fuera a proposito.

    Argumentos:
        modulos: Nombres tecnicos de la seleccion (no vacia).

    Retorna:
        Sentencia SQL con una columna 'name'.
    """
    lista = ", ".join(_literal_sql(m) for m in sorted(set(modulos)))
    return (
        "SELECT DISTINCT m.name FROM ir_module_module_dependency d "
        "JOIN ir_module_module m ON m.id = d.module_id "
        f"WHERE d.name IN ({lista}) AND m.state = 'installed' "
        "ORDER BY m.name"
    )


def dependientes_directos_instalados(
    modulos: Iterable[str],
    ejecutar_sql: Callable[[str], list[dict]],
) -> list[str]:
    """Devuelve los modulos instalados que dependen directamente de `modulos`.

    El ejecutor se inyecta para que core/ no dependa de commands/: el
    frontend pasa su camino SQL de siempre (`_execute_sql`). Esta funcion
    no traduce sus errores (RuntimeError de psql, CalledProcessError de
    docker): los propaga tal cual, y el frontend los envuelve en un
    RuntimeError con el contexto de --with-dependents.

    Argumentos:
        modulos:      Nombres tecnicos de la seleccion.
        ejecutar_sql: Ejecuta una consulta y devuelve filas como dicts.

    Retorna:
        Nombres sin duplicados y ordenados. Lista vacia sin consultar si la
        seleccion esta vacia.
    """
    seleccion = sorted(set(modulos))
    if not seleccion:
        return []
    filas = ejecutar_sql(consulta_dependientes_directos(seleccion))
    return sorted({fila["name"] for fila in filas if fila.get("name")})
