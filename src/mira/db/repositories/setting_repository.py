# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Module documentation."""

from __future__ import annotations


from datetime import date
from typing import TYPE_CHECKING, Any, cast

from mira.db import bootstrap as db_bootstrap
from mira.db import helpers as db_helpers
from mira.db.helpers import SAVINGS_GOALS_DEFAULTS, localized_savings_goals_parent_name
from mira.db.model import Currency, Setting

CURRENCY_CODES = db_helpers.CURRENCY_CODES


class SettingRepository:
    """Represent the SettingRepository class."""

    if TYPE_CHECKING:

        def _find_savings_goals_parent_category(self) -> dict[str, Any] | None:
            """Return find savings goals parent category."""
            ...

    def get(self, key: str) -> str | None:
        """Return get."""
        return self.get_setting(key)

    def get_setting(self, key: str) -> str | None:
        """Return get setting."""
        row = Setting.get_or_none(Setting.key == key)
        return row.value if row else None

    def set_setting(self, key: str, value: str) -> None:
        """Return set setting."""
        Setting.insert(key=key, value=value).on_conflict(
            conflict_target=[Setting.key],
            update={Setting.value: value},
        ).execute()

    def get_default_currency(self) -> str:
        """Return get default currency."""
        default_currency = self.get_setting("default_currency")
        if default_currency:
            return default_currency.strip().upper()
        return "USD"

    def _database_language(self) -> str:
        """Return database language."""
        language = str(self.get_setting("language") or "en").strip().lower()
        return "es" if language == "es" else "en"

    def _savings_goals_parent_name_candidates(self) -> list[str]:
        """Return savings goals parent name candidates."""
        current = SAVINGS_GOALS_DEFAULTS.name_for(self._database_language())
        candidates = [current]
        for name in SAVINGS_GOALS_DEFAULTS.all_names():
            if name not in candidates:
                candidates.append(name)
        return candidates

    def get_savings_goals_parent_name(self) -> str:
        """Return get savings goals parent name."""
        parent = self._find_savings_goals_parent_category()
        if parent is not None:
            return str(parent["name"])
        return localized_savings_goals_parent_name(self._database_language())

    def get_currencies(self, region: str | None = "americas") -> list[dict]:
        """Return get currencies."""
        query = Currency.select(Currency.code, Currency.name, Currency.region)
        if region is not None:
            query = query.where(Currency.region == region)
        return [{"code": row.code, "name": row.name, "region": row.region} for row in query.order_by(Currency.code)]

    def _default_category_seed_rows(self, lang: str) -> list[tuple[str, str, str, bool, str, str | None]]:
        """Return default category seed rows."""
        return db_bootstrap.default_category_seed_rows(lang)

    def _ensure_default_categories(self, lang: str, *, update_existing_metadata: bool) -> None:
        """Return ensure default categories."""
        bootstrap_db = cast(db_bootstrap._BootstrapDatabaseProtocol, self)
        db_bootstrap.ensure_default_categories(bootstrap_db, lang, update_existing_metadata=update_existing_metadata)

    def seed_initial_data(
        self,
        *,
        include_default_categories: bool = True,
        account_names: list[str] | None = None,
        account_specs: list[dict[str, Any]] | None = None,
        language: str = "en",
        update_existing_category_metadata: bool = True,
    ) -> None:
        """Return seed initial data."""
        bootstrap_db = cast(db_bootstrap._BootstrapDatabaseProtocol, self)
        db_bootstrap.seed_initial_data(
            bootstrap_db,
            include_default_categories=include_default_categories,
            account_names=account_names,
            account_specs=account_specs,
            language=language,
            update_existing_category_metadata=update_existing_category_metadata,
        )

    def seed_demo_data(self, *, reference_date: date | None = None) -> dict[str, Any]:
        """Return seed demo data."""
        bootstrap_db = cast(db_bootstrap._BootstrapDatabaseProtocol, self)
        return db_bootstrap.seed_demo_data(bootstrap_db, reference_date=reference_date)
