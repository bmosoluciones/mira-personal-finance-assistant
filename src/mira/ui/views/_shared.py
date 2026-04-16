# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Shared UI helpers used across MIRA view modules."""

from __future__ import annotations

from datetime import date
from typing import Any

from PySide6.QtCharts import QChartView
from PySide6.QtCore import QDate, QPoint, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mira.db.database import Database
from mira.error_policy import ErrorDescriptor, describe as describe_error
from mira.finance_summary import build_savings_lookup
from mira.transaction_kinds import is_balance_adjustment_transaction
from mira.ui.i18n import normalize_language, tr
from mira.ui.notifications import show_user_message
from mira.ui.number_format import format_number, get_number_format_config


def _make_tag_badge(tag: dict) -> QLabel:
    """Return make tag badge."""
    lbl = QLabel(tag["name"])
    lbl.setStyleSheet(
        f"background:{tag['color']};color:#222;border-radius:6px;padding:2px 8px;margin:2px;font-size:11px;"
    )
    return lbl


def _notify(widget: QWidget, *args: object, level: str = "info") -> None:
    """Return notify."""
    if len(args) == 3 and isinstance(args[0], QWidget):
        _, title, message = args
    elif len(args) == 2:
        title, message = args
    else:
        raise TypeError("_notify expects (title, message) or (widget, title, message)")
    show_user_message(widget, str(title), str(message), level=level)


def _notify_info(widget: QWidget, *args: object) -> None:
    """Return notify info."""
    _notify(widget, *args, level="info")


def _notify_warning(widget: QWidget, *args: object) -> None:
    """Return notify warning."""
    _notify(widget, *args, level="warning")


def _notify_error(widget: QWidget, *args: object) -> None:
    """Return notify error."""
    _notify(widget, *args, level="error")


def _describe_exception(db: Database, error: Exception) -> ErrorDescriptor:
    """Return describe exception."""
    return describe_error(error, language=_ui_lang(db))


def _notify_exception(widget: QWidget, db: Database, error: Exception, *, title: str | None = None) -> None:
    """Return notify exception."""
    descriptor = _describe_exception(db, error)
    _notify(widget, title or descriptor.title, descriptor.message, level=descriptor.level)


_TABLE_STYLE = (
    "QTableWidget{border:1px solid palette(mid);}"
    "QHeaderView::section{padding:6px 8px;border:none;border-bottom:1px solid palette(mid);}"
    "QTableWidget::item{padding:4px 8px;border:none;}"
)

_BTN_STYLE = "QPushButton{border:1px solid palette(mid);" "border-radius:4px;padding:4px 10px;font-size:12px;}"

_COMBO_STYLE = "QComboBox{border:1px solid palette(mid);" "border-radius:3px;padding:3px 8px;}"

_DATE_STYLE = "QDateEdit{border:1px solid palette(mid);border-radius:3px;padding:3px 6px;}"

_INPUT_STYLE = "QLineEdit{border:1px solid palette(mid);" "border-radius:3px;padding:3px 8px;}"

_SIGNAL_CELL_ROLE = int(Qt.ItemDataRole.UserRole) + 101
_TYPE_BADGE_ROLE = int(Qt.ItemDataRole.UserRole) + 102
_CATEGORY_BASE_LABEL_ROLE = int(Qt.ItemDataRole.UserRole) + 103


def _date_to_qdate(d: date) -> QDate:
    """Convert a Python :class:`~datetime.date` to a :class:`~PySide6.QtCore.QDate`."""
    return QDate(d.year, d.month, d.day)


def _section_title(text: str) -> QLabel:
    """Return section title."""
    lbl = QLabel(text)
    lbl.setFont(QFont("Arial", 15, QFont.Weight.Bold))
    lbl.setStyleSheet("padding-bottom:4px;")
    return lbl


def _sub_title(text: str) -> QLabel:
    """Return sub title."""
    lbl = QLabel(text)
    lbl.setStyleSheet("font-weight:bold;font-size:12px;padding:4px 0 2px 0;")
    return lbl


def _make_toolbar_btn(label: str) -> QPushButton:
    """Return make toolbar btn."""
    btn = QPushButton(label)
    btn.setStyleSheet(_BTN_STYLE)
    return btn


def _build_scrollable_container(parent: QWidget) -> tuple[QScrollArea, QWidget, QVBoxLayout]:
    """Create a reusable vertical scroll container for dense report views."""
    scroll = QScrollArea(parent)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")

    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    scroll.setWidget(content)
    return scroll, content, layout


def _configure_chart_view(chart_view: QChartView, *, minimum_height: int = 360) -> None:
    """Apply consistent sizing so report charts stay readable."""
    chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
    chart_view.setMinimumHeight(minimum_height)


def _select_row_at_pos(table: QTableWidget, pos: QPoint) -> bool:
    """Select the row under a context-menu click and return True when valid."""
    item = table.itemAt(pos)
    if item is None:
        return False
    table.setCurrentCell(item.row(), item.column())
    table.selectRow(item.row())
    return True


def _fmt_amount(db: Database, amount: float, *, decimals: int = 2) -> str:
    """Return fmt amount."""
    cfg = get_number_format_config(db.setting)
    return format_number(float(amount), cfg, decimals=decimals, grouping=True)


def _fmt_amount_with_currency(db: Database, amount: float, currency: str, *, decimals: int = 2) -> str:
    """Return fmt amount with currency."""
    normalized_currency = currency.strip().upper()
    return (
        f"{normalized_currency} {_fmt_amount(db, amount, decimals=decimals)}"
        if normalized_currency
        else _fmt_amount(db, amount, decimals=decimals)
    )


def _savings_category_names(db: Database) -> set[str]:
    """Return savings category names."""
    return build_savings_lookup(db.category.list("expense"))[1]


def _tx_type_indicator(tx: dict[str, Any], savings_categories: set[str]) -> tuple[str, QColor]:
    """Return tx type indicator."""
    if is_balance_adjustment_transaction(tx):
        return "~ adjustment", QColor("#7AA2F7")
    is_transfer = int(tx.get("is_transfer") or 0) == 1
    if is_transfer:
        return "↔ transfer", QColor("#D7BA7D")
    tx_type = str(tx.get("type") or "").strip().casefold()
    if tx_type == "income":
        return "+ income", QColor("#4EC9B0")
    if tx_type == "expense":
        category_key = str(tx.get("category") or "").strip().casefold()
        if category_key in savings_categories:
            return "@ savings", QColor("#569CD6")
        return "- expense", QColor("#F48771")
    return tx_type, QColor("#C4CCD5")


def _make_tx_type_item(tx: dict[str, Any], savings_categories: set[str]) -> QTableWidgetItem:
    """Return make tx type item."""
    text, color = _tx_type_indicator(tx, savings_categories)
    item = QTableWidgetItem(text)
    item.setForeground(QBrush(color))
    if is_balance_adjustment_transaction(tx):
        badge_kind = "adjustment"
    elif int(tx.get("is_transfer") or 0) == 1:
        badge_kind = "transfer"
    elif str(tx.get("type") or "").strip().casefold() == "income":
        badge_kind = "income"
    elif (
        str(tx.get("type") or "").strip().casefold() == "expense"
        and str(tx.get("category") or "").strip().casefold() in savings_categories
    ):
        badge_kind = "savings"
    elif str(tx.get("type") or "").strip().casefold() == "expense":
        badge_kind = "expense"
    else:
        badge_kind = "other"
    item.setData(_TYPE_BADGE_ROLE, badge_kind)
    return item


def _ui_lang(db: Database) -> str:
    """Return ui lang."""
    return normalize_language(db.setting.get("language"))


def _tr_db(db: Database, key: str, default: str, *, params: dict[str, object] | None = None) -> str:
    """Return tr db."""
    return tr(key, _ui_lang(db), default=default, params=params)


def _account_type_label(db: Database, account_type: str) -> str:
    """Return account type label."""
    normalized = str(account_type or "bank").strip().lower()
    if normalized == "card":
        normalized = "credit"
    labels = {
        "bank": _tr_db(db, "accounts.type.bank", "bank"),
        "cash": _tr_db(db, "accounts.type.cash", "cash"),
        "credit": _tr_db(db, "accounts.type.credit", "credit"),
    }
    return labels.get(normalized, normalized)


# ---------------------------------------------------------------------------
# DashboardView
# ---------------------------------------------------------------------------
