# task.md — MIRA: plan aprobado y cambios realizados

> Estado: **trabajo completo en local, sin commit** (75 archivos cambiados,
> `git status` limpio de staging: todo queda como cambio de working tree).
> Rama `main` sobre `cdaa1cb`.

---

## 1. Plan aprobado

### 1.1 Objetivo

Rehacer la arquitectura de MIRA (asistente de finanzas personales local-first):

1. **Quitar el LLM embebido** (llama.cpp / GGUF / `llama-cpp-python`) y pasar a
   **APIs HTTP externas**: proveedor compatible con OpenAI (LM Studio, Ollama,
   OpenAI…) y Anthropic.
2. **Servidor MCP opcional** por **stdio**, invocado desde `mira-cli mcp`.
3. **Completar `mira-cli`** con comandos de registro y consulta.
4. **Colapsar la fachada de base de datos** (eliminar la capa `*Facade` y la
   clase intermedia `DatabaseBackend`).
5. **Sacar PySide6 de la dependencia global** (extra `[gui]`).

### 1.2 Decisiones confirmadas por el usuario

| Tema | Decisión |
| --- | --- |
| Proveedores | OpenAI-compatible + Anthropic |
| Alcance MCP | lectura y escritura |
| Transporte MCP | stdio vía `mira-cli mcp` |
| MCP sin servicio intermedio | cada tool lanza `subprocess` de `mira-cli … --json` |
| Parser | el parser determinista local sigue siendo el modo por defecto |
| Privacidad del chat | solo prompt de sistema + texto del usuario; **nunca** el libro mayor |
| Entrega | cambios en local, **sin commit** |

### 1.3 Reglas de aviso a terceros (consentimiento)

- **Loopback** (`localhost`, `127.0.0.1`, `::1`) → sin diálogo.
- **Otro host** o **Anthropic** → exige acuse (`llm_third_party_ack=1` +
  `llm_ack_host` = host real del endpoint).
- **MCP** → siempre exige acuse (`mcp_enabled=1` + `mcp_third_party_ack=1`);
  si está apagado, `mira-cli mcp` sale con código 2.
- Si el usuario **rechaza** el acuse, el proveedor se guarda como `none`
  (el chat queda deshabilitado).

### 1.4 Seguridad de la API key

- No va en SQLite: sidecar **`llm-secrets.json`** junto a la base, permisos
  `0600`.
- Queda **fuera del respaldo** porque `create_backup()` copia únicamente el
  archivo `.db` (SQLite `conn.backup`).

---

## 2. Cambios realizados

### 2.1 Núcleo LLM remoto (nuevo)

| Archivo | Líneas | Contenido |
| --- | --- | --- |
| `src/mira/ai/llm_config.py` | 123 | `LlmConfig`, `endpoint_host`, `url_host`, `is_loopback_url`, `secrets_path_for`, `read_api_key` / `write_api_key` (0600), `load_llm_config`, `mcp_enabled` |
| `src/mira/ai/remote_chat.py` | 117 | `RemoteChatEngine`: chat HTTP con proveedor OpenAI-compatible y Anthropic |
| `src/mira/mcp_server.py` | 216 | servidor MCP stdio (encuadre LSP `Content-Length`), 5 tools |
| `src/mira/cli_commands.py` | 116 | implementación de los subcomandos nuevos de `mira-cli` |
| `src/mira/i18n.py` | 2251 | i18n movida desde `src/mira/ui/i18n.py` (que queda como shim de re-export) |

- `src/mira/ai/engine.py`: `get_chat_engine(config, …)` devuelve
  `RemoteChatEngine` solo si `chat_allowed`; `get_engine()` devuelve
  `TransactionParserEngine`. Eliminados los helpers llama
  (`is_llama_cpp_available`, `_looks_like_raspberry_pi`,
  `_detect_gpu_layers_for_llama`, `_recommended_llama_kwargs`).
- `src/mira/ai/pipeline.py`: `reload_engine()` ahora recarga el chat HTTP desde
  los ajustes guardados (`model_path` queda como parámetro legado sin efecto).

### 2.2 Eliminación física de llama.cpp / GGUF / descargas

Borrados:

- `src/mira/ai/chat_engine.py`
- `src/mira/ai/model_registry.py`
- `src/mira/app/model_download_service.py`
- `src/mira/ui/coordinators/model_download_coordinator.py`
- `src/mira/ui/coordinators/model_download_flow.py`
- `llama_cpp_compiler/` (4 scripts huérfanos de build de wheels, sin referencias)
- Tests: `test_chat_engine_unit.py`, `test_model_registry.py`,
  `test_model_download_service.py`, `test_model_download_flow.py`,
  `test_model_download_coordinator.py`

Limpieza derivada: `src/mira/app/__init__.py`, `main_window.py`,
`main_window_layout.py`, `main_window_lifecycle.py` sin flujos de descarga
(se eliminó la señal `download_default_model_requested` y las 226 líneas de
tests de descarga en `test_ui_headless_core.py`); `.gitignore` sin reglas
`*.gguf` ni de datos de fine-tuning.

### 2.3 Ajustes (Settings)

- **UI** `src/mira/ui/views/settings.py` (245/129): combo de proveedor
  (none / openai_compatible / anthropic), URL base, modelo, API key enmascarada,
  checkbox de acuse con host, combo de modo (assistant / chat), checkbox MCP +
  acuse; confirmaciones con `QMessageBox.question`; sin
  `is_llama_cpp_available` / `discover_gguf_models`.
- **Servicio** `src/mira/app/view_services/settings.py`: `SettingsViewState`
  con `llm_provider`, `llm_base_url`, `llm_model`, `llm_api_key`,
  `llm_third_party_ack`, `llm_ack_host`, `mcp_enabled`; `save()` persiste esos
  campos y delega la API key al sidecar.
- **Semillas** `src/mira/db/bootstrap.py`: `llm_provider=none`,
  `llm_base_url=http://localhost:1234/v1`, `llm_model=""`,
  `llm_third_party_ack=0`, `llm_ack_host=""`, `mcp_enabled=0`,
  `mcp_third_party_ack=0`, `llm_interaction_mode=assistant`.
- **i18n**: nuevas claves `settings.ai.*` y `settings.mcp.*` (ES + EN);
  eliminadas `settings.models*`, `settings.download_default_model`,
  `settings.chat_support_unavailable`; `chat.unavailable` y
  `chat.diagnostics.body` reescritos sin GGUF.
- `mira --model` sigue aceptado por compatibilidad, ahora documentado como
  **obsoleto e ignorado**.

### 2.4 CLI

- `src/mira/cli.py` (128/28): flags `--db`, `--version`, `--check`
  (import headless, no carga Qt), `--json`; subcomandos:
  `backup`, `restore`, `seed`, `income add`, `expense add`, `transfer`,
  `transactions list`, `report`, `record`, `mcp`.
- `src/mira/cli_commands.py`: lógica de cada subcomando; `ValueError` →
  código de salida 2.
- `mira-cli mcp` valida el consentimiento, cierra la conexión y delega en
  `mira.mcp_server.serve_stdio`.

### 2.5 MCP (`src/mira/mcp_server.py`)

- Tools: `add_income`, `add_expense`, `transfer`, `list_transactions`,
  `report`.
- Cada invocación ejecuta `python -m mira.cli --db <path> --json …` vía
  `subprocess` (sin servicio intermedio ni estado compartido).
- Errores de CLI (`KeyError`, `RuntimeError`, `ValueError`) se devuelven como
  `result.content[0].text` con `isError: true`.

### 2.6 Colapso de la fachada de base de datos

- **Borrado** `src/mira/db/backend.py` (`DatabaseBackend`, 42 líneas).
- **`src/mira/db/database.py`: 1286 → 324 líneas.**
  - `class Database(DatabaseRuntime + 14 repositorios)` — un solo objeto.
  - 15 espacios de nombres públicos (`db.account`, `db.category`, `db.tag`,
    `db.transaction`, `db.reconciliation`, `db.recurring`, `db.savings_goal`,
    `db.setting`, `db.budget`, `db.report`, `db.bucket`, `db.backup`,
    `db.feedback`, `db.sync`, `db.io`) con **143 entradas** mapeadas.
  - `_Namespace` resuelve cada entrada de forma **perezosa** (`getattr` en cada
    acceso) para que el monkeypatch de los tests siga operando.
  - Wrappers explícitos donde la fachada no era passthrough:
    `category.update` (conserva defaults `#888888`/`is_savings=False`/…),
    `budget.export_comparison_excel` (delega en `DatabaseIOService`).
- `FeedbackRepository.resolve_single_message` ahora acepta
  `Sequence[MessageCandidate | dict]` y normaliza internamente (antes la
  conversión vivía en la fachada).
- Referencias a `_backend` migradas:
  `tests/db_inspection.py`, `test_database.py`, `test_cli.py`,
  `test_category_relations.py`, `test_mira_master_report.py`,
  `test_mira_realtime_insights.py`, `test_mobile_sync_service.py`,
  `src/mira/services/mobile_sync.py` (`_push_atomic_context` usa
  `getattr(self._db, "_atomic", None)`).
- `tests/test_database_mixins_refactor.py` reescrito: verifica que `Database`
  no define métodos de negocio ni que existan `_DatabaseBackend` / clases
  `*Facade`.

### 2.7 Dependencias y empaquetado (`pyproject.toml`)

```toml
[project.optional-dependencies]
gui = ["PySide6==6.10.2", "qt-material==2.14"]
mcp = ["mcp>=1.9.0"]
docs = ["mkdocs>=1.6.0", "mkdocs-material>=9.6.0", "mkdocs-static-i18n>=1.3.0"]
dev = [..., "mcp>=1.9.0", ...]   # sin llama-cpp-python, sin extra "chat"
```

- Base sin PySide6; `requirements.txt` gana `mcp>=1.9.0`.
- README: dependencias base vs extras `[gui]`/`[mcp]`/`[dev]`, flag `--model`
  obsoleto y sección *Chat mode* reescrita.

### 2.8 Documentación

- Reescritos/limpiados (EN + ES): `troubleshooting.md`,
  `solucion_problemas.md`, `optional_local_ai.md`,
  `modelos_ia_opcional.md`, `faq.md`, `installation.md`, `instalacion.md`,
  `README.md` — sin `gguf`, `llama-cpp-python` ni `pip install ".[chat]"`.
- `mkdocs.yml`: nav `Optional Local AI` → `Optional AI Chat`
  (`IA Chat Opcional`).

### 2.9 Tests

- Nuevos: `tests/test_llm_config.py` (168 líneas) y
  `tests/test_remote_chat.py` (180 líneas).
- Reescritos/adaptados: `test_settings_view.py`, `test_engine_factory.py`,
  `test_model_lifecycle.py`, `test_main.py`, `test_i18n.py`,
  `test_pipeline.py`, `test_database_mixins_refactor.py`, `test_cli.py`,
  `test_feedback_logic.py`, `test_ui_headless_core.py`.

---

## 3. Verificación (todo en verde)

| Comando | Resultado |
| --- | --- |
| `python -m pytest -q -o addopts=""` | **1321 passed, 1 skipped** |
| `python -m pytest -q -o addopts="" -m full` | **15 passed** |
| `flake8 src/` | sin errores |
| `ruff check src/` | `All checks passed!` |
| `python -m mypy src/mira/` | `Success: no issues found in 136 source files` |
| `python -m mkdocs build --strict` | OK (0 errores; avisos preexistentes de páginas fuera de nav) |
| `PYTHONPATH=src python -m mira.cli --check` | `Check OK: headless modules imported correctly.` |

Diferencia total: **75 archivos cambiados, 1211 inserciones, 6422 borrados**
(más 8 archivos sin seguimiento: los 7 nuevos de código/tests y este
`task.md`).

---

## 4. Pendientes / notas de mantenimiento

1. **Sin commit**: todo está en working tree; el commit debe hacerlo el usuario.
2. Limpiezas menores opcionales relacionadas con el modelo eliminado:
   - `packaging/snap/snapcraft.yaml`: variable `MIRA_MODELS_DIR` (ya no la lee
     ningún código).
   - `src/mira/models/__init__.py` (paquete "MIRA datasets" sin importaciones)
     y `dist-assets/models/.gitkeep`.
   - `CHANGELOG.md` conserva la mención histórica de GGUF/`llama-cpp-python`
     de versiones pasadas (decisión: no reescribir historia).
   - `__pycache__` con `.pyc` huérfanos de los módulos borrados.
3. **Tests de MCP**: `src/mira/mcp_server.py` todavía no tiene tests propios
   (`tests/` no contiene ningún archivo de MCP). Conviene cubrir `_cli_argv`
   (mapeo tool → argv) y el ciclo completo `serve_stdio → mira-cli --json`.
