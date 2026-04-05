# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

from pathlib import Path

import pytest

from mira.app.view_services import (
    AccountsViewService,
    CategoriesViewService,
    RecurringViewService,
    SavingsGoalsViewService,
    SettingsViewService,
    TagsViewService,
)
from mira.db.database import Database


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "view-services-crud.db")
    database.connect()
    yield database
    database.close()


def test_accounts_view_service_roundtrip(db: Database) -> None:
    service = AccountsViewService(db)

    created = service.create(name="Wallet", account_type="cash", opening_balance=25.0, currency="USD")
    assert created.selected_id is not None

    service.update(created.selected_id, name="Wallet Pro", account_type="credit", currency="USD")
    service.set_default(created.selected_id)

    state = service.load_state()
    account = next(item for item in state.accounts if int(item["id"]) == int(created.selected_id))
    assert account["name"] == "Wallet Pro"
    assert account["account_type"] == "credit"
    assert int(account.get("is_default") or 0) == 1

    service.delete(created.selected_id)
    assert db.account.get(created.selected_id) is None


def test_tags_view_service_load_state_uses_report_counts(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    service = TagsViewService(db)
    tag = db.tag.create("Fixed", color="#336699")

    monkeypatch.setattr(db.report, "tag_transaction_counts", lambda **_kwargs: {int(tag["id"]): 3})
    monkeypatch.setattr(
        db.transaction,
        "list",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("legacy transaction listing should not be used")),
    )

    state = service.load_state()

    assert state.monthly_counts[int(tag["id"])] == 3
    assert any(int(item["id"]) == int(tag["id"]) for item in state.tags)


def test_settings_view_service_save_roundtrip(db: Database) -> None:
    service = SettingsViewService(db)

    saved = service.save(
        username="Alex",
        language="en",
        theme="dark_teal.xml",
        thousands_sep=" ",
        decimal_sep=",",
        preferred_model="tiny.gguf",
        interaction_mode="assistant",
    )

    assert saved.username == "Alex"
    assert saved.language == "en"
    assert saved.thousands_sep == " "
    assert saved.decimal_sep == ","
    assert saved.preferred_model == "tiny.gguf"
    assert service.load_state() == saved


def test_settings_view_service_save_rejects_equal_separators_without_persisting(db: Database) -> None:
    service = SettingsViewService(db)
    db.setting.set("username", "Alex")
    db.setting.set("language", "en")
    db.setting.set("theme", "dark_teal.xml")
    db.setting.set("number_thousands_separator", ",")
    db.setting.set("number_decimal_separator", ".")
    db.setting.set("preferred_model", "tiny.gguf")
    db.setting.set("llm_interaction_mode", "assistant")

    with pytest.raises(ValueError, match="different"):
        service.save(
            username="Bianca",
            language="es",
            theme="light_blue.xml",
            thousands_sep=".",
            decimal_sep=".",
            preferred_model="other.gguf",
            interaction_mode="chat",
        )

    assert db.setting.get("username") == "Alex"
    assert db.setting.get("language") == "en"
    assert db.setting.get("theme") == "dark_teal.xml"
    assert db.setting.get("number_thousands_separator") == ","
    assert db.setting.get("number_decimal_separator") == "."
    assert db.setting.get("preferred_model") == "tiny.gguf"
    assert db.setting.get("llm_interaction_mode") == "assistant"


def test_settings_view_service_load_state_normalizes_legacy_ambiguous_separators(db: Database) -> None:
    service = SettingsViewService(db)
    db.setting.set("number_thousands_separator", ".")
    db.setting.set("number_decimal_separator", ".")

    state = service.load_state()

    assert state.thousands_sep == "."
    assert state.decimal_sep == ","
    assert db.setting.get("number_thousands_separator") == "."
    assert db.setting.get("number_decimal_separator") == "."


def test_savings_goals_view_service_roundtrip(db: Database) -> None:
    service = SavingsGoalsViewService(db)

    created = service.create(name="Emergency Fund", target_amount=500.0, target_date="2026-12-31")
    assert created.selected_id is not None

    service.contribute(created.selected_id, 75.0)
    service.update(created.selected_id, name="Emergency Fund+", target_amount=600.0, target_date="2027-01-31")

    state = service.load_state()
    goal = next(item for item in state.goals if int(item["id"]) == int(created.selected_id))
    assert goal["name"] == "Emergency Fund+"
    assert float(goal["current_amount"]) == pytest.approx(75.0)
    assert float(goal["target_amount"]) == pytest.approx(600.0)

    service.delete(created.selected_id)
    with pytest.raises(ValueError, match="not found"):
        db.savings_goal.get(created.selected_id)


def test_categories_view_service_load_state_and_merge(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    service = CategoriesViewService(db)
    source = db.category.create("Coffee", "expense")
    target = db.category.create("Food", "expense")

    monkeypatch.setattr(db.report, "category_transaction_counts", lambda **_kwargs: {"Coffee": 2, "Food": 5})

    state = service.load_state()
    assert state.monthly_counts == {"Coffee": 2, "Food": 5}
    assert any(item["name"] == "Coffee" for item in state.expense_categories)

    feedback = service.merge(int(source["id"]), int(target["id"]))
    assert feedback.selected_id == int(target["id"])


def test_recurring_view_service_apply_returns_created_count(db: Database) -> None:
    service = RecurringViewService(db)
    account = db.account.get_or_create("General")
    category = db.category.create("Internet", "expense")

    created = service.create(
        {
            "account_id": account["id"],
            "tx_type": "expense",
            "amount": 40.0,
            "description": "Home Internet",
            "category_id": category["id"],
            "tag_ids": [],
            "note": "monthly",
            "day_of_month": 10,
        }
    )
    assert created.selected_id is not None

    applied = service.apply_for_month(2026, 3)

    assert int(applied.payload["created_count"]) == 1
    transactions = db.transaction.list(limit=50, since_date="2026-03-01", until_date="2026-03-31")
    assert any(tx.get("description") == "Home Internet" for tx in transactions)
