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


def test_settings_view_shows_provider_fields(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.settings")

    view = views_module.SettingsView(db)
    try:
        assert view._provider_combo.findData("none") >= 0
        assert view._provider_combo.findData("openai_compatible") >= 0
        assert view._provider_combo.findData("anthropic") >= 0
        assert view._mode_combo.findData("assistant") >= 0
        assert view._mode_combo.findData("chat") >= 0
        assert view._ack_check.isHidden() is True
        assert view._mcp_ack_check.isHidden() is True
    finally:
        view.close()


def test_settings_view_saves_loopback_provider_without_prompt(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.settings")

    prompts: list[str] = []
    view = views_module.SettingsView(db)
    monkeypatch.setattr(view, "_confirm_third_party", lambda host: prompts.append(host) or True)
    try:
        idx = view._provider_combo.findData("openai_compatible")
        view._provider_combo.setCurrentIndex(idx)
        view._base_url_input.setText("http://localhost:1234/v1")
        view._model_input.setText("local-model")
        view._api_key_input.setText("")
        view._mode_combo.setCurrentIndex(view._mode_combo.findData("chat"))

        view._save()

        assert prompts == []
        assert db.setting.get("llm_provider") == "openai_compatible"
        assert db.setting.get("llm_base_url") == "http://localhost:1234/v1"
        assert db.setting.get("llm_model") == "local-model"
        assert db.setting.get("llm_third_party_ack") == "0"
        assert db.setting.get("llm_interaction_mode") == "chat"
    finally:
        view.close()


def test_settings_view_rejects_remote_http_endpoint_before_saving(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.settings")
    warnings: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        views_module,
        "show_user_message",
        lambda _widget, title, message, level="info": warnings.append((title, message, level)),
    )
    view = views_module.SettingsView(db)
    try:
        view._provider_combo.setCurrentIndex(view._provider_combo.findData("openai_compatible"))
        view._base_url_input.setText("http://api.example.com/v1")
        view._model_input.setText("remote-model")

        view._save()

        assert warnings and "HTTPS" in warnings[0][1]
        assert warnings[0][2] == "warning"
        assert db.setting.get("llm_provider") == "none"
    finally:
        view.close()


def test_settings_view_disables_provider_when_remote_ack_declined(
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

    view = views_module.SettingsView(db)
    monkeypatch.setattr(view, "_confirm_third_party", lambda host: False)
    try:
        idx = view._provider_combo.findData("openai_compatible")
        view._provider_combo.setCurrentIndex(idx)
        view._base_url_input.setText("https://api.openai.com/v1")
        view._model_input.setText("gpt-4o-mini")

        view._save()

        assert db.setting.get("llm_provider") == "none"
        assert warnings and warnings[0][2] == "info"
    finally:
        view.close()


def test_settings_view_stores_remote_ack_for_accepted_host(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.settings")

    view = views_module.SettingsView(db)
    monkeypatch.setattr(view, "_confirm_third_party", lambda host: True)
    try:
        idx = view._provider_combo.findData("openai_compatible")
        view._provider_combo.setCurrentIndex(idx)
        view._base_url_input.setText("https://api.openai.com/v1")
        view._model_input.setText("gpt-4o-mini")
        view._api_key_input.setText("sk-test")

        view._save()

        assert db.setting.get("llm_provider") == "openai_compatible"
        assert db.setting.get("llm_third_party_ack") == "1"
        assert db.setting.get("llm_ack_host") == "api.openai.com"
        secrets = Path(db.path).parent / "llm-secrets.json"
        assert secrets.is_file()
        assert "sk-test" in secrets.read_text(encoding="utf-8")
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
