# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Regression tests for the first-run setup wizard."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from mira.db.database import Database


def _get_qapplication_or_xfail(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    try:
        qtwidgets = importlib.import_module("PySide6.QtWidgets")
    except (ImportError, OSError) as exc:
        pytest.xfail(f"Qt runtime unavailable for setup wizard test: {exc}")

    app = qtwidgets.QApplication.instance()
    if app is None:
        app = qtwidgets.QApplication([])
    return app


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "setup.db")
    database.connect()
    yield database
    database.close()


def test_initial_setup_dialog_constructs_before_accounts_page_is_shown(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    dialog = dialogs_module.InitialSetupDialog(db)

    try:
        assert dialog.page(dialog._PAGE_ACCOUNTS) is not None
        assert not hasattr(dialog, "_page_model")
        assert dialog.page(dialog._PAGE_ACCOUNTS + 1) is None
        assert dialog.styleSheet() == ""
    finally:
        dialog.close()


def test_initial_setup_dialog_skips_default_categories_page(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    dialog = dialogs_module.InitialSetupDialog(db)

    try:
        data = dialog.get_data()
        assert "seed_categories" not in data
        assert dialog.page(dialog._PAGE_CURRENCY + 1) is dialog.page(dialog._PAGE_ACCOUNTS)
        assert dialog.page(dialog._PAGE_ACCOUNTS + 1) is None
    finally:
        dialog.close()


def test_initial_setup_dialog_defaults_to_light_blue_theme(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    dialog = dialogs_module.InitialSetupDialog(db)

    try:
        assert dialog.get_data()["theme"] == "light_blue.xml"
        assert dialog.get_data()["default_currency"] == "USD"
    finally:
        dialog.close()


def test_initial_setup_dialog_rejects_equal_number_separators(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")
    setup_module = importlib.import_module("mira.ui.dialogs.setup")
    warnings: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        setup_module,
        "show_user_message",
        lambda _widget, title, message, level="info": warnings.append((title, message, level)),
    )

    dialog = dialogs_module.InitialSetupDialog(db)

    try:
        dot_idx = dialog._page_currency._thousands_combo.findData(".")
        assert dot_idx >= 0
        dialog._page_currency._thousands_combo.setCurrentIndex(dot_idx)
        dialog._page_currency._decimal_combo.setCurrentIndex(dot_idx)

        assert dialog._page_currency.validatePage() is False
        assert warnings == [
            (
                "Settings",
                "Thousands and decimal separators must be different.",
                "warning",
            )
        ]
    finally:
        dialog.close()


def test_initial_setup_dialog_requires_profile_name_before_continuing(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")
    shared_module = importlib.import_module("mira.ui.views._shared")

    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        shared_module,
        "_notify_warning",
        lambda _widget, title, message: warnings.append((str(title), str(message))),
    )

    dialog = dialogs_module.InitialSetupDialog(db)

    try:
        dialog._wizard_language = "en"
        dialog._page_profile._name_edit.setText("   ")

        assert dialog._page_profile.validatePage() is False
        assert warnings == [
            (
                "Validation",
                "A username is required. Please enter a name.",
            )
        ]
    finally:
        dialog.close()


def test_initial_setup_dialog_localizes_profile_validation_warning(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")
    shared_module = importlib.import_module("mira.ui.views._shared")

    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        shared_module,
        "_notify_warning",
        lambda _widget, title, message: warnings.append((str(title), str(message))),
    )

    dialog = dialogs_module.InitialSetupDialog(db)

    try:
        dialog._wizard_language = "es"
        dialog._page_profile._name_edit.setText("   ")

        assert dialog._page_profile.validatePage() is False
        assert warnings == [
            (
                "Validación",
                "El nombre de usuario es requerido. Por favor ingresa un nombre.",
            )
        ]
    finally:
        dialog.close()


def test_initial_setup_dialog_loads_brand_logos(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    dialog = dialogs_module.InitialSetupDialog(db)

    try:
        assert dialog._page_welcome._logo_lbl.pixmap() is not None
        assert not dialog._page_welcome._logo_lbl.pixmap().isNull()
        assert dialog._page_welcome._bmo_logo_lbl.pixmap() is not None
        assert not dialog._page_welcome._bmo_logo_lbl.pixmap().isNull()
    finally:
        dialog.close()


def test_accounts_page_tracks_selected_currency_without_overwriting_manual_choice(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    dialog = dialogs_module.InitialSetupDialog(db)

    try:
        dialog._page_accounts.initializePage()
        row = dialog._page_accounts._account_rows[0]
        currency_combo = row["currency"]

        assert currency_combo.currentText().strip().upper() == "USD"

        crc_index = dialog._page_currency._currency_combo.findData("CRC")
        assert crc_index >= 0
        dialog._page_currency._currency_combo.setCurrentIndex(crc_index)
        dialog._page_accounts.initializePage()
        assert currency_combo.currentText().strip().upper() == "CRC"

        currency_combo.setCurrentText("EUR")
        cop_index = dialog._page_currency._currency_combo.findData("COP")
        assert cop_index >= 0
        dialog._page_currency._currency_combo.setCurrentIndex(cop_index)
        dialog._page_accounts.initializePage()
        assert currency_combo.currentText().strip().upper() == "EUR"
    finally:
        dialog.close()


def test_run_initial_setup_localizes_default_account_and_respects_selected_currency(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    main_window_module = importlib.import_module("mira.ui.main_window")

    class FakeDialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, _db: Database, _parent=None) -> None:
            pass

        def exec(self) -> int:
            return self.DialogCode.Accepted

        def get_data(self) -> dict[str, object]:
            return {
                "username": "Alicia",
                "language": "es",
                "theme": "light_blue.xml",
                "default_currency": "crc",
                "decimal_sep": ",",
                "thousands_sep": ".",
                "account_names": [],
                "account_specs": [],
            }

    monkeypatch.setattr(main_window_module, "InitialSetupDialog", FakeDialog)

    calls: dict[str, object] = {"applied_themes": []}
    window = SimpleNamespace(
        _db=db,
        _language="en",
        _theme="light",
        _normalize_theme=lambda theme: theme,
        _apply_theme=lambda theme: calls["applied_themes"].append(theme),
        _refresh_all=lambda: calls.setdefault("refreshed", True),
        notify_user_message=lambda *_args, **_kwargs: calls.setdefault("message_shown", True),
    )

    main_window_module.MainWindow._run_initial_setup_if_needed(window)

    accounts = {account["name"]: account for account in db.account.list()}

    assert db.setting.get("language") == "es"
    assert db.setting.get("default_currency") == "CRC"
    assert "Cuenta principal" in accounts
    assert accounts["Cuenta principal"]["currency"] == "CRC"
    assert "General" not in accounts


def test_run_initial_setup_always_seeds_default_categories(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    main_window_module = importlib.import_module("mira.ui.main_window")

    calls: dict[str, object] = {"applied_themes": []}

    class FakeDialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, _db: Database, _parent=None) -> None:
            pass

        def exec(self) -> int:
            return self.DialogCode.Accepted

        def get_data(self) -> dict[str, object]:
            return {
                "username": "Alicia",
                "language": "es",
                "theme": "dark",
                "default_currency": "usd",
                "decimal_sep": ",",
                "thousands_sep": ".",
                "account_names": ["Caja"],
                "account_specs": [],
            }

    monkeypatch.setattr(main_window_module, "InitialSetupDialog", FakeDialog)

    def fake_seed_initial_data(**kwargs) -> None:
        calls["seed_kwargs"] = kwargs

    window = SimpleNamespace(
        _db=db,
        _language="en",
        _theme="light",
        _normalize_theme=lambda theme: theme,
        _apply_theme=lambda theme: calls["applied_themes"].append(theme),
        _refresh_all=lambda: calls.setdefault("refreshed", True),
        notify_user_message=lambda *_args, **_kwargs: calls.setdefault("message_shown", True),
    )
    monkeypatch.setattr(db.setting, "seed_initial_data", fake_seed_initial_data)

    main_window_module.MainWindow._run_initial_setup_if_needed(window)

    assert calls["seed_kwargs"] == {
        "include_default_categories": True,
        "account_names": ["Caja"],
        "account_specs": [],
        "language": "es",
    }
    assert db.setting.get("language") == "es"
    assert db.setting.get("theme") == "dark"
    assert db.setting.get("username") == "Alicia"
    assert db.setting.get("default_currency") == "USD"
    assert db.setting.get("number_decimal_separator") == ","
    assert db.setting.get("number_thousands_separator") == "."
    assert db.setting.get("onboarding_completed") == "1"
    assert window._language == "es"
    assert window._theme == "dark"
    assert calls["applied_themes"] == ["light_blue.xml", "dark"]
    assert calls["refreshed"] is True
    assert calls["message_shown"] is True


def test_run_initial_setup_cancel_does_not_mark_onboarding_completed(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    main_window_module = importlib.import_module("mira.ui.main_window")

    class FakeDialog:
        class DialogCode:
            Accepted = 1
            Rejected = 0

        def __init__(self, _db: Database, _parent=None) -> None:
            pass

        def exec(self) -> int:
            return self.DialogCode.Rejected

    monkeypatch.setattr(main_window_module, "InitialSetupDialog", FakeDialog)

    calls: dict[str, object] = {"applied_themes": []}

    def fake_seed_initial_data(**kwargs) -> None:
        calls["seed_kwargs"] = kwargs

    window = SimpleNamespace(
        _db=db,
        _language="en",
        _theme="light",
        _startup_cancelled=False,
        _normalize_theme=lambda theme: theme,
        _apply_theme=lambda theme: calls["applied_themes"].append(theme),
    )
    monkeypatch.setattr(db.setting, "seed_initial_data", fake_seed_initial_data)

    main_window_module.MainWindow._run_initial_setup_if_needed(window)

    assert "seed_kwargs" not in calls
    assert calls["applied_themes"] == ["light_blue.xml"]
    assert db.setting.get("onboarding_completed") != "1"
    assert window._startup_cancelled is True


def test_run_initial_setup_rejects_invalid_number_separator_pair(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    main_window_module = importlib.import_module("mira.ui.main_window")

    class FakeDialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, _db: Database, _parent=None) -> None:
            pass

        def exec(self) -> int:
            return self.DialogCode.Accepted

        def get_data(self) -> dict[str, object]:
            return {
                "username": "Alicia",
                "language": "en",
                "theme": "dark",
                "default_currency": "usd",
                "decimal_sep": ".",
                "thousands_sep": ".",
                "account_names": ["Cash"],
                "account_specs": [],
            }

    monkeypatch.setattr(main_window_module, "InitialSetupDialog", FakeDialog)

    warnings: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        main_window_module,
        "show_user_message",
        lambda _widget, title, message, level="info": warnings.append((title, message, level)),
    )

    calls: dict[str, object] = {}

    def fake_seed_initial_data(**kwargs) -> None:
        calls["seed_kwargs"] = kwargs

    db.setting.set("number_decimal_separator", ",")
    db.setting.set("number_thousands_separator", ".")

    window = SimpleNamespace(
        _db=db,
        _language="en",
        _theme="light",
        _startup_cancelled=False,
        _normalize_theme=lambda theme: theme,
        _apply_theme=lambda theme: calls.setdefault("applied_theme", theme),
        _refresh_all=lambda: calls.setdefault("refreshed", True),
    )
    monkeypatch.setattr(db.setting, "seed_initial_data", fake_seed_initial_data)

    main_window_module.MainWindow._run_initial_setup_if_needed(window)

    assert "seed_kwargs" not in calls
    assert db.setting.get("onboarding_completed") != "1"
    assert db.setting.get("number_decimal_separator") == ","
    assert db.setting.get("number_thousands_separator") == "."
    assert window._startup_cancelled is True
    assert warnings == [
        (
            "Settings",
            "Thousands and decimal separators must be different.",
            "warning",
        )
    ]
