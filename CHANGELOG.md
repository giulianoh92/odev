# Registro de Cambios

Todos los cambios notables en este proyecto se documentan en este archivo.

El formato esta basado en [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
y este proyecto adhiere a [Versionado Semantico](https://semver.org/spec/v2.0.0.html).
Politica de bumps: ver [VERSIONING.md](VERSIONING.md).

## [0.13.0] - 2026-09-19

### Cambiado

- **BREAKING: `addon-install`, `update` y `test` normalizan el exit code de
  Odoo.** Los tres publican `EPILOG_EXIT_CODES` en su `--help` (0 exito / 1
  error de runtime / 2 error de uso / 3 error de entorno) y `addon-install`/
  `update` lo violaban: propagaban tal cual el codigo del proceso Odoo del
  contenedor, que puede ser 3, 137 o cualquier cosa que devuelva Odoo o el OOM
  killer. Un caller no podia decidir si reintentar, porque un 3 significaba
  "error de entorno" en el resto de la CLI y "lo que dijo Odoo" en estos dos.
  Ahora cualquier fallo sale con 1. El codigo crudo no se pierde: queda en el
  mensaje de stderr, que es el canal disponible porque ninguno de los dos
  tiene `--json`. Un script que discriminaba por ese codigo debe leer stderr.
  `test` tenia el mismo defecto — un returncode de proceso fuera del contrato
  (137, 139, lo que sea) salia tal cual en vez del 1 prometido — y se corrige
  con el mismo mapeo (`normalizar_exit_code_odoo`, unico punto de verdad). A
  diferencia de los otros dos, `test` tiene `--json`: el codigo crudo
  ahora tambien queda expuesto como `process_exit_code` en el payload,
  presente en toda corrida (exitosa o no), no solo en el mensaje de stderr.
  El caso de puerto ocupado sigue saliendo 3 sin pasar por este mapeo: ese 3
  lo decide odev mismo, no viene del proceso Odoo.

### Corregido

- **`modules --json`, `status --json` y `doctor --json` emitian dos diagnosticos
  para el mismo fallo.** Sin proyecto resuelto salian el mensaje humano de
  `requerir_proyecto` y ademas el JSON del propio comando, los dos por stderr. Un
  consumidor que parsea linea por linea se comia el humano y fallaba con un error
  que no tenia nada que ver con la causa. `requerir_proyecto(silencioso=True)`
  deja que el caller arme el unico diagnostico parseable; el path humano por
  default no cambia.
- **`doctor --json` devolvia `no project context`,** que no le dice a nadie que
  hacer. Ahora da el mismo mensaje accionable que los otros dos comandos.
- **El contenedor dejaba `__pycache__` de root en `./addons`.** El proceso Odoo
  corre como root hasta el `setpriv` del entrypoint, asi que los `.pyc` que
  escribia sobre el bind mount quedaban `root:root` y el usuario no podia borrar
  su propio proyecto sin sudo. `PYTHONDONTWRITEBYTECODE=1` en el servicio web lo
  evita de raiz, sin costo real en un stack de desarrollo donde el codigo cambia
  todo el tiempo. `regenerar_configuracion()` corre en cada `odev up`, asi que los
  proyectos ya creados la reciben sin regenerarse enteros.

### Agregado

- `ARCHITECTURE.md`: el diseno global en un solo lugar — los dos frontends sobre
  un core comun, la resolucion de proyecto, el modelo de privilegios del
  contenedor, los contratos que un caller puede dar por sentado y las decisiones
  que no conviene relitigar.

### Eliminado

- `ROADMAP.md`, `docs/IMPROVEMENT-PLAN.md`, `docs/FALLAS-SILENCIOSAS.md` y
  `docs/sdd/`. Eran documentacion de proceso que describia trabajo ya hecho, y
  que envejecia para el lado peor: afirmaba con seguridad cosas que habian dejado
  de ser ciertas. Lo durable de esos documentos quedo en `ARCHITECTURE.md`. La
  documentacion del repo es README, CHANGELOG, VERSIONING, la Guia de Uso, la
  skill y ARCHITECTURE.

## [0.12.0] - 2026-09-19

### Cambiado

- **BREAKING: `error()` y `warning()` escriben a stderr, no a stdout.** stdout es
  el canal de datos: lo parsean los consumidores de `--json` y los pipes. Un
  diagnostico ahi rompe el parseo con un fallo que no tiene nada que ver con la
  causa real. Alcanza a las ~70 llamadas de todos los comandos. `info()` y
  `success()` se quedan en stdout: son el comando contando lo que hizo, no un
  diagnostico, y varios se leen como salida humana. Quien capture stdout para
  detectar fallos necesita capturar stderr.

### Eliminado

- `error_stderr` y `warning_stderr` de `odev.core.console`. Existian como arreglo
  acotado mientras `error`/`warning` seguian en stdout; ahora sobran. Un helper
  que solo acierta cuando uno se acuerda de usarlo es peor contrato que una
  funcion que acierta siempre.

### Corregido

- **Los rechazos tempranos de `sql` y `test` dejaban de emitir texto con formato
  por stdout.** Ambos tenian un rodeo manual escribiendo a stderr por su cuenta;
  con `error()` ya correcto, vuelven a la ruta comun.

### Interno

- `tests/_helpers.py::call_command()` resuelve los defaults de Typer al invocar
  un comando directamente. Sin el, un parametro booleano omitido conserva el
  objeto `typer.Option(...)`, que es **truthy**: el test ejercita la rama opuesta
  a la que aparenta y pasa igual. No era teorico — `up()` se llamaba pelado con
  `build` y `watch` como sentinels, testeando `--build --watch` mientras parecia
  testear el default.

## [0.11.0] - 2026-09-19

Release enfocada en una sola clase de defecto: **odev sabia algo que quien lo
invocaba no sabia, y no lo decia**. Los principios de diseno que salieron de ese
relevamiento viven en [ARCHITECTURE.md](ARCHITECTURE.md); el detalle de cada
defecto, con su razonamiento y las alternativas descartadas, esta en las
entradas de abajo.

### Cambiado

- **BREAKING: `odev down -v` ahora pide confirmacion.** Borraba los volumenes de
  DB y filestore sin preguntar nada, siendo el comando destructivo mas corto de
  tipear y el unico sin guarda. Esa asimetria volvia enganosa la guarda de los
  otros cuatro: quien generalizaba "odev pregunta antes de destruir" acertaba en
  cuatro de cinco casos. Ahora avisa, confirma y acepta `-y/--yes`. **La guarda
  dispara solo con `-v`**: `odev down` pelado no destruye nada persistente y
  sigue igual que siempre. Los scripts que usen `down -v` necesitan agregar
  `--yes`; sin el fallan cerrado con un mensaje claro, no se cuelgan.
- **BREAKING: `odev modules` emite una tabla legible en vez de JSON.** El flag
  `--json` se declaraba con default `True` y el cuerpo nunca leia su valor, asi
  que la salida era siempre JSON. Todos los demas comandos con `-j/--json` de
  este repo tienen salida legible por default y optan a JSON. Para seguir
  obteniendo JSON, pasar `-j/--json` explicitamente.
- **BREAKING: la tool MCP `odev_py` devuelve un objeto en vez de un string.**
  Ahora entrega `{result, committed, warning}`. Alinea la tool con las otras
  siete que ya devolvian dict o lista, y hace imposible pasar por alto el aviso
  de escritura descartada sin mezclarlo con el resultado.
- **BREAKING: exit codes alineados al contrato que el propio repo publica**
  (`0` exito, `1` proyecto/runtime, `2` uso, `3` entorno). `scaffold` usaba `1`
  para errores de uso; `mcp serve` usaba `2` para problemas de entorno. El exit
  code es la unica senal estructurada que tiene un script antes de parsear nada:
  si `1` significa a veces "error de uso" y a veces "runtime", no se puede
  automatizar el reintento, porque las dos situaciones piden respuestas
  opuestas. `addon-install` y `update` siguen reenviando el returncode de Odoo.

### Agregado

- **Aviso cuando una corrida de tests ejecuto cero tests.** Antes reportaba
  verde, que es indistinguible del exito. Cuatro causas convergian en el mismo
  silencio: un archivo no importado en `tests/__init__.py`, un nombre de modulo
  mal escrito, una expresion de `--tags` que no matchea, o un modulo sin tests.
  Ahora avisa por stderr nombrando el filtro efectivo. Va por stderr y no cambia
  el exit code: cero tests es legitimo a veces, y `odev test all` tiene que
  seguir andando sobre proyectos con modulos sin tests.
- **Lint de descubrimiento de tests.** Antes de lanzar, compara los `test_*.py`
  del addon contra lo realmente importado en su `tests/__init__.py`, parseado
  con `ast`. Odoo solo descubre los modulos de test importados, asi que un
  archivo huerfano aporta cero tests sin ningun error.
- **`odev py --commit`.** `odoo shell` hace `cr.rollback()` al cerrar, asi que
  las escrituras se descartan salvo commit explicito. Eso se mantiene: el uso
  dominante es de lectura, y commitear por default convertiria cada expresion
  exploratoria en una mutacion potencial. El flag agrega el commit para no tener
  que escribir `env.cr.commit()` a mano dentro de la expresion.
- **Aviso cuando una expresion de `py` parece escribir sin `--commit`.** El
  problema nunca fue que descarte, que es defendible: es que descartaba sin
  decirlo, y quien la invocaba reportaba trabajo hecho que no existia. Es una
  heuristica estatica sobre el texto (`.create(`, `.write(`, `.unlink(`,
  `.copy(`) con falsos negativos conocidos — una escritura dentro de un metodo
  de negocio no se detecta — pero cubre el caso dominante y convierte el modo de
  falla de silencioso a ruidoso.
- **`-y/--yes` y `--dry-run` en `db anonymize`**, que tenia prompt pero ninguna
  forma de saltearlo, al reves de su caso de uso: existe para preparar copias
  seguras dentro de pipelines. **`--dry-run` en `db restore`**, que le faltaba.
  Con esto los cinco comandos destructivos tienen las mismas cuatro guardas.
- **Check de subcomandos en `odev doctor`.** Los subcomandos opcionales se
  registran dentro de `try/except ImportError`; si el import fallaba, el
  subcomando no existia y el usuario recibia "comando desconocido" sin ninguna
  pista. La degradacion elegante esta bien; la invisible no.
- **`console_err`, `error_stderr` y `warning_stderr`** en `odev.core.console`.

### Corregido

- **La tool MCP `odev_test` devolvia `ToolError("2")`**, literalmente el digito.
  Los validadores compartidos lanzaban `typer.Exit(2)`, que hereda de
  `RuntimeError` y por lo tanto `_anticipado` atrapaba — pero `Exit.__init__`
  nunca llama a `super().__init__(mensaje)`, asi que `str()` devuelve el codigo
  de salida. El mensaje accionable quedaba en el log del servidor. Ahora
  `_parse_test_target`, `_build_test_tags`, `parsear_modulos_csv` y
  `validar_modulos` lanzan `ValueError` con el mensaje, y cada frontend decide
  como presentarlo. El contrato de la CLI no cambia.
- **`odev_status` y `odev_py` crasheaban sin traducir con el stack apagado.**
  Sus rutas terminan en `check=True` y lanzan `subprocess.CalledProcessError`,
  que no estaba en `FALLOS_OPERATIVOS`. El cliente veia `Error executing tool
  <name>`. Es la condicion de error mas comun y la mas accionable — solo hay que
  correr `odev up` — y presentarla como crash sacaba justo la informacion que
  permitia resolverla.
- **`doctor` reportaba `"version": "0.6.2"` hardcodeada.** El primer paso de
  cualquier diagnostico es saber que version se esta mirando; ese campo mandaba
  a leer el changelog equivocado. Hay un test que lo compara contra la version
  instalada, porque es la clase de literal que se vuelve a desincronizar.
- **`doctor` marcaba FAIL en los puertos del propio stack levantado.** Hacia un
  `socket.bind` crudo sin distinguir de quien era el puerto. Un falso positivo
  en la herramienta de diagnostico ensena a ignorarla, y el dia que el conflicto
  sea real ese FAIL ya no significa nada. Ahora reusa la clasificacion que `up`
  ya tenia resuelta.
- **Los diagnosticos contaminaban stdout, que es el canal de datos.** Las
  guardas tempranas de `sql` y `test`, y sobre todo `requerir_proyecto` — que
  llaman ~20 comandos — escribian el error con Rich por stdout antes de lanzar.
  El `except` de `status`, `doctor` y `modules` quedaba como codigo muerto para
  ese caso: emitian su error en JSON por stderr correctamente, pero stdout ya
  llevaba la linea con codigos de color, y el consumidor explotaba con un fallo
  que no tenia nada que ver con la causa real.
- **`odev.yaml` sin punto era invisible al walk inline**, que buscaba solo
  `.odev.yaml`. odev respondia "no encontre proyecto" sobre un directorio que
  claramente tenia uno.
- **`enterprise link` y `projects remove` usaban `SystemExit(1)`** donde el
  resto de sus archivos usa `typer.Exit`.

## [0.10.0] - 2026-09-19

### Cambiado

- **BREAKING: el extra `mcp` pasa de `mcp>=1.0.0,<2` a `mcp>=2,<3`.** El SDK 2.0 elimino `mcp.server.fastmcp`: FastMCP se llama ahora `MCPServer` y vive en `mcp.server`. Los decoradores (`tool`, `resource`, `prompt`) y `run(transport=..., port=...)` conservan la firma, asi que las 9 tools, 4 resources y 3 prompts se registran igual. Lo que si cambia es la senalizacion de errores: 2.x separa el fallo anticipado (`ToolError` / `ResourceError`, cuyo mensaje llega al cliente) del crash (cualquier otra excepcion, de la que el cliente solo ve `Error executing tool <name>` mientras el detalle queda en el log). Quien tenga el extra instalado necesita reinstalarlo.
- **BREAKING: `odev test --tags` ahora REEMPLAZA los prefijos de modulo auto-generados en vez de sumarse a ellos.** `odev test sale --tags foo` emite `-u sale --test-tags foo`, no `--test-tags /sale,foo`. El `--test-tags` emitido cambia, y con el cambia lo que se ejecuta: antes corria el modulo entero, ahora filtra. Ver la seccion **Corregido** para el porque.

### Corregido

- **`odev test --tags` filtra de verdad.** Odoo **une** (OR) los specs de `--test-tags` separados por coma, no los intersecta. Al concatenar el prefijo auto-generado con la expresion del usuario, `--test-tags /sale,foo` significaba "todos los tests standard de sale" O "todos los tagueados foo", de modo que el modulo entero corria y el filtro quedaba silenciosamente inutil. El `-u` ya acota que modulos se testean, asi que la expresion sola filtra exactamente dentro de ellos. La construccion estaba duplicada en las rutas MCP (`_execute_test`) y CLI (`_run_test`), que es lo que permitio que el bug existiera dos veces; ahora ambas llaman a un unico `_build_test_tags()`.
- **El shorthand `modulo:Clase.metodo` combinado con `--tags` sale con exit 2.** Los dos definen el filtro y Odoo uniria ambos en vez de intersectarlos. En vez de descartar el shorthand en silencio, el comando ahora rechaza la combinacion y nombra las dos salidas, igual que ya hacia con `--verbose` + `--json` o con `all` mezclado con nombres de modulo.
- **La documentacion de `odev py` decia exactamente lo contrario de lo que pasa.** README, el help del comando y la plantilla `claude-md.j2` advertian que los side-effects del ORM se commitean. No se commitean: `odoo/cli/shell.py` ejecuta `cr.rollback()` **despues** de cerrar la consola, asi que todo write sin `cr.commit()` explicito se descarta. La advertencia invertida llevaba a agentes a creer que ya habian persistido cambios que en realidad se perdian.
- **El guard del servidor MCP distingue el paquete ausente de la API incompatible.** `_import_fastmcp()` atrapaba cualquier `ImportError` y siempre respondia "'mcp' package not installed", mandando a reinstalar un paquete que ya estaba instalado. Ahora sondea `import mcp` primero y separa los dos fallos, que piden acciones distintas: ausente, instalar el extra; presente con API rota, reportar la version instalada y nombrar el simbolo que falta.
- **`pytest` resuelve odev desde `src/`.** Los tests importaban el odev que hubiera en site-packages, asi que una instalacion vieja hacia fallar la coleccion con `ImportError` sobre simbolos que si existen en el repo, y sin ninguna instalacion fallaba por no encontrar el paquete. Ninguno de los dos casos tenia que ver con el codigo. `pythonpath = ["src"]` hace que `pytest` funcione sin `PYTHONPATH` ni venv de desarrollo.

### Agregado

- **El repo trae su propia skill de Claude Code, en `.claude/skills/odev/SKILL.md`.** Queda versionada junto al codigo que documenta, asi que deja de desincronizarse con cada release. Se activa sola para agentes que trabajan dentro de este repo, y se instala global con `cp -r .claude/skills/odev ~/.claude/skills/` para que aplique a cualquier proyecto Odoo gestionado con odev. Cubre la trampa transaccional de `odev py`, la resolucion de proyecto, cuando usar MCP y cuando la CLI, los guards destructivos no uniformes, los exit codes, y un protocolo de una sola corrida para los tests.

## [0.9.0] - 2026-08-20

### Corregido

- **Odoo ya no se ejecuta como root dentro del contenedor.** `docker compose exec` entra como el usuario de la imagen (root, necesario para que el entrypoint instale `git` y los `requirements.txt` de los addons), asi que todo Odoo lanzado por odev creaba shards del filestore con owner `root`. El servidor de larga vida corre como `odoo` desde 0.8.2 (`setpriv`) y por lo tanto ya no podia escribir en ellos: los bundles de assets dejaban de archivarse (`PermissionError` en `ir_attachment._file_write`), `/web/assets/*` respondia 500 y la UI quedaba en blanco. Un solo `addon-install` alcanzaba para dejar >1200 rutas inaccesibles. Ahora `addon-install`, `update`, `test`, `py`, `model-info` y `neutralize` pasan `--user odoo`. `shell` y `tui` siguen entrando como root, que es lo util para depurar.
- **`odev up` ya no deja el proyecto sin `report.url` ni MailHog.** `asegurar_entorno_desarrollo` sondeaba la base inmediatamente despues de `compose up`, pero Odoo la crea recien segundos (o minutos, si el entrypoint todavia instala requirements) mas tarde. El fallo de psql se interpretaba como "no hay nada que hacer" y se retornaba **en silencio**, de modo que la base quedaba sin `report.url` — los PDF QWeb salian sin estilos porque wkhtmltopdf no podia bajar los bundles CSS — y sin MailHog como servidor de correo. Ahora `up` espera a que la base exista antes de decidir y, si aun asi no puede garantizar la configuracion, **avisa** en lugar de callarse.
- **El healthcheck de pgweb ya no reporta `unhealthy` de forma permanente.** Sondeaba con `wget -q --spider`, pero la imagen `sosedoff/pgweb:0.16.2` no incluye wget: cada intento fallaba con `wget: not found` mientras el servicio respondia HTTP 200, y el falso negativo contaminaba `odev status` y `odev doctor`. Ahora usa `curl -fsS` (presente en la imagen), que ademas falla ante un status HTTP de error y no solo cuando no hay conexion. El healthcheck de MailHog queda igual: `mailhog/mailhog:v1.0.1` si trae `/usr/bin/wget`.

### Agregado

- `esperar_base_lista()` en `odev.core.neutralize` — sondea hasta que la base tenga esquema de Odoo y **retorna** `bool` en lugar de abortar el comando (a diferencia del sondeo de `reset-db`, que lanza `typer.Exit`). Parametros `intentos`/`intervalo`, por defecto 60 x 5s.
- Parametros `esperar`, `intentos` e `intervalo` en `asegurar_entorno_desarrollo()`. Con `esperar=True` espera a que la base exista y vuelve a leer el estado.
- Parametro `user` en `DockerCompose.exec_cmd`, `exec_capture`, `exec_cmd_stream` y `exec_cmd_file`, mas la constante `USUARIO_ODOO`. El usuario se valida y `--user` se emite **antes** del nombre del servicio, como exige `docker compose exec`.
- `addon-install` y `update` revalidan la configuracion local al terminar (idempotente): instalar o actualizar modulos toca la base y reinicia web, asi que es el momento exacto para confirmar que `report.url` sigue apuntando al puerto interno y que MailHog sigue siendo el unico servidor de correo activo.

### Cambiado

- **Comportamiento default**: `odev up` puede tardar mas en el primer arranque de una base nueva, porque ahora espera a que Odoo termine de crearla para garantizar la configuracion local. Si la espera se agota, emite un warning explicito.

## [0.8.2] - 2026-08-15

### Corregido

- `entrypoint`: baja privilegios a `odoo` via `setpriv` en lugar de depender de un `apt-get` que moria en contenedores no-root.

## [0.8.1] - 2026-08-15

### Corregido

- `entrypoint`: instala `git` para las dependencias `git+` y ya no silencia los fallos de `pip install`.
- `entrypoint`: incluye todos los mounts de addons y enterprise en `addon_dirs_container`.

## [0.8.0] - 2026-08-15

### Agregado

- `neutralize`: `odev up` asegura los parametros de desarrollo y MailHog sobre la base existente.

### Corregido

- `neutralize`: `report.url` apunta al puerto interno del contenedor — con el puerto del host los PDF salen sin estilos cuando `WEB_PORT != 8069`.
- `config`: resuelve `.odev.yaml` y `odev.yaml` en `regen`, `reconfigure` y `reset-db`.
- `helpers`: valida modulos contra `paths.addons` del config antes de aplicar heuristicas.
- `preflight`: reconoce contenedores propios cuando las Labels vienen en formato string.

## [0.7.0] - 2026-07-03

### Agregado

- Flag `--verbose/-v` en `odev test`, `odev update` y `odev addon-install` — restaura el stream crudo de Odoo en vivo (comportamiento pre-0.7.0). En `test` es incompatible con `--json`/`--summary`/`--failures` (exit 2); combinado con `--save-log` streamea en vivo y guarda el log.
- Modo compacto en `update`/`addon-install`: se muestran solo lineas WARNING/ERROR/CRITICAL, bloques de traceback completos, la linea de exito de Odoo ("Modules loaded.") y un resumen de una linea (modulos procesados + exit code del proceso). Filtro implementado como funcion pura en `odev.core.odoo_log_filter`.

### Cambiado

- **BREAKING (comportamiento default)**: `odev test` sin flags imprime el summary compacto SIEMPRE (TTY o no); el log crudo interactivo requiere `--verbose`. `--summary/-s` queda como no-op retro-compatible.
- **BREAKING (comportamiento default)**: `odev update` y `odev addon-install` ya no vuelcan el log crudo completo de Odoo; usan el modo compacto por default (`--verbose` restaura el anterior). Ademas ahora propagan exit code: el del proceso Odoo si es != 0, y 1 si el proceso salio 0 pero el log contiene Traceback/CRITICAL.

### Corregido

- `odev test` salia con exit code 0 cuando los tests fallaban pero el proceso Odoo devolvia 0 (comportamiento real de Odoo 19 con `--test-enable --stop-after-init`). Ahora el codigo final combina el returncode del proceso con el resultado parseado (`TestResult.returncode_hint`): el proceso manda si sale != 0 (incluye puerto ocupado → 3); con 0 decide el parser (1 si hay failures/errors/parse_failed). Restaura el contrato documentado 0/1/2/3.

## [0.6.2] - 2026-05-18

### Corregido

- `ODEV_PROJECT` ahora es respetado por todos los comandos CLI (no solo el servidor MCP). El lookup se movio a `obtener_nombre_proyecto()` en `odev.main`, donde lo consumen los comandos de Path B (`status`, `sql`, `py`, `modules`, `logs`, `test`, `context`, `shell`, `doctor --json`, `model-info`, etc.). Precedencia: flag `-p/--project` > env var `ODEV_PROJECT`.

## [0.6.1] - 2026-05-18

### Corregido

- `odev doctor`: chequeos de archivos (.env, docker-compose.yml, config/odoo.conf, puertos, version) ahora usan `directorio_config` en lugar de `directorio_trabajo`, corrigiendo falso negativo en proyectos `mode: external`.
- `odev model-info`: invocacion de `odoo shell` ahora usa `--config=/etc/odoo/odoo.conf` y lee `DB_NAME` del `.env` del proyecto (antes hardcoded "odoo"), corrigiendo "Stack not running or DB unavailable" en proyectos con DB no llamada `odoo`.

## [0.6.0] - 2026-05-18

### Agregado

- `odev projects list` — nuevo subcomando explicito para listar proyectos registrados. Equivalente a `odev projects` (backward compat mantenida).
- Flag `--json/-j` en `odev projects list` (y `odev projects --json`) — emite la lista de proyectos como JSON estructurado: `{"projects": [...]}` con campos `name`, `path`, `modo`, `odoo_version`, `puerto_odoo`, `directorio_trabajo`, `directorio_config`, `exists`.
- Variable de entorno `ODEV_PROJECT` en servidor MCP — permite indicar el proyecto activo cuando el servidor MCP corre desde un directorio que no pertenece a ningun proyecto (ej. configuracion de Claude Code con `"env": {"ODEV_PROJECT": "<nombre>"}`).

### Corregido

- `odev doctor --json` ahora respeta el flag `-p/--project` y la variable `ODEV_PROJECT`; ya no falla cuando el cwd no pertenece a ningun proyecto y se paso el nombre via flag.
- Los helpers internos `_verificar_*` de doctor ya no ignoran el proyecto resuelto; el contexto fluye desde `_execute_doctor(contexto)` hacia cada verificacion.
- Las 9 herramientas MCP (`odev_model_info`, `odev_status`, etc.) resuelven el proyecto correctamente cuando el servidor arranca desde un cwd arbitrario y `ODEV_PROJECT` esta configurado.

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

- Especificaciones SDD completas del ciclo (proposal, spec, design, tasks)

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
