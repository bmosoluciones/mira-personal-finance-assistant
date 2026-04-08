# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Reusable item delegates for MIRA tables."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from mira.ui.views._shared import _SIGNAL_CELL_ROLE, _TYPE_BADGE_ROLE


class _SignalCellDelegate(QStyledItemDelegate):
    """Paint semantic comparison cells without relying on theme foreground/background rules."""

    def paint(self, painter: QPainter, option, index) -> None:  # type: ignore[override]
        signal = index.data(_SIGNAL_CELL_ROLE)
        if signal not in {"positive", "negative", "neutral"}:
            super().paint(painter, option, index)
            return

        if signal == "positive":
            background = QColor("#173B36")
            foreground = QColor("#7FE7D2")
            border = QColor("#2F7D6E")
            indicator = "▲"
        elif signal == "negative":
            background = QColor("#472624")
            foreground = QColor("#FFB0A3")
            border = QColor("#9B4F47")
            indicator = "▼"
        else:
            background = QColor("#30363D")
            foreground = QColor("#C4CCD5")
            border = QColor("#58616C")
            indicator = "•"

        if option.state & QStyle.StateFlag.State_Selected:
            background = background.lighter(120)

        rect = option.rect.adjusted(1, 1, -1, -1)
        alignment_data = index.data(Qt.ItemDataRole.TextAlignmentRole)
        alignment = int(alignment_data) if alignment_data is not None else int(Qt.AlignmentFlag.AlignVCenter)

        painter.save()
        painter.fillRect(rect, background)
        painter.setPen(border)
        painter.drawRect(rect.adjusted(0, 0, -1, -1))

        font = option.font
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(foreground)

        indicator_rect = rect.adjusted(rect.width() - 18, 0, -6, 0)
        text_rect = rect.adjusted(8, 0, -26, 0)
        painter.drawText(text_rect, alignment, str(index.data(Qt.ItemDataRole.DisplayRole) or ""))

        indicator_font = QFont(font)
        indicator_font.setWeight(QFont.Weight.Bold)
        painter.setFont(indicator_font)
        painter.drawText(
            indicator_rect,
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            indicator,
        )
        painter.restore()


class _TypeBadgeDelegate(QStyledItemDelegate):
    """Paint type badges without being overridden by active theme rules."""

    def paint(self, painter: QPainter, option, index) -> None:  # type: ignore[override]
        badge = index.data(_TYPE_BADGE_ROLE)
        if badge not in {"income", "expense", "savings", "transfer", "adjustment"}:
            super().paint(painter, option, index)
            return

        if badge == "income":
            background = QColor("#173B36")
            foreground = QColor("#4EC9B0")
            border = QColor("#2F7D6E")
        elif badge == "expense":
            background = QColor("#472624")
            foreground = QColor("#F48771")
            border = QColor("#9B4F47")
        elif badge == "transfer":
            background = QColor("#3B3520")
            foreground = QColor("#D7BA7D")
            border = QColor("#8B7D3C")
        elif badge == "adjustment":
            background = QColor("#24324D")
            foreground = QColor("#7AA2F7")
            border = QColor("#4B6FB6")
        else:
            background = QColor("#1F3650")
            foreground = QColor("#569CD6")
            border = QColor("#3D6D96")

        if option.state & QStyle.StateFlag.State_Selected:
            background = background.lighter(120)

        rect = option.rect.adjusted(6, 4, -6, -4)
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(border)
        painter.setBrush(background)
        painter.drawRoundedRect(rect, 6, 6)

        font = option.font
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(foreground)
        painter.drawText(
            rect.adjusted(8, 0, -8, 0),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            text,
        )
        painter.restore()
