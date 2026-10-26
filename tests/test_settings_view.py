# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from mira.db.database import Database


def _get_qapplication_or_xfail(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    try:
        qtwidgets = importlib.import_module("PySide6.QtWidgets")
    except (ImportError, OSError) as exc:
        pytest.xfail(f"Qt runtime unavailable for settings UI test: {exc}")

    app = qtwidgets.QApplication.instance()
    if app is None:
        app = qtwidgets.QApplication([])
    return app


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "settings-ui.db")
    database.connect()
    database.setting.set("language", "es")
    yield database
    database.close()


def test_settings_view_keeps_parser_and_mcp_without_chat_controls(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.settings")

    view = views_module.SettingsView(db)
    try:
        assert view._mcp_check is not None
        assert view._engine_label is not None
        assert not hasattr(view, "_provider_combo")
        assert not hasattr(view, "_mode_combo")
    finally:
        view.close()


def test_settings_view_requires_ack_for_mcp(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.settings")

    warnings: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        views_module,
        "show_user_message",
        lambda _widget, title, message, level="info": warnings.append((title, message, level)),
    )

    view = views_module.SettingsView(db)
    monkeypatch.setattr(view, "_confirm_mcp", lambda: True)
    try:
        view._mcp_check.setChecked(True)
        assert view._mcp_ack_check.isHidden() is False

        view._save()

        assert db.setting.get("mcp_enabled") == "1"
        assert db.setting.get("mcp_third_party_ack") == "1"

        monkeypatch.setattr(view, "_confirm_mcp", lambda: False)
        view._mcp_check.setChecked(False)
        view._save()
        assert db.setting.get("mcp_enabled") == "0"
    finally:
        view.close()


def test_settings_view_rejects_equal_number_separators_without_saving(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.settings")

    warnings: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        views_module,
        "show_user_message",
        lambda _widget, title, message, level="info": warnings.append((title, message, level)),
    )

    db.setting.set("username", "Alicia")
    db.setting.set("language", "es")
    db.setting.set("theme", "dark_teal.xml")
    db.setting.set("default_currency", "USD")
    db.setting.set("number_thousands_separator", ",")
    db.setting.set("number_decimal_separator", ".")

    view = views_module.SettingsView(db)
    saved_usernames: list[str] = []
    saved_languages: list[str] = []
    saved_themes: list[str] = []
    view.settings_saved.connect(saved_usernames.append)
    view.language_changed.connect(saved_languages.append)
    view.theme_changed.connect(saved_themes.append)

    try:
        view._username_input.setText("Chris")
        dot_idx = view._thousands_sep_combo.findData(".")
        assert dot_idx >= 0
        view._thousands_sep_combo.setCurrentIndex(dot_idx)
        view._decimal_sep_combo.setCurrentIndex(dot_idx)

        view._save()

        assert warnings == [
            (
                "Ajustes",
                "El separador de miles y el separador decimal deben ser distintos.",
                "warning",
            )
        ]
        assert saved_usernames == []
        assert saved_languages == []
        assert saved_themes == []
        assert db.setting.get("username") == "Alicia"
        assert db.setting.get("default_currency") == "USD"
        assert db.setting.get("number_thousands_separator") == ","
        assert db.setting.get("number_decimal_separator") == "."
    finally:
        view.close()


def test_settings_view_loads_and_saves_default_currency(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.settings")

    db.setting.set("default_currency", "NIO")

    view = views_module.SettingsView(db)

    try:
        assert view._default_currency_combo.currentData() == "NIO"
        assert "asistente" in view._default_currency_hint.text().casefold()

        crc_idx = view._default_currency_combo.findData("CRC")
        assert crc_idx >= 0
        view._default_currency_combo.setCurrentIndex(crc_idx)

        view._save()

        assert db.setting.get("default_currency") == "CRC"
    finally:
        view.close()
