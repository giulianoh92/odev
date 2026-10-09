"""Deteccion de los modulos Odoo tocados por el diff de git.

Soporte de 'odev test --changed': a partir de los archivos que difieren
entre merge-base(<base>, HEAD) y el working tree (commiteado, stageado y sin
stagear), mas los untracked que git no ignora, resuelve que modulos Odoo
quedaron tocados. Para --with-dependents arma ademas la consulta de los
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

# Modo de un gitlink (submodulo) en la salida --raw de git diff.
_MODO_GITLINK = "160000"


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
                      (modulos eliminados, submodulos, repos anidados).
    """

    modulos: list[ModuloDetectado] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)


@dataclass
class _CambiosGit:
    """Salida cruda de git ya clasificada (rutas relativas a la raiz)."""

    rutas: list[str] = field(default_factory=list)
    gitlinks: list[str] = field(default_factory=list)
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


def _resolver_merge_base(raiz: Path, base: str) -> str:
    """Resuelve merge-base(<base>, HEAD) a un sha de commit.

    Raises:
        ValueError: si la referencia es vacia, parece una opcion de git, no
            existe, o no tiene ancestro comun con HEAD.
    """
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

    `git diff --raw <commit>` compara el commit contra el working tree, asi
    que cubre lo commiteado despues del merge-base, lo stageado y lo sin
    stagear en una sola pasada. --no-renames separa un rename en baja + alta:
    los dos lados cuentan como tocados. Los untracked no ignorados salen de
    `git ls-files --others --exclude-standard`.

    Raises:
        RuntimeError: si git falla de una forma que no es de uso.
    """
    cambios = _CambiosGit()

    diff = _git(raiz, "diff", "--raw", "-z", "--no-renames", merge_base)
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
        modo_src, modo_dst, estado = campos[0], campos[1], campos[-1]
        if _MODO_GITLINK in (modo_src, modo_dst):
            cambios.gitlinks.append(ruta)
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
        f"modulo '{(raiz / rel).name}' ({rel}) eliminado: su {_MANIFEST} ya no existe, se omite."
        for rel in sorted(eliminados)
    ]
    modulos = sorted(encontrados.values(), key=lambda m: (m.nombre, str(m.directorio)))
    return modulos, advertencias


def detectar_modulos_cambiados(directorio: Path, base: str = "HEAD") -> DeteccionCambios:
    """Detecta los modulos Odoo tocados respecto de merge-base(<base>, HEAD).

    Argumentos:
        directorio: Directorio del proyecto; git corre contra el repositorio
                    que lo contiene y las rutas se mapean contra su raiz.
        base:       Referencia git. Default 'HEAD': solo trabajo sin commitear.

    Retorna:
        DeteccionCambios con los modulos y las advertencias.

    Raises:
        ValueError: si `base` no es una referencia valida.
        RuntimeError: si git no esta disponible o `directorio` no esta dentro
            de un repositorio git.
    """
    raiz = raiz_repositorio(directorio)
    merge_base = _resolver_merge_base(raiz, base)
    cambios = _listar_cambios(raiz, merge_base)

    modulos, advertencias = mapear_a_modulos(raiz, cambios.rutas, cambios.manifiestos_eliminados)
    advertencias.extend(
        f"submodulo git '{ruta}' cambiado: --changed no recorre submodulos, "
        "sus modulos no se detectan."
        for ruta in sorted(cambios.gitlinks)
    )
    advertencias.extend(
        f"repositorio git anidado '{ruta}' sin trackear: --changed no recorre "
        "repos anidados, sus modulos no se detectan."
        for ruta in sorted(cambios.repos_anidados)
    )
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
