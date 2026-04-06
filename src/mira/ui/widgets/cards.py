# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Reusable card widgets for MIRA views."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class CardWidget(QFrame):
    """A summary card showing a title and a large numeric value."""

    def __init__(self, title: str, value: str = "0.00", color: str = "#CCC") -> None:
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("QFrame{background:#3C4C61;border:1px solid #6E8198;border-radius:10px;}")
        self.setMinimumHeight(110)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        self._title_lbl = QLabel(title)
        self._title_lbl.setWordWrap(True)
        self._title_lbl.setStyleSheet(
            "font-size:12px;font-weight:700;color:#D6DEE8;background:transparent;border:none;"
        )
        layout.addWidget(self._title_lbl)

        self._value_lbl = QLabel(value)
        self._value_lbl.setStyleSheet(
            f"font-size:26px;font-weight:700;color:{color};background:transparent;border:none;"
        )
        layout.addWidget(self._value_lbl)

        self._primary_context_lbl = QLabel("")
        self._primary_context_lbl.setWordWrap(True)
        self._primary_context_lbl.setStyleSheet("font-size:10px;color:#D6DEE8;background:transparent;border:none;")
        self._primary_context_lbl.setVisible(False)
        layout.addWidget(self._primary_context_lbl)

        self._secondary_context_lbl = QLabel("")
        self._secondary_context_lbl.setWordWrap(True)
        self._secondary_context_lbl.setStyleSheet("font-size:9px;color:#9FB3C8;background:transparent;border:none;")
        self._secondary_context_lbl.setVisible(False)
        layout.addWidget(self._secondary_context_lbl)

    def set_value(self, value: str) -> None:
        self._value_lbl.setText(value)

    def set_color(self, color: str) -> None:
        self._value_lbl.setStyleSheet(
            f"font-size:26px;font-weight:700;color:{color};background:transparent;border:none;"
        )

    def set_context(
        self,
        primary: str = "",
        *,
        primary_color: str = "#D6DEE8",
        secondary: str = "",
        secondary_color: str = "#9FB3C8",
    ) -> None:
        self._primary_context_lbl.setText(primary)
        self._primary_context_lbl.setStyleSheet(
            f"font-size:10px;color:{primary_color};background:transparent;border:none;"
        )
        self._primary_context_lbl.setVisible(bool(primary))

        self._secondary_context_lbl.setText(secondary)
        self._secondary_context_lbl.setStyleSheet(
            f"font-size:9px;color:{secondary_color};background:transparent;border:none;"
        )
        self._secondary_context_lbl.setVisible(bool(secondary))
