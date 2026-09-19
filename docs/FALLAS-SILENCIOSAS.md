# Fallas silenciosas y asimetrias de guardas

- **Fecha**: 2026-09-19
- **Version base**: 0.10.0
- **Metodo**: inventario de la superficie publica desde el codigo fuente, mas
  verificacion puntual de cada afirmacion contra el archivo que la ejecuta.
- **Convenciones de esfuerzo**: XS < 1h · S 1-4h · M 4h-1d · L 1-3d.

---

## El principio que las une

Todas las fallas de este documento son la misma falla:

> **odev sabe algo que quien lo invoca no sabe, y no lo dice.**

Eso importa mas que de costumbre porque el consumidor principal de odev es un
agente. Una persona que ve un resultado raro abre el log, prueba otra cosa,
sospecha. Un agente toma la salida como verdad, la reporta, y sigue construyendo
sobre ella. Una falla silenciosa no le cuesta tiempo: le cuesta **correccion**.

De ahi el orden de prioridades de este documento. No esta ordenado por cuanto
molesta, sino por **con cuanta confianza hace afirmar algo falso**.

Una falla ruidosa es un inconveniente. Una falla silenciosa es un dato erroneo
que se propaga.

---

## Indice

| # | Prioridad | Problema | Recomendacion | Esfuerzo | Breaking |
|---|---|---|---|---|---|
| A1 | P1 | Una corrida de tests con 0 tests reporta exito | Avisar cuando `total == 0` + lint de descubrimiento | S | no |
| A2 | P1 | `odev_test` por MCP devuelve `ToolError("2")` | Lanzar `ValueError` y convertir en la capa CLI | S | no |
| A3 | P1 | `odev_py` y `odev_status` crashean sin traducir por MCP | Agregar `CalledProcessError` a `FALLOS_OPERATIVOS` | XS | no |
| B1 | P2 | `down -v` destruye volumenes sin ninguna guarda | Confirmacion + `--yes`, igual que sus hermanos | XS | si |
| B2 | P2 | `db anonymize` no se puede automatizar | Agregar `--yes` y `--dry-run` | XS | no |
| B3 | P2 | `db restore` no tiene `--dry-run` | Agregarlo | XS | no |
| C1 | P3 | `doctor` reporta una version hardcodeada | Leer la version real | XS | no |
| C2 | P3 | `doctor` marca FAIL en puertos del propio stack | Reusar `classify_bound_port` de `up` | S | no |
| C3 | P3 | Guardas tempranas rompen el contrato `--json` | Emitir el error en el formato pedido, a stderr | S | no |
| D1 | P4 | `modules --json` es un flag muerto | Implementarlo o eliminarlo | XS | segun |
| D2 | P4 | `odev.yaml` sin punto es invisible al walk inline | Aceptar ambos nombres o avisar | XS | no |
| D3 | P4 | Subcomandos desaparecen en silencio si falla el import | Registrar el fallo | XS | no |
| D4 | P4 | Exit codes inconsistentes con su propio epilogo | Alinear al contrato 0/1/2/3 | S | si |
| E1 | diseno | `odev py` descarta escrituras | Flag `--commit` explicito + lint, nunca commit automatico | S | no |

---

## P1 — Hacen afirmar algo falso

### A1. Una corrida de tests con cero tests reporta exito

**Sintoma.** `odev test <modulo>` termina con exit 0, `failed: 0`, `errors: 0`.
Todo verde. No corrio ni un test.

**Causas.** Son varias y convergen en el mismo silencio:

1. Odoo solo descubre los modulos de test **importados** en el
   `tests/__init__.py` del addon: `get_test_modules` usa
   `inspect.getmembers(mod, inspect.ismodule)`, y un submodulo solo es atributo
   del paquete si alguien lo importo. Un `test_*.py` que nadie importa aporta
   cero tests, sin error ni warning.
2. Un nombre de modulo mal escrito que igual pasa la validacion de addons-path.
3. Una expresion de `--tags` que no matchea nada.
4. Un modulo que legitimamente no tiene tests.

**Por que es la peor de todas.** Un agente que pide correr tests y recibe verde
concluye que el codigo funciona. No hay ninguna senal que lo contradiga. Las
otras fallas de este documento producen un error raro; esta produce **una
afirmacion falsa con formato de exito**.

**Recomendacion.** Dos arreglos complementarios, en este orden:

**(a) Avisar cuando la corrida ejecuto cero tests.** Al terminar, si
`result.total == 0`, emitir un warning por **stderr** nombrando el filtro
efectivo que se uso. Un solo chequeo que cubre las cuatro causas de arriba.

Por stderr y no por stdout, y warning y no error, por dos razones: no contamina
el contrato de `--json`, y cero tests es legitimo en algunos casos. Convertirlo
en exit distinto de cero romperia a quien corre `odev test all` sobre un
proyecto con modulos sin tests.

**(b) Lint de descubrimiento antes de lanzar.** Para cada modulo destino, listar
`<addons>/<modulo>/tests/test_*.py` y compararlos con los nombres realmente
importados en `tests/__init__.py`. Avisar por cada archivo huerfano.

Parsear el `__init__.py` con `ast`, no con regex: hay que manejar
`from . import a, b`, imports condicionales y comentarios. Es la diferencia
entre un lint correcto y uno que miente en la otra direccion.

(a) convierte un exito silencioso en una anomalia visible. (b) dice **por que**.
Si solo entra uno, entra (a): es mas barato y cubre mas causas.

---

### A2. `odev_test` por MCP devuelve `ToolError("2")`

**Sintoma.** Un cliente MCP llama `odev_test` con una combinacion invalida y
recibe un error cuyo mensaje es, literalmente, `2`.

**Causa.** `_execute_test` promete en su docstring `No I/O, no exits` y
`Raises: ValueError`, pero las funciones que llama lanzan `typer.Exit(2)`:
`_parse_test_target` (CSV+colon, `all:Class`), `parsear_modulos_csv`,
`validar_modulos` y `_build_test_tags` (shorthand + `--tags`).

`_anticipado` **si** lo atrapa, porque `typer.Exit` hereda de `RuntimeError` y
eso esta en `FALLOS_OPERATIVOS`. Pero re-lanza `error_cls(str(exc))`, y
`typer.Exit.__init__` nunca llama a `super().__init__(mensaje)`: guarda el codigo
de salida como `args`. Entonces `str(typer.Exit(2))` es `'2'`.

El mensaje accionable — `"Modulos no encontrados: ..."`, `"El shorthand y --tags
no se pueden combinar..."` — se escribio a `sys.stderr`, que bajo transporte
stdio es el log del servidor. El modelo nunca lo ve.

**Por que importa.** Es la capa de traduccion de errores fallando exactamente
en el caso para el que existe. El agente sabe que algo fallo pero no que, asi
que su unica estrategia es probar otra cosa a ciegas.

**Recomendacion.** Que las funciones compartidas lancen `ValueError(mensaje)` y
que la capa CLI lo convierta a stderr + `typer.Exit(2)`. Es exactamente el
patron que `_resolve_contexto` ya usa y documenta como *MCP-safe*: el codigo
compartido senaliza con excepciones de dominio, y cada frontend decide como
presentarlas.

Necesita tests en los dos frentes: que la CLI siga saliendo con 2 y el mismo
texto, y que la tool MCP devuelva un `ToolError` con el mensaje completo.

---

### A3. `odev_py` y `odev_status` crashean sin traducir por MCP

**Sintoma.** Con el stack apagado, esas dos tools no devuelven un error
operativo: el cliente ve `Error executing tool <name>` y el detalle queda en el
log del servidor.

**Causa.** `_execute_py` llama `dc.exec_cmd(...)` y `_execute_status` llama
`dc.ps_parsed()`; ambos terminan en `_run(..., check=True)`, que lanza
`subprocess.CalledProcessError`. Esa clase **no** esta en
`FALLOS_OPERATIVOS = (ValueError, RuntimeError)`, asi que escapa sin traducir.

El docstring de `_execute_py` documenta `Raises: subprocess.CalledProcessError`:
el autor lo sabia, pero el wrapper no lo contempla.

Las otras siete tools estan bien: `_execute_shell`, `_execute_sql`,
`_execute_modules` y `_execute_logs` usan variantes con `check=False`, y
`_execute_model_info` atrapa `CalledProcessError` explicitamente y re-lanza
`RuntimeError`.

**Por que importa.** "El stack esta apagado" es la condicion de error mas comun
que existe, y es perfectamente accionable: el agente solo tiene que correr
`odev up`. Presentarla como un crash le saca justo la informacion que le
permitiria resolverla sola.

**Recomendacion.** Agregar `subprocess.CalledProcessError` a
`FALLOS_OPERATIVOS`. Es una linea, y es correcta conceptualmente: un comando
docker que falla es un fallo operativo, no un bug de odev.

Conviene ademas que `_execute_py` atrape y re-lance `RuntimeError` con un
mensaje util — `"Stack no levantado o DB no disponible"` — igual que ya hace
`_execute_model_info`. El `str()` crudo de un `CalledProcessError` no le dice
nada a nadie.

---

## P2 — Riesgo de perdida de datos y asimetria de guardas

La familia destructiva de odev tiene hoy cuatro formas distintas de protegerse.
Esa inconsistencia **es** el problema: una guarda que no se puede predecir no
protege, porque nadie la interioriza.

| Comando | Destruye | Warning | `confirm` | `--yes` | `--dry-run` |
|---|---|---|---|---|---|
| `down -v` | volumenes: DB + filestore | no | **no** | **no** | si |
| `reset-db` | DB + volumenes, reinicializa | si | si | si | si |
| `load-backup` | pisa DB + filestore | si | si | si | si |
| `db restore` | dropea y recrea la DB | si | si | si | **no** |
| `db anonymize` | PII + todas las passwords | si | si | **no** | **no** |

### B1. `down -v` destruye volumenes sin ninguna guarda

**Sintoma.** `odev down -v` borra los volumenes de DB y filestore sin preguntar
nada. Llega directo a `dc.down(volumes=volumes)`.

**Por que es el filo mas peligroso de la herramienta.** Es el comando destructivo
**mas corto de tipear** y el unico sin confirmacion. Peor: quien aprendio que
`reset-db` y `load-backup` preguntan, generaliza — razonablemente — que odev
pregunta antes de destruir. Esa generalizacion es correcta para cuatro de cinco
comandos. Se rompe justo en el mas facil de ejecutar por accidente.

La asimetria no es un detalle de implementacion. Es lo que hace que la guarda de
los otros comandos sea **enganosa**.

**Recomendacion.** Espejar `reset-db` exactamente: warning nombrando el proyecto
y que se va a destruir, `typer.confirm`, y `-y/--yes` para saltearla. El
`--dry-run` ya existe.

**Sobre el riesgo de romper scripts**, que es la objecion obvia: verificado que
`typer.confirm` con stdin no interactivo lanza `Abort`, no cuelga. Un script que
hoy corre `odev down -v` empezaria a fallar con un mensaje claro en vez de
colgarse esperando input. Falla cerrado, que es el comportamiento correcto para
una operacion irreversible.

Es breaking y hay que anunciarlo como tal. Pero el costo de no hacerlo es
perdida de datos irreversible, y el de hacerlo es agregar `--yes` a unos scripts.
Ademas estamos pre-1.0, que es exactamente cuando corresponde pagar esto.

### B2. `db anonymize` no se puede automatizar

**Sintoma.** No existe `--yes`. La unica forma de scriptearlo es pipear `y` por
stdin.

**Por que importa.** Es al reves de lo que pide el caso de uso. Anonimizar
existe para **preparar una copia segura**: restaurar un dump de produccion,
anonimizarlo, trabajar tranquilo. Eso es una cadena scripteada por definicion.
El unico comando que casi siempre corre dentro de un pipeline es el unico que no
se puede automatizar.

**Recomendacion.** Agregar `-y/--yes` y `--dry-run`, igual que sus hermanos.

### B3. `db restore` no tiene `--dry-run`

**Sintoma.** Tiene `--yes` pero no `--dry-run`, a diferencia de `reset-db` y
`load-backup`.

**Recomendacion.** Agregarlo. Es el ultimo hueco para que la familia destructiva
tenga las cuatro guardas completas y, sobre todo, **predecibles**.

---

## P3 — Diagnosticos falsos y contratos rotos

### C1. `doctor` reporta una version hardcodeada

**Sintoma.** `odev doctor --json` y `mcp__odev__odev_doctor` devuelven siempre
`"version": "0.6.2"`, sin relacion con lo instalado.

**Por que importa.** El primer paso de cualquier diagnostico es establecer que
version se esta mirando. Este campo miente en el comando cuyo unico proposito es
decir la verdad sobre el entorno. Un agente que lo lea va a razonar sobre el
changelog equivocado.

**Recomendacion.** Leer `odev.__version__`, que ya resuelve dinamicamente con
`importlib.metadata`. Una linea. Conviene ademas un test que compare ese campo
contra `importlib.metadata.version("odev")`, justamente porque es la clase de
literal que se vuelve a desincronizar sin que nadie lo note.

### C2. `doctor` marca FAIL en los puertos del propio stack

**Sintoma.** Con el proyecto levantado y sano, `doctor` reporta `[FAIL]` en el
check de puertos.

**Causa.** `_verificar_puertos` hace un `socket.bind` crudo sin distinguir de
quien es el puerto. `odev up` ya resuelve esto bien con `classify_bound_port`,
que separa `free` / `own_running` / `foreign_known` / `foreign_unknown`.

**Por que importa.** Un falso positivo en la herramienta de diagnostico es peor
que no tener diagnostico: ensena a ignorarla. Y el dia que el conflicto de
puertos sea real, ese FAIL ya no significa nada.

**Recomendacion.** Reusar `classify_bound_port`. `own_running` es `ok` o `info`,
nunca `fail`. La logica correcta ya existe en el repo; es unificar, no escribir.

### C3. Las guardas tempranas rompen el contrato `--json`

**Sintoma.** `odev sql "" --json` imprime un `ERROR ...` de Rich en **stdout**
en vez del `{"error": ...}` que el resto del modo JSON respeta.

**Causa.** Las validaciones tempranas usan `error()` de `core.console`, que
escribe con un `rich.console.Console()` plano — o sea stdout — y corren **antes**
de la rama que conoce `--json`. Mismo patron en el rechazo temprano de
`--verbose` en `test`.

**Por que importa.** Un consumidor programatico parsea stdout como JSON y recibe
texto con codigos de color. El parseo explota con un error que no tiene nada que
ver con la causa real, que era un argumento mal pasado.

**Recomendacion.** Mover las validaciones de modo despues de resolver el formato
de salida, o hacer que `error()` respete el formato activo. Lo minimo: que en
modo JSON todo error salga como JSON por stderr. Vale revisar los otros comandos
con `--json`, porque el patron se repite.

---

## P4 — Superficie muerta o enganosa

### D1. `modules --json` es un flag muerto

El flag se declara con default `True` y **el cuerpo de la funcion nunca lee su
valor**: siempre emite JSON. El help promete "output human-readable planificado
para 0.6.0"; van varias minor desde entonces.

**Recomendacion.** Decidir: implementar la salida human-readable, o eliminar el
flag y ajustar el help. Un flag que no hace nada es peor que ausente, porque
quien lo lee cree que tiene una opcion.

### D2. `odev.yaml` sin punto es invisible al walk inline

El walk hacia arriba desde cwd busca **solo** `.odev.yaml` con punto. Un
`odev.yaml` sin punto solo se reconoce cuando el directorio del proyecto ya se
conocia por otra via. Los dos nombres son validos en otras partes del codigo.

**Recomendacion.** Aceptar ambos en el walk, o avisar explicitamente al
encontrar un `odev.yaml` sin punto que no se va a usar como ancla. El estado
actual es un "no encontre proyecto" sobre un directorio que claramente tiene uno.

### D3. Subcomandos que desaparecen en silencio

`adopt`, `reconfigure`, `projects` y `enterprise` se registran dentro de
`try/except ImportError`. Si el import falla, el subcomando simplemente no
existe: `odev adopt` responde "comando desconocido".

**Recomendacion.** Loguear el `ImportError` a stderr en modo `--debug`, y
mencionar los subcomandos no disponibles en `doctor`. La degradacion elegante
esta bien; la degradacion invisible no.

### D4. Exit codes inconsistentes con su propio epilogo

El repo documenta `0` exito, `1` proyecto/runtime, `2` uso, `3` entorno. No se
cumple:

- `scaffold` publica ese epilogo y **nunca** usa 2 ni 3: nombre invalido,
  template faltante y destino existente salen todos con 1.
- `mcp serve` usa **2** para "el paquete `mcp` no esta instalado" y "esta pero es
  pre-2.x", que son problemas de entorno, o sea 3.
- `addon-install` y `update` reenvian el returncode crudo de Odoo, asi que
  pueden devolver cualquier numero.
- `enterprise link` y `projects remove` usan `raise SystemExit(1)` en vez de
  `typer.Exit`, inconsistente con el resto del archivo.

**Por que importa.** El exit code es la unica senal estructurada que tiene un
script antes de parsear nada. Si `1` significa a veces "error de uso" y a veces
"runtime", no se puede automatizar el reintento: son respuestas opuestas.
Reintentar un error de uso es inutil; no reintentar uno de entorno, prematuro.

**Recomendacion.** Alinear al contrato publicado y agregar un test por comando.
Es breaking para quien discrimine por codigo, asi que va agrupado en una minor
y anunciado.

---

## E1 — Decision de diseno: `odev py` y las escrituras

**Estado actual.** `odev py` descarta las escrituras: `odoo/cli/shell.py` ejecuta
`cr.rollback()` despues de cerrar la consola. Hay que terminar con
`env.cr.commit()` para persistir. La documentacion ya dice esto correctamente en
los tres lugares donde antes decia lo contrario.

La pregunta abierta no es si documentarlo, sino si el comportamiento deberia
cambiar.

### Commitear siempre: no

Cuatro razones, en orden de peso:

1. **El uso dominante es de lectura.** `odev py` se usa mayormente para
   inspeccionar: contar registros, mirar un campo, verificar un estado.
   Commitear por default convierte cada expresion exploratoria en una mutacion
   potencial.
2. **Rompe el rollback ante error.** Si la expresion escribe y despues lanza, hoy
   Odoo descarta todo. Con commit automatico habria que decidir si commitear
   estado parcial. Esa atomicidad es una propiedad de seguridad que se estaria
   entregando a cambio de comodidad.
3. **Sorprende en la direccion peor.** Quien conoce `odoo shell` espera rollback.
   Cambiarlo sorprende con **escrituras silenciosas** en vez de con perdidas
   silenciosas. Una perdida se recupera volviendo a correr; una escritura
   incorrecta en produccion puede no recuperarse.
4. **Convierte una falla reversible en una irreversible.** Que es exactamente la
   direccion equivocada.

### Ponerlo en configuracion: tampoco

Un setting en `.odev.yaml` hace que el **mismo comando destruya o no segun el
proyecto**. Eso es estado invisible en el peor lugar posible: un agente que
aprendio el comportamiento en un proyecto lo aplica mal en otro, sin ninguna
senal. El comportamiento que destruye datos tiene que ser visible en el sitio de
la llamada, no en un archivo que nadie releyo.

### Flag `--commit` explicito: si

Visible en la linea de comando, en el log, y en el transcript del agente. Quien
lee la invocacion sabe lo que hizo. Es la misma logica por la que `down -v`
necesita `--yes`: las operaciones irreversibles se piden, no se heredan.

### Y el arreglo que de verdad importa: romper el silencio

Lo grave de `odev py` no es que descarte escrituras — eso es una decision
defendible de Odoo. Es que **descarta escrituras sin decir nada**. La expresion
corre, no hay error, y el agente reporta trabajo hecho que no existe.

Recomendacion: si la expresion contiene una llamada de escritura y no se paso
`--commit`, emitir un warning por stderr:

```
WARN: la expresion parece escribir (.create) y no se paso --commit.
      odoo shell hace rollback al cerrar: los cambios se van a descartar.
```

Es una heuristica estatica sobre el texto de la expresion — `.create(`,
`.write(`, `.unlink(`, `.copy(` — no una garantia, y hay que documentarla como
tal. Tiene falsos negativos: una escritura dentro de un metodo de negocio no se
detecta. Pero cubre el caso dominante, cuesta muy poco, y convierte el modo de
falla de **silencioso** a **ruidoso**, que es el unico cambio que realmente
importa. `--commit` suprime el warning.

---

## Agrupacion sugerida para release

| Release | Contenido | Criterio |
|---|---|---|
| 0.10.1 (patch) | A3, C1 | Una linea cada uno, sin cambio de contrato |
| 0.11.0 (minor) | A1, A2, C2, C3, E1, B2, B3 | Arreglan silencios y completan guardas sin romper invocaciones existentes |
| 0.12.0 (minor) | B1, D4 | Los dos breaking: la guarda de `down -v` y la normalizacion de exit codes |
| sin agrupar | D1, D2, D3 | Decisiones de producto pendientes, no defectos |

Los breaking van juntos y solos a proposito: un solo anuncio, una sola migracion
para quien scriptea.

---

## Que no esta en este documento

- La skill de odev documenta estos comportamientos tal como son hoy. Describir
  una falla no la arregla, y este documento no cambia codigo.
- Los items de `ROADMAP.md` y `docs/IMPROVEMENT-PLAN.md` siguen vigentes por su
  cuenta; esto no los reemplaza ni los reordena.
