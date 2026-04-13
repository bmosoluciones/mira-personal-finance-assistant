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


def test_settings_view_hides_chat_controls_without_llama_cpp(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.settings")

    monkeypatch.setattr(views_module, "is_llama_cpp_available", lambda: False)

    view = views_module.SettingsView(db)
    try:
        assert view._models_frame.isHidden() is True
        assert view._download_default_btn.isHidden() is True
        assert view._mode_label.isHidden() is True
        assert view._mode_combo.isHidden() is True
        assert view._mode_combo.findData("chat") == -1
        assert view._chat_support_note.isHidden() is False
    finally:
        view.close()


def test_settings_view_shows_chat_controls_when_llama_cpp_is_available(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.settings")

    monkeypatch.setattr(views_module, "is_llama_cpp_available", lambda: True)
    monkeypatch.setattr(views_module, "discover_gguf_models", lambda: [])

    view = views_module.SettingsView(db)
    try:
        assert view._models_frame.isHidden() is False
        assert view._mode_label.isHidden() is False
        assert view._mode_combo.isHidden() is False
        assert view._mode_combo.findData("chat") >= 0
        assert view._chat_support_note.isHidden() is True
    finally:
        view.close()


def test_settings_view_rejects_equal_number_separators_without_saving(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.settings")

    monkeypatch.setattr(views_module, "is_llama_cpp_available", lambda: False)
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

    monkeypatch.setattr(views_module, "is_llama_cpp_available", lambda: False)
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
