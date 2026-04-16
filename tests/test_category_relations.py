# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Tests for income↔expense category relations."""

from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from mira.db.database import Database
from mira.db.migrations import _migrate_v2_to_v3
from mira.reports.mira_master import _build_income_vs_expense_section

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    d = Database(path=tmp_path / "test.db")
    d.connect()
    yield d
    d.close()


def _seed_income_expense_parents(db: Database) -> dict[str, int]:
    """Create two income and three expense level-1 categories and return id map."""
    ids: dict[str, int] = {}
    for name, cat_type in [
        ("Salary", "income"),
        ("Rental", "income"),
        ("Housing", "expense"),
        ("Food", "expense"),
        ("Transport", "expense"),
    ]:
        cat = db.category.get_or_create(name, cat_type)
        ids[name] = int(cat["id"])
    return ids


# ---------------------------------------------------------------------------
# CategoryFacade / Repository CRUD
# ---------------------------------------------------------------------------


class TestCategoryRelationCRUD:
    """Validate create, list, and delete operations for category relations."""

    def test_create_and_list_relation(self, db: Database) -> None:
        ids = _seed_income_expense_parents(db)
        result = db.category.create_relation(ids["Salary"], ids["Housing"])
        assert result["income_category_id"] == ids["Salary"]
        assert result["expense_category_id"] == ids["Housing"]

        relations = db.category.list_relations()
        assert len(relations) == 1
        assert relations[0]["income_category_name"] == "Salary"
        assert relations[0]["expense_category_name"] == "Housing"

    def test_one_income_many_expenses(self, db: Database) -> None:
        ids = _seed_income_expense_parents(db)
        db.category.create_relation(ids["Salary"], ids["Housing"])
        db.category.create_relation(ids["Salary"], ids["Food"])
        db.category.create_relation(ids["Salary"], ids["Transport"])

        relations = db.category.list_relations()
        assert len(relations) == 3
        income_names = {r["income_category_name"] for r in relations}
        assert income_names == {"Salary"}
        expense_names = {r["expense_category_name"] for r in relations}
        assert expense_names == {"Housing", "Food", "Transport"}

    def test_expense_cannot_be_linked_twice(self, db: Database) -> None:
        ids = _seed_income_expense_parents(db)
        db.category.create_relation(ids["Salary"], ids["Housing"])
        with pytest.raises(ValueError, match="already linked"):
            db.category.create_relation(ids["Rental"], ids["Housing"])

    def test_reject_non_income_category(self, db: Database) -> None:
        ids = _seed_income_expense_parents(db)
        with pytest.raises(ValueError, match="not an income"):
            db.category.create_relation(ids["Housing"], ids["Food"])

    def test_reject_non_expense_category(self, db: Database) -> None:
        ids = _seed_income_expense_parents(db)
        with pytest.raises(ValueError, match="not an expense"):
            db.category.create_relation(ids["Salary"], ids["Rental"])

    def test_reject_child_income_category(self, db: Database) -> None:
        ids = _seed_income_expense_parents(db)
        child = db.category.create("Bonus", "income", parent_id=ids["Salary"])
        with pytest.raises(ValueError, match="not a level-1"):
            db.category.create_relation(int(child["id"]), ids["Housing"])

    def test_reject_child_expense_category(self, db: Database) -> None:
        ids = _seed_income_expense_parents(db)
        child = db.category.create("Rent", "expense", parent_id=ids["Housing"])
        with pytest.raises(ValueError, match="not a level-1"):
            db.category.create_relation(ids["Salary"], int(child["id"]))

    def test_reject_nonexistent_income(self, db: Database) -> None:
        ids = _seed_income_expense_parents(db)
        with pytest.raises(ValueError, match="not found"):
            db.category.create_relation(99999, ids["Housing"])

    def test_reject_nonexistent_expense(self, db: Database) -> None:
        ids = _seed_income_expense_parents(db)
        with pytest.raises(ValueError, match="not found"):
            db.category.create_relation(ids["Salary"], 99999)

    def test_delete_relation(self, db: Database) -> None:
        ids = _seed_income_expense_parents(db)
        rel = db.category.create_relation(ids["Salary"], ids["Housing"])
        db.category.delete_relation(rel["id"])
        assert db.category.list_relations() == []

    def test_delete_nonexistent_relation(self, db: Database) -> None:
        with pytest.raises(ValueError, match="not found"):
            db.category.delete_relation(99999)

    def test_linked_expense_ids(self, db: Database) -> None:
        ids = _seed_income_expense_parents(db)
        db.category.create_relation(ids["Salary"], ids["Housing"])
        db.category.create_relation(ids["Salary"], ids["Food"])
        linked = db.category.linked_expense_ids()
        assert linked == {ids["Housing"], ids["Food"]}

    def test_list_ordered_by_income_then_expense(self, db: Database) -> None:
        ids = _seed_income_expense_parents(db)
        db.category.create_relation(ids["Salary"], ids["Transport"])
        db.category.create_relation(ids["Rental"], ids["Housing"])
        db.category.create_relation(ids["Salary"], ids["Food"])

        relations = db.category.list_relations()
        names = [(r["income_category_name"], r["expense_category_name"]) for r in relations]
        assert names == [
            ("Rental", "Housing"),
            ("Salary", "Food"),
            ("Salary", "Transport"),
        ]

    def test_cascade_delete_income_category_removes_relations(self, db: Database) -> None:
        ids = _seed_income_expense_parents(db)
        db.category.create_relation(ids["Salary"], ids["Housing"])
        db.category.create_relation(ids["Salary"], ids["Food"])
        db.category.delete(ids["Salary"])
        assert db.category.list_relations() == []

    def test_cascade_delete_expense_category_removes_relation(self, db: Database) -> None:
        ids = _seed_income_expense_parents(db)
        db.category.create_relation(ids["Salary"], ids["Housing"])
        db.category.create_relation(ids["Salary"], ids["Food"])
        db.category.delete(ids["Housing"])
        relations = db.category.list_relations()
        assert len(relations) == 1
        assert relations[0]["expense_category_name"] == "Food"

    def test_rename_category_does_not_break_relation(self, db: Database) -> None:
        ids = _seed_income_expense_parents(db)
        db.category.create_relation(ids["Salary"], ids["Housing"])
        db.category.update(ids["Salary"], "Monthly Salary", "income")
        relations = db.category.list_relations()
        assert len(relations) == 1
        assert relations[0]["income_category_name"] == "Monthly Salary"


# ---------------------------------------------------------------------------
# CategoriesViewService helpers
# ---------------------------------------------------------------------------


class TestCategoriesViewServiceRelations:
    def test_parent_income_categories(self, db: Database) -> None:
        from mira.app.view_services.categories import CategoriesViewService

        ids = _seed_income_expense_parents(db)
        db.category.create("Bonus", "income", parent_id=ids["Salary"])
        svc = CategoriesViewService(db)
        parents = svc.parent_income_categories()
        names = {c["name"] for c in parents}
        assert "Salary" in names
        assert "Rental" in names
        assert "Bonus" not in names

    def test_available_parent_expense_excludes_linked(self, db: Database) -> None:
        from mira.app.view_services.categories import CategoriesViewService

        ids = _seed_income_expense_parents(db)
        db.category.create_relation(ids["Salary"], ids["Housing"])
        svc = CategoriesViewService(db)
        available = svc.available_parent_expense_categories()
        names = {c["name"] for c in available}
        assert "Housing" not in names
        assert "Food" in names
        assert "Transport" in names


# ---------------------------------------------------------------------------
# Migration idempotency
# ---------------------------------------------------------------------------


class TestMigrationIdempotency:
    def test_v2_to_v3_creates_relations_table(self, tmp_path) -> None:
        db_path = tmp_path / "migrate.db"
        database = Database(path=db_path)
        database.connect()
        database.close()

        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA user_version = 2")
            conn.execute("DROP TABLE IF EXISTS income_expense_relations")
            conn.commit()

        database = Database(path=db_path)
        database.connect()
        try:
            tables = {
                row[0]
                for row in database._backend._require_connection()
                .execute("SELECT name FROM sqlite_master WHERE type='table'")
                .fetchall()
            }
            assert "income_expense_relations" in tables
        finally:
            database.close()

    def test_v2_to_v3_idempotent_rerun(self, tmp_path) -> None:
        db_path = tmp_path / "idem.db"
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS accounts"
            "(id INTEGER PRIMARY KEY, name TEXT UNIQUE, balance_cents INTEGER DEFAULT 0,"
            " account_type TEXT DEFAULT 'bank', currency TEXT DEFAULT 'USD',"
            " is_default INTEGER DEFAULT 0, created_at TIMESTAMP)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS categories"
            "(id INTEGER PRIMARY KEY, name TEXT UNIQUE, type TEXT,"
            " color TEXT DEFAULT '#888888', icon TEXT DEFAULT '',"
            " is_savings INTEGER DEFAULT 0, parent_id INTEGER)"
        )
        conn.execute("PRAGMA user_version = 2")
        conn.commit()

        # Run migration twice — must not raise.
        _migrate_v2_to_v3(conn)
        _migrate_v2_to_v3(conn)
        conn.commit()

        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "income_expense_relations" in tables
        conn.close()


# ---------------------------------------------------------------------------
# Report section: _build_income_vs_expense_section
# ---------------------------------------------------------------------------


class TestBuildIncomeVsExpenseSection:
    def test_returns_none_without_relations(self) -> None:
        assert _build_income_vs_expense_section([], {}, {}) is None

    def test_returns_none_with_empty_names(self) -> None:
        result = _build_income_vs_expense_section(
            [{"income_category_name": "", "expense_category_name": ""}],
            {},
            {},
        )
        assert result is None

    def test_single_income_multiple_expenses(self) -> None:
        relations: list[dict[str, Any]] = [
            {"income_category_name": "Salary", "expense_category_name": "Housing"},
            {"income_category_name": "Salary", "expense_category_name": "Food"},
            {"income_category_name": "Salary", "expense_category_name": "Transport"},
        ]
        income_by_root = {"Salary": 2000.0}
        expense_by_root = {"Housing": 300.0, "Food": 400.0, "Transport": 500.0}

        result = _build_income_vs_expense_section(relations, income_by_root, expense_by_root)

        assert result is not None
        assert len(result) == 1
        entry = result[0]
        assert entry["income_category"] == "Salary"
        assert entry["income_amount"] == 2000.0
        assert len(entry["expenses"]) == 3
        assert entry["expense_total"] == 1200.0
        expense_names = [e["category"] for e in entry["expenses"]]
        assert expense_names == sorted(expense_names)

    def test_multiple_income_categories(self) -> None:
        relations: list[dict[str, Any]] = [
            {"income_category_name": "Salary", "expense_category_name": "Housing"},
            {"income_category_name": "Salary", "expense_category_name": "Food"},
            {"income_category_name": "Rental", "expense_category_name": "Maintenance"},
            {"income_category_name": "Rental", "expense_category_name": "Taxes"},
        ]
        income_by_root = {"Salary": 2000.0, "Rental": 500.0}
        expense_by_root = {"Housing": 300.0, "Food": 400.0, "Maintenance": 200.0, "Taxes": 100.0}

        result = _build_income_vs_expense_section(relations, income_by_root, expense_by_root)

        assert result is not None
        assert len(result) == 2
        # Sorted alphabetically by income category
        assert result[0]["income_category"] == "Rental"
        assert result[0]["income_amount"] == 500.0
        assert result[0]["expense_total"] == 300.0
        assert result[1]["income_category"] == "Salary"
        assert result[1]["income_amount"] == 2000.0
        assert result[1]["expense_total"] == 700.0

    def test_missing_amounts_default_to_zero(self) -> None:
        relations: list[dict[str, Any]] = [
            {"income_category_name": "Salary", "expense_category_name": "Housing"},
        ]
        result = _build_income_vs_expense_section(relations, {}, {})

        assert result is not None
        assert result[0]["income_amount"] == 0.0
        assert result[0]["expense_total"] == 0.0

    def test_amounts_are_rounded(self) -> None:
        relations: list[dict[str, Any]] = [
            {"income_category_name": "Salary", "expense_category_name": "Food"},
        ]
        result = _build_income_vs_expense_section(
            relations,
            {"Salary": 1000.006},
            {"Food": 123.456},
        )
        assert result is not None
        assert result[0]["income_amount"] == 1000.01
        assert result[0]["expenses"][0]["amount"] == 123.46


# ---------------------------------------------------------------------------
# Integration: full report includes income_vs_expense_by_income
# ---------------------------------------------------------------------------


class TestReportIncludesIncomeVsExpense:
    def test_report_omits_section_when_no_relations(self, db: Database) -> None:
        _seed_income_expense_parents(db)
        db.account.get_or_create("General")
        db.transaction.create(
            tx_type="income",
            amount=1000,
            description="test",
            category="Salary",
            account_id=1,
        )
        report = db.report.get_mira_master_report(year=2025, month=1)
        assert report["income_vs_expense_by_income"] is None

    def test_report_shows_section_with_relations(self, db: Database) -> None:
        ids = _seed_income_expense_parents(db)
        db.category.create_relation(ids["Salary"], ids["Housing"])
        db.category.create_relation(ids["Salary"], ids["Food"])
        acc = db.account.get_or_create("General")
        acc_id = int(acc["id"])
        db.transaction.create(
            tx_type="income",
            amount=2000,
            description="salary",
            category="Salary",
            account_id=acc_id,
            tx_date="2025-01-15",
        )
        db.transaction.create(
            tx_type="expense",
            amount=300,
            description="rent",
            category="Housing",
            account_id=acc_id,
            tx_date="2025-01-15",
        )
        db.transaction.create(
            tx_type="expense",
            amount=400,
            description="groceries",
            category="Food",
            account_id=acc_id,
            tx_date="2025-01-15",
        )

        report = db.report.get_mira_master_report(year=2025, month=1)
        section = report["income_vs_expense_by_income"]
        assert section is not None
        assert len(section) == 1
        entry = section[0]
        assert entry["income_category"] == "Salary"
        assert entry["income_amount"] == 2000.0
        assert entry["expense_total"] == 700.0
        expense_cats = [e["category"] for e in entry["expenses"]]
        assert "Housing" in expense_cats
        assert "Food" in expense_cats

    def test_report_respects_month_filter(self, db: Database) -> None:
        """Amounts must come only from the requested month."""
        ids = _seed_income_expense_parents(db)
        db.category.create_relation(ids["Salary"], ids["Housing"])
        acc = db.account.get_or_create("General")
        acc_id = int(acc["id"])
        # January transaction
        db.transaction.create(
            tx_type="income",
            amount=1000,
            description="jan salary",
            category="Salary",
            account_id=acc_id,
            tx_date="2025-01-15",
        )
        db.transaction.create(
            tx_type="expense",
            amount=300,
            description="jan rent",
            category="Housing",
            account_id=acc_id,
            tx_date="2025-01-15",
        )
        # February transaction (should NOT appear in January report)
        db.transaction.create(
            tx_type="income",
            amount=5000,
            description="feb salary",
            category="Salary",
            account_id=acc_id,
            tx_date="2025-02-15",
        )
        db.transaction.create(
            tx_type="expense",
            amount=900,
            description="feb rent",
            category="Housing",
            account_id=acc_id,
            tx_date="2025-02-15",
        )

        jan_report = db.report.get_mira_master_report(year=2025, month=1)
        section = jan_report["income_vs_expense_by_income"]
        assert section is not None
        entry = section[0]
        assert entry["income_amount"] == 1000.0
        assert entry["expense_total"] == 300.0
