# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Settings feature view."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mira.ai.llm_config import url_host
from mira.app.view_services import SettingsViewService, SettingsViewState
from mira.db.database import CURRENCY_CODES, Database
from mira.ui.i18n import SUPPORTED_LANGUAGES, normalize_language, tr
from mira.ui.notifications import show_user_message
from mira.ui.number_format import (
    separator_options,
)
from mira.ui.views._shared import (
    _BTN_STYLE,
    _COMBO_STYLE,
    _section_title,
)

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class SettingsView(QWidget):
    """Application settings view."""

    settings_saved = Signal(str)  # emits new username
    language_changed = Signal(str)  # emits selected language code
    theme_changed = Signal(str)  # emits selected theme

    def __init__(
        self,
        db: Database,
        parent: QWidget | None = None,
        service: SettingsViewService | None = None,
    ) -> None:
        """Initialize the SettingsView instance."""
        super().__init__(parent)
        self._db = db
        self._service = service or SettingsViewService(db)
        self._language = normalize_language(self._db.setting.get("language"))
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        """Return build ui."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        layout.addWidget(_section_title(tr("settings.title", self._language, default="Settings")))

        _grp_style = (
            "QGroupBox{border:1px solid palette(mid);border-radius:4px;"
            "margin-top:10px;padding:12px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:10px;}"
        )
        _input_style = (
            "QLineEdit{background:palette(base);color:palette(text);border:1px solid palette(mid);"
            "border-radius:3px;padding:5px;}"
        )

        # General group
        general = QGroupBox(tr("settings.general", self._language, default="General"))
        general.setStyleSheet(_grp_style)
        form = QFormLayout(general)
        form.setSpacing(10)

        self._username_input = QLineEdit()
        self._username_input.setStyleSheet(_input_style)
        form.addRow(
            tr("settings.username", self._language, default="Username:"),
            self._username_input,
        )

        self._language_combo = QComboBox()
        self._language_combo.setStyleSheet(_COMBO_STYLE)
        for code, label in SUPPORTED_LANGUAGES.items():
            self._language_combo.addItem(label, code)
        form.addRow(
            tr("settings.language", self._language, default="Language:"),
            self._language_combo,
        )

        self._theme_combo = QComboBox()
        self._theme_combo.setStyleSheet(_COMBO_STYLE)
        try:
            import qt_material  # type: ignore[import-untyped]

            for theme_file in qt_material.list_themes():
                label = theme_file.replace(".xml", "").replace("_", " ").title()
                self._theme_combo.addItem(label, theme_file)
        except ImportError:  # pragma: no cover – qt-material not installed
            self._theme_combo.addItem(tr("settings.theme.dark", self._language, default="Dark"), "dark")
            self._theme_combo.addItem(tr("settings.theme.light", self._language, default="Light"), "light")
        form.addRow(tr("settings.theme", self._language, default="Theme:"), self._theme_combo)

        self._default_currency_combo = QComboBox()
        self._default_currency_combo.setStyleSheet(_COMBO_STYLE)
        self._default_currency_combo.setEditable(False)
        self._default_currency_combo.setMaxVisibleItems(15)
        self._populate_currency_options()
        form.addRow(
            tr("settings.default_currency", self._language, default="Default currency:"),
            self._default_currency_combo,
        )

        self._default_currency_hint = QLabel(
            tr(
                "settings.default_currency.help",
                self._language,
                default=(
                    "Updates the default currency for new flows and the assistant. "
                    "Existing accounts and records keep their current currency."
                ),
            )
        )
        self._default_currency_hint.setWordWrap(True)
        self._default_currency_hint.setStyleSheet("font-size:10px;")
        form.addRow("", self._default_currency_hint)

        self._thousands_sep_combo = QComboBox()
        self._thousands_sep_combo.setStyleSheet(_COMBO_STYLE)
        self._decimal_sep_combo = QComboBox()
        self._decimal_sep_combo.setStyleSheet(_COMBO_STYLE)

        label_by_sep = {
            ",": tr("settings.number.sep.comma", self._language, default="Comma (,)"),
            ".": tr("settings.number.sep.dot", self._language, default="Dot (.)"),
            "_": tr(
                "settings.number.sep.underscore",
                self._language,
                default="Underscore (_)",
            ),
            " ": tr("settings.number.sep.space", self._language, default="Space"),
            "'": tr(
                "settings.number.sep.apostrophe",
                self._language,
                default="Apostrophe (')",
            ),
        }
        for sep, fallback in separator_options():
            self._thousands_sep_combo.addItem(label_by_sep.get(sep, fallback), sep)
            self._decimal_sep_combo.addItem(label_by_sep.get(sep, fallback), sep)

        form.addRow(
            tr(
                "settings.number.thousands",
                self._language,
                default="Thousands separator:",
            ),
            self._thousands_sep_combo,
        )
        form.addRow(
            tr("settings.number.decimal", self._language, default="Decimal separator:"),
            self._decimal_sep_combo,
        )

        save_btn = QPushButton(tr("settings.save", self._language, default="Save Settings"))
        save_btn.setStyleSheet(_BTN_STYLE)
        save_btn.clicked.connect(self._save)
        form.addRow("", save_btn)
        layout.addWidget(general)

        # AI Engine group
        ai_grp = QGroupBox(tr("settings.ai_engine", self._language, default="AI Engine"))
        ai_grp.setStyleSheet(_grp_style)
        ai_layout = QVBoxLayout(ai_grp)
        ai_layout.setSpacing(8)

        self._engine_label = QLabel(
            tr(
                "settings.ai_rule_based",
                self._language,
                default="Engine: Deterministic assistant parser (local, offline)",
            )
        )
        self._engine_label.setStyleSheet("font-size:11px;")
        ai_layout.addWidget(self._engine_label)

        ai_note = QLabel(
            tr(
                "settings.ai_note",
                self._language,
                default=(
                    "The assistant always uses the deterministic local parser. "
                    "Configure a provider only if you want free-form chat."
                ),
            )
        )
        ai_note.setWordWrap(True)
        ai_note.setStyleSheet("font-size:10px;")
        ai_layout.addWidget(ai_note)

        ai_form = QFormLayout()
        ai_form.setSpacing(8)
        ai_form.setContentsMargins(0, 4, 0, 0)

        self._provider_combo = QComboBox()
        self._provider_combo.setStyleSheet(_COMBO_STYLE)
        self._provider_combo.addItem(
            tr("settings.ai.provider.none", self._language, default="None (local only)"), "none"
        )
        self._provider_combo.addItem(
            tr(
                "settings.ai.provider.openai",
                self._language,
                default="OpenAI-compatible endpoint (LM Studio, Ollama, OpenAI...)",
            ),
            "openai_compatible",
        )
        self._provider_combo.addItem(
            tr("settings.ai.provider.anthropic", self._language, default="Anthropic (Claude)"),
            "anthropic",
        )
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        ai_form.addRow(
            tr("settings.ai.provider", self._language, default="Chat provider:"),
            self._provider_combo,
        )

        self._base_url_input = QLineEdit()
        self._base_url_input.setStyleSheet(_input_style)
        self._base_url_input.setPlaceholderText(
            tr("settings.ai.base_url.placeholder", self._language, default="http://localhost:1234/v1")
        )
        self._base_url_label = QLabel(tr("settings.ai.base_url", self._language, default="Endpoint URL:"))
        ai_form.addRow(self._base_url_label, self._base_url_input)

        self._model_input = QLineEdit()
        self._model_input.setStyleSheet(_input_style)
        ai_form.addRow(tr("settings.ai.model", self._language, default="Model:"), self._model_input)

        self._api_key_input = QLineEdit()
        self._api_key_input.setStyleSheet(_input_style)
        self._api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_input.setPlaceholderText(
            tr("settings.ai.api_key.placeholder", self._language, default="Not needed for local endpoints")
        )
        self._api_key_clear_btn = QPushButton(
            tr("settings.ai.api_key_clear", self._language, default="Forget key")
        )
        self._api_key_clear_btn.setToolTip(
            tr(
                "settings.ai.api_key_clear.tooltip",
                self._language,
                default="Delete the stored API key from this device",
            )
        )
        self._api_key_clear_btn.clicked.connect(self._forget_api_key)
        api_key_row = QHBoxLayout()
        api_key_row.setSpacing(8)
        api_key_row.addWidget(self._api_key_input, 1)
        api_key_row.addWidget(self._api_key_clear_btn)
        ai_form.addRow(tr("settings.ai.api_key", self._language, default="API key:"), api_key_row)

        ai_layout.addLayout(ai_form)

        self._ack_check = QCheckBox(
            tr(
                "settings.ai.ack",
                self._language,
                default="I understand that chat text leaves this device towards {host}.",
                params={"host": ""},
            )
        )
        self._ack_check.setStyleSheet("font-size:11px;")
        self._ack_check.setVisible(False)
        ai_layout.addWidget(self._ack_check)

        self._mode_label = QLabel(tr("settings.mode", self._language, default="LLM interaction mode"))
        ai_layout.addWidget(self._mode_label)
        self._mode_combo = QComboBox()
        self._mode_combo.setStyleSheet(_COMBO_STYLE)
        self._mode_combo.addItem(
            tr("settings.mode.assistant", self._language, default="Assistant mode"),
            "assistant",
        )
        self._mode_combo.addItem(tr("settings.mode.chat", self._language, default="Chat mode"), "chat")
        ai_layout.addWidget(self._mode_combo)

        mcp_note = QLabel(
            tr(
                "settings.mcp.note",
                self._language,
                default=(
                    "The MCP server lets external applications read and record data "
                    "through mira-cli. It runs only on this machine (stdio)."
                ),
            )
        )
        mcp_note.setWordWrap(True)
        mcp_note.setStyleSheet("font-size:10px;")
        ai_layout.addWidget(mcp_note)

        self._mcp_check = QCheckBox(
            tr("settings.mcp.enable", self._language, default="Enable MCP server (mira-cli mcp)")
        )
        self._mcp_check.setStyleSheet("font-size:11px;")
        self._mcp_check.toggled.connect(self._on_mcp_toggled)
        ai_layout.addWidget(self._mcp_check)

        self._mcp_ack_check = QCheckBox(
            tr(
                "settings.mcp.ack",
                self._language,
                default="I understand that external applications will access my local data through MCP.",
            )
        )
        self._mcp_ack_check.setStyleSheet("font-size:11px;")
        self._mcp_ack_check.setVisible(False)
        ai_layout.addWidget(self._mcp_ack_check)

        layout.addWidget(ai_grp)

        layout.addStretch()

    def _on_provider_changed(self) -> None:
        """Return on provider changed."""
        host = self._current_host()
        is_openai = self._provider_combo.currentData() == "openai_compatible"
        is_configured = host != ""
        self._base_url_input.setVisible(is_openai)
        self._base_url_label.setVisible(is_openai)
        needs_ack = bool(host) and host not in _LOOPBACK_HOSTS
        self._ack_check.setVisible(needs_ack)
        if needs_ack:
            self._ack_check.setText(
                tr(
                    "settings.ai.ack",
                    self._language,
                    default="I understand that chat text leaves this device towards {host}.",
                    params={"host": host},
                )
            )
        self._model_input.setEnabled(is_configured or self._provider_combo.currentData() != "none")
        self._api_key_input.setEnabled(self._provider_combo.currentData() != "none")
        self._api_key_clear_btn.setEnabled(bool(self._api_key_input.text().strip()))

    def _on_mcp_toggled(self, checked: bool) -> None:
        """Return on mcp toggled."""
        self._mcp_ack_check.setVisible(checked)

    def _current_host(self) -> str:
        """Return the host chat requests would reach with the current form values."""
        provider = self._provider_combo.currentData()
        if provider == "anthropic":
            return "api.anthropic.com"
        if provider == "openai_compatible":
            return url_host(self._base_url_input.text().strip())
        return ""

    def _forget_api_key(self) -> None:
        """Delete the stored API key and clear the field."""
        state = self._service.forget_api_key()
        self._api_key_input.setText(state.llm_api_key)
        self._api_key_clear_btn.setEnabled(False)

    def _confirm_third_party(self, host: str) -> bool:
        """Return whether the user accepted sending chat text to host."""
        answer = QMessageBox.question(
            self,
            tr("settings.title", self._language, default="Settings"),
            tr(
                "settings.ai.ack.question",
                self._language,
                default=(
                    "Chat text will leave this device and be sent to {host}. "
                    "The ledger itself is never sent. Do you accept?"
                ),
                params={"host": host},
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _confirm_mcp(self) -> bool:
        """Return whether the user accepted the MCP third-party warning."""
        answer = QMessageBox.question(
            self,
            tr("settings.title", self._language, default="Settings"),
            tr(
                "settings.mcp.ack.question",
                self._language,
                default=(
                    "Enabling MCP allows other applications on this computer to read and "
                    "record your data through mira-cli. Do you accept?"
                ),
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _save(self) -> None:
        """Return save."""
        username = self._username_input.text().strip() or tr(
            "settings.saved_default_user", self._language, default="Usuario"
        )
        language = normalize_language(self._language_combo.currentData())
        theme = self._theme_combo.currentData() or "dark_teal.xml"
        interaction_mode = self._mode_combo.currentData() or "assistant"
        provider = str(self._provider_combo.currentData() or "none")
        base_url = self._base_url_input.text().strip()
        model = self._model_input.text().strip()
        api_key = self._api_key_input.text().strip()
        ack = self._ack_check.isChecked()
        mcp_on = self._mcp_check.isChecked()
        mcp_ack = self._mcp_ack_check.isChecked()

        current = self._service.load_state()
        host = self._current_host()
        needs_ack = bool(host) and host not in _LOOPBACK_HOSTS
        if needs_ack and not (current.llm_third_party_ack and current.llm_ack_host == host) and not ack:
            if self._confirm_third_party(host):
                ack = True
                self._ack_check.setChecked(True)
            else:
                provider = "none"
                ack = False
                show_user_message(
                    self,
                    tr("settings.title", language, default="Settings"),
                    tr(
                        "settings.ai.ack.declined",
                        language,
                        default="Chat stays disabled until you accept the third-party notice.",
                    ),
                    level="info",
                )
        ack_host = host if ack else ""

        if mcp_on and not mcp_ack:
            if self._confirm_mcp():
                mcp_ack = True
                self._mcp_ack_check.setChecked(True)
            else:
                mcp_on = False
                mcp_ack = False
                self._mcp_check.setChecked(False)
                show_user_message(
                    self,
                    tr("settings.title", language, default="Settings"),
                    tr(
                        "settings.mcp.ack.declined",
                        language,
                        default="The MCP server stays disabled until you accept the notice.",
                    ),
                    level="info",
                )

        try:
            state = self._service.save(
                username=username,
                language=language,
                theme=theme,
                default_currency=str(self._default_currency_combo.currentData() or "USD"),
                thousands_sep=str(self._thousands_sep_combo.currentData() or ","),
                decimal_sep=str(self._decimal_sep_combo.currentData() or "."),
                preferred_model="",
                interaction_mode=interaction_mode,
                llm_provider=provider,
                llm_base_url=base_url or "http://localhost:1234/v1",
                llm_model=model,
                llm_api_key=api_key,
                llm_third_party_ack=ack,
                llm_ack_host=ack_host,
                mcp_enabled=mcp_on,
                mcp_third_party_ack=mcp_ack,
            )
        except ValueError:
            show_user_message(
                self,
                tr("settings.title", language, default="Settings"),
                tr(
                    "settings.validation.number_separators_distinct",
                    language,
                    default="Thousands and decimal separators must be different.",
                ),
                level="warning",
            )
            return
        self.settings_saved.emit(state.username)
        self.language_changed.emit(state.language)
        self.theme_changed.emit(state.theme)

    def refresh(self) -> None:
        """Return refresh."""
        state = self._service.load_state()
        self._apply_saved_settings(state)

    def _apply_saved_settings(self, state: SettingsViewState) -> None:
        """Return apply saved settings."""
        username = state.username or tr("settings.saved_default_user", self._language, default="Usuario")
        self._username_input.setText(username)
        self._language = normalize_language(state.language)
        idx = self._language_combo.findData(self._language)
        if idx >= 0:
            self._language_combo.setCurrentIndex(idx)
        theme = state.theme or "dark_teal.xml"
        tidx = self._theme_combo.findData(theme)
        if tidx >= 0:
            self._theme_combo.setCurrentIndex(tidx)
        if (currency_idx := self._default_currency_combo.findData(state.default_currency)) >= 0:
            self._default_currency_combo.setCurrentIndex(currency_idx)
        gidx = self._thousands_sep_combo.findData(state.thousands_sep)
        if gidx >= 0:
            self._thousands_sep_combo.setCurrentIndex(gidx)
        didx = self._decimal_sep_combo.findData(state.decimal_sep)
        if didx >= 0:
            self._decimal_sep_combo.setCurrentIndex(didx)

        pidx = self._provider_combo.findData(state.llm_provider)
        if pidx >= 0:
            self._provider_combo.setCurrentIndex(pidx)
        self._base_url_input.setText(state.llm_base_url)
        self._model_input.setText(state.llm_model)
        self._api_key_input.setText(state.llm_api_key)
        self._api_key_clear_btn.setEnabled(bool(state.llm_api_key))
        host = self._current_host()
        self._ack_check.setChecked(bool(state.llm_third_party_ack) and state.llm_ack_host == host)
        self._on_provider_changed()

        midx = self._mode_combo.findData(state.interaction_mode or "assistant")
        if midx >= 0:
            self._mode_combo.setCurrentIndex(midx)

        self._mcp_check.setChecked(state.mcp_enabled)
        self._mcp_ack_check.setChecked(
            str(self._db.setting.get("mcp_third_party_ack") or "0") == "1"
        )
        self._mcp_ack_check.setVisible(state.mcp_enabled)

    def set_engine_info(self, info: str) -> None:
        """Return set engine info."""
        self._engine_label.setText(
            tr("settings.engine.info", self._language, default="Engine: {info}", params={"info": info})
        )

    def _populate_currency_options(self) -> None:
        """Return populate currency options."""
        for currency in self._db.setting.list_currencies(region=None):
            code = str(currency.get("code") or "").strip().upper()
            name = str(currency.get("name") or "").strip()
            if code:
                self._default_currency_combo.addItem(f"{code}  -  {name}", code)
        for code in CURRENCY_CODES:
            if self._default_currency_combo.findData(code) < 0:
                self._default_currency_combo.addItem(code, code)
