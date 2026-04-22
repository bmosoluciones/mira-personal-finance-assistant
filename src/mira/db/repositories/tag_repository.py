# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Module documentation."""

from __future__ import annotations


from datetime import datetime as _datetime
from typing import TYPE_CHECKING

from peewee import IntegrityError as PeeweeIntegrityError, fn

from mira.sync_utils import utc_now_iso as _utc_now_iso
from mira.db.errors import DuplicateTagNameError
from mira.db.helpers import _ICON_MAX_LENGTH
from mira.db.model import RecurringTransactionTag, Tag, TransactionTag


def _fmt_updated_at(value: object) -> str | None:
    """Normalize a datetime/string to ISO-8601 UTC format with T and Z."""
    if isinstance(value, _datetime):
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, str) and value:
        s = value.replace(" ", "T")
        if not s.endswith("Z") and "+" not in s:
            s = s + "Z"
        return s
    return None


class TagRepository:
    """Represent the TagRepository class."""

    if TYPE_CHECKING:

        def get_setting(self, key: str) -> str | None:
            """Return get setting."""

        def _atomic(self):
            """Return atomic."""

    def add_tag(
        self,
        name: str,
        color: str = "#888888",
        icon: str = "",
        global_id: str | None = None,
        device_id: str | None = None,
    ) -> dict:
        """Return add tag."""
        normalized = name.strip()
        if not normalized:
            raise ValueError("Tag name cannot be empty")
        if len(icon) > _ICON_MAX_LENGTH:
            raise ValueError(f"Tag icon cannot exceed {_ICON_MAX_LENGTH} characters")
        create_kwargs: dict[str, object] = dict(name=normalized, icon=icon, color=color)
        if global_id:
            create_kwargs["global_id"] = global_id
        if device_id:
            create_kwargs["last_modified_by_device_id"] = device_id
        try:
            tag = Tag.create(**create_kwargs)
        except PeeweeIntegrityError as exc:
            raise DuplicateTagNameError(f"Tag '{normalized}' already exists") from exc
        return {
            "id": tag.id,
            "name": tag.name,
            "icon": tag.icon,
            "color": tag.color,
            "created_at": tag.created_at,
            "global_id": tag.global_id,
            "updated_at": _fmt_updated_at(tag.updated_at),
            "sync_version": tag.sync_version,
            "last_modified_by_device_id": tag.last_modified_by_device_id,
        }

    def get_tags(self) -> list[dict]:
        """Return get tags."""
        return [
            {
                "id": row.id,
                "name": row.name,
                "icon": row.icon,
                "color": row.color,
                "created_at": row.created_at,
                "global_id": row.global_id,
                "updated_at": _fmt_updated_at(row.updated_at),
                "sync_version": row.sync_version,
                "last_modified_by_device_id": row.last_modified_by_device_id,
            }
            for row in Tag.select().order_by(Tag.name)
        ]

    def get_tag_by_id(self, tag_id: int) -> dict | None:
        """Return get tag by id."""
        row = Tag.get_or_none(Tag.id == tag_id)
        if row is None:
            return None
        return {
            "id": row.id,
            "name": row.name,
            "icon": row.icon,
            "color": row.color,
            "created_at": row.created_at,
            "global_id": row.global_id,
            "updated_at": _fmt_updated_at(row.updated_at),
            "sync_version": row.sync_version,
            "last_modified_by_device_id": row.last_modified_by_device_id,
        }

    def get_tag_by_name(self, name: str) -> dict | None:
        """Return get tag by name."""
        normalized = name.strip()
        if not normalized:
            return None
        row = Tag.select().where(fn.LOWER(fn.TRIM(Tag.name)) == normalized.casefold()).limit(1).first()
        if row is None:
            return None
        return {
            "id": row.id,
            "name": row.name,
            "icon": row.icon,
            "color": row.color,
            "created_at": row.created_at,
            "global_id": row.global_id,
            "updated_at": _fmt_updated_at(row.updated_at),
            "sync_version": row.sync_version,
            "last_modified_by_device_id": row.last_modified_by_device_id,
        }

    def get_tag_by_global_id(self, global_id: str) -> dict | None:
        """Return the tag with the given global_id, or None."""
        normalized = str(global_id or "").strip()
        if not normalized:
            return None
        row = Tag.get_or_none(Tag.global_id == normalized)
        if row is None:
            return None
        return {
            "id": row.id,
            "name": row.name,
            "icon": row.icon,
            "color": row.color,
            "created_at": row.created_at,
            "global_id": row.global_id,
            "updated_at": _fmt_updated_at(row.updated_at),
            "sync_version": row.sync_version,
            "last_modified_by_device_id": row.last_modified_by_device_id,
        }

    def update_tag(self, tag_id: int, name: str, color: str, icon: str = "", device_id: str | None = None) -> None:
        """Return update tag."""
        normalized = name.strip()
        if not normalized:
            raise ValueError("Tag name cannot be empty")
        if len(icon) > _ICON_MAX_LENGTH:
            raise ValueError(f"Tag icon cannot exceed {_ICON_MAX_LENGTH} characters")
        updates: dict[str, object] = {"name": normalized, "color": color, "icon": icon}
        if device_id:
            updates["last_modified_by_device_id"] = device_id
            updates["updated_at"] = _utc_now_iso()
            row = Tag.get_or_none(Tag.id == tag_id)
            if row is not None:
                updates["sync_version"] = int(row.sync_version or 1) + 1
        try:
            Tag.update(**updates).where(Tag.id == tag_id).execute()
        except PeeweeIntegrityError as exc:
            raise DuplicateTagNameError(f"Tag '{normalized}' already exists") from exc

    def delete_tag(self, tag_id: int) -> None:
        """Return delete tag."""
        Tag.delete().where(Tag.id == tag_id).execute()

    def get_transaction_tags(self, transaction_id: int) -> list[dict]:
        """Return get transaction tags."""
        query = (
            Tag.select()
            .join(TransactionTag, on=(TransactionTag.tag == Tag.id))
            .where(TransactionTag.transaction_id == transaction_id)
            .order_by(Tag.name)
        )
        return [
            {
                "id": row.id,
                "name": row.name,
                "icon": row.icon,
                "color": row.color,
                "created_at": row.created_at,
                "global_id": row.global_id,
                "updated_at": _fmt_updated_at(row.updated_at),
                "sync_version": row.sync_version,
                "last_modified_by_device_id": row.last_modified_by_device_id,
            }
            for row in query
        ]

    def _normalize_tag_ids(self, tag_ids: list[int] | None) -> list[int]:
        """Return normalize tag ids."""
        max_tags = int(self.get_setting("max_tags_per_transaction") or 10)
        unique_ids = list(dict.fromkeys(int(tag_id) for tag_id in (tag_ids or [])))
        if len(unique_ids) > max_tags:
            raise ValueError(f"Cannot assign more than {max_tags} tags to a transaction")
        return unique_ids

    def set_transaction_tags(self, transaction_id: int, tag_ids: list[int]) -> None:
        """Return set transaction tags."""
        unique_ids = self._normalize_tag_ids(tag_ids)
        with self._atomic():
            TransactionTag.delete().where(TransactionTag.transaction_id == transaction_id).execute()
            for tid in unique_ids:
                TransactionTag.insert(transaction_id=transaction_id, tag=tid).on_conflict_ignore().execute()

    def add_transaction_tag(self, transaction_id: int, tag_id: int) -> None:
        """Return add transaction tag."""
        current = self.get_transaction_tags(transaction_id)
        if any(t["id"] == tag_id for t in current):
            return
        max_tags = int(self.get_setting("max_tags_per_transaction") or 10)
        if len(current) >= max_tags:
            raise ValueError(f"Cannot assign more than {max_tags} tags to a transaction")
        TransactionTag.insert(transaction_id=transaction_id, tag=tag_id).on_conflict_ignore().execute()

    def remove_transaction_tag(self, transaction_id: int, tag_id: int) -> None:
        """Return remove transaction tag."""
        TransactionTag.delete().where(
            (TransactionTag.transaction_id == transaction_id) & (TransactionTag.tag == tag_id)
        ).execute()

    def get_transactions_tags_bulk(self, transaction_ids: list[int]) -> dict[int, list[dict]]:
        """Return get transactions tags bulk."""
        if not transaction_ids:
            return {}
        result: dict[int, list[dict]] = {tid: [] for tid in transaction_ids}
        query = (
            TransactionTag.select(
                TransactionTag.transaction_id,
                Tag.id.alias("id"),
                Tag.name.alias("name"),
                Tag.icon.alias("icon"),
                Tag.color.alias("color"),
                Tag.created_at.alias("created_at"),
            )
            .join(Tag, on=(TransactionTag.tag == Tag.id))
            .where(TransactionTag.transaction_id.in_(transaction_ids))
            .order_by(Tag.name)
            .dicts()
        )
        for row in query:
            tx_id = int(row.pop("transaction_id"))
            result[tx_id].append(row)
        return result

    def get_recurring_tags(self, recurring_id: int) -> list[dict]:
        """Return get recurring tags."""
        query = (
            Tag.select(Tag.id, Tag.name, Tag.icon, Tag.color, Tag.created_at)
            .join(RecurringTransactionTag, on=(RecurringTransactionTag.tag == Tag.id))
            .where(RecurringTransactionTag.recurring_id == recurring_id)
            .order_by(Tag.name)
        )
        return [
            {
                "id": row.id,
                "name": row.name,
                "icon": row.icon,
                "color": row.color,
                "created_at": row.created_at,
            }
            for row in query
        ]

    def _replace_recurring_tags(self, recurring_id: int, tag_ids: list[int]) -> None:
        """Return replace recurring tags."""
        unique_ids = self._normalize_tag_ids(tag_ids)
        with self._atomic():
            RecurringTransactionTag.delete().where(RecurringTransactionTag.recurring_id == recurring_id).execute()
            for tag_id in unique_ids:
                RecurringTransactionTag.insert(recurring_id=recurring_id, tag=tag_id).on_conflict_ignore().execute()

    def set_recurring_tags(self, recurring_id: int, tag_ids: list[int]) -> None:
        """Return set recurring tags."""
        self._replace_recurring_tags(recurring_id, tag_ids)

    def get_recurring_tags_bulk(self, recurring_ids: list[int]) -> dict[int, list[dict]]:
        """Return get recurring tags bulk."""
        if not recurring_ids:
            return {}
        result: dict[int, list[dict]] = {recurring_id: [] for recurring_id in recurring_ids}
        query = (
            RecurringTransactionTag.select(
                RecurringTransactionTag.recurring_id,
                Tag.id.alias("id"),
                Tag.name.alias("name"),
                Tag.icon.alias("icon"),
                Tag.color.alias("color"),
                Tag.created_at.alias("created_at"),
            )
            .join(Tag, on=(RecurringTransactionTag.tag == Tag.id))
            .where(RecurringTransactionTag.recurring_id.in_(recurring_ids))
            .order_by(Tag.name)
            .dicts()
        )
        for row in query:
            recurring_id = int(row.pop("recurring_id"))
            result[recurring_id].append(row)
        return result

    def _enrich_recurring_rows(self, rows: list[dict]) -> list[dict]:
        """Return enrich recurring rows."""
        recurring_ids = [int(row["id"]) for row in rows if row.get("id") is not None]
        tags_by_recurring = self.get_recurring_tags_bulk(recurring_ids)
        enriched_rows: list[dict] = []
        for row in rows:
            enriched = dict(row)
            recurring_id = enriched.get("id")
            tags = tags_by_recurring.get(int(recurring_id), []) if recurring_id is not None else []
            enriched["tags"] = tags
            enriched["tag_ids"] = [int(tag["id"]) for tag in tags]
            enriched["tag_names"] = ", ".join(str(tag.get("name") or "") for tag in tags)
            enriched_rows.append(enriched)
        return enriched_rows
