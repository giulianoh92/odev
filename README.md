# odev

**Toolkit CLI para entornos de desarrollo Odoo basados en Docker.**

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License MIT](https://img.shields.io/badge/license-MIT-green)
![PyPI](https://img.shields.io/badge/pypi-odev-orange)

## Que es odev?

odev es un toolkit de linea de comandos que provee un entorno de desarrollo Odoo completo, basado en Docker. Cada proyecto es totalmente independiente con su propia configuracion, base de datos, puertos y stack de Docker Compose. Instala odev una vez de forma global y despues crea tantos proyectos aislados como necesites.

## Inicio Rapido

```bash
pip install git+https://github.com/relexsrl/odev
```

### Proyecto nuevo

```bash
odev init mi-proyecto
cd mi-proyecto
odev up
# Abrir http://localhost:8069
```

El comando `init` ejecuta un wizard interactivo que te permite elegir la version de Odoo (17.0, 18.0, 19.0), credenciales de base de datos, puertos y funcionalidades opcionales como addons Enterprise, pgweb, debugpy y GitHub Actions CI.

Para una configuracion no interactiva con valores por defecto razonables:

```bash
odev init mi-proyecto --no-interactive
```

### Proyecto existente

Si ya tenes un repositorio con modulos Odoo:

```bash
cd mi-repo-odoo
odev adopt
odev up
```

El comando `adopt` detecta automaticamente el layout del repositorio (modulo unico, multi-addon, Odoo.sh), configura el entorno Docker y registra el proyecto en el registro global de odev.

## Funcionalidades

- **Configuracion en un comando** -- `odev init` genera un proyecto completo con Docker Compose, configuracion de Odoo, `.env`, `.gitignore`, hooks de pre-commit y pipeline CI opcional
- **Adopcion de proyectos existentes** -- `odev adopt` detecta el layout de un repositorio Odoo existente y lo configura para usar odev
- **Hot-reload** -- Odoo corre en modo dev; los cambios en XML, QWeb y JS se detectan automaticamente
- **Snapshots de base de datos** -- Guarda y restaura el estado de la base de datos en cualquier momento con `odev db snapshot` / `odev db restore`
- **Scaffolding de modulos** -- `odev scaffold` genera un esqueleto completo de modulo Odoo (modelos, vistas, seguridad, tests)
- **Soporte multi-proyecto** -- Deteccion automatica de puertos para que multiples proyectos puedan correr simultaneamente sin conflictos. `odev projects` permite listar, eliminar y limpiar proyectos registrados
- **TUI interactiva** -- Dashboard de terminal con estado de servicios en vivo, streaming de logs y atajos de teclado
- **Carga de backups externos** -- Importa backups `.zip` de Odoo.sh o Database Manager con neutralizacion automatica
- **Anonimizacion de datos** -- Elimina datos personales de copias de bases de datos de produccion para desarrollo seguro
- **Generacion de contexto del proyecto** -- Genera un `PROJECT_CONTEXT.md` con analisis de modulos para asistentes de IA
- **Migracion legacy** -- Migra del layout viejo `odoo-dev-env` a proyectos independientes
- **Diagnostico del entorno** -- `odev doctor` verifica Docker, Compose, puertos, archivos de configuracion y compatibilidad de versiones
- **MCP server (0.5.2+)** -- `odev mcp serve` expone odev como servidor MCP consumible por Claude Code, Cursor y otros clientes. 9 tools, 4 resources, 3 prompts. Install via `pipx install 'odev[mcp]'`. Ver seccion [Servidor MCP](#servidor-mcp).
- **Salida JSON estructurada (0.5.0+)** -- Todos los comandos agent-relevant (`status`, `doctor`, `logs`, `modules`, `sql`, `model-info`, `test`, `py`, `context`) emiten JSON con `--json` para parsing programatico.
- **Auto-actualizacion** -- `odev self-update` actualiza a la ultima version via pip

## Servidor MCP

Desde 0.5.2, odev expone todas sus operaciones agent-relevant como servidor MCP (Model Context Protocol). Esto permite que Claude Code, Cursor y otros clientes MCP invoquen odev sin parsear salida CLI.

### Instalacion

El servidor MCP es una dependencia opcional. Instalalo con el extra `[mcp]`:

```bash
# Local editable install con MCP
pipx install --force '/path/to/odev[mcp]'

# Desde git con MCP
pipx install 'odev[mcp] @ git+https://github.com/giulianoh92/odev.git'
```

Sin el extra, `odev mcp serve` sale con exit 2 y muestra el hint de instalacion.

### Configuracion en Claude Code

```bash
claude mcp add -s user odev -- odev mcp serve --transport stdio
```

Esto registra el servidor user-scope (disponible en cualquier proyecto). `claude mcp list` debe mostrar `odev: ... - ✓ Connected`.

Para configuracion manual, agregar a `~/.claude.json`:

```json
{
  "mcpServers": {
    "odev": {
      "command": "odev",
      "args": ["mcp", "serve", "--transport", "stdio"]
    }
  }
}
```

#### Configuracion con proyecto fijo (ODEV_PROJECT)

Cuando el servidor MCP arranca desde un directorio que no pertenece a ningun proyecto
(por ejemplo, en la configuracion user-scope de Claude Code), la resolucion de contexto
puede fallar porque no encuentra un `.odev.yaml` en el cwd.

Para fijar el proyecto sin usar `--project` en el comando de arranque, usa la variable
de entorno `ODEV_PROJECT`:

```json
{
  "mcpServers": {
    "odev": {
      "command": "odev",
      "args": ["mcp", "serve", "--transport", "stdio"],
      "env": {
        "ODEV_PROJECT": "sis-odoo"
      }
    }
  }
}
```

Orden de resolucion del proyecto (de mayor a menor prioridad):
1. Flag `--project` en `odev mcp serve` (raramente usado en MCP)
2. Variable de entorno `ODEV_PROJECT`
3. Busqueda desde el cwd del servidor (comportamiento previo, sin cambios)

Si `ODEV_PROJECT` no esta definido y el cwd no pertenece a ningun proyecto, los tools
MCP retornan un error estructurado de tipo `"No odev project found"`.

### Configuracion en Cursor (HTTP transport)

```bash
odev mcp serve --transport http --port 3333
```

### Tools expuestos (9)

| Tool | Equivale a |
|---|---|
| `odev_status` | `odev status --json` |
| `odev_shell` | `odev shell <svc> -c "<cmd>"` |
| `odev_sql` | `odev sql --json "<query>"` |
| `odev_py` | `odev py "<expr>"` (banner stripped) |
| `odev_test` | `odev test <m1,m2> --json` |
| `odev_logs` | `odev logs <svc> --json` (snapshot) |
| `odev_doctor` | `odev doctor --json` |
| `odev_model_info` | `odev model-info <model>` |
| `odev_modules` | `odev modules --json` |

### Resources expuestos (4)

| URI | Contenido |
|---|---|
| `odev://project/context` | Markdown auto-generado del contexto del proyecto |
| `odev://project/config` | `.odev.yaml` parseado como JSON |
| `odev://db/schema` | Snapshot de `pg_dump --schema-only` |
| `odev://modules/{name}/manifest` | Manifest del modulo parseado |

### Prompts pre-armados (3)

- `diagnose_failing_test` — Template para diagnosticar tests fallando
- `explain_module` — Template para explicar un modulo Odoo
- `generate_migration` — Template para generar migracion ORM

## Opciones Globales

Las siguientes opciones aplican a todos los comandos y deben pasarse **antes** del subcomando:

| Opcion | Descripcion |
|--------|-------------|
| `--project` / `-p` | Nombre del proyecto cuando hay ambiguedad (multiples proyectos en el mismo directorio) |
| `--version` / `-V` | Muestra la version instalada de odev |
| `--debug` | Activa logging `DEBUG` global — imprime mensajes internos de todos los subsistemas en stderr |

```bash
# Activar debug para diagnosticar problemas
odev --debug up
odev --debug doctor
odev --project mi-proyecto --debug status
```

## Referencia de Comandos

### Referencia Rapida

| Comando | Descripcion |
|---------|-------------|
| `odev init [nombre]` | Crear un nuevo proyecto Odoo |
| `odev adopt [directorio]` | Adoptar un proyecto Odoo existente |
| `odev up` | Levantar el entorno de desarrollo |
| `odev down` | Detener y eliminar contenedores |
| `odev restart [servicio]` | Reiniciar un servicio (default: web) |
| `odev status` | Ver estado de los servicios |
| `odev logs [servicio]` | Ver logs de un servicio |
| `odev shell [servicio]` | Abrir terminal en un contenedor |
| `odev shell <svc> -c "<cmd>"` | Ejecutar comando bash no-interactivo |
| `odev sql <query>` | Ejecutar SQL en el contenedor db |
| `odev py <expresion>` | Evaluar expresion Python en odoo shell |
| `odev scaffold <nombre>` | Crear un nuevo modulo Odoo |
| `odev addon-install <modulo(s)>` | Instalar modulo(s) — CSV soportado: `m1,m2` |
| `odev update <modulo(s)>` | Actualizar modulo(s) — CSV soportado: `m1,m2` |
| `odev test <modulo(s)>` | Ejecutar tests — CSV soportado: `m1,m2` |
| `odev db snapshot <nombre>` | Crear snapshot de la base de datos |
| `odev db restore <nombre>` | Restaurar un snapshot |
| `odev db list` | Listar snapshots disponibles |
| `odev db anonymize` | Anonimizar datos personales |
| `odev load-backup <archivo>` | Cargar backup de Odoo.sh |
| `odev reset-db` | Destruir y recrear la base de datos |
| `odev context` | Generar PROJECT_CONTEXT.md para IA |
| `odev doctor` | Diagnosticar el entorno |
| `odev tui` | Dashboard interactivo |
| `odev projects` | Listar proyectos registrados (tabla Rich) |
| `odev projects list` | Listar proyectos registrados (subcomando explicito) |
| `odev projects list --json` | Listar proyectos como JSON estructurado |
| `odev migrate` | Migrar proyecto legacy |
| `odev mcp serve` | Iniciar servidor MCP (requiere `[mcp]` extra) |
| `odev model-info <model>` | Introspeccion ORM de un modelo (JSON) |
| `odev modules` | Listar modulos instalados (JSON) |
| `odev self-update` | Actualizar odev |

### Comandos Principales

| Comando | Descripcion |
|---------|-------------|
| `odev init [nombre]` | Crear un nuevo proyecto Odoo (wizard interactivo o `--no-interactive`) |
| `odev adopt [directorio]` | Adoptar un proyecto Odoo existente para gestionarlo con odev |
| `odev up` | Iniciar el entorno de desarrollo (`--build` para reconstruir, `--watch` para modo watch) |
| `odev down` | Detener y eliminar contenedores (`-v` para eliminar tambien los volumenes) |
| `odev restart [servicio]` | Reiniciar un servicio del stack Docker (por defecto: `web`) |
| `odev status` | Mostrar tabla de estado de servicios (nombre, estado, salud, puertos) |
| `odev logs [servicio]` | Seguir logs de un servicio (`web`, `db` o `all`; `--tail`, `--no-follow`) |
| `odev shell [servicio]` | Abrir un shell bash interactivo dentro de un contenedor (por defecto: `web`) |
| `odev shell <svc> -c "<cmd>"` | Ejecutar un comando bash no-interactivo en el contenedor |
| `odev sql <query>` | Ejecutar SQL en el contenedor db via psql (`--csv` para salida sin bordes) |
| `odev py <expresion>` | Evaluar expresion Python en odoo shell via stdin |
| `odev test <modulo(s)>` | Ejecutar tests de modulo(s) (CSV: `m1,m2`; `all`; `--log-level`; `--no-validate`) |
| `odev scaffold <nombre>` | Crear un nuevo modulo Odoo desde el template incluido |
| `odev addon-install <modulo(s)>` | Instalar modulo(s) — CSV: `m1,m2`; `--no-validate` |
| `odev update <modulo(s)>` | Actualizar modulo(s) — CSV: `m1,m2`; `--no-validate` |
| `odev reset-db` | Destruir base de datos y volumenes, reiniciar con un entorno limpio |
| `odev load-backup <ruta>` | Cargar un backup de Odoo.sh / Database Manager (`.zip`; `--no-neutralize`) |
| `odev context` | Generar `PROJECT_CONTEXT.md` a partir del analisis de modulos |
| `odev tui` | Lanzar el dashboard interactivo TUI |
| `odev projects` | Gestionar proyectos registrados (listar, eliminar, limpiar) |
| `odev migrate` | Migrar un proyecto legacy `odoo-dev-env` al nuevo formato |
| `odev doctor` | Diagnosticar el entorno de desarrollo y reportar problemas |
| `odev self-update` | Actualizar odev a la ultima version |

### Subcomandos de Base de Datos (`odev db`)

| Comando | Descripcion |
|---------|-------------|
| `odev db snapshot <nombre>` | Crear un snapshot de la base de datos (pg_dump en formato custom) |
| `odev db restore <nombre>` | Restaurar base de datos desde un snapshot (por nombre o prefijo) |
| `odev db list` | Listar todos los snapshots disponibles con fecha y tamano |
| `odev db anonymize` | Anonimizar datos personales (nombres, emails, telefonos) y resetear passwords |

### `odev adopt [directorio]`

Adopta un proyecto Odoo existente para gestionarlo con odev. Detecta automaticamente
el layout del repositorio (modulo unico, multi-addon, Odoo.sh), configura el entorno
Docker y registra el proyecto en el registro global.

```bash
# Adoptar el directorio actual
odev adopt

# Adoptar un directorio especifico con nombre
odev adopt /path/to/repo --name mi-proyecto --odoo-version 18.0

# Modo no-interactivo
odev adopt . --no-interactive
```

Opciones:
- `--name, -n` — Nombre del proyecto (por defecto: nombre del directorio).
- `--odoo-version` — Version de Odoo (19.0, 18.0, 17.0, 16.0).
- `--no-interactive` — Usar valores por defecto sin preguntar.

### `odev restart [servicio]`

Reinicia un servicio del stack Docker (por defecto: web).

```bash
odev restart        # Reinicia el servicio web
odev restart db     # Reinicia la base de datos
odev restart pgweb  # Reinicia pgweb
```

### `odev shell [servicio]`

Abre una terminal bash dentro de un contenedor (por defecto: web).

```bash
odev shell          # Terminal en el contenedor web (Odoo)
odev shell db       # Terminal en el contenedor de base de datos
```

Con `-c`, ejecuta un comando de forma no-interactiva y propaga el exit code
(util para scripts y pipelines CI/IA):

```bash
odev shell web -c "ls /mnt/extra-addons"
odev shell web -c "python -c 'import odoo; print(odoo.__version__)'"
```

### `odev sql <query> [--csv]`

Ejecuta una sentencia SQL en el contenedor `db` via `psql -c` y propaga stdout/exit code.
Lee `DB_NAME` y `DB_USER` del `.env` del proyecto (defaults: `odoo_db` / `odoo`).

```bash
odev sql "SELECT count(*) FROM res_partner"
odev sql "SELECT id, name FROM res_partner LIMIT 3" --csv
```

El flag `--csv` agrega `-A -t -F','` a psql (salida sin bordes, solo datos, separados por coma).
No es RFC 4180 CSV — campos con comas o comillas no se escapan.

Codigos de salida: `0` exito, `1` error de psql, `2` query vacia.

### `odev py <expresion>`

Evalua una expresion Python en `odoo shell` via stdin (flag `--no-http`) y propaga stdout/exit code.
Lee `DB_NAME` del `.env` del proyecto (default: `odoo_db`).

```bash
odev py "env['res.partner'].search_count([])"
odev py "env['product.template'].search_count([('active', '=', True)])"
```

Caveats:
- El banner de Odoo se elimina automaticamente del stdout desde 0.5.0. Usar `--keep-banner` para conservar la salida raw (debug).
- Side-effects ORM (`.create()`, `.write()`) se commitean. Usar `env.cr.rollback()` si se necesita dry-run.

Codigos de salida: `0` exito, `1` error en odoo shell, `2` expresion vacia.

### `odev projects`

Gestiona los proyectos registrados en el registro global de odev.

```bash
# Listar todos los proyectos registrados
odev projects

# Eliminar un proyecto del registro
odev projects remove mi-proyecto

# Eliminar y borrar la configuracion
odev projects remove mi-proyecto --delete-config

# Limpiar proyectos cuyo directorio ya no existe
odev projects clean
```

### Soporte CSV de Modulos (`update`, `addon-install`, `test`)

Los comandos `update`, `addon-install` y `test` aceptan uno o varios modulos
en un solo token separado por comas. Odoo recibe una unica invocacion, no N
invocaciones secuenciales.

#### Ejemplos basicos

```bash
# Un solo modulo (backward-compatible)
odev update sale
odev addon-install account
odev test crm

# Varios modulos via CSV
odev update sale,stock,crm
odev addon-install sale,account,purchase
odev test sale,crm
```

El argumento debe ser un **unico token de shell**. Si tus modulos tienen espacios
en sus nombres, usa comillas: `odev update "sale,stock"`. No uses espacios
directamente entre modulos (`odev update sale stock` es un error — Typer rechaza
argumentos extra).

#### `odev update <modulos> [--no-validate]`

```bash
# Actualizar multiples modulos en una sola invocacion Odoo
odev update sale,crm,stock

# Saltar la validacion previa (util si el modulo es nuevo o esta fuera del addons-path)
odev update mi_modulo --no-validate

# 'all' sigue funcionando como siempre
odev update all
```

#### `odev addon-install <modulos> [--no-validate]`

```bash
# Instalar varios modulos de una sola vez
odev addon-install sale,account,base_setup

# Saltar validacion
odev addon-install nuevo_modulo --no-validate
```

#### `odev test <modulos> [--no-validate]`

```bash
# Testear multiples modulos: genera -u sale,crm --test-tags /sale,/crm
odev test sale,crm

# Agregar filtro de tag extra (se agrega al final del --test-tags auto-generado)
odev test sale,crm --tags :test_create
# Resultado: --test-tags /sale,/crm,:test_create

# Saltar validacion previa de modulos
odev test sale,crm --no-validate

# 'all' sigue sin filtros de modulo ni de tags
odev test all
```

#### Flag `--no-validate`

Por defecto `update`, `addon-install` y `test` verifican que cada modulo
exista en el `addons-path` del proyecto antes de invocar a Odoo. Si la
verificacion falla, el comando sale con exit code `2` y muestra la lista
completa de modulos no encontrados.

`--no-validate` omite esta verificacion de disco. El parsing del CSV sigue
corriendo (errores de formato como `'all' mezclado con otros modulos` se
reportan igual).

#### Regla `all`

El token `all` solo puede usarse **solo**. Mezclarlo con otros modulos
(`odev update sale,all`) es un error y sale con exit code `2`.

```bash
odev update all       # OK: actualiza todos los modulos
odev update sale,all  # ERROR: exit 2 — 'all' no puede combinarse
```

#### Codigos de salida

| Codigo | Condicion |
|--------|-----------|
| `0` | Exito |
| `2` | Error de uso: modulo(s) no encontrado(s), `all` mezclado, o lista vacia |
| `3` | Error de entorno: puerto ocupado (solo `test`) |

---

## Estructura del Proyecto

Ejecutar `odev init mi-proyecto` genera el siguiente arbol de directorios:

```
mi-proyecto/
├── addons/                  # Tus modulos Odoo custom (trackeados en git)
├── config/
│   └── odoo.conf            # Generado automaticamente desde .env (gitignored)
├── enterprise/              # Addons enterprise (opcional, gitignored)
├── snapshots/               # Snapshots de base de datos (gitignored)
├── logs/                    # Archivos de log de Odoo (gitignored)
├── docs/                    # Documentacion y artefactos SDD
├── docker-compose.yml       # Servicios Docker (Odoo + PostgreSQL + pgweb)
├── entrypoint.sh            # Script de entrada del contenedor
├── .odev.yaml               # Configuracion del proyecto para odev
├── .env                     # Variables de entorno (gitignored)
├── .env.example             # Template de entorno compartible
├── .gitignore               # Ignores pre-configurados
├── .pre-commit-config.yaml  # Hooks de pre-commit (ruff, etc.)
├── pyproject.toml           # Configuracion de herramientas del proyecto
├── CLAUDE.md                # Instrucciones para asistentes de IA
└── .github/
    └── workflows/
        └── ci.yml           # GitHub Actions CI (opcional)
```

## Configuracion

### .odev.yaml

El archivo de configuracion del proyecto que odev usa para detectar y gestionar el proyecto:

```yaml
odev_min_version: "0.1.0"

odoo:
  version: "19.0"
  image: "odoo:19"

database:
  image: "pgvector/pgvector:pg16"

enterprise:
  enabled: false
  path: "./enterprise"

services:
  pgweb: true

project:
  name: "mi-proyecto"
  description: ""
```

### .env

Variables de entorno que controlan el stack Docker. Creadas por `odev init` y gitignoreadas (los secretos quedan locales). Comparti `.env.example` con tu equipo en su lugar.

Variables principales:

| Variable | Default | Proposito |
|----------|---------|-----------|
| `ODOO_VERSION` | `19.0` | Version de Odoo |
| `ODOO_IMAGE_TAG` | `19` | Tag de la imagen Docker para Odoo |
| `DB_IMAGE_TAG` | `16` | Version de PostgreSQL (via imagen pgvector) |
| `WEB_PORT` | `8069` | Puerto web de Odoo |
| `PGWEB_PORT` | `8081` | Puerto de pgweb |
| `DB_NAME` | `odoo_db` | Nombre de la base de datos |
| `DB_USER` | `odoo` | Usuario de la base de datos |
| `LOAD_LANGUAGE` | `en_US` | Idioma a auto-instalar |
| `WITHOUT_DEMO` | `all` | Omitir datos demo (`all` = omitir, vacio = cargar) |
| `DEBUGPY` | `False` | Habilitar depurador remoto en puerto 5678 |

## Soporte Multi-Proyecto

odev asigna atomicamente puertos disponibles al crear un nuevo proyecto. Si el puerto 8069 ya esta en uso (por otro proyecto odev, por ejemplo), `odev init` asigna el siguiente set de puertos disponible:

```
Proyecto A: Odoo en 8069, pgweb en 8081, DB en 5432, debugpy en 5678, Mailhog en 8025
Proyecto B: Odoo en 8070, pgweb en 8082, DB en 5433, debugpy en 5679, Mailhog en 8026
Proyecto C: Odoo en 8071, pgweb en 8083, DB en 5434, debugpy en 5680, Mailhog en 8027
```

Cada proyecto tiene su propio stack de Docker Compose con contenedores y volumenes aislados. Solo ejecuta `odev up` en el directorio de cada proyecto.

Para ver y gestionar todos los proyectos registrados, usa `odev projects`. Ver la seccion [odev projects](#odev-projects) para mas detalles.

## Asignacion de Puertos

### Como funciona (desde 0.4.0)

`odev init` y `odev adopt` usan asignacion atomica de puertos via el registro global (`~/.odev/registry.yaml`). Esto previene colisiones TOCTOU cuando varios wizards corren en paralelo.

Cada proyecto registrado tiene un conjunto de 5 puertos:

| Variable | Puerto base | Servicio |
|----------|-------------|---------|
| `WEB_PORT` | 8069 | Odoo (HTTP) |
| `PGWEB_PORT` | 8081 | pgweb (browser de BD) |
| `DB_PORT` | 5432 | PostgreSQL |
| `DEBUGPY_PORT` | 5678 | debugpy (remote debug) |
| `MAILHOG_PORT` | 8025 | Mailhog (captura de correo) |

Si los puertos base estan ocupados, odev incrementa el offset para todos los puertos del set en 1 hasta encontrar un set completamente libre.

### Verificacion pre-vuelo (`odev up`)

Antes de iniciar el stack, `odev up` verifica cada puerto del `.env`:

- **Libre** — sin accion, `docker compose up` continua.
- **Propio corriendo** — WARN y continua (compose reutiliza el contenedor existente).
- **Foraneo** — FAIL con mensaje identificando el proyecto propietario; exit code 3.

```bash
# Ejemplo de fallo:
$ odev up
[FAIL] puerto 8069 (WEB_PORT) usado por proyecto otro-proyecto
# exit code 3
```

### Mantenimiento con `odev doctor`

`odev doctor` realiza dos tareas de mantenimiento del registro de puertos:

1. **GC de entradas obsoletas**: elimina del registro los proyectos cuyo directorio ya no existe, liberando sus puertos para nuevas asignaciones.
2. **Backfill de entradas legacy**: para proyectos creados con odev < 0.4.0 (sin campo `ports` en el registro), lee el `.env` y rellena el campo automaticamente.

```bash
odev doctor
# [INFO] Registro: 1 entrada(s) con backfill de puertos: mi-proyecto-legacy
# [INFO] Registro: 2 entrada(s) obsoleta(s) eliminada(s): proyecto-borrado, proyecto-viejo
```

## Gestion de Base de Datos

### Snapshots

Guarda y restaura el estado de la base de datos en cualquier punto del desarrollo:

```bash
# Guardar el estado actual de la base de datos
odev db snapshot instalacion-limpia

# Hacer cambios, experimentar, romper cosas...

# Restaurar al estado guardado (prompt interactivo)
odev db restore instalacion-limpia

# Restaurar sin confirmacion (agentes IA / CI)
odev db restore instalacion-limpia --yes

# Listar todos los snapshots disponibles
odev db list
```

Los snapshots se guardan como dumps de PostgreSQL en formato custom en el directorio `snapshots/` con timestamps, asi que podes tener multiples snapshots con el mismo prefijo.

### Cargar Backups Externos

Importa un backup de Odoo.sh o Database Manager (`.zip` que contiene `dump.sql` o `dump.dump` con `filestore/` opcional):

```bash
odev load-backup /ruta/al/backup.zip
```

Este comando:
1. Extrae el archivo de backup
2. Detiene el servicio web para liberar conexiones a la base de datos
3. Elimina y recrea la base de datos
4. Restaura el dump SQL (soporta tanto SQL plano como formato custom)
5. Copia el filestore al volumen de datos de Odoo (si esta presente)
6. Neutraliza la base de datos (desactiva crons, servidores de correo, etc.)
7. Resetea las credenciales de admin a `admin` / `admin`
8. Reinicia todos los servicios

Usa `--no-neutralize` para omitir el paso de neutralizacion.

### Anonimizacion

Elimina datos personales de una copia de base de datos de produccion para desarrollo seguro:

```bash
odev db anonymize
```

Reemplaza nombres, emails, numeros de telefono y direcciones con datos ficticios. Resetea todas las passwords de usuarios a `admin`.

### Reiniciar Base de Datos

Empeza completamente de cero destruyendo la base de datos y todos los volumenes Docker:

```bash
odev reset-db
```

Esto ejecuta `docker compose down -v` seguido de `docker compose up -d`.

## Desarrollo de Modulos

### Crear un Modulo Nuevo

```bash
odev scaffold mi_modulo
```

Esto crea `addons/mi_modulo/` con una estructura completa de modulo Odoo:

```
addons/mi_modulo/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   └── mi_modulo.py          # Modelo de ejemplo con campos
├── views/
│   └── mi_modulo_views.xml   # Vistas list + form, accion, item de menu
├── security/
│   └── ir.model.access.csv   # Lista de control de acceso
└── tests/
    ├── __init__.py
    └── test_mi_modulo.py     # Test de ejemplo con TransactionCase
```

### Flujo de Desarrollo

```bash
# 1. Crear el esqueleto del modulo
odev scaffold mi_modulo

# 2. Editar modelos, vistas, reglas de seguridad...

# 3. Instalar el modulo por primera vez
odev addon-install mi_modulo

# 4. Despues de hacer cambios en modelos Python o archivos de datos
odev update mi_modulo

# 5. Ejecutar tests
odev test mi_modulo

# 6. Generar contexto del proyecto para asistentes de IA
odev context
```

Los cambios en XML y JS se detectan automaticamente gracias al modo dev de Odoo con hot-reload.

### Testing

```bash
# Testear un modulo especifico
odev test mi_modulo

# Output JSON estructurado para agentes / CI
odev test mi_modulo --json

# Shorthand para test especifico (0.5.0+)
odev test mi_modulo:TestFoo.test_bar

# Testear con un nivel de log especifico
odev test mi_modulo --log-level debug

# Ejecutar todos los tests (puede llevar mucho tiempo)
odev test all

# Solo mostrar failures con tracebacks
odev test mi_modulo --failures

# Guardar log crudo a archivo
odev test mi_modulo --save-log /tmp/test.log
```

## Migracion desde odoo-dev-env

Si tenes un proyecto existente que usa el layout viejo `odoo-dev-env` (donde el repositorio de la herramienta ES el proyecto), podes migrarlo al nuevo formato:

```bash
# 1. Instalar odev globalmente
pip install git+https://github.com/giulianoh92/odev.git

# 2. Navegar a tu proyecto existente
cd /ruta/a/tu-proyecto-odoo-dev-env

# 3. Ejecutar la migracion
odev migrate
```

El comando `migrate` va a:
- Crear `.odev.yaml` a partir de la configuracion existente en `.env`
- Actualizar `.gitignore` para trackear `addons/` (en vez de ignorarlo)
- Generar archivos faltantes (`.env.example`, `CLAUDE.md`, etc.)
- Crear directorios necesarios (`docs/`, `snapshots/`, `logs/`) con `.gitkeep`

Despues de la migracion, revisa los cambios con `git diff` y commitea:

```bash
git add .odev.yaml addons/
git commit -m "feat: migrar a formato de proyecto independiente"
```

## Dashboard TUI

Lanza el dashboard interactivo de terminal:

```bash
odev tui
```

La TUI provee tres paneles:
- **Panel de estado** -- Estado de servicios en vivo (auto-refresco) mostrando estado del contenedor, salud y puertos
- **Barra de acciones** -- Referencia rapida de atajos de teclado
- **Visor de logs** -- Streaming de logs de Odoo en tiempo real

### Atajos de Teclado

| Tecla | Accion |
|-------|--------|
| `U` | Levantar servicios (docker compose up) |
| `D` | Detener servicios (docker compose down) |
| `R` | Reiniciar el contenedor web de Odoo |
| `S` | Abrir shell bash en el contenedor de Odoo |
| `C` | Generar PROJECT_CONTEXT.md |
| `Q` | Salir de la TUI |

## Diagnostico del Entorno

Ejecuta `odev doctor` para verificar tu entorno:

```bash
odev doctor
```

Verifica:
- Docker esta instalado y corriendo
- Docker Compose v2 esta disponible
- Version de Python es 3.10+
- Proyecto detectado (modo PROJECT, LEGACY o NONE)
- El archivo `.env` existe
- El archivo `docker-compose.yml` existe
- El archivo `config/odoo.conf` existe
- Directorio `addons/` y cantidad de modulos
- Los puertos configurados estan disponibles (no en uso por otros procesos)
- La version del CLI es compatible con el `odev_min_version` del proyecto

Ejemplo de salida:

```
Diagnostico del entorno odev
========================================

  [OK]   Docker instalado (Docker version 27.x.x)
  [OK]   Docker Compose v2 disponible
  [OK]   Python 3.12.x
  [OK]   Proyecto detectado: mi-proyecto (modo: project)
  [OK]   .env existe
  [OK]   docker-compose.yml existe
  [OK]   config/odoo.conf existe
  [INFO] addons/ tiene 3 modulo(s)
  [OK]   Puerto 8069 (Odoo) disponible
  [OK]   Puerto 8081 (pgweb) disponible
  [OK]   odev version 0.1.0 (minimo requerido: 0.1.0)

Todas las verificaciones pasaron correctamente.
```

## Instalacion

### Con pip

```bash
pip install git+https://github.com/giulianoh92/odev.git
```

### Con pipx (entorno aislado)

```bash
pipx install git+https://github.com/giulianoh92/odev.git
```

### Para contribuidores (instalacion editable)

```bash
git clone https://github.com/giulianoh92/odev.git
cd odev
pip install -e ".[dev]"
```

## Requisitos

- **Python 3.10+** (se recomienda 3.12)
- **Docker** con **Docker Compose v2** (Docker Desktop o `docker-compose-plugin`)
- Una terminal que soporte colores ANSI (para la TUI y la salida con Rich)

## Contribuir

1. Hace un fork del repositorio
2. Crea una rama para tu funcionalidad (`git checkout -b feature/mi-funcionalidad`)
3. Instala las dependencias de desarrollo: `pip install -e ".[dev]"`
4. Hace tus cambios
5. Ejecuta el linting: `ruff check src/ && ruff format --check src/`
6. Ejecuta los tests: `pytest`
7. Envia un pull request

## Licencia

MIT
