# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Savings goal dialogs."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout

from mira.db.database import Database
from mira.ui.dialogs._shared import _NOTICE_LABEL_STYLE, _make_amount_spin, _make_date_edit, _notify_warning
from mira.ui.i18n import normalize_language, tr


class SavingsGoalDialog(QDialog):
    """Create a savings goal."""

    def __init__(self, db: Database, goal: dict | None = None, prefill: dict | None = None, parent=None) -> None:
        """Initialize the SavingsGoalDialog instance."""
        super().__init__(parent)
        self._db = db
        self._goal = goal
        self._language = normalize_language(self._db.setting.get("language"))
        self.setWindowTitle(
            self._t("goals.dialog.title.edit", "Edit Goal")
            if goal
            else self._t("goals.dialog.title.add", "Add Savings Goal")
        )
        self.setMinimumWidth(340)
        self._build_ui()
        if goal:
            self._prefill(goal)
        elif prefill:
            self._prefill(prefill)
        self._update_notice()

    def _t(self, key: str, default: str, *, params: dict[str, object] | None = None) -> str:
        """Return t."""
        return tr(key, self._language, default=default, params=params)

    def _build_ui(self) -> None:
        """Return build ui."""
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText(self._t("goals.dialog.name.placeholder", "Goal name… (e.g. Trip to Europe)"))
        self._name_edit.textChanged.connect(self._update_notice)
        form.addRow(self._t("goals.dialog.name", "Name:"), self._name_edit)
        self._target_spin = _make_amount_spin(self._db)
        form.addRow(self._t("goals.dialog.target_amount", "Target Amount:"), self._target_spin)
        self._date_edit = _make_date_edit()
        form.addRow(self._t("goals.dialog.target_date", "Target Date:"), self._date_edit)
        layout.addLayout(form)
        self._notice_lbl = QLabel("")
        self._notice_lbl.setWordWrap(True)
        self._notice_lbl.setStyleSheet(_NOTICE_LABEL_STYLE)
        layout.addWidget(self._notice_lbl)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _prefill(self, goal: dict) -> None:
        """Return prefill."""
        from PySide6.QtCore import QDate

        self._name_edit.setText(goal.get("name", ""))
        if (target_amount := goal.get("target_amount")) is not None:
            try:
                self._target_spin.setValue(float(target_amount))
            except (ValueError, TypeError):
                pass
        if td := goal.get("target_date"):
            parts = td.split("-")
            if len(parts) == 3:
                try:
                    self._date_edit.setDate(QDate(int(parts[0]), int(parts[1]), int(parts[2])))
                except (ValueError, TypeError):
                    pass

    def _update_notice(self) -> None:
        """Return update notice."""
        goal_name = self._name_edit.text().strip()
        parent_name = self._db.setting.get_savings_goals_parent_name()
        if self._goal is None:
            key = "goals.dialog.notice.create.named" if goal_name else "goals.dialog.notice.create.generic"
            default = (
                "MIRA will link this goal to the savings expense category '{name}'. "
                "If it does not exist, it will be created automatically under '{parent}'."
                if goal_name
                else "MIRA will link this goal to a savings expense category with the same name. "
                "If it does not exist, it will be created automatically under '{parent}'."
            )
        else:
            key = "goals.dialog.notice.edit.named" if goal_name else "goals.dialog.notice.edit.generic"
            default = (
                "This goal is linked to a savings expense category. If you change its name to '{name}', "
                "MIRA will relink it to a category with that name under '{parent}'. Existing categories and history are not renamed."
                if goal_name
                else "This goal remains linked to a savings expense category. If you change its name, "
                "MIRA will relink it to a category with that new name under '{parent}'. Existing categories and history are not renamed."
            )
        self._notice_lbl.setText(self._t(key, default, params={"name": goal_name, "parent": parent_name}))

    def _on_accept(self) -> None:
        """Return on accept."""
        if not self._name_edit.text().strip():
            _notify_warning(
                self,
                self._t("validation.title", "Validation"),
                self._t("goals.dialog.validation.name", "Goal name cannot be empty."),
            )
            return
        if self._target_spin.value() <= 0:
            _notify_warning(
                self,
                self._t("validation.title", "Validation"),
                self._t("goals.dialog.validation.target", "Target amount must be greater than zero."),
            )
            return
        self.accept()

    def get_data(self) -> dict:
        """Return get data."""
        return {
            "name": self._name_edit.text().strip(),
            "target_amount": self._target_spin.value(),
            "target_date": self._date_edit.date().toString("yyyy-MM-dd"),
        }


class ContributeGoalDialog(QDialog):
    """Add a contribution to a savings goal.

    When *goals* contains more than one entry, the dialog shows a dropdown so
    the user can explicitly choose the target goal.  *selected_goal_id* pre-
    selects the goal that was active in the list view (if any).
    """

    def __init__(
        self,
        db: Database,
        goal_name: str,
        parent=None,
        *,
        goals: list[dict] | None = None,
        selected_goal_id: int | None = None,
    ) -> None:
        """Initialize the ContributeGoalDialog instance."""
        super().__init__(parent)
        self._db = db
        self._language = normalize_language(self._db.setting.get("language"))
        self._goals = list(goals) if goals else []
        self.setWindowTitle(tr("goals.contribute.dialog.title", self._language, default="Contribute to Savings Goal"))
        self.setMinimumWidth(320)
        self._build_ui(goal_name=goal_name, selected_goal_id=selected_goal_id)

    def _t(self, key: str, default: str, *, params: dict[str, object] | None = None) -> str:
        """Return t."""
        return tr(key, self._language, default=default, params=params)

    def _build_ui(self, *, goal_name: str, selected_goal_id: int | None) -> None:
        """Return build ui."""
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        if self._goals:
            self._goal_combo = QComboBox()
            for goal in self._goals:
                self._goal_combo.addItem(str(goal.get("name", "")), goal.get("id"))
            # Pre-select based on selected_goal_id, falling back to goal_name.
            preselect_index = -1
            if selected_goal_id is not None:
                for i, g in enumerate(self._goals):
                    if g.get("id") == selected_goal_id:
                        preselect_index = i
                        break
            if preselect_index == -1:
                for i, g in enumerate(self._goals):
                    if g.get("name") == goal_name:
                        preselect_index = i
                        break
            if preselect_index >= 0:
                self._goal_combo.setCurrentIndex(preselect_index)
            form.addRow(self._t("goals.contribute.dialog.goal", "Savings goal:"), self._goal_combo)
        else:
            self._goal_combo = None  # type: ignore[assignment]

        self._amount_spin = _make_amount_spin(self._db)
        form.addRow(self._t("goals.contribute.dialog.amount", "Amount to contribute:"), self._amount_spin)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        """Return on accept."""
        if self._amount_spin.value() <= 0:
            _notify_warning(
                self,
                self._t("validation.title", "Validation"),
                self._t("goals.contribute.dialog.validation.amount", "Amount must be greater than zero."),
            )
            return
        self.accept()

    def get_data(self) -> dict:
        """Return get data."""
        data: dict = {"amount": self._amount_spin.value()}
        if self._goal_combo is not None:
            data["goal_id"] = self._goal_combo.currentData()
        return data


__all__ = ["ContributeGoalDialog", "SavingsGoalDialog"]
