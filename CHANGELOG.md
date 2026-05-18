# Registro de Cambios

Todos los cambios notables en este proyecto se documentan en este archivo.

El formato esta basado en [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
y este proyecto adhiere a [Versionado Semantico](https://semver.org/spec/v2.0.0.html).
Politica de bumps: ver [VERSIONING.md](VERSIONING.md).

## [0.5.3] - 2026-05-17

### Documentacion

- README extendido con seccion "Servidor MCP" (instalacion, configuracion Claude Code/Cursor, tabla de 9 tools, 4 resources, 3 prompts).
- README agrega items "MCP server (0.5.2+)" y "Salida JSON estructurada (0.5.0+)" a Funcionalidades.
- README incluye `odev mcp serve`, `odev model-info`, `odev modules` en Referencia Rapida.
- Caveat de `odev py` actualizado: el banner de Odoo se elimina automaticamente desde 0.5.0 (`--keep-banner` para raw).
- Seccion Testing expandida con `--json`, `mod:Class.method` shorthand, `--failures`, `--save-log`.
- Snapshot section menciona `db restore --yes` para uso no-interactivo (agentes IA / CI).

Sin cambios de codigo. Pure docs release.

## [0.5.2] - 2026-05-17

### Agregado

- `odev mcp serve` — nuevo subcomando que expone odev como servidor MCP (Model Context Protocol). Arranca un servidor FastMCP sobre transporte `stdio` (default) o `http --port N`. Requiere el extra opcional `[mcp]`: `pipx install 'odev[mcp]'`. Sin el extra, el comando sale con exit 2 y muestra el hint de instalacion en stderr.
- 9 herramientas MCP: `odev_status`, `odev_shell`, `odev_sql`, `odev_py`, `odev_test`, `odev_logs`, `odev_doctor`, `odev_model_info`, `odev_modules`. Cada una delega al helper `_execute_*` correspondiente y retorna datos estructurados JSON-RPC.
- 4 recursos MCP: `odev://project/context` (markdown), `odev://project/config` (JSON), `odev://db/schema` (pg_dump --schema-only), `odev://modules/{name}/manifest` (JSON del manifiesto).
- 3 prompts MCP: `diagnose_failing_test`, `explain_module`, `generate_migration` — templates estaticos con interpolacion de argumentos.
- `[project.optional-dependencies] mcp = ["mcp>=1.0.0"]` en `pyproject.toml`. Instalacion base sin el extra permanece identica a 0.5.1.

### Interno

- Refactor (MCP prep): extraidos helpers `_execute_*` en 10 modulos de comandos (`status`, `sql`, `py`, `test`, `model_info`, `logs`, `modules`, `doctor`, `shell`, `context`). Cada helper retorna datos Python puros sin I/O, sin `typer.Exit`. Los `_run_*` existentes delegan a ellos y mantienen comportamiento CLI byte-identical. Seam necesario para el servidor MCP de PR2.
- Nuevo: `ProjectConfig.to_dict()` en `core/project.py` — expone la configuracion como dict JSON-serializable para el recurso MCP `odev://project/config`.

## [0.5.1] - 2026-05-17

### Agregado

- F2: `odev doctor --json` / `-j` — emite documento JSON unico con resultados de todos los checks. Schema: `{"version": "0.5.1", "checks": [{"name": str, "status": "ok"|"warn"|"fail"|"info", "message": str, "hint": str|null}], "summary": {"ok": int, "warn": int, "fail": int}, "exit_code": 0|1}`. Exit 0 si no hay fail, exit 1 si hay al menos uno. Sin proyecto: `{"error": "no project context"}` en stderr, exit 1, stdout vacio.
- F3: `odev logs <service> --json` / `-j` — captura snapshot de logs recientes y los emite como array JSON `[{"service": str, "timestamp": str, "level": str|null, "message": str}]`. Implica no-follow. `--tail N` (default 100) limita las lineas capturadas. `--json` y `--follow` / `-f` son mutuamente excluyentes (exit 2).
- F5: `odev model-info <model>` — nuevo comando. Introspecta un modelo Odoo via ORM en tiempo real y emite JSON `{"model": str, "description": str, "inherits": [str], "fields": [{"name": str, "type": str, "required": bool, "relation": str|null}]}`. Requiere stack corriendo. `--pretty` para JSON indentado. Exit 1 si modelo no existe; exit 3 si stack detenido.

### Corregido

- doctor `--json`: sin contexto de proyecto emite `{"error": "no project context"}` en stderr y sale con exit 1 en lugar de emitir JSON de checks a stdout con exit 0 (W1).
- doctor `--json`: el backfill interno del registro ya no llama `_imprimir_warn` (que usaba `console.print` y filtraba Rich a stdout en modo JSON); reemplazado por `logging.warning` (W2).

### Interno

- Refactor: `_strip_banner` y `_BANNER_LINE_RE` extraidos de `commands/py.py` a nuevo modulo `commands/_odoo_shell.py` para reutilizacion en futuros comandos de shell Odoo. `py.py` re-importa desde la nueva ubicacion (sin cambio de comportamiento).

## [0.5.0] - 2026-05-17

### Cambios incompatibles

- `odev.core.ports.sugerir_puertos` ha sido **eliminada**. Si tu codigo importa esta funcion, reemplazala por `allocate_ports(project_name, registry)` de `odev.core.ports`. La deprecacion estaba activa desde 0.4.0 con `DeprecationWarning`; la eliminacion es un break MINOR bajo la politica pre-1.0 del proyecto.

### Agregado

- D1: `DockerCompose.exec_capture(service, command)` — nuevo metodo que retorna `(stdout: bytes, stderr: bytes, returncode: int)` sin TTY, sin lanzar excepcion en codigo no cero. Base para todos los flujos de captura de agentes en 0.5.0.
- D4: `odev status --json` / `-j` — emite array JSON `[{"service": str, "status": str, "ports": [int]}, ...]`. Stack down retorna `[]`. Sin proyecto retorna `{"error": "..."}` en stderr con exit 1.
- D5: `odev context --json --quiet` — emite objeto JSON con `project_name`, `odoo_version`, `addons_paths`, `modules_installed`, `db`. `--quiet` suprime decoraciones Rich. `--json` solo siempre suprime Markdown.
- D6: `odev sql --json` / `-j` — emite array JSON de filas como lista de dicts `[{"col": "val", ...}]`. Valores como strings (protocolo texto psql — usar CAST en SQL para tipos). Cero filas retorna `[]`. Error psql en stderr JSON + exit 1. Mutuamente excluyente con `--csv` (exit 2).
- D8: `odev test module:Class.method` — shorthand para filtrar tests por clase/metodo sin escribir `--tags` a mano. `odev test mymod:TestFoo.test_bar` se expande a `--test-tags /mymod:TestFoo.test_bar`. CSV+colon invalido (exit 2 con mensaje de uso).
- D9: `odev modules --json` — nuevo comando. Lista modulos instalados desde `ir_module_module` (`state IN ('installed', 'to upgrade', 'to install')`). Schema: `[{"name": str, "state": str, "version": str}]`. Dependencias entre modulos diferidas a 0.6.0.
- D10: `odev db restore --yes` / `-y` — flag para saltarse la confirmacion interactiva. Util para agentes IA y scripts CI. Sin el flag, el comportamiento de prompt existente no cambia.
- D11: Codigos de salida en `--help` de todos los comandos publicos — cada comando expone una seccion epilog estandar con codigos 0/1/2/3 y sus significados. Constante `EPILOG_EXIT_CODES` en `commands/_helpers.py`.

### Cambiado

- D7: `odev py` ahora elimina automaticamente el banner del shell Odoo del stdout. Solo el resultado de la expresion aparece en stdout (equivalente al anterior `| tail -n 1`). Usar `--keep-banner` para conservar la salida raw (debug). Compatible con Odoo 16/17/18/19.

### Corregido

- D2: `odev db restore` ahora streamea el dump via `exec_cmd_file` en lugar de cargarlo entero en RAM con `read_bytes()`. Elimina OOM en snapshots grandes. Mismo patron que la fix B3 de `load-backup` en 0.4.3.

### Eliminado

- D3: `sugerir_puertos()` eliminada de `odev.core.ports`. Reemplazar por `allocate_ports(project_name, registry)`.

## [0.4.3] - 2026-05-17

### Corregido

- B3: `odev load-backup` ahora streamea el dump SQL desde archivo (`DockerCompose.exec_cmd_file`) en lugar de cargarlo entero en RAM, eliminando OOM en dumps grandes (5-20 GB)

### Agregado

- Q5: Flag `--dry-run` en `odev down`, `odev reset-db`, y `odev load-backup` — previsualiza operaciones destructivas sin ejecutarlas. Util para agentes IA y operadores antes de comandos peligrosos

### Cambiado

- Lint cleanup interno: ruff check + format clean en todo src/. Configurados per-file-ignores en pyproject.toml para template strings (init.py CI YAML, scaffold templates)
- Nota: `commands/db.py` snapshot restore (mismo patron OOM que B3) queda diferido a 0.5.0; impacto menor (snapshots son tipicamente mas pequenos que dumps de produccion)

## [0.4.2] - 2026-05-17

### Corregido

- `odev test` fallaba con `Address already in use` en Odoo 19 cuando el stack del proyecto estaba corriendo. Odoo 19 ignora el flag `--no-http` y sigue bindeando el puerto HTTP default (8069 interno), lo que colisionaba con el proceso principal de odoo en el container. Solucion: pasar `--http-port=8073` (constante `_TEST_HTTP_PORT` en `commands/test.py`) para redirigir el bind del proceso de test a un puerto interno libre. Se mantiene `--no-http` para retro-compat con Odoo ≤18 donde si era suficiente. Bloqueaba el flujo TDD para agentes IA en proyectos Odoo 19.

## [0.4.1] - 2026-05-17

### Corregido

- B1: Rechazo de miembros ZIP con path traversal (`../../` o absoluto) en `odev load-backup`; error `LOAD_BACKUP_UNSAFE_MEMBER` en exit 1
- B2: Eliminado race condition TOCTOU en escritura del registro (`registry.yaml`) — siempre usa modo `"w"` bajo flock
- B4/Q8: Reemplazado `asyncio.get_event_loop()` por `asyncio.get_running_loop()` en `LogViewer` (compat Python 3.12+)
- B5: Narrowed `except Exception: pass` a `except (subprocess.SubprocessError, OSError)` en `reset_db._esperar_base_datos_lista`
- B6: Guard de `ImportError` en `import fcntl` para compatibilidad Windows; degrada a lock de thread sin flock
- Q2: `registry._leer()` crea `.bak` y emite warning `REGISTRY_YAML_CORRUPT` cuando el YAML es invalido, en lugar de perderse silenciosamente
- Q4: URL de pgweb en `odev up` solo se imprime cuando `services.pgweb: true` en `odev.yaml`
- Q6: `odev doctor` ejecuta el GC del registro (`_ejecutar_registry_gc_y_backfill`) **antes** de verificar puertos, limpiando orphans primero
- Q7: `odev up` incluye hint `odev doctor` y `odev --project {owner} down` en el mensaje de error de preflight cuando hay conflicto de puertos

### Seguridad

- S1: `.env` creado por `odev init` / `odev adopt` recibe `chmod 0600` inmediatamente; impide lectura por otros usuarios del sistema
- S2: Regex de validacion de `DB_NAME` en `load-backup` restringido a `^[a-zA-Z_][a-zA-Z0-9_]*$`; rechaza nombres con `.`, `-` o digito inicial
- S3: `odev migrate` emite advertencia y aplica `chmod 0600` al `.env.example` generado; agrega header de aviso de secretos al archivo

### Cambiado

- Q1: Flag global `--debug` en `odev`; activa `logging.DEBUG` en todos los loggers antes de ejecutar cualquier subcomando
- Q10: `PORT_KEYS` derivado de `CONJUNTOS_PUERTOS.keys()` en `core/ports.py` — fuente unica de verdad para claves de puerto; elimina listas duplicadas en `up.py` y `doctor.py`

### Agregado

- Q3: Subgrupos `db`, `projects` y `enterprise` aparecen bajo panel **Subgrupos** en `odev --help` via `rich_help_panel`
- Q9: Columna **Puertos** en `StatusPanel` del TUI — muestra puertos publicados de cada servicio Docker leidos de `docker compose ps --format json`

### Cambios incompatibles

- S2: La regex estricta de `DB_NAME` rechaza proyectos existentes con `.` o `-` en el nombre de base de datos. Para migrar: renombrar la BD de Postgres o usar `odev load-backup` sobre una copia renombrada.

## [0.4.0] - 2026-05-17

### Agregado

- Asignacion atomica de puertos via registro global (`allocate_ports`) — elimina la race condition TOCTOU en wizards concurrentes (`odev init` / `odev adopt`)
- `RegistryEntry.ports` — campo opcional `dict[str, int]` en el registro para reclamar y trackear puertos por proyecto
- Metodos `asignar_puertos()`, `liberar_puertos()`, `puertos_ocupados()` en `Registry` para gestion coordinada de puertos
- `PortAllocationError` — excepcion especifica cuando se agotan los 100 offsets disponibles
- Nuevo modulo `core/preflight.py` con `verificar_puertos_pre_up()` — verifica puertos antes de `docker compose up`
- Clasificacion de puertos en `odev up`: libre / propio-corriendo (WARN) / foraneo (FAIL exit 3)
- `_verificar_registry_puertos()` en `doctor` — backfill de entradas legacy desde `.env` y GC de entradas obsoletas
- `MAILHOG_PORT` agregado a la verificacion de puertos en `odev doctor`
- Seccion "Asignacion de Puertos" en README con tabla de variables, descripcion de preflight y uso de `odev doctor`
- Lock de thread (`threading.Lock`) en el registro para serializar escrituras concurrentes intra-proceso

### Cambiado

- `odev init` y `odev adopt` usan `allocate_ports()` en lugar de `sugerir_puertos()` para evitar colisiones
- `commands/doctor.py` importa `puerto_disponible` desde `odev.core.ports` (elimina duplicado local `_puerto_disponible`)
- TUI `ProjectInfoPanel`: fila de Mailhog reemplaza a la fila de longpolling (dead concept en Odoo 16+)

### Corregido

- Colision de puertos TOCTOU cuando multiples wizards de `init`/`adopt` corren simultaneamente
- `odev up` ahora falla antes de invocar docker compose si hay un puerto ocupado por un proceso ajeno (exit 3)
- `odev doctor` ahora verifica `MAILHOG_PORT` ademas de los 4 puertos previos

### Eliminado

- `_puerto_disponible` local en `commands/doctor.py` (duplicado del de `core/ports.py`)
- `LONGPOLL_PORT` / `PORT_LONGPOLL` del widget TUI (fallback estatico incorrecto; Odoo 16+ no usa puerto separado)

### Deprecado

- `sugerir_puertos()` en `core/ports.py` — emite `DeprecationWarning` desde 0.4.0; usar `allocate_ports(project_name, registry)` en su lugar; se eliminara en 0.5.0

## [0.3.1] - 2026-05-17

### Corregido

- `__version__` ahora se resuelve dinamicamente via `importlib.metadata.version("odev")` en lugar de string hardcoded. Elimina drift entre `pyproject.toml` y `src/odev/__init__.py`. Hace cumplir politica VERSIONING.md (pyproject como unica fuente de verdad).

## [0.3.0] - 2026-05-17

### Agregado

- Comandos agent-friendly no-interactivos con propagacion de stdout/stderr crudo y exit code:
  - `odev shell <svc> -c "<cmd>"` -- bash -c en contenedor
  - `odev sql "<query>"` -- psql -c en db (flag `--csv` sin bordes ni alineacion)
  - `odev py "<expr>"` -- eval Python via `odoo shell` (stdin pipe)
- `odev test` con flags `--summary`, `--failures`, `--json`, `--tags`, `--save-log` para output AI-friendly
- Parser de output de tests Odoo (`core/odoo_test_parser.py`) con soporte Odoo 19, `setUpClass`, loading errors
- Pre-flight de modulo + puerto en `odev test` (usa `WEB_PORT` env)
- CSV multi-modulo en `update`, `addon-install`, `test` -- una sola invocacion a Odoo (`mod1,mod2,mod3`)
- Flag `--no-validate` para saltar validacion de addons-path en operaciones multi-modulo
- Helper de parseo/validacion de CSV de modulos + listado de modulos disponibles
- TUI: panel de proyecto, paleta de comandos, ayuda contextual, selector de servicio, sistema de notificaciones
- `core/docker.exec_cmd_stream()` para streaming de stdout en operaciones largas
- Detect: descubre modulos en submodulos git anidados y en subdirectorios convencionales (`addons/`, `custom/`, etc.)
- Politica de versionado explicita -- ver `VERSIONING.md`

### Corregido

- Parser de tests soporta formato Odoo 19, `setUpClass` y loading errors
- `[fix] test`: merge correcto de `--tags`, `raw_summary_line` en JSON, epilog con exit codes
- `[fix] test`: removido pre-flight de puerto host (falso positivo con web container ya corriendo)
- `[fix] test`: usa `--no-http` para evitar colision de puerto con web container corriendo
- `[fix] docker`: normaliza nombre de proyecto a minusculas para `docker compose`
- `[fix] enterprise`: corrige lookup de `odev.yaml` en modo config externo
- `[fix] test`: aisla test de `ruta_enterprise` del filesystem del host

### Cambiado

- Refactor: `ejecutar_passthrough()` en `_helpers.py` unifica logica de `shell -c`, `sql` y `py`
- Refactor: limpia imports stale y dead code post CSV-modules
- Docs: README documenta CSV de modulos, flag `--no-validate`, ejemplos `shell -c` / `sql` / `py`
- Docs: CLAUDE.md template agrega comandos no-interactivos + CSV multi-modulo
- `.gitignore`: agrega `.atl/` y `uv.lock`

## [0.2.0] - 2026-03-26

### Agregado

- Nuevo comando `reconfigure` -- Regenera docker-compose.yml y odoo.conf desde odev.yaml sin re-adoptar
- Nuevo modulo `core/regen.py` -- Motor de regeneracion compartido (usado por reconfigure, up, adopt)
- Nuevo subcomando `enterprise` con 4 operaciones:
  - `enterprise import <version> <ruta>` -- Importar addons enterprise a almacenamiento compartido
  - `enterprise path <version>` -- Mostrar ruta de enterprise para una version
  - `enterprise status` -- Listar versiones enterprise disponibles y proyectos que las usan
  - `enterprise link` -- Vincular enterprise compartido al proyecto actual
- Almacenamiento compartido de enterprise en `~/.odev/enterprise/{version}/` (evita copias por proyecto)
- Auto-regeneracion de configs en `odev up` cuando odev.yaml cambia (deteccion por mtime)
- Flag `--force` / `-f` en `adopt` para re-adoptar proyectos existentes
- Flag `--yes` / `-y` en `load-backup` y `reset-db` para omitir confirmacion (automatizacion/CI)
- Verificacion pre-vuelo en `load-backup`: detecta si el contenedor de BD esta corriendo antes de proceder
- Metodo `is_service_running()` en DockerCompose para verificar estado de servicios
- Validacion de esquema nested en odev.yaml con warnings para claves desconocidas y tipos incorrectos
- Propiedad `ruta_enterprise` en ProjectConfig con fallback a enterprise compartido
- 58 tests nuevos (237 → 295), 0 regresiones

### Corregido

- Enterprise ahora es PRIMERO en addons_path de odoo.conf (antes se agregaba al final, causando que modulos CE overridearan EE)

### Documentacion

- Especificaciones SDD completas en `docs/sdd/` (proposal, spec, design, tasks)

## [0.1.0] - 2026-03-19

### Agregado

- Release inicial de odev como paquete instalable via pip
- 18 comandos CLI de nivel superior:
  - `init` -- Wizard interactivo de proyecto (o `--no-interactive` para valores por defecto)
  - `up` -- Iniciar entorno Docker Compose (`--build`, `--watch`)
  - `down` -- Detener y eliminar contenedores (`-v` para eliminar volumenes)
  - `restart` -- Reiniciar el contenedor web de Odoo
  - `status` -- Tabla de estado de servicios con formato Rich
  - `logs` -- Seguir logs de servicios (`--tail`, `--no-follow`)
  - `shell` -- Shell bash interactivo en el contenedor de Odoo
  - `test` -- Ejecutar tests de modulos Odoo (`--log-level`)
  - `scaffold` -- Crear un modulo nuevo desde el template incluido
  - `addon-install` -- Instalar un modulo por primera vez
  - `update` -- Actualizar un modulo y reiniciar
  - `reset-db` -- Destruir base de datos y volumenes, empezar de cero
  - `load-backup` -- Importar backups de Odoo.sh / Database Manager (`.zip`)
  - `context` -- Generar PROJECT_CONTEXT.md a partir del analisis de modulos
  - `tui` -- Dashboard interactivo de terminal (Textual)
  - `migrate` -- Migrar proyectos legacy odoo-dev-env al nuevo formato
  - `doctor` -- Diagnostico del entorno (Docker, Compose, puertos, configuracion)
  - `self-update` -- Actualizar odev via pip
- 4 subcomandos de base de datos (`odev db`):
  - `snapshot` -- Crear un snapshot de la base de datos (pg_dump formato custom)
  - `restore` -- Restaurar base de datos desde un snapshot
  - `list` -- Listar snapshots disponibles con fecha y tamano
  - `anonymize` -- Reemplazar datos personales con valores ficticios, resetear passwords
- Dashboard TUI interactivo con:
  - Panel de estado de servicios en vivo (auto-refresco)
  - Visor de logs en streaming
  - Atajos de teclado para acciones comunes (U/D/R/S/C/Q)
- Deteccion de proyecto con tres modos: PROJECT, LEGACY, NONE
- Soporte multi-proyecto con asignacion automatica de puertos
- Scaffolding de proyectos basado en Jinja2 (docker-compose.yml, .env, odoo.conf, etc.)
- Template de modulo con modelos, vistas, seguridad y tests
- Soporte de versiones de Odoo: 19.0, 18.0, 17.0
- PostgreSQL con soporte pgvector (pg16 para Odoo 18/19, pg15 para Odoo 17)
- Addons Enterprise, pgweb, debugpy y GitHub Actions CI opcionales
- Regeneracion automatica de odoo.conf cuando cambia .env
- Carga de backups con neutralizacion automatica y reseteo de credenciales admin
- Generacion de configuracion de pre-commit (ruff)
- Generacion de CLAUDE.md para integracion con asistentes de IA
