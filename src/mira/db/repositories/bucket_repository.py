# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mira.db.money import MoneyLike
from mira.db.model import Bucket


class BucketRepository:
    if TYPE_CHECKING:

        def _cents_to_money(self, value: object, *, allow_none: bool = False) -> Any: ...
        def _money_to_cents(self, value: object, *, allow_none: bool = False) -> int | None: ...

    def _serialize_bucket_row(self, row: Bucket) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "budget_amount": self._cents_to_money(row.budget_amount),
            "spent_amount": self._cents_to_money(row.spent_amount),
            "period": row.period,
            "start_day": row.start_day,
            "end_day": row.end_day,
            "alert_threshold": row.alert_threshold,
        }

    def get_buckets(self) -> list[dict]:
        return [self._serialize_bucket_row(row) for row in Bucket.select().order_by(Bucket.name)]

    def get_bucket_by_name(self, name: str) -> dict | None:
        row = Bucket.get_or_none(Bucket.name == name)
        if row is None:
            return None
        return self._serialize_bucket_row(row)

    def upsert_bucket(
        self,
        name: str,
        budget_amount: MoneyLike,
        period: str = "monthly",
        start_day: int = 1,
        end_day: int = 31,
        alert_threshold: float = 0.75,
    ) -> dict:
        Bucket.insert(
            name=name,
            budget_amount=self._money_to_cents(budget_amount),
            spent_amount=0,
            period=period,
            start_day=start_day,
            end_day=end_day,
            alert_threshold=alert_threshold,
        ).on_conflict(
            conflict_target=[Bucket.name],
            update={
                Bucket.budget_amount: self._money_to_cents(budget_amount),
                Bucket.period: period,
                Bucket.start_day: start_day,
                Bucket.end_day: end_day,
                Bucket.alert_threshold: alert_threshold,
            },
        ).execute()
        bucket = self.get_bucket_by_name(name)
        if bucket is None:
            raise RuntimeError(f"Failed to upsert bucket {name}")
        return bucket

    def update_bucket_spent(self, bucket_name: str, amount: MoneyLike) -> None:
        amount_cents = self._money_to_cents(amount) or 0
        Bucket.update(spent_amount=Bucket.spent_amount + amount_cents).where(Bucket.name == bucket_name).execute()

    def delete_bucket(self, name: str) -> None:
        """Delete a budget bucket by name."""
        Bucket.delete().where(Bucket.name == name).execute()
