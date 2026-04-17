# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Tests for application entrypoint behavior."""

from __future__ import annotations

import argparse
import builtins
import importlib
import logging
import sys
import types
from pathlib import Path

import pytest

from conftest import opengl_import_error
from mira import main as main_module
from mira.ai.executor import ActionResult
from mira.db.database import Database


def _import_main_window_or_xfail_headless() -> types.ModuleType:
    try:
        return importlib.import_module("mira.ui.main_window")
    except (ImportError, OSError) as exc:
        message = str(exc).casefold()
        headless_markers = (
            "libgl.so",
            "libegl.so",
            "could not load the qt platform plugin",
            "qt platform plugin",
            "xcb",
            "egl",
        )
        if any(marker in message for marker in headless_markers):
            pytest.xfail(f"GUI-dependent test skipped in headless environment: {exc}")
        raise


def _get_qapplication_or_xfail(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    try:
        qtwidgets = importlib.import_module("PySide6.QtWidgets")
    except (ImportError, OSError) as exc:
        pytest.xfail(f"Qt runtime unavailable for main window test: {exc}")

    app = qtwidgets.QApplication.instance()
    if app is None:
        app = qtwidgets.QApplication([])
    return app


class _FakeDatabase:
    def __init__(self, path: str | None = None, selected_model: str = "") -> None:
        self.path = path
        self.selected_model = selected_model
        self.connected = False
        self.closed = False
        self.saved_settings: dict[str, str] = {}
        self.cleanup_events: list[str] = []
        self.setting = self._SettingFacade(self)

    class _SettingFacade:
        def __init__(self, db: "_FakeDatabase") -> None:
            self._db = db

        def get(self, key: str) -> str:
            if key == "preferred_model":
                return self._db.selected_model
            return ""

        def set(self, key: str, value: str) -> None:
            self._db.saved_settings[key] = value

    def connect(self) -> None:
        self.connected = True

    def close(self) -> None:
        self.cleanup_events.append("db.close")
        self.closed = True


class _DummyPipeline:
    def __init__(self) -> None:
        self.llm_ready = False
        self.engine = object()
        self._model_path = None

    def reload_engine(self, model_path: str | None = None) -> None:
        self._model_path = model_path

    def shutdown(self) -> None:
        return None


def _install_fake_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    selected_model: str = "",
    found_model: Path | None = None,
    discovered: list[Path] | None = None,
    app_exit_code: int = 0,
    startup_cancelled: bool = False,
) -> dict[str, object]:
    state: dict[str, object] = {
        "window_kwargs": None,
        "pipeline_kwargs": None,
        "cleanup_events": [],
    }

    # Skip the display-availability check so unit tests can run headless.
    monkeypatch.setattr(main_module, "_check_display_available", lambda: None)

    class FakeQApplication:
        def __init__(self, _argv: list[str]) -> None:
            self.name = ""
            self.display_name = ""
            self.version = ""
            self.exec_calls = 0
            state["app"] = self

        def setApplicationName(self, value: str) -> None:
            self.name = value

        def setApplicationDisplayName(self, value: str) -> None:
            self.display_name = value

        def setApplicationVersion(self, value: str) -> None:
            self.version = value

        def exec(self) -> int:
            self.exec_calls += 1
            return app_exit_code

    pyside_module = types.ModuleType("PySide6")
    qtwidgets_module = types.ModuleType("PySide6.QtWidgets")
    qtwidgets_module.QApplication = FakeQApplication
    monkeypatch.setitem(sys.modules, "PySide6", pyside_module)
    monkeypatch.setitem(sys.modules, "PySide6.QtWidgets", qtwidgets_module)

    db_holder: dict[str, _FakeDatabase] = {}

    class FakeDatabaseFactory(_FakeDatabase):
        def __init__(self, path: str | None = None) -> None:
            super().__init__(path=path, selected_model=selected_model)
            db_holder["db"] = self

    class FakePipeline:
        def __init__(self, **kwargs: object) -> None:
            state["pipeline_kwargs"] = kwargs
            self.shutdown_called = False
            state["pipeline"] = self

        def shutdown(self) -> None:
            self.shutdown_called = True
            cleanup_events = state["cleanup_events"]
            assert isinstance(cleanup_events, list)
            cleanup_events.append("pipeline.shutdown")

    class FakeMainWindow:
        def __init__(self, **kwargs: object) -> None:
            state["window_kwargs"] = kwargs
            self._startup_cancelled = startup_cancelled

        def show(self) -> None:
            return None

    pipeline_module = types.ModuleType("mira.ai.pipeline")
    pipeline_module.Pipeline = FakePipeline

    model_registry_module = types.ModuleType("mira.ai.model_registry")
    model_registry_module.discover_gguf_models = lambda: (discovered or [])
    model_registry_module.find_model_path_by_name = lambda _name: found_model

    database_module = types.ModuleType("mira.db.database")
    database_module.Database = FakeDatabaseFactory

    main_window_module = types.ModuleType("mira.ui.main_window")
    main_window_module.MainWindow = FakeMainWindow

    monkeypatch.setitem(sys.modules, "mira.ai.pipeline", pipeline_module)
    monkeypatch.setitem(sys.modules, "mira.ai.model_registry", model_registry_module)
    monkeypatch.setitem(sys.modules, "mira.db.database", database_module)
    monkeypatch.setitem(sys.modules, "mira.ui.main_window", main_window_module)

    state["db_holder"] = db_holder
    return state


def test_parse_args_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["mira"])
    args = main_module._parse_args()

    assert args.model is None
    assert args.db is None
    assert args.debug is False


def test_main_starts_app_and_uses_persisted_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    old_level = logging.getLogger().level
    set_levels: list[int] = []
    model_path = tmp_path / "saved.gguf"
    model_path.write_text("stub", encoding="utf-8")

    state = _install_fake_runtime(
        monkeypatch,
        selected_model="saved.gguf",
        found_model=model_path,
        discovered=[model_path],
        app_exit_code=7,
    )

    monkeypatch.setattr(
        main_module,
        "_parse_args",
        lambda: argparse.Namespace(
            model=None,
            db="custom.db",
            debug=True,
        ),
    )
    monkeypatch.setattr(logging.getLogger(), "setLevel", lambda level: set_levels.append(level))

    try:
        with pytest.raises(SystemExit) as exc_info:
            main_module.main()
    finally:
        logging.getLogger().setLevel(old_level)

    assert exc_info.value.code == 7

    db = state["db_holder"]["db"]
    assert isinstance(db, _FakeDatabase)
    assert db.connected is True
    assert db.closed is True
    assert db.cleanup_events == ["db.close"]

    pipeline_kwargs = state["pipeline_kwargs"]
    assert isinstance(pipeline_kwargs, dict)
    assert pipeline_kwargs["model_path"] == str(model_path)
    pipeline = state["pipeline"]
    assert hasattr(pipeline, "shutdown_called")
    assert pipeline.shutdown_called is True
    assert state["cleanup_events"] == ["pipeline.shutdown"]

    window_kwargs = state["window_kwargs"]
    assert isinstance(window_kwargs, dict)
    assert window_kwargs["startup_alert"] is None
    assert logging.DEBUG in set_levels

    app = state["app"]
    assert app is not None
    assert app.version == main_module.APP_VERSION


def test_main_clears_missing_preferred_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    missing_model = tmp_path / "missing.gguf"

    state = _install_fake_runtime(
        monkeypatch,
        selected_model="missing.gguf",
        found_model=missing_model,
        discovered=[],
        app_exit_code=0,
    )

    monkeypatch.setattr(
        main_module,
        "_parse_args",
        lambda: argparse.Namespace(
            model=None,
            db=None,
            debug=False,
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        main_module.main()

    assert exc_info.value.code == 0

    db = state["db_holder"]["db"]
    assert isinstance(db, _FakeDatabase)
    assert db.saved_settings["preferred_model"] == ""
    pipeline = state["pipeline"]
    assert hasattr(pipeline, "shutdown_called")
    assert pipeline.shutdown_called is True
    assert state["cleanup_events"] == ["pipeline.shutdown"]

    window_kwargs = state["window_kwargs"]
    assert isinstance(window_kwargs, dict)
    assert "ya no está disponible" in str(window_kwargs["startup_alert"])


def test_main_exits_early_when_initial_setup_is_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _install_fake_runtime(
        monkeypatch,
        startup_cancelled=True,
        app_exit_code=9,
    )

    monkeypatch.setattr(
        main_module,
        "_parse_args",
        lambda: argparse.Namespace(
            model=None,
            db=None,
            debug=False,
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        main_module.main()

    assert exc_info.value.code == 0

    db = state["db_holder"]["db"]
    assert isinstance(db, _FakeDatabase)
    assert db.connected is True
    assert db.closed is True
    assert db.cleanup_events == ["db.close"]
    pipeline = state["pipeline"]
    assert hasattr(pipeline, "shutdown_called")
    assert pipeline.shutdown_called is True
    assert state["cleanup_events"] == ["pipeline.shutdown"]

    app = state["app"]
    assert app is not None
    assert app.exec_calls == 0


def test_main_exits_when_pyside_is_missing(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(main_module, "_check_display_available", lambda: None)
    monkeypatch.delitem(sys.modules, "PySide6", raising=False)
    monkeypatch.delitem(sys.modules, "PySide6.QtWidgets", raising=False)

    original_import = builtins.__import__

    def _fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "PySide6.QtWidgets":
            raise ImportError("No module named 'PySide6.QtWidgets'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    monkeypatch.setattr(
        main_module,
        "_parse_args",
        lambda: argparse.Namespace(
            model=None,
            db=None,
            debug=False,
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        main_module.main()

    assert exc_info.value.code == 1
    stderr = capsys.readouterr().err
    assert "PySide6 is required to run MIRA" in stderr


# ---------------------------------------------------------------------------
# Tests for _check_display_available()
# ---------------------------------------------------------------------------


def test_check_display_skipped_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module.sys, "platform", "win32")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    # Should not raise or exit
    main_module._check_display_available()


def test_check_display_skipped_on_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module.sys, "platform", "darwin")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    main_module._check_display_available()


def test_check_display_passes_with_display_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module.sys, "platform", "linux")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    main_module._check_display_available()


def test_check_display_passes_with_wayland_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module.sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    main_module._check_display_available()


def test_check_display_passes_with_qt_qpa_platform_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module.sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    main_module._check_display_available()


def test_check_display_exits_when_no_display_on_linux(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(main_module.sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)

    with pytest.raises(SystemExit) as exc_info:
        main_module._check_display_available()

    assert exc_info.value.code == 1
    stderr = capsys.readouterr().err
    assert "No display server detected" in stderr
    assert "DISPLAY" in stderr
    assert "QT_QPA_PLATFORM" in stderr


def test_main_exits_with_no_display_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """main() surfaces the display error before any Qt code runs."""
    monkeypatch.setattr(main_module.sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.setattr(
        main_module,
        "_parse_args",
        lambda: argparse.Namespace(model=None, db=None, debug=False),
    )

    with pytest.raises(SystemExit) as exc_info:
        main_module.main()

    assert exc_info.value.code == 1
    stderr = capsys.readouterr().err
    assert "No display server detected" in stderr


def test_set_windows_app_user_model_id_ignores_oserror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Shell32:
        @staticmethod
        def SetCurrentProcessExplicitAppUserModelID(_app_id: str) -> None:
            raise OSError("not available")

    class _Windll:
        shell32 = _Shell32()

    monkeypatch.setattr(main_module.sys, "platform", "win32")
    monkeypatch.setattr(main_module.ctypes, "windll", _Windll(), raising=False)

    main_module._set_windows_app_user_model_id("mira.test")


def test_set_windows_app_user_model_id_raises_unexpected_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Shell32:
        @staticmethod
        def SetCurrentProcessExplicitAppUserModelID(_app_id: str) -> None:
            raise AssertionError("critical failure")

    class _Windll:
        shell32 = _Shell32()

    monkeypatch.setattr(main_module.sys, "platform", "win32")
    monkeypatch.setattr(main_module.ctypes, "windll", _Windll(), raising=False)

    with pytest.raises(AssertionError, match="critical failure"):
        main_module._set_windows_app_user_model_id("mira.test")


def test_chat_keeps_focus_on_first_message_of_new_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main_window_module = _import_main_window_or_xfail_headless()
    prompt_module = importlib.import_module("mira.ui.main_window_prompt")
    scheduled_callbacks: list[object] = []

    class FakeTimer:
        @staticmethod
        def singleShot(_delay: int, callback: object) -> None:
            scheduled_callbacks.append(callback)

    class DummyWindow:
        def __init__(self) -> None:
            self._language = "es"
            self._chat_state = main_window_module.ChatState()
            self.visible_message = ""

        def _show_chat_message(self) -> None:
            self.visible_message = self._chat_state.current_message() or ""

        def _clear_pending_chat_batch(self) -> None:
            self._chat_state.reset_pending_batch()

    monkeypatch.setattr(prompt_module, "QTimer", FakeTimer)
    monkeypatch.setattr(main_window_module, "QTimer", FakeTimer)

    window = DummyWindow()
    main_window_module.MainWindow._append_chat_assistant(window, "Primer mensaje", "Análisis MIRA")
    main_window_module.MainWindow._append_chat_assistant(window, "Segundo mensaje", "Análisis MIRA")

    assert len(window._chat_state.messages) == 2
    assert window._chat_state.current_index == 0
    assert "Primer mensaje" in window.visible_message
    assert len(scheduled_callbacks) == 1

    callback = scheduled_callbacks.pop()
    assert callable(callback)
    callback()

    main_window_module.MainWindow._append_chat_assistant(window, "Tercer mensaje", "Análisis MIRA")
    assert window._chat_state.current_index == 2
    assert "Tercer mensaje" in window.visible_message


def test_main_window_support_import_does_not_import_main_window(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib
    import sys

    module_name = "mira.ui.main_window"
    sys.modules.pop(module_name, None)
    sys.modules.pop("mira.ui.main_window_support", None)

    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == module_name or name.startswith(f"{module_name}."):
            raise AssertionError("Unexpected import of mira.ui.main_window")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    support_module = importlib.import_module("mira.ui.main_window_support")

    assert support_module is not None


def test_main_window_prompt_append_assistant_uses_qtimer_without_importing_main_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib
    import sys

    from tests.qt_stubs import install_fake_pyside

    sys.modules.pop("mira.ui.main_window_prompt", None)
    sys.modules.pop("mira.ui.notification_service", None)

    fake_pyside = install_fake_pyside(monkeypatch)

    qtimer_calls: list[callable] = []

    class FakeTimer:
        @staticmethod
        def singleShot(delay: int, callback: object) -> None:
            assert delay == 0
            assert callable(callback)
            qtimer_calls.append(callback)

    fake_pyside.QtCore.QTimer = FakeTimer
    prompt_module = importlib.import_module("mira.ui.main_window_prompt")

    module_name = "mira.ui.main_window"
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == module_name or name.startswith(f"{module_name}."):
            raise AssertionError("Unexpected import of mira.ui.main_window")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    class DummyChatState:
        def __init__(self) -> None:
            self.messages: list[str] = []
            self.current_index = -1

        def append_block(self, block: str) -> bool:
            self.messages.append(block)
            self.current_index = len(self.messages) - 1
            return True

        def current_message(self) -> str | None:
            return self.messages[self.current_index] if self.messages else None

        def reset_pending_batch(self) -> None:
            pass

    class DummyWindow:
        def __init__(self) -> None:
            self._language = "es"
            self._chat_state = DummyChatState()
            self.visible_message = ""

        def _show_chat_message(self) -> None:
            self.visible_message = self._chat_state.current_message() or ""

        def _clear_pending_chat_batch(self) -> None:
            self._chat_state.reset_pending_batch()

    window = DummyWindow()
    prompt_module.MainWindowPromptMixin._append_chat_assistant(window, "Primer mensaje", "Análisis MIRA")

    assert len(qtimer_calls) == 1
    assert "Primer mensaje" in window.visible_message


def test_main_window_no_longer_uses_startup_model_offer() -> None:
    main_window_module = _import_main_window_or_xfail_headless()
    assert not hasattr(main_window_module.MainWindow, "_offer_model_download_if_needed")


def test_main_window_no_longer_exposes_start_model_download() -> None:
    main_window_module = _import_main_window_or_xfail_headless()
    assert not hasattr(main_window_module.MainWindow, "_start_model_download")


def test_main_window_uses_laptop_friendly_splitters(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    main_window_module = _import_main_window_or_xfail_headless()
    db = Database(path=tmp_path / "main-window-layout.db")
    db.connect()
    db.setting.set("language", "es")
    db.setting.set("onboarding_completed", "1")
    db.setting.set("theme", "dark_teal.xml")

    monkeypatch.setattr(main_window_module.MainWindow, "_qt_material_themes", staticmethod(lambda: ["dark_teal.xml"]))
    monkeypatch.setattr(main_window_module.MainWindow, "_apply_theme", staticmethod(lambda _theme: None))
    monkeypatch.setattr(main_window_module.MainWindow, "_run_initial_setup_if_needed", lambda self: None)

    window = main_window_module.MainWindow(db, _DummyPipeline())

    try:
        window.show()
        app.processEvents()

        assert window._footer.maximumHeight() == 140
        assert window._response_browser.maximumHeight() == 70
        assert window._sidebar_panel.width() == main_window_module._SIDEBAR_WIDTH
        assert window._logo_panel.width() == main_window_module._SIDEBAR_WIDTH
        assert window._chat_content.isVisible() is True

        window._toggle_chat_content()
        app.processEvents()

        assert window._chat_content.isVisible() is False
        assert window._logo_panel.isVisible() is True

        window._toggle_chat_content()
        app.processEvents()

        assert window._chat_content.isVisible() is True
        assert window._logo_panel.isVisible() is True
    finally:
        window.close()
        db.close()


def test_data_analysis_action_routes_to_mira_view() -> None:
    main_window_module = _import_main_window_or_xfail_headless()
    controller_module = importlib.import_module("mira.app.application_controller")

    class DummyFrame:
        def __init__(self) -> None:
            self.visible: bool | None = None

        def setVisible(self, visible: bool) -> None:
            self.visible = visible

    class DummyInput:
        def __init__(self) -> None:
            self.focused = False

        def setFocus(self) -> None:
            self.focused = True

    class DummyReportsView:
        def __init__(self) -> None:
            self.payloads: list[dict[str, object]] = []

        def set_report_payload(self, payload: dict[str, object]) -> None:
            self.payloads.append(payload)

    class DummyMiraView:
        def __init__(self) -> None:
            self.run_calls: list[bool] = []

        def has_loaded_report(self) -> bool:
            return True

        def run_report(self, *, emit_to_assistant: bool = False) -> None:
            self.run_calls.append(emit_to_assistant)

    class DummyWindow:
        def __init__(self) -> None:
            self._language = "es"
            self._quick_btns_frame = DummyFrame()
            self._view_reports = DummyReportsView()
            self._view_mira_analysis = DummyMiraView()
            self._input = DummyInput()
            self.messages: list[tuple[str, str | None]] = []
            self.navigation: list[int] = []
            self.interaction: list[bool] = []
            self.statuses: list[str] = []
            self.refreshed = False
            self._controller = types.SimpleNamespace(
                handle_result=lambda _result: controller_module.ApplicationDirective(
                    kind="run_analysis",
                    chat_message="Abrir MIRA",
                    analysis_period=None,
                    show_quick_actions=False,
                    refresh_all=True,
                )
            )

        def _append_chat_assistant(self, text: str, title: str | None = None) -> None:
            self.messages.append((text, title))

        def _navigate(self, index: int) -> None:
            self.navigation.append(index)

        def _refresh_all(self) -> None:
            self.refreshed = True

        def _set_interaction_enabled(self, enabled: bool) -> None:
            self.interaction.append(enabled)

        def _set_status(self, text: str, color: str | None = None) -> None:
            self.statuses.append(text)

        def _after_command_success(self, directive) -> None:
            main_window_module.MainWindow._after_command_success(self, directive)

        def _finish_command(self) -> None:
            main_window_module.MainWindow._finish_command(self)

    window = DummyWindow()
    result = ActionResult(success=True, action="data_analysis", message="Abrir MIRA", data={})

    main_window_module.MainWindow._on_result(window, result)

    assert window.messages == [("Abrir MIRA", None)]
    assert window._quick_btns_frame.visible is False
    assert window.navigation == [main_window_module.MainWindow.VIEW_MIRA_ANALYSIS]
    assert window._view_mira_analysis.run_calls == [True]
    assert window.refreshed is True
    assert window.interaction == [True]
    assert window._input.focused is True


def test_clear_chat_messages_resets_history_and_view() -> None:
    main_window_module = _import_main_window_or_xfail_headless()

    class DummyBrowser:
        def __init__(self) -> None:
            self.cleared = False

        def clear(self) -> None:
            self.cleared = True

    class DummyWindow:
        def __init__(self) -> None:
            self._chat_state = main_window_module.ChatState()
            self._chat_state.append_block("uno")
            self._chat_state.reset_pending_batch()
            self._chat_state.append_block("dos")
            self._chat_state.reset_pending_batch()
            self._response_browser = DummyBrowser()
            self.navigation_updated = False

        def _show_chat_message(self) -> None:
            main_window_module.MainWindow._show_chat_message(self)

        def _update_chat_navigation(self) -> None:
            self.navigation_updated = True

    window = DummyWindow()

    main_window_module.MainWindow._clear_chat_messages(window)

    assert window._chat_state.messages == []
    assert window._chat_state.current_index == -1
    assert window._chat_state.pending_batch_start is None
    assert window._response_browser.cleared is True
    assert window.navigation_updated is True


def test_notify_user_message_uses_notification_service_not_chat() -> None:
    main_window_module = _import_main_window_or_xfail_headless()

    class DummyService:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str, object | None]] = []

        def info(self, title: str, message: str, widget=None) -> None:
            self.calls.append(("info", title, message, widget))

        def warning(self, title: str, message: str, widget=None) -> None:
            self.calls.append(("warning", title, message, widget))

        def error(self, title: str, message: str, widget=None) -> None:
            self.calls.append(("error", title, message, widget))

    class DummyWindow:
        def __init__(self) -> None:
            self._notification_service = DummyService()
            self.chat_messages: list[str] = []

        def _notification_handler(self):
            return main_window_module.MainWindow._notification_handler(self)

        def _append_chat_assistant(self, text: str, title: str | None = None) -> None:
            self.chat_messages.append(text)

    window = DummyWindow()

    main_window_module.MainWindow.notify_user_message(window, "Aviso", "Texto", level="warning")

    assert window._notification_service.calls == [("warning", "Aviso", "Texto", None)]
    assert window.chat_messages == []


def test_on_download_default_model_delegates_to_flow() -> None:
    main_window_module = _import_main_window_or_xfail_headless()

    class DummyFlow:
        def __init__(self) -> None:
            self.calls = 0
            self.worker = object()

        def start_default_download(self):
            self.calls += 1
            return types.SimpleNamespace(handle=types.SimpleNamespace(worker=self.worker))

    class DummyWindow:
        def __init__(self) -> None:
            self._model_download_flow = DummyFlow()
            self._download_session = None
            self._download_worker = None

    window = DummyWindow()

    main_window_module.MainWindow._on_download_default_model(window)

    assert window._model_download_flow.calls == 1
    assert window._download_session.handle.worker is window._model_download_flow.worker
    assert window._download_worker is window._model_download_flow.worker


def test_on_error_notifies_user_without_writing_to_chat() -> None:
    main_window_module = _import_main_window_or_xfail_headless()

    class DummyInput:
        def __init__(self) -> None:
            self.focused = False

        def setFocus(self) -> None:
            self.focused = True

    class DummyService:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str, object | None]] = []

        def info(self, title: str, message: str, widget=None) -> None:
            self.calls.append(("info", title, message, widget))

        def warning(self, title: str, message: str, widget=None) -> None:
            self.calls.append(("warning", title, message, widget))

        def error(self, title: str, message: str, widget=None) -> None:
            self.calls.append(("error", title, message, widget))

    class DummyWindow:
        def __init__(self) -> None:
            self._language = "es"
            self._notification_service = DummyService()
            self._input = DummyInput()
            self.interaction: list[bool] = []
            self.statuses: list[str] = []
            self.chat_messages: list[str] = []

        def _set_interaction_enabled(self, enabled: bool) -> None:
            self.interaction.append(enabled)

        def _set_status(self, text: str, color: str | None = None) -> None:
            self.statuses.append(text)

        def _notification_handler(self):
            return main_window_module.MainWindow._notification_handler(self)

        def notify_user_message(self, *args: object, level: str = "info") -> None:
            main_window_module.MainWindow.notify_user_message(self, *args, level=level)

        def notify_user_error(self, *args: object) -> None:
            if len(args) == 3:
                _widget, title, message = args
                main_window_module.MainWindow.notify_user_message(self, title, message, level="error")
                return
            main_window_module.MainWindow.notify_user_message(self, *args, level="error")

        def _after_command_error(self, error: str) -> None:
            main_window_module.MainWindow._after_command_error(self, error)

        def _finish_command(self) -> None:
            main_window_module.MainWindow._finish_command(self)

        def _append_chat_assistant(self, text: str, title: str | None = None) -> None:
            self.chat_messages.append(text)

    window = DummyWindow()

    main_window_module.MainWindow._on_error(window, "fallo inesperado")

    assert window._notification_service.calls == [("error", "MIRA", "fallo inesperado", None)]
    assert window.chat_messages == []
    assert window.interaction == [True]
    assert window._input.focused is True


@pytest.mark.skipif(
    opengl_import_error(),
    reason="PySide6.QtCharts requires OpenGL (not available in headless environments)",
)
def test_goal_scenario_dialog_requests_goal_form_without_persisting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main_window_module = _import_main_window_or_xfail_headless()
    goal_dialog_module = importlib.import_module("mira.ui.dialogs.financial.goal_simulator")
    info_messages: list[str] = []

    monkeypatch.setattr(
        goal_dialog_module,
        "show_user_message",
        lambda _parent, _title, message, level="info": info_messages.append(message),
    )

    class DummyDialog:
        def __init__(self) -> None:
            self._language = "es"
            self._latest = types.SimpleNamespace(is_reachable=True, target_amount=7500.5, years=2.0)
            self._request_open_goal_form = False
            self._goal_prefill = None
            self.accepted = False

        @staticmethod
        def _target_date_from_years(_years: float) -> str:
            return "2028-03-25"

        def accept(self) -> None:
            self.accepted = True

    dialog = DummyDialog()

    main_window_module._GoalScenarioDialog._create_goal_from_scenario(dialog)

    assert dialog._request_open_goal_form is True
    assert dialog._goal_prefill == {
        "target_amount": 7500.5,
        "target_date": "2028-03-25",
    }
    assert dialog.accepted is True
    assert len(info_messages) == 1


def test_menu_open_goal_simulator_opens_goal_add_flow_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main_window_module = _import_main_window_or_xfail_headless()

    class FakeGoalDialog:
        def __init__(self, _language: str, _currency: str, _parent: object) -> None:
            self.should_open_goal_form = True
            self.goal_prefill = {"target_amount": 9000.0, "target_date": "2029-01-01"}

        def exec(self) -> object:
            return main_window_module.QDialog.DialogCode.Accepted

    class DummyGoalsView:
        def __init__(self) -> None:
            self.open_add_calls = 0
            self.last_prefill = None

        def open_add_dialog(self, prefill: dict | None = None) -> None:
            self.open_add_calls += 1
            self.last_prefill = prefill

    class DummyWindow:
        def __init__(self) -> None:
            self._language = "es"
            self._db = types.SimpleNamespace(setting=types.SimpleNamespace(get=lambda _key: "USD"))
            self._view_goals = DummyGoalsView()
            self.navigation: list[int] = []

        def _navigate(self, view: int) -> None:
            self.navigation.append(view)

    monkeypatch.setattr(main_window_module, "_GoalScenarioDialog", FakeGoalDialog)

    window = DummyWindow()
    main_window_module.MainWindow._menu_open_goal_simulator(window)

    assert window.navigation == [main_window_module.MainWindow.VIEW_GOALS]
    assert window._view_goals.open_add_calls == 1
    assert window._view_goals.last_prefill == {
        "target_amount": 9000.0,
        "target_date": "2029-01-01",
    }


def test_help_assets_resolve_and_documentation_opens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    main_window_module = _import_main_window_or_xfail_headless()

    class DummyWindow:
        pass

    dummy = DummyWindow()
    opened_urls: list[str] = []
    monkeypatch.setattr(
        main_window_module.webbrowser,
        "open",
        lambda url: opened_urls.append(url) or True,
    )

    mira_logo = main_window_module.MainWindow._resolve_ui_icon_path(dummy, "256x256.png", "mira.ico")
    bmo_logo = main_window_module.MainWindow._resolve_ui_icon_path(dummy, "BMOLogoSmall.png")

    assert mira_logo is not None and mira_logo.is_file()
    assert bmo_logo is not None and bmo_logo.is_file()

    mira_label = main_window_module.MainWindow._build_about_logo_label(dummy, mira_logo, max_height=64)
    bmo_label = main_window_module.MainWindow._build_about_logo_label(dummy, bmo_logo, max_height=32)

    assert mira_label.pixmap() is not None
    assert bmo_label.pixmap() is not None

    main_window_module.MainWindow._on_open_documentation(dummy)

    assert opened_urls == [main_window_module._DOCS_URL]


def test_on_theme_changed_refreshes_sidebar(monkeypatch: pytest.MonkeyPatch) -> None:
    """_on_theme_changed must call _refresh_sidebar_style so palette() refs in the
    sidebar nav-list stylesheet are re-evaluated after the new theme is applied."""
    main_window_module = _import_main_window_or_xfail_headless()

    applied_themes: list[str] = []
    refreshed: list[bool] = []

    class DummyWindow:
        _theme = "dark_teal.xml"

        def _refresh_sidebar_style(self) -> None:
            refreshed.append(True)

    monkeypatch.setattr(
        main_window_module.MainWindow,
        "_apply_theme",
        staticmethod(lambda theme: applied_themes.append(theme)),
    )
    monkeypatch.setattr(
        main_window_module.MainWindow,
        "_normalize_theme",
        staticmethod(lambda theme: theme),
    )

    window = DummyWindow()
    main_window_module.MainWindow._on_theme_changed(window, "light_blue.xml")

    assert applied_themes == ["light_blue.xml"]
    assert refreshed == [True], "_refresh_sidebar_style was not called by _on_theme_changed"


def test_on_language_changed_warns_about_restart_only_when_language_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    main_window_module = _import_main_window_or_xfail_headless()

    class DummyWindow:
        def __init__(self, language: str) -> None:
            self._language = language
            self.menu_rebuilds = 0
            self.messages: list[tuple[str, str]] = []

        def _build_menu(self) -> None:
            self.menu_rebuilds += 1

        def notify_user_info(self, _widget, title: str, message: str) -> None:
            self.messages.append((title, message))

    changed = DummyWindow("es")
    unchanged = DummyWindow("en")

    main_window_module.MainWindow._on_language_changed(changed, "en")
    main_window_module.MainWindow._on_language_changed(unchanged, "en")

    assert changed.menu_rebuilds == 1
    assert changed.messages == [("MIRA", "Language change was saved. Close and reopen MIRA to apply it completely.")]
    assert unchanged.menu_rebuilds == 1
    assert unchanged.messages == [("MIRA", "Configuration was saved successfully.")]
