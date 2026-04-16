# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Initial setup dialogs."""

from __future__ import annotations

from typing import cast

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWizard,
    QWizardPage,
    QWidget,
)

from mira.db.database import CURRENCY_CODES, Database
from mira.ui.dialogs._shared import (
    _INITIAL_SETUP_THEME,
    _make_balance_spin,
    _resolve_ui_icon_path,
)
from mira.ui.i18n import SUPPORTED_LANGUAGES, normalize_language, tr
from mira.ui.notifications import show_user_message
from mira.ui.number_format import separator_options, validate_number_format_config


class InitialSetupDialog(QWizard):
    """Multi-page first-run setup wizard."""

    _PAGE_WELCOME = 0
    _PAGE_PROFILE = 1
    _PAGE_LANGUAGE = 2
    _PAGE_CURRENCY = 3
    _PAGE_ACCOUNTS = 4

    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._wizard_language = "en"
        self.setWindowTitle(tr("setup.wizard.title", self._wizard_language, default="MIRA - Initial setup"))
        self.setMinimumWidth(560)
        self.setMinimumHeight(520)
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.setButtonText(QWizard.WizardButton.NextButton, tr("setup.wizard.btn.next", self._wizard_language))
        self.setButtonText(QWizard.WizardButton.BackButton, tr("setup.wizard.btn.back", self._wizard_language))
        self.setButtonText(QWizard.WizardButton.FinishButton, tr("setup.wizard.btn.finish", self._wizard_language))
        self.setButtonText(QWizard.WizardButton.CancelButton, tr("setup.wizard.btn.cancel", self._wizard_language))

        self._page_welcome = _WelcomePage()
        self._page_profile = _ProfilePage(db)
        self._page_language = _LanguageThemePage()
        self._page_currency = _CurrencyFormatPage(db)
        self._page_accounts = _AccountsPage()

        self.addPage(self._page_welcome)
        self.addPage(self._page_profile)
        self.addPage(self._page_language)
        self.addPage(self._page_currency)
        self.addPage(self._page_accounts)

        self._page_language.language_changed.connect(self._apply_language)
        self._apply_language(self._page_language.get_language())

    def _apply_language(self, language: str) -> None:
        lang = normalize_language(language)
        self._wizard_language = lang

        self.setWindowTitle(tr("setup.wizard.title", lang, default="MIRA - Initial setup"))
        self.setButtonText(QWizard.WizardButton.NextButton, tr("setup.wizard.btn.next", lang, default="Next ->"))
        self.setButtonText(QWizard.WizardButton.BackButton, tr("setup.wizard.btn.back", lang, default="<- Back"))
        self.setButtonText(QWizard.WizardButton.FinishButton, tr("setup.wizard.btn.finish", lang, default="Start"))
        self.setButtonText(QWizard.WizardButton.CancelButton, tr("setup.wizard.btn.cancel", lang, default="Cancel"))

        self._page_welcome.apply_language(lang)
        self._page_profile.apply_language(lang)
        self._page_language.apply_language(lang)
        self._page_currency.apply_language(lang)
        self._page_accounts.apply_language(lang)

    def get_data(self) -> dict:
        language = self._page_language.get_language()
        return {
            "username": self._page_profile.get_username(language),
            "language": language,
            "theme": self._page_language.get_theme(),
            "default_currency": self._page_currency.get_currency(),
            "decimal_sep": self._page_currency.get_decimal_sep(),
            "thousands_sep": self._page_currency.get_thousands_sep(),
            "account_names": self._page_accounts.get_account_names(),
            "account_specs": self._page_accounts.get_account_specs(),
        }


class _WelcomePage(QWizardPage):
    _ICON_SIZE = 75
    _BMO_LOGO_HEIGHT = 66

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._language = "en"
        self.setTitle(" ")

        layout = QVBoxLayout(self)
        layout.setSpacing(18)
        layout.setContentsMargins(30, 20, 30, 20)

        logo_lbl = QLabel()
        logo_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        logo_lbl.setMinimumSize(self._ICON_SIZE, self._ICON_SIZE)
        logo_lbl.setStyleSheet("background:transparent;")
        icon_path = _resolve_ui_icon_path("256x256.png")
        pixmap = QPixmap(str(icon_path))
        if not pixmap.isNull():
            logo_lbl.setPixmap(
                pixmap.scaled(
                    self._ICON_SIZE,
                    self._ICON_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            logo_font = QFont()
            logo_font.setPointSize(28)
            logo_font.setBold(True)
            logo_lbl.setFont(logo_font)
            logo_lbl.setText(tr("app.name", self._language, default="MIRA"))
        layout.addWidget(logo_lbl)

        tagline_lbl = QLabel()
        tagline_font = QFont()
        tagline_font.setPointSize(13)
        tagline_lbl.setFont(tagline_font)
        tagline_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        tagline_lbl.setStyleSheet("background:transparent;")
        layout.addWidget(tagline_lbl)

        layout.addSpacing(10)

        welcome_text = QLabel()
        welcome_text.setWordWrap(True)
        welcome_text.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        welcome_text.setStyleSheet("font-size:13px;background:transparent;")
        layout.addWidget(welcome_text)

        layout.addSpacing(10)

        features_box = QGroupBox()
        features_layout = QVBoxLayout(features_box)
        feature_labels: list[QLabel] = []
        for _ in range(4):
            lbl = QLabel()
            lbl.setStyleSheet("font-size:12px;background:transparent;")
            features_layout.addWidget(lbl)
            feature_labels.append(lbl)
        layout.addWidget(features_box)

        layout.addStretch()

        note = QLabel()
        note.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        note.setStyleSheet("font-size:11px;background:transparent;")
        layout.addWidget(note)

        bmo_logo_lbl = QLabel()
        bmo_logo_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        bmo_logo_lbl.setStyleSheet("background:transparent;padding-top:4px;")
        bmo_logo_path = _resolve_ui_icon_path("BMOLogoSmall.png")
        bmo_pixmap = QPixmap(str(bmo_logo_path))
        if not bmo_pixmap.isNull():
            bmo_logo_lbl.setPixmap(
                bmo_pixmap.scaledToHeight(
                    self._BMO_LOGO_HEIGHT,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            layout.addWidget(bmo_logo_lbl)

        self._logo_lbl = logo_lbl
        self._tagline_lbl = tagline_lbl
        self._welcome_text_lbl = welcome_text
        self._features_box = features_box
        self._feature_labels = feature_labels
        self._note_lbl = note
        self._bmo_logo_lbl = bmo_logo_lbl
        self.apply_language("en")

    def apply_language(self, lang: str) -> None:
        self._tagline_lbl.setText(tr("setup.page.welcome.tagline", lang, default="Personal Finance Assistant"))
        self._welcome_text_lbl.setText(tr("setup.page.welcome.text", lang))
        self._features_box.setTitle(tr("setup.page.welcome.features_title", lang))
        items = [
            tr("setup.page.welcome.feature.language", lang),
            tr("setup.page.welcome.feature.currency", lang),
            tr("setup.page.welcome.feature.categories", lang),
            tr("setup.page.welcome.feature.accounts", lang),
        ]
        self._note_lbl.setText(tr("setup.page.welcome.note", lang))
        for lbl, text in zip(self._feature_labels, items):
            lbl.setText(text)


class _ProfilePage(QWizardPage):
    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self.setTitle("")
        self.setSubTitle("")

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 10, 20, 10)

        self._intro_label = QLabel()
        self._intro_label.setWordWrap(True)
        self._intro_label.setStyleSheet("background:transparent;")
        layout.addWidget(self._intro_label)

        form = QFormLayout()
        form.setSpacing(12)

        self._name_label = QLabel()
        self._name_edit = QLineEdit()
        current_username = str(self._db.setting.get("username") or "").strip()
        if current_username and current_username.casefold() not in {"usuario", "user"}:
            self._name_edit.setText(current_username)
        form.addRow(self._name_label, self._name_edit)
        layout.addLayout(form)

        self._hint_label = QLabel()
        self._hint_label.setWordWrap(True)
        self._hint_label.setStyleSheet("font-size:11px;background:transparent;")
        layout.addWidget(self._hint_label)
        layout.addStretch()

        self.apply_language("en")

    def apply_language(self, lang: str) -> None:
        self.setTitle(tr("setup.page.profile.title", lang))
        self.setSubTitle(tr("setup.page.profile.subtitle", lang))
        self._intro_label.setText(tr("setup.page.profile.intro", lang))
        self._name_label.setText(tr("setup.page.profile.name_label", lang))
        self._name_edit.setPlaceholderText(tr("setup.page.profile.name_placeholder", lang))
        self._hint_label.setText(tr("setup.page.profile.hint", lang))

    def validatePage(self) -> bool:  # noqa: N802
        if not self._name_edit.text().strip():
            from mira.ui.views._shared import _notify_warning as shared_notify_warning

            wizard = self.wizard()
            setup_wizard = cast("InitialSetupDialog | None", wizard)
            lang = setup_wizard._wizard_language if setup_wizard else "en"
            shared_notify_warning(
                self,
                tr("validation.title", lang, default="Validation"),
                tr("setup.page.profile.validation.required", lang),
            )
            return False
        return True

    def get_username(self, language: str) -> str:
        return self._name_edit.text().strip() or tr("settings.saved_default_user", language)


class _LanguageThemePage(QWizardPage):
    language_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fallback_theme_options: list[tuple[str, str, str]] = []
        self.setTitle("")
        self.setSubTitle("")

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 10, 20, 10)

        form = QFormLayout()
        form.setSpacing(12)

        self._language_combo = QComboBox()
        self._language_combo.addItem(SUPPORTED_LANGUAGES["es"], "es")
        self._language_combo.addItem(SUPPORTED_LANGUAGES["en"], "en")
        if (en_idx := self._language_combo.findData("en")) >= 0:
            self._language_combo.setCurrentIndex(en_idx)
        self._language_label = QLabel()
        form.addRow(self._language_label, self._language_combo)

        self._theme_combo = QComboBox()
        self._theme_combo.setMaxVisibleItems(15)
        try:
            import qt_material  # noqa: PLC0415

            for theme_file in qt_material.list_themes():
                label = theme_file.replace(".xml", "").replace("_", " ").title()
                self._theme_combo.addItem(label, theme_file)
        except ImportError:
            self._fallback_theme_options = [
                ("settings.theme.dark", "Dark", "dark_teal.xml"),
                ("settings.theme.light", "Light", "light_blue.xml"),
            ]
            self._populate_fallback_theme_labels("en")
        if (default_idx := self._theme_combo.findData(_INITIAL_SETUP_THEME)) >= 0:
            self._theme_combo.setCurrentIndex(default_idx)
        self._theme_label = QLabel()
        form.addRow(self._theme_label, self._theme_combo)

        layout.addLayout(form)
        layout.addStretch()
        self._language_combo.currentIndexChanged.connect(self._on_language_changed)
        self.apply_language("en")

    def _populate_fallback_theme_labels(self, lang: str) -> None:
        if not self._fallback_theme_options:
            return
        current_value = self._theme_combo.currentData()
        self._theme_combo.clear()
        for key, default, theme_file in self._fallback_theme_options:
            self._theme_combo.addItem(tr(key, lang, default=default), theme_file)
        if current_value is not None and (idx := self._theme_combo.findData(current_value)) >= 0:
            self._theme_combo.setCurrentIndex(idx)
        elif (default_idx := self._theme_combo.findData(_INITIAL_SETUP_THEME)) >= 0:
            self._theme_combo.setCurrentIndex(default_idx)

    def _on_language_changed(self) -> None:
        lang = self.get_language()
        self.apply_language(lang)
        self.language_changed.emit(lang)

    def apply_language(self, lang: str) -> None:
        self.setTitle(tr("setup.page.language.title", lang))
        self.setSubTitle(tr("setup.page.language.subtitle", lang))
        self._language_label.setText(tr("setup.page.language.language_label", lang))
        self._theme_label.setText(tr("setup.page.language.theme_label", lang))
        self._populate_fallback_theme_labels(lang)

    def get_language(self) -> str:
        return self._language_combo.currentData() or "en"

    def get_theme(self) -> str:
        return self._theme_combo.currentData() or _INITIAL_SETUP_THEME


class _CurrencyFormatPage(QWizardPage):
    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._language = "en"
        self.setTitle("")
        self.setSubTitle("")

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 10, 20, 10)

        form = QFormLayout()
        form.setSpacing(12)

        self._currency_combo = QComboBox()
        self._currency_combo.setMaxVisibleItems(15)
        for currency in self._db.setting.list_currencies(region=None):
            code = currency.get("code", "").strip().upper()
            name = currency.get("name", "")
            if code:
                self._currency_combo.addItem(f"{code} - {name}", code)
        for code in CURRENCY_CODES:
            if self._currency_combo.findData(code) < 0:
                self._currency_combo.addItem(code, code)
        default_currency = (self._db.setting.get("default_currency") or "USD").strip().upper()
        if (idx := self._currency_combo.findData(default_currency)) >= 0:
            self._currency_combo.setCurrentIndex(idx)
        self._currency_label = QLabel()
        form.addRow(self._currency_label, self._currency_combo)

        sep_opts = separator_options()
        self._thousands_combo = QComboBox()
        self._decimal_combo = QComboBox()
        for value, label in sep_opts:
            self._thousands_combo.addItem(label, value)
            self._decimal_combo.addItem(label, value)
        self._thousands_combo.setCurrentIndex(0)
        if (dot_idx := self._decimal_combo.findData(".")) >= 0:
            self._decimal_combo.setCurrentIndex(dot_idx)
        self._thousands_label = QLabel()
        self._decimal_label = QLabel()
        form.addRow(self._thousands_label, self._thousands_combo)
        form.addRow(self._decimal_label, self._decimal_combo)

        layout.addLayout(form)
        self._hint_label = QLabel()
        self._hint_label.setStyleSheet("font-size:11px;background:transparent;")
        self._hint_label.setWordWrap(True)
        layout.addWidget(self._hint_label)
        layout.addStretch()
        self.apply_language("en")

    def apply_language(self, lang: str) -> None:
        self._language = normalize_language(lang)
        self.setTitle(tr("setup.page.currency.title", lang))
        self.setSubTitle(tr("setup.page.currency.subtitle", lang))
        self._currency_label.setText(tr("setup.page.currency.currency_label", lang))
        self._thousands_label.setText(tr("setup.page.currency.thousands_label", lang))
        self._decimal_label.setText(tr("setup.page.currency.decimal_label", lang))
        self._hint_label.setText(tr("setup.page.currency.hint", lang))

    def get_currency(self) -> str:
        return self._currency_combo.currentData() or "USD"

    def get_thousands_sep(self) -> str:
        return self._thousands_combo.currentData() or ","

    def get_decimal_sep(self) -> str:
        return self._decimal_combo.currentData() or "."

    def validatePage(self) -> bool:
        try:
            validate_number_format_config(self.get_thousands_sep(), self.get_decimal_sep())
        except ValueError:
            show_user_message(
                self,
                tr("settings.title", self._language, default="Settings"),
                tr(
                    "settings.validation.number_separators_distinct",
                    self._language,
                    default="Thousands and decimal separators must be different.",
                ),
                level="warning",
            )
            return False
        return True


class _AccountsPage(QWizardPage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._account_rows: list[dict[str, object]] = []

        self.setTitle("")
        self.setSubTitle("")

        outer = QVBoxLayout(self)
        outer.setSpacing(10)
        outer.setContentsMargins(20, 10, 20, 10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border-radius:4px;}")
        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background:transparent;")
        self._inputs_layout = QVBoxLayout(scroll_widget)
        self._inputs_layout.setSpacing(8)
        self._inputs_layout.setContentsMargins(10, 10, 10, 10)
        self._inputs_layout.addStretch()
        scroll.setWidget(scroll_widget)
        outer.addWidget(scroll, 1)

        self._btn_add = QPushButton()
        self._btn_add.clicked.connect(self._add_input_row)
        outer.addWidget(self._btn_add)

        self._btn_skip = QPushButton()
        self._btn_skip.setStyleSheet(
            "QPushButton{background:transparent;border:none;text-decoration:underline;padding:2px;}"
        )
        self._btn_skip.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_skip.clicked.connect(self._on_skip)
        outer.addWidget(self._btn_skip, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._btn_skip.hide()

        self.apply_language("en")

    def initializePage(self) -> None:
        super().initializePage()
        if not self._account_rows:
            self._add_input_row()
        else:
            self._sync_account_row_currency_defaults()

    def _add_input_row(self) -> None:
        idx = len(self._account_rows) + 1
        lang = getattr(self, "_lang", "en")
        currency_default = self._db_default_currency()

        card = QGroupBox()
        card.setStyleSheet("QGroupBox{margin-top:6px;}")
        form = QFormLayout(card)
        form.setSpacing(8)

        name_edit = QLineEdit()
        name_edit.setPlaceholderText(tr("setup.page.accounts.row.name_placeholder", lang, params={"idx": idx}))
        form.addRow(tr("setup.page.accounts.row.name_label", lang), name_edit)

        type_combo = QComboBox()
        type_combo.addItem(tr("setup.page.accounts.row.type.bank", lang), "bank")
        type_combo.addItem(tr("setup.page.accounts.row.type.cash", lang), "cash")
        type_combo.addItem(tr("setup.page.accounts.row.type.credit", lang), "credit")
        form.addRow(tr("setup.page.accounts.row.type_label", lang), type_combo)

        currency_combo = QComboBox()
        currency_combo.setEditable(True)
        for cur in self._db_currencies():
            code = str(cur["code"]).upper()
            currency_combo.addItem(code, code)
        if (idx_currency := currency_combo.findData(currency_default)) >= 0:
            currency_combo.setCurrentIndex(idx_currency)
        else:
            currency_combo.setCurrentText(currency_default)
        form.addRow(tr("setup.page.accounts.row.currency_label", lang), currency_combo)

        balance_spin = _make_balance_spin(self._db_ref())
        balance_spin.setValue(0.0)
        form.addRow(tr("setup.page.accounts.row.balance_label", lang), balance_spin)

        row_spec: dict[str, object] = {
            "card": card,
            "name": name_edit,
            "type": type_combo,
            "currency": currency_combo,
            "opening_balance": balance_spin,
            "suggested_currency": currency_default,
        }
        self._account_rows.append(row_spec)
        self._apply_row_title(row_spec, idx)

        stretch_idx = self._inputs_layout.count() - 1
        self._inputs_layout.insertWidget(stretch_idx, card)

    def _db_ref(self) -> Database:
        wizard = self.wizard()
        if wizard is not None and hasattr(wizard, "_db"):
            return cast(Database, wizard._db)
        raise RuntimeError("Accounts page requires a database reference")

    def _db_default_currency(self) -> str:
        wizard = self.wizard()
        if wizard is not None and hasattr(wizard, "_page_currency"):
            return str(wizard._page_currency.get_currency()).upper()
        return self._db_ref().setting.get_default_currency()

    def _db_currencies(self) -> list[dict]:
        return self._db_ref().setting.list_currencies(region="americas")

    def _sync_account_row_currency_defaults(self) -> None:
        current_default = self._db_default_currency()
        for row_spec in self._account_rows:
            currency_combo = cast(QComboBox, row_spec["currency"])
            previous_default = str(row_spec.get("suggested_currency") or "").strip().upper()
            current_value = currency_combo.currentText().strip().upper()
            if not current_value or current_value == previous_default:
                if (idx_currency := currency_combo.findData(current_default)) >= 0:
                    currency_combo.setCurrentIndex(idx_currency)
                else:
                    currency_combo.setCurrentText(current_default)
            row_spec["suggested_currency"] = current_default

    def _apply_row_title(self, row_spec: dict[str, object], idx: int) -> None:
        card = cast(QGroupBox, row_spec["card"])
        name_edit = cast(QLineEdit, row_spec["name"])
        lang = getattr(self, "_lang", "en")
        card.setTitle(tr("setup.page.accounts.row.title", lang, params={"idx": idx}))
        name_edit.setPlaceholderText(tr("setup.page.accounts.row.name_placeholder", lang, params={"idx": idx}))

    def _refresh_input_labels(self) -> None:
        for idx, row_spec in enumerate(self._account_rows, start=1):
            self._apply_row_title(row_spec, idx)

    def _on_skip(self) -> None:
        return

    def apply_language(self, lang: str) -> None:
        self._lang = lang
        self.setTitle(tr("setup.page.accounts.title", lang))
        self.setSubTitle(tr("setup.page.accounts.subtitle", lang))
        self._btn_add.setText(tr("setup.page.accounts.btn_add", lang))
        self._btn_skip.setText(tr("setup.page.accounts.btn_skip", lang))
        self._refresh_input_labels()

    def get_account_names(self) -> list[str]:
        return [str(spec["name"]) for spec in self.get_account_specs()]

    def get_account_specs(self) -> list[dict[str, object]]:
        specs: list[dict[str, object]] = []
        for row_spec in self._account_rows:
            name_edit = cast(QLineEdit, row_spec["name"])
            type_combo = cast(QComboBox, row_spec["type"])
            currency_combo = cast(QComboBox, row_spec["currency"])
            balance_spin = cast(QDoubleSpinBox, row_spec["opening_balance"])
            name = name_edit.text().strip()
            if not name:
                continue
            specs.append(
                {
                    "name": name,
                    "account_type": str(type_combo.currentData() or "bank"),
                    "currency": currency_combo.currentText().strip().upper() or self._db_default_currency(),
                    "opening_balance": float(balance_spin.value()),
                }
            )
        return specs


__all__ = ["InitialSetupDialog"]
