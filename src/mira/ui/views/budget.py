# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Budget analytics feature view."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, cast

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mira.budget_processor import process_budget_value
from mira.db.database import Database
from mira.db.errors import BudgetError, DuplicateBudgetCodeError
from mira.ui.number_format import (
    get_number_format_config,
    parse_number,
)
from mira.ui.views._shared import (
    _COMBO_STYLE,
    _SIGNAL_CELL_ROLE,
    _TABLE_STYLE,
    _build_scrollable_container,
    _fmt_amount,
    _make_toolbar_btn,
    _notify_error,
    _notify_info,
    _notify_warning,
    _section_title,
    _sub_title,
    _tr_db,
)
from mira.ui.widgets.cards import CardWidget
from mira.ui.delegates.cell_delegates import _SignalCellDelegate

_BUDGET_AMOUNT_ROLE = int(Qt.ItemDataRole.UserRole) + 1


@dataclass
class BudgetViewState:
    """Explicit local state for the budget workspace."""

    current_budget_id: int | None = None
    loaded_budget_id: int | None = None
    current_monthly_tracking: dict[str, Any] | None = None
    budget_list_cache: list[dict[str, Any]] = field(default_factory=list)
    budget_list_dirty: bool = True
    loading_budget_table: bool = False


class BudgetView(QWidget):
    """Annual budget planning and real-vs-budget comparison."""

    _MONTH_LABELS = [
        ("budget.month.jan", "Ene"),
        ("budget.month.feb", "Feb"),
        ("budget.month.mar", "Mar"),
        ("budget.month.apr", "Abr"),
        ("budget.month.may", "May"),
        ("budget.month.jun", "Jun"),
        ("budget.month.jul", "Jul"),
        ("budget.month.aug", "Ago"),
        ("budget.month.sep", "Sep"),
        ("budget.month.oct", "Oct"),
        ("budget.month.nov", "Nov"),
        ("budget.month.dec", "Dic"),
    ]

    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._state = BudgetViewState()
        self._build_ui()

    @property
    def _current_budget_id(self) -> int | None:
        return self._state.current_budget_id

    @_current_budget_id.setter
    def _current_budget_id(self, value: int | None) -> None:
        self._state.current_budget_id = value

    @property
    def _loaded_budget_id(self) -> int | None:
        return self._state.loaded_budget_id

    @_loaded_budget_id.setter
    def _loaded_budget_id(self, value: int | None) -> None:
        self._state.loaded_budget_id = value

    @property
    def _current_monthly_tracking(self) -> dict[str, Any] | None:
        return self._state.current_monthly_tracking

    @_current_monthly_tracking.setter
    def _current_monthly_tracking(self, value: dict[str, Any] | None) -> None:
        self._state.current_monthly_tracking = value

    @property
    def _budget_list_cache(self) -> list[dict[str, Any]]:
        return self._state.budget_list_cache

    @_budget_list_cache.setter
    def _budget_list_cache(self, value: list[dict[str, Any]]) -> None:
        self._state.budget_list_cache = value

    @property
    def _budget_list_dirty(self) -> bool:
        return self._state.budget_list_dirty

    @_budget_list_dirty.setter
    def _budget_list_dirty(self, value: bool) -> None:
        self._state.budget_list_dirty = value

    @property
    def _loading_budget_table(self) -> bool:
        return self._state.loading_budget_table

    @_loading_budget_table.setter
    def _loading_budget_table(self, value: bool) -> None:
        self._state.loading_budget_table = value

    def _t(self, key: str, default: str, *, params: dict[str, object] | None = None) -> str:
        return _tr_db(self._db, key, default, params=params)

    def _month_labels(self) -> list[str]:
        return [self._t(key, fallback) for key, fallback in self._MONTH_LABELS]

    def _set_budget_status(self, text: str, *, color: str = "#9FB3C8") -> None:
        self._budget_status_lbl.setText(text)
        self._budget_status_lbl.setStyleSheet(f"font-size:11px;color:{color};padding:0 2px 2px 2px;")

    def _set_budget_placeholder_hint(self, text: str) -> None:
        self._budget_placeholder_hint.setText(text)

    def _selected_budget_from_cache(self) -> dict[str, Any] | None:
        if self._current_budget_id is None:
            return None
        return next(
            (budget for budget in self._budget_list_cache if int(budget["id"]) == self._current_budget_id),
            None,
        )

    def _clear_budget_outputs(self) -> None:
        self._income_card.set_value("0.00")
        self._expense_card.set_value("0.00")
        self._balance_card.set_value("0.00")
        self._balance_card.set_color("#D6DEE8")
        self._warning_lbl.setText("")
        self._budget_table.clearContents()
        self._budget_table.setRowCount(0)
        self._comparison_table.clear()
        self._comparison_table.setRowCount(0)
        self._comparison_table.setColumnCount(0)
        self._comparison_hint.setText("")
        self._monthly_tracking_table.clearContents()
        self._monthly_tracking_table.setRowCount(0)
        self._monthly_tracking_hint.setText("")
        self._tracking_assigned_card.set_value("0.00")
        self._tracking_executed_card.set_value("0.00")
        self._tracking_available_card.set_value("0.00")
        self._tracking_available_card.set_color("#4EC9B0")
        self._reassign_source_combo.clear()
        self._reassign_target_combo.clear()
        self._reassign_amount_input.clear()
        self._reassign_available_lbl.setText(self._t("budget.reassign.available", "Disponible: 0.00"))
        self._btn_apply_reassign.setEnabled(False)

    def _mark_budget_pending(self) -> None:
        self._loaded_budget_id = None
        self._current_monthly_tracking = None
        if self._current_budget_id is None:
            self._set_budget_placeholder_hint(
                self._t(
                    "budget.placeholder.hint",
                    "No hay presupuestos creados todavia. Crea uno nuevo con codigo, ano y moneda. "
                    "Cuando lo guardes, esta tabla se llenara con las 12 columnas mensuales y el total anual.",
                )
            )
            self._clear_budget_outputs()
            self._set_budget_status(self._t("budget.status.empty", "Crea o selecciona un presupuesto para comenzar."))
            return

        self._set_budget_placeholder_hint(
            self._t(
                "budget.placeholder.load_hint",
                "La vista ya esta lista. Pulsa 'Cargar presupuesto' para consultar la matriz anual del presupuesto seleccionado.",
            )
        )
        self._clear_budget_outputs()
        self._comparison_hint.setText(
            self._t(
                "budget.compare.pending",
                "Pulsa 'Comparar con real' para consultar el comparativo del presupuesto seleccionado.",
            )
        )
        self._monthly_tracking_hint.setText(
            self._t(
                "budget.monthly.pending",
                "Pulsa 'Ejecutar' para consultar la ejecucion mensual del presupuesto seleccionado.",
            )
        )
        self._set_budget_status(
            self._t(
                "budget.status.pending",
                "La pantalla ya esta visible. Carga el presupuesto solo cuando quieras consultar la base de datos.",
            )
        )
        self._set_budget_enabled(True)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        layout.addWidget(_section_title(self._t("budget.title", "Presupuestos")))

        help_lbl = QLabel(
            self._t(
                "budget.help",
                "Un presupuesto en MIRA se prepara por año, permite presupuestar los 12 meses y puede quedar "
                "deficitario si esperas cubrirlo con ahorro o deuda. Proponer presupuesto usa el promedio mensual "
                "del último año con datos suficientes. La comparación con lo real excluye movimientos en monedas "
                "que no se puedan reconciliar con la moneda del presupuesto.",
            )
        )
        help_lbl.setWordWrap(True)
        help_lbl.setStyleSheet("font-size:11px;color:#B7C3D0;padding-bottom:4px;")
        layout.addWidget(help_lbl)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.addWidget(QLabel(self._t("budget.selector", "Presupuesto:")))

        self._budget_combo = QComboBox()
        self._budget_combo.setStyleSheet(_COMBO_STYLE)
        self._budget_combo.currentIndexChanged.connect(self._on_budget_changed)
        toolbar.addWidget(self._budget_combo, 1)

        self._btn_load_budget = _make_toolbar_btn(self._t("budget.load", "Cargar presupuesto"))
        self._btn_load_budget.clicked.connect(self._load_budget)
        toolbar.addWidget(self._btn_load_budget)

        self._btn_new = _make_toolbar_btn(self._t("budget.new", "Nuevo presupuesto"))
        self._btn_new.clicked.connect(self.open_create_dialog)
        toolbar.addWidget(self._btn_new)

        self._btn_delete = _make_toolbar_btn(self._t("budget.delete", "Eliminar"))
        self._btn_delete.clicked.connect(self._on_delete_budget)
        toolbar.addWidget(self._btn_delete)

        self._btn_set_default = _make_toolbar_btn(self._t("budget.set_default", "Definir como predeterminado"))
        self._btn_set_default.clicked.connect(self._on_set_default_budget)
        toolbar.addWidget(self._btn_set_default)

        self._btn_propose = _make_toolbar_btn(self._t("budget.propose", "Proponer presupuesto"))
        self._btn_propose.clicked.connect(self._on_propose_budget)
        toolbar.addWidget(self._btn_propose)

        self._btn_compare = _make_toolbar_btn(self._t("budget.compare", "Comparar con real"))
        self._btn_compare.setCheckable(True)
        self._btn_compare.clicked.connect(self._on_toggle_compare)
        toolbar.addWidget(self._btn_compare)

        self._btn_monthly_tracking = _make_toolbar_btn(
            self._t("budget.monthly_tracking", "Seguimiento mensual presupuestario")
        )
        self._btn_monthly_tracking.setCheckable(True)
        self._btn_monthly_tracking.clicked.connect(self._on_toggle_monthly_tracking)
        toolbar.addWidget(self._btn_monthly_tracking)

        self._btn_export_excel = _make_toolbar_btn(self._t("budget.export_excel", "Exportar Excel"))
        self._btn_export_excel.clicked.connect(self._on_export_comparison_excel)
        toolbar.addWidget(self._btn_export_excel)

        self._granularity_label = QLabel(self._t("budget.granularity.label", "Vista real vs ppto:"))
        toolbar.addWidget(self._granularity_label)
        self._granularity_combo = QComboBox()
        self._granularity_combo.setStyleSheet(_COMBO_STYLE)
        self._granularity_combo.addItem(self._t("budget.granularity.quarterly", "Trimestral"), "quarterly")
        self._granularity_combo.addItem(self._t("budget.granularity.annual", "Anual"), "annual")
        self._granularity_combo.addItem(self._t("budget.granularity.semiannual", "Semestral"), "semiannual")
        self._granularity_combo.addItem(self._t("budget.granularity.monthly", "Mensual"), "monthly")
        self._granularity_combo.currentIndexChanged.connect(self._refresh_comparison)
        toolbar.addWidget(self._granularity_combo)

        layout.addLayout(toolbar)

        self._budget_status_lbl = QLabel("")
        self._budget_status_lbl.setWordWrap(True)
        layout.addWidget(self._budget_status_lbl)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)
        self._income_card = CardWidget(self._t("budget.card.income", "Ingreso total esperado"), "0.00", "#4EC9B0")
        self._expense_card = CardWidget(
            self._t("budget.card.expense", "Gasto total presupuestado"),
            "0.00",
            "#F48771",
        )
        self._balance_card = CardWidget(
            self._t("budget.card.balance", "Balance presupuestado anual"),
            "0.00",
            "#D6DEE8",
        )
        cards_row.addWidget(self._income_card)
        cards_row.addWidget(self._expense_card)
        cards_row.addWidget(self._balance_card)
        layout.addLayout(cards_row)

        self._warning_lbl = QLabel("")
        self._warning_lbl.setWordWrap(True)
        self._warning_lbl.setStyleSheet("font-size:11px;color:#F7C16B;")
        layout.addWidget(self._warning_lbl)

        self._content_stack = QStackedWidget()

        self._editor_panel = QWidget()
        editor_layout = QVBoxLayout(self._editor_panel)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(10)
        editor_layout.addWidget(_sub_title(self._t("budget.plan.title", "Plan anual por categoría")))
        self._budget_table_stack = QStackedWidget()
        self._budget_table = QTableWidget(0, 14)
        self._budget_table.setStyleSheet(_TABLE_STYLE)
        self._budget_table.setAlternatingRowColors(True)
        self._budget_table.setHorizontalHeaderLabels(
            [
                self._t("budget.table.category", "Categoría"),
                *self._month_labels(),
                self._t("budget.table.total", "Total anual"),
            ]
        )
        self._budget_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._budget_table.verticalHeader().setVisible(False)
        self._budget_table.setMinimumHeight(240)
        self._budget_table.cellChanged.connect(self._on_budget_cell_changed)
        self._budget_table_stack.addWidget(self._budget_table)

        self._budget_placeholder = self._build_budget_placeholder()
        self._budget_table_stack.addWidget(self._budget_placeholder)
        editor_layout.addWidget(self._budget_table_stack, 1)
        self._content_stack.addWidget(self._editor_panel)

        self._comparison_panel = QWidget()
        comparison_layout = QVBoxLayout(self._comparison_panel)
        comparison_layout.setContentsMargins(0, 0, 0, 0)
        comparison_layout.setSpacing(10)
        comparison_layout.addWidget(_sub_title(self._t("budget.compare", "Comparar con real")))

        self._comparison_hint = QLabel("")
        self._comparison_hint.setWordWrap(True)
        self._comparison_hint.setStyleSheet("font-size:11px;color:#9FB3C8;")
        comparison_layout.addWidget(self._comparison_hint)

        self._comparison_table = QTableWidget(0, 0)
        self._comparison_table.setStyleSheet(_TABLE_STYLE)
        self._comparison_table.setAlternatingRowColors(True)
        self._comparison_table.verticalHeader().setVisible(False)
        self._comparison_table.setItemDelegate(_SignalCellDelegate(self._comparison_table))
        comparison_layout.addWidget(self._comparison_table, 1)
        self._content_stack.addWidget(self._comparison_panel)

        self._monthly_tracking_panel, _tracking_content, tracking_layout = _build_scrollable_container(self)
        tracking_layout.addWidget(_sub_title(self._t("budget.monthly_tracking", "Seguimiento mensual presupuestario")))

        filters_row = QHBoxLayout()
        filters_row.setSpacing(8)
        filters_row.addWidget(QLabel(self._t("budget.month", "Mes")))
        self._tracking_month_combo = QComboBox()
        self._tracking_month_combo.setStyleSheet(_COMBO_STYLE)
        for month_idx, (key, fallback) in enumerate(self._MONTH_LABELS, start=1):
            self._tracking_month_combo.addItem(self._t(key, fallback), month_idx)
        filters_row.addWidget(self._tracking_month_combo)
        filters_row.addWidget(QLabel(self._t("budget.year", "Año")))
        self._tracking_year_spin = QSpinBox()
        self._tracking_year_spin.setRange(1900, 9999)
        self._tracking_year_spin.setStyleSheet(_COMBO_STYLE)
        filters_row.addWidget(self._tracking_year_spin)
        self._btn_run_monthly_tracking = _make_toolbar_btn(self._t("budget.run", "Ejecutar"))
        self._btn_run_monthly_tracking.clicked.connect(self._refresh_monthly_tracking)
        filters_row.addWidget(self._btn_run_monthly_tracking)
        filters_row.addStretch()
        tracking_layout.addLayout(filters_row)

        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)
        self._tracking_assigned_card = CardWidget(
            self._t("budget.monthly.assigned", "Total asignado"), "0.00", "#4D96FF"
        )
        self._tracking_executed_card = CardWidget(
            self._t("budget.monthly.executed", "Total ejecutado"), "0.00", "#F48771"
        )
        self._tracking_available_card = CardWidget(
            self._t("budget.monthly.available", "Total disponible"),
            "0.00",
            "#4EC9B0",
        )
        kpi_row.addWidget(self._tracking_assigned_card)
        kpi_row.addWidget(self._tracking_executed_card)
        kpi_row.addWidget(self._tracking_available_card)
        tracking_layout.addLayout(kpi_row)

        self._monthly_tracking_hint = QLabel("")
        self._monthly_tracking_hint.setWordWrap(True)
        self._monthly_tracking_hint.setStyleSheet("font-size:11px;color:#9FB3C8;")
        tracking_layout.addWidget(self._monthly_tracking_hint)

        self._monthly_tracking_table = QTableWidget(0, 5)
        self._monthly_tracking_table.setStyleSheet(_TABLE_STYLE)
        self._monthly_tracking_table.setAlternatingRowColors(True)
        self._monthly_tracking_table.verticalHeader().setVisible(False)
        self._monthly_tracking_table.setHorizontalHeaderLabels(
            [
                self._t("budget.table.category", "Categoría"),
                self._t("budget.monthly.assigned", "Total asignado"),
                self._t("budget.monthly.executed", "Total ejecutado"),
                self._t("budget.monthly.available", "Total disponible"),
                self._t("budget.status", "Estado"),
            ]
        )
        self._monthly_tracking_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tracking_layout.addWidget(self._monthly_tracking_table, 1)

        reassignment_row = QHBoxLayout()
        reassignment_row.setSpacing(8)
        reassignment_row.addWidget(QLabel(self._t("budget.reassign.source", "Categoría origen")))
        self._reassign_source_combo = QComboBox()
        self._reassign_source_combo.setStyleSheet(_COMBO_STYLE)
        self._reassign_source_combo.currentIndexChanged.connect(self._on_reassign_source_changed)
        reassignment_row.addWidget(self._reassign_source_combo, 1)
        self._reassign_available_lbl = QLabel(self._t("budget.reassign.available", "Disponible: 0.00"))
        reassignment_row.addWidget(self._reassign_available_lbl)
        reassignment_row.addWidget(QLabel(self._t("budget.reassign.target", "Categoría destino")))
        self._reassign_target_combo = QComboBox()
        self._reassign_target_combo.setStyleSheet(_COMBO_STYLE)
        reassignment_row.addWidget(self._reassign_target_combo, 1)
        reassignment_row.addWidget(QLabel(self._t("budget.reassign.amount", "Asignación")))
        self._reassign_amount_input = QLineEdit()
        self._reassign_amount_input.setPlaceholderText("0.00")
        self._reassign_amount_input.setFixedWidth(120)
        reassignment_row.addWidget(self._reassign_amount_input)
        self._btn_apply_reassign = _make_toolbar_btn(self._t("budget.reassign.apply", "Reasignar"))
        self._btn_apply_reassign.clicked.connect(self._on_apply_reassignment)
        reassignment_row.addWidget(self._btn_apply_reassign)
        tracking_layout.addLayout(reassignment_row)
        tracking_layout.addStretch()
        self._content_stack.addWidget(self._monthly_tracking_panel)

        layout.addWidget(self._content_stack, 1)
        current = date.today()
        self._tracking_month_combo.setCurrentIndex(current.month - 1)
        self._tracking_year_spin.setValue(current.year)
        self._set_budget_view_mode("editor")

    def _build_budget_placeholder(self) -> QWidget:
        placeholder = QWidget()
        layout = QVBoxLayout(placeholder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        table = QTableWidget(3, 14)
        table.setStyleSheet(_TABLE_STYLE)
        table.setAlternatingRowColors(True)
        table.setHorizontalHeaderLabels(
            [
                self._t("budget.table.category", "Categoría"),
                *self._month_labels(),
                self._t("budget.table.total", "Total anual"),
            ]
        )
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setMinimumHeight(240)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        placeholder_rows = [
            (self._t("budget.section.income", "Ingresos"), "#21332E", "#4EC9B0"),
            (self._t("budget.section.expense", "Gastos"), "#352826", "#F48771"),
            (self._t("budget.section.balance", "Balance"), "#223042", "#D6DEE8"),
        ]
        zero_amount = _fmt_amount(self._db, 0.0)
        for row_idx, (title, background, accent) in enumerate(placeholder_rows):
            title_item = self._make_text_item(title)
            title_font = title_item.font()
            title_font.setWeight(QFont.Weight.DemiBold)
            title_item.setFont(title_font)
            title_item.setForeground(QColor("#D6DEE8"))
            title_item.setBackground(QColor(background))
            table.setItem(row_idx, 0, title_item)

            for col_idx in range(1, table.columnCount()):
                amount_item = self._make_text_item(zero_amount)
                amount_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                amount_item.setForeground(QColor(accent if col_idx == table.columnCount() - 1 else "#9FB3C8"))
                amount_item.setBackground(QColor(background))
                table.setItem(row_idx, col_idx, amount_item)

        layout.addWidget(table)

        self._budget_placeholder_hint = QLabel(
            self._t(
                "budget.placeholder.hint",
                "No hay presupuestos creados todavía. Crea uno nuevo con código, año y moneda. "
                "Cuando lo guardes, esta tabla se llenará con las 12 columnas mensuales y el total anual.",
            )
        )
        self._budget_placeholder_hint.setWordWrap(True)
        self._budget_placeholder_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._budget_placeholder_hint.setStyleSheet(
            "font-size:12px;color:#B7C3D0;padding:18px;border:1px solid palette(mid);border-radius:8px;"
        )
        layout.addWidget(self._budget_placeholder_hint)
        return placeholder

    def open_create_dialog(self) -> None:
        from mira.ui.dialogs import BudgetCreateDialog

        dlg = BudgetCreateDialog(self._db, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        try:
            budget = self._db.budget.create(data["code"], int(data["year"]), data["currency"])
        except DuplicateBudgetCodeError:
            _notify_warning(
                self,
                self._t("budget.dialog.title", "Presupuestos"),
                self._t("budget.validation.duplicate_code", "Ya existe un presupuesto con ese código."),
            )
            return
        except (BudgetError, ValueError) as exc:
            _notify_warning(self, self._t("budget.dialog.title", "Presupuestos"), str(exc))
            return
        self._current_budget_id = int(budget["id"])
        self._budget_list_dirty = True
        self.refresh()
        self._load_budget()

    def _format_budget_amount(self, amount: float, currency: str) -> str:
        return f"{currency} {_fmt_amount(self._db, amount)}"

    def _make_text_item(self, text: str, *, editable: bool = False, user_data: int | None = None) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if editable:
            flags |= Qt.ItemFlag.ItemIsEditable
        item.setFlags(flags)
        if user_data is not None:
            item.setData(Qt.ItemDataRole.UserRole, user_data)
        return item

    def _make_amount_item(self, amount: float, *, editable: bool = False, color: str | None = None) -> QTableWidgetItem:
        item = self._make_text_item(_fmt_amount(self._db, amount), editable=editable)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        item.setData(_BUDGET_AMOUNT_ROLE, float(amount))
        if color:
            font = item.font()
            font.setWeight(QFont.Weight.DemiBold)
            item.setFont(font)
        return item

    def _restore_budget_cell_after_invalid_input(self, row: int, column: int, message: str) -> None:
        self._load_budget()
        self._set_budget_status(message, color="#F7C16B")
        restored_item = self._budget_table.item(row, column)
        if restored_item is None:
            return
        restored_item.setToolTip(message)
        self._budget_table.setCurrentCell(row, column)
        index = self._budget_table.model().index(row, column)
        if index.isValid():
            self._budget_table.scrollTo(index)

    def _style_row(self, row: int, color: str) -> None:
        for col in range(self._budget_table.columnCount()):
            item = self._budget_table.item(row, col)
            if item is None:
                continue
            item.setBackground(QColor(color))

    def _style_comparison_row(self, row: int, color: str) -> None:
        for col in range(self._comparison_table.columnCount()):
            item = self._comparison_table.item(row, col)
            if item is None:
                continue
            item.setBackground(QColor(color))

    def _apply_signal_highlight(self, item, signal=None):
        if item is None or signal is None:
            return
        item.setData(_SIGNAL_CELL_ROLE, signal)
        font = item.font()
        font.setWeight(QFont.Weight.DemiBold)
        item.setFont(font)

    def _comparison_signal_color(self, section: str, variance: float) -> str:
        if abs(variance) < 0.005:
            return "neutral"
        if section == "income":
            return "positive" if variance > 0 else "negative"
        if section == "expense":
            return "negative" if variance > 0 else "positive"
        return "positive" if variance > 0 else "negative"

    def _selected_budget(self) -> dict | None:
        if self._current_budget_id is None:
            return None
        cached = self._selected_budget_from_cache()
        if cached is not None:
            return cached
        return self._db.budget.get(self._current_budget_id)

    def _on_budget_changed(self, index: int) -> None:
        budget_id = self._budget_combo.itemData(index)
        if budget_id is None:
            self._current_budget_id = None
            self._set_budget_enabled(False)
            self._mark_budget_pending()
            return
        self._current_budget_id = int(budget_id)
        budget = self._db.budget.get(self._current_budget_id)
        if budget is not None:
            self._db.setting.set("active_budget_code", str(budget["code"]))
            self._sync_tracking_year_with_budget(budget)
        if self._loaded_budget_id == self._current_budget_id:
            self._set_budget_enabled(True)
            self._set_budget_status(
                self._t(
                    "budget.status.loaded",
                    "Mostrando el último presupuesto cargado. Usa los botones para consultar comparativos o seguimiento.",
                ),
                color="#4EC9B0",
            )
            return
        if self._btn_compare.isChecked():
            self._refresh_comparison()
            return
        if self._btn_monthly_tracking.isChecked():
            self._refresh_monthly_tracking()
            return
        self._mark_budget_pending()

    def _set_budget_enabled(self, enabled: bool) -> None:
        self._budget_combo.setEnabled(enabled)
        self._budget_table_stack.setCurrentWidget(
            self._budget_table
            if enabled and self._loaded_budget_id == self._current_budget_id
            else self._budget_placeholder
        )
        self._btn_load_budget.setEnabled(enabled)
        self._btn_delete.setEnabled(enabled)
        self._btn_set_default.setEnabled(enabled)
        self._btn_propose.setEnabled(enabled)
        self._btn_compare.setEnabled(enabled)
        self._btn_monthly_tracking.setEnabled(enabled)
        self._warning_lbl.setVisible(enabled)
        mode = "editor"
        if enabled and self._btn_compare.isChecked():
            mode = "comparison"
        elif enabled and self._btn_monthly_tracking.isChecked():
            mode = "monthly_tracking"
        self._set_budget_view_mode(mode)

    def _set_budget_view_mode(self, mode: str) -> None:
        is_compare = mode == "comparison"
        is_tracking = mode == "monthly_tracking"
        self._btn_compare.setChecked(is_compare)
        self._btn_monthly_tracking.setChecked(is_tracking)
        self._btn_compare.setText(
            self._t("budget.compare.hide", "Ocultar comparación")
            if is_compare
            else self._t("budget.compare", "Comparar con real")
        )
        self._btn_monthly_tracking.setText(
            self._t("budget.monthly_tracking.hide", "Ocultar seguimiento mensual")
            if is_tracking
            else self._t("budget.monthly_tracking", "Seguimiento mensual presupuestario")
        )
        self._granularity_label.setVisible(is_compare)
        self._granularity_combo.setVisible(is_compare)
        self._granularity_combo.setEnabled(is_compare)
        self._btn_export_excel.setVisible(is_compare)
        self._btn_export_excel.setEnabled(is_compare and self._current_budget_id is not None)
        if is_compare:
            self._content_stack.setCurrentWidget(self._comparison_panel)
        elif is_tracking:
            self._content_stack.setCurrentWidget(self._monthly_tracking_panel)
        else:
            self._content_stack.setCurrentWidget(self._editor_panel)

    def _sync_tracking_year_with_budget(self, budget: dict[str, Any] | None) -> None:
        if budget is None:
            return
        budget_year = int(budget["year"])
        if int(self._tracking_year_spin.value()) != budget_year:
            self._tracking_year_spin.setValue(budget_year)

    def _load_budget(self) -> None:
        budget = self._selected_budget()
        if budget is None:
            return
        self._sync_tracking_year_with_budget(budget)

        matrix = self._db.budget.get_matrix(int(budget["id"]))
        totals = cast(dict[str, Any], matrix["totals"])
        currency = str(budget["currency"])
        income_total = float(totals["income_annual"])
        expense_total = float(totals["expense_annual"])
        balance_total = float(totals["balance_annual"])

        self._income_card.set_value(self._format_budget_amount(income_total, currency))
        self._expense_card.set_value(self._format_budget_amount(expense_total, currency))
        self._balance_card.set_value(self._format_budget_amount(balance_total, currency))
        self._balance_card.set_color("#4EC9B0" if balance_total >= 0 else "#F48771")
        self._warning_lbl.setText(
            self._t(
                "budget.warning.deficit",
                "Precaución: los gastos superan los ingresos esperados. Esto no bloquea el presupuesto y puede representar ahorro o deuda.",
            )
            if expense_total > income_total
            else ""
        )
        self._populate_budget_table(matrix)
        self._loaded_budget_id = self._current_budget_id
        self._current_monthly_tracking = None
        self._budget_table_stack.setCurrentWidget(self._budget_table)
        self._comparison_hint.setText(
            self._t(
                "budget.compare.pending",
                "Pulsa 'Comparar con real' para consultar el comparativo del presupuesto seleccionado.",
            )
        )
        self._monthly_tracking_hint.setText(
            self._t(
                "budget.monthly.pending",
                "Pulsa 'Ejecutar' para consultar la ejecución mensual del presupuesto seleccionado.",
            )
        )
        self._set_budget_status(
            self._t(
                "budget.status.loaded",
                "Presupuesto cargado. Ahora puedes consultar comparativos o seguimiento sin bloquear la navegación al entrar.",
            ),
            color="#4EC9B0",
        )

    def _populate_budget_table(self, matrix: dict[str, Any]) -> None:
        rows = list(matrix["rows"])
        incomes = [row for row in rows if row["type"] == "income"]
        expenses = [row for row in rows if row["type"] == "expense"]
        totals = dict(matrix["totals"])
        structure = [
            ("section", self._t("budget.section.income", "Ingresos")),
            *[("category", row) for row in incomes],
            ("total_income", None),
            ("section", self._t("budget.section.expense", "Gastos")),
            *[("category", row) for row in expenses],
            ("total_expense", None),
            ("balance", None),
        ]

        self._loading_budget_table = True
        self._budget_table.blockSignals(True)
        self._budget_table.clearContents()
        self._budget_table.setRowCount(len(structure))

        for row_idx, (kind, payload) in enumerate(structure):
            if kind == "section":
                label_item = self._make_text_item(str(payload))
                label_item.setForeground(QColor("#D6DEE8"))
                self._budget_table.setItem(row_idx, 0, label_item)
                for col in range(1, self._budget_table.columnCount()):
                    self._budget_table.setItem(row_idx, col, self._make_text_item(""))
                self._style_row(row_idx, "#263140")
                continue

            if kind == "category":
                category = dict(payload)
                self._budget_table.setItem(
                    row_idx,
                    0,
                    self._make_text_item(str(category["name"]), user_data=int(category["category_id"])),
                )
                for month_idx, amount in enumerate(list(category["months"]), start=1):
                    self._budget_table.setItem(
                        row_idx,
                        month_idx,
                        self._make_amount_item(float(amount), editable=True),
                    )
                self._budget_table.setItem(row_idx, 13, self._make_amount_item(float(category["annual_total"])))
                continue

            if kind == "total_income":
                self._budget_table.setItem(
                    row_idx,
                    0,
                    self._make_text_item(self._t("budget.total.income", "Subtotal ingresos")),
                )
                for month_idx, amount in enumerate(list(totals["income"]), start=1):
                    self._budget_table.setItem(
                        row_idx,
                        month_idx,
                        self._make_amount_item(float(amount), color="#4EC9B0"),
                    )
                self._budget_table.setItem(
                    row_idx,
                    13,
                    self._make_amount_item(float(totals["income_annual"]), color="#4EC9B0"),
                )
                self._style_row(row_idx, "#21332E")
                continue

            if kind == "total_expense":
                self._budget_table.setItem(
                    row_idx,
                    0,
                    self._make_text_item(self._t("budget.total.expense", "Subtotal gastos")),
                )
                for month_idx, amount in enumerate(list(totals["expense"]), start=1):
                    self._budget_table.setItem(
                        row_idx,
                        month_idx,
                        self._make_amount_item(float(amount), color="#F48771"),
                    )
                self._budget_table.setItem(
                    row_idx,
                    13,
                    self._make_amount_item(float(totals["expense_annual"]), color="#F48771"),
                )
                self._style_row(row_idx, "#352826")
                continue

            self._budget_table.setItem(
                row_idx,
                0,
                self._make_text_item(self._t("budget.section.balance", "Balance")),
            )
            for month_idx, amount in enumerate(list(totals["balance"]), start=1):
                color = "#4EC9B0" if float(amount) >= 0 else "#F48771"
                self._budget_table.setItem(
                    row_idx,
                    month_idx,
                    self._make_amount_item(float(amount), color=color),
                )
            annual_balance = float(totals["balance_annual"])
            balance_color = "#4EC9B0" if annual_balance >= 0 else "#F48771"
            self._budget_table.setItem(row_idx, 13, self._make_amount_item(annual_balance, color=balance_color))
            self._style_row(row_idx, "#223042")

        self._budget_table.blockSignals(False)
        self._loading_budget_table = False

    def _on_budget_cell_changed(self, row: int, column: int) -> None:
        if self._loading_budget_table or self._current_budget_id is None or column < 1 or column > 12:
            return
        category_item = self._budget_table.item(row, 0)
        value_item = self._budget_table.item(row, column)
        if category_item is None or value_item is None:
            return
        category_id = category_item.data(Qt.ItemDataRole.UserRole)
        if category_id is None:
            return
        raw_value = value_item.text().strip()
        if not raw_value:
            amount = 0.0
        else:
            try:
                amount = process_budget_value(
                    raw_value,
                    number_format=get_number_format_config(self._db.setting),
                )
            except ValueError as exc:
                message = str(exc)
                _notify_warning(
                    self,
                    self._t("budget.dialog.title", "Presupuestos"),
                    message,
                )
                self._restore_budget_cell_after_invalid_input(row, column, message)
                return
        previous_amount = value_item.data(_BUDGET_AMOUNT_ROLE)
        if previous_amount is not None and abs(float(previous_amount) - amount) < 1e-9:
            return
        budget = self._selected_budget()
        if budget is None:
            return
        self._db.budget.upsert_amount(
            self._current_budget_id,
            int(category_id),
            int(budget["year"]),
            column,
            amount,
        )
        self._load_budget()

    def _on_propose_budget(self) -> None:
        if self._current_budget_id is None:
            return
        if self._db.budget.has_values(self._current_budget_id):
            reply = QMessageBox.question(
                self,
                self._t("budget.dialog.title", "Presupuestos"),
                self._t(
                    "budget.propose.confirm_replace",
                    "Este presupuesto ya tiene montos. ¿Deseas reemplazarlos con la propuesta inicial?",
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        result = self._db.budget.propose(self._current_budget_id)
        if not result.get("applied"):
            _notify_info(
                self,
                self._t("budget.dialog.title", "Presupuestos"),
                str(result.get("reason") or self._t("budget.propose.failed", "No se pudo proponer un presupuesto.")),
            )
            return
        _notify_info(
            self,
            self._t("budget.dialog.title", "Presupuestos"),
            self._t(
                "budget.propose.success",
                "Se cargó una propuesta inicial usando el promedio mensual del año {year}.",
                params={"year": result["source_year"]},
            ),
        )
        self._load_budget()

    def _on_delete_budget(self) -> None:
        budget = self._selected_budget()
        if budget is None:
            return
        reply = QMessageBox.question(
            self,
            self._t("budget.dialog.title", "Presupuestos"),
            self._t(
                "budget.delete.confirm",
                "¿Eliminar el presupuesto '{code}'?",
                params={"code": budget["code"]},
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._db.budget.delete(int(budget["id"]))
        self._current_budget_id = None
        self._budget_list_dirty = True
        self.refresh()

    def _on_set_default_budget(self) -> None:
        budget = self._selected_budget()
        if budget is None:
            return
        try:
            self._db.budget.set_default_for_year(int(budget["id"]))
        except ValueError as exc:
            _notify_warning(self, self._t("budget.dialog.title", "Presupuestos"), str(exc))
            return
        _notify_info(
            self,
            self._t("budget.dialog.title", "Presupuestos"),
            self._t(
                "budget.set_default.success",
                "'{code}' quedó como presupuesto predeterminado del año {year}.",
                params={"code": budget["code"], "year": budget["year"]},
            ),
        )
        self._budget_list_dirty = True
        self.refresh()

    def _on_toggle_compare(self) -> None:
        showing = self._btn_compare.isChecked()
        self._set_budget_view_mode("comparison" if showing else "editor")
        if showing:
            self._refresh_comparison()

    def _on_toggle_monthly_tracking(self) -> None:
        showing = self._btn_monthly_tracking.isChecked()
        self._set_budget_view_mode("monthly_tracking" if showing else "editor")
        if showing:
            self._sync_tracking_year_with_budget(self._selected_budget())
            self._refresh_monthly_tracking()

    def _on_export_comparison_excel(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        budget = self._selected_budget()
        if budget is None or self._current_budget_id is None:
            return

        granularity = str(self._granularity_combo.currentData() or "quarterly")
        code = str(budget["code"]).replace(" ", "_")
        default_name = self._t(
            "budget.export.default_name",
            "real-vs-ppto-{code}-{year}-{granularity}.xlsx",
            params={"code": code, "year": budget["year"], "granularity": granularity},
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            self._t("budget.export.dialog.title", "Exportar comparación a Excel"),
            default_name,
            self._t("budget.export.file_filter", "Excel Files (*.xlsx);;All Files (*)"),
        )
        if not path:
            return
        try:
            exported_rows = self._db.budget.export_comparison_excel(
                path,
                self._current_budget_id,
                granularity=granularity,
            )
            _notify_info(
                self,
                self._t("budget.export.success.title", "Exportación completada"),
                self._t(
                    "budget.export.success.body",
                    "Se exportaron {rows} fila(s) del comparativo a:\n{path}",
                    params={"rows": exported_rows, "path": path},
                ),
            )
        except Exception as exc:  # noqa: BLE001
            _notify_error(
                self,
                self._t("budget.export.error.title", "Error de exportación"),
                self._t(
                    "budget.export.error.body",
                    "No se pudo exportar el Excel:\n{error}",
                    params={"error": exc},
                ),
            )

    def _refresh_comparison(self) -> None:
        if not self._btn_compare.isChecked() or self._current_budget_id is None:
            return
        granularity = str(self._granularity_combo.currentData() or "quarterly")
        comparison = self._db.budget.compare(self._current_budget_id, granularity=granularity)
        excluded = int(cast(Any, comparison["excluded_transactions"]))
        excluded_msg = (
            self._t(
                "budget.compare.excluded",
                " Se excluyeron {count} transacciones porque su moneda no coincide con la moneda del presupuesto.",
                params={"count": excluded},
            )
            if excluded > 0
            else ""
        )
        self._comparison_hint.setText(
            self._t(
                "budget.compare.hint",
                "Variación = Real - PPTO para ingresos y gastos. Vista actual: {view}.{excluded}",
                params={"view": self._granularity_combo.currentText(), "excluded": excluded_msg},
            )
        )
        self._populate_comparison_table(comparison)
        self._set_budget_status(
            self._t("budget.compare.loaded", "Comparativo cargado para el presupuesto seleccionado."),
            color="#4EC9B0",
        )

    def _tracking_status_meta(self, status: str) -> tuple[str, str]:
        if status == "over":
            return (self._t("budget.monthly.status.over", "Sobregiro"), "#E06C75")
        if status == "matched":
            return (self._t("budget.monthly.status.matched", "Ejecutado exacto"), "#D6DEE8")
        return (self._t("budget.monthly.status.available", "Saldo disponible"), "#4EC9B0")

    def _refresh_monthly_tracking(self) -> None:
        if not self._btn_monthly_tracking.isChecked() or self._current_budget_id is None:
            return
        year = int(self._tracking_year_spin.value())
        month = int(self._tracking_month_combo.currentData() or date.today().month)
        try:
            tracking = self._db.budget.get_monthly_tracking(self._current_budget_id, year, month)
        except ValueError as exc:
            self._current_monthly_tracking = None
            self._monthly_tracking_hint.setText(str(exc))
            self._monthly_tracking_table.setRowCount(0)
            self._reassign_source_combo.clear()
            self._reassign_target_combo.clear()
            self._tracking_assigned_card.set_value("0.00")
            self._tracking_executed_card.set_value("0.00")
            self._tracking_available_card.set_value("0.00")
            return
        self._populate_monthly_tracking(tracking)
        self._set_budget_status(
            self._t("budget.monthly.loaded", "Seguimiento mensual cargado para el presupuesto seleccionado."),
            color="#4EC9B0",
        )

    def _populate_monthly_tracking(self, tracking: dict[str, Any]) -> None:
        self._current_monthly_tracking = tracking
        budget = cast(dict[str, Any], tracking["budget"])
        totals = cast(dict[str, Any], tracking["totals"])
        validations = cast(dict[str, Any], tracking["validations"])
        rows = cast(list[dict[str, Any]], tracking["rows"])
        excluded = int(cast(Any, tracking["excluded_transactions"]))

        currency = str(budget["currency"])
        self._tracking_assigned_card.set_value(self._format_budget_amount(float(totals["assigned"]), currency))
        self._tracking_executed_card.set_value(self._format_budget_amount(float(totals["executed"]), currency))
        self._tracking_available_card.set_value(self._format_budget_amount(float(totals["available"]), currency))
        self._tracking_available_card.set_color("#4EC9B0" if float(totals["available"]) >= 0 else "#F48771")

        notes: list[str] = []
        if not bool(validations.get("has_defined_budget")):
            notes.append(
                self._t(
                    "budget.monthly.validation.missing",
                    "No existe presupuesto mensual asignado para categorías de gasto en el período seleccionado.",
                )
            )
        if bool(validations.get("is_partial_budget")):
            notes.append(
                self._t(
                    "budget.monthly.validation.partial",
                    "El presupuesto mensual está incompleto. Se muestran categorías con asignación y/o ejecución.",
                )
            )
        if excluded > 0:
            notes.append(
                self._t(
                    "budget.compare.excluded",
                    "Se excluyeron {count} transacciones porque su moneda no coincide con la moneda del presupuesto.",
                    params={"count": excluded},
                )
            )
        self._monthly_tracking_hint.setText(" ".join(notes))

        self._monthly_tracking_table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            self._monthly_tracking_table.setItem(row_idx, 0, self._make_text_item(str(row["name"])))
            self._monthly_tracking_table.setItem(row_idx, 1, self._make_amount_item(float(row["assigned"])))
            self._monthly_tracking_table.setItem(row_idx, 2, self._make_amount_item(float(row["executed"])))
            available = float(row["available"])
            available_item = self._make_amount_item(available, color="#4EC9B0" if available >= 0 else "#F48771")
            self._monthly_tracking_table.setItem(row_idx, 3, available_item)
            status_label, status_color = self._tracking_status_meta(str(row["status"]))
            status_item = self._make_text_item(status_label)
            status_item.setForeground(QColor(status_color))
            self._monthly_tracking_table.setItem(row_idx, 4, status_item)

        self._reassign_source_combo.blockSignals(True)
        self._reassign_source_combo.clear()
        for row in rows:
            if float(row["available"]) > 0:
                self._reassign_source_combo.addItem(str(row["name"]), int(row["category_id"]))
        self._reassign_source_combo.blockSignals(False)

        self._reassign_target_combo.clear()
        for row in rows:
            self._reassign_target_combo.addItem(str(row["name"]), int(row["category_id"]))
        self._on_reassign_source_changed()

        can_reassign = bool(validations.get("has_defined_budget")) and self._reassign_source_combo.count() > 0
        self._btn_apply_reassign.setEnabled(can_reassign)

    def _on_reassign_source_changed(self) -> None:
        if self._current_budget_id is None or self._current_monthly_tracking is None:
            return
        if self._reassign_source_combo.count() <= 0:
            self._reassign_available_lbl.setText(self._t("budget.reassign.available", "Disponible: 0.00"))
            return
        source_category_id = self._reassign_source_combo.currentData()
        if source_category_id is None:
            self._reassign_available_lbl.setText(self._t("budget.reassign.available", "Disponible: 0.00"))
            return
        source_row = next(
            (
                row
                for row in cast(list[dict[str, Any]], self._current_monthly_tracking["rows"])
                if int(row["category_id"]) == int(source_category_id)
            ),
            None,
        )
        if source_row is None:
            self._reassign_available_lbl.setText(self._t("budget.reassign.available", "Disponible: 0.00"))
            return
        budget = cast(dict[str, Any], self._current_monthly_tracking["budget"])
        available_text = self._format_budget_amount(float(source_row["available"]), str(budget["currency"]))
        self._reassign_available_lbl.setText(
            self._t(
                "budget.reassign.available",
                "Disponible: {amount}",
                params={"amount": available_text},
            )
        )

    def _on_apply_reassignment(self) -> None:
        if self._current_budget_id is None:
            return
        source_category_id = self._reassign_source_combo.currentData()
        target_category_id = self._reassign_target_combo.currentData()
        if source_category_id is None or target_category_id is None:
            return
        try:
            amount = parse_number(
                self._reassign_amount_input.text().strip(),
                get_number_format_config(self._db.setting),
            )
        except ValueError:
            _notify_warning(
                self,
                self._t("budget.dialog.title", "Presupuestos"),
                self._t("budget.validation.amount", "Ingresa un monto válido."),
            )
            return

        year = int(self._tracking_year_spin.value())
        month = int(self._tracking_month_combo.currentData() or date.today().month)
        try:
            self._db.budget.reassign_monthly(
                self._current_budget_id,
                year,
                month,
                int(source_category_id),
                int(target_category_id),
                float(amount),
            )
        except ValueError as exc:
            _notify_warning(self, self._t("budget.dialog.title", "Presupuestos"), str(exc))
            return

        self._reassign_amount_input.clear()
        self._load_budget()
        self._refresh_monthly_tracking()

    def _populate_comparison_table(self, comparison: dict[str, Any]) -> None:
        periods = list(comparison["periods"])
        headers = [self._t("budget.table.category", "Categoría")]
        for period in periods:
            label = str(period["label"])
            headers.extend(
                [
                    self._t("budget.compare.header.real", "{label} Real", params={"label": label}),
                    self._t("budget.compare.header.budget", "{label} PPTO", params={"label": label}),
                    self._t("budget.compare.header.variance", "{label} Var", params={"label": label}),
                ]
            )
        headers.extend(
            [
                self._t("budget.compare.header.year_real", "Año Real"),
                self._t("budget.compare.header.year_budget", "Año PPTO"),
                self._t("budget.compare.header.year_variance", "Año Var"),
            ]
        )

        rows = list(comparison["rows"])
        incomes = [row for row in rows if row["type"] == "income"]
        expenses = [row for row in rows if row["type"] == "expense"]
        totals = dict(comparison["totals"])
        structure = [
            ("section", self._t("budget.section.income", "Ingresos")),
            *[("category", row) for row in incomes],
            ("total_income", None),
            ("section", self._t("budget.section.expense", "Gastos")),
            *[("category", row) for row in expenses],
            ("total_expense", None),
            ("balance", None),
        ]

        self._comparison_table.clear()
        self._comparison_table.setColumnCount(len(headers))
        self._comparison_table.setHorizontalHeaderLabels(headers)
        self._comparison_table.setRowCount(len(structure))
        self._comparison_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        for row_idx, (kind, payload) in enumerate(structure):
            if kind == "section":
                self._comparison_table.setItem(row_idx, 0, self._make_text_item(str(payload)))
                for col in range(1, self._comparison_table.columnCount()):
                    self._comparison_table.setItem(row_idx, col, self._make_text_item(""))
                self._style_comparison_row(row_idx, "#263140")
                continue

            if kind == "category":
                category = dict(payload)
                section = str(category["type"])
                self._comparison_table.setItem(row_idx, 0, self._make_text_item(str(category["name"])))
                col_idx = 1
                for period in list(category["periods"]):
                    variance = float(period["variance"])
                    signal_color = self._comparison_signal_color(section, variance)
                    real_item = self._make_amount_item(float(period["real"]))
                    budget_item = self._make_amount_item(float(period["budget"]))
                    variance_item = self._make_amount_item(variance, color=signal_color)
                    self._apply_signal_highlight(variance_item, signal_color)
                    self._comparison_table.setItem(row_idx, col_idx, real_item)
                    self._comparison_table.setItem(row_idx, col_idx + 1, budget_item)
                    self._comparison_table.setItem(row_idx, col_idx + 2, variance_item)
                    col_idx += 3
                annual_variance = float(category["annual_variance"])
                annual_color = self._comparison_signal_color(section, annual_variance)
                annual_real_item = self._make_amount_item(float(category["annual_real"]))
                annual_budget_item = self._make_amount_item(float(category["annual_budget"]))
                annual_variance_item = self._make_amount_item(annual_variance, color=annual_color)
                self._apply_signal_highlight(annual_variance_item, annual_color)
                self._comparison_table.setItem(row_idx, col_idx, annual_real_item)
                self._comparison_table.setItem(row_idx, col_idx + 1, annual_budget_item)
                self._comparison_table.setItem(row_idx, col_idx + 2, annual_variance_item)
                continue

            total_key = "income" if kind == "total_income" else "expense" if kind == "total_expense" else "balance"
            title = (
                self._t("budget.total.income", "Subtotal ingresos")
                if kind == "total_income"
                else (
                    self._t("budget.total.expense", "Subtotal gastos")
                    if kind == "total_expense"
                    else self._t("budget.section.balance", "Balance")
                )
            )
            period_totals = list(totals[total_key])
            annual_totals = dict(totals[f"{total_key}_annual"])
            self._comparison_table.setItem(row_idx, 0, self._make_text_item(title))
            col_idx = 1
            for period in period_totals:
                variance = float(period["variance"])
                signal_color = self._comparison_signal_color(total_key, variance)
                real_item = self._make_amount_item(float(period["real"]))
                budget_item = self._make_amount_item(float(period["budget"]))
                variance_item = self._make_amount_item(variance, color=signal_color)
                self._apply_signal_highlight(variance_item, signal_color)
                self._comparison_table.setItem(row_idx, col_idx, real_item)
                self._comparison_table.setItem(row_idx, col_idx + 1, budget_item)
                self._comparison_table.setItem(row_idx, col_idx + 2, variance_item)
                col_idx += 3
            annual_variance = float(annual_totals["variance"])
            annual_color = self._comparison_signal_color(total_key, annual_variance)
            annual_real_item = self._make_amount_item(float(annual_totals["real"]))
            annual_budget_item = self._make_amount_item(float(annual_totals["budget"]))
            annual_variance_item = self._make_amount_item(annual_variance, color=annual_color)
            self._comparison_table.setItem(row_idx, col_idx, annual_real_item)
            self._comparison_table.setItem(row_idx, col_idx + 1, annual_budget_item)
            self._comparison_table.setItem(row_idx, col_idx + 2, annual_variance_item)
            if kind == "total_income":
                self._style_comparison_row(row_idx, "#21332E")
            elif kind == "total_expense":
                self._style_comparison_row(row_idx, "#352826")
            else:
                self._style_comparison_row(row_idx, "#223042")
            for signal_col in range(1, col_idx, 3):
                self._apply_signal_highlight(
                    self._comparison_table.item(row_idx, signal_col + 2),
                    self._comparison_signal_color(
                        total_key,
                        float(period_totals[(signal_col - 1) // 3]["variance"]),
                    ),
                )
            self._apply_signal_highlight(self._comparison_table.item(row_idx, col_idx + 2), annual_color)

    def refresh(self) -> None:
        budgets = self._load_budget_list()
        self._apply_budget_selection_state(budgets)

    def _load_budget_list(self) -> list[dict[str, Any]]:
        if self._budget_list_dirty or not self._budget_list_cache:
            self._budget_list_cache = self._db.budget.list()
            self._budget_list_dirty = False
            self._budget_combo.blockSignals(True)
            self._budget_combo.clear()
            for budget in self._budget_list_cache:
                label = f"{budget['code']} | {budget['year']} | {budget['currency']}"
                if int(budget.get("is_default_year") or 0) == 1:
                    label = f"★ {label}"
                self._budget_combo.addItem(label, int(budget["id"]))
            self._budget_combo.blockSignals(False)

        return list(self._budget_list_cache)

    def _apply_budget_selection_state(self, budgets: list[dict[str, Any]]) -> None:
        has_budgets = bool(budgets)
        self._set_budget_enabled(has_budgets)
        if not has_budgets:
            self._current_budget_id = None
            self._loaded_budget_id = None
            self._current_monthly_tracking = None
            self._set_budget_view_mode("editor")
            self._clear_budget_outputs()
            self._set_budget_placeholder_hint(
                self._t(
                    "budget.placeholder.hint",
                    "No hay presupuestos creados todavía. Crea uno nuevo con código, año y moneda. "
                    "Cuando lo guardes, esta tabla se llenará con las 12 columnas mensuales y el total anual.",
                )
            )
            self._set_budget_status(self._t("budget.status.empty", "Crea un presupuesto para comenzar."))
            return

        available_ids = [int(budget["id"]) for budget in budgets]
        if self._current_budget_id not in available_ids:
            current_year_default = self._db.budget.get_default_for_year(date.today().year)
            active_code = (self._db.setting.get("active_budget_code") or "").strip()
            active = next(
                (
                    budget
                    for budget in budgets
                    if current_year_default is not None and int(budget["id"]) == int(current_year_default["id"])
                ),
                next(
                    (budget for budget in budgets if str(budget["code"]) == active_code),
                    budgets[0],
                ),
            )
            self._current_budget_id = int(active["id"])

        selected_index = self._budget_combo.findData(self._current_budget_id)
        if selected_index >= 0:
            self._budget_combo.blockSignals(True)
            self._budget_combo.setCurrentIndex(selected_index)
            self._budget_combo.blockSignals(False)
        budget = self._selected_budget()
        if budget is not None:
            self._db.setting.set("active_budget_code", str(budget["code"]))
            self._sync_tracking_year_with_budget(budget)
        if self._loaded_budget_id != self._current_budget_id:
            self._mark_budget_pending()
            return
        self._set_budget_enabled(True)
        self._set_budget_status(
            self._t(
                "budget.status.loaded",
                "Mostrando el último presupuesto cargado. Recarga solo si necesitas consultar nuevos datos.",
            ),
            color="#4EC9B0",
        )


# ---------------------------------------------------------------------------
# CategoriesView
# ---------------------------------------------------------------------------
