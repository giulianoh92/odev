"""Neutralizacion de base de datos para entornos de desarrollo.

Proporciona funciones compartidas para neutralizar una base de datos Odoo,
desactivando crons, servidores de correo, y configurando parametros seguros
para desarrollo local. Usado por los comandos load-backup y reset-db.
"""

from __future__ import annotations

import re

from odev.core.console import info, success
from odev.core.docker import USUARIO_ODOO, DockerCompose

_PATRON_NOMBRE_BD = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_.-]*$")
_PATRON_PUERTO = re.compile(r"^\d+$")

# report.url la consume wkhtmltopdf DENTRO del contenedor web, donde Odoo
# escucha siempre en el 8069 interno (el compose publica ${WEB_PORT}:8069).
# Con el puerto del host los PDF salen sin estilos cuando WEB_PORT != 8069:
# wkhtmltopdf no puede bajar los bundles CSS (ConnectionRefusedError).
URL_REPORTES_INTERNA = "http://127.0.0.1:8069"

# Servicio mailhog del docker-compose generado por odev: el contenedor web
# lo alcanza por nombre de servicio en la red interna, puerto SMTP 1025
# (el puerto publicado MAILHOG_PORT es solo la UI web).
CORREO_MAILHOG_HOST = "mailhog"
CORREO_MAILHOG_PUERTO = 1025
CORREO_MAILHOG_NOMBRE = "MailHog (odev)"


def _validar_nombre_bd(nombre: str) -> None:
    """Valida que el nombre de base de datos sea seguro para uso en comandos.

    Argumentos:
        nombre: Nombre de la base de datos a validar.

    Lanza:
        ValueError: Si el nombre contiene caracteres no permitidos.
    """
    if not _PATRON_NOMBRE_BD.match(nombre):
        raise ValueError(
            f"Nombre de base de datos invalido: '{nombre}'. "
            "Solo se permiten letras, numeros, guiones, puntos y guiones bajos."
        )


def _validar_puerto(puerto: str) -> None:
    """Valida que el puerto sea un numero valido.

    Argumentos:
        puerto: Puerto como string a validar.

    Lanza:
        ValueError: Si el puerto no es un numero o esta fuera de rango.
    """
    if not _PATRON_PUERTO.match(puerto):
        raise ValueError(f"Puerto invalido: '{puerto}'. Debe ser un numero.")
    numero = int(puerto)
    if not (1 <= numero <= 65535):
        raise ValueError(f"Puerto fuera de rango: {numero}. Debe estar entre 1 y 65535.")


def neutralizar_base_datos(
    dc: DockerCompose,
    nombre_bd: str,
    usuario_bd: str,
) -> None:
    """Ejecuta la neutralizacion de Odoo sobre la base de datos.

    Usa el comando 'odoo neutralize' del contenedor web para desactivar
    crons, servidores de correo y otros componentes peligrosos en
    entornos de desarrollo.

    Argumentos:
        dc: Instancia de DockerCompose configurada para el proyecto.
        nombre_bd: Nombre de la base de datos a neutralizar.
        usuario_bd: Usuario de la base de datos.
    """
    _validar_nombre_bd(nombre_bd)
    info("Neutralizando base de datos (desactivando crons, servidores de correo, etc.)...")
    dc.exec_cmd(
        "web",
        [
            "odoo",
            "neutralize",
            "--config=/etc/odoo/odoo.conf",
            "-d",
            nombre_bd,
        ],
        interactive=True,
        user=USUARIO_ODOO,
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

    Argumentos:
        dc: Instancia de DockerCompose configurada para el proyecto.
        nombre_bd: Nombre de la base de datos.
        usuario_bd: Usuario de la base de datos.
    """
    _validar_nombre_bd(nombre_bd)
    info("Reseteando credenciales de admin (admin/admin)...")
    resultado_hash = dc.exec_cmd(
        "web",
        [
            "python3",
            "-c",
            "from passlib.context import CryptContext; "
            "print(CryptContext(['pbkdf2_sha512']).hash('admin'))",
        ],
    )
    hash_pw = resultado_hash.stdout.decode().strip()
    # Escapar comillas simples en el hash para prevenir inyeccion SQL
    hash_pw_safe = hash_pw.replace("'", "''")
    dc.exec_cmd(
        "db",
        [
            "psql",
            "-U",
            usuario_bd,
            "-d",
            nombre_bd,
            "-c",
            f"UPDATE res_users SET login = 'admin', password = '{hash_pw_safe}' WHERE id = 2;",
        ],
    )
    success("Credenciales de admin reseteadas: login=admin, password=admin")


def configurar_parametros_desarrollo(
    dc: DockerCompose,
    nombre_bd: str,
    usuario_bd: str,
    puerto_web: str = "8069",
) -> None:
    """Configura parametros del sistema para entorno de desarrollo.

    Establece web.base.url apuntando a localhost en el puerto publicado del
    host, report.url apuntando al puerto interno del contenedor, y desactiva
    web.base.url.freeze para evitar que Odoo sobreescriba la URL base con un
    dominio de produccion.

    Argumentos:
        dc: Instancia de DockerCompose configurada para el proyecto.
        nombre_bd: Nombre de la base de datos.
        usuario_bd: Usuario de la base de datos.
        puerto_web: Puerto web publicado en el host (por defecto 8069).
    """
    _validar_nombre_bd(nombre_bd)
    _validar_puerto(puerto_web)
    url_local = f"http://localhost:{puerto_web}"
    url_reportes = URL_REPORTES_INTERNA
    sql = (
        "INSERT INTO ir_config_parameter "
        "(key, value, create_uid, create_date, write_uid, write_date) "
        "VALUES "
        f"('web.base.url', '{url_local}', 1, NOW(), 1, NOW()), "
        f"('report.url', '{url_reportes}', 1, NOW(), 1, NOW()), "
        "('web.base.url.freeze', 'False', 1, NOW(), 1, NOW()) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, write_date = NOW();"
    )
    info("Configurando parametros de desarrollo (web.base.url, report.url)...")
    dc.exec_cmd(
        "db",
        ["psql", "-U", usuario_bd, "-d", nombre_bd, "-c", sql],
    )
    success("Parametros de desarrollo configurados.")


def configurar_servidor_correo_mailhog(
    dc: DockerCompose,
    nombre_bd: str,
    usuario_bd: str,
) -> None:
    """Deja MailHog como unico servidor de correo saliente activo.

    Desactiva cualquier otro ir_mail_server (por ejemplo los que vienen en
    un backup de produccion) y crea o actualiza el registro 'MailHog (odev)'
    apuntando al servicio mailhog del compose. Idempotente: correr varias
    veces produce el mismo estado.

    Argumentos:
        dc: Instancia de DockerCompose configurada para el proyecto.
        nombre_bd: Nombre de la base de datos.
        usuario_bd: Usuario de la base de datos.
    """
    _validar_nombre_bd(nombre_bd)
    sql = (
        f"UPDATE ir_mail_server SET active = false "
        f"WHERE name <> '{CORREO_MAILHOG_NOMBRE}'; "
        f"INSERT INTO ir_mail_server "
        f"(name, smtp_host, smtp_port, smtp_encryption, smtp_authentication, "
        f"active, sequence, create_uid, create_date, write_uid, write_date) "
        f"SELECT '{CORREO_MAILHOG_NOMBRE}', '{CORREO_MAILHOG_HOST}', "
        f"{CORREO_MAILHOG_PUERTO}, 'none', 'login', true, 1, 1, NOW(), 1, NOW() "
        f"WHERE NOT EXISTS "
        f"(SELECT 1 FROM ir_mail_server WHERE name = '{CORREO_MAILHOG_NOMBRE}'); "
        f"UPDATE ir_mail_server SET smtp_host = '{CORREO_MAILHOG_HOST}', "
        f"smtp_port = {CORREO_MAILHOG_PUERTO}, smtp_encryption = 'none', "
        f"smtp_authentication = 'login', active = true, write_date = NOW() "
        f"WHERE name = '{CORREO_MAILHOG_NOMBRE}';"
    )
    info("Configurando MailHog como servidor de correo saliente...")
    dc.exec_cmd(
        "db",
        ["psql", "-U", usuario_bd, "-d", nombre_bd, "-c", sql],
    )
    success(f"Servidor de correo: {CORREO_MAILHOG_HOST}:{CORREO_MAILHOG_PUERTO} (MailHog).")


def esperar_base_lista(
    dc: DockerCompose,
    nombre_bd: str,
    usuario_bd: str,
    intentos: int = 60,
    intervalo: int = 5,
) -> bool:
    """Espera a que la base tenga esquema de Odoo, sin abortar el comando.

    `docker compose up` retorna en cuanto los contenedores arrancan, pero Odoo
    crea la base e instala `base` recien despues — segundos en el mejor caso,
    minutos cuando el entrypoint todavia esta instalando requirements de los
    addons. Consultar la configuracion antes de eso devuelve un fallo de psql
    que no significa "no hay nada que hacer" sino "todavia no se puede saber".

    A diferencia del sondeo de reset-db, esta funcion NO lanza typer.Exit: el
    caller decide si avisa, reintenta o sigue.

    Argumentos:
        dc: Instancia de DockerCompose configurada para el proyecto.
        nombre_bd: Nombre de la base de datos.
        usuario_bd: Usuario de la base de datos.
        intentos: Numero maximo de sondeos.
        intervalo: Segundos entre sondeos.

    Retorna:
        True si la base quedo lista, False si se agotaron los intentos.

    Lanza:
        ValueError: Si el nombre de base es invalido.
    """
    import time

    _validar_nombre_bd(nombre_bd)
    sql_check = (
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_name = 'ir_config_parameter');"
    )
    for i in range(intentos):
        stdout, _stderr, codigo = dc.exec_capture(
            "db",
            ["psql", "-U", usuario_bd, "-d", nombre_bd, "-tAc", sql_check],
        )
        if codigo == 0 and stdout.decode(errors="replace").strip() == "t":
            return True
        if i < intentos - 1:
            info(f"  Esperando inicializacion de '{nombre_bd}'... ({i + 1}/{intentos})")
            time.sleep(intervalo)
    return False


def asegurar_entorno_desarrollo(
    dc: DockerCompose,
    nombre_bd: str,
    usuario_bd: str,
    puerto_web: str = "8069",
    esperar: bool = False,
    intentos: int = 60,
    intervalo: int = 5,
) -> str:
    """Verifica y aplica parametros de desarrollo y MailHog si hace falta.

    Pensado para comandos que no crean la base (odev up): primero consulta el
    estado actual y solo escribe si algo difiere, para no invalidar caches de
    Odoo sin necesidad. Si la base todavia no esta inicializada (sin esquema
    de Odoo), no hace nada.

    Argumentos:
        dc: Instancia de DockerCompose configurada para el proyecto.
        nombre_bd: Nombre de la base de datos.
        usuario_bd: Usuario de la base de datos.
        puerto_web: Puerto web publicado en el host.
        esperar: Si True y la base no responde, espera a que Odoo la cree
            antes de decidir. Necesario en `odev up`, donde la base nace
            despues de que `docker compose up` retorna.
        intentos: Sondeos maximos de la espera.
        intervalo: Segundos entre sondeos.

    Retorna:
        'omitido' si la base no esta lista, 'sin_cambios' si ya estaba
        todo configurado, 'aplicado' si hubo que escribir cambios.
    """
    _validar_nombre_bd(nombre_bd)
    _validar_puerto(puerto_web)
    url_local = f"http://localhost:{puerto_web}"
    sql_estado = (
        "SELECT COALESCE((SELECT value FROM ir_config_parameter "
        "WHERE key = 'report.url'), '') || '|' || "
        "COALESCE((SELECT value FROM ir_config_parameter "
        "WHERE key = 'web.base.url'), '') || '|' || "
        "(SELECT COUNT(*) FROM ir_mail_server "
        f"WHERE active AND name <> '{CORREO_MAILHOG_NOMBRE}')::text || '|' || "
        "(SELECT COUNT(*) FROM ir_mail_server "
        f"WHERE name = '{CORREO_MAILHOG_NOMBRE}' AND active "
        f"AND smtp_host = '{CORREO_MAILHOG_HOST}' "
        f"AND smtp_port = {CORREO_MAILHOG_PUERTO})::text;"
    )
    stdout, _stderr, codigo = dc.exec_capture(
        "db",
        ["psql", "-U", usuario_bd, "-d", nombre_bd, "-tAc", sql_estado],
    )
    if codigo != 0 and esperar:
        # La base todavia no existe: Odoo la crea despues de `compose up`.
        # Esperarla es lo que convierte la garantia en garantia.
        if not esperar_base_lista(dc, nombre_bd, usuario_bd, intentos, intervalo):
            return "omitido"
        stdout, _stderr, codigo = dc.exec_capture(
            "db",
            ["psql", "-U", usuario_bd, "-d", nombre_bd, "-tAc", sql_estado],
        )
    if codigo != 0:
        return "omitido"
    estado = stdout.decode().strip()
    if estado == f"{URL_REPORTES_INTERNA}|{url_local}|0|1":
        return "sin_cambios"
    configurar_parametros_desarrollo(dc, nombre_bd, usuario_bd, puerto_web)
    configurar_servidor_correo_mailhog(dc, nombre_bd, usuario_bd)
    return "aplicado"
