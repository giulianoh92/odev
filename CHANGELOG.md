# Registro de Cambios

Todos los cambios notables en este proyecto se documentan en este archivo.

El formato esta basado en [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
y este proyecto adhiere a [Versionado Semantico](https://semver.org/spec/v2.0.0.html).

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
