# Registro de Cambios

Todos los cambios notables en este proyecto se documentan en este archivo.

El formato esta basado en [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
y este proyecto adhiere a [Versionado Semantico](https://semver.org/spec/v2.0.0.html).
Politica de bumps: ver [VERSIONING.md](VERSIONING.md).

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
