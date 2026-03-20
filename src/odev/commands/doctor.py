"""Comando 'doctor': diagnostica el entorno de desarrollo y reporta problemas.

Ejecuta una serie de verificaciones del sistema y del proyecto,
mostrando resultados con indicadores de color:
- [OK]   verde  -> todo correcto
- [WARN] amarillo -> advertencia, no bloqueante
- [FAIL] rojo   -> problema que impide el funcionamiento
- [INFO] azul   -> informacion adicional
"""

import platform
import shutil
import socket
import subprocess
import sys

import typer

from odev import __version__
from odev.core.compat import ProjectMode, detect_mode
from odev.core.console import console


def doctor() -> None:
    """Diagnostica el entorno de desarrollo y reporta problemas.

    Ejecuta verificaciones de Docker, Docker Compose, Python,
    proyecto detectado, archivos de configuracion, puertos
    disponibles y compatibilidad de version.
    """
    console.print()
    console.print("[bold]Diagnostico del entorno odev[/]")
    console.print("=" * 40)
    console.print()

    # Ejecutar todas las verificaciones en orden
    verificaciones = [
        _verificar_docker,
        _verificar_docker_compose,
        _verificar_python,
        _verificar_proyecto,
        _verificar_env,
        _verificar_docker_compose_file,
        _verificar_odoo_conf,
        _verificar_addons,
        _verificar_puertos,
        _verificar_version_compatible,
    ]

    total_fallos = 0
    for verificacion in verificaciones:
        resultado = verificacion()
        if resultado is False:
            total_fallos += 1

    console.print()
    if total_fallos == 0:
        console.print("[bold green]Todas las verificaciones pasaron correctamente.[/]")
    else:
        console.print(
            f"[bold red]{total_fallos} verificacion(es) fallaron.[/] "
            "Revisa los errores marcados con [FAIL]."
        )


def _imprimir_ok(mensaje: str) -> None:
    """Imprime un resultado exitoso con indicador verde.

    Args:
        mensaje: Descripcion del chequeo exitoso.
    """
    console.print(f"  [bold green]\\[OK][/]   {mensaje}")


def _imprimir_warn(mensaje: str) -> None:
    """Imprime una advertencia con indicador amarillo.

    Args:
        mensaje: Descripcion de la advertencia.
    """
    console.print(f"  [bold yellow]\\[WARN][/] {mensaje}")


def _imprimir_fail(mensaje: str) -> None:
    """Imprime un fallo con indicador rojo.

    Args:
        mensaje: Descripcion del fallo.
    """
    console.print(f"  [bold red]\\[FAIL][/] {mensaje}")


def _imprimir_info(mensaje: str) -> None:
    """Imprime informacion adicional con indicador azul.

    Args:
        mensaje: Informacion adicional a mostrar.
    """
    console.print(f"  [bold blue]\\[INFO][/] {mensaje}")


def _verificar_docker() -> bool:
    """Verifica que Docker este instalado y funcionando.

    Returns:
        True si Docker esta disponible, False si no.
    """
    ruta_docker = shutil.which("docker")
    if ruta_docker is None:
        _imprimir_fail("Docker no esta instalado o no esta en el PATH.")
        return False

    try:
        resultado = subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if resultado.returncode == 0:
            version = resultado.stdout.strip()
            _imprimir_ok(f"Docker instalado ({version})")
            return True
        else:
            _imprimir_fail("Docker instalado pero no responde correctamente.")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        _imprimir_fail("Docker instalado pero no se pudo obtener la version.")
        return False


def _verificar_docker_compose() -> bool:
    """Verifica que Docker Compose v2 este disponible.

    Returns:
        True si Docker Compose v2 esta disponible, False si no.
    """
    try:
        resultado = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if resultado.returncode == 0:
            version = resultado.stdout.strip()
            _imprimir_ok(f"Docker Compose v2 disponible ({version})")
            return True
        else:
            _imprimir_fail("Docker Compose v2 no esta disponible.")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        _imprimir_fail(
            "Docker Compose v2 no esta disponible. "
            "Asegurate de tener Docker Desktop o el plugin 'docker-compose-plugin'."
        )
        return False


def _verificar_python() -> bool:
    """Verifica la version de Python.

    Returns:
        True siempre (informativo).
    """
    version_python = platform.python_version()
    version_info = sys.version_info

    if version_info >= (3, 10):
        _imprimir_ok(f"Python {version_python}")
        return True
    else:
        _imprimir_fail(
            f"Python {version_python} (se requiere 3.10+). "
            "Actualiza tu version de Python."
        )
        return False


def _verificar_proyecto() -> bool | None:
    """Verifica si se detecta un proyecto odev.

    Returns:
        True si se detecto proyecto, False si no hay proyecto,
        None si es informativo.
    """
    modo, raiz = detect_mode()

    if modo == ProjectMode.PROJECT:
        nombre = raiz.name if raiz else "desconocido"
        # Intentar leer nombre desde .odev.yaml
        try:
            from odev.core.project import ProjectConfig

            config = ProjectConfig(raiz)
            nombre = config.nombre_proyecto or nombre
        except (FileNotFoundError, Exception):
            pass
        _imprimir_ok(f"Proyecto detectado: {nombre} (modo: {modo.value})")
        return True
    elif modo == ProjectMode.LEGACY:
        nombre = raiz.name if raiz else "desconocido"
        _imprimir_warn(
            f"Proyecto legacy detectado: {nombre} (modo: {modo.value}). "
            "Ejecuta 'odev migrate' para migrar."
        )
        return True
    else:
        _imprimir_info(
            "No se detecto proyecto odev en el directorio actual. "
            "Ejecuta 'odev init' para crear uno."
        )
        return None


def _verificar_env() -> bool | None:
    """Verifica si existe el archivo .env.

    Returns:
        True si existe, False si no, None si no hay proyecto.
    """
    modo, raiz = detect_mode()
    if modo == ProjectMode.NONE or raiz is None:
        _imprimir_info(".env: no se puede verificar sin un proyecto detectado.")
        return None

    ruta_env = raiz / ".env"
    if ruta_env.exists():
        _imprimir_ok(".env existe")
        return True
    else:
        _imprimir_fail(
            ".env no existe. Ejecuta 'odev init' para generar la configuracion."
        )
        return False


def _verificar_docker_compose_file() -> bool | None:
    """Verifica si existe docker-compose.yml.

    Returns:
        True si existe, False si no, None si no hay proyecto.
    """
    modo, raiz = detect_mode()
    if modo == ProjectMode.NONE or raiz is None:
        _imprimir_info(
            "docker-compose.yml: no se puede verificar sin un proyecto detectado."
        )
        return None

    ruta_compose = raiz / "docker-compose.yml"
    if ruta_compose.exists():
        _imprimir_ok("docker-compose.yml existe")
        return True
    else:
        _imprimir_fail(
            "docker-compose.yml no existe. "
            "Ejecuta 'odev init' para generar la configuracion."
        )
        return False


def _verificar_odoo_conf() -> bool | None:
    """Verifica si existe config/odoo.conf.

    Returns:
        True si existe, None en otros casos (es WARN, no FAIL).
    """
    modo, raiz = detect_mode()
    if modo == ProjectMode.NONE or raiz is None:
        _imprimir_info(
            "config/odoo.conf: no se puede verificar sin un proyecto detectado."
        )
        return None

    ruta_conf = raiz / "config" / "odoo.conf"
    if ruta_conf.exists():
        _imprimir_ok("config/odoo.conf existe")
        return True
    else:
        _imprimir_warn(
            "config/odoo.conf no existe (se regenerara automaticamente con 'odev up')."
        )
        return None


def _verificar_addons() -> bool | None:
    """Verifica el estado de los directorios de addons.

    Usa el resolver unificado para obtener todos los directorios de addons
    configurados y verificar su existencia y contenido.

    Returns:
        True si tiene modulos, None si es informativo.
    """
    modo, raiz = detect_mode()
    if modo == ProjectMode.NONE or raiz is None:
        _imprimir_info(
            "addons/: no se puede verificar sin un proyecto detectado."
        )
        return None

    # Intentar usar el resolver para obtener todos los addons_dirs
    try:
        from odev.commands._helpers import obtener_rutas, requerir_proyecto
        from odev.main import obtener_nombre_proyecto

        contexto = requerir_proyecto(obtener_nombre_proyecto())
        rutas = obtener_rutas(contexto)
        directorios_addons = rutas.addons_dirs
    except SystemExit:
        # Fallback a directorio por defecto si no se puede resolver
        directorios_addons = [raiz / "addons"]

    cantidad_total = 0
    for directorio_addons in directorios_addons:
        if not directorio_addons.exists():
            _imprimir_info(
                f"{directorio_addons} no existe. Se creara al ejecutar 'odev scaffold' o 'odev init'."
            )
            continue

        # Contar modulos (subdirectorios con __manifest__.py)
        cantidad = 0
        for subdirectorio in directorio_addons.iterdir():
            if subdirectorio.is_dir() and (subdirectorio / "__manifest__.py").exists():
                cantidad += 1
        cantidad_total += cantidad
        _imprimir_info(f"{directorio_addons.name}/ tiene {cantidad} modulo(s)")

    if cantidad_total == 0 and not any(d.exists() for d in directorios_addons):
        return None
    return True


def _verificar_puertos() -> bool:
    """Verifica la disponibilidad de los puertos configurados.

    Lee los puertos del .env del proyecto y verifica si estan libres.

    Returns:
        True si todos los puertos estan disponibles, False si alguno esta ocupado.
    """
    modo, raiz = detect_mode()
    if modo == ProjectMode.NONE or raiz is None:
        _imprimir_info(
            "Puertos: no se puede verificar sin un proyecto detectado."
        )
        return True

    # Intentar leer puertos del .env
    ruta_env = raiz / ".env"
    if not ruta_env.exists():
        _imprimir_info("Puertos: no se puede verificar sin archivo .env.")
        return True

    from odev.core.config import load_env

    valores_env = load_env(ruta_env)

    # Puertos a verificar con sus nombres descriptivos
    puertos_a_verificar = {
        "WEB_PORT": "Odoo",
        "DB_PORT": "PostgreSQL",
        "PGWEB_PORT": "pgweb",
        "DEBUGPY_PORT": "debugpy",
    }

    todos_disponibles = True
    for clave_env, nombre_servicio in puertos_a_verificar.items():
        valor_puerto = valores_env.get(clave_env)
        if valor_puerto is None:
            continue

        try:
            puerto = int(valor_puerto)
        except (ValueError, TypeError):
            continue

        if _puerto_disponible(puerto):
            _imprimir_ok(f"Puerto {puerto} ({nombre_servicio}) disponible")
        else:
            _imprimir_fail(
                f"Puerto {puerto} ({nombre_servicio}) ya esta en uso por otro proceso."
            )
            todos_disponibles = False

    return todos_disponibles


def _puerto_disponible(puerto: int) -> bool:
    """Verifica si un puerto TCP esta disponible para escuchar.

    Args:
        puerto: Numero de puerto a verificar.

    Returns:
        True si el puerto esta libre, False si esta en uso.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", puerto))
            return True
        except OSError:
            return False


def _verificar_version_compatible() -> bool | None:
    """Verifica compatibilidad de version entre el CLI y el proyecto.

    Lee odev_min_version de .odev.yaml y compara con la version instalada.

    Returns:
        True si es compatible, False si no, None si no aplica.
    """
    modo, raiz = detect_mode()
    if modo == ProjectMode.NONE or raiz is None:
        _imprimir_info(f"odev version {__version__}")
        return None

    if modo == ProjectMode.LEGACY:
        _imprimir_info(f"odev version {__version__} (proyecto legacy, sin verificacion de version)")
        return None

    # Intentar leer la version minima del .odev.yaml
    ruta_yaml = raiz / ".odev.yaml"
    if not ruta_yaml.exists():
        _imprimir_info(f"odev version {__version__} (sin .odev.yaml para verificar)")
        return None

    try:
        from packaging.version import Version

        from odev.core.project import ProjectConfig

        config = ProjectConfig(raiz)
        version_minima = config.version_minima
        version_cli = Version(__version__)
        version_requerida = Version(version_minima)

        if version_cli >= version_requerida:
            _imprimir_ok(
                f"odev version {__version__} "
                f"(minimo requerido: {version_minima})"
            )
            return True
        else:
            _imprimir_warn(
                f"odev version {__version__} es menor a la requerida "
                f"por este proyecto ({version_minima}). "
                "Ejecuta: pip install --upgrade git+https://github.com/giulianoh92/odev.git"
            )
            return False
    except (FileNotFoundError, Exception) as exc:
        _imprimir_warn(
            f"odev version {__version__} "
            f"(no se pudo verificar compatibilidad: {exc})"
        )
        return None
