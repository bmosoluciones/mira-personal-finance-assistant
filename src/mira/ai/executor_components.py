# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Internal collaborators used by :mod:`mira.ai.executor`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, cast

from mira.db.database import Database
from mira.db.money import MONEY_ZERO, Money, money_to_decimal
from mira.transaction_kinds import TransactionType
from mira.ui.i18n import normalize_language, tr


@dataclass(frozen=True)
class CreditCardDetectionPatterns:
    has_card_reference: Any
    card_payment: Any
    card_payment_target: Any
    card_usage: Any


def _component_language(db: Database) -> str:
    return normalize_language(db.setting.get("language"))


def _component_tr(
    db: Database,
    key: str,
    default: str,
    *,
    params: dict[str, object] | None = None,
) -> str:
    return tr(key, _component_language(db), default=default, params=params)


class ExecutorAccountResolver:
    def __init__(self, db: Database) -> None:
        self._db = db

    def mentioned_accounts(
        self,
        text: str | None,
        *,
        account_types: tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        if not text:
            return []
        return self._db.account.find_mentions(text, account_types=account_types)

    def resolve_known_account(
        self,
        requested_name: str | None,
        *,
        account_types: tuple[str, ...] | None = None,
    ) -> dict[str, Any] | None:
        if not requested_name or not requested_name.strip():
            return None

        direct = self._db.account.find_by_name(requested_name.strip())
        if direct is not None:
            if account_types is None or str(direct.get("account_type") or "") in set(account_types):
                return direct
            return None

        mentioned = self.mentioned_accounts(requested_name, account_types=account_types)
        if len(mentioned) == 1:
            return mentioned[0]
        return None

    def default_account(self, *, account_types: tuple[str, ...] | None = None) -> dict[str, Any] | None:
        default = self._db.account.get_default()
        if default is not None:
            if account_types is None or str(default.get("account_type") or "") in set(account_types):
                return default

        candidates = self._db.account.list(account_types)
        if len(candidates) == 1:
            return candidates[0]
        return None

    def resolve_account(
        self,
        requested_name: str | None,
        *,
        raw_text: str | None = None,
        account_types: tuple[str, ...] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        known = self.resolve_known_account(requested_name, account_types=account_types)
        if known is not None:
            return str(known.get("name") or requested_name or ""), known

        mentioned = self.mentioned_accounts(raw_text, account_types=account_types)
        if len(mentioned) == 1:
            return str(mentioned[0].get("name") or ""), mentioned[0]

        if default := self.default_account(account_types=account_types):
            return str(default.get("name") or ""), default

        context = requested_name or (raw_text[:40] if raw_text else None) or "unknown"
        raise ValueError(
            _component_tr(
                self._db,
                "chat.account.resolve.error",
                "I could not identify a valid account for '{context}'. Create or select an account in the application before adding transactions.",
                params={"context": str(context)},
            )
        )


class ExecutorCategoryResolver:
    def __init__(self, db: Database, *, matcher: Any) -> None:
        self._db = db
        self._matcher = matcher

    def resolve_category(self, action: dict[str, Any], cat_type: str) -> str | None:
        category = action.get("category")
        if not isinstance(category, str):
            return None
        normalized = category.strip()
        if not normalized:
            return None

        if existing_for_type := self._db.category.find_by_name(normalized, cat_type):
            return str(existing_for_type.get("name") or normalized)

        if existing_any_type := self._db.category.find_by_name(normalized):
            return str(existing_any_type.get("name") or normalized)

        all_categories = self._db.category.list(cat_type)
        best = self._matcher(normalized, all_categories)
        return str(best.get("name")) if best is not None else None


class ExecutorCreditCardHelper:
    def __init__(
        self,
        db: Database,
        *,
        account_resolver: ExecutorAccountResolver,
        patterns: CreditCardDetectionPatterns,
        action_result_cls: type,
        format_money: Any,
    ) -> None:
        self._db = db
        self._accounts = account_resolver
        self._patterns = patterns
        self._action_result_cls = action_result_cls
        self._format_money = format_money

    def has_card_reference(self, text: str | None) -> bool:
        return bool(text and self._patterns.has_card_reference.search(text))

    def looks_like_credit_card_payment(self, text: str | None) -> bool:
        if not text:
            return False
        has_payment_verb = self._patterns.card_payment.search(text) is not None
        has_target_reference = self._patterns.card_payment_target.search(text) is not None
        if not has_payment_verb and not has_target_reference:
            return False
        if not self._patterns.has_card_reference.search(text):
            return False
        return self._patterns.card_usage.search(text) is None

    def looks_like_credit_card_purchase(self, text: str | None) -> bool:
        if not text:
            return False
        return (
            self._patterns.has_card_reference.search(text) is not None
            and self._patterns.card_usage.search(text) is not None
        )

    def resolve_credit_payment_target(self, action: dict[str, Any]) -> dict[str, Any] | None:
        requested = action.get("account")
        raw_text = cast(str | None, action.get("description"))
        explicit = self._accounts.resolve_known_account(cast(str | None, requested), account_types=("credit",))
        if explicit is not None:
            return explicit

        mentioned = self._accounts.mentioned_accounts(raw_text, account_types=("credit",))
        match len(mentioned):
            case 1:
                return mentioned[0]
            case count if count > 1:
                return None
        credit_accounts = self._db.account.list_credit()
        if self.has_card_reference(raw_text) and len(credit_accounts) == 1:
            return credit_accounts[0]
        return None

    def resolve_credit_payment_source(self, raw_text: str | None) -> dict[str, Any] | None:
        mentioned = self._accounts.mentioned_accounts(raw_text, account_types=("bank", "cash"))
        match len(mentioned):
            case 1:
                return mentioned[0]
            case count if count > 1:
                return None
        return self._accounts.default_account(account_types=("bank", "cash"))

    def maybe_record_credit_card_payment(self, action: dict[str, Any]):
        raw_text = cast(str | None, action.get("description"))
        if not self.looks_like_credit_card_payment(raw_text):
            return None

        target = self.resolve_credit_payment_target(action)
        if target is None:
            return self._action_result_cls(
                success=True,
                action="none",
                message=_component_tr(
                    self._db,
                    "chat.card_payment.target_required",
                    "I need to identify the credit card clearly before I can record that payment.",
                ),
            )

        source = self.resolve_credit_payment_source(raw_text)
        if source is None:
            return self._action_result_cls(
                success=True,
                action="none",
                message=_component_tr(
                    self._db,
                    "chat.card_payment.source_required",
                    "I need to know which bank or cash account was used to pay the card.",
                ),
            )

        amount_value = action.get("converted_amount")
        if amount_value is None:
            amount_value = action.get("amount")
        if amount_value is None:
            raise ValueError(
                _component_tr(
                    self._db,
                    "chat.card_payment.amount_required",
                    "The credit card payment amount is required.",
                )
            )
        stored_amount = money_to_decimal(cast(Any, amount_value)) or MONEY_ZERO
        debit_tx, credit_tx = self._db.transaction.record_credit_card_payment(
            from_account_id=int(source["id"]),
            credit_account_id=int(target["id"]),
            amount=stored_amount,
            description=raw_text,
            exchange_rate=action.get("exchange_rate"),
            converted_amount=action.get("converted_amount"),
        )
        return self._action_result_cls(
            success=True,
            action="add_expense",
            message=_component_tr(
                self._db,
                "chat.card_payment.recorded",
                "Card payment recorded: {amount} {currency} to {target} from {source}",
                params={
                    "amount": self._format_money(action["amount"]),
                    "currency": str(action.get("base_currency", "USD")),
                    "target": str(target["name"]),
                    "source": str(source["name"]),
                },
            ),
            data={
                "debit_transaction": debit_tx,
                "credit_transaction": credit_tx,
                "from_account": source,
                "to_account": target,
            },
        )

    def resolve_expense_account(self, action: dict[str, Any]):
        raw_text = cast(str | None, action.get("description"))
        explicit = self._accounts.resolve_known_account(cast(str | None, action.get("account")))
        if explicit is not None:
            return str(explicit.get("name") or ""), explicit

        mentioned_credit = self._accounts.mentioned_accounts(raw_text, account_types=("credit",))
        if len(mentioned_credit) == 1 and self.has_card_reference(raw_text):
            return str(mentioned_credit[0].get("name") or ""), mentioned_credit[0]
        if len(mentioned_credit) > 1 and self.has_card_reference(raw_text):
            return self._action_result_cls(
                success=True,
                action="none",
                message=_component_tr(
                    self._db,
                    "chat.card_purchase.multiple_cards",
                    "There is more than one possible card for that expense. Tell me which credit account I should use.",
                ),
            )

        if self.looks_like_credit_card_purchase(raw_text):
            credit_accounts = self._db.account.list_credit()
            if len(credit_accounts) == 1:
                return str(credit_accounts[0].get("name") or ""), credit_accounts[0]
            if len(credit_accounts) > 1:
                return self._action_result_cls(
                    success=True,
                    action="none",
                    message=_component_tr(
                        self._db,
                        "chat.card_purchase.card_required",
                        "I need to know which credit card you used for that purchase.",
                    ),
                )

        return self._accounts.resolve_account(cast(str | None, action.get("account")), raw_text=raw_text)


class ExecutorReportBuilder:
    def __init__(
        self,
        db: Database,
        *,
        action_result_cls: type,
        compute_summary: Any,
        format_money: Any,
    ) -> None:
        self._db = db
        self._action_result_cls = action_result_cls
        self._compute_summary = compute_summary
        self._format_money = format_money

    @staticmethod
    def period_range(period: dict[str, Any] | None) -> tuple[str | None, str | None, str]:
        today = date.today()
        if not period:
            start = today.replace(day=1)
            return start.isoformat(), today.isoformat(), "this_month"

        preset = period.get("preset") or "this_month"
        match preset:
            case "this_month":
                start = today.replace(day=1)
                return start.isoformat(), today.isoformat(), preset
            case "last_month":
                first_this_month = today.replace(day=1)
                last_prev_month = first_this_month - timedelta(days=1)
                start_prev = last_prev_month.replace(day=1)
                return start_prev.isoformat(), last_prev_month.isoformat(), preset
            case "last_week":
                start = today - timedelta(days=7)
                return start.isoformat(), today.isoformat(), preset
            case "last_2_months":
                approx_start = today - timedelta(days=60)
                return approx_start.isoformat(), today.isoformat(), preset
            case "last_3_months":
                approx_start = today - timedelta(days=90)
                return approx_start.isoformat(), today.isoformat(), preset
            case "last_6_months":
                approx_start = today - timedelta(days=180)
                return approx_start.isoformat(), today.isoformat(), preset
            case "this_year":
                return date(today.year, 1, 1).isoformat(), today.isoformat(), preset
            case "all_time":
                return None, today.isoformat(), preset
            case "custom":
                return period.get("from"), period.get("to"), preset
        start = today.replace(day=1)
        return start.isoformat(), today.isoformat(), "this_month"

    def build_report(self, action: dict[str, Any]):
        report_type = action.get("report_type") or "summary"
        since_date, until_date, period_preset = self.period_range(action.get("period"))
        filters = action.get("filters") or {}

        categories = filters.get("categories") or []
        account_names = filters.get("accounts") or []
        search_text = filters.get("text")
        min_amount = filters.get("min_amount")
        max_amount = filters.get("max_amount")

        tx_type = None
        if report_type == "expenses":
            tx_type = "expense"
        elif report_type == "incomes":
            tx_type = "income"

        single_account_id: int | None = None
        multi_account_ids: set[int] = set()
        for account_name in account_names:
            if account := self._db.account.find_by_name(account_name):
                multi_account_ids.add(int(account["id"]))
        if len(multi_account_ids) == 1:
            single_account_id = next(iter(multi_account_ids))
            multi_account_ids = set()

        category_filter = categories[0] if len(categories) == 1 else None
        transactions = self._db.transaction.list(
            limit=1000,
            tx_type=tx_type,
            account_id=single_account_id,
            since_date=since_date,
            until_date=until_date,
            category=category_filter,
            search=search_text,
            min_amount=min_amount,
            max_amount=max_amount,
        )

        if multi_account_ids:
            transactions = [t for t in transactions if t.get("account_id") in multi_account_ids]
        if len(categories) > 1:
            categories_set = set(categories)
            transactions = [t for t in transactions if t.get("category") in categories_set]

        summary: dict[str, Money] = self._compute_summary(self._db, transactions)
        accounts = self._db.account.list()
        recent = transactions[:10]
        lines = [
            _component_tr(
                self._db,
                "chat.report.header",
                "Report ({report_type}) - period: {period}",
                params={"report_type": str(report_type), "period": str(period_preset)},
            ),
            _component_tr(
                self._db,
                "chat.report.line.income",
                "  Income: {amount}",
                params={"amount": self._format_money(summary["total_income"])},
            ),
            _component_tr(
                self._db,
                "chat.report.line.expense",
                "  Expense: {amount}",
                params={"amount": self._format_money(summary["total_expenses"])},
            ),
            _component_tr(
                self._db,
                "chat.report.line.savings",
                "  Savings: {amount}",
                params={"amount": self._format_money(summary["savings"])},
            ),
            _component_tr(
                self._db,
                "chat.report.line.net",
                "  Net: {amount}",
                params={"amount": self._format_money(summary["net"])},
            ),
            _component_tr(
                self._db,
                "chat.report.line.transactions",
                "  Transactions matched: {count}",
                params={"count": len(transactions)},
            ),
            "",
            _component_tr(self._db, "chat.report.section.accounts", "Accounts:"),
        ]
        for acc in accounts:
            lines.append(f"  {acc['name']}: {self._format_money(acc['balance'])}")

        return self._action_result_cls(
            success=True,
            action="report",
            message="\n".join(lines),
            data={
                "report_type": report_type,
                "period": {"preset": period_preset, "from": since_date, "to": until_date},
                "filters": filters,
                "summary": summary,
                "accounts": accounts,
                "recent_transactions": recent,
                "transactions": transactions,
            },
        )


class ExecutorSummaryTools:
    @staticmethod
    def period_range(period: dict[str, Any] | None, *, today: date | None = None) -> tuple[str | None, str | None, str]:
        today_value = today or date.today()
        if not period:
            start = today_value.replace(day=1)
            return start.isoformat(), today_value.isoformat(), "this_month"
        preset = period.get("preset") or "this_month"
        match preset:
            case "this_month":
                start = today_value.replace(day=1)
                return start.isoformat(), today_value.isoformat(), preset
            case "last_month":
                first_this_month = today_value.replace(day=1)
                last_prev_month = first_this_month - timedelta(days=1)
                start_prev = last_prev_month.replace(day=1)
                return start_prev.isoformat(), last_prev_month.isoformat(), preset
            case "last_week":
                start = today_value - timedelta(days=7)
                return start.isoformat(), today_value.isoformat(), preset
            case "last_2_months":
                return (today_value - timedelta(days=60)).isoformat(), today_value.isoformat(), preset
            case "last_3_months":
                return (today_value - timedelta(days=90)).isoformat(), today_value.isoformat(), preset
            case "last_6_months":
                return (today_value - timedelta(days=180)).isoformat(), today_value.isoformat(), preset
            case "this_year":
                return date(today_value.year, 1, 1).isoformat(), today_value.isoformat(), preset
            case "all_time":
                return None, today_value.isoformat(), preset
            case "custom":
                return period.get("from"), period.get("to"), preset
        start = today_value.replace(day=1)
        return start.isoformat(), today_value.isoformat(), "this_month"

    @staticmethod
    def format_money(value: Any) -> str:
        amount = money_to_decimal(value) or MONEY_ZERO
        return f"{amount:,.2f}"

    @staticmethod
    def compute_summary(db: Database, transactions: list[dict[str, Any]]) -> dict[str, Money]:
        summary = db.report.summarize_financials(transactions)
        return {
            "total_income": summary.income,
            "total_expenses": summary.expense,
            "savings": summary.savings,
            "net": summary.net,
        }


class ExecutorTransactionRecorder:
    def __init__(
        self,
        db: Database,
        *,
        action_result_cls: type,
        format_money: Any,
        account_resolver: ExecutorAccountResolver,
        category_resolver: ExecutorCategoryResolver,
        credit_card_helper: ExecutorCreditCardHelper,
    ) -> None:
        self._db = db
        self._action_result_cls = action_result_cls
        self._format_money = format_money
        self._account_resolver = account_resolver
        self._category_resolver = category_resolver
        self._credit_card_helper = credit_card_helper

    def add_income(self, action: dict[str, Any]):
        raw_text = cast(str | None, action.get("description"))
        account_name, account = self._account_resolver.resolve_account(
            cast(str | None, action.get("account")), raw_text=raw_text
        )
        category_name = self._category_resolver.resolve_category(action, "income")
        amount_value = action.get("converted_amount")
        if amount_value is None:
            amount_value = action.get("amount")
        if amount_value is None:
            raise ValueError(
                _component_tr(
                    self._db,
                    "chat.income.amount_required",
                    "The income amount is required.",
                )
            )
        stored_amount = money_to_decimal(cast(Any, amount_value)) or MONEY_ZERO
        tx = self._db.transaction.create(
            account_id=account["id"],
            tx_type=TransactionType.INCOME,
            amount=stored_amount,
            description=action.get("description"),
            category=category_name,
            exchange_rate=action.get("exchange_rate"),
            converted_amount=action.get("converted_amount"),
            source="nl_assistant",
        )
        description_suffix = f" - {action['description']}" if action.get("description") else ""
        msg = _component_tr(
            self._db,
            "chat.income.recorded",
            "Income recorded: {amount} {currency} (converted: {converted}){description} (account: {account})",
            params={
                "amount": self._format_money(action["amount"]),
                "currency": str(action.get("base_currency", "USD")),
                "converted": self._format_money(stored_amount),
                "description": description_suffix,
                "account": str(account_name),
            },
        )
        return self._action_result_cls(
            success=True,
            action="add_income",
            message=msg,
            data={"transaction": tx, "account": account},
        )

    def add_expense(self, action: dict[str, Any]):
        if (payment_result := self._credit_card_helper.maybe_record_credit_card_payment(action)) is not None:
            return payment_result

        resolved_account = self._credit_card_helper.resolve_expense_account(action)
        if isinstance(resolved_account, self._action_result_cls):
            return resolved_account
        account_name, account = resolved_account
        category_name = self._category_resolver.resolve_category(action, "expense")
        amount_value = action.get("converted_amount")
        if amount_value is None:
            amount_value = action.get("amount")
        if amount_value is None:
            raise ValueError(
                _component_tr(
                    self._db,
                    "chat.expense.amount_required",
                    "The expense amount is required.",
                )
            )
        stored_amount = money_to_decimal(cast(Any, amount_value)) or MONEY_ZERO
        tx = self._db.transaction.create(
            account_id=account["id"],
            tx_type=TransactionType.EXPENSE,
            amount=stored_amount,
            description=action.get("description"),
            category=category_name,
            exchange_rate=action.get("exchange_rate"),
            converted_amount=action.get("converted_amount"),
            source="nl_assistant",
        )
        description_suffix = f" - {action['description']}" if action.get("description") else ""
        msg = _component_tr(
            self._db,
            "chat.expense.recorded",
            "Expense recorded: {amount} {currency} (converted: {converted}){description} (account: {account})",
            params={
                "amount": self._format_money(action["amount"]),
                "currency": str(action.get("base_currency", "USD")),
                "converted": self._format_money(stored_amount),
                "description": description_suffix,
                "account": str(account_name),
            },
        )
        return self._action_result_cls(
            success=True,
            action="add_expense",
            message=msg,
            data={"transaction": tx, "account": account},
        )
