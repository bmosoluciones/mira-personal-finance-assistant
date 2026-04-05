# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from mira.db.database import Database
from tests.db_inspection import fetch_all_dicts, fetch_one_dict


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "daily-contextual.db")
    database.connect()
    database.setting.set("language", "es")
    yield database
    database.close()


def test_daily_message_shows_budget_missing_only_once_per_day(db: Database) -> None:
    payload = db.feedback.pop_daily_contextual_message(on_date=date(2026, 3, 12))

    assert payload is not None
    assert payload["code"] == "daily_budget_missing"
    assert db.setting.get("_last_daily_message") == "2026-03-12"

    repeated = db.feedback.pop_daily_contextual_message(on_date=date(2026, 3, 12))
    assert repeated is None
    row = fetch_one_dict(
        db,
        "SELECT COUNT(*) AS total FROM message_events WHERE source_event_type = 'app_start'",
    )
    assert int(row["total"]) == 1


def test_daily_message_prioritizes_transaction_inactivity_over_savings_goal_hint(
    db: Database,
) -> None:
    db.budget.create("B2026", 2026, "NIO")

    payload = db.feedback.pop_daily_contextual_message(on_date=date(2026, 3, 25))

    assert payload is not None
    assert payload["code"] == "daily_no_transactions"


def test_daily_message_returns_none_when_no_relevant_trigger(db: Database) -> None:
    db.budget.create("B2026", 2026, "NIO")
    db.savings_goal.get_or_create("Fondo emergencia", 500.0)

    account = db.account.get_or_create("General")
    db.transaction.create(
        account_id=int(account["id"]),
        tx_type="income",
        amount=100.0,
        category="Salario",
        tx_date="2026-03-05",
    )

    payload = db.feedback.pop_daily_contextual_message(on_date=date(2026, 3, 6))

    assert payload is None
    assert db.setting.get("_last_daily_message") is None


def test_day_cooldown_uses_reference_date_instead_of_insert_timestamp(
    db: Database,
) -> None:
    candidate = {
        "code": "expense_unusual_high",
        "message_type": "realtime_insight",
        "message": "Gasto alto atípico",
        "priority": 60,
        "cooldown_scope": "day",
    }

    first = db.feedback.resolve_single_message(
        [candidate],
        source_event_type="transaction",
        source_event_id=101,
        period_key="2026-03",
        reference_date="2026-03-20",
        source="manual",
    )
    repeated_same_reference_day = db.feedback.resolve_single_message(
        [candidate],
        source_event_type="transaction",
        source_event_id=102,
        period_key="2026-03",
        reference_date="2026-03-20",
        source="manual",
    )
    next_reference_day = db.feedback.resolve_single_message(
        [candidate],
        source_event_type="transaction",
        source_event_id=103,
        period_key="2026-03",
        reference_date="2026-03-21",
        source="manual",
    )

    assert first is not None
    assert repeated_same_reference_day is None
    assert next_reference_day is not None

    rows = fetch_all_dicts(
        db,
        """
        SELECT reference_date
        FROM message_events
        WHERE message_code = 'expense_unusual_high'
        ORDER BY id
        """,
    )
    assert [str(row["reference_date"]) for row in rows] == ["2026-03-20", "2026-03-21"]
