"""Comando 'reset-db': destruye la base de datos y volumenes, reinicia desde cero.

Ejecuta docker compose down -v para eliminar contenedores y volumenes,
luego levanta el entorno nuevamente para empezar con una base de datos limpia.
Opcionalmente neutraliza la base de datos y configura parametros de desarrollo.
"""

import typer

from odev.commands._helpers import obtener_docker, obtener_rutas, requerir_proyecto
from odev.core.config import load_env
from odev.core.console import info, success, warning
from odev.core.neutralize import (
    configurar_parametros_desarrollo,
    neutralizar_base_datos,
    resetear_credenciales_admin,
)


def reset_db(
    neutralize: bool = typer.Option(
        True,
        help="Neutralizar la base de datos despues de reiniciar (desactivar crons, correo, etc.).",
    ),
    yes: bool = typer.Option(
        False,
        "--yes", "-y",
        help="Skip confirmation prompt (for automation/CI).",
    ),
) -> None:
    """Destruye la base de datos y volumenes, luego reinicia el entorno desde cero.

    Pide confirmacion antes de proceder ya que esta operacion es destructiva
    e irreversible. Elimina todos los volumenes de datos incluyendo la
    base de datos y el filestore.

    Tras reiniciar, opcionalmente neutraliza la base de datos y configura
    parametros seguros para desarrollo (web.base.url, report.url, credenciales
    de admin).
    """
    from odev.main import obtener_nombre_proyecto
    contexto = requerir_proyecto(obtener_nombre_proyecto())

    warning("Esto ELIMINARA la base de datos y TODOS los datos!")
    if not yes:
        confirmacion = typer.confirm("Estas seguro?", default=False)
        if not confirmacion:
            info("Operacion cancelada.")
            raise typer.Exit()

    rutas = obtener_rutas(contexto)
    valores_env = load_env(rutas.env_file)
    usuario_bd = valores_env.get("DB_USER", "odoo")
    nombre_bd = valores_env.get("DB_NAME", "odoo_db")
    puerto_web = valores_env.get("WEB_PORT", "8069")

    dc = obtener_docker(contexto)

    info("Deteniendo contenedores y eliminando volumenes...")
    dc.down(volumes=True)

    info("Iniciando entorno limpio...")
    dc.up()

    if neutralize:
        info("Esperando a que Odoo inicialice la base de datos...")
        _esperar_base_datos_lista(dc, nombre_bd, usuario_bd)

        neutralizar_base_datos(dc, nombre_bd, usuario_bd)
        resetear_credenciales_admin(dc, nombre_bd, usuario_bd)
        configurar_parametros_desarrollo(dc, nombre_bd, usuario_bd, puerto_web)

        info("Reiniciando servicios tras neutralizacion...")
        dc.restart("web")

    success(
        f"Base de datos reiniciada y configurada para desarrollo. "
        f"Acceder en http://localhost:{puerto_web}"
    )


def _esperar_base_datos_lista(
    dc: "DockerCompose",  # noqa: F821
    nombre_bd: str,
    usuario_bd: str,
    intentos: int = 30,
    intervalo: int = 5,
) -> None:
    """Espera hasta que la base de datos tenga la tabla ir_config_parameter.

    Cuando Odoo inicia con una base de datos vacia, necesita tiempo para
    instalar el modulo base y crear las tablas. Esta funcion espera hasta
    que la tabla ir_config_parameter exista, lo que indica que el modulo
    base ya fue instalado y la base de datos esta lista para ser
    neutralizada.

    Args:
        dc: Instancia de DockerCompose configurada para el proyecto.
        nombre_bd: Nombre de la base de datos.
        usuario_bd: Usuario de la base de datos.
        intentos: Numero maximo de intentos (por defecto 30).
        intervalo: Segundos entre cada intento (por defecto 5).

    Raises:
        typer.Exit: Si la base de datos no esta lista despues de todos los intentos.
    """
    import time

    from odev.core.console import error

    sql_check = (
        "SELECT EXISTS ("
        "  SELECT 1 FROM information_schema.tables "
        "  WHERE table_name = 'ir_config_parameter'"
        ");"
    )

    for i in range(intentos):
        try:
            resultado = dc.exec_cmd(
                "db",
                ["psql", "-U", usuario_bd, "-d", nombre_bd, "-tAc", sql_check],
            )
            salida = resultado.stdout.decode().strip() if resultado.stdout else ""
            if salida == "t":
                info("Base de datos lista.")
                return
        except Exception:
            pass  # El contenedor de BD puede no estar listo aun

        if i < intentos - 1:
            info(f"  Esperando inicializacion... ({i + 1}/{intentos})")
            time.sleep(intervalo)

    error(
        f"La base de datos no se inicializo despues de {intentos * intervalo} segundos. "
        "Verifica los logs con 'odev logs web'."
    )
    raise typer.Exit(1)
