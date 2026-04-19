# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Module documentation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mira.db import io_csv_excel as db_io


class DatabaseIOService:
    """Thin application service for CSV/Excel database transport."""

    def __init__(self, db: Any) -> None:
        """Initialize the DatabaseIOService instance."""
        self._db = db

    def export_transactions_csv(
        self,
        filepath: str,
        *,
        tx_type: str | None = None,
        account_id: int | None = None,
        since_date: str | None = None,
        until_date: str | None = None,
        category: str | None = None,
        search: str | None = None,
    ) -> int:
        """Return export transactions csv."""
        return db_io.export_transactions_csv(
            self._db,
            filepath,
            tx_type=tx_type,
            account_id=account_id,
            since_date=since_date,
            until_date=until_date,
            category=category,
            search=search,
        )

    def export_transactions_file(
        self,
        filepath: str,
        *,
        tx_type: str | None = None,
        account_id: int | None = None,
        since_date: str | None = None,
        until_date: str | None = None,
        category: str | None = None,
        search: str | None = None,
    ) -> int:
        """Return export transactions file."""
        return db_io.export_transactions_file(
            self._db,
            filepath,
            tx_type=tx_type,
            account_id=account_id,
            since_date=since_date,
            until_date=until_date,
            category=category,
            search=search,
        )

    def export_budget_comparison_excel(
        self,
        filepath: str | Path,
        budget_id: int,
        *,
        granularity: str = "quarterly",
    ) -> int:
        """Return export budget comparison excel."""
        return db_io.export_budget_comparison_excel(self._db, filepath, budget_id, granularity=granularity)

    def import_transactions_csv(self, filepath: str) -> tuple[int, int]:
        """Return import transactions csv."""
        return db_io.import_transactions_csv(self._db, filepath)

    def import_transactions_file(self, filepath: str) -> tuple[int, int]:
        """Return import transactions file."""
        return db_io.import_transactions_file(self._db, filepath)
