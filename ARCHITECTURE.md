# Arquitectura de odev

Este documento describe el diseno global de odev: que forma tiene, que
invariantes sostiene y por que. Esta escrito para quien va a cambiar el codigo:
no es un tutorial ni una referencia de comandos — eso vive en
`docs/guia-de-uso.md` y en la skill de `.claude/skills/odev/`. Cada seccion
enuncia una invariante y su razon; si el codigo la contradice, es el codigo el
que esta mal.

---

## Que es odev

odev gestiona un stack Odoo dockerizado **por proyecto**. Un proyecto es un
directorio con configuracion propia desde la que odev renderiza, con plantillas
Jinja, un `docker-compose.yml`, un `entrypoint.sh`, un `odoo.conf` y un `.env`.
El stack tiene dos servicios obligatorios — `db` (PostgreSQL) y `web` (Odoo) — y
dos opcionales, `pgweb` y `mailhog`.

Sobre ese stack hay dos frentes de invocacion: una **CLI Typer**, con los
comandos de nivel superior y los subgrupos `db`, `mcp`, `projects` y
`enterprise`; y un **servidor MCP** (`odev mcp serve`) que expone las mismas
operaciones a un agente como nueve tools, cuatro resources y tres prompts. Los
dos frentes no son dos implementaciones: son dos presentaciones de la misma capa
de operaciones, y eso define casi toda la estructura del repo.

| Paquete | Contiene | Puede |
|---|---|---|
| `odev/core/` | Logica de dominio: resolucion de proyecto, registro global, config del proyecto, wrapper de docker compose, pre-flight de puertos, neutralizacion, regeneracion de archivos, parseo de salida de tests | Lanzar excepciones de dominio, loguear, leer y escribir archivos del proyecto |
| `odev/commands/` | Un modulo por comando: declaracion de argumentos Typer, presentacion, eleccion del codigo de salida | Todo lo anterior, mas decidir stream, formato y exit code |
| `odev/templates/project/` | Plantillas Jinja de los archivos generados del proyecto | — |

La frontera se enuncia como una prohibicion verificable: **`core/` no importa
`typer`**. Ningun modulo de `core/` sabe que existe una CLI, y por lo tanto
ninguno puede decidir por el llamador como se presenta un fallo ni con que
codigo se sale; un `import typer` ahi abajo es la senal de que una decision de
presentacion se filtro. En la direccion inversa la regla es de reuso: un modulo
de `commands/` no reimplementa lo que `core/` ya resuelve. La clasificacion de
puertos es el ejemplo canonico — `up` y `doctor` consumen la misma
`classify_bound_port`, no dos heuristicas parecidas.

---

## Dos frontends, un solo core

**Esta es la invariante estructural mas importante del repo.**

Toda operacion que los dos frentes necesitan vive en una funcion
`_execute_*(contexto, ...)` dentro del modulo de su comando. **Retorna datos**
— un dict, una lista de dicts, un string — y nunca imprime. **No sale**: no
llama a `typer.Exit` ni a `sys.exit`. **Senaliza fallos con excepciones de
dominio**: `ValueError` para entrada invalida, `RuntimeError` para un entorno
inutilizable, y `subprocess.CalledProcessError` propagada desde docker.

Alrededor de cada una hay dos envoltorios. El **wrapper CLI** (`_run_*`, o la
funcion Typer misma) decide como se presenta: renderiza, elige el stream y
traduce la excepcion a un codigo de salida. El **wrapper MCP** decora la tool con
`_anticipado(ToolError)`, que atrapa la tupla `FALLOS_OPERATIVOS` y la re-lanza
como el error *anticipado* del SDK, cuyo mensaje si llega al cliente. Cualquier
otra excepcion escapa sin traducir, que es lo correcto: un bug de odev pertenece
al log con su traceback, no al contexto del modelo disfrazado de fallo
operativo.

De ahi la regla: **el codigo compartido senaliza con excepciones, cada frontend
decide la presentacion.** Por eso `_resolve_contexto` lanza `ValueError` en vez
de salir, y por eso `parsear_modulos_csv`, `validar_modulos`,
`_parse_test_target` y `_build_test_tags` lanzan `ValueError` con el mensaje
accionable, que la CLI convierte en stderr mas `typer.Exit(2)`.

Un `typer.Exit` en codigo compartido no falla de forma visible: falla de una
forma especifica y muy mala. `typer.Exit` hereda de `RuntimeError`, asi que
`_anticipado` **si** lo atrapa; pero `Exit.__init__` nunca llama a
`super().__init__(mensaje)`, guarda el codigo de salida en `args`. El resultado
es que `str(typer.Exit(2))` vale `'2'`, y el cliente MCP recibe un error cuyo
mensaje completo es un digito. El texto util se escribio a stderr, que bajo
transporte stdio es el log del servidor: el modelo nunca lo ve, sabe que algo
fallo pero no que, y su unica estrategia es probar otra cosa a ciegas. Es la
capa de traduccion de errores fallando exactamente en el caso para el que
existe, y un solo `typer.Exit` mal ubicado alcanza. Corolario: una funcion
compartida necesita cobertura en los dos frentes.

---

## Resolucion de proyecto

`core/resolver.py::resolver_proyecto()` es la unica entrada. Todos los comandos
la usan — la CLI via `requerir_proyecto`, el servidor MCP via
`_resolve_contexto` — y devuelve un `ProjectContext` con cinco campos: `nombre`,
`modo`, `directorio_config`, `directorio_trabajo` y `config`. El orden de
resolucion es:

1. **Nombre explicito**, buscado en el registro global. Sale del flag
   `--project` y, si no esta, de la variable `ODEV_PROJECT` — la via practica
   para un shell, `direnv` o el servidor MCP.
2. **INLINE**: busqueda ascendente desde cwd hasta la raiz, buscando
   `.odev.yaml` u `odev.yaml`. Los dos nombres son validos; si conviven en un
   mismo directorio gana el que lleva punto, y esa prioridad se decide en un
   solo lugar (`resolver_ruta_yaml`) para que no pueda desincronizarse.
3. **EXTERNAL**: consulta al registro por directorio de trabajo, con
   coincidencia por prefijo sobre rutas resueltas. Varias coincidencias lanzan
   `ProyectoAmbiguoError` nombrando los candidatos: la ambiguedad la resuelve el
   usuario con `--project`, no una heuristica.
4. **LEGACY**: el layout viejo de `odoo-dev-env`, un directorio con
   `docker-compose.yml` y un subdirectorio `cli/`.
5. Sin coincidencias, `ProyectoNoEncontradoError`.

| Modo | Donde vive la config | Donde vive el codigo | Nombre de proyecto compose |
|---|---|---|---|
| `inline` | En el directorio del proyecto, junto al codigo | El mismo directorio | El que deduce docker compose |
| `external` | En `~/.odev/projects/<nombre>/` | En el directorio de trabajo registrado | `<nombre>` en minusculas, forzado con `-p` |
| `legacy` | No hay `.odev.yaml`; `config` es `None` | El directorio detectado | El que deduce docker compose |

`external` fuerza el nombre del proyecto compose precisamente para que los
volumenes queden aislados entre proyectos que comparten un directorio padre.
`legacy` existe solo para compatibilidad de lectura: no hay config que validar,
y los comandos que la necesitan tienen que tolerar `config is None`.

El registro global vive en `~/.odev/`: `registry.yaml` guarda el mapa
`projects: {nombre: entrada}` con directorios, modo, version de Odoo y puertos
reclamados; `projects/<nombre>/` guarda la configuracion de los proyectos
`external`; y `enterprise/` un checkout de enterprise compartido. El registro
tambien arbitra los puertos — cada entrada lleva el diccionario `ports` que
reclamo, y eso permite a `up` distinguir un puerto propio de uno ajeno. Dos
propiedades que conviene no romper: la **escritura se serializa dos veces**, con
un `threading.Lock` entre threads y `fcntl.flock(LOCK_EX)` entre procesos (hacen
falta los dos, porque `fcntl` no es seguro entre threads que comparten
descriptor), y el archivo se abre siempre en modo `w` bajo el lock, lo que
elimina la ventana TOCTOU; y la **lectura degrada en vez de abortar**, con el
YAML corrupto copiado a `.yaml.bak` y tratado como registro vacio, y las claves
desconocidas filtradas para que un escritor mas moderno no rompa a uno viejo.

---

## El modelo de privilegios del contenedor

El servicio `web` declara `user: root` en el compose, y el entrypoint baja
privilegios a `odoo` con `setpriv` como ultimo paso. Las dos mitades son
necesarias y ninguna es negociable.

**Por que arranca como root.** El entrypoint instala las dependencias Python de
los `requirements.txt` de los addons montados, igual que hace Odoo.sh, y si
alguno declara una dependencia `git+` necesita instalar `git` con `apt-get`. La
imagen oficial de Odoo arranca como el usuario `odoo`: sin el override esa
instalacion nunca se ejecuta, y el fallo aparece mucho mas tarde, lejos de su
causa.

**Por que no puede quedarse como root.** Odoo corriendo como root crea shards
del filestore con owner `root`. El servidor de larga vida corre como `odoo` y no
puede escribir en ellos: los bundles de assets dejan de archivarse con
`PermissionError` en `ir_attachment._file_write`, `/web/assets/*` responde 500,
la UI queda en blanco y los reportes salen sin estilos. Un solo comando mal
ejecutado alcanza para dejar miles de rutas inaccesibles, y el envenenamiento es
persistente: vive en el volumen, no en el proceso. El drop usa `setpriv
--reuid=odoo --regid=odoo --init-groups`, y no `gosu`, porque `setpriv` esta en
la imagen y `gosu` no; antes del `exec` hay que exportar `HOME=/var/lib/odoo`,
sin lo cual el proceso hereda el `HOME` de root y `pip` y el user-site apuntan
al lugar equivocado.

**La consecuencia al escribir un comando nuevo.** `docker compose exec` entra
con el usuario **por defecto de la imagen**, que aca es root: el drop del
entrypoint aplica al proceso de larga vida, no a los exec posteriores. Por lo
tanto:

> Todo comando one-off que **ejecute Odoo** pasa `user=USUARIO_ODOO`.

Lo cumplen `addon-install`, `update`, `test`, `py`, `model-info` y la
neutralizacion. `DockerCompose` acepta `user` en `exec_cmd`, `exec_capture`,
`exec_cmd_stream` y `exec_cmd_file`, valida el valor contra un patron y emite
`--user` **antes** del nombre del servicio, como exige `docker compose exec`.

`shell` y `tui` deliberadamente **no** lo pasan. Abren un `bash` interactivo para
depurar, y ahi root es justamente lo util: instalar un paquete, leer un archivo
con owner root, inspeccionar el filestore. No ejecutan Odoo, asi que no pueden
crear shards. La excepcion esta acotada a "no lanza Odoo", no a "es interactivo".

---

## Contratos que un caller puede dar por sentado

Esta es la superficie publica de odev para cualquier consumidor programatico.

### Streams

| Stream | Lleva |
|---|---|
| stdout | **Solo datos**: resultados, payloads `--json`, tablas renderizadas, el valor de una expresion de `py`. Tambien `info()` y `success()`, que son el comando contando lo que hizo, no un diagnostico |
| stderr | **Todo error y toda advertencia**: `error()`, `warning()`, el aviso de cero tests, el de escritura sin `--commit`, el lint de descubrimiento |

`core/console.py` sostiene la separacion con dos consolas Rich distintas,
`console` a stdout y `console_err` a stderr. No hay variantes "a stderr" de
`error()` y `warning()` a proposito: un helper que solo acierta cuando uno se
acuerda de usarlo es peor contrato que una funcion que acierta siempre.

La consecuencia practica es que **stdout se parsea sin filtrar**. Un diagnostico
en stdout rompe el parseo con un fallo que no tiene nada que ver con la causa
real — el consumidor recibe un `JSONDecodeError` cuando el problema era un
argumento mal pasado. Y a la inversa: quien capture solo stdout para detectar
fallos no captura nada. El transporte stdio de MCP lleva el caso al extremo,
porque ahi stdout lleva los mensajes JSON-RPC; por eso
`_configure_stderr_logging()` saca todos los handlers del logger raiz y deja uno
solo a stderr antes de arrancar el servidor.

### Codigos de salida

| Codigo | Significa |
|---|---|
| `0` | Exito |
| `1` | Error de proyecto o de runtime |
| `2` | Error de uso: argumento invalido, modulo inexistente, combinacion prohibida |
| `3` | Error de entorno: puerto ocupado, DB o Docker no disponible, dependencia opcional faltante |

El contrato es uniforme en todos los comandos, y `EPILOG_EXIT_CODES` se adjunta
como epilogo de cada uno para que el help y el comportamiento no puedan
divergir. La unica excepcion declarada es que `addon-install` y `update`
reenvian el returncode crudo de Odoo.

El razonamiento: el codigo de salida es la unica senal estructurada que tiene un
script **antes** de parsear nada. Si `1` significa a veces "error de uso" y a
veces "runtime", el reintento no se puede automatizar, porque las dos
situaciones piden respuestas opuestas — reintentar un error de uso es inutil, no
reintentar uno de entorno es prematuro.

### El silencio es un defecto

> Cuando odev sabe algo que quien lo invoca no sabe, lo dice.

La razon esta en el consumidor. Una persona que ve un resultado raro abre el
log, prueba otra cosa, sospecha. Un agente toma la salida como verdad, la
reporta y sigue construyendo sobre ella. **Una falla ruidosa cuesta tiempo; una
silenciosa cuesta correccion.** De ahi el criterio para priorizar un defecto: no
cuanto molesta, sino con cuanta confianza hace afirmar algo falso. Lo peor que
puede emitir odev es una afirmacion falsa con formato de exito.

Lo que el principio obliga, en concreto:

- Una corrida de tests que ejecuto **cero** tests avisa, nombrando el filtro
  efectivo. Cero tests es indistinguible del exito si nadie lo dice, y converge
  desde cuatro causas: un `test_*.py` no importado en `tests/__init__.py`, un
  nombre de modulo mal escrito que igual pasa la validacion de addons-path, una
  expresion de `--tags` que no matchea nada, o un modulo sin tests.
- El **lint de descubrimiento** compara, antes de lanzar, los `test_*.py` del
  addon contra lo que su `tests/__init__.py` realmente importa. Odoo solo
  descubre los modulos de test importados — `get_test_modules` usa
  `inspect.getmembers(mod, inspect.ismodule)`, y un submodulo solo es atributo
  del paquete si alguien lo importo — asi que un archivo huerfano aporta cero
  tests sin error ni warning. El parseo va con `ast` y no con regex, para
  manejar `from . import a, b` y los imports condicionales: un lint que reporta
  huerfanos falsos es peor que ningun lint, y ante un archivo no parseable se
  omite en silencio.
- Una expresion de `py` que parece escribir sin `--commit` avisa, y un comando
  destructivo nombra el proyecto y que va a destruir.
- `up` avisa cuando no puede garantizar la configuracion local del entorno en
  vez de retornar callado, y `doctor` reporta los subcomandos opcionales cuyo
  import fallo. La degradacion elegante esta bien; la invisible no.

Dos limites hacen el principio aplicable: **un aviso no cambia el codigo de
salida** — cero tests es legitimo a veces, y convertirlo en error rompe a quien
corre `odev test all` sobre un proyecto con modulos sin tests — y **un aviso
nunca toca stdout**, de modo que no contamina `--json` ni el valor que el
llamador parsea.

### Las guardas destructivas son uniformes

| Comando | Destruye | Warning | Confirmacion | `--yes` | `--dry-run` |
|---|---|---|---|---|---|
| `down -v` | Volumenes: DB y filestore | si | si | si | si |
| `reset-db` | DB y volumenes, reinicializa | si | si | si | si |
| `load-backup` | Pisa DB y filestore | si | si | si | si |
| `db restore` | Dropea y recrea la DB | si | si | si | si |
| `db anonymize` | PII y todas las passwords | si | si | si | si |

**La uniformidad es el punto, no la suma de guardas.** Una guarda que no se
puede predecir no protege, porque nadie la interioriza. Quien aprende que
`reset-db` pregunta generaliza — razonablemente — que odev pregunta antes de
destruir; si esa generalizacion vale para cuatro de cinco casos, la guarda de
los cuatro vuelve **enganoso** al quinto, y el quinto termina siendo justamente
el mas corto de tipear y el mas facil de ejecutar por accidente. Una tabla con
un hueco es peor que una tabla vacia.

Dos detalles del diseno. `typer.confirm` con stdin no interactivo lanza `Abort`,
no se cuelga: un script sin `--yes` falla cerrado con un mensaje claro, que es
el comportamiento correcto para una operacion irreversible. Y `--yes` existe
para que la guarda sea **automatizable**, no para debilitarla — `db anonymize`
es el caso que lo explica, porque existe para preparar una copia segura
(restaurar un dump, anonimizarlo, trabajar tranquilo) y eso es una cadena
scripteada por definicion. `odev down` sin `-v` no destruye nada persistente y
no lleva guarda: dispara el flag que borra volumenes, no el comando.

---

## Decisiones que no conviene relitigar

### `odev py` descarta escrituras salvo `--commit`

`odoo shell` ejecuta `cr.rollback()` **despues** de cerrar la consola, asi que
toda escritura ORM se descarta salvo commit explicito. odev conserva ese
comportamiento y agrega `--commit` para pedirlo. Commitear por default se
descarta por cuatro razones, en orden de peso:

1. **El uso dominante es de lectura.** `odev py` se usa mayormente para
   inspeccionar: contar registros, mirar un campo, verificar un estado.
   Commitear por default convierte cada expresion exploratoria en una mutacion
   potencial.
2. **Rompe el rollback ante error.** Si la expresion escribe y despues lanza,
   Odoo descarta todo. Con commit automatico habria que decidir si commitear
   estado parcial, y esa atomicidad es una propiedad de seguridad que se estaria
   entregando a cambio de comodidad.
3. **Sorprende en la peor direccion.** Quien conoce `odoo shell` espera
   rollback; cambiarlo sorprende con escrituras silenciosas en vez de con
   perdidas silenciosas, y una perdida se recupera volviendo a correr mientras
   que una escritura incorrecta puede no recuperarse.
4. **Convierte una falla reversible en irreversible**, que es exactamente la
   direccion equivocada.

Ponerlo en configuracion se descarta por una razon distinta y mas fuerte: un
setting en `.odev.yaml` hace que **el mismo comando destruya o no segun el
proyecto**. Eso es estado invisible en el peor lugar posible — quien aprendio el
comportamiento en un proyecto lo aplica mal en otro, sin ninguna senal. El
comportamiento que destruye datos tiene que ser visible **en el sitio de la
llamada**, no en un archivo que nadie releyo. Un flag se ve en la linea de
comando, en el log y en el transcript del agente: quien lee la invocacion sabe
lo que hizo. Es la misma logica por la que `down -v` pide `--yes`; las
operaciones irreversibles se piden, no se heredan. El flag ademas ahorra
escribir `env.cr.commit()` a mano dentro de la expresion: `_construir_script`
agrega la linea del commit despues de la del `print`.

### La deteccion de escritura es una heuristica de texto

Lo grave de `odev py` nunca fue que descarte escrituras — eso es una decision
defendible de Odoo. Es que las descarte **sin decir nada**: la expresion corre,
no hay error, y el llamador reporta trabajo hecho que no existe.

`_expresion_parece_escribir` busca `.create(`, `.write(`, `.unlink(` y `.copy(`
en el texto de la expresion. Sin AST, sin entender el contexto. Tiene falsos
negativos conocidos: una escritura dentro de un metodo de negocio propio no se
detecta. **La ausencia del aviso no prueba nada, y la documentacion lo dice.**

Eso es aceptable, y el porque importa mas que la heuristica: convierte el modo
de falla dominante de **silencioso** a **ruidoso**, que es el unico cambio que
realmente importa. Un analisis exhaustivo costaria mucho mas y tampoco seria una
garantia, porque la expresion corre contra codigo de servidor arbitrario.
`--commit` suprime el aviso por completo, y en MCP la misma informacion viaja
como campo y no como texto suelto — `odev_py` devuelve
`{result, committed, warning}` — asi el aviso no se puede pasar por alto y
tampoco se mezcla con el resultado.

### `--tags` reemplaza los prefijos de modulo

Odoo **une** (OR) los specs de `--test-tags` separados por coma, no los
intersecta: `check()` en `odoo/tests/tag_selector.py` hace `any(...)` sobre los
includes, y dentro de un solo spec `_is_matching()` exige que coincida todo.
Ademas, un include sin tag toma `standard` por default. Por eso concatenar el
prefijo auto-generado con la expresion del usuario **amplia** la seleccion en
vez de acotarla: `--test-tags /sale,foo` significa "todos los tests standard de
sale" O "todos los tagueados foo", de modo que el modulo entero corre y el
filtro queda silenciosamente inutil. El argumento `-u <modulos>` ya acota que
modulos corren tests, asi que la expresion del usuario sola filtra exactamente
dentro de ellos.

| Entrada de `_build_test_tags` | Specs emitidos |
|---|---|
| Modulos, sin `--tags` | `/m1,/m2` |
| `all`, sin `--tags` | Ninguno: no se emite `--test-tags` |
| Shorthand `modulo:Clase.metodo` | `/modulo:Clase.metodo` |
| `--tags <expresion>` | La expresion sola |
| Shorthand y `--tags` juntos | Rechazado con `ValueError` |

La ultima fila sigue del mismo hecho: los dos definen el filtro y Odoo uniria
ambos en vez de intersectarlos; rechazar la combinacion nombrando las dos
salidas es mejor que descartar una en silencio. `_build_test_tags` es una sola
funcion que consumen los dos frentes, porque la construccion duplicada en las
rutas CLI y MCP es precisamente lo que permite que el mismo defecto exista dos
veces.

---

## Testear la CLI

Llamar una funcion de comando Typer **directamente** desde un test, sin pasar
todos sus parametros, deja a cada parametro omitido con el objeto
`typer.Option(...)` o `typer.Argument(...)` como valor. Ese objeto es **truthy**,
no `False`. Un test que omite un flag booleano termina ejercitando la rama
contraria a la que aparenta testear, y pasa igual — la peor combinacion posible:
cobertura aparente sobre la rama equivocada.

`tests/_helpers.py::call_command()` resuelve el problema en un lugar:
introspecciona la firma con `inspect` y, para cada parametro cuyo default sea una
`OptionInfo` o `ArgumentInfo`, lo reemplaza por el `.default` real de ese objeto
— el mismo valor que Typer le daria en la CLI si el flag no se paso. Los
`overrides` explicitos del caller tienen prioridad.

> Todo test que invoque una funcion de comando Typer directamente pasa por
> `call_command()`.

Una llamada pelada solo es segura si se pasan **todos** los parametros, y esa es
exactamente la disciplina que se erosiona con el tiempo. Dos notas mas:
`pythonpath = ["src"]` en `pyproject.toml` hace que pytest resuelva odev desde el
repo y no desde site-packages, sin lo cual una instalacion vieja hace fallar la
coleccion con errores ajenos al codigo bajo test; y las funciones compartidas se
testean en los dos frentes, porque el contrato de la CLI y el mensaje que recibe
el cliente MCP son dos afirmaciones distintas.
