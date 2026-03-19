# Guia de Uso de odev

**odev** es un toolkit de linea de comandos que estandariza entornos de desarrollo Odoo basados en Docker. Se instala una vez de forma global y permite crear tantos proyectos aislados como necesites, cada uno con su propia configuracion, base de datos, puertos y stack de Docker Compose.

Esta guia cubre todo lo que necesitas para ir de cero a un entorno productivo de desarrollo.

---

## 1. Requisitos Previos

Antes de instalar odev, asegurate de tener las siguientes herramientas:

| Herramienta | Version minima | Verificacion |
|-------------|----------------|--------------|
| Docker | 20+ | `docker --version` |
| Docker Compose v2 | 2.0+ | `docker compose version` |
| Python | 3.10+ (recomendado 3.12) | `python3 --version` |
| pip o pipx | Cualquiera reciente | `pip --version` o `pipx --version` |

```bash
# Verificar todo de una vez
docker --version
docker compose version
python3 --version
pip --version
```

> **Nota:** Docker Compose debe ser la v2 (comando `docker compose`, no `docker-compose`). Si usas Docker Desktop ya viene incluido. En Linux, instala el paquete `docker-compose-plugin`.

Tambien necesitas una terminal que soporte colores ANSI (cualquier terminal moderna en Linux/macOS sirve; en Windows usa Windows Terminal).

---

## 2. Instalacion

### Con pip (recomendado)

```bash
pip install odev
```

### Con pipx (entorno aislado)

```bash
pipx install odev
```

### Verificar la instalacion

```bash
odev --version
```

Salida esperada:

```
odev 0.1.0
```

### Actualizar a la ultima version

```bash
odev self-update
```

Este comando ejecuta `pip install --upgrade odev` usando el interprete de Python correcto. Si ya tienes la ultima version, te lo indica:

```
[INFO] Version actual: 0.1.0
[INFO] Buscando actualizaciones...
[INFO] Ya tienes la ultima version disponible.
```

---

## 3. Crear un Proyecto Nuevo

### Wizard interactivo

```bash
odev init mi-proyecto
```

Esto crea el directorio `mi-proyecto/` y lanza un wizard que te pregunta paso a paso:

| Pregunta | Default | Descripcion |
|----------|---------|-------------|
| Nombre del proyecto | `mi-proyecto` | Nombre para Docker Compose y archivos de configuracion |
| Version de Odoo | `19.0` | Opciones: 19.0, 18.0, 17.0 |
| Puerto de Odoo | `8069` | Puerto HTTP para acceder a Odoo (auto-detectado si esta ocupado) |
| Puerto de pgweb | `8081` | Puerto para el visor web de PostgreSQL |
| Nombre de la base de datos | `odoo_db` | Nombre de la BD en PostgreSQL |
| Usuario de la base de datos | `odoo` | Usuario PostgreSQL |
| Password de la base de datos | `odoo` | Password PostgreSQL |
| Idioma por defecto | `en_US` | Idioma a instalar (ej. `es_AR`, `fr_FR`) |
| Datos de demo | Omitir | Cargar o no los datos de demostracion de Odoo |
| Habilitar debugpy | No | Depuracion remota para VS Code en puerto 5678 |
| Habilitar enterprise addons | No | Montar directorio `enterprise/` en el contenedor |
| Habilitar pgweb | Si | Visor web para explorar la BD |
| Generar GitHub Actions CI | Si | Pipeline de linting y testing automatico |
| Inicializar repositorio git | Si | Ejecuta `git init` + commit inicial |

### Modo no-interactivo (CI/automatizacion)

```bash
odev init mi-proyecto --no-interactive
```

Usa todos los valores por defecto. Ideal para scripts de CI o para crear proyectos rapido.

Tambien podes especificar la version de Odoo:

```bash
odev init mi-proyecto --no-interactive --odoo-version 18.0
```

### Inicializar en el directorio actual

```bash
mkdir mi-proyecto && cd mi-proyecto
odev init .
```

### Archivos generados

Despues de ejecutar `odev init`, el directorio del proyecto queda asi:

```
mi-proyecto/
├── addons/                  # Tus modulos Odoo (trackeado en git)
├── config/
│   └── odoo.conf            # Configuracion de Odoo (generado, gitignored)
├── enterprise/              # Addons enterprise (opcional, gitignored)
├── snapshots/               # Snapshots de base de datos (gitignored)
├── logs/                    # Logs de Odoo y PostgreSQL (gitignored)
├── docs/                    # Documentacion y artefactos SDD
├── docker-compose.yml       # Servicios Docker (Odoo + PostgreSQL + pgweb)
├── entrypoint.sh            # Script de entrada del contenedor
├── .odev.yaml               # Configuracion del proyecto para odev
├── .env                     # Variables de entorno (gitignored, secretos locales)
├── .env.example             # Template compartible con el equipo
├── .gitignore               # Ignores pre-configurados
├── .pre-commit-config.yaml  # Hooks de pre-commit (ruff, etc.)
├── pyproject.toml           # Configuracion de herramientas del proyecto
├── CLAUDE.md                # Instrucciones para asistentes AI
└── .github/
    └── workflows/
        └── ci.yml           # GitHub Actions CI (opcional)
```

| Archivo | Proposito |
|---------|-----------|
| `.odev.yaml` | Archivo principal de configuracion de odev. Identifica el directorio como proyecto. |
| `.env` | Variables de entorno para Docker Compose. Contiene secretos, no se commitea. |
| `.env.example` | Copia de `.env` con placeholders para passwords. Se commitea para compartir. |
| `docker-compose.yml` | Define los servicios: `web` (Odoo), `db` (PostgreSQL), `pgweb` (opcional). |
| `entrypoint.sh` | Script que configura Odoo al iniciar el contenedor. |
| `config/odoo.conf` | Configuracion de Odoo. Se regenera automaticamente desde `.env`. |
| `CLAUDE.md` | Contexto del proyecto para asistentes de IA (Claude, Copilot, etc.). |

---

## 4. Levantar y Gestionar el Entorno

### Iniciar el entorno

```bash
cd mi-proyecto
odev up
```

Salida esperada:

```
[INFO] Iniciando entorno...
[OK]   Entorno iniciado correctamente.
[INFO]   Odoo:  http://localhost:8069
[INFO]   pgweb: http://localhost:8081
```

El comando `odev up` hace lo siguiente internamente:
1. Verifica que exista el archivo `.env`.
2. Regenera `config/odoo.conf` si el `.env` fue modificado despues.
3. Asegura que el directorio `logs/` tenga permisos de escritura para los contenedores.
4. Ejecuta `docker compose up -d`.

#### Opciones de `odev up`

```bash
# Reconstruir imagenes antes de iniciar (despues de cambiar Dockerfile o dependencias)
odev up --build

# Activar modo watch de Docker Compose (sincroniza cambios en addons/ automaticamente)
odev up --watch
```

### Detener el entorno

```bash
# Detiene y elimina los contenedores (los datos se preservan en los volumenes)
odev down

# Detiene, elimina contenedores Y elimina volumenes (base de datos, filestore, todo)
odev down -v
```

> **Nota:** `odev down` sin `-v` es seguro. Tus datos persisten en volumenes Docker. Con `-v` se pierde todo: base de datos, filestore y snapshots internos del volumen.

### Reiniciar Odoo

```bash
odev restart
```

Reinicia solo el contenedor `web` (Odoo). Util despues de cambiar `odoo.conf` o cuando Odoo queda en un estado inconsistente. La base de datos no se toca.

### Ver el estado de los servicios

```bash
odev status
```

Salida esperada:

```
Proyecto: mi-proyecto (modo: project)

            Servicios
┏━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━┓
┃ Servicio ┃ Estado   ┃ Salud   ┃ Puertos       ┃
┡━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━┩
│ db       │ running  │ healthy │ 5432:5432     │
│ web      │ running  │ healthy │ 8069:8069     │
│ pgweb    │ running  │         │ 8081:8081     │
└──────────┴──────────┴─────────┴───────────────┘
```

La tabla muestra por cada servicio: nombre, estado del contenedor, salud (basada en el healthcheck de Docker) y puertos publicados.

### Ver logs

```bash
# Logs del servicio web (Odoo) — por defecto, sigue en tiempo real
odev logs

# Logs de la base de datos
odev logs db

# Logs de todos los servicios
odev logs all

# Ultimas 50 lineas sin seguir en tiempo real
odev logs web --tail 50 --no-follow
```

| Flag | Default | Descripcion |
|------|---------|-------------|
| `--tail` / `-n` | `100` | Cantidad de lineas a mostrar desde el final |
| `--no-follow` | `False` | No seguir la salida en tiempo real (solo imprime y sale) |

Para salir de los logs en modo follow, presiona `Ctrl+C`.

### Shell interactivo

```bash
odev shell
```

Abre un shell `bash` dentro del contenedor de Odoo. Desde ahi podes:

- Ejecutar comandos de Odoo directamente: `odoo shell -d odoo_db`
- Inspeccionar el filesystem del contenedor
- Verificar que los addons estan montados: `ls /mnt/extra-addons/`
- Probar imports de Python: `python3 -c "import odoo; print(odoo.__version__)"`

---

## 5. Desarrollo de Modulos

### Crear un modulo nuevo

```bash
odev scaffold mi_modulo
```

> **Regla de nombres:** El nombre debe ser `snake_case` (letras minusculas, numeros y guiones bajos, comenzando con una letra). Ejemplos validos: `mi_modulo`, `ventas_custom`, `hr_extensiones`. Ejemplos invalidos: `MiModulo`, `mi-modulo`, `2modulo`.

Esto genera la siguiente estructura en `addons/mi_modulo/`:

```
addons/mi_modulo/
├── __init__.py
├── __manifest__.py           # Manifiesto del modulo
├── models/
│   ├── __init__.py
│   └── mi_modulo.py          # Modelo de ejemplo con campos
├── views/
│   └── mi_modulo_views.xml   # Vistas list + form, accion y menu
├── security/
│   └── ir.model.access.csv   # Lista de control de acceso
└── tests/
    ├── __init__.py
    └── test_mi_modulo.py     # Test de ejemplo con TransactionCase
```

Despues de crear el modulo, el CLI te indica los proximos pasos:

```
[OK]   Modulo creado: /ruta/al/proyecto/addons/mi_modulo
[INFO] Proximos pasos:
[INFO]   1. Editar addons/mi_modulo/__manifest__.py
[INFO]   2. Reiniciar Odoo o ejecutar: odev update mi_modulo
```

### Instalar un modulo por primera vez

```bash
odev addon-install mi_modulo
```

Este comando ejecuta `odoo -i mi_modulo` dentro del contenedor, lo que instala el modulo en la base de datos. Luego reinicia automaticamente el servicio web para aplicar los cambios.

### Actualizar un modulo despues de cambios

```bash
odev update mi_modulo
```

Ejecuta `odoo -u mi_modulo` (upgrade) y reinicia el servicio web. Usa esto despues de modificar:
- Modelos Python (nuevos campos, logica de negocio)
- Archivos de datos XML/CSV
- Archivos de seguridad

> **Nota:** Los cambios en archivos XML de vistas, QWeb y JS se detectan automaticamente gracias al modo dev de Odoo. Para esos cambios normalmente basta con recargar la pagina en el navegador.

### Ejecutar tests

```bash
# Tests de un modulo especifico
odev test mi_modulo

# Tests con nivel de log diferente
odev test mi_modulo --log-level debug

# Ejecutar TODOS los tests (puede tomar mucho tiempo)
odev test all
```

| Flag | Default | Descripcion |
|------|---------|-------------|
| `--log-level` / `-l` | `test` | Nivel de log: `test`, `debug`, `info`, `warn`, `error` |

### Ciclo de desarrollo tipico

```bash
# 1. Crear el esqueleto del modulo
odev scaffold ventas_custom

# 2. Editar modelos, vistas, seguridad...
#    (usa tu editor favorito)

# 3. Instalar el modulo por primera vez
odev addon-install ventas_custom

# 4. Hacer cambios en modelos Python o datos XML
#    ...

# 5. Actualizar el modulo para aplicar los cambios
odev update ventas_custom

# 6. Ejecutar tests para verificar
odev test ventas_custom

# 7. Repetir desde el paso 4
```

---

## 6. Gestion de Base de Datos

### Crear un snapshot

```bash
odev db snapshot instalacion-limpia
```

Salida esperada:

```
[INFO] Creando snapshot de 'odoo_db'...
[OK]   Snapshot guardado: instalacion-limpia_20260319_143022.dump (45.2 MB)
```

El snapshot se guarda como un dump de PostgreSQL en formato custom dentro del directorio `snapshots/` del proyecto. El nombre del archivo incluye un timestamp, asi que podes tener multiples snapshots con el mismo prefijo.

**Cuando crear snapshots:**
- Antes de instalar un modulo nuevo
- Antes de cargar un backup de produccion
- Despues de una instalacion limpia que funciona bien
- Antes de experimentar con cambios destructivos

### Restaurar un snapshot

```bash
odev db restore instalacion-limpia
```

El comando busca el snapshot por nombre exacto o por prefijo (retorna el mas reciente que coincida). El proceso completo es:

1. Pide confirmacion (operacion destructiva)
2. Detiene el servicio web para liberar conexiones a la BD
3. Elimina la base de datos actual
4. Crea una nueva base de datos vacia
5. Restaura el dump con `pg_restore`
6. Reinicia el servicio web

### Listar snapshots disponibles

```bash
odev db list
```

Salida esperada:

```
       Snapshots de Base de Datos
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Nombre                             ┃ Fecha               ┃  Tamano  ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ instalacion-limpia_20260319_143022 │ 2026-03-19 14:30:22 │  45.2 MB │
│ pre-migracion_20260318_091500      │ 2026-03-18 09:15:00 │ 120.8 MB │
└────────────────────────────────────┴─────────────────────┴──────────┘
```

### Anonimizar datos

```bash
odev db anonymize
```

Este comando ejecuta un script SQL que:
- Reemplaza nombres de partners con datos ficticios
- Reemplaza emails con direcciones generadas
- Reemplaza numeros de telefono
- Reemplaza direcciones
- Resetea las passwords de todos los usuarios a `admin`

Ideal para trabajar con copias de bases de datos de produccion sin exponer datos personales reales.

> **Nota:** El comando pide confirmacion antes de ejecutar. La operacion es irreversible; haz un snapshot antes si queres poder volver atras.

### Cargar un backup externo

```bash
odev load-backup /ruta/al/backup.zip
```

Acepta backups en formato `.zip` de Odoo.sh o del Database Manager de Odoo. El zip debe contener `dump.sql` (SQL plano) o `dump.dump` (formato custom de PostgreSQL), y opcionalmente un directorio `filestore/`.

El proceso completo es:

1. Valida que el archivo es un `.zip` valido con un dump dentro
2. Muestra informacion del backup (tamano, tipo de dump, si tiene filestore)
3. Pide confirmacion
4. Extrae el backup a un directorio temporal
5. Detiene los servicios web y pgweb para liberar conexiones
6. Elimina y recrea la base de datos
7. Restaura el dump SQL
8. Copia el filestore al volumen de datos de Odoo (si existe)
9. Neutraliza la base de datos (desactiva crons, servidores de correo, etc.)
10. Resetea las credenciales de admin a `admin` / `admin`
11. Reinicia todos los servicios

Para omitir la neutralizacion:

```bash
odev load-backup /ruta/al/backup.zip --no-neutralize
```

### Reiniciar la base de datos desde cero

```bash
odev reset-db
```

Esta es la opcion nuclear: elimina **todos** los volumenes Docker (base de datos, filestore, todo) y levanta el entorno desde cero con una base de datos virgen.

Internamente ejecuta `docker compose down -v` seguido de `docker compose up -d`.

> **Nota:** El comando pide confirmacion. No hay vuelta atras despues de confirmar, a menos que tengas un snapshot guardado.

---

## 7. Multiples Proyectos Simultaneos

odev permite ejecutar varios proyectos Odoo al mismo tiempo sin conflictos de puertos.

### Como funciona la auto-deteccion de puertos

Cuando ejecutas `odev init`, el sistema verifica la disponibilidad de los puertos base:

| Servicio | Puerto base |
|----------|-------------|
| Odoo (web) | 8069 |
| pgweb | 8081 |
| PostgreSQL | 5432 |
| debugpy | 5678 |

Si alguno de los puertos base esta ocupado, odev incrementa **todos** los puertos del conjunto en 1 y vuelve a verificar. Repite esto hasta encontrar un set completo disponible (con un limite de 100 intentos).

### Ejemplo: dos proyectos simultaneos

```bash
# Proyecto A: toma los puertos base
odev init proyecto-a --no-interactive
cd proyecto-a && odev up
# Odoo en 8069, pgweb en 8081, DB en 5432

# Proyecto B: detecta que los puertos base estan ocupados, usa offset +1
cd ..
odev init proyecto-b --no-interactive
cd proyecto-b && odev up
# Odoo en 8070, pgweb en 8082, DB en 5433
```

Resultado:

```
Proyecto A: http://localhost:8069  (pgweb en :8081)
Proyecto B: http://localhost:8070  (pgweb en :8082)
```

### Aislamiento con COMPOSE_PROJECT_NAME

Cada proyecto tiene su propio `COMPOSE_PROJECT_NAME` definido en el `.env`, lo que garantiza que los contenedores y volumenes Docker estan completamente aislados entre proyectos.

### Verificar que puertos usa cada proyecto

Desde el directorio de cada proyecto:

```bash
odev status
```

Esto muestra la tabla de servicios con los puertos publicados de ese proyecto.

Tambien podes verificar directamente en el `.env`:

```bash
grep PORT .env
```

---

## 8. Dashboard Interactivo (TUI)

### Iniciar la TUI

```bash
odev tui
```

> **Nota:** Si Textual no esta instalado, el comando te indica como instalarlo: `pip install odev[tui]`.

La TUI muestra tres paneles:

- **Panel de estado** (arriba izquierda): Estado en vivo de los servicios Docker con auto-refresco. Muestra contenedor, estado, salud y puertos.
- **Barra de acciones** (arriba derecha): Referencia rapida de los atajos de teclado disponibles.
- **Visor de logs** (abajo): Streaming de logs de Odoo en tiempo real.

El titulo de la ventana muestra el nombre del proyecto y la version de Odoo.

### Atajos de teclado

| Tecla | Accion |
|-------|--------|
| `U` | Levantar servicios (docker compose up) |
| `D` | Detener servicios (docker compose down) |
| `R` | Reiniciar el contenedor web de Odoo |
| `S` | Abrir shell bash en el contenedor (sale de la TUI temporalmente) |
| `C` | Generar PROJECT_CONTEXT.md |
| `Q` | Salir de la TUI |

### Cuando usar la TUI vs. comandos CLI

- **Usa la TUI** cuando quieras monitorear logs mientras realizas acciones rapidas, o cuando estes haciendo desarrollo activo y necesites reiniciar Odoo frecuentemente.
- **Usa los comandos CLI** para operaciones especificas y en scripts de automatizacion.

---

## 9. Diagnostico del Entorno

### Ejecutar diagnosticos

```bash
odev doctor
```

Este comando ejecuta una serie de verificaciones sobre tu sistema y el proyecto actual, mostrando resultados con indicadores de color:

- `[OK]` (verde): Verificacion exitosa
- `[WARN]` (amarillo): Advertencia, no bloqueante
- `[FAIL]` (rojo): Problema que impide el funcionamiento
- `[INFO]` (azul): Informacion adicional

### Que verifica

| Verificacion | Que busca |
|--------------|-----------|
| Docker | Que este instalado y responda |
| Docker Compose v2 | Que el comando `docker compose` funcione |
| Python | Que la version sea 3.10+ |
| Proyecto | Si detecta un proyecto odev (PROJECT, LEGACY o NONE) |
| `.env` | Que el archivo de variables de entorno exista |
| `docker-compose.yml` | Que el archivo de servicios Docker exista |
| `config/odoo.conf` | Que la configuracion de Odoo exista (se regenera automaticamente) |
| `addons/` | Cantidad de modulos Odoo encontrados |
| Puertos | Que los puertos configurados esten disponibles |
| Version compatible | Que la version de odev cumpla con `odev_min_version` del proyecto |

### Ejemplo de salida

```
Diagnostico del entorno odev
========================================

  [OK]   Docker instalado (Docker version 27.5.1, build 9f9e405)
  [OK]   Docker Compose v2 disponible (Docker Compose version v2.32.4)
  [OK]   Python 3.12.3
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

### Como solucionar problemas comunes que reporta doctor

**Puerto en uso:**
```
  [FAIL] Puerto 8069 (Odoo) ya esta en uso por otro proceso.
```
Solucion: Otro proceso esta usando ese puerto. Busca cual es y detenlo, o cambia el puerto en el `.env`.

**Proyecto no detectado:**
```
  [INFO] No se detecto proyecto odev en el directorio actual.
```
Solucion: Asegurate de estar en el directorio raiz del proyecto (donde esta `.odev.yaml`), o ejecuta `odev init` para crear uno.

**Proyecto legacy:**
```
  [WARN] Proyecto legacy detectado. Ejecuta 'odev migrate' para migrar.
```
Solucion: Ejecuta `odev migrate` para convertir al nuevo formato (ver seccion 11).

---

## 10. Generacion de Contexto para AI

### Generar el archivo de contexto

```bash
odev context
```

Salida esperada:

```
[OK] Generado PROJECT_CONTEXT.md con 3 modulo(s).
```

### Que contiene PROJECT_CONTEXT.md

El comando escanea el directorio `addons/` y genera un documento Markdown detallado que incluye, para cada modulo:

- **Nombre tecnico y humano** (desde `__manifest__.py`)
- **Version y dependencias**
- **Modelos** con sus campos (analizados via AST, sin ejecutar codigo)
- **Cantidad de vistas XML** (registros `ir.ui.view`)
- **Cantidad de tests** (metodos `test_*`)
- **Si tiene controladores HTTP**
- **Cantidad de reportes** (`ir.actions.report`)
- **Cantidad de wizards** (clases `TransientModel`)

### Cuando regenerar

Regenera `PROJECT_CONTEXT.md` cada vez que:
- Agregues un modulo nuevo
- Modifiques modelos (nuevos campos, nuevas clases)
- Cambies la estructura de un modulo (nuevos controllers, wizards, etc.)

### Como ayuda a los asistentes de IA

El archivo `PROJECT_CONTEXT.md` proporciona a asistentes como Claude o Copilot un mapa completo del proyecto: que modulos hay, que modelos definen, como se relacionan entre si. Esto permite que el asistente genere codigo mas preciso y contextualizado sin tener que leer cada archivo individualmente.

> **Nota:** El archivo esta incluido en `.gitignore` por defecto, ya que se genera automaticamente y puede quedar desactualizado.

---

## 11. Migracion desde odoo-dev-env

### A quien aplica

Si tenes un proyecto que usa el layout viejo `odoo-dev-env` (donde el repositorio de la herramienta ES el proyecto, con un directorio `cli/` que contiene el CLI), podes migrarlo al nuevo formato independiente.

### Ejecutar la migracion

```bash
# 1. Instalar odev globalmente
pip install odev

# 2. Ir al directorio del proyecto legacy
cd /ruta/a/mi-proyecto-odoo-dev-env

# 3. Ejecutar la migracion
odev migrate
```

### Que hace el comando migrate

1. **Crea `.odev.yaml`** leyendo la configuracion existente del `.env` (version de Odoo, imagenes Docker, nombre del proyecto, si tiene enterprise).

2. **Actualiza `.gitignore`**: remueve la linea que ignora `addons/` (en el layout viejo, los addons no se trackeaban en git; en el nuevo, si se trackean).

3. **Genera archivos faltantes**:
   - `CLAUDE.md` con instrucciones para asistentes de IA
   - `.env.example` con los valores actuales del `.env` (reemplazando passwords con placeholders)
   - Directorios `docs/`, `snapshots/`, `logs/` con `.gitkeep`

### Pasos manuales post-migracion

```bash
# Revisar los cambios
git diff

# Agregar los nuevos archivos y los addons al tracking
git add .odev.yaml addons/

# Hacer commit
git commit -m "feat: migrar a formato de proyecto independiente"
```

> **Nota:** Si `addons/` tiene modulos, ahora se trackean en git. Revisalos antes de hacer commit para asegurarte de que no incluyan archivos innecesarios.

---

## 12. Configuracion Avanzada

### .odev.yaml

Este es el archivo de configuracion principal del proyecto. odev lo usa para detectar que un directorio es un proyecto y para leer metadatos del mismo.

```yaml
# Version minima de odev requerida por este proyecto
odev_min_version: "0.1.0"

odoo:
  # Version de Odoo (17.0, 18.0, 19.0)
  version: "19.0"
  # Imagen Docker de Odoo a usar
  image: "odoo:19"

database:
  # Imagen Docker de PostgreSQL (pgvector incluye extensiones)
  image: "pgvector/pgvector:pg16"

enterprise:
  # Si se montan los addons enterprise
  enabled: false
  # Ruta relativa al directorio enterprise
  path: "./enterprise"

services:
  # Habilitar pgweb (visor web de PostgreSQL)
  pgweb: true

project:
  # Nombre del proyecto (usado en Docker Compose y mensajes)
  name: "mi-proyecto"
  # Descripcion libre del proyecto
  description: ""

sdd:
  # Habilitar flujo Spec-Driven Development
  enabled: true
  # Idioma de la documentacion SDD
  language: "es"
```

| Campo | Descripcion |
|-------|-------------|
| `odev_min_version` | Si tu CLI es mas vieja que esta version, `odev doctor` te avisa |
| `odoo.version` | Version semantica de Odoo |
| `odoo.image` | Tag de la imagen Docker para el contenedor web |
| `database.image` | Tag de la imagen Docker para PostgreSQL |
| `enterprise.enabled` | Si montar `./enterprise` como volumen en el contenedor |
| `services.pgweb` | Si incluir el servicio pgweb en docker-compose.yml |
| `project.name` | Nombre del proyecto, usado como `COMPOSE_PROJECT_NAME` |
| `sdd.enabled` | Si usar el flujo de Spec-Driven Development |

### .env

Archivo de variables de entorno que alimenta `docker-compose.yml` y la generacion de `odoo.conf`. Se crea con `odev init` y **no se commitea** (esta en `.gitignore`).

| Variable | Default | Descripcion |
|----------|---------|-------------|
| `PROJECT_NAME` | Nombre del proyecto | Nombre para Docker Compose |
| `ODOO_VERSION` | `19.0` | Version de Odoo |
| `ODOO_IMAGE_TAG` | `19` | Tag de la imagen Docker de Odoo |
| `ODOO_IMAGE` | `odoo:19` | Imagen completa de Odoo |
| `DB_IMAGE_TAG` | `16` | Version de PostgreSQL |
| `DB_IMAGE` | `pgvector/pgvector:pg16` | Imagen completa de PostgreSQL |
| `WEB_PORT` | `8069` | Puerto HTTP de Odoo en el host |
| `PGWEB_PORT` | `8081` | Puerto de pgweb en el host |
| `DB_PORT` | `5432` | Puerto de PostgreSQL en el host |
| `DB_HOST` | `db` | Hostname interno del servicio de BD |
| `DB_NAME` | `odoo_db` | Nombre de la base de datos |
| `DB_USER` | `odoo` | Usuario de PostgreSQL |
| `DB_PASSWORD` | `odoo` | Password de PostgreSQL |
| `LOAD_LANGUAGE` | `en_US` | Idioma a instalar automaticamente |
| `WITHOUT_DEMO` | `all` | `all` = sin datos demo, vacio = con datos demo |
| `DEBUGPY` | `False` | `True` para habilitar depuracion remota en puerto 5678 |
| `DEBUGPY_PORT` | `5678` | Puerto de debugpy en el host |
| `ADMIN_PASSWORD` | `admin` | Master password de Odoo |
| `INIT_MODULES` | (vacio) | Modulos a instalar al iniciar |

Para compartir la configuracion con tu equipo, usa `.env.example`:

```bash
# El equipo clona el repo y copia el ejemplo
cp .env.example .env
# Luego edita los valores sensibles (passwords)
```

### config/odoo.conf

La configuracion de Odoo se genera automaticamente a partir de las variables del `.env`. Cada vez que ejecutas `odev up`, si el `.env` es mas reciente que `odoo.conf`, se regenera.

No necesitas editar este archivo manualmente. Si necesitas cambiar algo, modifica el `.env` y ejecuta `odev up` de nuevo.

Este archivo esta en `.gitignore` porque contiene passwords y se genera dinamicamente.

### Enterprise addons

Si tu proyecto necesita addons enterprise de Odoo:

1. En el wizard de `odev init`, responde "Si" a "Habilitar enterprise addons"
2. Coloca los addons enterprise en el directorio `enterprise/` del proyecto
3. El directorio se monta automaticamente en `/mnt/enterprise-addons` dentro del contenedor

```bash
# Clonar los addons enterprise (necesitas acceso al repo privado de Odoo)
git clone git@github.com:odoo/enterprise.git --branch 19.0 --depth 1 enterprise/
```

El directorio `enterprise/` esta en `.gitignore` porque los addons enterprise son propiedad de Odoo SA y no deben redistribuirse.

### Debugpy para VS Code

Para depurar Odoo de forma remota con VS Code:

1. Asegurate de que `DEBUGPY=True` en el `.env` (o habilitalo en el wizard de `odev init`)
2. El debugger escucha en el puerto configurado en `DEBUGPY_PORT` (default: 5678)
3. En VS Code, crea un archivo `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Odoo: Attach",
      "type": "debugpy",
      "request": "attach",
      "connect": {
        "host": "localhost",
        "port": 5678
      },
      "pathMappings": [
        {
          "localRoot": "${workspaceFolder}/addons",
          "remoteRoot": "/mnt/extra-addons"
        }
      ]
    }
  ]
}
```

4. Ejecuta `odev up` y luego "Start Debugging" en VS Code

### .pre-commit-config.yaml

El proyecto incluye hooks de pre-commit configurados con **ruff** para linting y formateo de codigo Python. Se ejecutan automaticamente antes de cada `git commit`.

Para instalar los hooks:

```bash
pip install pre-commit
pre-commit install
```

---

## 13. Referencia Rapida de Comandos

### Comandos principales

| Comando | Descripcion | Flags principales |
|---------|-------------|-------------------|
| `odev init [nombre]` | Crear un nuevo proyecto Odoo | `--no-interactive`, `--odoo-version`/`-v` |
| `odev up` | Levantar el entorno de desarrollo | `--build`, `--watch` |
| `odev down` | Detener y eliminar contenedores | `-v`/`--volumes` (elimina datos) |
| `odev restart` | Reiniciar el contenedor de Odoo | (sin flags) |
| `odev status` | Mostrar estado de los servicios | (sin flags) |
| `odev logs [servicio]` | Ver logs de un servicio | `--tail`/`-n`, `--no-follow` |
| `odev shell` | Abrir shell bash en el contenedor | (sin flags) |
| `odev scaffold <nombre>` | Crear un modulo Odoo nuevo | (sin flags) |
| `odev addon-install <modulo>` | Instalar un modulo por primera vez | (sin flags) |
| `odev update <modulo>` | Actualizar (upgrade) un modulo | (sin flags) |
| `odev test <modulo>` | Ejecutar tests de un modulo | `--log-level`/`-l` |
| `odev reset-db` | Destruir BD y volumenes, reiniciar | (pide confirmacion) |
| `odev load-backup <ruta.zip>` | Cargar backup de Odoo.sh | `--no-neutralize` |
| `odev context` | Generar PROJECT_CONTEXT.md | (sin flags) |
| `odev tui` | Abrir el dashboard interactivo | (sin flags) |
| `odev migrate` | Migrar proyecto legacy al nuevo formato | (sin flags) |
| `odev doctor` | Diagnosticar el entorno | (sin flags) |
| `odev self-update` | Actualizar odev a la ultima version | (sin flags) |

### Subcomandos de base de datos

| Comando | Descripcion | Detalles |
|---------|-------------|----------|
| `odev db snapshot <nombre>` | Crear snapshot de la BD | Dump en formato custom, con timestamp |
| `odev db restore <nombre>` | Restaurar desde snapshot | Busca por nombre exacto o prefijo |
| `odev db list` | Listar snapshots disponibles | Tabla con nombre, fecha y tamano |
| `odev db anonymize` | Anonimizar datos personales | Reemplaza PII, resetea passwords |

### Flags globales

| Flag | Descripcion |
|------|-------------|
| `--version` / `-V` | Mostrar la version de odev |
| `--help` | Mostrar ayuda del comando |

---

## 14. Solucion de Problemas

### "Puerto en uso"

**Sintoma:** `odev doctor` reporta que un puerto esta ocupado, o `odev up` falla con un error de bind.

**Solucion:**

```bash
# Buscar que proceso usa el puerto (ej. 8069)
sudo lsof -i :8069
# o
sudo ss -tlnp | grep 8069

# Si es otro proyecto odev, detenerlo desde su directorio
cd /ruta/al/otro/proyecto && odev down

# Si es otro proceso, matarlo
kill <PID>

# Alternativa: cambiar el puerto en el .env
# Editar WEB_PORT=8070 en .env y ejecutar odev up
```

### "No se encontro un proyecto odev"

**Sintoma:** Casi todos los comandos fallan con este mensaje.

**Solucion:**
- Asegurate de estar en el directorio raiz del proyecto (donde esta `.odev.yaml` o `docker-compose.yml`).
- Si no tenes un proyecto, crea uno con `odev init`.
- odev busca hacia arriba en el arbol de directorios, asi que tambien funciona desde subdirectorios del proyecto.

### "Docker no esta corriendo"

**Sintoma:** `odev doctor` reporta que Docker no responde.

**Solucion:**

```bash
# En Linux
sudo systemctl start docker

# En macOS/Windows
# Abre Docker Desktop y asegurate de que este corriendo

# Verificar
docker info
```

### "Odoo no arranca"

**Sintoma:** El contenedor web se inicia pero Odoo no responde en el navegador, o el estado aparece como "unhealthy".

**Solucion:**

```bash
# Ver los logs del contenedor web para identificar el error
odev logs web --no-follow

# Errores comunes en los logs:
# - "database does not exist" → ejecutar odev reset-db
# - "relation does not exist" → la BD esta corrupta, ejecutar odev reset-db
# - "port already in use" → Odoo intenta usar un puerto interno ocupado
# - Error de modulo → desinstalar o corregir el modulo problematico
```

Si el problema persiste, intenta reconstruir las imagenes:

```bash
odev down
odev up --build
```

### "Modulo no se instala"

**Sintoma:** `odev addon-install mi_modulo` falla o el modulo no aparece en Odoo.

**Solucion:**
- Verifica que el archivo `addons/mi_modulo/__manifest__.py` exista y sea un diccionario de Python valido.
- Verifica que el directorio del modulo este dentro de `addons/` (no en un subdirectorio anidado).
- Verifica que `addons/` este montado correctamente. Podes comprobarlo entrando al contenedor:

```bash
odev shell
ls /mnt/extra-addons/
```

- Revisa los logs para ver si hay errores de importacion:

```bash
odev logs web --no-follow | grep -i error
```

### "Tests fallan"

**Sintoma:** `odev test mi_modulo` muestra errores.

**Causas comunes:**
- **`TransactionCase` vs `HttpCase`**: Si tus tests hacen requests HTTP, necesitas usar `HttpCase`.
- **Datos faltantes**: Los tests corren con `--stop-after-init`, asi que asegurate de que las dependencias del modulo esten instaladas.
- **Modulo desactualizado**: Ejecuta `odev update mi_modulo` antes de los tests para asegurar que el esquema de BD este al dia.
- **Error en `__init__.py`**: Verifica que `tests/__init__.py` importa correctamente los archivos de test.

```bash
# Para ver mas detalle de los errores
odev test mi_modulo --log-level debug
```

### "config/odoo.conf no existe"

**Sintoma:** `odev doctor` lo reporta como advertencia.

**Solucion:** No es un problema critico. El archivo se regenera automaticamente la proxima vez que ejecutes `odev up`. Si queres generarlo manualmente, simplemente ejecuta:

```bash
odev up
odev down
```

### "odev version menor a la requerida"

**Sintoma:** `odev doctor` advierte que tu version de odev es menor a `odev_min_version` del proyecto.

**Solucion:**

```bash
odev self-update
# o manualmente
pip install --upgrade odev
```
