# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from peewee import IntegrityError as PeeweeIntegrityError, fn

from mira.db.errors import DuplicateCategoryNameError
from mira.db.helpers import (
    _ICON_MAX_LENGTH,
    _SAVINGS_GOALS_PARENT_COLOR,
    _SAVINGS_GOALS_PARENT_NAMES,
    _UNSET,
)
from mira.db.model import Bucket, Category, RecurringTransaction, SavingsGoal, Transaction


class CategoryRepository:
    if TYPE_CHECKING:

        def _savings_goals_parent_name_candidates(self) -> list[str]: ...
        def _database_language(self) -> str: ...
        def _atomic(self) -> Any: ...
        def _merge_budget_details_for_categories(self, source_category_id: int, target_category_id: int) -> None: ...

    @staticmethod
    def _normalized_name_expression(field: Any) -> Any:
        return fn.LOWER(fn.TRIM(field))

    def get_categories(self, cat_type: str | None = None, *, include_savings: bool = True) -> list[dict]:
        query = Category.select()
        if cat_type:
            query = query.where(Category.type == cat_type)
        if not include_savings:
            query = query.where(Category.is_savings == False)  # noqa: E712
        return [
            {
                "id": row.id,
                "name": row.name,
                "type": row.type,
                "color": row.color,
                "icon": row.icon,
                "is_savings": int(bool(row.is_savings)),
                "parent_id": row.parent_id,
            }
            for row in query.order_by(Category.name)
        ]

    @staticmethod
    def _serialize_category_row(row: Category) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "type": row.type,
            "color": row.color,
            "icon": row.icon,
            "is_savings": int(bool(row.is_savings)),
            "parent_id": row.parent_id,
        }

    def get_category(
        self,
        *,
        cat_id: int | None = None,
        name: str | None = None,
        cat_type: str | None = None,
    ) -> dict | None:
        if cat_id is not None:
            row = Category.get_or_none(Category.id == int(cat_id))
            return None if row is None else self._serialize_category_row(row)

        normalized_name = (name or "").strip()
        if not normalized_name:
            return None

        query = Category.select().where(fn.LOWER(fn.TRIM(Category.name)) == normalized_name.casefold())
        if cat_type:
            query = query.where(Category.type == cat_type)
        row = query.order_by(Category.id).limit(1).first()
        return None if row is None else self._serialize_category_row(row)

    def get_category_by_id(self, cat_id: int) -> dict | None:
        return self.get_category(cat_id=cat_id)

    def get_category_by_name(self, name: str, cat_type: str | None = None) -> dict | None:
        return self.get_category(name=name, cat_type=cat_type)

    def add_category(
        self,
        name: str,
        cat_type: str,
        color: str = "#888888",
        parent_id: int | None = None,
        is_savings: bool = False,
        icon: str = "",
    ) -> dict:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Category name cannot be empty")
        if parent_id is not None:
            self._validate_category_parent(None, parent_id, cat_type)
        if len(icon) > _ICON_MAX_LENGTH:
            raise ValueError(f"Category icon cannot exceed {_ICON_MAX_LENGTH} characters")
        try:
            cat = Category.create(
                name=normalized_name,
                type=cat_type,
                color=color,
                parent_id=parent_id,
                is_savings=is_savings,
                icon=icon,
            )
        except PeeweeIntegrityError as exc:
            raise DuplicateCategoryNameError(f"Category '{normalized_name}' already exists") from exc
        return self._serialize_category_row(cat)

    def get_or_create_category(
        self,
        name: str,
        cat_type: str,
        color: str = "#888888",
        parent_id: int | None = None,
        is_savings: bool = False,
        icon: str = "",
    ) -> dict:
        existing = self.get_category_by_name(name, cat_type)
        if existing is not None:
            if is_savings and int(existing.get("is_savings") or 0) == 0:
                self._set_category_is_savings(int(existing["id"]), True)
                refreshed = self.get_category_by_id(int(existing["id"]))
                if refreshed is not None:
                    return refreshed
            return existing
        return self.add_category(
            name=name,
            cat_type=cat_type,
            color=color,
            parent_id=parent_id,
            is_savings=is_savings,
            icon=icon,
        )

    def _update_category_metadata_direct(
        self,
        cat_id: int,
        *,
        color: str | None = None,
        is_savings: bool | None = None,
        parent_id: int | None | object = _UNSET,
        icon: str | None = None,
    ) -> dict:
        updates: dict[str, object | None] = {}
        if color is not None:
            updates["color"] = color
        if is_savings is not None:
            updates["is_savings"] = is_savings
        if parent_id is not _UNSET:
            updates["parent_id"] = cast(int | None, parent_id)
        if icon is not None:
            updates["icon"] = icon
        if updates:
            Category.update(**updates).where(Category.id == cat_id).execute()
        refreshed = self.get_category_by_id(cat_id)
        if refreshed is None:
            raise ValueError(f"Category {cat_id} not found")
        return refreshed

    def _find_savings_goals_parent_category(self) -> dict | None:
        for name in self._savings_goals_parent_name_candidates():
            existing = self.get_category_by_name(name)
            if existing is None:
                continue
            if str(existing["type"]) != "expense":
                raise ValueError(f"Category '{name}' exists but is not an expense category")
            return existing
        return None

    def _is_savings_goals_parent_category(self, cat_id: int) -> bool:
        parent = self._find_savings_goals_parent_category()
        return parent is not None and int(parent["id"]) == cat_id

    def _ensure_savings_goals_parent_category(self) -> dict:
        parent = self._find_savings_goals_parent_category()
        if parent is None:
            return self.add_category(
                name=_SAVINGS_GOALS_PARENT_NAMES[self._database_language()],
                cat_type="expense",
                color=_SAVINGS_GOALS_PARENT_COLOR,
                is_savings=True,
            )
        updates: dict[str, object] = {}
        if int(parent.get("is_savings") or 0) == 0:
            updates["is_savings"] = True
        if parent.get("parent_id") is not None:
            updates["parent_id"] = None
        if updates:
            return self._update_category_metadata_direct(
                int(parent["id"]),
                is_savings=cast(bool | None, updates.get("is_savings")),
                parent_id=updates.get("parent_id", _UNSET),
            )
        return parent

    def _linked_savings_goal_for_category(self, cat_id: int) -> dict | None:
        row = (
            SavingsGoal.select(SavingsGoal.id, SavingsGoal.name, SavingsGoal.category_id)
            .where(SavingsGoal.category_id == cat_id)
            .order_by(SavingsGoal.id)
            .limit(1)
            .dicts()
            .first()
        )
        return cast(dict[str, Any] | None, row)

    def _category_is_linked_to_other_goal(self, cat_id: int, *, excluding_goal_id: int | None = None) -> bool:
        query = SavingsGoal.select(SavingsGoal.id).where(SavingsGoal.category_id == cat_id)
        if excluding_goal_id is not None:
            query = query.where(SavingsGoal.id != excluding_goal_id)
        return query.limit(1).exists()

    def _reserved_savings_goals_parent_name_match(self, name: str) -> bool:
        normalized = name.strip().casefold()
        return normalized in {candidate.casefold() for candidate in _SAVINGS_GOALS_PARENT_NAMES.values()}

    def _group_savings_goal_category(self, category: dict) -> dict:
        parent = self._ensure_savings_goals_parent_category()
        if int(category["id"]) == int(parent["id"]):
            raise ValueError("Goal name cannot match the reserved savings goals group category")
        updates: dict[str, object] = {}
        if int(category.get("is_savings") or 0) == 0:
            updates["is_savings"] = True
        if category.get("parent_id") != parent["id"]:
            updates["parent_id"] = int(parent["id"])
        if updates:
            return self._update_category_metadata_direct(
                int(category["id"]),
                is_savings=cast(bool | None, updates.get("is_savings")),
                parent_id=updates.get("parent_id", _UNSET),
            )
        return category

    def _ensure_goal_linked_savings_category(self, category_name: str, *, color: str = "#3FB950") -> dict:
        normalized_name = category_name.strip()
        if self._reserved_savings_goals_parent_name_match(normalized_name):
            raise ValueError("Goal name cannot match the reserved savings goals group category")
        category = self._ensure_savings_category(normalized_name, color=color)
        return self._group_savings_goal_category(category)

    def _category_has_transaction_history(self, cat_id: int) -> bool:
        category = self.get_category_by_id(cat_id)
        if category is None:
            return False
        category_name = str(category["name"])
        normalized_name = category_name.strip().casefold()
        return (
            Transaction.select(Transaction.id)
            .where(
                (Transaction.category_id == cat_id)
                | (self._normalized_name_expression(Transaction.category) == normalized_name)
            )
            .limit(1)
            .exists()
        )

    def _assert_category_change_allowed(
        self,
        current: dict,
        *,
        new_name: str,
        new_type: str,
        new_is_savings: bool | None,
        new_parent_id: int | None | object,
    ) -> None:
        cat_id = int(current["id"])
        goal = self._linked_savings_goal_for_category(cat_id)
        is_parent = self._is_savings_goals_parent_category(cat_id)

        if goal is not None:
            current_name = str(current["name"])
            goal_name = str(goal["name"])
            if new_name != current_name:
                raise ValueError(
                    f"Category '{current_name}' is linked to savings goal '{goal_name}' and cannot be renamed here. "
                    "Edit the goal instead."
                )
            if new_type != str(current["type"]):
                raise ValueError(
                    f"Category '{current_name}' is linked to savings goal '{goal_name}' and cannot change type."
                )
            if new_is_savings is not None and not new_is_savings:
                raise ValueError(
                    f"Category '{current_name}' is linked to savings goal '{goal_name}' and must remain a savings category."
                )
            if new_parent_id is not _UNSET and new_parent_id != current.get("parent_id"):
                raise ValueError(
                    f"Category '{current_name}' is linked to savings goal '{goal_name}' and must stay in the savings goals group."
                )

        if is_parent:
            current_name = str(current["name"])
            if new_name != current_name:
                raise ValueError(f"Category '{current_name}' is reserved for grouping savings goal categories.")
            if new_type != str(current["type"]):
                raise ValueError(f"Category '{current_name}' is reserved for grouping savings goal categories.")
            if new_is_savings is not None and not new_is_savings:
                raise ValueError(f"Category '{current_name}' is reserved for grouping savings goal categories.")
            if new_parent_id is not _UNSET and new_parent_id is not None:
                raise ValueError(f"Category '{current_name}' is reserved for grouping savings goal categories.")

    def _assert_category_can_be_deleted(self, category: dict) -> None:
        cat_id = int(category["id"])
        goal = self._linked_savings_goal_for_category(cat_id)
        if goal is not None:
            raise ValueError(
                f"Category '{category['name']}' is linked to savings goal '{goal['name']}' and cannot be deleted here. "
                "Delete the goal instead."
            )
        if self._is_savings_goals_parent_category(cat_id):
            raise ValueError(f"Category '{category['name']}' is reserved for grouping savings goal categories.")

    def _assert_category_can_be_merged(self, category: dict) -> None:
        cat_id = int(category["id"])
        goal = self._linked_savings_goal_for_category(cat_id)
        if goal is not None:
            raise ValueError(
                f"Category '{category['name']}' is linked to savings goal '{goal['name']}' and cannot be merged."
            )
        if self._is_savings_goals_parent_category(cat_id):
            raise ValueError(f"Category '{category['name']}' is reserved for grouping savings goal categories.")

    def _validate_category_parent(
        self,
        cat_id: int | None,
        parent_id: int,
        cat_type: str,
    ) -> None:
        if cat_id is not None and parent_id == cat_id:
            raise ValueError("A category cannot be its own parent")
        parent = self.get_category_by_id(parent_id)
        if parent is None:
            raise ValueError(f"Parent category {parent_id} does not exist")
        if parent["type"] != cat_type:
            raise ValueError(f"Child type '{cat_type}' must match parent type '{parent['type']}'")
        if parent.get("parent_id") is not None:
            raise ValueError("Category hierarchy supports a maximum depth of 2 levels")
        if cat_id is not None:
            if Category.select(Category.id).where(Category.parent_id == cat_id).limit(1).exists():
                raise ValueError("Category hierarchy supports a maximum depth of 2 levels")
        if cat_id is not None:
            visited: set[int] = {cat_id}
            current: int | None = parent_id
            while current is not None:
                if current in visited:
                    raise ValueError("Circular category hierarchy detected")
                visited.add(current)
                ancestor = self.get_category_by_id(current)
                if ancestor is None:
                    break
                parent_value = ancestor.get("parent_id")
                current = int(cast(Any, parent_value)) if parent_value is not None else None

    def update_category(
        self,
        cat_id: int,
        name: str,
        cat_type: str,
        color: str,
        is_savings: bool | None = None,
        parent_id: int | None | object = _UNSET,
        icon: str | None = None,
    ) -> None:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Category name cannot be empty")
        current = self.get_category_by_id(cat_id)
        if current is None:
            raise ValueError(f"Category {cat_id} not found")
        if icon is not None and len(icon) > _ICON_MAX_LENGTH:
            raise ValueError(f"Category icon cannot exceed {_ICON_MAX_LENGTH} characters")
        normalized_parent_id: int | None | object = parent_id
        if normalized_parent_id is not _UNSET and normalized_parent_id is not None:
            normalized_parent_id = int(cast(Any, normalized_parent_id))
        current_parent_id = current.get("parent_id")
        if normalized_parent_id is not _UNSET and normalized_parent_id == current_parent_id:
            normalized_parent_id = _UNSET
        self._assert_category_change_allowed(
            current,
            new_name=normalized_name,
            new_type=cat_type,
            new_is_savings=is_savings,
            new_parent_id=normalized_parent_id,
        )
        if normalized_parent_id is not _UNSET and normalized_parent_id is not None:
            self._validate_category_parent(cat_id, cast(int, normalized_parent_id), cat_type)
        updates: dict[str, object | None] = {
            "name": normalized_name,
            "type": cat_type,
            "color": color,
        }
        if is_savings is not None:
            updates["is_savings"] = is_savings
        if normalized_parent_id is not _UNSET:
            updates["parent_id"] = cast(int | None, normalized_parent_id)
        if icon is not None:
            updates["icon"] = icon
        try:
            with self._atomic():
                Category.update(**updates).where(Category.id == cat_id).execute()
                RecurringTransaction.update(category=normalized_name).where(
                    RecurringTransaction.category_id == cat_id
                ).execute()
        except PeeweeIntegrityError as exc:
            raise DuplicateCategoryNameError(f"Category '{normalized_name}' already exists") from exc

    def _set_category_is_savings(self, cat_id: int, is_savings: bool) -> None:
        Category.update(is_savings=is_savings).where(Category.id == cat_id).execute()

    def _ensure_savings_category(self, category_name: str, *, color: str = "#3FB950") -> dict:
        normalized_name = category_name.strip()
        if not normalized_name:
            raise ValueError("Savings category name cannot be empty")
        existing = self.get_category_by_name(normalized_name)
        if existing is None:
            return self.add_category(
                name=normalized_name,
                cat_type="expense",
                color=color,
                is_savings=True,
            )
        if str(existing["type"]) != "expense":
            raise ValueError(f"Category '{normalized_name}' exists but is not an expense category")
        if int(existing.get("is_savings") or 0) == 0:
            self._set_category_is_savings(int(existing["id"]), True)
            refreshed = self.get_category_by_id(int(existing["id"]))
            if refreshed is not None:
                return refreshed
        return existing

    def get_subcategories(self, parent_id: int) -> list[dict]:
        query = Category.select().where(Category.parent_id == parent_id).order_by(Category.name)
        return [self._serialize_category_row(row) for row in query]

    def delete_category(self, cat_id: int) -> None:
        category = self.get_category_by_id(cat_id)
        if category is None:
            raise ValueError(f"Category {cat_id} not found")
        self._assert_category_can_be_deleted(category)
        Category.delete().where(Category.id == cat_id).execute()

    def merge_categories(self, source_cat_id: int, target_cat_id: int) -> dict:
        if source_cat_id == target_cat_id:
            raise ValueError("Source and destination categories must be different")

        source = self.get_category_by_id(source_cat_id)
        target = self.get_category_by_id(target_cat_id)
        if source is None or target is None:
            raise ValueError("Source or destination category does not exist")
        self._assert_category_can_be_merged(source)
        self._assert_category_can_be_merged(target)
        if source["type"] != target["type"]:
            raise ValueError("Cannot merge categories of different types")

        source_name = str(source["name"])
        target_name = str(target["name"])
        normalized_source_name = source_name.strip().casefold()

        with self._atomic():
            if target.get("parent_id") == source_cat_id:
                Category.update(parent_id=None).where(Category.id == target_cat_id).execute()
            Category.update(parent_id=target_cat_id).where(
                (Category.parent_id == source_cat_id) & (Category.id != target_cat_id)
            ).execute()

            Transaction.update(category=target_name).where(
                self._normalized_name_expression(Transaction.category) == normalized_source_name
            ).execute()
            Transaction.update(category_id=target_cat_id).where(Transaction.category_id == source_cat_id).execute()
            RecurringTransaction.update(category=target_name).where(
                self._normalized_name_expression(RecurringTransaction.category) == normalized_source_name
            ).execute()
            RecurringTransaction.update(category_id=target_cat_id).where(
                RecurringTransaction.category_id == source_cat_id
            ).execute()

            source_bucket = (
                Bucket.select()
                .where(self._normalized_name_expression(Bucket.name) == normalized_source_name)
                .order_by(Bucket.id)
                .first()
            )
            target_bucket = (
                Bucket.select()
                .where(self._normalized_name_expression(Bucket.name) == target_name.strip().casefold())
                .order_by(Bucket.id)
                .first()
            )
            if source_bucket and target_bucket and int(source_bucket.id) != int(target_bucket.id):
                (
                    Bucket.update(spent_amount=Bucket.spent_amount + int(source_bucket.spent_amount or 0))
                    .where(Bucket.id == int(target_bucket.id))
                    .execute()
                )
                Bucket.delete().where(Bucket.id == int(source_bucket.id)).execute()
            elif source_bucket and (target_bucket is None or int(source_bucket.id) == int(target_bucket.id)):
                Bucket.update(name=target_name).where(Bucket.id == int(source_bucket.id)).execute()

            self._merge_budget_details_for_categories(source_cat_id, target_cat_id)
            Category.delete().where(Category.id == source_cat_id).execute()

        merged = self.get_category_by_id(target_cat_id)
        if merged is None:
            raise RuntimeError(f"Failed to merge category into {target_name}")
        return merged

    def get_categories_tree(self, cat_type: str | None = None, *, include_savings: bool = True) -> list[dict]:
        all_cats = self.get_categories(cat_type, include_savings=include_savings)
        by_id: dict[int, dict] = {}
        for cat in all_cats:
            cat["children"] = []
            by_id[int(cat["id"])] = cat
        roots: list[dict] = []
        for cat in all_cats:
            pid = cat.get("parent_id")
            if pid is not None and int(pid) in by_id:
                by_id[int(pid)]["children"].append(cat)
            else:
                roots.append(cat)
        return roots

    def get_category_with_descendants(self, cat_id: int, _depth: int = 0) -> list[int]:
        if _depth > 10:
            return [cat_id]
        result = [cat_id]
        children = self.get_subcategories(cat_id)
        for child in children:
            result.extend(self.get_category_with_descendants(int(child["id"]), _depth + 1))
        return result

    def get_descendant_category_names(self, cat_id: int) -> list[str]:
        descendant_ids = self.get_category_with_descendants(cat_id)
        if not descendant_ids:
            return []
        rows = Category.select(Category.id, Category.name).where(Category.id.in_(descendant_ids)).dicts()
        names_by_id = {int(row["id"]): str(row["name"]) for row in rows}
        return [names_by_id[descendant_id] for descendant_id in descendant_ids if descendant_id in names_by_id]
