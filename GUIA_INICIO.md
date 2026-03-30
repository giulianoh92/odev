# Guía de Inicio: odev

**Una guía completa para principiantes en desarrollo Odoo con Docker**

Si acabas de empezar con odev, esta guía te llevará de cero a un entorno Odoo completamente funcional en unos 15 minutos. No necesitas conocimiento previo de Docker ni Odoo.

---

## Tabla de Contenidos

1. [¿Qué es odev?](#qué-es-odev)
2. [Instalación](#instalación)
3. [Crear tu Primer Proyecto](#crear-tu-primer-proyecto)
4. [Iniciar y Detener Servicios](#iniciar-y-detener-servicios)
5. [Ver Estado y Logs](#ver-estado-y-logs)
6. [Crear tu Primer Módulo](#crear-tu-primer-módulo)
7. [Flujo de Trabajo Básico](#flujo-de-trabajo-básico)
8. [Gestión de Base de Datos](#gestión-de-base-de-datos)
9. [Usar Módulos Enterprise](#usar-módulos-enterprise)
10. [Múltiples Proyectos](#múltiples-proyectos)
11. [Configuración](#configuración)
12. [Solución de Problemas](#solución-de-problemas)

---

## ¿Qué es odev?

**odev es un kit de herramientas que te da un entorno Odoo completo dentro de Docker.**

En lugar de instalar Odoo manualmente en tu computadora (lo que es complicado), odev maneja toda la complejidad de Docker por ti. Es como comparar:

```
Forma tradicional:    Instalar Python → PostgreSQL → Odoo → Configurar todo
Forma con odev:       odev init mi-proyecto → odev up
```

Beneficios clave:
- ✅ **Proyectos aislados** — Cada proyecto tiene su propia BD, puertos y contenedores
- ✅ **Setup de un comando** — Sin configuración compleja
- ✅ **Recarga en caliente** — Edita código, recarga el navegador, verás cambios al instante
- ✅ **Snapshots de BD** — Guarda/restaura el estado de la BD
- ✅ **Múltiples proyectos** — Ejecuta 3+ proyectos Odoo simultáneamente sin conflictos
- ✅ **Pre-configurado** — Git, pre-commit hooks, pipeline CI incluidos

---

## Instalación

### Requisitos Previos

Necesitas dos cosas en tu computadora:

1. **Python 3.10+** (se recomienda 3.12)
   ```bash
   python3 --version
   ```
   Si no lo tienes, instálalo desde [python.org](https://www.python.org)

2. **Docker** con Docker Compose v2
   - **Mac/Windows:** Instala [Docker Desktop](https://www.docker.com/products/docker-desktop)
   - **Linux:** Sigue [Docker Engine](https://docs.docker.com/engine/install/) + [Docker Compose Plugin](https://docs.docker.com/compose/install/linux/)

   Verifica:
   ```bash
   docker --version
   docker compose version
   ```

### Instalar odev

Elige uno de estos métodos:

**Opción 1: Instalación Simple (recomendado)**
```bash
pip install git+https://github.com/giulianoh92/odev.git
```

**Opción 2: Instalación Aislada (más seguro)**
```bash
pipx install git+https://github.com/giulianoh92/odev.git
```

**Opción 3: Para Contribuidores (desarrollo)**
```bash
git clone https://github.com/giulianoh92/odev.git
cd odev
pip install -e ".[dev]"
```

### Verificar Instalación

```bash
odev --version
odev --help
```

Deberías ver el número de versión y una lista de comandos.

---

## Crear tu Primer Proyecto

### Paso 1: Setup Interactivo

La forma más fácil es dejar que odev te haga preguntas:

```bash
odev init mi-primer-proyecto
```

Te preguntará:

```
¿Versión de Odoo? [17.0 / 18.0 / 19.0]: 19.0
¿Nombre de base de datos? [odoo_db]: mi_base_datos
¿Puerto web? [8069]: 8069
¿Habilitar pgweb (navegador de BD)? [s/n]: s
¿Habilitar módulos Enterprise? [s/n]: n
¿Habilitar debugpy (depurador remoto)? [s/n]: n
```

Presiona Enter para aceptar valores por defecto, o escribe tu elección.

### Paso 2: Navega al Proyecto

```bash
cd mi-primer-proyecto
```

Dentro encontrarás:

```
mi-primer-proyecto/
├── addons/                  ← Tus módulos personalizados van aquí
├── config/
│   └── odoo.conf            ← Auto-generado (edita odev.yaml en su lugar)
├── docker-compose.yml       ← Auto-generado (edita odev.yaml en su lugar)
├── entrypoint.sh            ← Auto-generado
├── .odev.yaml               ← Configuración del proyecto (EDITA ESTO)
├── .env                     ← Variables de entorno (mantén privado)
├── .env.example             ← Comparte esto con tu equipo
├── .gitignore               ← Reglas de ignorar en Git
├── .pre-commit-config.yaml  ← Verificaciones de calidad de código
├── pyproject.toml           ← Configuración de herramientas Python
├── CLAUDE.md                ← Instrucciones para asistentes de IA
└── .github/
    └── workflows/
        └── ci.yml           ← Pipeline CI opcional
```

### Paso 3 (Opcional): Setup No-Interactivo

Si quieres valores por defecto sin preguntas:

```bash
odev init mi-proyecto --no-interactive
```

---

## Iniciar y Detener Servicios

### Inicia tu Entorno de Desarrollo

```bash
odev up
```

Esto hará:
1. Construir imágenes Docker (primera vez, toma ~2-3 minutos)
2. Crear base de datos PostgreSQL
3. Iniciar servidor web Odoo
4. Configurar pgweb (si está habilitado)
5. Descargar paquetes Python requeridos

Después del inicio, verás:

```
✓ Web Odoo: http://localhost:8069
✓ pgweb: http://localhost:8081 (opcional)
```

Abre tu navegador en `http://localhost:8069` e ingresa con:
- **Usuario:** admin
- **Contraseña:** admin

### Detener Todo

```bash
odev down
```

Detiene todos los contenedores pero mantiene tu base de datos.

### Reiniciar Sin Reconstruir

```bash
odev restart
```

Útil cuando quieres reiniciar Odoo pero mantener la BD ejecutándose.

---

## Ver Estado y Logs

### Ver Estado de Servicios

```bash
odev status
```

Muestra:

```
Servicio    Estado      Salud       Puertos
────────────────────────────────────────────
web         running     healthy     8069
db          running     healthy     5432
pgweb       running     healthy     8081
```

### Ver Logs en Vivo

Sigue los logs de Odoo en tiempo real:

```bash
odev logs
```

Sigue los logs de la base de datos:

```bash
odev logs db
```

Sigue todos los servicios:

```bash
odev logs all
```

Presiona `Ctrl+C` para dejar de seguir.

### Dashboard Interactivo

Para un dashboard visual completo:

```bash
odev tui
```

Muestra estado, logs y atajos de teclado rápidos.

---

## Crear tu Primer Módulo

### Generar Esqueleto de Módulo

```bash
odev scaffold mi_modulo
```

Esto crea:

```
addons/mi_modulo/
├── __init__.py
├── __manifest__.py          ← Metadatos del módulo
├── models/
│   ├── __init__.py
│   └── mi_modulo.py         ← Tu primer modelo (tabla de BD)
├── views/
│   └── mi_modulo_views.xml  ← Vistas Lista/Formulario/Búsqueda
├── security/
│   └── ir.model.access.csv  ← Permisos de usuario
└── tests/
    ├── __init__.py
    └── test_mi_modulo.py    ← Pruebas unitarias
```

### Instalar el Módulo

```bash
odev addon-install mi_modulo
```

Luego:
1. Abre Odoo en el navegador
2. Ve al menú **Aplicaciones** (arriba a la izquierda)
3. Busca **Mi Módulo**
4. Haz clic en **Instalar**

### Actualizar Después de Cambios de Código

Después de editar modelos Python o datos XML:

```bash
odev update mi_modulo
```

Luego recarga tu navegador.

### Para Cambios en XML/QWeb/JS

Solo recarga tu navegador — odev recarga en caliente automáticamente.

### Ejecutar Pruebas

```bash
odev test mi_modulo
```

Todas las pruebas deberían pasar.

---

## Flujo de Trabajo Básico

Así es cómo trabajarás día a día:

```bash
# 1. Inicia el entorno
odev up

# 2. Edita archivos en addons/mi_modulo/
#    • Modelos Python: cambios toman efecto después de odev update
#    • Vistas XML: cambios se ven después de recarga del navegador
#    • JS: cambios se ven después de recarga del navegador

# 3. Prueba tus cambios
odev test mi_modulo

# 4. Ver logs si algo se daña
odev logs

# 5. Cuando termines
odev down
```

### Ediciones Típicas

**Editar un Modelo Python:**
```python
# addons/mi_modulo/models/mi_modulo.py
class MiModelo(models.Model):
    _name = "mi.modulo"

    nombre = fields.Char("Nombre")
    activo = fields.Boolean(default=True)
```

Luego ejecuta:
```bash
odev update mi_modulo
```

**Editar una Vista:**
```xml
<!-- addons/mi_modulo/views/mi_modulo_views.xml -->
<form string="Mi Formulario">
    <field name="nombre"/>
    <field name="activo"/>
</form>
```

Solo recarga tu navegador.

---

## Gestión de Base de Datos

### Guardar Snapshots de BD

En cualquier momento, guarda el estado de tu BD:

```bash
odev db snapshot instalacion-limpia
```

Puedes tener múltiples snapshots:

```bash
odev db snapshot despues-de-importar
odev db snapshot antes-de-probar
```

### Restaurar desde Snapshot

```bash
odev db restore instalacion-limpia
```

Revierte instantáneamente a ese estado exacto.

### Listar Snapshots

```bash
odev db list
```

Muestra todos los snapshots guardados con marca de tiempo y tamaño.

### Cargar Base de Datos de Producción

Para probar con datos reales de producción:

```bash
odev load-backup /ruta/a/backup.zip
```

odev hará:
1. Extraer el backup
2. Reemplazar tu BD
3. Remover datos sensibles (trabajos cron, servidores de correo, resetear contraseñas)
4. Establecer contraseña admin a `admin`

Usa `--no-neutralize` si quieres saltar la limpieza de datos.

### Empezar Limpio

Para borrar todo y comenzar de nuevo:

```bash
odev reset-db
```

---

## Usar Módulos Enterprise

Si tienes acceso a Odoo Enterprise, puedes usar módulos enterprise.

### Setup Una Sola Vez

1. **Clona enterprise a una ubicación compartida:**

```bash
# Crear directorio de addons compartido
mkdir -p ~/.odev/addons/enterprise/19.0

# Clonar (necesitas acceso a GitHub)
git clone --branch 19.0 https://github.com/odoo/enterprise.git ~/.odev/addons/enterprise/19.0
```

2. **Configura tu proyecto para usarlo:**

Edita el `.odev.yaml` de tu proyecto:

```yaml
enterprise:
  enabled: true
  path: ~/.odev/addons/enterprise/19.0

addons_paths:
  - ./addons                           # Tus módulos personalizados
  - ~/.odev/addons/enterprise/19.0     # Enterprise compartido
```

3. **Regenera configuración y reinicia:**

```bash
odev sync-config
odev restart
```

### Usar en tu Proyecto

Una vez configurado, los módulos enterprise están disponibles automáticamente:

```bash
# Inicia tu proyecto
odev up

# En Odoo, ve a Aplicaciones y busca módulos enterprise
# (p.ej. "Contabilidad", "Web Grid View", etc.)
```

### Gestionar Enterprise Compartido

Si tienes múltiples proyectos usando el mismo clon de enterprise:

```bash
# Ve cuáles de tus proyectos usan enterprise
odev addons used-by enterprise/19.0

# Actualizar enterprise (afecta todos los proyectos que lo usan)
cd ~/.odev/addons/enterprise/19.0
git pull

# Reinicia cada proyecto
odev restart
```

---

## Múltiples Proyectos

Una de las superpotencias de odev es ejecutar múltiples proyectos simultáneamente.

### Crear Proyecto A

```bash
odev init proyecto-a
cd proyecto-a
odev up
# Se ejecuta en puerto 8069
```

### Crear Proyecto B (en otra terminal)

```bash
odev init proyecto-b
cd proyecto-b
odev up
# Se asigna automáticamente puerto 8070 (ya que 8069 está en uso)
```

Cada proyecto tiene:
- ✅ Base de datos independiente
- ✅ Puertos independientes (8069, 8070, 8071...)
- ✅ Contenedores Docker independientes
- ✅ Volúmenes independientes (sin conflictos de disco)

### Ver Todos los Proyectos

```bash
# En proyecto-a
odev status

# En proyecto-b
odev status
```

Cada uno muestra sus propios puertos.

### Addons Compartidos Entre Proyectos

Si Proyecto A y Proyecto B ambos necesitan enterprise:

```yaml
# .odev.yaml de ambos proyectos
addons_paths:
  - ./addons
  - ~/.odev/addons/enterprise/19.0  # Misma ruta, ambos proyectos la usan
```

Sin duplicación, ahorra espacio en disco.

---

## Configuración

### Configuración del Proyecto (.odev.yaml)

Este es el **único lugar de verdad** para tu proyecto:

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
  description: "Mi primer proyecto Odoo"
```

Después de editar este archivo, regenera las configuraciones:

```bash
odev sync-config
odev restart
```

### Variables de Entorno (.env)

Auto-generado después de `odev init`. Personaliza:

| Variable | Ejemplo | Propósito |
|----------|---------|-----------|
| `ODOO_VERSION` | `19.0` | Versión de Odoo |
| `WEB_PORT` | `8069` | Puerto del servidor web |
| `DB_NAME` | `odoo_db` | Nombre de la BD |
| `DB_USER` | `odoo` | Usuario de la BD |
| `LOAD_LANGUAGE` | `es_AR` | Idioma por defecto |
| `WITHOUT_DEMO` | `all` | Saltar datos de demostración |
| `DEBUGPY` | `False` | Habilitar depurador remoto |

**Mantén `.env` privado** — comparte `.env.example` con tu equipo.

---

## Solución de Problemas

### Odoo No Inicia

**Problema:** `odev up` toma mucho tiempo o falla

**Solución:**
```bash
# Ver qué está pasando
odev logs

# Buscar ERROR en los logs
# Causas comunes: puerto en uso, espacio en disco insuficiente, Docker no ejecutándose
```

**Verificar que Docker está ejecutándose:**
```bash
docker ps
```

Si eso falla, Docker no está ejecutándose. Inicia Docker Desktop o el daemon de Docker.

### Puerto Ya en Uso

**Problema:** `Port 8069 already in use` (Puerto 8069 ya está en uso)

**Solución:**

O bien:
1. Usa un puerto diferente (odev te sugerirá uno)
2. Detén el otro proyecto:
   ```bash
   cd /ruta/a/otro-proyecto
   odev down
   ```

### BD No Se Conecta

**Problema:** `could not translate host name "db" to address`

**Solución:**

Los contenedores no pueden comunicarse. Reinicia todo:

```bash
odev down -v
odev up
```

La bandera `-v` borra todos los volúmenes (BD), así que comienzas limpio.

### Módulo No Instala

**Problema:** `Module not found` (Módulo no encontrado) o `failed to load module` (fallo al cargar módulo)

**Solución:**

```bash
# 1. Verificar sintaxis en __manifest__.py
# 2. Verificar archivo está en addons/mi_modulo/__manifest__.py
# 3. Reiniciar
odev restart

# 4. En Odoo, ve a Configuración → Técnico → Módulos, búscalo
```

### Recarga en Caliente No Funciona

**Problema:** Cambié un archivo pero Odoo no lo detectó

**Solución:**

- **XML/JS:** Solo recarga tu navegador
- **Modelos Python:** Ejecuta `odev update mi_modulo` luego recarga
- **__manifest__.py:** Ejecuta `odev restart`

### No Puedo Conectar al Navegador de BD

**Problema:** No puedo acceder a pgweb en puerto 8081

**Solución:**

1. Verificar si está habilitado:
   ```bash
   odev status
   ```
   Si pgweb no está listado, habilítalo en `.odev.yaml`:
   ```yaml
   services:
     pgweb: true
   ```

2. Regenera y reinicia:
   ```bash
   odev sync-config
   odev restart
   ```

### Espacio en Disco se Agota

**Problema:** Los contenedores Docker ocupan mucho espacio

**Solución:**

Los snapshots de BD e imágenes Docker usan espacio. Limpia:

```bash
# Remover todos los snapshots
rm snapshots/*.dump

# Listar todos los snapshots
odev db list

# Remover snapshot específico
rm snapshots/nombre-snapshot-*.dump
```

---

## Referencia Rápida

### Comandos Más Comunes

| Comando | Qué Hace |
|---------|----------|
| `odev up` | Inicia todo |
| `odev down` | Detiene todo |
| `odev restart` | Reinicia Odoo |
| `odev status` | Muestra estado de servicios |
| `odev logs` | Ve logs en vivo |
| `odev scaffold mi_modulo` | Crea nuevo módulo |
| `odev addon-install mi_modulo` | Instala módulo primera vez |
| `odev update mi_modulo` | Actualiza módulo |
| `odev test mi_modulo` | Ejecuta pruebas |
| `odev db snapshot nombre` | Guarda BD |
| `odev db restore nombre` | Carga BD |
| `odev tui` | Dashboard interactivo |

### Diagnóstico de Entorno

Si algo está mal, ejecuta:

```bash
odev doctor
```

Verifica:
- Docker está instalado
- Docker Compose v2 está disponible
- Versión de Python
- Configuración del proyecto
- Disponibilidad de puertos
- Compatibilidad de versiones

---

## Próximos Pasos

Ahora que conoces lo básico:

1. **Lee el README.md completo** para funciones avanzadas
2. **Crea tu primer módulo** con `odev scaffold mi_app`
3. **Instala el módulo** con `odev addon-install mi_app`
4. **Edita modelos Python** y ejecuta `odev update mi_app`
5. **Crea vistas** en XML
6. **Escribe pruebas** en `tests/test_*.py`
7. **Ejecuta pruebas** con `odev test mi_app`

---

## Obtener Ayuda

### Comandos que te Ayudan a Aprender

```bash
odev --help                    # Listar todos los comandos
odev up --help                 # Ayuda para comando específico
odev doctor                     # Diagnosticar problemas
```

### Documentación

- **README.md** — Referencia completa de funciones
- **~/.odev/addons/README.md** — Protocolo de addons compartidos
- **Project CLAUDE.md** — Instrucciones para asistentes de IA

### Preguntas Frecuentes

**P: ¿Puedo usar odev en Windows?**
R: Sí, instala Docker Desktop. Funciona igual que Mac/Linux.

**P: ¿Puedo tener 10 proyectos ejecutándose a la vez?**
R: Sí, pero cada uno necesita puertos únicos. odev los asigna automáticamente.

**P: ¿Funciona odev con Odoo 17, 18, 19?**
R: Sí. Establece `version` en `.odev.yaml`.

**P: ¿Puedo usarlo para producción?**
R: No, odev es solo para desarrollo. Usa Odoo.sh u hosting administrado para producción.

**P: ¿Necesito saber Docker?**
R: No, odev oculta toda la complejidad de Docker. Solo usas comandos `odev`.

---

## ¡Felicidades! 🎉

Ahora sabes todo lo que necesitas para comenzar a desarrollar con Odoo usando odev.

**La próxima vez que estés atascado:**
1. Ejecuta `odev doctor` para diagnosticar
2. Revisa la sección de solución de problemas arriba
3. Lee el README.md completo
4. Pide ayuda con el mensaje de error exacto

¡Feliz codificación!
