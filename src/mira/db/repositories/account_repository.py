# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Module documentation."""

from __future__ import annotations


from datetime import date
import re
from typing import TYPE_CHECKING, Any, cast

from peewee import Case, fn

from mira.db.helpers import (
    _ACCOUNT_ALIAS_STOPWORDS,
    canonical_account_type as _canonical_account_type,
    fold_text as _fold_text,
)
from mira.db.money import MONEY_ZERO, MoneyLike
from mira.db.model import Account, Transaction


class AccountRepository:
    """Represent the AccountRepository class."""

    if TYPE_CHECKING:

        def get_default_currency(self) -> str:
            """Return get default currency."""

        def _atomic(self) -> Any:
            """Return atomic."""

        def _cents_to_money(self, value: object, *, allow_none: bool = False) -> Any:
            """Return cents to money."""

        def _money_to_decimal(self, value: object, *, allow_none: bool = False) -> Any:
            """Return money to decimal."""

        def _money_to_cents(self, value: object, *, allow_none: bool = False) -> int | None:
            """Return money to cents."""

        def _round_money(self, value: object) -> Any:
            """Return round money."""

    @staticmethod
    def _normalize_account_name(name: str) -> str:
        """Return normalize account name."""
        normalized = str(name).strip()
        if not normalized:
            raise ValueError("Account name cannot be empty")
        return normalized

    @staticmethod
    def _normalize_account_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
        """Return normalize account row."""
        if row is None:
            return None
        normalized = dict(row)
        normalized["account_type"] = _canonical_account_type(cast(str | None, normalized.get("account_type")))
        return normalized

    def get_accounts(self, account_types: tuple[str, ...] | None = None) -> list[dict]:
        """Return get accounts."""
        query = Account.select().order_by(Account.name)
        if account_types:
            normalized_types = tuple(_canonical_account_type(item) for item in account_types)
            query = query.where(Account.account_type.in_(normalized_types))
        rows = [
            {
                "id": row.id,
                "name": row.name,
                "balance": self._cents_to_money(row.balance),
                "account_type": row.account_type,
                "currency": row.currency,
                "is_default": int(bool(row.is_default)),
                "created_at": row.created_at,
            }
            for row in query
        ]
        return [cast(dict, self._normalize_account_row(row)) for row in rows]

    def get_account_by_name(self, name: str) -> dict | None:
        """Return get account by name."""
        normalized_name = str(name).strip()
        if not normalized_name:
            return None
        row = (
            Account.select()
            .where(fn.LOWER(fn.TRIM(Account.name)) == normalized_name.casefold())
            .order_by(Account.id)
            .limit(1)
            .first()
        )
        if row is None:
            return None
        return self._normalize_account_row(
            {
                "id": row.id,
                "name": row.name,
                "balance": self._cents_to_money(row.balance),
                "account_type": row.account_type,
                "currency": row.currency,
                "is_default": int(bool(row.is_default)),
                "created_at": row.created_at,
            }
        )

    def get_account_by_id(self, account_id: int) -> dict | None:
        """Return get account by id."""
        row = Account.get_or_none(Account.id == account_id)
        if row is None:
            return None
        return self._normalize_account_row(
            {
                "id": row.id,
                "name": row.name,
                "balance": self._cents_to_money(row.balance),
                "account_type": row.account_type,
                "currency": row.currency,
                "is_default": int(bool(row.is_default)),
                "created_at": row.created_at,
            }
        )

    def get_or_create_account(self, name: str) -> dict:
        """Return get or create account."""
        normalized_name = self._normalize_account_name(name)
        account = self.get_account_by_name(normalized_name)
        if account is None:
            Account.create(name=normalized_name, currency=self.get_default_currency())
            account = self.get_account_by_name(normalized_name)
        if account is None:
            raise RuntimeError("Failed to create or retrieve account")
        return account

    def add_account(
        self,
        name: str,
        account_type: str = "bank",
        opening_balance: MoneyLike = 0.0,
        currency: str | None = None,
    ) -> dict:
        """Return add account."""
        normalized_name = self._normalize_account_name(name)
        normalized_type = _canonical_account_type(account_type)
        selected_currency = str(currency or self.get_default_currency()).strip().upper()
        Account.create(
            name=normalized_name,
            account_type=normalized_type,
            balance=self._money_to_cents(opening_balance),
            currency=selected_currency,
        )
        result = self.get_account_by_name(normalized_name)
        if result is None:
            raise RuntimeError("Failed to create account")
        return result

    def update_account(
        self,
        account_id: int,
        name: str,
        account_type: str,
        currency: str | None = None,
    ) -> None:
        """Return update account."""
        normalized_name = self._normalize_account_name(name)
        normalized_type = _canonical_account_type(account_type)
        selected_currency = str(currency or self.get_default_currency()).strip().upper()
        (
            Account.update(name=normalized_name, account_type=normalized_type, currency=selected_currency)
            .where(Account.id == account_id)
            .execute()
        )

    def delete_account(self, account_id: int) -> None:
        """Return delete account."""
        Account.delete().where(Account.id == account_id).execute()

    def set_default_account(self, account_id: int) -> None:
        """Return set default account."""
        if self.get_account_by_id(account_id) is None:
            raise ValueError(f"Account {account_id} not found")
        with self._atomic():
            Account.update(is_default=False).execute()
            Account.update(is_default=True).where(Account.id == account_id).execute()

    def get_default_account(self) -> dict | None:
        """Return get default account."""
        row = Account.select().where(Account.is_default == True).limit(1).first()  # noqa: E712
        if row is None:
            return None
        return self._normalize_account_row(
            {
                "id": row.id,
                "name": row.name,
                "balance": self._cents_to_money(row.balance),
                "account_type": row.account_type,
                "currency": row.currency,
                "is_default": int(bool(row.is_default)),
                "created_at": row.created_at,
            }
        )

    def get_credit_accounts(self) -> list[dict]:
        """Return get credit accounts."""
        return self.get_accounts(("credit",))

    def is_credit_account(self, account_id: int) -> bool:
        """Return whether credit account."""
        account = self.get_account_by_id(account_id)
        return account is not None and str(account.get("account_type") or "") == "credit"

    @staticmethod
    def _account_aliases(account_name: str) -> set[str]:
        """Return account aliases."""
        folded_name = _fold_text(account_name)
        if not folded_name:
            return set()
        aliases = {folded_name}
        for token in folded_name.split():
            if len(token) < 3 or token in _ACCOUNT_ALIAS_STOPWORDS:
                continue
            aliases.add(token)
        return aliases

    def find_account_mentions(self, text: str, *, account_types: tuple[str, ...] | None = None) -> list[dict]:
        """Return find account mentions."""
        folded_text = _fold_text(text)
        if not folded_text:
            return []

        matches: list[tuple[int, int, dict[str, Any]]] = []
        for account in self.get_accounts(account_types):
            best_alias: tuple[int, int] | None = None
            best_pos: int | None = None
            for alias in self._account_aliases(str(account.get("name") or "")):
                pattern = re.compile(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])")
                found = pattern.search(folded_text)
                if found is None:
                    continue
                score = (len(alias.split()), len(alias))
                if best_alias is None or score > best_alias:
                    best_alias = score
                    best_pos = found.start()
            if best_alias is not None and best_pos is not None:
                matches.append((best_pos, -best_alias[0], cast(dict[str, Any], account)))

        matches.sort(key=lambda item: (item[0], item[1], str(item[2].get("name") or "").casefold()))
        return [item[2] for item in matches]

    def get_account_balance_report(self) -> dict[str, Any]:
        """Return get account balance report."""
        default_currency = self.get_default_currency()
        rows: list[dict[str, Any]] = []
        consolidated_total = MONEY_ZERO
        for account in self.get_accounts():
            balance = self._money_to_decimal(account.get("balance")) or MONEY_ZERO
            consolidated_balance = balance
            consolidated_total += consolidated_balance
            rows.append(
                {
                    "id": int(account["id"]),
                    "name": str(account.get("name") or ""),
                    "account_type": str(account.get("account_type") or "bank"),
                    "currency": str(account.get("currency") or default_currency),
                    "balance": balance,
                    "consolidated_balance": consolidated_balance,
                }
            )
        return {
            "default_currency": default_currency,
            "rows": rows,
            "consolidated_total": self._round_money(consolidated_total),
        }

    def get_account_balance_as_of(
        self,
        account_id: int,
        on_date: str,
        *,
        exclude_transaction_id: int | None = None,
    ) -> dict[str, Any]:
        """Return get account balance as of."""
        account = self.get_account_by_id(account_id)
        if account is None:
            raise ValueError(f"Account {account_id} not found")

        normalized_date = str(on_date or "").strip()
        try:
            target_day = date.fromisoformat(normalized_date)
        except ValueError as exc:
            raise ValueError(f"Invalid balance date: {normalized_date!r}. Expected YYYY-MM-DD.") from exc

        current_balance = self._money_to_decimal(account.get("balance")) or MONEY_ZERO
        if exclude_transaction_id is not None:
            excluded_tx = Transaction.get_or_none(
                (Transaction.id == int(exclude_transaction_id)) & (Transaction.account_id == int(account_id))  # type: ignore[attr-defined]
            )
            if excluded_tx is not None:
                excluded_amount = self._cents_to_money(excluded_tx.amount) or MONEY_ZERO
                excluded_effect = excluded_amount if str(excluded_tx.type or "") == "income" else -excluded_amount
                current_balance -= excluded_effect

        future_effect_query = Transaction.select(
            fn.COALESCE(
                fn.SUM(
                    Case(
                        None,
                        (
                            ((Transaction.type == "income"), Transaction.amount),
                            ((Transaction.type == "expense"), Transaction.amount * -1),
                        ),
                        0,
                    )
                ),
                0,
            ).alias("net_effect_cents")
        ).where(
            (Transaction.account_id == int(account_id)) & (Transaction.date > target_day)  # type: ignore[attr-defined]
        )
        if exclude_transaction_id is not None:
            future_effect_query = future_effect_query.where(Transaction.id != int(exclude_transaction_id))

        future_effect = self._cents_to_money(future_effect_query.scalar()) or MONEY_ZERO
        balance_as_of = self._round_money(current_balance - future_effect)
        return {
            "account_id": int(account["id"]),
            "currency": str(account.get("currency") or self.get_default_currency()).strip().upper(),
            "balance_as_of": balance_as_of,
        }

    def update_account_balance(self, account_id: int, delta: MoneyLike) -> None:
        """Return update account balance."""
        delta_cents = self._money_to_cents(delta) or 0
        Account.update(balance=Account.balance + delta_cents).where(Account.id == account_id).execute()
