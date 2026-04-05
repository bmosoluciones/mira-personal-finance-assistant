# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Savings goals feature view."""

from __future__ import annotations


from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QFont, QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from mira.app.view_services import SavingsGoalsViewService, SavingsGoalsViewState
from mira.db.database import Database
from mira.ui.views._shared import (
    _fmt_amount,
    _make_toolbar_btn,
    _notify_info,
    _notify_warning,
    _section_title,
    _tr_db,
)


class _GoalCard(QFrame):
    """A styled card for savings goals that emits the goal id when clicked."""

    clicked = Signal(int)  # emits the goal id
    activated = Signal(int)  # emits the goal id on double-click
    context_requested = Signal(int, QPoint)  # emits goal id and local/global click point

    def __init__(self, goal_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._goal_id = goal_id
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        self.clicked.emit(self._goal_id)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        self.activated.emit(self._goal_id)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:  # type: ignore[override]
        self.context_requested.emit(self._goal_id, event.globalPos())
        event.accept()


class SavingsGoalsView(QWidget):
    """Savings goals management view with progress bars and CRUD."""

    def __init__(
        self,
        db: Database,
        parent: QWidget | None = None,
        service: SavingsGoalsViewService | None = None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._service = service or SavingsGoalsViewService(db)
        self._goals: list[dict] = []
        self._selected_id: int | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        layout.addWidget(_section_title(_tr_db(self._db, "goals.title", "🎯 Savings Goals")))

        hint = QLabel(
            _tr_db(
                self._db,
                "goals.hint",
                "Define saving goals with a target amount and date. Use 'Contribute' to track deposits toward each goal.",
            )
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size:10px;padding:2px 0 4px 0;")
        layout.addWidget(hint)

        # Toolbar
        tb = QHBoxLayout()
        self._btn_add = _make_toolbar_btn(_tr_db(self._db, "btn.add_goal", "+ Add Goal"))
        self._btn_edit = _make_toolbar_btn(_tr_db(self._db, "btn.edit", "✏ Edit"))
        self._btn_contribute = _make_toolbar_btn(_tr_db(self._db, "btn.contribute", "💰 Contribute"))
        self._btn_delete = _make_toolbar_btn(_tr_db(self._db, "btn.delete", "🗑 Delete"))
        for btn in [
            self._btn_add,
            self._btn_edit,
            self._btn_contribute,
            self._btn_delete,
        ]:
            tb.addWidget(btn)
        tb.addStretch()
        layout.addLayout(tb)

        # Scrollable cards area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        self._cards_container = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._cards_layout.setSpacing(8)
        scroll.setWidget(self._cards_container)
        layout.addWidget(scroll, 1)

        self._btn_add.clicked.connect(self._on_add)
        self._btn_edit.clicked.connect(self._on_edit)
        self._btn_contribute.clicked.connect(self._on_contribute)
        self._btn_delete.clicked.connect(self._on_delete)

    def _on_add(self, prefill: dict | None = None) -> None:
        from mira.ui.dialogs import SavingsGoalDialog

        dlg = SavingsGoalDialog(self._db, prefill=prefill, parent=self)
        if dlg.exec() == SavingsGoalDialog.DialogCode.Accepted:
            data = dlg.get_data()
            try:
                feedback = self._service.create(
                    name=data["name"],
                    target_amount=data["target_amount"],
                    target_date=data["target_date"],
                )
            except ValueError as exc:
                _notify_warning(self, _tr_db(self._db, "validation.title", "Validation"), str(exc))
                return
            self._selected_id = feedback.selected_id
            self.refresh()

    def _on_contribute(self) -> None:
        from mira.ui.dialogs import ContributeGoalDialog

        goal = next((g for g in self._goals if g["id"] == self._selected_id), None)
        if goal is None:
            _notify_info(
                self,
                _tr_db(self._db, "goals.contribute.title", "Contribute"),
                _tr_db(self._db, "selection.goal_required", "Select a goal first."),
            )
            return
        dlg = ContributeGoalDialog(self._db, goal_name=goal["name"], parent=self)
        if dlg.exec() == ContributeGoalDialog.DialogCode.Accepted:
            data = dlg.get_data()
            self._service.contribute(int(goal["id"]), data["amount"])
            self.refresh()

    def _on_edit(self) -> None:
        from mira.ui.dialogs import SavingsGoalDialog

        goal = next((g for g in self._goals if g["id"] == self._selected_id), None)
        if goal is None:
            _notify_info(
                self,
                _tr_db(self._db, "goals.edit.title", "Edit Goal"),
                _tr_db(self._db, "selection.goal_required", "Select a goal first."),
            )
            return
        dlg = SavingsGoalDialog(self._db, goal=goal, parent=self)
        if dlg.exec() != SavingsGoalDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        try:
            feedback = self._service.update(
                int(goal["id"]),
                name=data["name"],
                target_amount=data["target_amount"],
                target_date=data["target_date"],
            )
        except ValueError as exc:
            _notify_warning(self, _tr_db(self._db, "validation.title", "Validation"), str(exc))
            return
        self._selected_id = feedback.selected_id
        self.refresh()

    def _on_delete(self) -> None:
        goal = next((g for g in self._goals if g["id"] == self._selected_id), None)
        if goal is None:
            _notify_info(
                self,
                _tr_db(self._db, "goals.delete.title", "Delete Goal"),
                _tr_db(self._db, "selection.goal_required", "Select a goal first."),
            )
            return
        reply = QMessageBox.question(
            self,
            "Delete Goal",
            f"Delete savings goal '{goal['name']}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self._service.delete(int(goal["id"]))
            except ValueError as exc:
                _notify_warning(self, _tr_db(self._db, "validation.title", "Validation"), str(exc))
                return
            self._selected_id = None
            self.refresh()

    def _select_goal(self, goal_id: int) -> None:
        self._selected_id = goal_id
        self.refresh()

    def _on_goal_context_menu(self, goal_id: int, global_pos: QPoint) -> None:
        self._selected_id = goal_id
        self.refresh()

        menu = QMenu(self)
        act_contribute = menu.addAction("Contribute")
        act_edit = menu.addAction("Edit")
        act_delete = menu.addAction("Delete")
        chosen = menu.exec(global_pos)
        if chosen is act_contribute:
            self._on_contribute()
        elif chosen is act_edit:
            self._on_edit()
        elif chosen is act_delete:
            self._on_delete()

    def _on_goal_activated(self, goal_id: int) -> None:
        self._selected_id = goal_id
        self._on_contribute()

    def open_add_dialog(self, prefill: dict | None = None) -> None:
        """Public helper used by the main menu to add a savings goal."""
        self._on_add(prefill=prefill)

    def open_contribute_dialog(self) -> None:
        """Public helper used by the main menu to contribute to a goal."""
        if self._selected_id is None and self._goals:
            self._selected_id = self._goals[0]["id"]
        self._on_contribute()

    def refresh(self) -> None:
        self._apply_state(self._service.load_state())

    def _apply_state(self, state: SavingsGoalsViewState) -> None:
        self._goals = list(state.goals)

        # Clear existing cards
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not self._goals:
            empty_lbl = QLabel(
                _tr_db(
                    self._db,
                    "goals.empty",
                    "No savings goals yet. Click '+ Add Goal' to get started.",
                )
            )
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_lbl.setStyleSheet("color:palette(window-text);font-size:13px;padding:40px;")
            self._cards_layout.addWidget(empty_lbl)
            return

        for goal in self._goals:
            goal_id = goal["id"]
            target = float(goal["target_amount"])
            current = float(goal["current_amount"])
            remaining = float(goal["remaining_amount"])
            pct = int(min(goal["progress"] * 100, 100))
            achieved = current >= target

            selected = goal_id == self._selected_id
            card = _GoalCard(goal_id)
            card.setFrameShape(QFrame.Shape.StyledPanel)
            if selected:
                card.setStyleSheet("QFrame{border-radius:6px;border:2px solid palette(highlight);}")
            else:
                card.setStyleSheet("QFrame{border-radius:6px;border:1px solid palette(mid);}")
            card.clicked.connect(self._select_goal)
            card.activated.connect(self._on_goal_activated)
            card.context_requested.connect(self._on_goal_context_menu)

            cl = QVBoxLayout(card)
            cl.setContentsMargins(12, 8, 12, 8)
            cl.setSpacing(4)

            name_row = QHBoxLayout()
            name_lbl = QLabel(goal["name"])
            name_lbl.setFont(QFont("Arial", 12, QFont.Weight.Bold))
            name_lbl.setStyleSheet("background:transparent;border:none;")
            name_row.addWidget(name_lbl)
            name_row.addStretch()
            status_lbl = QLabel(_tr_db(self._db, "goals.achieved", "Achieved") if achieved else f"{pct}%")
            status_lbl.setStyleSheet("background:transparent;border:none;font-size:11px;")
            name_row.addWidget(status_lbl)
            cl.addLayout(name_row)

            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(pct)
            bar.setTextVisible(False)
            bar.setFixedHeight(10)
            bar_color = "#4EC9B0" if achieved else "#0078D4"
            bar.setStyleSheet(
                "QProgressBar{border-radius:5px;border:none;}"
                f"QProgressBar::chunk{{background:{bar_color};border-radius:5px;}}"
            )
            cl.addWidget(bar)

            amounts_row = QHBoxLayout()
            saved_lbl = QLabel(
                _tr_db(
                    self._db,
                    "goals.saved",
                    "Saved: {amount}",
                    params={"amount": _fmt_amount(self._db, current)},
                )
            )
            saved_lbl.setStyleSheet("background:transparent;border:none;font-size:11px;")
            target_lbl = QLabel(
                _tr_db(
                    self._db,
                    "goals.target",
                    "Target: {amount}",
                    params={"amount": _fmt_amount(self._db, target)},
                )
            )
            target_lbl.setStyleSheet("background:transparent;border:none;font-size:11px;")
            rem_lbl = QLabel(
                _tr_db(
                    self._db,
                    "goals.remaining",
                    "Remaining: {amount}",
                    params={"amount": _fmt_amount(self._db, remaining)},
                )
            )
            rem_lbl.setStyleSheet("background:transparent;border:none;font-size:11px;")
            amounts_row.addWidget(saved_lbl)
            amounts_row.addStretch()
            amounts_row.addWidget(target_lbl)
            amounts_row.addStretch()
            amounts_row.addWidget(rem_lbl)
            cl.addLayout(amounts_row)

            if goal.get("target_date"):
                date_lbl = QLabel(
                    _tr_db(
                        self._db,
                        "goals.target_date",
                        "Target date: {date}",
                        params={"date": goal["target_date"]},
                    )
                )
                date_lbl.setStyleSheet("background:transparent;border:none;font-size:10px;")
                cl.addWidget(date_lbl)

            self._cards_layout.addWidget(card)


# ---------------------------------------------------------------------------
# TagsView
# ---------------------------------------------------------------------------
