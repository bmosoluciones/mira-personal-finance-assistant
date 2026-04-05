# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Action executor for MIRA.

Receives a validated action dict and performs the corresponding database
operations, returning a human-readable result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, cast

from mira.db.database import Database
from mira.db.helpers import localized_default_account_name
from mira.db.money import MONEY_ZERO, Money, money_to_decimal

_SAVINGS_CATEGORY_ALIASES = {
    "savings",
    "saving",
    "ahorro",
    "ahorros",
    "inversion",
    "inversión",
    "investment",
}
_CARD_REFERENCE_PATTERN = re.compile(
    r"\b(?:card|credit\s+card|tarjeta|tarjeta\s+de\s+credito|tarjeta\s+de\s+crédito|visa|mastercard|amex|american\s+express)\b",
    re.IGNORECASE,
)
_CARD_USAGE_PATTERN = re.compile(
    r"\b(?:with|using|con|usando|desde|from|on|en)\b.{0,30}"
    r"\b(?:card|credit\s+card|tarjeta|visa|mastercard|amex|american\s+express)\b",
    re.IGNORECASE,
)
_CARD_PAYMENT_PATTERN = re.compile(
    r"\b(?:abone|aboné|abonar|abono|abonaré|cancele|cancelé|cancelar|cancelo|"
    r"pay(?:ed)?\s+(?:the|my)\s+card|payment\s+(?:to|for)\s+(?:my\s+)?card|"
    r"pague|pagué|pagar|transferi|transferí|transfer(?:red)?)\b",
    re.IGNORECASE,
)
_CARD_PAYMENT_TARGET_PATTERN = re.compile(
    r"\b(?:to|a|para)\b(?:\s+(?:my|mi|the|la|el))?\s+"
    r"(?:card|credit\s+card|tarjeta|visa|mastercard|amex|american\s+express)\b",
    re.IGNORECASE,
)


@dataclass
class ActionResult:
    """The outcome of executing an action."""

    success: bool
    action: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)


def _period_range(period: dict[str, Any] | None) -> tuple[str | None, str | None, str]:
    today = date.today()
    if not period:
        start = today.replace(day=1)
        return start.isoformat(), today.isoformat(), "this_month"

    preset = period.get("preset") or "this_month"
    if preset == "this_month":
        start = today.replace(day=1)
        return start.isoformat(), today.isoformat(), preset
    if preset == "last_month":
        first_this_month = today.replace(day=1)
        last_prev_month = first_this_month - timedelta(days=1)
        start_prev = last_prev_month.replace(day=1)
        return start_prev.isoformat(), last_prev_month.isoformat(), preset
    if preset == "last_week":
        start = today - timedelta(days=7)
        return start.isoformat(), today.isoformat(), preset
    if preset == "last_2_months":
        approx_start = today - timedelta(days=60)
        return approx_start.isoformat(), today.isoformat(), preset
    if preset == "last_3_months":
        approx_start = today - timedelta(days=90)
        return approx_start.isoformat(), today.isoformat(), preset
    if preset == "last_6_months":
        approx_start = today - timedelta(days=180)
        return approx_start.isoformat(), today.isoformat(), preset
    if preset == "this_year":
        return date(today.year, 1, 1).isoformat(), today.isoformat(), preset
    if preset == "all_time":
        return None, today.isoformat(), preset
    if preset == "custom":
        return period.get("from"), period.get("to"), preset

    start = today.replace(day=1)
    return start.isoformat(), today.isoformat(), "this_month"


def _format_money(value: Any) -> str:
    amount = money_to_decimal(value) or MONEY_ZERO
    return f"{amount:.2f}"


def _compute_summary(db: Database, transactions: list[dict[str, Any]]) -> dict[str, Money]:
    summary = db.report.summarize_financials(transactions)
    return {
        "total_income": summary["income"],
        "total_expenses": summary["expense"],
        "savings": summary["savings"],
        "net": summary["net"],
    }


class Executor:
    """Executes structured MIRA actions against the database."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def execute(self, action: dict[str, Any]) -> ActionResult:
        """Execute *action* and return an :class:`ActionResult`."""
        action_name = action.get("action", "none")
        handlers = {
            "add_income": self._add_income,
            "add_expense": self._add_expense,
            "report": self._report,
            "data_analysis": self._data_analysis,
            "none": self._none,
        }
        handler = handlers.get(action_name, self._none)
        return handler(action)

    def _mentioned_accounts(
        self,
        text: str | None,
        *,
        account_types: tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        if not text:
            return []
        return self._db.account.find_mentions(text, account_types=account_types)

    def _resolve_known_account(
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

        mentioned = self._mentioned_accounts(requested_name, account_types=account_types)
        if len(mentioned) == 1:
            return mentioned[0]
        return None

    def _default_account(self, *, account_types: tuple[str, ...] | None = None) -> dict[str, Any] | None:
        default = self._db.account.get_default()
        if default is not None:
            if account_types is None or str(default.get("account_type") or "") in set(account_types):
                return default

        candidates = self._db.account.list(account_types)
        if len(candidates) == 1:
            return candidates[0]
        return None

    def _resolve_account(
        self,
        requested_name: str | None,
        *,
        raw_text: str | None = None,
        account_types: tuple[str, ...] | None = None,
        create_if_missing: bool = True,
    ) -> tuple[str, dict[str, Any]]:
        known = self._resolve_known_account(requested_name, account_types=account_types)
        if known is not None:
            return str(known.get("name") or requested_name or ""), known

        mentioned = self._mentioned_accounts(raw_text, account_types=account_types)
        if len(mentioned) == 1:
            return str(mentioned[0].get("name") or ""), mentioned[0]

        fallback_name = localized_default_account_name(self._db.setting.get("language"))
        if account_types is None and not (requested_name and requested_name.strip()):
            existing = self._db.account.find_by_name(fallback_name)
            if existing is not None:
                return fallback_name, existing
            if create_if_missing:
                return fallback_name, self._db.account.get_or_create(fallback_name)

        if requested_name and requested_name.strip() and create_if_missing and account_types is None:
            normalized_name = requested_name.strip()
            return normalized_name, self._db.account.get_or_create(normalized_name)

        default = self._default_account(account_types=account_types)
        if default is not None:
            return str(default.get("name") or ""), default

        existing = self._db.account.find_by_name(fallback_name)
        if existing is not None and (
            account_types is None or str(existing.get("account_type") or "") in set(account_types)
        ):
            return fallback_name, existing
        if create_if_missing and account_types is None:
            return fallback_name, self._db.account.get_or_create(fallback_name)
        raise ValueError("No matching account could be resolved.")

    @staticmethod
    def _has_card_reference(text: str | None) -> bool:
        return bool(text and _CARD_REFERENCE_PATTERN.search(text))

    @staticmethod
    def _looks_like_credit_card_payment(text: str | None) -> bool:
        if not text:
            return False
        has_payment_verb = _CARD_PAYMENT_PATTERN.search(text) is not None
        has_target_reference = _CARD_PAYMENT_TARGET_PATTERN.search(text) is not None
        if not has_payment_verb and not has_target_reference:
            return False
        if not _CARD_REFERENCE_PATTERN.search(text):
            return False
        return _CARD_USAGE_PATTERN.search(text) is None

    @staticmethod
    def _looks_like_credit_card_purchase(text: str | None) -> bool:
        if not text:
            return False
        return _CARD_REFERENCE_PATTERN.search(text) is not None and _CARD_USAGE_PATTERN.search(text) is not None

    def _resolve_credit_payment_target(
        self,
        action: dict[str, Any],
    ) -> dict[str, Any] | None:
        requested = action.get("account")
        raw_text = cast(str | None, action.get("description"))
        explicit = self._resolve_known_account(cast(str | None, requested), account_types=("credit",))
        if explicit is not None:
            return explicit

        mentioned = self._mentioned_accounts(raw_text, account_types=("credit",))
        if len(mentioned) == 1:
            return mentioned[0]
        if len(mentioned) > 1:
            return None

        credit_accounts = self._db.account.list_credit()
        if self._has_card_reference(raw_text) and len(credit_accounts) == 1:
            return credit_accounts[0]
        return None

    def _resolve_credit_payment_source(self, raw_text: str | None) -> dict[str, Any] | None:
        mentioned = self._mentioned_accounts(raw_text, account_types=("bank", "cash"))
        if len(mentioned) == 1:
            return mentioned[0]
        if len(mentioned) > 1:
            return None
        return self._default_account(account_types=("bank", "cash"))

    def _maybe_record_credit_card_payment(self, action: dict[str, Any]) -> ActionResult | None:
        raw_text = cast(str | None, action.get("description"))
        if not self._looks_like_credit_card_payment(raw_text):
            return None

        target = self._resolve_credit_payment_target(action)
        if target is None:
            return ActionResult(
                success=True,
                action="none",
                message="Necesito identificar con claridad la tarjeta de crédito para registrar ese pago.",
            )

        source = self._resolve_credit_payment_source(raw_text)
        if source is None:
            return ActionResult(
                success=True,
                action="none",
                message="Necesito saber desde qué cuenta bank/cash se realizó el pago de la tarjeta.",
            )

        amount_value = action.get("converted_amount")
        if amount_value is None:
            amount_value = action.get("amount")
        if amount_value is None:
            raise ValueError("Credit card payment amount is required")
        stored_amount = money_to_decimal(cast(Any, amount_value)) or MONEY_ZERO
        debit_tx, credit_tx = self._db.transaction.record_credit_card_payment(
            from_account_id=int(source["id"]),
            credit_account_id=int(target["id"]),
            amount=stored_amount,
            description=raw_text,
            exchange_rate=action.get("exchange_rate"),
            converted_amount=action.get("converted_amount"),
        )
        return ActionResult(
            success=True,
            action="add_expense",
            message=(
                f"↔ Card payment recorded: {_format_money(action['amount'])} {action.get('base_currency', 'USD')}"
                f" to {target['name']} from {source['name']}"
            ),
            data={
                "debit_transaction": debit_tx,
                "credit_transaction": credit_tx,
                "from_account": source,
                "to_account": target,
            },
        )

    def _resolve_expense_account(self, action: dict[str, Any]) -> ActionResult | tuple[str, dict[str, Any]]:
        raw_text = cast(str | None, action.get("description"))
        explicit = self._resolve_known_account(cast(str | None, action.get("account")))
        if explicit is not None:
            return str(explicit.get("name") or ""), explicit

        mentioned_credit = self._mentioned_accounts(raw_text, account_types=("credit",))
        if len(mentioned_credit) == 1 and self._has_card_reference(raw_text):
            return str(mentioned_credit[0].get("name") or ""), mentioned_credit[0]
        if len(mentioned_credit) > 1 and self._has_card_reference(raw_text):
            return ActionResult(
                success=True,
                action="none",
                message="Hay más de una tarjeta posible para ese gasto. Indica cuál cuenta credit usar.",
            )

        if self._looks_like_credit_card_purchase(raw_text):
            credit_accounts = self._db.account.list_credit()
            if len(credit_accounts) == 1:
                return str(credit_accounts[0].get("name") or ""), credit_accounts[0]
            if len(credit_accounts) > 1:
                return ActionResult(
                    success=True,
                    action="none",
                    message="Necesito saber con cuál tarjeta de crédito hiciste esa compra.",
                )

        return self._resolve_account(cast(str | None, action.get("account")), raw_text=raw_text)

    def _resolve_category(self, action: dict[str, Any], cat_type: str) -> str | None:
        category = action.get("category")
        if not isinstance(category, str):
            return None
        normalized = category.strip()
        if not normalized:
            return None
        is_savings_category = cat_type == "expense" and normalized.lower() in _SAVINGS_CATEGORY_ALIASES
        category_name = "Ahorro" if is_savings_category else normalized
        existing_for_type = self._db.category.find_by_name(category_name, cat_type)
        if existing_for_type is not None:
            return category_name

        existing_any_type = self._db.category.find_by_name(category_name)
        if existing_any_type is not None:
            # Category names are globally unique in the current schema, so the
            # assistant must reuse an existing category label instead of trying
            # to create a same-name row for the opposite transaction type.
            return str(existing_any_type.get("name") or category_name)

        self._db.category.get_or_create(category_name, cat_type, is_savings=is_savings_category)
        return category_name

    def _add_income(self, action: dict[str, Any]) -> ActionResult:
        raw_text = cast(str | None, action.get("description"))
        account_name, account = self._resolve_account(cast(str | None, action.get("account")), raw_text=raw_text)
        category_name = self._resolve_category(action, "income")
        amount_value = action.get("converted_amount")
        if amount_value is None:
            amount_value = action.get("amount")
        if amount_value is None:
            raise ValueError("Income amount is required")
        stored_amount = money_to_decimal(cast(Any, amount_value)) or MONEY_ZERO
        tx = self._db.transaction.create(
            account_id=account["id"],
            tx_type="income",
            amount=stored_amount,
            description=action.get("description"),
            category=category_name,
            exchange_rate=action.get("exchange_rate"),
            converted_amount=action.get("converted_amount"),
            source="nl_assistant",
        )
        msg = (
            f"✅ Income recorded: {_format_money(action['amount'])} {action.get('base_currency', 'USD')}"
            f" (converted: {_format_money(stored_amount)})"
            f"{' – ' + action['description'] if action.get('description') else ''}"
            f" (account: {account_name})"
        )
        return ActionResult(
            success=True,
            action="add_income",
            message=msg,
            data={"transaction": tx, "account": account},
        )

    def _add_expense(self, action: dict[str, Any]) -> ActionResult:
        payment_result = self._maybe_record_credit_card_payment(action)
        if payment_result is not None:
            return payment_result

        resolved_account = self._resolve_expense_account(action)
        if isinstance(resolved_account, ActionResult):
            return resolved_account
        account_name, account = resolved_account
        category_name = self._resolve_category(action, "expense")
        amount_value = action.get("converted_amount")
        if amount_value is None:
            amount_value = action.get("amount")
        if amount_value is None:
            raise ValueError("Expense amount is required")
        stored_amount = money_to_decimal(cast(Any, amount_value)) or MONEY_ZERO
        tx = self._db.transaction.create(
            account_id=account["id"],
            tx_type="expense",
            amount=stored_amount,
            description=action.get("description"),
            category=category_name,
            exchange_rate=action.get("exchange_rate"),
            converted_amount=action.get("converted_amount"),
            source="nl_assistant",
        )
        msg = (
            f"💸 Expense recorded: {_format_money(action['amount'])} {action.get('base_currency', 'USD')}"
            f" (converted: {_format_money(stored_amount)})"
            f"{' – ' + action['description'] if action.get('description') else ''}"
            f" (account: {account_name})"
        )
        return ActionResult(
            success=True,
            action="add_expense",
            message=msg,
            data={"transaction": tx, "account": account},
        )

    def _report(self, action: dict[str, Any]) -> ActionResult:
        report_type = action.get("report_type") or "summary"
        since_date, until_date, period_preset = _period_range(action.get("period"))
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
            account = self._db.account.find_by_name(account_name)
            if account is not None:
                multi_account_ids.add(int(account["id"]))
        if len(multi_account_ids) == 1:
            # Single account — push the filter into SQL for efficiency
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

        summary = _compute_summary(self._db, transactions)
        accounts = self._db.account.list()
        recent = transactions[:10]

        lines = [
            f"📊 Report ({report_type}) – period: {period_preset}",
            f"  Income:   {_format_money(summary['total_income']):>10}",
            f"  Expenses: {_format_money(summary['total_expenses']):>10}",
            f"  Savings:  {_format_money(summary['savings']):>10}",
            f"  Net:      {_format_money(summary['net']):>10}",
            f"  Transactions matched: {len(transactions)}",
            "",
            "Accounts:",
        ]
        for acc in accounts:
            lines.append(f"  {acc['name']:<20} {_format_money(acc['balance']):>10}")

        msg = "\n".join(lines)
        return ActionResult(
            success=True,
            action="report",
            message=msg,
            data={
                "report_type": report_type,
                "period": {
                    "preset": period_preset,
                    "from": since_date,
                    "to": until_date,
                },
                "filters": filters,
                "summary": summary,
                "accounts": accounts,
                "recent_transactions": recent,
                "transactions": transactions,
            },
        )

    def _none(self, action: dict[str, Any]) -> ActionResult:
        msg = action.get("message") or (
            "Disculpa, no entendí tu solicitud. "
            "Puedo ayudarte a registrar ingresos, gastos o ver tu resumen financiero."
        )
        return ActionResult(success=True, action="none", message=msg)

    def _data_analysis(self, action: dict[str, Any]) -> ActionResult:
        period = action.get("period") or {}
        msg = (
            "Abriré el reporte MIRA oficial para analizar tus datos financieros. "
            "Ahí verás el resumen y las comparativas del periodo."
        )
        return ActionResult(
            success=True,
            action="data_analysis",
            message=msg,
            data={
                "period": period,
                "filters": action.get("filters") or {},
            },
        )
