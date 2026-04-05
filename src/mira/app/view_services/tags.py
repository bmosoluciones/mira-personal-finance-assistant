# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Application service for the Tags view."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from mira.app.view_services._common import OperationFeedback
from mira.db.database import Database


@dataclass(frozen=True)
class TagsViewState:
    tags: list[dict[str, Any]]
    monthly_counts: dict[int, int]


class TagsViewService:
    """Move tag CRUD and related counts out of the QWidget."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def load_state(self) -> TagsViewState:
        since = date.today().replace(day=1).isoformat()
        return TagsViewState(
            tags=self._db.tag.list(),
            monthly_counts=self._db.report.tag_transaction_counts(since_date=since),
        )

    def create(self, *, name: str, color: str, icon: str = "") -> OperationFeedback:
        created = self._db.tag.create(name, color, icon=icon)
        return OperationFeedback(selected_id=int(created["id"]))

    def update(self, tag_id: int, *, name: str, color: str, icon: str = "") -> OperationFeedback:
        self._db.tag.update(tag_id, name, color, icon=icon)
        return OperationFeedback(selected_id=int(tag_id))

    def delete(self, tag_id: int) -> OperationFeedback:
        self._db.tag.delete(tag_id)
        return OperationFeedback()
