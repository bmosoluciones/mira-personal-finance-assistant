# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Headless finance commands for mira-cli. No Qt imports."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from mira.ai.executor import Executor
from mira.ai.executor_components import ExecutorAccountResolver
from mira.ai.pipeline import Pipeline
from mira.db.database import Database
from mira.db.money import money_to_decimal


def _account_id(db: Database, name: str) -> int:
    """Return the id of a named account."""
    account = db.account.find_by_name(name)
    if account is None:
        raise ValueError(f"Account not found: {name}")
    return int(account["id"])


def _require_known_account(db: Database, name: str) -> None:
    """Reject an unresolvable account before any write is attempted.

    The executor falls back to the default account when it cannot resolve a
    name, which is right for free-form text but wrong for a structured caller:
    a mistyped account would silently record the movement somewhere else.
    """
    if not str(name or "").strip():
        raise ValueError("An account name is required.")
    if ExecutorAccountResolver(db).resolve_known_account(name) is None:
        raise ValueError(f"Account not found: {name}")


def _action(kind: str, amount: str, account: str, description: str | None, category: str | None, tx_date: str | None, note: str | None) -> dict[str, Any]:
    """Build an executor action without calling a remote model."""
    parsed = money_to_decimal(amount)
    return {
        "action": kind,
        "amount": parsed,
        "description": description,
        "category": category,
        "account": account,
        "base_currency": None,
        "exchange_rate": None,
        "converted_amount": parsed,
        "report_type": None,
        "period": None,
        "filters": None,
        "message": None,
        "date": tx_date,
        "note": note,
    }


_MOVEMENT_KINDS = ("add_income", "add_expense")


def add_movement(db: Database, *, kind: str, amount: str, account: str, description: str | None, category: str | None, tx_date: str | None, note: str | None) -> dict[str, Any]:
    """Record an income or expense through the local executor."""
    if kind not in _MOVEMENT_KINDS:
        raise ValueError(f"Unsupported movement kind: {kind}")
    _require_known_account(db, account)
    result = Executor(db).execute(_action(kind, amount, account, description, category, tx_date, note))
    if not result.success:
        raise ValueError(result.message)
    transaction = result.data.get("transaction") if isinstance(result.data, dict) else None
    if isinstance(transaction, dict) and transaction.get("id") is not None and (tx_date or note):
        updates: dict[str, Any] = {}
        if tx_date:
            updates["tx_date"] = tx_date
        if note:
            updates["note"] = note
        transaction = db.transaction.update(int(transaction["id"]), **updates)
        result.data["transaction"] = transaction
    return {"ok": True, "action": result.action, "message": result.message, "data": result.data}


def transfer(db: Database, *, source: str, target: str, amount: str, tx_date: str | None, note: str | None) -> dict[str, Any]:
    """Move money between two local accounts."""
    expense, income = db.transaction.transfer_between_accounts(
        _account_id(db, source),
        _account_id(db, target),
        money_to_decimal(amount),
        note=note,
        tx_date=tx_date,
    )
    return {"ok": True, "action": "transfer", "expense": expense, "income": income}


def list_transactions(db: Database, *, limit: int, account: str | None, since: str | None, until: str | None) -> dict[str, Any]:
    """Return recent transactions."""
    account_id = _account_id(db, account) if account else None
    rows = db.transaction.list(limit=limit, account_id=account_id, since_date=since, until_date=until)
    return {"ok": True, "transactions": rows}


def report_summary(db: Database, *, since: str | None) -> dict[str, Any]:
    """Return a local financial summary."""
    return {"ok": True, "summary": db.report.summary(since_date=since)}


def record_text(db: Database, text: str) -> dict[str, Any]:
    """Parse text with the local assistant. Never calls a remote model."""
    pipeline = Pipeline(db=db)
    try:
        result = pipeline.process(text)
    finally:
        pipeline.shutdown()
    if not result.success:
        raise ValueError(result.message)
    return {"ok": True, "action": result.action, "message": result.message, "data": result.data}


def dump(payload: dict[str, Any], *, as_json: bool) -> str:
    """Render a command result for stdout."""
    if as_json:
        return json.dumps(payload, default=str, ensure_ascii=False)
    if "message" in payload:
        return str(payload["message"])
    if "transactions" in payload:
        lines = [f"{row.get('date')} {row.get('type')} {row.get('amount')} {row.get('description') or ''}".rstrip() for row in payload["transactions"]]
        return "\n".join(lines) if lines else "No transactions."
    if "summary" in payload:
        return json.dumps(payload["summary"], default=str, ensure_ascii=False)
    return json.dumps(payload, default=str, ensure_ascii=False)


def today_iso() -> str:
    """Return today's date as ISO text."""
    return date.today().isoformat()
