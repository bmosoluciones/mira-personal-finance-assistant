# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tests.qt_stubs import fresh_import, install_fake_pyside


class _StatusBar:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def showMessage(self, text: str, timeout: int) -> None:
        self.calls.append((text, timeout))


def test_navigation_coordinator_syncs_row_and_refreshes(monkeypatch) -> None:
    install_fake_pyside(monkeypatch)
    module = fresh_import(monkeypatch, "mira.ui.coordinators.navigation_coordinator")

    class View:
        def __init__(self) -> None:
            self.refresh_calls = 0

        def refresh(self) -> None:
            self.refresh_calls += 1

    class Stack:
        def __init__(self) -> None:
            self.views = [View(), View()]
            self.current_index = 0

        def setCurrentIndex(self, index: int) -> None:
            self.current_index = index

        def currentWidget(self):
            return self.views[self.current_index]

    class NavList:
        def __init__(self) -> None:
            self.row = 0
            self.block_calls: list[bool] = []

        def currentRow(self) -> int:
            return self.row

        def blockSignals(self, value: bool) -> None:
            self.block_calls.append(value)

        def setCurrentRow(self, value: int) -> None:
            self.row = value

    stack = Stack()
    nav_list = NavList()
    coordinator = module.NavigationCoordinator(stack, nav_list)

    visible = coordinator.go(1)

    assert visible is stack.views[1]
    assert nav_list.row == 1
    assert nav_list.block_calls == [True, False]
    assert stack.views[1].refresh_calls == 1


def test_notification_service_updates_status_and_routes_message_boxes(monkeypatch) -> None:
    qt = install_fake_pyside(monkeypatch)
    module = fresh_import(monkeypatch, "mira.ui.notification_service")

    ui = qt.QtWidgets.QWidget()
    ui._status_bar = _StatusBar()
    ui._language = "en"
    statuses: list[str] = []
    ui._set_status = statuses.append

    service = module.NotificationService(ui)
    service.warning("Heads up", "Review latest transaction")
    service.error("Error", "Could not save")
    service.info("Ignored", "   ")

    assert ui._status_bar.calls == [
        ("Review latest transaction", 5000),
        ("Could not save", 7000),
    ]
    assert statuses == ["●  Review latest message", "●  Attention required"]
    assert module.QMessageBox.calls == [
        ("warning", ui, "Heads up", "Review latest transaction"),
        ("error", ui, "Error", "Could not save"),
    ]


def test_show_user_message_prefers_window_target_then_falls_back(monkeypatch) -> None:
    qt = install_fake_pyside(monkeypatch)
    module = fresh_import(monkeypatch, "mira.ui.notifications")

    class Target(qt.QtWidgets.QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.calls: list[tuple[str, str, str]] = []

        def notify_user_message(self, title: str, message: str, *, level: str = "info") -> None:
            self.calls.append((title, message, level))

    target = Target()
    child = qt.QtWidgets.QWidget()
    child._window = target

    module.show_user_message(child, "Done", "Saved", level="warning")
    module.show_user_message(qt.QtWidgets.QWidget(), "Info", "Plain message", level="info")
    module.show_user_message(None, "Skip", "   ", level="error")

    assert target.calls == [("Done", "Saved", "warning")]
    kind, parent, title, text = module.QMessageBox.calls[0]
    assert (kind, title, text) == ("info", "Info", "Plain message")
    assert isinstance(parent, qt.QtWidgets.QWidget)


def test_command_coordinator_runs_pipeline_and_wires_callbacks(monkeypatch) -> None:
    install_fake_pyside(monkeypatch)
    module = fresh_import(monkeypatch, "mira.ui.coordinators.command_coordinator")

    class Pipeline:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def process(self, text: str) -> str:
            self.calls.append(("assistant", text))
            return "assistant-result"

        def process_chat(self, text: str) -> str:
            self.calls.append(("chat", text))
            return "chat-result"

    pipeline = Pipeline()
    worker = module.PipelineCommandWorker(pipeline, "hola", "chat")
    results: list[str] = []
    errors: list[str] = []
    worker.finished.connect(results.append)
    worker.error.connect(errors.append)

    worker.run()

    coordinator = module.CommandCoordinator(pipeline)
    threaded_worker = coordinator.execute("adios", "assistant", results.append, errors.append)

    assert pipeline.calls == [("chat", "hola")]
    assert results == ["chat-result"]
    assert errors == []
    assert threaded_worker.started is True


def test_command_coordinator_emits_error_text(monkeypatch) -> None:
    install_fake_pyside(monkeypatch)
    module = fresh_import(monkeypatch, "mira.ui.coordinators.command_coordinator")

    class BrokenPipeline:
        def process(self, _text: str) -> str:
            raise ValueError("boom")

        def process_chat(self, _text: str) -> str:
            raise AssertionError("unexpected")

    worker = module.PipelineCommandWorker(BrokenPipeline(), "hola", "assistant")
    errors: list[str] = []
    worker.error.connect(errors.append)

    worker.run()

    assert errors == ["boom"]


class _FakeDateEdit:
    def __init__(self, iso_date: str) -> None:
        self.iso_date = iso_date

    def date(self):
        return self

    def toString(self, _fmt: str) -> str:
        return self.iso_date


class _FakeCombo:
    def __init__(self, data) -> None:
        self._data = data

    def currentData(self):
        return self._data


class _FakeCheckBox:
    def __init__(self, checked: bool) -> None:
        self._checked = checked

    def isChecked(self) -> bool:
        return self._checked


def _make_reports_view_probe(module, *, since: str, until: str, filters: dict[str, object], has_loaded_data: bool):
    status_calls: list[tuple[str, str]] = []
    loaded_states: list[object] = []
    view = SimpleNamespace(
        _from_date=_FakeDateEdit(since),
        _to_date=_FakeDateEdit(until),
        _account_filter=_FakeCombo(filters.get("account_id")),
        _tx_type_filter=_FakeCombo(filters.get("tx_type")),
        _category_filter=_FakeCombo(filters.get("category")),
        _tag_filter=_FakeCombo(filters.get("tag_id")),
        _include_children=_FakeCheckBox(bool(filters.get("include_children"))),
        _report_has_loaded_data=has_loaded_data,
        _report_dirty=True,
        _inflight_request_snapshot=None,
        _language="es",
    )

    def set_report_status(text: str, *, color: str = "#9FB3C8") -> None:
        status_calls.append((text, color))

    def set_loaded_state(state: object) -> None:
        loaded_states.append(state)

    view._set_report_status = set_report_status
    view._set_loaded_state = set_loaded_state
    view._current_filters = lambda: module.ReportsView._current_filters(view)
    view._build_request_snapshot = (
        lambda since_date, until_date, current_filters: module.ReportsView._build_request_snapshot(
            view, since_date, until_date, current_filters
        )
    )
    view._current_request_snapshot = lambda: module.ReportsView._current_request_snapshot(view)
    view._should_apply_completed_request = lambda request_snapshot: module.ReportsView._should_apply_completed_request(
        view, request_snapshot
    )
    view._mark_report_pending = lambda: module.ReportsView._mark_report_pending(view)
    view._status_calls = status_calls
    view._loaded_states = loaded_states
    return view


def test_reports_view_discards_stale_async_results(monkeypatch) -> None:
    install_fake_pyside(monkeypatch)
    module = fresh_import(
        monkeypatch,
        "mira.ui.views.reports",
        clear_prefixes=("mira.ui.views._shared", "mira.ui.delegates"),
    )
    filters = {
        "account_id": None,
        "tx_type": None,
        "category": None,
        "tag_id": None,
        "include_children": False,
    }
    view = _make_reports_view_probe(
        module,
        since="2026-03-01",
        until="2026-03-31",
        filters=filters,
        has_loaded_data=True,
    )
    request_snapshot = view._build_request_snapshot("2026-03-01", "2026-03-31", filters)
    view._inflight_request_snapshot = request_snapshot
    view._from_date.iso_date = "2026-04-01"
    view._to_date.iso_date = "2026-04-30"
    view._mark_report_pending()

    module.ReportsView._on_report_loaded(view, request_snapshot, {"old": "state"})

    assert view._loaded_states == []
    assert view._report_dirty is True
    assert view._status_calls[-1][0].startswith("Los filtros cambiaron.")


def test_reports_view_applies_matching_async_results(monkeypatch) -> None:
    install_fake_pyside(monkeypatch)
    module = fresh_import(
        monkeypatch,
        "mira.ui.views.reports",
        clear_prefixes=("mira.ui.views._shared", "mira.ui.delegates"),
    )
    filters = {
        "account_id": 7,
        "tx_type": "expense",
        "category": "Food",
        "tag_id": 3,
        "include_children": True,
    }
    view = _make_reports_view_probe(
        module,
        since="2026-03-01",
        until="2026-03-31",
        filters=filters,
        has_loaded_data=False,
    )
    request_snapshot = view._build_request_snapshot("2026-03-01", "2026-03-31", filters)
    view._inflight_request_snapshot = request_snapshot

    module.ReportsView._on_report_loaded(view, request_snapshot, {"fresh": "state"})

    assert view._loaded_states == [{"fresh": "state"}]
    assert view._report_has_loaded_data is True
    assert view._report_dirty is False
    assert view._status_calls[-1][0] == "Reporte cargado con los filtros seleccionados."


def test_reports_view_ignores_stale_async_failures(monkeypatch) -> None:
    install_fake_pyside(monkeypatch)
    module = fresh_import(
        monkeypatch,
        "mira.ui.views.reports",
        clear_prefixes=("mira.ui.views._shared", "mira.ui.delegates"),
    )
    filters = {
        "account_id": None,
        "tx_type": "income",
        "category": None,
        "tag_id": None,
        "include_children": False,
    }
    view = _make_reports_view_probe(
        module,
        since="2026-03-01",
        until="2026-03-31",
        filters=filters,
        has_loaded_data=True,
    )
    request_snapshot = view._build_request_snapshot("2026-03-01", "2026-03-31", filters)
    view._inflight_request_snapshot = request_snapshot
    view._from_date.iso_date = "2026-05-01"
    view._to_date.iso_date = "2026-05-31"
    view._mark_report_pending()
    previous_status = view._status_calls[-1]

    module.ReportsView._on_report_failed(view, request_snapshot, "boom")

    assert view._report_dirty is True
    assert view._loaded_states == []
    assert view._status_calls[-1] == previous_status


def test_model_download_coordinator_worker_handles_progress_cancel_and_errors(monkeypatch, tmp_path: Path) -> None:
    install_fake_pyside(monkeypatch)
    module = fresh_import(monkeypatch, "mira.ui.coordinators.model_download_coordinator")

    response = SimpleNamespace(close_calls=0)
    response.close = lambda: setattr(response, "close_calls", response.close_calls + 1)

    def fake_download(url: str, dest_dir: Path, progress_callback, is_cancelled, on_response_opened, **_kwargs) -> Path:
        assert url == "https://example.invalid/model.gguf"
        assert dest_dir == tmp_path
        on_response_opened(response)
        progress_callback(3, 6)
        worker.cancel()
        assert is_cancelled() is True
        raise module.DownloadCancelledError("cancelled")

    monkeypatch.setattr(module, "download_model_to", fake_download)

    worker = module.ModelDownloadWorker("https://example.invalid/model.gguf", tmp_path)
    progress: list[tuple[int, int]] = []
    finished: list[str] = []
    errors: list[str] = []
    worker.progress.connect(lambda received, total: progress.append((received, total)))
    worker.finished_path.connect(finished.append)
    worker.error.connect(errors.append)

    worker.run()

    assert progress == [(3, 6)]
    assert finished == []
    assert errors == []
    assert response.close_calls == 1

    def broken_download(_url: str, _dest_dir: Path, progress_callback, **_kwargs) -> Path:
        progress_callback(1, 2)
        raise RuntimeError("network down")

    monkeypatch.setattr(module, "download_model_to", broken_download)
    worker = module.ModelDownloadWorker("https://example.invalid/model.gguf", tmp_path)
    worker.error.connect(errors.append)
    worker.run()

    assert errors == ["network down"]


def test_model_download_coordinator_returns_handle_and_starts_worker(monkeypatch, tmp_path: Path) -> None:
    install_fake_pyside(monkeypatch)
    module = fresh_import(monkeypatch, "mira.ui.coordinators.model_download_coordinator")

    class FakeWorker:
        def __init__(self, url: str, dest_dir: Path) -> None:
            self.url = url
            self.dest_dir = dest_dir
            self.progress = SimpleNamespace(callbacks=[], connect=lambda cb: self.progress.callbacks.append(cb))
            self.finished_path = SimpleNamespace(
                callbacks=[],
                connect=lambda cb: self.finished_path.callbacks.append(cb),
            )
            self.error = SimpleNamespace(callbacks=[], connect=lambda cb: self.error.callbacks.append(cb))
            self.started = False
            self.cancel_calls = 0

        def start(self) -> None:
            self.started = True

        def cancel(self) -> None:
            self.cancel_calls += 1

    monkeypatch.setattr(module, "get_default_model_download_url", lambda: "https://example.invalid/model.gguf")
    monkeypatch.setattr(module, "model_filename_from_url", lambda _url: "model.gguf")
    monkeypatch.setattr(module, "get_writable_models_dir", lambda: tmp_path)
    monkeypatch.setattr(module, "ModelDownloadWorker", FakeWorker)

    progress: list[tuple[int, int]] = []
    finished: list[str] = []
    errors: list[str] = []
    handle = module.ModelDownloadCoordinator().start_default_download(
        lambda received, total: progress.append((received, total)),
        finished.append,
        errors.append,
    )

    assert handle.filename == "model.gguf"
    assert handle.dest_dir == tmp_path
    assert handle.worker.started is True
    assert len(handle.worker.progress.callbacks) == 1
    assert handle.worker.finished_path.callbacks == [finished.append]
    assert handle.worker.error.callbacks == [errors.append]

    handle.cancel()
    assert handle.worker.cancel_calls == 1


def test_model_download_flow_success_cancel_and_error_paths(monkeypatch) -> None:
    install_fake_pyside(monkeypatch)
    module = fresh_import(monkeypatch, "mira.ui.coordinators.model_download_flow")

    class Handle:
        def __init__(self) -> None:
            self.filename = "model.gguf"
            self.cancel_calls = 0

        def cancel(self) -> None:
            self.cancel_calls += 1

    class Coordinator:
        def __init__(self) -> None:
            self.handle = Handle()
            self.on_progress = None
            self.on_finished = None
            self.on_error = None

        def start_default_download(self, on_progress, on_finished, on_error):
            self.on_progress = on_progress
            self.on_finished = on_finished
            self.on_error = on_error
            return self.handle

    class DownloadService:
        def __init__(self, result=None, error: Exception | None = None) -> None:
            self.result = result
            self.error = error
            self.calls: list[tuple[str, str, str | None, str]] = []

        def complete_default_download(self, filename: str, downloaded_path: str, active_runtime_path, interaction_mode):
            self.calls.append((filename, downloaded_path, active_runtime_path, interaction_mode))
            if self.error is not None:
                raise self.error
            return self.result

    class Notifications:
        def __init__(self) -> None:
            self.info_calls: list[tuple[str, str, object | None]] = []
            self.error_calls: list[tuple[str, str, object | None]] = []

        def info(self, title: str, message: str, widget=None) -> None:
            self.info_calls.append((title, message, widget))

        def error(self, title: str, message: str, widget=None) -> None:
            self.error_calls.append((title, message, widget))

    lifecycle_state = object()
    coordinator = Coordinator()
    notifications = Notifications()
    statuses: list[str] = []
    refreshed: list[str] = []
    applied: list[object] = []
    service = DownloadService(
        result=SimpleNamespace(
            downloaded_path="C:/models/model.gguf",
            preferred_model_name="model.gguf",
            lifecycle_state=lifecycle_state,
            refresh_settings=True,
        )
    )

    flow = module.ModelDownloadFlow(
        parent=None,
        language="en",
        db=object(),
        download_coordinator=coordinator,
        download_service=service,
        notification_service=notifications,
        apply_model_lifecycle_state=applied.append,
        refresh_settings_view=lambda: refreshed.append("refresh"),
        get_active_runtime_path=lambda: "C:/runtime/old.gguf",
        get_interaction_mode=lambda: "chat",
        get_username=lambda: "User",
        set_status=statuses.append,
    )

    session = flow.start_default_download()
    coordinator.on_progress(1, 2)
    coordinator.on_finished("C:/models/model.gguf")

    assert session.progress_dialog.value == 50
    assert session.progress_dialog.closed is True
    assert service.calls == [("model.gguf", "C:/models/model.gguf", "C:/runtime/old.gguf", "chat")]
    assert applied == [lifecycle_state]
    assert refreshed == ["refresh"]
    assert notifications.info_calls == [("MIRA", "Model downloaded:\nC:/models/model.gguf", None)]
    assert statuses[0].startswith("Updating model for mode")
    assert statuses[-1] == "●  Ready"

    cancel_session = module.ModelDownloadSession(
        handle=coordinator.handle, progress_dialog=module.QProgressDialog("", "", 0, 100)
    )
    cancel_session.cancel()
    cancel_session.cancel()
    assert cancel_session.cancelled is True
    assert coordinator.handle.cancel_calls == 1

    error_notifications = Notifications()
    error_flow = module.ModelDownloadFlow(
        parent=None,
        language="en",
        db=object(),
        download_coordinator=Coordinator(),
        download_service=DownloadService(error=RuntimeError("reload failed")),
        notification_service=error_notifications,
        apply_model_lifecycle_state=lambda _state: None,
        refresh_settings_view=lambda: None,
        get_active_runtime_path=lambda: None,
        get_interaction_mode=lambda: "assistant",
        get_username=lambda: "User",
        set_status=lambda _text: None,
    )
    error_session = error_flow.start_default_download()
    error_flow._download_coordinator.on_finished("C:/models/model.gguf")

    assert error_session.progress_dialog.closed is True
    title, message, widget = error_notifications.error_calls[0]
    assert title.endswith("Download Error")
    assert (message, widget) == ("reload failed", None)


def test_card_widget_menu_builder_and_report_types(monkeypatch) -> None:
    install_fake_pyside(monkeypatch)
    report_types = fresh_import(monkeypatch, "mira.ui.views.report_types")
    cards_module = fresh_import(monkeypatch, "mira.ui.widgets.cards")
    menu_module = fresh_import(monkeypatch, "mira.ui.menu_builder")

    card = cards_module.CardWidget("Balance", "$0.00", "#CCC")
    card.set_value("$10.00")
    card.set_color("#123456")
    card.set_context("Primary context", secondary="Secondary context")

    assert card._value_lbl.text() == "$10.00"
    assert "#123456" in card._value_lbl.style_sheet
    assert card._primary_context_lbl.visible is True
    assert card._secondary_context_lbl.visible is True

    class Menu:
        def __init__(self, title: str) -> None:
            self.title = title
            self.actions: list[object] = []

        def addAction(self, action) -> None:
            self.actions.append(action)

        def addSeparator(self) -> None:
            self.actions.append("separator")

    class MenuBar:
        def __init__(self) -> None:
            self.menus: list[Menu] = []

        def clear(self) -> None:
            self.menus.clear()

        def addMenu(self, title: str) -> Menu:
            menu = Menu(title)
            self.menus.append(menu)
            return menu

    class Window:
        def __init__(self) -> None:
            self._language = "en"
            self._menu_bar = MenuBar()
            self.open_accounts_calls = 0
            self.open_transactions_calls = 0
            self.open_budget_calls = 0
            self.open_categories_calls = 0
            self.open_tags_calls = 0
            self.open_recurring_calls = 0
            self.open_goals_calls = 0
            self.report_calls: list[int] = []
            self.closed = False

        def menuBar(self) -> MenuBar:
            return self._menu_bar

        def close(self) -> None:
            self.closed = True

        def _on_import_csv(self) -> None:
            return None

        def _on_export_csv(self) -> None:
            return None

        def _on_backup(self) -> None:
            return None

        def _on_restore(self) -> None:
            return None

        def _menu_add_account(self) -> None:
            return None

        def _menu_open_accounts(self) -> None:
            self.open_accounts_calls += 1

        def _menu_open_transactions(self) -> None:
            self.open_transactions_calls += 1

        def _menu_add_transaction(self) -> None:
            return None

        def _menu_transfer(self) -> None:
            return None

        def _menu_credit_payment(self) -> None:
            return None

        def _menu_add_budget(self) -> None:
            return None

        def _menu_open_budget(self) -> None:
            self.open_budget_calls += 1

        def _menu_open_categories(self) -> None:
            self.open_categories_calls += 1

        def _menu_add_income_category(self) -> None:
            return None

        def _menu_add_expense_category(self) -> None:
            return None

        def _menu_open_tags(self) -> None:
            self.open_tags_calls += 1

        def _menu_add_tag(self) -> None:
            return None

        def _menu_add_recurring(self) -> None:
            return None

        def _menu_open_recurring(self) -> None:
            self.open_recurring_calls += 1

        def _menu_apply_recurring(self) -> None:
            return None

        def _menu_open_goals(self) -> None:
            self.open_goals_calls += 1

        def _open_report_type(self, report_type: int) -> None:
            self.report_calls.append(report_type)

        def _menu_open_mira_analysis(self) -> None:
            return None

        def _menu_add_goal(self) -> None:
            return None

        def _menu_contribute_goal(self) -> None:
            return None

        def _menu_open_compound_interest(self) -> None:
            return None

        def _menu_open_loan_amortization(self) -> None:
            return None

        def _menu_open_goal_simulator(self) -> None:
            return None

        def _toggle_sidebar(self) -> None:
            return None

        def _toggle_prompt_panel(self) -> None:
            return None

        def _menu_open_settings(self) -> None:
            return None

        def _on_about(self) -> None:
            return None

        def _on_open_documentation(self) -> None:
            return None

    window = Window()
    menu_module.MenuBuilder().build(window)

    titles = [menu.title for menu in window._menu_bar.menus]
    assert titles[:3] == ["File", "Accounts", "Transactions"]
    assert window._act_sidebar.isCheckable() is True
    assert window._act_prompt.isCheckable() is True

    tags_menu = next(menu for menu in window._menu_bar.menus if menu.title == "Tags")
    accounts_menu = next(menu for menu in window._menu_bar.menus if menu.title == "Accounts")
    transactions_menu = next(menu for menu in window._menu_bar.menus if menu.title == "Transactions")
    budget_menu = next(menu for menu in window._menu_bar.menus if menu.title == "Budget")
    categories_menu = next(menu for menu in window._menu_bar.menus if menu.title == "Categories")
    recurring_menu = next(menu for menu in window._menu_bar.menus if menu.title == "Recurring")
    goals_menu = next(menu for menu in window._menu_bar.menus if menu.title == "Goals")
    reports_menu = next(menu for menu in window._menu_bar.menus if menu.title == "Reports")
    file_menu = next(menu for menu in window._menu_bar.menus if menu.title == "File")

    accounts_menu.actions[0].trigger()
    transactions_menu.actions[0].trigger()
    budget_menu.actions[0].trigger()
    categories_menu.actions[0].trigger()
    tags_menu.actions[0].trigger()
    recurring_menu.actions[0].trigger()
    goals_menu.actions[0].trigger()
    reports_menu.actions[3].trigger()
    file_menu.actions[-1].trigger()

    assert window.open_accounts_calls == 1
    assert window.open_transactions_calls == 1
    assert window.open_budget_calls == 1
    assert window.open_categories_calls == 1
    assert window.open_tags_calls == 1
    assert window.open_recurring_calls == 1
    assert window.open_goals_calls == 1
    assert window.report_calls == [report_types.REPORT_CASH_FLOW]
    assert window.closed is True
    assert [
        report_types.REPORT_TOTAL,
        report_types.REPORT_CATEGORY,
        report_types.REPORT_ACCOUNT_TREND,
        report_types.REPORT_CASH_FLOW,
        report_types.REPORT_TAG,
        report_types.REPORT_BUDGET,
        report_types.REPORT_ACCOUNT_BALANCE,
    ] == list(range(7))


def test_refresh_sidebar_style_regenerates_nav_stylesheet_from_qt_material_env(monkeypatch) -> None:
    """_refresh_sidebar_style must rebuild sidebar colours from qt-material env vars."""
    install_fake_pyside(monkeypatch)
    module = fresh_import(monkeypatch, "mira.ui.main_window_shell")
    monkeypatch.setenv("QTMATERIAL_SECONDARYDARKCOLOR", "#101820")
    monkeypatch.setenv("QTMATERIAL_SECONDARYLIGHTCOLOR", "#1f3a4a")
    monkeypatch.setenv("QTMATERIAL_SECONDARYTEXTCOLOR", "#f7fafc")
    monkeypatch.setenv("QTMATERIAL_PRIMARYCOLOR", "#ffbf00")
    monkeypatch.setenv("QTMATERIAL_PRIMARYTEXTCOLOR", "#111111")

    class _FakeWidget:
        def __init__(self) -> None:
            self.history: list[str] = []

        def setStyleSheet(self, ss: str) -> None:
            self.history.append(ss)

    nav_list = _FakeWidget()

    class DummyWindow(module.MainWindowShellMixin):
        _nav_list = nav_list

    module.MainWindowShellMixin._refresh_sidebar_style(DummyWindow())
    first_stylesheet = nav_list.history[-1]

    assert "palette(" not in first_stylesheet
    assert "background-color:#101820;" in first_stylesheet
    assert "background-color:#1f3a4a;" in first_stylesheet
    assert "color:#f7fafc;" in first_stylesheet
    assert "background-color:#ffbf00;" in first_stylesheet
    assert "color:#111111;" in first_stylesheet

    monkeypatch.setenv("QTMATERIAL_PRIMARYCOLOR", "#1de9b6")
    module.MainWindowShellMixin._refresh_sidebar_style(DummyWindow())

    assert nav_list.history[-1] != first_stylesheet
    assert "background-color:#1de9b6;" in nav_list.history[-1]


def test_refresh_sidebar_style_skips_missing_widgets(monkeypatch) -> None:
    """_refresh_sidebar_style must silently skip sidebar attributes that are absent."""
    install_fake_pyside(monkeypatch)
    module = fresh_import(monkeypatch, "mira.ui.main_window_shell")

    class DummyWindow:
        pass  # no _nav_list or _sidebar_panel attributes

    # Should not raise
    module.MainWindowShellMixin._refresh_sidebar_style(DummyWindow())
