# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Tag dialogs."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mira.db.database import Database
from mira.ui.dialogs._shared import _build_icon_combo, _notify_warning, _set_icon_combo_value
from mira.ui.i18n import normalize_language


class TagDialog(QDialog):
    """Create or edit a transversal tag."""

    def __init__(self, db: Database, tag: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        self._db = db
        self._tag = tag
        self.setWindowTitle("Edit Tag" if tag else "Add Tag")
        self.setMinimumWidth(320)
        self._build_ui()
        if tag:
            self._prefill(tag)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Tag name…")
        form.addRow("Name:", self._name_edit)
        self._color_preview = QLabel()
        self._color_preview.setFixedSize(24, 24)
        self._color_preview.setStyleSheet("border:1px solid #888888;border-radius:4px;background:#888888;")
        self._color_value_label = QLabel()
        self._color_value_label.setMinimumWidth(84)
        self._color_value_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._color_btn = QPushButton("Choose color")
        self._color_btn.clicked.connect(self._choose_color)
        color_container = QWidget()
        color_row = QHBoxLayout(color_container)
        color_row.setContentsMargins(0, 0, 0, 0)
        color_row.addWidget(self._color_preview)
        color_row.addWidget(self._color_value_label)
        color_row.addStretch()
        color_row.addWidget(self._color_btn)
        self._selected_color = "#888888"
        self._update_color_preview(self._selected_color)
        form.addRow("Color:", color_container)
        self._icon_combo = _build_icon_combo(self, lang=normalize_language(self._db.setting.get("language")))
        form.addRow("Icon:", self._icon_combo)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _prefill(self, tag: dict) -> None:
        self._name_edit.setText(tag.get("name", ""))
        self._update_color_preview(str(tag.get("color") or "#888888"))
        _set_icon_combo_value(self._icon_combo, str(tag.get("icon") or ""))

    def _update_color_preview(self, color_value: str) -> None:
        color = QColor(color_value)
        if not color.isValid():
            color = QColor("#888888")
        self._selected_color = color.name()
        self._color_value_label.setText(self._selected_color.upper())
        self._color_preview.setStyleSheet(
            f"border:1px solid #888888;border-radius:4px;background:{self._selected_color};"
        )

    def _choose_color(self) -> None:
        color = QColorDialog.getColor(QColor(self._selected_color), self, "Select Tag Color")
        if color.isValid():
            self._update_color_preview(color.name())

    def _on_accept(self) -> None:
        if not self._name_edit.text().strip():
            _notify_warning(self, "Validation", "Tag name cannot be empty.")
            return
        self.accept()

    def get_data(self) -> dict:
        icon_value = (self._icon_combo.currentData() or self._icon_combo.currentText()).strip()
        return {
            "name": self._name_edit.text().strip(),
            "color": self._selected_color,
            "icon": icon_value,
        }


__all__ = ["TagDialog"]
