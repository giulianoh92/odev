"""Neutralizacion de base de datos para entornos de desarrollo.

Proporciona funciones compartidas para neutralizar una base de datos Odoo,
desactivando crons, servidores de correo, y configurando parametros seguros
para desarrollo local. Usado por los comandos load-backup y reset-db.
"""

from __future__ import annotations

from odev.core.console import info, success
from odev.core.docker import DockerCompose


def neutralizar_base_datos(
    dc: DockerCompose,
    nombre_bd: str,
    usuario_bd: str,
) -> None:
    """Ejecuta la neutralizacion de Odoo sobre la base de datos.

    Usa el comando 'odoo neutralize' del contenedor web para desactivar
    crons, servidores de correo y otros componentes peligrosos en
    entornos de desarrollo.

    Args:
        dc: Instancia de DockerCompose configurada para el proyecto.
        nombre_bd: Nombre de la base de datos a neutralizar.
        usuario_bd: Usuario de la base de datos.
    """
    info("Neutralizando base de datos (desactivando crons, servidores de correo, etc.)...")
    dc.exec_cmd(
        "web",
        [
            "odoo", "neutralize",
            "--config=/etc/odoo/odoo.conf",
            "-d", nombre_bd,
        ],
        interactive=True,
    )
    success("Base de datos neutralizada.")


def resetear_credenciales_admin(
    dc: DockerCompose,
    nombre_bd: str,
    usuario_bd: str,
) -> None:
    """Resetea las credenciales del usuario admin a admin/admin.

    Genera un hash seguro de la password 'admin' usando passlib dentro
    del contenedor web, y actualiza el usuario con id=2 (admin por
    convencion de Odoo).

    Args:
        dc: Instancia de DockerCompose configurada para el proyecto.
        nombre_bd: Nombre de la base de datos.
        usuario_bd: Usuario de la base de datos.
    """
    info("Reseteando credenciales de admin (admin/admin)...")
    resultado_hash = dc.exec_cmd(
        "web",
        [
            "python3", "-c",
            "from passlib.context import CryptContext; "
            "print(CryptContext(['pbkdf2_sha512']).hash('admin'))",
        ],
    )
    hash_pw = resultado_hash.stdout.decode().strip()
    dc.exec_cmd(
        "db",
        ["psql", "-U", usuario_bd, "-d", nombre_bd, "-c",
         f"UPDATE res_users SET login = 'admin', password = '{hash_pw}' WHERE id = 2;"],
    )
    success("Credenciales de admin reseteadas: login=admin, password=admin")


def configurar_parametros_desarrollo(
    dc: DockerCompose,
    nombre_bd: str,
    usuario_bd: str,
    puerto_web: str = "8069",
) -> None:
    """Configura parametros del sistema para entorno de desarrollo.

    Establece web.base.url y report.url apuntando a localhost,
    y desactiva web.base.url.freeze para evitar que Odoo sobreescriba
    la URL base con un dominio de produccion.

    Args:
        dc: Instancia de DockerCompose configurada para el proyecto.
        nombre_bd: Nombre de la base de datos.
        usuario_bd: Usuario de la base de datos.
        puerto_web: Puerto web local (por defecto 8069).
    """
    url_local = f"http://localhost:{puerto_web}"
    sql = (
        "INSERT INTO ir_config_parameter (key, value, create_uid, create_date, write_uid, write_date) "
        "VALUES "
        f"('web.base.url', '{url_local}', 1, NOW(), 1, NOW()), "
        f"('report.url', '{url_local}', 1, NOW(), 1, NOW()), "
        "('web.base.url.freeze', 'False', 1, NOW(), 1, NOW()) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, write_date = NOW();"
    )
    info("Configurando parametros de desarrollo (web.base.url, report.url)...")
    dc.exec_cmd(
        "db",
        ["psql", "-U", usuario_bd, "-d", nombre_bd, "-c", sql],
    )
    success("Parametros de desarrollo configurados.")
