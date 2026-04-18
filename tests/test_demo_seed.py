# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from mira.db import demo_seed


@dataclass(frozen=True)
class FakeCategoryRow:
    id: int
    name: str


class FakeDemoSeedDB:
    def __init__(self) -> None:
        self.deleted_transaction_ids: list[int] = []
        self.deleted_budget_id: int | None = None
        self.default_set_account_id: int | None = None
        self.created_accounts: list[dict[str, Any]] = []
        self.goals_created: list[dict[str, Any]] = []
        self.upsert_calls: list[tuple[int, int, int, int, float]] = []
        self.transactions: list[dict[str, Any]] = []

    def get_category_by_name(self, name: str, cat_type: str) -> dict[str, Any] | None:
        return self._categories.get((name, cat_type))

    def get_tag_by_name(self, name: str) -> dict[str, Any] | None:
        return self._tags.get(name)

    def get_default_account(self) -> dict[str, Any] | None:
        return self._default_account

    def get_account_by_name(self, name: str) -> dict[str, Any] | None:
        return self._accounts_by_name.get(name)

    def get_or_create_account(self, name: str) -> dict[str, Any]:
        return self.add_account(name=name, account_type="bank", opening_balance=0.0, currency="USD")

    def set_default_account(self, account_id: int) -> None:
        self.default_set_account_id = account_id

    def add_account(self, name: str, account_type: str, opening_balance: float, currency: str) -> dict[str, Any]:
        account = {"id": len(self.created_accounts) + 1, "name": name, "account_type": account_type, "currency": currency}
        self.created_accounts.append(account)
        self._accounts_by_name[name] = account
        return account

    def get_default_currency(self) -> str:
        return "USD"

    def get_savings_goal_by_name(self, name: str) -> dict[str, Any] | None:
        return None

    def add_savings_goal(
        self,
        *,
        name: str,
        target_amount: float,
        target_date: str,
        currency: str,
        category_name: str,
    ) -> None:
        self.goals_created.append(
            {
                "name": name,
                "target_amount": target_amount,
                "target_date": target_date,
                "currency": currency,
                "category_name": category_name,
            }
        )

    def get_budget_by_code(self, code: str) -> dict[str, Any] | None:
        return self._budget_by_code.get(code)

    def delete_transaction(self, tx_id: int) -> None:
        self.deleted_transaction_ids.append(tx_id)

    def delete_budget(self, budget_id: int) -> None:
        self.deleted_budget_id = budget_id

    def upsert_budget_amount(
        self,
        budget_id: int,
        category_id: int,
        year: int,
        month: int,
        amount: float,
    ) -> None:
        self.upsert_calls.append((budget_id, category_id, year, month, amount))

    def prepare_categories(self, categories: dict[tuple[str, str], dict[str, Any]]) -> None:
        self._categories = categories

    def prepare_tags(self, tags: dict[str, dict[str, Any]]) -> None:
        self._tags = tags

    def prepare_accounts(
        self,
        default_account: dict[str, Any] | None = None,
        named_accounts: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._default_account = default_account
        self._accounts_by_name = named_accounts or {}

    def prepare_budgets(self, budgets: dict[str, dict[str, Any]]) -> None:
        self._budget_by_code = budgets


class FakeField:
    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, other: object) -> bool:
        return True

    def desc(self) -> "FakeField":
        return self


@dataclass(frozen=True)
class FakeTransaction:
    id: int


class FakeTransactionQuery:
    def __init__(self, transactions: list[FakeTransaction]) -> None:
        self._transactions = transactions

    def where(self, *args: Any, **kwargs: Any) -> "FakeTransactionQuery":
        return self

    def order_by(self, *args: Any, **kwargs: Any) -> "FakeTransactionQuery":
        return self

    def __iter__(self) -> Any:
        return iter(self._transactions)


class FakeTransactionModel:
    id = FakeField("id")
    note = FakeField("note")

    @classmethod
    def select(cls, *args: Any) -> FakeTransactionQuery:
        return FakeTransactionQuery([FakeTransaction(1), FakeTransaction(2)])


def test_build_demo_seed_runtime_and_result() -> None:
    runtime = demo_seed.build_demo_seed_runtime(
        year=2026,
        budget_id=33,
        default_account={"id": "10"},
        reserve_account={"id": "20"},
        seed_note="seed-note",
        category_rows={"salary": {"id": 1, "name": "Salary"}},
        tag_rows={"fixed": {"id": 2, "name": "Fixed"}},
        descriptions={"salary": "Salary"},
    )

    assert runtime.year == 2026
    assert runtime.budget_id == 33
    assert runtime.default_account_id == 10
    assert runtime.reserve_account_id == 20
    assert runtime.seed_note == "seed-note"
    assert runtime.category_rows["salary"]["name"] == "Salary"

    result = demo_seed.build_demo_seed_result(
        year=2026,
        budget_code="mira_cli_seed_2026",
        budget_id=33,
        transactions_created=120,
        tag_links_created=80,
        language="es",
    )

    assert result == {
        "year": 2026,
        "budget_code": "mira_cli_seed_2026",
        "budget_id": 33,
        "transactions_created": 120,
        "tag_links_created": 80,
        "language": "es",
    }


def test_resolve_seed_categories_returns_rows_and_reports_missing() -> None:
    db = FakeDemoSeedDB()
    db.prepare_categories(
        {
            ("Salary", "income"): {"id": 1, "name": "Salary"},
            ("Food", "expense"): {"id": 2, "name": "Food"},
        }
    )

    catalog = demo_seed.DemoSeedCatalog(
        main_account="Main",
        reserve_account="Reserve",
        categories={
            "salary": ("Salary", "income"),
            "food": ("Food", "expense"),
        },
        tags={"fixed": "Fixed"},
        descriptions={"salary": "Salary"},
    )

    rows = demo_seed.resolve_seed_categories(db, catalog)
    assert rows["salary"]["id"] == 1
    assert rows["food"]["id"] == 2

    db.prepare_categories({("Salary", "income"): {"id": 1, "name": "Salary"}})
    with pytest.raises(ValueError, match="Missing: Food"):
        demo_seed.resolve_seed_categories(db, catalog)


def test_resolve_seed_tags_filters_missing_items() -> None:
    db = FakeDemoSeedDB()
    db.prepare_tags({"Fixed": {"id": 1, "name": "Fixed"}})

    catalog = demo_seed.DemoSeedCatalog(
        main_account="Main",
        reserve_account="Reserve",
        categories={"salary": ("Salary", "income")},
        tags={"fixed": "Fixed", "variable": "Variable"},
        descriptions={"salary": "Salary"},
    )

    tags = demo_seed.resolve_seed_tags(db, catalog)
    assert tags == {"fixed": {"id": 1, "name": "Fixed"}}


def test_ensure_seed_accounts_creates_missing_accounts_and_sets_default() -> None:
    db = FakeDemoSeedDB()
    db.prepare_accounts(default_account=None, named_accounts={})
    catalog = demo_seed.DemoSeedCatalog(
        main_account="Main account",
        reserve_account="Reserve account",
        categories={"salary": ("Salary", "income")},
        tags={"fixed": "Fixed"},
        descriptions={"salary": "Salary"},
    )

    default_account, reserve_account = demo_seed.ensure_seed_accounts(db, catalog)

    assert default_account["name"] == "Main account"
    assert reserve_account["name"] == "Reserve account"
    assert db.default_set_account_id == 1
    assert reserve_account["id"] == 2


def test_ensure_seed_goals_adds_missing_savings_goals() -> None:
    db = FakeDemoSeedDB()
    category_rows = {
        "emergency_fund": {"id": 1, "name": "Emergency"},
        "retirement": {"id": 2, "name": "Retirement"},
    }

    demo_seed.ensure_seed_goals(db, year=2025, category_rows=category_rows)
    assert len(db.goals_created) == 2
    assert db.goals_created[0]["name"] == "Emergency"
    assert db.goals_created[1]["name"] == "Retirement"


def test_reset_seed_artifacts_deletes_transactions_and_budget() -> None:
    db = FakeDemoSeedDB()
    db.prepare_budgets({"mira_cli_seed_2024": {"id": 13}})

    seed_note, budget_code = demo_seed.reset_seed_artifacts(
        db,
        year=2024,
        transaction_model=FakeTransactionModel,
    )

    assert seed_note == "mira_cli_seed:2024"
    assert budget_code == "mira_cli_seed_2024"
    assert db.deleted_transaction_ids == [1, 2]
    assert db.deleted_budget_id == 13


def test_build_and_seed_budget_plan_calls_upsert_for_every_category_and_month() -> None:
    db = FakeDemoSeedDB()
    budget_plan = demo_seed.build_budget_plan()
    category_rows = {key: {"id": idx + 1, "name": key} for idx, key in enumerate(budget_plan)}

    demo_seed.seed_budget_plan(
        db,
        budget_id=27,
        year=2026,
        category_rows=category_rows,
        budget_plan=budget_plan,
    )

    assert len(db.upsert_calls) == 12 * len(budget_plan)
    assert db.upsert_calls[0][0] == 27
    assert db.upsert_calls[0][2] == 2026


class FakeSeedMonthlyDB:
    def __init__(self) -> None:
        self.transactions: list[dict[str, Any]] = []
        self.tag_links: list[tuple[int, int]] = []
        self.transfer_calls: list[tuple[int, int, float, str, str]] = []
        self._next_transaction_id = 1

    def add_transaction(
        self,
        *,
        account_id: int,
        tx_type: str,
        amount: float,
        category: str,
        description: str | None = None,
        tx_date: str | None = None,
        note: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        transaction = {
            "id": self._next_transaction_id,
            "account_id": account_id,
            "tx_type": tx_type,
            "amount": amount,
            "category": category,
            "description": description,
            "date": tx_date,
            "note": note,
        }
        self._next_transaction_id += 1
        self.transactions.append(transaction)
        return transaction

    def add_transaction_tag(self, transaction_id: int, tag_id: int) -> None:
        self.tag_links.append((transaction_id, tag_id))

    def transfer_between_accounts(
        self,
        *,
        from_account_id: int,
        to_account_id: int,
        amount: float,
        note: str | None = None,
        tx_date: str | None = None,
        description: str | None = None,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        self.transfer_calls.append((from_account_id, to_account_id, amount, note or "", str(tx_date)))
        self._next_transaction_id += 2
        return ({"id": self._next_transaction_id - 2}, {"id": self._next_transaction_id - 1})


def test_seed_monthly_transactions_creates_expected_transactions_and_tag_links() -> None:
    db = FakeSeedMonthlyDB()
    budget_plan = demo_seed.build_budget_plan()
    category_rows = {key: {"id": idx + 1, "name": key} for idx, key in enumerate(budget_plan)}
    descriptions = {
        key: key
        for key in {
            "salary",
            "freelance",
            "bonus",
            "item_sales",
            "rent_income",
            "interest_income",
            "housing",
            "home_maintenance",
            "utilities",
            "telecom",
            "food_a",
            "food_b",
            "transport",
            "public_transport",
            "health",
            "health_insurance",
            "tuition",
            "books",
            "life_insurance",
            "property_insurance",
            "credit_cards",
            "personal_loans",
            "subscriptions",
            "restaurants",
            "savings",
            "emergency_fund",
            "retirement",
            "transfer",
        }
    }
    runtime = demo_seed.build_demo_seed_runtime(
        year=2026,
        budget_id=1,
        default_account={"id": "1"},
        reserve_account={"id": "2"},
        seed_note="mira_cli_seed:2026",
        category_rows=category_rows,
        tag_rows={"fixed": {"id": 1}, "variable": {"id": 2}, "essential": {"id": 3}, "discretionary": {"id": 4}},
        descriptions=descriptions,
    )

    tx_count, tag_links = demo_seed.seed_monthly_transactions(db, runtime, budget_plan)

    assert tx_count == len(db.transactions) + 8
    assert len(db.transfer_calls) == 4
    assert tag_links == len(db.tag_links)
    assert tag_links > 0
    assert any(tx["category"] == "savings" for tx in db.transactions)
    assert any(tx["note"] == "mira_cli_seed:2026" for tx in db.transactions)

