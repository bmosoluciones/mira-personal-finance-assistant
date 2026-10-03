# review.md — revisión independiente del trabajo de MIRA

> Revisión realizada sobre `task.md` como referencia, con `HEAD = cdaa1cb` y el
> working tree sin commit (rama `main`). Todos los comandos de verificación se
> ejecutaron de nuevo; nada se dio por bueno por estar declarado.

---

## 1. Veredicto en una línea

El trabajo es **sólido y está bien hecho en lo que puede verificarse
automáticamente** (todas las cifras de `task.md` §3 se reproducen, el colapso de
la fachada de BD es una migración fiel y el diseño de consentimiento es
fail-closed), pero **el servidor MCP, que es la pieza nueva más visible del
plan, no es interoperable con clientes MCP reales** y hay un **fallo de
integridad de datos en el camino de escritura** (`add_income` / `add_expense`
aceptan un nombre de cuenta inexistente y escriben en la cuenta por defecto
devolviendo `ok: true`). Ninguno de los dos está cubierto por tests.

---

## 2. Método

1. Contraste de `git status` / `git diff --stat` contra las cifras de `task.md`.
2. Lectura completa de los 5 módulos nuevos y del diff de los modificados con
   riesgo funcional (`engine.py`, `pipeline.py`, `ui/views/settings.py`,
   `app/view_services/settings.py`, `db/database.py`, `tag_repository.py`).
3. Reproducción de la tabla de verificación de `task.md` §3.
4. Comprobaciones estáticas propias: paridad de firmas entre las 15 fachadas
   antiguas y los 15 namespaces nuevos; paridad ES/EN de i18n; residuos de
   llama.cpp/GGUF; cobertura por referencia de los módulos nuevos.
5. **Pruebas de humo reales** de `mira-cli` y del servidor MCP sobre una base
   temporal (`seed`, `income/expense add`, `transfer`, `transactions list`,
   `report`, `record`, `mcp` con tramas LSP y con el framing real de MCP).

---

## 3. Verificación de `task.md` §3 (todo reproducido)

| Comando | `task.md` | Ejecutado aquí |
| --- | --- | --- |
| `python -m pytest -q -o addopts=""` | 1321 passed, 1 skipped | **1321 passed, 1 skipped** (212 s) |
| `python -m pytest -q -o addopts="" -m full` | 15 passed | **15 passed** |
| `flake8 src/` | sin errores | **exit 0** |
| `ruff check src/` | All checks passed | **All checks passed!** |
| `python -m mypy src/mira/` | 136 archivos | **Success: no issues found in 136 source files** |
| `python -m mkdocs build --strict` | OK | **exit 0** |
| `PYTHONPATH=src python -m mira.cli --check` | Check OK | **Check OK** |

Nota sobre `flake8`: `task.md` §3 y el CI (`python-package.yml:34`) solo pasan
`flake8 src/`. Ampliado a `flake8 src tests` —que es lo que exige
`AGENTS.md`— aparece un **F401 ×2 en `tests/test_ui_headless_core.py:6,9`**:
al eliminar los tests de descarga de modelos quedaron sin uso
`from pathlib import Path` y `from mira.ui.i18n import tr`. El CI no lo detecta
porque nunca mira `tests/`. Corregido en el mismo commit (imports eliminados).

Cifras del diff también coinciden: **75 archivos cambiados, 1211 inserciones,
6422 borrados** y 8 archivos sin seguimiento (5 módulos + 2 tests + `task.md`).

Comprobaciones adicionales que pasé y no están en `task.md`:

- Las 15 tablas de API tienen exactamente los mismos tamaños que las 15 fachadas
  antiguas (16/17/15/13/5/6/8/10/16/11/5/2/8/6/5 = **143 entradas**).
- **Todas** las 143 entradas son resolubles en una `Database` real (0 `AttributeError`).
- Los 143 métodos públicos de las fachadas antiguas tienen equivalente en el
  mapa nuevo o en `Database` (0 pérdidas) y las firmas son compatibles
  salvo 4 renombres de parámetro (ver H9).
- `llm-secrets.json` **no** entra en los respaldos: `BackupRepository.create_backup()`
  solo hace `conn.backup(dest)` sobre el `.db` (confirmado en
  `src/mira/db/repositories/backup_repository.py:57`).
- i18n: 0 claves huérfanas ES/EN, 20 claves nuevas `settings.ai.*`/`settings.mcp.*`
  presentes en ambos idiomas, sin valores vacíos.
- Sin residuos de llama.cpp/GGUF fuera de los tests (solo nombres de archivo
  `.gguf` en tests legacy) y ninguna referencia a `mira.db.backend` /
  `DatabaseBackend` / `*Facade`.

---

## 4. Hallazgos

### H1 — Alta: el servidor MCP no habla el protocolo MCP (framing LSP)

`src/mira/mcp_server.py:82-110` implementa framing **LSP** (`Content-Length:
N\r\n\r\n`), pero la especificación del transporte *stdio* de MCP define
mensajes JSON-RPC **delimitados por saltos de línea** ("Messages are delimited
by newlines"). El código es internamente consistente (cliente y servidor usan el
mismo framing), lo que lo hace pasar cualquier prueba hecha contra sí mismo, pero
**no se conecta con ningún cliente MCP real** (Claude Desktop, MCP Inspector,
SDK `mcp` de Python).

Prueba empírica (cliente que envía el framing correcto de MCP):

```
$ printf '{"jsonrpc":"2.0","id":1,"method":"initialize",...}\n' | mira-cli --db X mcp
exit: 0
stdout: b''          # sin respuesta alguna
stderr: b''
```

El bucle `while True: line = readline()` interpreta la línea JSON como cabecera
(`{"jsonrpc"` → clave), sigue leyendo hasta EOF y devuelve `None` → salida
silenciosa con código 0. Un cliente real no ve `tools/list` ni siquiera.

Impacto: la mitad del objetivo §1.2 (punto 2) y de §1.1 (punto 2) no es
alcanzable en la práctica. Además el protocolo **no se ha verificado nunca**
contra una implementación de referencia, lo que explica que el error pasara
desapercibido.

### H2 — Alta: `add_income` / `add_expense` escriben en la cuenta equivocada sin avisar

`cli_commands.add_movement()` (`src/mira/cli_commands.py:47-61`) delega la
resolución de cuenta en `Executor`, cuyo `resolve_known_account()` devuelve
`None` para un nombre desconocido y cae a `default_account()`. Como el nombre
viene de un argumento **preciso** de tool MCP (no de texto natural), el fallback
es un error silencioso.

```
$ mira-cli --db X --json expense add --amount 5 --account "No Existe"
{"ok": true, "message": "Expense recorded: 5.00 None (converted: 5.00) (account: General)", ...}
```

Es decir: escritura en `General` + `ok: true`. Verificado también a través de MCP
(`tools/call` → `add_expense` con `"account": "Nonexistent Account"` creó la
transacción 305 en `General` y devolvió `isError` ausente).

Inconsistencia interna que lo hace más llamativo: `transfer()` y
`list_transactions()` **sí** usan `_account_id()`, que lanza `ValueError`
("Account not found") y el CLI sale con código 2. Los dos caminos de escritura
no se comportan igual, que es exactamente el error que un agente LLM comete en
un segundo de usar mal.

Recomendación: resolver la cuenta estrictamente en `add_movement` (reusar
`_account_id`) y no dejar que el Executor aplique el fallback para entrada
estructurada.

### H3 — Media: el extra `mcp` es una dependencia muerta

`pyproject.toml` declara `mcp = ["mcp>=1.9.0"]`, `requirements.txt` lo añade
como "optional feature" y el README lo anuncia, pero **ningún módulo importa
`mcp`** (verificado: `grep -rn "import mcp" src/` → 0 resultados; el paquete
tampoco está instalado en el entorno). El servidor está hecho a mano. Instalar
`pip install ".[mcp]"` no aporta nada y sugiere una garantía que no existe
—justo la garantía que habría detectado H1—.

### H4 — Media: 332 líneas nuevas sin un solo test

Ningún test importa `mira.mcp_server` ni `mira.cli_commands`
(`tests/test_cli.py` tiene 14 tests, ninguno sobre `income/expense/transfer/
transactions list/report/record/mcp` ni sobre `--json`). `task.md` §4.3 reconoce
el hueco de MCP, pero **no menciona `cli_commands.py`** (116 líneas) ni que los
subcomandos nuevos del CLI están sin cubrir. Con `--cov` en `addopts` esto se ve
como cobertura verde sobre módulos no ejecutados.

Mínimo razonable: `_cli_argv` (mapeo tool → argv), el ciclo
`serve_stdio → mira-cli --json`, y el código de salida 2 de `mcp` sin
consentimiento (que sí verifiqué a mano: correcto).

### H5 — Media: el "sidecar 0600" tiene carreras y no se puede borrar

`write_api_key()` (`src/mira/ai/llm_config.py:94-101`) hace
`write_text()` y **después** `os.chmod(0o600)`: entre ambas operaciones el
archivo existe con los permisos del umask (típicamente `0644`), y si el
`chmod` falla se hace `return` silencioso. `docs/optional_local_ai.md` y el
README afirman "0600" como si fuera garantizado. Debería crearse con
`os.open(path, O_CREAT|O_WRONLY|O_TRUNC, 0o600)`.

Además: **la API key nunca se borra**. El flujo de Ajustes escribe siempre
`llm_api_key` (incluso al elegir proveedor `none` o al **rechazar** el aviso a
terceros), así que el secreto queda en disco en texto plano sin ninguna forma
de limpiarlo desde la UI. Dado que el propio diseño lo justifies (el ledger
nunca sale, la clave tampoco debería quedarse sin motivo), falta un botón de
"borrar clave" o, al menos, borrar el sidecar al pasar a `none`.

### H6 — Media-baja: todo fallo de chat se reporta como "no hay proveedor"

`Pipeline.process_chat()` (`src/mira/ai/pipeline.py:148-154`) descarta la
excepción y devuelve siempre `_chat_unavailable_message()` ("Chat mode is
unavailable because **no AI provider is configured** in Settings"). Un 401, un
502 o un host inalcanzable se muestran como si faltara la configuración; el
motivo real (`Chat request failed with HTTP 401`, `Chat endpoint unreachable: …`)
solo queda en el log. `RemoteChatEngine` ya construye mensajes de error
correctos: el pipeline los tira. Con depuración remota esto va a generar
soportes-ticket innecesarios.

### H7 — Baja: lógica de consentimiento duplicada en la UI

`src/mira/ui/views/settings.py:37` redefine
`_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})` y calcula el
host con su propio `_current_host()`, mientras `llm_config` ya exporta
`is_loopback_url()`, `url_host()` y `endpoint_host()`. Hoy coinciden (el fichero
ya importa `url_host` de `llm_config`), pero son dos fuentes de verdad para la
regla de seguridad: si mañana se admite `127.0.0.0/8` o `.local`, hay que
recordar los dos sitios. Lo natural es que la vista use `is_loopback_url()` /
`endpoint_host(LlmConfig(...))`.

Nota positiva: la regla es **fail-closed** en todos los casos que probé
(`api.openai.com.evil.com`, `localhost.evil.com`, `https://api.openai.com@evil.com`,
URL vacía → todos se consideran "tercero"), y `chat_allowed` exige
`ack_host == endpoint_host`, de modo que cambiar de host invalida el acuse.

### H8 — Baja: cambio de comportamiento no documentado en `tag_repository`

`set_transaction_tags()` gana `device_id` / `touch_sync` y ahora **sí** actualiza
`last_modified_by_device_id` / `updated_at` (`tag_repository.py:206-226`). La
fachada antigua (`git show HEAD:src/mira/db/database.py`) aceptaba esos dos
parámetros y **los ignoraba en silencio**. Es decir, es un bug fix real
embebido en un refactor que se presenta como mecánico, sin mención en
`task.md` §2.6 y sin test que cubra la rama nueva. Merece una línea en el
changelog.

### H9 — Baja: 4 renombres de parámetro en la API pública colapsada

`category.update(cat_id → category_id)` y
`recurring.{get,update,delete}(recurring_id → rec_id)`. No hay ningún llamador
por palabra clave dentro del repo (verificado), así que no rompe nada aquí, pero
es una ruptura silenciosa para cualquier consumidor externo del API
(`mira-mobile-helper` es un submódulo aparte). Si el API no es público,
convendría dejar los nombres antiguos.

### H10 — Baja: MCP no está documentado para el usuario

README y docs mencionan el extra `[mcp]` en dos líneas y nada más. Falta: cómo
se habilita (Ajustes → MCP + acuse), cómo registra un cliente
(`mira-cli mcp` como comando), qué significa el código de salida 2, y cuáles
son las 5 tools. Dado que el consentimiento es la barrera de seguridad de esta
funcionalidad, la documentación es parte del control, no un extra. En el mismo
apartado, los subcomandos nuevos del CLI (`record`, `report`,
`transactions list`…) tampoco aparecen en el README, que solo lista flags
globales.

### H11 — Baja: hueco de markdown en los docs

En `docs/troubleshooting.md:34-35` y `docs/es/troubleshooting.md` el ítem
`3. Review logs with --debug.` queda pegado a `## CSV import fails` sin línea en
blanco (se perdió el salto de línea que tenía el original). Renderiza, pero es un
error de formato en un fichero recién editado.

### H12 — Baja: la i18n queda partida en dos

`mira.i18n` es el módulo real, pero 28 módulos de UI siguen importando el shim
`mira.ui.i18n`; solo la capa no-Qt (`pipeline`, `executor`, `error_policy`,
`db/helpers`, `db/io_csv_excel`, `feedback_repository`, `model_lifecycle`) usa la
ruta nueva. Funciona, pero el shim existe solo para no tocar 28 ficheros: o se
termina el cambio, o se elimina el shim y se asumen los 28 `sed`.

### H13 — Informativa: deuda y flags muertos que deja la eliminación de llama.cpp

- `main.py:144` declara `startup_alert = None` y ya **nadie** lo asigna, pero
  `MainWindow` sigue recibiéndolo y mostrándolo (el aviso "el modelo ya no está
  en disco" era su único productor).
- `Pipeline._model_path`, `ModelLifecycle.active_model_path` y
  `resolve_model_path()` ahora contienen un **nombre de modelo**, no una ruta;
  el nombre del campo miente y `mira --model PATH` sigue aceptándose sin efecto.
- `preferred_model` sigue sembrado, leído y escrito por el servicio de Ajustes,
  pero la UI siempre escribe `""`; `model_download_offer_shown` se quitó de las
  semillas pero queda en las bases existentes (inofensivo) y aún lo usa un test.
- `settings.mode.chat_unavailable`/`_CHAT_UNAVAILABLE_MESSAGES` está duplicado
  entre `pipeline.py` y `model_lifecycle.py` (además de la clave i18n).
- En `mcp_server._call_tool`, `--since` se añade dos veces para `report`
  (`_cli_argv` y `_optional_flags`); inocuo con argparse (gana el último), pero
  es ruido. Y `ping` responde `-32601`, que es un método de utilidad válido del
  protocolo MCP.
- `reload_engine()` llama `set_default_currency` dos veces (preexistente).
- Alias `--outpu-file` (typo) en `cli.py:53`: **preexistente**, pero ahora el
  CLI es superficie documentada y promovida desde MCP/README; es el momento de
  arreglarlo.
- `docs/solucion_problemas.md` es byte-idéntico a `docs/troubleshooting.md`
  (preexistente): el fichero "en español" sigue en inglés.

### H14 — Informativa: `requirements.txt` ya no representa el proyecto

Mantiene `PySide6` y `qt-material` sin marcar, añade `mcp` "opcional" y no lo
consume nadie (ningún workflow ni script de `packaging/` lo usa; CI y el
validador instalan `.[dev]`). Es un fichero que ya no describe ninguna
combinación instalable real; lo dejaría como "entorno de desarrollo completo"
explícito o lo regeneraría desde `pyproject.toml`.

### H15 — Informativa: endurecimiento menor del cliente HTTP

`_post_json()` usa `urllib.request.urlopen` con verificación TLS por defecto
(bien) y timeout de 60 s (bien), pero no restringe redirecciones: un endpoint
nube mal configurado o comprometido puede devolver un 30x y desviar la
conversación a otro host sin que el acuse por host lo note. También
`_anthropic_chat` envía `x-api-key: ""` si no hay clave (error 401 opaco en vez
de un mensaje claro). Ambos son menores y easy-fix.

---

## 5. Lo que está muy bien hecho

- **Fail-closed en el consentimiento**: loopback exacto (no prefijo), ack atado
  al host real, comparación por host y no por " checkbox marcado", MCP exige
  *dos* flags, y `mcp_enabled=False` → salida 2. Probé los casos de ataque
  habituales (`localhost.evil.com`, userinfo `api.openai.com@evil.com`, base URL
  vacía) y ninguno cuela.
- **Invariante de privacidad verificada**: `RemoteChatEngine.chat()` envía
  exactamente `system` + `user`, y hay un test que lo comprueba inspeccionando el
  `Request` construido, no un mock de alto nivel. El ledger no sale.
- **La API key fuera del `.db`** y, por tanto, fuera de los respaldos, verificado
  leyendo `create_backup()`. La idea es correcta y está bien ejecutada.
- **El colapso de la fachada es una migración fiel**: comprobé las 143 firmas
  una a una contra las 15 fachadas de `HEAD`; los tamaños coinciden uno a uno y
  solo sobreviven 4 renombres de parámetro. Los wrappers explícitos
  (`category.update`, `budget.export_comparison_excel`) están bien identificados.
- **`_Namespace` resuelve en cada acceso** vía `getattr`, lo que preserva el
  monkeypatch de los tests sin trucos de copia. Decisión acertada.
- **Tests nuevos de calidad**: `test_llm_config.py` incluye la matriz completa de
  `chat_allowed` (incluido el caso de ack caducado por cambio de host) y verifica
  los permisos del sidecar; `test_remote_chat.py` cubre ambos proveedores, los
  errores HTTP y que **no** se envía la cabecera `Authorization` sin clave.
- **El flujo de consentimiento de la UI está testeado** (5 tests en
  `test_settings_view.py`: loopback sin diálogo, rechazo, acuse por host, MCP).
- **Sin residuos**: la eliminación de llama.cpp/GGUF es física y completa
  (módulos, tests, coordinators, scripts de build, seeds, i18n, docs, snap).

---

## 6. Recomendaciones, por orden

1. **Arreglar el framing de MCP** (H1) o, si el objetivo es no escribir el
   protocolo a mano, usar el SDK `mcp` (que ya está declarado, H3) y añadir un
   test que hable con un cliente real de la especificación. Sin esto, la
   funcionalidad MCP no existe para el usuario.
2. **Validar la cuenta estrictamente en `add_income`/`add_expense`** (H2) antes
   de escribir, igual que ya hace `transfer`.
3. **Añadir tests de `mcp_server` y `cli_commands`** (H4), empezando por
   `_cli_argv` y el ciclo completo hasta `--json`.
4. **Crear el sidecar con 0600 en la propia creación y ofrecer borrar la
   clave** (H5); o suavizar la afirmación de los docs.
5. **Propagar el motivo real del error de chat a la UI** (H6).
6. Documentar MCP y los subcomandos nuevos (H10) y arreglar el hueco de markdown
   (H11).
7. Higiene: unificar la regla loopback en `llm_config` (H7), registrar el cambio
   de `set_transaction_tags` (H8), cerrar la deuda de flags muertos (H13),
   limpiar `requirements.txt` (H14).

Nada de lo anterior bloquea el resto del trabajo: el diseño de privacidad, la
separación de la base de datos y la eliminación del LLM embebido son un avance
sólido y verificable. Los dos hallazgos altos (H1, H2) son de una tarde de
trabajo cada uno y no comprometen ninguna de las decisiones de diseño del plan.

---

## 7. Nota sobre el estado del árbol

Se confirma lo indicado en `task.md` §4.1: todo está en el working tree, sin
commit ni staging (75 modificados + 8 sin seguimiento). `git status` está limpio
de staging, tal y como se describe. Los restos aceptables (`packaging/snap`
`MIRA_MODELS_DIR`, `src/mira/models/`, `dist-assets/models/.gitkeep`,
`CHANGELOG.md`, `.pyc` huérfanos de los módulos borrados) son reales y coinciden
con la nota de mantenimiento §4.2.

---

## 8. Correcciones aplicadas y seguimiento

### 8.1 H1 y H2 corregidos en el working tree (sin commit)

| Hallazgo | Archivo | Cambio |
| --- | --- | --- |
| H1 | `src/mira/mcp_server.py` | Framing LSP → **newline-delimited JSON-RPC** (spec MCP). Líneas corruptas se saltan con `logger.debug` en vez de tumbar el bucle; se añade `ping`; `tools/call` captura también `TypeError`/`OSError`. |
| H2 | `src/mira/cli_commands.py` | Nuevo `_require_known_account()` al inicio de `add_movement()`: cuenta vacía o no resoluble → `ValueError` → mensaje por stderr y **exit 2 sin escribir**. Usa `ExecutorAccountResolver.resolve_known_account()`, el mismo resolutor del `Executor`, para no duplicar reglas ni perder la resolución por mención única. |

Verificación tras los cambios:

- MCP con el framing de la especificación: `initialize` ✅, `tools/list` (5 tools) ✅,
  `ping` → `{}` ✅, `add_expense` con cuenta inexistente → `isError: true` con
  `"Account not found: Nonexistent Account"` ✅ (antes creaba la transacción 305
  en la cuenta por defecto y devolvía `ok: true`).
- CLI: cuenta inexistente → `Account not found: No Existe`, exit 2, 0
  transacciones nuevas; cuentas válidas sin cambios.
- `python -m pytest -q -o addopts=""` → **1321 passed, 1 skipped** (sin regresión).

### 8.1.1 Regresión de lint introducida por el propio cambio

`flake8 src tests` (más estricto que el CI, que solo mira `src/`) fallaba con
**F401 ×2** en `tests/test_ui_headless_core.py`: al borrar los tests de descarga
de modelos quedaron sin uso `Path` y `tr`. Imports eliminados; `flake8 src tests`
vuelve a estar limpio.

### 8.1.2 Verificación final antes del commit

| Comando | Resultado |
| --- | --- |
| `pytest -q -o addopts=""` | 1321 passed, 1 skipped |
| `pytest -q -m full -o addopts=""` | 15 passed |
| `flake8 src tests` | limpio |
| `ruff check src tests` | All checks passed |
| `mypy src` | Success: 136 archivos |
| `mkdocs build --strict` | exit 0 |
| `PYTHONPATH=src python -m mira.cli --check` | Check OK |

### 8.2 Issues de seguimiento creados

| # | Título | Etiqueta | Origen |
| --- | --- | --- | --- |
| [#7](https://github.com/bmosoluciones/mira-personal-finance-assistant/issues/7) | framing LSP en el servidor stdio MCP | bug | H1 (corregido) |
| [#8](https://github.com/bmosoluciones/mira-personal-finance-assistant/issues/8) | cuenta inexistente → escritura en la cuenta por defecto | bug | H2 (corregido) |
| [#9](https://github.com/bmosoluciones/mira-personal-finance-assistant/issues/9) | el extra `[mcp]` no lo importa nadie | enhancement | H3 |
| [#10](https://github.com/bmosoluciones/mira-personal-finance-assistant/issues/10) | sin cobertura para `mcp_server.py` y `cli_commands.py` | enhancement | H4 |
| [#11](https://github.com/bmosoluciones/mira-personal-finance-assistant/issues/11) | `llm-secrets.json`: carrera del chmod 0600 y clave no borrable | bug | H5 |
| [#12](https://github.com/bmosoluciones/mira-personal-finance-assistant/issues/12) | todo error de chat se reporta como "no hay proveedor" | bug | H6 |
| [#13](https://github.com/bmosoluciones/mira-personal-finance-assistant/issues/13) | regla de loopback duplicada entre UI y `llm_config` | enhancement | H7 |
| [#14](https://github.com/bmosoluciones/mira-personal-finance-assistant/issues/14) | `set_transaction_tags` toca `last_modified_by_device_id` sin documentar | bug | H8 |
| [#15](https://github.com/bmosoluciones/mira-personal-finance-assistant/issues/15) | 4 parámetros renombrados rompen llamadas por palabra clave | bug | H9 |
| [#16](https://github.com/bmosoluciones/mira-personal-finance-assistant/issues/16) | MCP y subcomandos de `mira-cli` sin documentar | documentation | H10 |
| [#17](https://github.com/bmosoluciones/mira-personal-finance-assistant/issues/17) | salto de línea perdido en `troubleshooting` | documentation | H11 |
| [#18](https://github.com/bmosoluciones/mira-personal-finance-assistant/issues/18) | migración de i18n partida (28 ficheros) | enhancement | H12 |
| [#19](https://github.com/bmosoluciones/mira-personal-finance-assistant/issues/19) | cableado muerto tras eliminar llama.cpp | enhancement | H13 |
| [#20](https://github.com/bmosoluciones/mira-personal-finance-assistant/issues/20) | `requirements.txt` desalineado con `pyproject.toml` | enhancement | H14 |
| [#21](https://github.com/bmosoluciones/mira-personal-finance-assistant/issues/21) | redirecciones HTTP sin restringir + `x-api-key` vacío | enhancement | H15 |

Los issues #7 y #8 quedan abiertos a propósito: falta el commit del arreglo y
los tests de regresión (que van dentro del alcance de #10).
