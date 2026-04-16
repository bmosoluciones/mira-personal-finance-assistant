# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import calendar
from decimal import Decimal
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, cast

from peewee import JOIN, Case, fn

from mira.db.money import MONEY_ZERO, MoneyLike
from mira.db.model import Account, BudgetDetail, Category, Transaction, TransactionTag
from mira.transaction_kinds import (
    BALANCE_ADJUSTMENT_PAYMENT_METHOD,
    TransactionType,
    analytics_included_expr,
    is_analytics_excluded_transaction,
    is_balance_adjustment_transaction,
    localized_balance_adjustment_description,
)


class TransactionRepository:
    if TYPE_CHECKING:

        def _money_to_decimal(self, value: object, *, allow_none: bool = False) -> Any: ...
        def _cents_to_decimal(self, value: object, *, allow_none: bool = False) -> Any: ...
        def _money_to_cents(self, value: object, *, allow_none: bool = False) -> int | None: ...
        def _round_money(self, value: object) -> Any: ...
        def _atomic(self) -> Any: ...

        def get_category(
            self,
            *,
            cat_id: int | None = None,
            name: str | None = None,
            cat_type: str | None = None,
        ) -> dict[str, Any] | None: ...

        def get_category_by_name(self, name: str, cat_type: str | None = None) -> dict[str, Any] | None: ...
        def get_descendant_category_names(self, cat_id: int) -> list[str]: ...
        def get_default_budget_for_year(self, year: int) -> dict[str, Any] | None: ...
        def update_account_balance(self, account_id: int, delta: MoneyLike) -> None: ...
        def _apply_savings_goal_delta_for_transaction(self, tx: dict[str, Any] | None, sign: int) -> None: ...

        def select_best_operation_message(
            self, tx: dict[str, Any], *, source: str | None = None
        ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]: ...

        def get_accounts(self, account_types: tuple[str, ...] | None = None) -> list[dict[str, Any]]: ...
        def get_account_by_id(self, account_id: int) -> dict[str, Any] | None: ...
        def get_setting(self, key: str) -> str | None: ...

    _MAX_TRANSACTION_AMOUNT = 10_000_000_000

    def _validate_tx_date(self, tx_date: Any) -> str:
        value = str(tx_date or date.today().isoformat()).strip()
        if "T" in value or " " in value:
            try:
                parsed_dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed_dt.date().isoformat()
            except ValueError:
                pass
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"Invalid transaction date: {value!r}. Expected YYYY-MM-DD.") from exc
        return parsed.date().isoformat()

    def _validate_tx_amount(self, amount: Any) -> Decimal:
        value = self._money_to_decimal(amount) or MONEY_ZERO
        limit = self._money_to_decimal(self._MAX_TRANSACTION_AMOUNT) or MONEY_ZERO
        if abs(value) > limit:
            raise ValueError(f"Amount {value} out of valid range [±{self._MAX_TRANSACTION_AMOUNT:g}]")
        return value

    def _resolve_transaction_category_id(self, tx_type: str, category: str | None) -> int | None:
        category_row = self.get_category(name=category, cat_type=tx_type)
        if category_row is None or category_row.get("id") is None:
            return None
        return int(category_row["id"])

    def _month_window(self, year: int, month: int) -> tuple[str, str]:
        last_day = calendar.monthrange(year, month)[1]
        return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last_day:02d}"

    def _validate_balance_adjustment_account(self, account_id: int) -> dict[str, Any]:
        account = self.get_account_by_id(account_id)
        if account is None:
            raise ValueError(f"Account {account_id} not found.")
        if str(account.get("account_type") or "") not in {"bank", "credit"}:
            raise ValueError("Balance adjustments are only available for bank and credit accounts.")
        return account

    def _normalize_balance_adjustment_payload(
        self,
        account_id: int,
        signed_amount: MoneyLike,
        tx_date: str | None,
    ) -> tuple[str, Decimal, str, str]:
        self._validate_balance_adjustment_account(account_id)
        normalized_signed_amount = self._money_to_decimal(signed_amount) or MONEY_ZERO
        if normalized_signed_amount == MONEY_ZERO:
            raise ValueError("Balance adjustment amount cannot be zero.")
        normalized_date = self._validate_tx_date(tx_date or date.today().isoformat())
        tx_type = TransactionType.INCOME if normalized_signed_amount > MONEY_ZERO else TransactionType.EXPENSE
        absolute_amount = abs(normalized_signed_amount)
        description = localized_balance_adjustment_description(self.get_setting("language"))
        return tx_type, absolute_amount, normalized_date, description

    def _serialize_transaction_row(self, row: Transaction) -> dict[str, Any]:
        # Rehydrate exact cents from SQLite into the decimal contract expected
        # by the rest of the app and export/reporting layers.
        date_value = row.date.isoformat() if hasattr(row.date, "isoformat") else row.date
        created_raw = row.created_at
        if isinstance(created_raw, datetime):
            created_value: Any = created_raw.strftime("%Y-%m-%d %H:%M:%S")
        else:
            created_value = created_raw
        return {
            "id": row.id,
            "account_id": row.account_id,  # type: ignore[attr-defined]
            "type": row.type,
            "amount": self._cents_to_decimal(row.amount),
            "description": row.description,
            "category": row.category,
            "category_id": row.category_id,
            "subcategory": row.subcategory,
            "note": row.note,
            "payment_method": row.payment_method,
            "receipt_path": row.receipt_path,
            "to_account_id": row.to_account_id,
            "is_transfer": int(bool(row.is_transfer)),
            "exchange_rate": row.exchange_rate,
            "converted_amount": self._cents_to_decimal(row.converted_amount, allow_none=True),
            "date": date_value,
            "created_at": created_value,
        }

    def build_monthly_context(self, tx: dict[str, Any]) -> dict[str, Any]:
        tx_date = self._validate_tx_date(tx.get("date"))
        year = int(tx_date[:4])
        month = int(tx_date[5:7])
        period_key = f"{year:04d}-{month:02d}"
        date_start, date_end = self._month_window(year, month)
        tx_type = str(tx.get("type") or "")
        tx_amount = self._validate_tx_amount(tx.get("amount"))
        tx_category_id = tx.get("category_id")
        category_id = int(tx_category_id) if tx_category_id is not None else None
        category_name = str(tx.get("category") or "").strip()

        totals = (
            Transaction.select(
                fn.COALESCE(
                    fn.SUM(Case(None, (((Transaction.type == TransactionType.INCOME), Transaction.amount),), 0)),
                    0,
                ).alias("income_actual"),
                fn.COALESCE(
                    fn.SUM(Case(None, (((Transaction.type == TransactionType.EXPENSE), Transaction.amount),), 0)),
                    0,
                ).alias("expense_actual"),
                fn.COALESCE(
                    fn.SUM(
                        Case(
                            None,
                            (
                                (
                                    (Transaction.type == TransactionType.EXPENSE)
                                    & (fn.COALESCE(Category.is_savings, 0) == 1),
                                    Transaction.amount,
                                ),
                            ),
                            0,
                        )
                    ),
                    0,
                ).alias("savings_actual"),
                fn.COALESCE(
                    fn.AVG(Case(None, (((Transaction.type == TransactionType.INCOME), Transaction.amount),), None)), 0
                ).alias("income_avg_amount"),
                fn.COALESCE(fn.SUM(Case(None, (((Transaction.type == TransactionType.INCOME), 1),), 0)), 0).alias(
                    "income_total_count"
                ),
            )
            .join(Category, JOIN.LEFT_OUTER, on=(Category.id == Transaction.category_id))
            .where(analytics_included_expr(Transaction) & (Transaction.date.between(date_start, date_end)))
            .dicts()
            .get()
        )

        budget = self.get_default_budget_for_year(year)
        income_goal = MONEY_ZERO
        expense_budget = MONEY_ZERO
        category_budget = MONEY_ZERO
        savings_expected = MONEY_ZERO
        if budget is not None:
            budget_rows = (
                BudgetDetail.select(
                    Category.id,
                    Category.type,
                    Category.is_savings,
                    fn.COALESCE(fn.SUM(BudgetDetail.amount), 0).alias("amount"),
                )
                .join(Category, on=(Category.id == BudgetDetail.category))
                .where(
                    (BudgetDetail.budget == int(budget["id"]))
                    & (BudgetDetail.year == year)
                    & (BudgetDetail.month == month)
                )
                .group_by(Category.id, Category.type, Category.is_savings)
                .dicts()
            )
            for row in budget_rows:
                amount = self._cents_to_decimal(row["amount"]) or MONEY_ZERO
                if row["type"] == TransactionType.INCOME:
                    income_goal += amount
                else:
                    expense_budget += amount
                    if int(row.get("is_savings") or 0) == 1:
                        savings_expected += amount
                if category_id is not None and int(row["id"]) == category_id:
                    category_budget = amount

        category_spent_current = MONEY_ZERO
        expense_avg_amount = MONEY_ZERO
        expense_total_count = 0
        if category_id is not None:
            category_stats = (
                Transaction.select(
                    fn.COALESCE(fn.SUM(Transaction.amount), 0).alias("total"),
                    fn.COALESCE(fn.AVG(Transaction.amount), 0).alias("avg_amount"),
                    fn.COUNT(Transaction.id).alias("total_count"),
                )
                .where(
                    analytics_included_expr(Transaction)
                    & (Transaction.type == TransactionType.EXPENSE)
                    & (Transaction.category_id == category_id)
                    & (Transaction.date.between(date_start, date_end))
                )
                .dicts()
                .get()
            )
            category_spent_current = self._cents_to_decimal(category_stats["total"]) or MONEY_ZERO
            expense_avg_amount = self._cents_to_decimal(category_stats["avg_amount"]) or MONEY_ZERO
            expense_total_count = int(category_stats["total_count"] or 0)

        savings_actual = self._cents_to_decimal(totals["savings_actual"]) or MONEY_ZERO
        income_actual = self._cents_to_decimal(totals["income_actual"]) or MONEY_ZERO
        expense_actual = self._cents_to_decimal(totals["expense_actual"]) or MONEY_ZERO

        prev_income_actual = (
            max(MONEY_ZERO, income_actual - tx_amount) if tx_type == TransactionType.INCOME else income_actual
        )
        prev_expense_actual = (
            max(MONEY_ZERO, expense_actual - tx_amount) if tx_type == TransactionType.EXPENSE else expense_actual
        )
        prev_category_spent = (
            max(MONEY_ZERO, category_spent_current - tx_amount)
            if tx_type == TransactionType.EXPENSE and category_id is not None
            else category_spent_current
        )

        income_count = int(totals["income_total_count"] or 0)
        expense_count = expense_total_count
        income_avg_prev = (
            ((income_actual - tx_amount) / max(1, income_count - 1))
            if tx_type == TransactionType.INCOME and income_count > 1
            else (
                self._cents_to_decimal(totals["income_avg_amount"]) or MONEY_ZERO
                if income_count > 0 and tx_type != TransactionType.INCOME
                else None
            )
        )
        expense_avg_prev = (
            ((category_spent_current - tx_amount) / max(1, expense_count - 1))
            if tx_type == TransactionType.EXPENSE and expense_count > 1
            else (expense_avg_amount if expense_count > 0 and tx_type != TransactionType.EXPENSE else None)
        )

        day_of_month = int(tx_date[8:10]) if len(tx_date) >= 10 else date.today().day
        month_days = calendar.monthrange(year, month)[1]

        return {
            "period_key": period_key,
            "year": year,
            "month": month,
            "day_of_month": day_of_month,
            "month_days": month_days,
            "category_id": category_id,
            "category_name": category_name,
            "income_actual": self._round_money(income_actual),
            "income_actual_prev": self._round_money(prev_income_actual),
            "income_goal": self._round_money(income_goal),
            "expense_actual": self._round_money(expense_actual),
            "expense_actual_prev": self._round_money(prev_expense_actual),
            "expense_budget": self._round_money(expense_budget),
            "category_spent": self._round_money(category_spent_current),
            "category_spent_prev": self._round_money(prev_category_spent),
            "category_budget": self._round_money(category_budget),
            "savings_expected": self._round_money(savings_expected),
            "savings_actual": self._round_money(savings_actual),
            "income_avg_prev": self._round_money(income_avg_prev) if income_avg_prev is not None else None,
            "expense_category_avg_prev": self._round_money(expense_avg_prev) if expense_avg_prev is not None else None,
        }

    def add_transaction(
        self,
        *,
        account_id: int,
        tx_type: str,
        amount: MoneyLike,
        description: str | None = None,
        category: str | None = None,
        subcategory: str | None = None,
        payment_method: str = "cash",
        receipt_path: str | None = None,
        tx_date: str | None = None,
        note: str | None = None,
        to_account_id: int | None = None,
        is_transfer: int = 0,
        exchange_rate: float | None = None,
        converted_amount: MoneyLike | None = None,
        category_id: int | None = None,
        source: str | None = None,
    ) -> dict:
        if tx_date is None:
            tx_date = date.today().isoformat()
        normalized_amount = self._validate_tx_amount(amount)
        resolved_category_id = (
            int(category_id) if category_id is not None else self._resolve_transaction_category_id(tx_type, category)
        )
        with self._atomic():
            tx = Transaction.create(
                account=account_id,
                type=tx_type,
                amount=self._money_to_cents(normalized_amount),
                description=description,
                category=category,
                category_id=resolved_category_id,
                date=tx_date,
                subcategory=subcategory,
                payment_method=payment_method,
                receipt_path=receipt_path,
                note=note,
                to_account_id=to_account_id,
                is_transfer=bool(is_transfer),
                exchange_rate=exchange_rate,
                converted_amount=self._money_to_cents(converted_amount, allow_none=True),
            )
            delta = normalized_amount if tx_type == TransactionType.INCOME else -normalized_amount
            self.update_account_balance(account_id, delta)
            tx_data = self._serialize_transaction_row(tx)
            self._apply_savings_goal_delta_for_transaction(tx_data, sign=1)
        if is_analytics_excluded_transaction(tx_data):
            tx_data["mira_achievement"] = None
            tx_data["mira_insight"] = None
        else:
            achievement, insight = self.select_best_operation_message(tx_data, source=source)
            tx_data["mira_achievement"] = achievement
            tx_data["mira_insight"] = insight
        return tx_data

    def get_transaction_by_id(self, tx_id: int) -> dict | None:
        row = Transaction.get_or_none(Transaction.id == tx_id)
        return self._serialize_transaction_row(row) if row is not None else None

    def delete_transaction(self, tx_id: int) -> None:
        # Policy: message_events are immutable historical records and must not
        # be deleted when transactions are edited or removed.
        tx = self.get_transaction_by_id(tx_id)
        if tx is None:
            return
        with self._atomic():
            self._apply_savings_goal_delta_for_transaction(tx, sign=-1)
            if tx["account_id"] is not None:
                amount_value = self._money_to_decimal(tx.get("amount")) or MONEY_ZERO
                delta = amount_value if tx["type"] == TransactionType.INCOME else -amount_value
                self.update_account_balance(tx["account_id"], -delta)
            Transaction.delete().where(Transaction.id == tx_id).execute()

    def update_transaction(self, tx_id: int, **kwargs: object) -> dict:
        # Policy: message_events are immutable historical records and must not
        # be deleted when transactions are edited or removed.
        old = self.get_transaction_by_id(tx_id)
        if old is None:
            raise ValueError(f"Transaction {tx_id} not found")

        new_account_id_raw: Any = kwargs.get("account_id", old["account_id"])
        new_account_id = int(new_account_id_raw) if new_account_id_raw is not None else None
        new_type = str(kwargs.get("tx_type", old["type"]))
        new_amount_raw = kwargs.get("amount", old["amount"])
        if new_amount_raw is None:
            raise ValueError("Transaction amount cannot be empty")
        new_amount = self._validate_tx_amount(new_amount_raw)
        new_description = kwargs.get("description", old["description"])
        new_category = kwargs.get("category", old["category"])
        new_subcategory = kwargs.get("subcategory", old.get("subcategory"))
        new_payment_method = kwargs.get("payment_method", old.get("payment_method", "cash"))
        new_receipt_path = kwargs.get("receipt_path", old.get("receipt_path"))
        new_date = kwargs.get("tx_date", old["date"])
        new_note = kwargs.get("note", old.get("note"))
        new_exchange_rate = kwargs.get("exchange_rate", old.get("exchange_rate"))
        new_converted_amount = kwargs.get("converted_amount", old.get("converted_amount"))
        if "category_id" in kwargs:
            explicit_category_id = kwargs.get("category_id")
            new_category_id = int(cast(Any, explicit_category_id)) if explicit_category_id is not None else None
        elif "category" in kwargs or "tx_type" in kwargs:
            new_category_id = self._resolve_transaction_category_id(str(new_type), cast(str | None, new_category))
        else:
            old_category_id = old.get("category_id")
            new_category_id = int(cast(Any, old_category_id)) if old_category_id is not None else None

        result: dict[str, Any] | None = None
        with self._atomic():
            self._apply_savings_goal_delta_for_transaction(old, sign=-1)
            if old["account_id"] is not None:
                old_amount = self._money_to_decimal(old.get("amount")) or MONEY_ZERO
                old_delta = old_amount if old["type"] == TransactionType.INCOME else -old_amount
                self.update_account_balance(int(old["account_id"]), -old_delta)
            if new_account_id is not None:
                new_delta = new_amount if new_type == TransactionType.INCOME else -new_amount
                self.update_account_balance(new_account_id, new_delta)
            (
                Transaction.update(
                    account=new_account_id,
                    type=new_type,
                    amount=self._money_to_cents(new_amount),
                    description=new_description,
                    category=new_category,
                    subcategory=new_subcategory,
                    category_id=new_category_id,
                    payment_method=new_payment_method,
                    receipt_path=new_receipt_path,
                    date=new_date,
                    note=new_note,
                    exchange_rate=new_exchange_rate,
                    converted_amount=self._money_to_cents(new_converted_amount, allow_none=True),
                )
                .where(Transaction.id == tx_id)
                .execute()
            )
            result = self.get_transaction_by_id(tx_id)
            if result is not None:
                self._apply_savings_goal_delta_for_transaction(result, sign=1)
        if result is None:
            raise RuntimeError(f"Failed to update transaction {tx_id}")
        return result

    def update_transaction_account(self, tx_id: int, account_id: int) -> dict:
        if self.get_account_by_id(account_id) is None:
            raise ValueError(f"Account {account_id} not found")
        return self.update_transaction(tx_id, account_id=account_id)

    def update_transaction_category(self, tx_id: int, category: str | None) -> dict:
        normalized = (category or "").strip() or None
        return self.update_transaction(tx_id, category=normalized)

    def get_transactions(
        self,
        *,
        limit: int = 50,
        tx_type: str | None = None,
        account_id: int | None = None,
        since_date: str | None = None,
        until_date: str | None = None,
        category: str | None = None,
        payment_method: str | None = None,
        min_amount: MoneyLike | None = None,
        max_amount: MoneyLike | None = None,
        search: str | None = None,
        tag_id: int | None = None,
        include_children: bool = False,
    ) -> list[dict]:
        query = Transaction.select()
        if tx_type:
            query = query.where(Transaction.type == tx_type)
        if account_id is not None:
            query = query.where(Transaction.account == account_id)
        if since_date:
            query = query.where(Transaction.date >= since_date)
        if until_date:
            query = query.where(Transaction.date <= until_date)
        if category:
            if include_children:
                cat_row = self.get_category_by_name(category)
                if cat_row is not None:
                    names = self.get_descendant_category_names(int(cat_row["id"]))
                    query = query.where(Transaction.category.in_(names))
                else:
                    query = query.where(Transaction.category == category)
            else:
                query = query.where(Transaction.category == category)
        if payment_method:
            query = query.where(Transaction.payment_method == payment_method)
        if min_amount is not None:
            query = query.where(Transaction.amount >= (self._money_to_cents(min_amount) or 0))
        if max_amount is not None:
            query = query.where(Transaction.amount <= (self._money_to_cents(max_amount) or 0))
        if search:
            query = query.where((Transaction.description.contains(search)) | (Transaction.note.contains(search)))
        if tag_id is not None:
            tagged_ids = TransactionTag.select(TransactionTag.transaction_id).where(TransactionTag.tag == tag_id)
            query = query.where(Transaction.id.in_(tagged_ids))

        rows_raw = list(query.order_by(Transaction.date.desc(), Transaction.id.desc()).limit(limit))
        referenced_ids = {int(row.account_id) for row in rows_raw if row.account_id is not None}
        account_name_by_id: dict[int, str] = {}
        if referenced_ids:
            for acc_row in Account.select(Account.id, Account.name).where(Account.id.in_(referenced_ids)).dicts():
                account_name_by_id[int(acc_row["id"])] = str(acc_row.get("name") or "")
        rows: list[dict] = []
        for row in rows_raw:
            item = self._serialize_transaction_row(row)
            account_key = item.get("account_id")
            item["account_name"] = None if account_key is None else account_name_by_id.get(int(account_key))
            rows.append(item)
        return rows

    def transfer_between_accounts(
        self,
        from_account_id: int,
        to_account_id: int,
        amount: MoneyLike,
        note: str | None = None,
        tx_date: str | None = None,
        exchange_rate: float | None = None,
        converted_amount: MoneyLike | None = None,
        description: str | None = None,
    ) -> tuple[dict, dict]:
        if from_account_id == to_account_id:
            raise ValueError("Source and destination accounts must be different.")
        normalized_amount = self._money_to_decimal(amount) or MONEY_ZERO
        if normalized_amount <= MONEY_ZERO:
            raise ValueError("Transfer amount must be greater than zero.")
        from_acc = self.get_account_by_id(from_account_id)
        to_acc = self.get_account_by_id(to_account_id)
        if from_acc is None:
            raise ValueError(f"Source account {from_account_id} not found.")
        if to_acc is None:
            raise ValueError(f"Destination account {to_account_id} not found.")
        if str(from_acc.get("account_type") or "") == "credit" and str(to_acc.get("account_type") or "") == "credit":
            raise ValueError("Credit accounts cannot be both source and destination in the same transfer.")
        from_name = from_acc["name"] if from_acc else f"#{from_account_id}"
        to_name = to_acc["name"] if to_acc else f"#{to_account_id}"
        tx_date_val = tx_date or date.today().isoformat()
        from_currency = (from_acc or {}).get("currency", "NIO")
        to_currency = (to_acc or {}).get("currency", "NIO")

        debit_desc = description or f"Transfer to {to_name}"
        credit_desc = description or f"Transfer from {from_name}"

        credit_amount = normalized_amount
        applied_rate: float | None = None
        if from_currency != to_currency:
            normalized_converted = self._money_to_decimal(converted_amount, allow_none=True)
            if normalized_converted is not None and normalized_converted > MONEY_ZERO:
                credit_amount = normalized_converted
                if normalized_amount > MONEY_ZERO:
                    applied_rate = float(credit_amount / normalized_amount)
            elif exchange_rate is not None and exchange_rate > 0:
                applied_rate = exchange_rate
                credit_amount = self._round_money(normalized_amount * Decimal(str(exchange_rate)))
            else:
                raise ValueError("Exchange rate or converted amount is required for cross-currency transfers.")

        detail = note or ""
        if from_currency != to_currency:
            fx_note = f"FX {from_currency}->{to_currency}"
            if applied_rate is not None:
                fx_note += f" @ {applied_rate:.6f}"
            detail = f"{detail} | {fx_note}".strip(" |")

        with self._atomic():
            expense_tx = Transaction.create(
                account=from_account_id,
                type=TransactionType.EXPENSE,
                amount=self._money_to_cents(normalized_amount),
                description=debit_desc,
                category=None,
                date=tx_date_val,
                note=detail,
                to_account_id=to_account_id,
                is_transfer=True,
                exchange_rate=applied_rate,
                converted_amount=self._money_to_cents(credit_amount),
                payment_method="cash",
            )
            self.update_account_balance(from_account_id, -normalized_amount)

            income_tx = Transaction.create(
                account=to_account_id,
                type=TransactionType.INCOME,
                amount=self._money_to_cents(credit_amount),
                description=credit_desc,
                category=None,
                date=tx_date_val,
                note=detail,
                to_account_id=from_account_id,
                is_transfer=True,
                exchange_rate=applied_rate,
                converted_amount=self._money_to_cents(credit_amount),
                payment_method="cash",
            )
            self.update_account_balance(to_account_id, credit_amount)

        expense = self.get_transaction_by_id(int(expense_tx.id))  # type: ignore[call-overload]
        income = self.get_transaction_by_id(int(income_tx.id))  # type: ignore[call-overload]
        if expense is None or income is None:
            raise RuntimeError("Failed to create transfer transactions")
        return expense, income

    def record_credit_card_payment(
        self,
        from_account_id: int,
        credit_account_id: int,
        amount: MoneyLike,
        *,
        note: str | None = None,
        tx_date: str | None = None,
        exchange_rate: float | None = None,
        converted_amount: MoneyLike | None = None,
        description: str | None = None,
    ) -> tuple[dict, dict]:
        if from_account_id == credit_account_id:
            raise ValueError("Source and destination accounts must be different.")
        normalized_amount = self._money_to_decimal(amount) or MONEY_ZERO
        if normalized_amount <= MONEY_ZERO:
            raise ValueError("Credit card payment amount must be greater than zero.")

        from_acc = self.get_account_by_id(from_account_id)
        credit_acc = self.get_account_by_id(credit_account_id)
        if from_acc is None:
            raise ValueError(f"Source account {from_account_id} not found.")
        if credit_acc is None:
            raise ValueError(f"Credit account {credit_account_id} not found.")

        from_type = str(from_acc.get("account_type") or "bank")
        to_type = str(credit_acc.get("account_type") or "bank")
        if from_type not in {"bank", "cash"}:
            raise ValueError("Credit card payments must originate from a bank or cash account.")
        if to_type != "credit":
            raise ValueError("Credit card payments must target an account of type credit.")

        created_at_raw = str(credit_acc.get("created_at") or "")[:19]
        created_day: date | None = None
        if created_at_raw:
            created_day = datetime.fromisoformat(created_at_raw.replace(" ", "T")).date()

        if tx_date is None:
            tx_day = date.today()
            if created_day is not None and tx_day < created_day:
                tx_day = created_day
            effective_date = tx_day.isoformat()
        else:
            effective_date = tx_date
            try:
                tx_day = date.fromisoformat(effective_date)
            except ValueError as exc:
                raise ValueError("Payment date must be a valid ISO date YYYY-MM-DD.") from exc

        if created_day is not None and tx_day < created_day:
            raise ValueError("Credit card payments cannot be dated before the destination account was created.")

        payment_description = description or f"Credit card payment to {credit_acc['name']}"
        return self.transfer_between_accounts(
            from_account_id=from_account_id,
            to_account_id=credit_account_id,
            amount=normalized_amount,
            note=note,
            tx_date=effective_date,
            exchange_rate=exchange_rate,
            converted_amount=converted_amount,
            description=payment_description,
        )

    def record_balance_adjustment(
        self,
        account_id: int,
        signed_amount: MoneyLike,
        *,
        tx_date: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        tx_type, absolute_amount, normalized_date, description = self._normalize_balance_adjustment_payload(
            account_id,
            signed_amount,
            tx_date,
        )
        return self.add_transaction(
            account_id=account_id,
            tx_type=tx_type,
            amount=absolute_amount,
            description=description,
            category=None,
            subcategory=None,
            payment_method=BALANCE_ADJUSTMENT_PAYMENT_METHOD,
            receipt_path=None,
            tx_date=normalized_date,
            note=note,
            to_account_id=None,
            is_transfer=0,
            exchange_rate=None,
            converted_amount=None,
            category_id=None,
            source="balance_adjustment",
        )

    def update_balance_adjustment(
        self,
        tx_id: int,
        account_id: int,
        signed_amount: MoneyLike,
        *,
        tx_date: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        existing = self.get_transaction_by_id(tx_id)
        if existing is None:
            raise ValueError(f"Transaction {tx_id} not found")
        if not is_balance_adjustment_transaction(existing):
            raise ValueError(f"Transaction {tx_id} is not a balance adjustment")
        tx_type, absolute_amount, normalized_date, description = self._normalize_balance_adjustment_payload(
            account_id,
            signed_amount,
            tx_date,
        )
        return self.update_transaction(
            tx_id,
            account_id=account_id,
            tx_type=tx_type,
            amount=absolute_amount,
            description=description,
            category=None,
            category_id=None,
            subcategory=None,
            payment_method=BALANCE_ADJUSTMENT_PAYMENT_METHOD,
            receipt_path=None,
            tx_date=normalized_date,
            note=note,
            exchange_rate=None,
            converted_amount=None,
        )
