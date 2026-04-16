# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Settings feature view."""

from __future__ import annotations


from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mira.ai.engine import is_llama_cpp_available
from mira.ai.model_registry import discover_gguf_models
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


class _SettingsRuntimeAdapter:
    """Small seam around runtime/model discovery for SettingsView."""

    def is_llama_cpp_available(self) -> bool:
        """Return whether llama cpp available."""
        return is_llama_cpp_available()

    def discover_models(self):
        """Return discover models."""
        return discover_gguf_models()


class SettingsView(QWidget):
    """Application settings view."""

    settings_saved = Signal(str)  # emits new username
    language_changed = Signal(str)  # emits selected language code
    theme_changed = Signal(str)  # emits selected theme
    download_default_model_requested = Signal()

    def __init__(
        self,
        db: Database,
        parent: QWidget | None = None,
        runtime_adapter: _SettingsRuntimeAdapter | None = None,
        service: SettingsViewService | None = None,
    ) -> None:
        """Initialize the SettingsView instance."""
        super().__init__(parent)
        self._db = db
        self._service = service or SettingsViewService(db)
        self._language = normalize_language(self._db.setting.get("language"))
        self._runtime = runtime_adapter or _SettingsRuntimeAdapter()
        self._llama_cpp_available = self._runtime.is_llama_cpp_available()
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
            import qt_material  # noqa: PLC0415

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

        self._engine_label = QLabel(
            tr(
                "settings.ai_rule_based",
                self._language,
                default="Engine: Deterministic assistant parser (no GGUF model loaded)",
            )
        )
        self._engine_label.setStyleSheet("font-size:11px;")
        ai_layout.addWidget(self._engine_label)

        ai_note = QLabel(
            tr(
                "settings.ai_note",
                self._language,
                default="Assistant mode uses the deterministic parser. Select a GGUF model only if you want local chat.",
            )
        )
        ai_note.setWordWrap(True)
        ai_note.setStyleSheet("font-size:10px;")
        ai_layout.addWidget(ai_note)

        self._chat_support_note = QLabel(
            tr(
                "settings.chat_support_unavailable",
                self._language,
                default=(
                    "Local chat controls are unavailable in this environment because "
                    "llama-cpp-python is not installed."
                ),
            )
        )
        self._chat_support_note.setWordWrap(True)
        self._chat_support_note.setStyleSheet("font-size:10px;")
        self._chat_support_note.setVisible(not self._llama_cpp_available)
        ai_layout.addWidget(self._chat_support_note)

        self._model_checks: list[QCheckBox] = []
        self._models_frame = QFrame()
        self._models_layout = QVBoxLayout(self._models_frame)
        self._models_layout.setContentsMargins(0, 4, 0, 0)
        self._models_layout.setSpacing(4)

        self._download_default_btn = QPushButton(
            tr(
                "settings.download_default_model",
                self._language,
                default="Descargar modelo predeterminado",
            )
        )
        self._download_default_btn.setStyleSheet(_BTN_STYLE)
        self._download_default_btn.clicked.connect(self.download_default_model_requested.emit)

        self._refresh_model_options(selected_model="")
        ai_layout.addWidget(self._models_frame)

        self._mode_combo = QComboBox()
        self._mode_combo.setStyleSheet(_COMBO_STYLE)
        self._mode_combo.addItem(
            tr("settings.mode.assistant", self._language, default="Assistant mode"),
            "assistant",
        )
        if self._llama_cpp_available:
            self._mode_combo.addItem(tr("settings.mode.chat", self._language, default="Chat mode"), "chat")
        self._mode_label = QLabel(tr("settings.mode", self._language, default="LLM interaction mode"))
        self._mode_label.setVisible(self._llama_cpp_available)
        ai_layout.addWidget(self._mode_label)
        self._mode_combo.setVisible(self._llama_cpp_available)
        ai_layout.addWidget(self._mode_combo)

        layout.addWidget(ai_grp)

        layout.addStretch()

    def _save(self) -> None:
        """Return save."""
        username = self._username_input.text().strip() or tr(
            "settings.saved_default_user", self._language, default="Usuario"
        )
        language = normalize_language(self._language_combo.currentData())
        theme = self._theme_combo.currentData() or "dark_teal.xml"
        selected_model = ""
        for chk in self._model_checks:
            if chk.isChecked():
                selected_model = chk.text()
                break
        interaction_mode = "assistant"
        if self._llama_cpp_available:
            interaction_mode = self._mode_combo.currentData() or "assistant"
        try:
            state = self._service.save(
                username=username,
                language=language,
                theme=theme,
                default_currency=str(self._default_currency_combo.currentData() or "USD"),
                thousands_sep=str(self._thousands_sep_combo.currentData() or ","),
                decimal_sep=str(self._decimal_sep_combo.currentData() or "."),
                preferred_model=selected_model if self._llama_cpp_available else "",
                interaction_mode=interaction_mode,
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
        self._refresh_runtime_availability(selected_model=state.preferred_model)
        self._apply_saved_settings(state)

    def _refresh_runtime_availability(self, *, selected_model: str) -> None:
        """Return refresh runtime availability."""
        self._llama_cpp_available = self._runtime.is_llama_cpp_available()
        self._chat_support_note.setVisible(not self._llama_cpp_available)
        self._mode_label.setVisible(self._llama_cpp_available)
        self._mode_combo.setVisible(self._llama_cpp_available)
        self._refresh_model_options(selected_model=selected_model)

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
        mode = "assistant"
        if self._llama_cpp_available:
            mode = state.interaction_mode or "assistant"
        midx = self._mode_combo.findData(mode)
        if midx >= 0:
            self._mode_combo.setCurrentIndex(midx)

    def set_engine_info(self, info: str) -> None:
        """Return set engine info."""
        self._engine_label.setText(
            tr("settings.engine.info", self._language, default="Engine: {info}", params={"info": info})
        )

    def _refresh_model_options(self, *, selected_model: str) -> None:
        """Return refresh model options."""
        self._models_frame.setVisible(self._llama_cpp_available)
        self._download_default_btn.setVisible(False)
        while self._models_layout.count():
            item = self._models_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None and widget is not self._download_default_btn:
                widget.deleteLater()
        self._model_checks.clear()

        if not self._llama_cpp_available:
            return

        model_label = QLabel(tr("settings.models", self._language, default="Available GGUF models"))
        model_label.setStyleSheet("font-size:11px;")
        self._models_layout.addWidget(model_label)

        available_models = self._runtime.discover_models()
        for model in available_models:
            chk = QCheckBox(model.name)
            chk.setStyleSheet("")
            chk.setChecked(model.name == selected_model)
            chk.stateChanged.connect(lambda _state, current=chk: self._on_model_checked(current))
            self._model_checks.append(chk)
            self._models_layout.addWidget(chk)

        if not available_models:
            no_models = QLabel(
                tr(
                    "settings.models.none",
                    self._language,
                    default="No GGUF models found in model directories",
                )
            )
            no_models.setStyleSheet("font-size:10px;")
            self._models_layout.addWidget(no_models)
            self._download_default_btn.setVisible(True)
            self._models_layout.addWidget(self._download_default_btn)
        else:
            self._download_default_btn.setVisible(False)

    def _on_model_checked(self, current: QCheckBox) -> None:
        """Return on model checked."""
        if not current.isChecked():
            return
        for chk in self._model_checks:
            if chk is current:
                continue
            chk.blockSignals(True)
            chk.setChecked(False)
            chk.blockSignals(False)

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
