# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Module documentation."""

from __future__ import annotations


import time
from datetime import datetime
from secrets import randbits
from typing import TYPE_CHECKING, Any

from peewee import JOIN

from mira.db.model import ReconciliationGroup, ReconciliationMatch, Transaction
from mira.transaction_kinds import is_balance_adjustment_transaction

_ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode_crockford(value: int, length: int) -> str:
    """Return encode crockford."""
    chars = ["0"] * length
    for index in range(length - 1, -1, -1):
        chars[index] = _ULID_ALPHABET[value & 0x1F]
        value >>= 5
    return "".join(chars)


def _generate_ulid() -> str:
    """Return generate ulid."""
    timestamp_ms = int(time.time() * 1000)
    return f"{_encode_crockford(timestamp_ms, 10)}{_encode_crockford(randbits(80), 16)}"


class ReconciliationRepository:
    """Represent the ReconciliationRepository class."""

    if TYPE_CHECKING:

        def _atomic(self) -> Any:
            """Return atomic."""

        def _money_to_cents(self, value: object, *, allow_none: bool = False) -> int | None:
            """Return money to cents."""
            ...

        def _cents_to_decimal(self, value: object, *, allow_none: bool = False) -> Any:
            """Return cents to decimal."""
            ...

        def get_account_by_id(self, account_id: int) -> dict[str, Any] | None:
            """Return get account by id."""
            ...

        def get_transaction_by_id(self, tx_id: int) -> dict[str, Any] | None:
            """Return get transaction by id."""
            ...

            ...

    @staticmethod
    def _serialize_group(row: ReconciliationGroup) -> dict[str, Any]:
        """Return serialize group."""
        return {
            "id": str(row.id),
            "account_id": int(row.account_id),  # type: ignore[attr-defined]
            "date_from": row.date_from.isoformat(),  # type: ignore[attr-defined]
            "date_to": row.date_to.isoformat(),  # type: ignore[attr-defined]
            "created_at": row.created_at.strftime("%Y-%m-%d %H:%M:%S"),  # type: ignore[attr-defined]
        }

    def _serialize_match(self, row: ReconciliationMatch) -> dict[str, Any]:
        """Return serialize match."""
        return {
            "id": str(row.id),
            "reconciliation_group_id": str(row.reconciliation_group_id),  # type: ignore[attr-defined]
            "system_transaction_id": int(row.system_transaction_id),  # type: ignore[attr-defined]
            "external_reference": row.external_reference,
            "external_date": row.external_date.isoformat(),  # type: ignore[attr-defined]
            "external_description": row.external_description,
            "external_amount": self._cents_to_decimal(row.external_amount),
            "external_item_key": str(row.external_item_key),
        }

    def list_reconciliation_groups(self, *, account_id: int, date_from: str, date_to: str) -> list[dict[str, Any]]:
        """Return list reconciliation groups."""
        rows = (
            ReconciliationGroup.select()
            .where(
                (ReconciliationGroup.account == int(account_id))
                & (ReconciliationGroup.date_from >= date_from)
                & (ReconciliationGroup.date_to <= date_to)
            )
            .order_by(ReconciliationGroup.created_at.desc(), ReconciliationGroup.id.desc())
        )
        return [self._serialize_group(row) for row in rows]

    def list_reconciliation_matches(
        self,
        *,
        account_id: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        transaction_ids: list[int] | None = None,
        group_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return list reconciliation matches."""
        query = ReconciliationMatch.select(ReconciliationMatch, ReconciliationGroup).join(
            ReconciliationGroup, JOIN.INNER, on=(ReconciliationMatch.reconciliation_group == ReconciliationGroup.id)
        )
        if account_id is not None:
            query = query.where(ReconciliationGroup.account == int(account_id))
        if date_from is not None:
            query = query.where(ReconciliationGroup.date_from >= date_from)
        if date_to is not None:
            query = query.where(ReconciliationGroup.date_to <= date_to)
        if transaction_ids:
            query = query.where(ReconciliationMatch.system_transaction.in_([int(item) for item in transaction_ids]))
        if group_ids:
            query = query.where(ReconciliationMatch.reconciliation_group.in_(group_ids))
        return [
            self._serialize_match(row)
            for row in query.order_by(ReconciliationMatch.external_date, ReconciliationMatch.id)
        ]

    def _update_transaction_reconciled_flags(self, transaction_ids: list[int]) -> None:
        """Return update transaction reconciled flags."""
        if not transaction_ids:
            return
        unique_ids = sorted({int(item) for item in transaction_ids})
        rows = (
            ReconciliationMatch.select(ReconciliationMatch.system_transaction)
            .where(ReconciliationMatch.system_transaction.in_(unique_ids))
            .dicts()
        )
        matched_ids = {int(row["system_transaction_id"]) for row in rows}
        now_value = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for transaction_id in unique_ids:
            has_matches = transaction_id in matched_ids
            transaction = Transaction.get_by_id(transaction_id)
            next_reconciled_at = transaction.reconciled_at
            if has_matches and next_reconciled_at is None:
                next_reconciled_at = now_value
            if not has_matches:
                next_reconciled_at = None
            (
                Transaction.update(
                    is_reconciled=bool(has_matches),
                    reconciled_at=next_reconciled_at,
                )
                .where(Transaction.id == transaction_id)
                .execute()
            )

    def reconcile_transactions(
        self,
        *,
        account_id: int,
        date_from: str,
        date_to: str,
        system_transaction_ids: list[int],
        external_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Return reconcile transactions."""
        if self.get_account_by_id(account_id) is None:
            raise ValueError(f"Account {account_id} not found.")
        tx_ids = sorted({int(item) for item in system_transaction_ids})
        if not tx_ids:
            raise ValueError("Select at least one system transaction.")
        if not external_rows:
            raise ValueError("Select at least one external movement.")

        system_rows: list[dict[str, Any]] = []
        for transaction_id in tx_ids:
            tx = self.get_transaction_by_id(transaction_id)
            if tx is None:
                raise ValueError(f"Transaction {transaction_id} not found.")
            if int(tx.get("account_id") or 0) != int(account_id):
                raise ValueError("Selected transactions must belong to the active account.")
            if int(tx.get("is_transfer") or 0) == 1 or is_balance_adjustment_transaction(tx):
                raise ValueError("Transfers and balance adjustments cannot be reconciled.")
            system_rows.append(tx)

        group_id = _generate_ulid()
        match_ids: list[str] = []
        with self._atomic():
            ReconciliationGroup.create(
                id=group_id,
                account=account_id,
                date_from=date_from,
                date_to=date_to,
            )
            for tx in system_rows:
                for external_row in external_rows:
                    match_id = _generate_ulid()
                    match_ids.append(match_id)
                    ReconciliationMatch.insert(
                        id=match_id,
                        reconciliation_group=group_id,
                        system_transaction=int(tx["id"]),
                        external_reference=external_row.get("reference"),
                        external_date=str(external_row["date"]),
                        external_description=external_row.get("description"),
                        external_amount=self._money_to_cents(external_row.get("amount")) or 0,
                        external_item_key=str(external_row["external_item_key"]),
                    ).on_conflict_ignore().execute()
            self._update_transaction_reconciled_flags(tx_ids)

        group = ReconciliationGroup.get_by_id(group_id)
        matches = self.list_reconciliation_matches(group_ids=[group_id])
        return {
            "group": self._serialize_group(group),
            "matches": matches,
            "created_match_ids": match_ids,
        }

    def _cleanup_empty_groups(self, group_ids: list[str]) -> None:
        """Return cleanup empty groups."""
        if not group_ids:
            return
        for group_id in sorted(set(group_ids)):
            remaining = (
                ReconciliationMatch.select()
                .where(ReconciliationMatch.reconciliation_group == group_id)
                .limit(1)
                .exists()
            )
            if not remaining:
                ReconciliationGroup.delete().where(ReconciliationGroup.id == group_id).execute()

    def clear_reconciliation_for_transactions(self, transaction_ids: list[int]) -> int:
        """Return clear reconciliation for transactions."""
        tx_ids = sorted({int(item) for item in transaction_ids})
        if not tx_ids:
            return 0
        group_ids = [
            str(row["reconciliation_group_id"])
            for row in ReconciliationMatch.select(ReconciliationMatch.reconciliation_group)
            .where(ReconciliationMatch.system_transaction.in_(tx_ids))
            .dicts()
        ]
        with self._atomic():
            deleted = ReconciliationMatch.delete().where(ReconciliationMatch.system_transaction.in_(tx_ids)).execute()
            self._cleanup_empty_groups(group_ids)
            self._update_transaction_reconciled_flags(tx_ids)
        return int(deleted)

    def clear_reconciliation_groups(self, group_ids: list[str]) -> int:
        """Return clear reconciliation groups."""
        normalized_group_ids = sorted({str(item) for item in group_ids if str(item).strip()})
        if not normalized_group_ids:
            return 0
        transaction_ids = [
            int(row["system_transaction_id"])
            for row in ReconciliationMatch.select(ReconciliationMatch.system_transaction)
            .where(ReconciliationMatch.reconciliation_group.in_(normalized_group_ids))
            .dicts()
        ]
        with self._atomic():
            deleted = (
                ReconciliationMatch.delete()
                .where(ReconciliationMatch.reconciliation_group.in_(normalized_group_ids))
                .execute()
            )
            ReconciliationGroup.delete().where(ReconciliationGroup.id.in_(normalized_group_ids)).execute()
            self._update_transaction_reconciled_flags(transaction_ids)
        return int(deleted)
