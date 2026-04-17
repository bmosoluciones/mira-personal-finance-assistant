# Changelog

All notable changes to this project will be documented in this file.

The format is inspired by Keep a Changelog and follows semantic releases.

## [Unreleased]

## [0.0.1b3] - 2026-04-17

### Added

- **Bank reconciliation**: new reconciliation dialog accessible from the Accounts view toolbar, context menu, and the Accounts menu in the menu bar. Users can load a bank statement Excel file (`.xlsx`), compare external transactions side-by-side with system transactions, reconcile selected rows, clear reconciliation marks, and inspect opening/closing balance summaries per account and date range. Schema migrated to v4 with `reconciliation_groups`, `reconciliation_matches` tables, and `is_reconciled`/`reconciled_at` columns on transactions.
- Migration audit trail: `schema_version` table now records the origin version and each applied version step, providing full auditability of applied migrations.
- ~70 i18n keys for reconciliation UI in Spanish and English.

- Transaction amount field now accepts simple arithmetic formulas (e.g. `=100+50`, `=(200*3)/4`) using the same formula engine as the budget planner. Only positive results are accepted.
- Category dropdown in the create/edit transaction dialog is now searchable: typing filters categories by name using a case-insensitive contains match, making it easy to find categories in large lists.

### Fixed

- Settings now let users correct the system default currency after onboarding, and the deterministic assistant picks up the new default without restarting MIRA.
- Presupuestos and Budget vs Actual tables now keep the category column usable on laptop-width screens by applying explicit responsive column sizing and enabling horizontal scrolling when needed.
- Transaction and transfer dialogs now open with a minimum width of 720 px so the two-column form layout is never cut off.
- The create/edit transaction dialog now also opens with a larger default height to prevent the two-column form from appearing truncated on desktop screens.
- Report load failures now preserve the detailed runtime error when one is available, while keeping the localized fallback status message for empty failures.
- CI dependency install now covers the full development extras, including pydocstyle and typing stub packages required for mypy validation.

### Changed

### Notes

For the record: I have started using MIRA for my personal income and expense traking.

## [0.0.1b1] - 2026-04-11

### Added

 - Add balance adjustment flow for accounts and cards 

### Changed

- Internal refactor for the demo seed flow, executor collaborators, main window orchestration seams, and dialog package exports while preserving the public behavior of the offline assistant, MIRA report, and notification flows.
- `mira.ui.dialogs.crud` is now a compatibility layer only; transaction, category, budget, recurring, goal, and tag dialogs live in dedicated owner modules, while `MainWindow` now delegates layout and navigation to focused mixins and the demo seed/executor helpers moved further into internal collaborators.
- `MainWindow` now delegates prompt/chat command flow to a dedicated mixin, `Executor` delegates income/expense recording to a transaction recorder collaborator, and the demo seed bootstrap now uses explicit runtime/result builders to keep the seed entrypoint declarative.
- Beta readiness cleanup: the main window shell/refresh helpers now live in a dedicated mixin, executor delegation was reduced further to collaborators, and the development environment documentation/metadata now explicitly includes `openpyxl` so `pytest -m full` is a real quality gate instead of an implicit setup trap.
- Master-data deletion confirmations now explicitly warn that accounts, categories, tags, budgets, recurring rules, and savings goals are destructive non-reversible changes.

### Fixed

- The create/edit transaction dialog now keeps Save/Cancel accessible by moving the form content into an internal vertical scroll area.
- Category parent selection now only lists root categories, preventing invalid child-as-parent choices that led to false maximum-depth validation errors.
- The accounts view now exposes the existing transfer-between-accounts and credit-card-payment flows directly from the account list.
- Changing the application language now tells the user to close and reopen MIRA for the language change to apply completely.
- Applying recurring transactions without any recurring rules now warns the user instead of falling through into the monthly apply flow.

## [0.0.1a3] - 2026-04-07

### Added

- Schema migration scaffolding in `src/mira/db/migrations.py`, including a version gate, sequential migration registry, and a shared migration entrypoint for future database upgrades.

### Changed

- Database open/restore flows now inspect SQLite `user_version` and route compatible schema upgrades through a staged migration path instead of treating every non-current file as disposable.
- Backup restore now validates the selected file, restores through a staging database, reconnects the runtime after swap, and reports when a schema upgrade was applied during restore.

### Fixed

- Chat batch navigation once again defers the pending assistant-batch reset to the next event-loop tick, preserving focus on the first message when the UI appends multi-part assistant responses within the same turn.
- MIRA now rejects corrupt SQLite files, non-MIRA backups, and unsupported pre-`0.0.1a2` legacy schemas before touching the active database.
- Startup no longer silently deletes incompatible database files when the schema is unsupported for in-place migration.
- Application shutdown now calls `pipeline.shutdown()` before closing the database so loaded GGUF chat resources are released cleanly on exit.

## [0.0.1a2] - 2026-04-02

### Changed

- Breaking: monetary values are now stored as exact integer cents in SQLite instead of floating-point columns, while UI/API/export surfaces continue to show decimal amounts. Existing pre-`0.0.1a2` databases that used float-backed money storage are treated as disposable test data: MIRA no longer ships migration or deep schema-validation logic for those files, does not archive them, and startup recreates the selected database file with the current schema instead of preserving the old contents.
- Breaking (developer-facing): the natural-language transaction JSON contract now treats `amount`, `converted_amount`, `filters.min_amount`, and `filters.max_amount` as exact money values normalized to two-decimal `Decimal` semantics at validation time. `converted_amount` must match `amount * exchange_rate` rounded with `ROUND_HALF_UP`, and a single action still supports only one FX leg into `base_currency`.
- Breaking: MIRA no longer scans or copies databases from the legacy `~/.mira/` location during startup. Databases left in that directory are ignored entirely as of `0.0.1a2`; only the current OS/XDG default path or an explicit `--db` path participates in startup.
- Breaking: existing databases created before `0.0.1a2` are NOT preserved.
  On startup, incompatible database files are silently replaced with a fresh schema,
  resulting in complete data loss.

## [0.0.1a1] - 2026-04-01

### Added

- Database repository layer (`src/mira/db/repositories/`) with dedicated repository classes for accounts, transactions, categories, tags, budgets, buckets, recurring, savings goals, settings, reports, feedback, and backup; replaces the legacy `src/mira/db/mixes/` mixin structure.
- `DatabaseRuntime` base class with a process-wide active-connection guard that raises explicit runtime errors on invalid usage instead of relying on assertions.
- Domain-specific database exceptions in `src/mira/db/errors.py`: `DuplicateCategoryNameError`, `DuplicateTagNameError`, `DuplicateBucketNameError`, `BudgetValidationError`, and `ApplicationError`; UI views now catch these instead of raw `sqlite3` integrity errors.
- `ReportRepository` with Peewee-only queries for financial summaries, category summaries with parent aggregation, tag transaction counts, category transaction counts, and the MIRA master report backend.
- `BaseEngine` abstract interface (`src/mira/ai/base_engine.py`) defining `parse`, `chat`, and `set_language` for all AI engine implementations.
- `PromptAssets` class (`src/mira/ai/prompt_assets.py`) for managing few-shot examples and loading exact-match action examples from the curated CSV dataset.
- `ModelRegistry` class and module-level helpers (`src/mira/ai/model_registry.py`) for GGUF model discovery across platform-specific search paths, writable-directory selection, URL normalization, and cooperative-cancellation downloads; `DownloadCancelledError` raised when a download is cancelled mid-transfer.
- `LlamaCppEngine` moved to a dedicated `src/mira/ai/chat_engine.py` module with `PromptAssets` injected as a constructor dependency.
- `TransactionParserEngine` moved to a dedicated `src/mira/ai/parser_engine.py` module.
- `ApplicationController` (`src/mira/app/application_controller.py`) mapping `ActionResult` outcomes from the executor to UI-agnostic directives.
- `ModelDownloadService` (`src/mira/app/model_download_service.py`) for persisting model selection and reloading the active chat engine at runtime.
- New desktop UI views: `DashboardView` (KPI cards with time filters and recent transactions), `AccountsView`, `BucketsView`, `TagsView`, `RecurringView`, `SavingsGoalsView`, and `SettingsView` (with model discovery and runtime adapter seam).
- `NavigationCoordinator` (`src/mira/ui/coordinators/navigation_coordinator.py`) to synchronize the sidebar selection with the main stacked view.
- `CommandCoordinator` (`src/mira/ui/coordinators/command_coordinator.py`) to execute the NL pipeline in background threads and emit results back to the UI thread.
- `ModelDownloadCoordinator` and `ModelDownloadFlow` (`src/mira/ui/coordinators/`) providing a QThread-backed download worker with cooperative cancellation and a guided UI flow for activating the default GGUF model.
- `ChatState` (`src/mira/ui/coordinators/chat_state.py`) as a pure state holder for chat history navigation.
- Financial calculator dialogs under `src/mira/ui/dialogs/financial/`: compound interest, loan amortization, and savings goal simulator.
- `CardWidget` (`src/mira/ui/widgets/cards.py`) reusable KPI summary card with primary/secondary context labels and per-value color support.
- Table cell delegates (`src/mira/ui/delegates/cell_delegates.py`) for semantic cell customization and transaction-type badge rendering.
- `error_policy.py` (`src/mira/error_policy.py`) with a centralized exception-to-UI-message mapping used across views and coordinators.
- `NotificationService` (`src/mira/ui/notification_service.py`) routing informational messages to message boxes or a status bar depending on context.
- `MenuBuilder` (`src/mira/ui/menu_builder.py`) extracting main-window menu construction into a dedicated builder class.
- `services/` package (`src/mira/services/`) with `ModelLifecycleService` for non-UI model orchestration and `DatabaseIOService` wrapping CSV/Excel import-export paths.
- `MiraAnalysisView` (`src/mira/ui/views/mira_analysis.py`) providing the full MIRA master report workspace including a custom waterfall chart, YTD line chart, stacked bar trend chart, top-categories and top-tags drilldown tables, and assistant context emission.
- `_shared.py` module (`src/mira/ui/views/_shared.py`) consolidating shared UI helpers, table styling, amount formatting, notification routing, and chart configuration used across all views.
- `report_types.py` (`src/mira/ui/views/report_types.py`) with shared report-type constants for menus and views.

### Changed

- Breaking (developer-facing): the runtime database layer now uses Peewee-only repository queries for categories, reports, and feedback. `_DatabaseBackend._cursor()` is no longer part of the supported internal contract.
- Breaking (developer-facing): `message_events` cooldown and deduplication context now lives in typed columns (`reference_date`, `context_category_id`, `context_amount`, `context_source`) instead of the old JSON-backed `extra_context` runtime contract.
- Active desktop views now delegate CRUD/report orchestration through `src/mira/app/view_services/`, keeping widgets focused on rendering, dialogs, and interaction boundaries.
- `ReportsView` and `MiraAnalysisView` now bind pre-shaped presentation state from `src/mira/app/view_services/`, moving comparison formatting, chart datasets, drilldown rows, pagination, and transaction-detail shaping below the widgets.
- The unused legacy `BucketsView` UI and its dedicated `BucketDialog` were removed; the active budgeting surface remains `BudgetView`.
- `src/mira/ai/engine.py` refactored into a factory and runtime-helper module; engine implementations, model registry utilities, and the base interface now live in separate dedicated modules.
- `executor.py` migrated from ad-hoc monolithic `Database` method calls to the public facade API (`db.account.*`, `db.transaction.*`, `db.category.*`, `db.report.*`).
- `pipeline.py` replaces broad `except Exception` clauses with explicit exception-type tuples to avoid silently swallowing unexpected errors.
- `SettingRepository` now exposes a `get(key)` method; `get_setting(key)` remains as a delegate for backwards compatibility. Callers in `number_format.py`, views, and tests updated to use `settings.get(...)`.
- `PromptAssets` is now injected as a constructor dependency into both `LlamaCppEngine` and `TransactionParserEngine` instead of relying on module-level globals.
- `download_model_to()` accepts an `is_cancelled` callable and an `on_response_opened` callback to support cooperative cancellation by closing the active HTTP response between chunk reads.
- `mira_master_backend.py` migrated snapshot query to Peewee models and adopted the renamed active-budget API.
- Database path resolution now adheres to OS-specific conventions: `XDG Base Directory Specification` on Linux (with Flatpak sandbox awareness), `APPDATA` environment variable on Windows, and `~/Library/Application Support` on macOS.
- Database category retrieval now uses a single internal source (`get_category`) for lookups by id or by normalized name/type, and legacy helpers delegate to that same path.
- Achievement counter increments now validate `step` boundaries and use additive upsert semantics so `(previous, current)` values remain consistent.
- Monthly transaction context building now validates date format (`YYYY-MM-DD`) and amount finiteness/range before running calculations.
- `pyproject.toml` adds `tests` to `pythonpath` so shared test helpers are importable without installation.

### Fixed

- Model download cancellation now works cooperatively: the cancel flag is checked between each 1 MB chunk read and the active HTTP response is closed, preventing the download from running to completion after the user requests cancellation.
- Service-level tests now cover the new view-service seams without requiring a Qt/OpenGL runtime, reducing false negatives in headless environments.
- Broad `except Exception` blocks in `engine.py`, `pipeline.py`, and coordinator modules replaced with specific exception types so unexpected errors are no longer silently swallowed.
- Windows now automatically migrates legacy database files from `~/.mira/mira.db` to the APPDATA-compliant location on application startup.
- Linux properly resolves the database directory within Flatpak sandboxes using XDG_DATA_HOME environment variable when available.
- macOS database location now follows standard application data conventions.
- Database runtime checks now avoid `assert` in critical connection paths (`_cursor`, `_init_schema`, backup/restore) and raise explicit runtime errors when disconnected.
- Backup restore now uses in-memory staging plus explicit transaction handling to reduce partial-restore risk when failures occur.
- Monthly report context now tolerates ISO timestamp-like transaction dates (for example `YYYY-MM-DDTHH:MM:SS`) by normalizing them to `YYYY-MM-DD`.

## [0.0.1-rc3] - 2026-03-30

### Added

- The documentation site now ships the project `.ico` as a favicon so the browser tab matches the desktop application branding.

### Changed

- The custom documentation landing page now uses a manual screenshot carousel with square-edged visuals instead of a single rounded hero image, and the duplicated screenshot blocks were removed from the localized home page content.
- Local GGUF chat engines now receive the selected application language when they are initialized and whenever chat mode is used.

### Fixed

- English chat prompt controls now include their own placeholder, send button, and status strings instead of falling back to Spanish defaults.
- Chat mode availability and parser fallback messages now follow the current application language more consistently.

## [0.0.1-rc2] - 2026-03-29

Second public release candidate of MIRA.

### Added

- Bilingual MkDocs documentation in Spanish and English, including translated navigation and a custom landing page.
- Documentation theme overrides and stylesheet customizations for a branded home experience and top navigation bar.
- Shared UI notification helper to route informational messages into the main MIRA chat area.

### Changed

- The initial setup flow no longer exposes the "Skip -> Create a default account automatically" action on the final account page.
- NSIS installer setup now exposes built-in English and Spanish language selection.
- User-facing feedback such as daily messages, transaction feedback, imports, exports, backups, restores, onboarding notices, and similar informational messages are now shown through the MIRA chat interface instead of separate message dialogs.
- Validation warnings and selection prompts across dialogs, tag management, category/budget flows, recurring operations, savings goals, and analysis/report views now reuse the shared in-chat notification path.
- Project metadata now uses `MarkupSafe>=2.1.5`, and the docs extra includes `mkdocs-static-i18n` for bilingual documentation builds.

### Fixed

- Canceling the initial onboarding now aborts startup cleanly instead of continuing without creating default tags or leaving setup state partially completed.
- Initial onboarding now persists the chosen username so the Settings view and welcome status no longer fall back to `Usuario` after setup completes.
- Initial onboarding now refreshes the dashboard with the chosen default currency and reuses the pristine bootstrap account so fresh setups do not keep showing a leftover `General` account in `NIO` after choosing another currency such as `USD`.
- The transaction dialog now refreshes the category picker when switching between expense and income, so income entries no longer keep showing expense categories.
- The account dialog now restricts the currency field to the seeded system currency list, preventing new accounts from being created with arbitrary free-text currency codes.
- The Accounts view now refreshes reliably after create, edit, default-selection, and delete operations, formats account creation dates correctly, and keeps the table selection aligned with the account that was changed.
- Monthly budget reassignments now reload both the budget matrix and the tracking panel so the updated allocation is shown immediately after moving funds between categories.
- Monthly budget tracking now provides vertical scrolling so the full view remains accessible on smaller windows.
- Automated tests were updated to cover onboarding cancellation, chat-routed notifications, and the scrollable monthly budget tracking view.

## [0.0.1-rc1] - 2026-03-28

Initial public release candidate of MIRA.

### Added

- Desktop personal finance application built with PySide6.
- Offline-first transaction workflow with a deterministic natural-language parser.
- Guided first-run setup for user profile, language, theme, currency, and number formatting.
- Account, transaction, category, tag, recurring-operation, budget, report, goal, and settings management views.
- MIRA Analysis reporting flow with assistant integration and background execution support.
- Import and export helpers for spreadsheet-based workflows.
- Local SQLite persistence layer with modular database mixins.
- Optional local chat support through GGUF models and `llama-cpp-python`.
- CLI entry point for scripted and terminal-based usage.
- Packaging support for Windows distributions and Flatpak-based Linux builds.
- GPL-3.0-or-later licensing and public project documentation.

### Highlights

- Register income, expenses, transfers, and savings-related activity from structured UI forms or natural-language commands.
- Organize financial data by account, category, and tags, and review it through dashboards and reports.
- Plan annual budgets, compare budgeted values against actual execution, and inspect monthly budget tracking.
- Generate consolidated financial insights with MIRA reports while keeping user data local.
- Preserve privacy by default: the core assistant mode does not require external services.

### Quality

- Project quality gates include `black`, `ruff`, `flake8`, `pytest`, and `pytest -m full`.
- Source tree prepared for the first public release under GPLv3-compatible project metadata.
