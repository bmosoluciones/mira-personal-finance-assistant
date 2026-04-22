# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Sync repository for mobile synchronization support."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from mira.db.model import SyncDevice, Transaction, TransactionSyncEvent, TransactionTombstone
from mira.sync_utils import generate_ulid, normalize_utc_iso, utc_now_iso

DESKTOP_LOCAL_DEVICE_ID = "desktop-local"
DEFAULT_SYNC_APP_ID = "mira-mobile-helper"
SyncOperation = Literal["create", "update", "delete"]


@dataclass(frozen=True)
class TransactionSyncMetadata:
    """Represent the TransactionSyncMetadata class."""

    sync_id: str
    sync_version: int
    updated_at: str
    device_id: str


class SyncRepository:
    """Represent the SyncRepository class."""

    if TYPE_CHECKING:

        def _atomic(self) -> Any: ...

        def get_transaction_by_id(self, tx_id: int) -> dict[str, Any] | None:
            """Return get transaction by id."""
            ...

        def get_transaction_tags(self, transaction_id: int) -> list[dict[str, Any]]:
            """Return get transaction tags."""
            ...

        def get_account_by_id(self, account_id: int) -> dict[str, Any] | None:
            """Return get account by id."""
            ...

        def get_category_by_id(self, cat_id: int) -> dict[str, Any] | None:
            """Return get category by id."""
            ...

        def get_local_desktop_device_id(self) -> str:
            """Return get local desktop device id."""
            ...

    def _normalize_device_id(self, device_id: str | None) -> str:
        normalized = str(device_id or "").strip()
        if normalized:
            return normalized
        return self.get_local_desktop_device_id()

    def _build_new_transaction_sync_metadata(
        self,
        *,
        sync_id: str | None = None,
        device_id: str | None = None,
    ) -> TransactionSyncMetadata:
        normalized_sync_id = str(sync_id or "").strip() or generate_ulid()
        normalized_device_id = self._normalize_device_id(device_id)
        return TransactionSyncMetadata(
            sync_id=normalized_sync_id,
            sync_version=1,
            updated_at=utc_now_iso(),
            device_id=normalized_device_id,
        )

    def _build_next_transaction_sync_metadata(
        self,
        current_tx: dict[str, Any],
        *,
        device_id: str | None = None,
        sync_id: str | None = None,
    ) -> TransactionSyncMetadata:
        current_sync_id = str(current_tx.get("sync_id") or "").strip() or str(sync_id or "").strip() or generate_ulid()
        current_version = int(current_tx.get("sync_version") or 1)
        normalized_device_id = self._normalize_device_id(device_id)
        return TransactionSyncMetadata(
            sync_id=current_sync_id,
            sync_version=current_version + 1,
            updated_at=utc_now_iso(),
            device_id=normalized_device_id,
        )

    def _record_transaction_sync_event(
        self,
        *,
        sync_id: str,
        operation: SyncOperation,
        transaction_version: int,
        device_id: str,
        created_at: str,
    ) -> int:
        event = TransactionSyncEvent.create(
            transaction_sync_id=sync_id,
            operation=operation,
            transaction_version=transaction_version,
            device_id=self._normalize_device_id(device_id),
            created_at=created_at,
        )
        return int(event.event_id)  # type: ignore[call-overload]

    def _clear_transaction_tombstone(self, sync_id: str) -> None:
        TransactionTombstone.delete().where(TransactionTombstone.transaction_sync_id == sync_id).execute()

    def _upsert_transaction_tombstone(
        self,
        *,
        sync_id: str,
        deleted_version: int,
        device_id: str,
        deleted_at: str,
    ) -> None:
        existing = TransactionTombstone.get_or_none(TransactionTombstone.transaction_sync_id == sync_id)
        if existing is None:
            TransactionTombstone.create(
                transaction_sync_id=sync_id,
                last_deleted_version=deleted_version,
                deleted_by_device_id=self._normalize_device_id(device_id),
                deleted_at=deleted_at,
            )
            return
        (
            TransactionTombstone.update(
                last_deleted_version=deleted_version,
                deleted_by_device_id=self._normalize_device_id(device_id),
                deleted_at=deleted_at,
            )
            .where(TransactionTombstone.transaction_sync_id == sync_id)
            .execute()
        )

    def get_transaction_by_sync_id(self, sync_id: str) -> dict[str, Any] | None:
        """Return get transaction by sync id."""
        normalized_sync_id = str(sync_id or "").strip()
        if not normalized_sync_id:
            return None
        row = Transaction.get_or_none(Transaction.sync_id == normalized_sync_id)
        if row is None:
            return None
        tx = self.get_transaction_by_id(int(row.id))  # type: ignore[arg-type]
        if tx is None:
            return None
        return self._serialize_transaction_for_sync(tx)

    def get_transaction_tombstone(self, sync_id: str) -> dict[str, Any] | None:
        """Return get transaction tombstone."""
        normalized_sync_id = str(sync_id or "").strip()
        if not normalized_sync_id:
            return None
        row = TransactionTombstone.get_or_none(TransactionTombstone.transaction_sync_id == normalized_sync_id)
        if row is None:
            return None
        return {
            "transaction_sync_id": row.transaction_sync_id,
            "last_deleted_version": int(row.last_deleted_version),
            "deleted_by_device_id": row.deleted_by_device_id,
            "deleted_at": normalize_utc_iso(row.deleted_at),
        }

    def register_sync_device(
        self,
        *,
        device_id: str | None,
        device_name: str,
        platform: str,
        app_id: str = DEFAULT_SYNC_APP_ID,
    ) -> dict[str, Any]:
        """Return register sync device."""
        normalized_device_id = str(device_id or "").strip() or generate_ulid()
        normalized_name = str(device_name or "").strip() or "Unnamed device"
        normalized_platform = str(platform or "").strip() or "android"
        normalized_app_id = str(app_id or DEFAULT_SYNC_APP_ID).strip() or DEFAULT_SYNC_APP_ID
        seen_at = utc_now_iso()
        row = SyncDevice.get_or_none(SyncDevice.device_id == normalized_device_id)
        if row is None:
            row = SyncDevice.create(
                device_id=normalized_device_id,
                device_name=normalized_name,
                platform=normalized_platform,
                app_id=normalized_app_id,
                created_at=seen_at,
                last_seen_at=seen_at,
                last_acked_event_id=0,
            )
        else:
            (
                SyncDevice.update(
                    device_name=normalized_name,
                    platform=normalized_platform,
                    app_id=normalized_app_id,
                    last_seen_at=seen_at,
                )
                .where(SyncDevice.device_id == normalized_device_id)
                .execute()
            )
            row = SyncDevice.get_by_id(normalized_device_id)
        return {
            "device_id": row.device_id,
            "device_name": row.device_name,
            "platform": row.platform,
            "app_id": row.app_id,
            "created_at": normalize_utc_iso(row.created_at),
            "last_seen_at": normalize_utc_iso(row.last_seen_at),
            "last_acked_event_id": int(row.last_acked_event_id),
        }

    def ack_sync_device_cursor(self, device_id: str, last_acked_event_id: int) -> dict[str, Any]:
        """Return ack sync device cursor."""
        device = SyncDevice.get_or_none(SyncDevice.device_id == device_id)
        if device is None:
            raise ValueError(f"Sync device {device_id} not found")
        next_cursor = max(int(device.last_acked_event_id or 0), int(last_acked_event_id or 0))
        seen_at = utc_now_iso()
        (
            SyncDevice.update(last_acked_event_id=next_cursor, last_seen_at=seen_at)
            .where(SyncDevice.device_id == device_id)
            .execute()
        )
        refreshed = SyncDevice.get_by_id(device_id)
        return {
            "device_id": refreshed.device_id,
            "device_name": refreshed.device_name,
            "platform": refreshed.platform,
            "app_id": refreshed.app_id,
            "created_at": normalize_utc_iso(refreshed.created_at),
            "last_seen_at": normalize_utc_iso(refreshed.last_seen_at),
            "last_acked_event_id": int(refreshed.last_acked_event_id),
        }

    def get_sync_device(self, device_id: str) -> dict[str, Any] | None:
        """Return get sync device."""
        row = SyncDevice.get_or_none(SyncDevice.device_id == device_id)
        if row is None:
            return None
        return {
            "device_id": row.device_id,
            "device_name": row.device_name,
            "platform": row.platform,
            "app_id": row.app_id,
            "created_at": normalize_utc_iso(row.created_at),
            "last_seen_at": normalize_utc_iso(row.last_seen_at),
            "last_acked_event_id": int(row.last_acked_event_id),
        }

    def _serialize_transaction_for_sync(self, tx: dict[str, Any]) -> dict[str, Any]:
        serialized = dict(tx)
        tx_id = int(serialized["id"])
        serialized["updated_at"] = normalize_utc_iso(serialized.get("updated_at"))
        tags = self.get_transaction_tags(tx_id)
        serialized["tag_ids"] = [int(tag["id"]) for tag in tags]
        account_id = serialized.get("account_id")
        to_account_id = serialized.get("to_account_id")
        category_id = serialized.get("category_id")
        account = None if account_id is None else self.get_account_by_id(int(account_id))
        to_account = None if to_account_id is None else self.get_account_by_id(int(to_account_id))
        category = None if category_id is None else self.get_category_by_id(int(category_id))
        serialized["account_global_id"] = None if account is None else account.get("global_id")
        serialized["to_account_global_id"] = None if to_account is None else to_account.get("global_id")
        serialized["category_global_id"] = None if category is None else category.get("global_id")
        serialized["tag_global_ids"] = [
            str(tag.get("global_id")) for tag in tags if str(tag.get("global_id") or "").strip()
        ]
        return serialized

    def list_transaction_changes(self, *, after_event_id: int, limit: int = 500) -> list[dict[str, Any]]:
        """Return list transaction changes."""
        events = (
            TransactionSyncEvent.select()
            .where(TransactionSyncEvent.event_id > int(after_event_id))
            .order_by(TransactionSyncEvent.event_id.asc())
            .limit(limit)
        )
        changes: list[dict[str, Any]] = []
        for event in events:
            item = {
                "event_id": int(event.event_id),
                "transaction_sync_id": event.transaction_sync_id,
                "operation": event.operation,
                "transaction_version": int(event.transaction_version),
                "device_id": event.device_id,
                "created_at": normalize_utc_iso(event.created_at),
            }
            match str(event.operation):
                case "delete":
                    item["transaction"] = None
                    item["tombstone"] = self.get_transaction_tombstone(event.transaction_sync_id)
                case _:
                    current = self.get_transaction_by_sync_id(event.transaction_sync_id)
                    item["transaction"] = None if current is None else self._serialize_transaction_for_sync(current)
                    item["tombstone"] = self.get_transaction_tombstone(event.transaction_sync_id)
            changes.append(item)
        return changes

    def touch_transaction_sync(
        self,
        tx_id: int,
        *,
        device_id: str | None = None,
        operation: SyncOperation = "update",
    ) -> dict[str, Any] | None:
        """Return touch transaction sync."""
        current_tx = self.get_transaction_by_id(tx_id)
        if current_tx is None:
            return None
        metadata = self._build_next_transaction_sync_metadata(current_tx, device_id=device_id)
        (
            Transaction.update(
                sync_id=metadata.sync_id,
                sync_version=metadata.sync_version,
                updated_at=metadata.updated_at,
                last_modified_by_device_id=metadata.device_id,
            )
            .where(Transaction.id == tx_id)
            .execute()
        )
        self._clear_transaction_tombstone(metadata.sync_id)
        self._record_transaction_sync_event(
            sync_id=metadata.sync_id,
            operation=operation,
            transaction_version=metadata.sync_version,
            device_id=metadata.device_id,
            created_at=metadata.updated_at,
        )
        refreshed = self.get_transaction_by_id(tx_id)
        if refreshed is None:
            return None
        return self._serialize_transaction_for_sync(refreshed)

    def touch_transactions_sync(
        self,
        transaction_ids: list[int],
        *,
        device_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return touch transactions sync."""
        touched: list[dict[str, Any]] = []
        for tx_id in dict.fromkeys(int(item) for item in transaction_ids):
            if (refreshed := self.touch_transaction_sync(tx_id, device_id=device_id)) is not None:
                touched.append(refreshed)
        return touched
