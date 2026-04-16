# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Shared helpers for demo data seeding."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from typing import Any, Protocol


class DemoSeedDatabase(Protocol):
    """Represent the DemoSeedDatabase class."""

    def add_transaction(self, **kwargs: Any) -> dict[str, Any]:
        """Return add transaction."""
        ...

    def add_transaction_tag(self, transaction_id: int, tag_id: int) -> None:
        """Return add transaction tag."""
        ...

    def transfer_between_accounts(
        self,
        *,
        from_account_id: int,
        to_account_id: int,
        amount: float,
        note: str | None,
        tx_date: str,
        description: str | None,
    ) -> None:
        """Return transfer between accounts."""
        ...

    def upsert_budget_amount(
        self,
        budget_id: int,
        category_id: int,
        year: int,
        month: int,
        amount: float,
    ) -> None:
        """Return upsert budget amount."""
        ...

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        """Return get setting."""
        ...

    def get_category_by_name(self, name: str, cat_type: str) -> dict[str, Any] | None:
        """Return get category by name."""
        ...

    def get_tag_by_name(self, name: str) -> dict[str, Any] | None:
        """Return get tag by name."""
        ...

    def get_default_account(self) -> dict[str, Any] | None:
        """Return get default account."""
        ...

    def get_account_by_name(self, name: str) -> dict[str, Any] | None:
        """Return get account by name."""
        ...

    def get_or_create_account(self, name: str) -> dict[str, Any]:
        """Return get or create account."""
        ...

    def set_default_account(self, account_id: int) -> None:
        """Return set default account."""
        ...

    def add_account(self, name: str, account_type: str, opening_balance: float, currency: str) -> dict[str, Any]:
        """Return add account."""
        ...

    def get_default_currency(self) -> str:
        """Return get default currency."""
        ...

    def get_savings_goal_by_name(self, name: str) -> dict[str, Any] | None:
        """Return get savings goal by name."""
        ...

    def add_savings_goal(
        self,
        *,
        name: str,
        target_amount: float,
        target_date: str,
        currency: str,
        category_name: str,
    ) -> None:
        """Return add savings goal."""
        ...

    def get_budget_by_code(self, code: str) -> dict[str, Any] | None:
        """Return get budget by code."""
        ...

    def delete_budget(self, budget_id: int) -> None:
        """Return delete budget."""
        ...

    def create_budget(self, code: str, year: int, currency: str) -> dict[str, Any]:
        """Return create budget."""
        ...

    def delete_transaction(self, tx_id: int) -> None:
        """Return delete transaction."""
        ...


@dataclass(frozen=True)
class DemoSeedCatalog:
    """Represent the DemoSeedCatalog class."""

    main_account: str

    reserve_account: str
    categories: dict[str, tuple[str, str]]
    tags: dict[str, str]
    descriptions: dict[str, str]


@dataclass(frozen=True)
class DemoSeedRuntime:
    """Represent the DemoSeedRuntime class."""

    year: int

    budget_id: int
    default_account_id: int
    reserve_account_id: int
    seed_note: str
    category_rows: dict[str, dict[str, Any]]
    tag_rows: dict[str, dict[str, Any]]
    descriptions: dict[str, str]


def build_demo_seed_runtime(
    *,
    year: int,
    budget_id: int,
    default_account: dict[str, Any],
    reserve_account: dict[str, Any],
    seed_note: str,
    category_rows: dict[str, dict[str, Any]],
    tag_rows: dict[str, dict[str, Any]],
    descriptions: dict[str, str],
) -> DemoSeedRuntime:
    """Return build demo seed runtime."""
    return DemoSeedRuntime(
        year=year,
        budget_id=budget_id,
        default_account_id=int(default_account["id"]),
        reserve_account_id=int(reserve_account["id"]),
        seed_note=seed_note,
        category_rows=category_rows,
        tag_rows=tag_rows,
        descriptions=descriptions,
    )


def build_demo_seed_result(
    *,
    year: int,
    budget_code: str,
    budget_id: int,
    transactions_created: int,
    tag_links_created: int,
    language: str,
) -> dict[str, Any]:
    """Return build demo seed result."""
    return {
        "year": year,
        "budget_code": budget_code,
        "budget_id": budget_id,
        "transactions_created": transactions_created,
        "tag_links_created": tag_links_created,
        "language": language,
    }


def normalize_demo_seed_language(language: str | None) -> str:
    """Return normalize demo seed language."""
    normalized = (language or "en").strip().lower()
    return normalized if normalized in {"es", "en"} else "en"


def build_demo_seed_catalog(
    *,
    language: str,
    catalog_data: dict[str, dict[str, Any]],
    translate: Any,
) -> DemoSeedCatalog:
    """Return build demo seed catalog."""
    localized = catalog_data.get(language, catalog_data["en"])
    return DemoSeedCatalog(
        main_account=str(localized["main_account"]),
        reserve_account=str(localized["reserve_account"]),
        categories={
            "salary": (translate(language, "net_salary"), "income"),
            "freelance": (translate(language, "freelance"), "income"),
            "bonus": (translate(language, "bonuses"), "income"),
            "item_sales": (translate(language, "item_sales"), "income"),
            "rent_income": (translate(language, "rent_collected"), "income"),
            "interest_income": (translate(language, "investment_interest"), "income"),
            "housing": (translate(language, "rent_mortgage"), "expense"),
            "home_maintenance": (translate(language, "home_maintenance"), "expense"),
            "utilities": (translate(language, "electricity"), "expense"),
            "telecom": (translate(language, "internet_phone"), "expense"),
            "food": (translate(language, "groceries"), "expense"),
            "cleaning": (translate(language, "hygiene_cleaning"), "expense"),
            "transport": (translate(language, "fuel_tolls"), "expense"),
            "public_transport": (translate(language, "public_transport"), "expense"),
            "health": (translate(language, "pharmacy"), "expense"),
            "health_insurance": (translate(language, "health_insurance"), "expense"),
            "tuition": (translate(language, "tuition"), "expense"),
            "books": (translate(language, "books_courses"), "expense"),
            "life_insurance": (translate(language, "life_insurance"), "expense"),
            "property_insurance": (translate(language, "vehicle_home_insurance"), "expense"),
            "credit_cards": (translate(language, "credit_cards"), "expense"),
            "personal_loans": (translate(language, "personal_loans"), "expense"),
            "savings": (translate(language, "savings"), "expense"),
            "emergency_fund": (translate(language, "emergency_fund"), "expense"),
            "retirement": (translate(language, "retirement"), "expense"),
            "subscriptions": (translate(language, "subscriptions"), "expense"),
            "restaurants": (translate(language, "restaurants"), "expense"),
        },
        tags={
            "fixed": translate(language, "tag_fixed"),
            "variable": translate(language, "tag_variable"),
            "essential": translate(language, "tag_essential"),
            "discretionary": translate(language, "tag_discretionary"),
        },
        descriptions=localized["descriptions"],
    )


def resolve_seed_categories(db: DemoSeedDatabase, catalog: DemoSeedCatalog) -> dict[str, dict[str, Any]]:
    """Return resolve seed categories."""
    category_rows: dict[str, dict[str, Any]] = {}
    missing_categories: list[str] = []
    for key, (name, cat_type) in catalog.categories.items():
        if (category := db.get_category_by_name(name, cat_type)) is None:
            missing_categories.append(name)
            continue
        category_rows[key] = category
    if missing_categories:
        raise ValueError(
            "Seed requires the default category catalog for the database language. Missing: "
            + ", ".join(missing_categories)
        )
    return category_rows


def resolve_seed_tags(db: DemoSeedDatabase, catalog: DemoSeedCatalog) -> dict[str, dict[str, Any]]:
    """Return resolve seed tags."""
    tag_rows: dict[str, dict[str, Any]] = {}
    for key, name in catalog.tags.items():
        if (tag := db.get_tag_by_name(name)) is not None:
            tag_rows[key] = tag
    return tag_rows


def ensure_seed_accounts(db: DemoSeedDatabase, catalog: DemoSeedCatalog) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ensure seed accounts."""
    default_account = db.get_default_account()
    if default_account is None:
        default_account = db.get_account_by_name(catalog.main_account) or db.get_or_create_account(catalog.main_account)
        db.set_default_account(int(default_account["id"]))
    reserve_account = db.get_account_by_name(catalog.reserve_account)
    if reserve_account is None:
        reserve_account = db.add_account(
            name=catalog.reserve_account,
            account_type="bank",
            opening_balance=0.0,
            currency=db.get_default_currency(),
        )
    return default_account, reserve_account


def ensure_seed_goals(
    db: DemoSeedDatabase,
    *,
    year: int,
    category_rows: dict[str, dict[str, Any]],
) -> None:
    """Return ensure seed goals."""
    savings_goal_specs = [
        (str(category_rows["emergency_fund"]["name"]), 2500.0, f"{year + 1}-12-31", "emergency_fund"),
        (str(category_rows["retirement"]["name"]), 6000.0, f"{year + 3}-12-31", "retirement"),
    ]
    for goal_name, target_amount, target_date, category_key in savings_goal_specs:
        if db.get_savings_goal_by_name(goal_name) is None:
            db.add_savings_goal(
                name=goal_name,
                target_amount=target_amount,
                target_date=target_date,
                currency=db.get_default_currency(),
                category_name=str(category_rows[category_key]["name"]),
            )


def reset_seed_artifacts(
    db: DemoSeedDatabase,
    *,
    year: int,
    transaction_model: Any,
) -> tuple[str, str]:
    """Return reset seed artifacts."""
    seed_note = f"mira_cli_seed:{year}"
    budget_code = f"mira_cli_seed_{year}"
    seeded_ids = [
        int(tx.id)
        for tx in transaction_model.select(transaction_model.id)
        .where(transaction_model.note == seed_note)
        .order_by(transaction_model.id.desc())
    ]
    for tx_id in seeded_ids:
        db.delete_transaction(tx_id)
    if (existing_budget := db.get_budget_by_code(budget_code)) is not None:
        db.delete_budget(int(existing_budget["id"]))
    return seed_note, budget_code


def build_budget_plan() -> dict[str, list[float]]:
    """Return build budget plan."""
    return {
        "salary": [1850.0] * 12,
        "freelance": [180.0, 240.0, 190.0, 260.0, 210.0, 280.0, 200.0, 270.0, 220.0, 290.0, 210.0, 320.0],
        "bonus": [0.0, 0.0, 260.0, 0.0, 0.0, 280.0, 0.0, 0.0, 300.0, 0.0, 0.0, 350.0],
        "item_sales": [40.0, 0.0, 35.0, 0.0, 55.0, 0.0, 45.0, 0.0, 60.0, 0.0, 50.0, 0.0],
        "rent_income": [0.0, 0.0, 0.0, 220.0, 0.0, 0.0, 0.0, 220.0, 0.0, 0.0, 0.0, 220.0],
        "interest_income": [12.0, 12.0, 14.0, 14.0, 15.0, 15.0, 16.0, 16.0, 16.0, 18.0, 18.0, 20.0],
        "housing": [560.0] * 12,
        "home_maintenance": [0.0, 0.0, 35.0, 0.0, 0.0, 45.0, 0.0, 0.0, 40.0, 0.0, 0.0, 60.0],
        "utilities": [92.0, 94.0, 96.0, 98.0, 100.0, 104.0, 106.0, 104.0, 100.0, 98.0, 96.0, 94.0],
        "telecom": [42.0] * 12,
        "food": [250.0, 255.0, 265.0, 260.0, 270.0, 280.0, 275.0, 285.0, 278.0, 290.0, 282.0, 300.0],
        "cleaning": [35.0, 36.0, 38.0, 37.0, 39.0, 41.0, 40.0, 42.0, 41.0, 43.0, 42.0, 45.0],
        "transport": [85.0, 82.0, 88.0, 86.0, 90.0, 92.0, 91.0, 93.0, 89.0, 94.0, 90.0, 96.0],
        "public_transport": [20.0, 22.0, 21.0, 24.0, 25.0, 23.0, 26.0, 24.0, 23.0, 27.0, 25.0, 28.0],
        "health": [18.0, 0.0, 22.0, 0.0, 26.0, 18.0, 30.0, 0.0, 24.0, 0.0, 20.0, 28.0],
        "health_insurance": [48.0] * 12,
        "tuition": [75.0] * 12,
        "books": [12.0, 0.0, 18.0, 0.0, 15.0, 0.0, 20.0, 0.0, 18.0, 0.0, 24.0, 0.0],
        "life_insurance": [28.0] * 12,
        "property_insurance": [0.0, 45.0, 0.0, 0.0, 45.0, 0.0, 0.0, 45.0, 0.0, 0.0, 45.0, 0.0],
        "credit_cards": [78.0, 80.0, 82.0, 85.0, 87.0, 89.0, 90.0, 92.0, 94.0, 95.0, 97.0, 100.0],
        "personal_loans": [32.0] * 12,
        "savings": [90.0, 95.0, 90.0, 100.0, 95.0, 105.0, 100.0, 110.0, 105.0, 115.0, 110.0, 120.0],
        "emergency_fund": [60.0] * 12,
        "retirement": [45.0, 45.0, 50.0, 50.0, 50.0, 55.0, 55.0, 55.0, 60.0, 60.0, 60.0, 65.0],
        "subscriptions": [18.0, 18.0, 20.0, 20.0, 22.0, 22.0, 24.0, 24.0, 24.0, 26.0, 26.0, 28.0],
        "restaurants": [32.0, 36.0, 38.0, 35.0, 42.0, 45.0, 39.0, 48.0, 44.0, 50.0, 46.0, 55.0],
    }


def seed_budget_plan(
    db: DemoSeedDatabase,
    *,
    budget_id: int,
    year: int,
    category_rows: dict[str, dict[str, Any]],
    budget_plan: dict[str, list[float]],
) -> None:
    """Return seed budget plan."""
    for month in range(1, 13):
        for key, monthly_amounts in budget_plan.items():
            db.upsert_budget_amount(
                budget_id,
                int(category_rows[key]["id"]),
                year,
                month,
                float(monthly_amounts[month - 1]),
            )


def seed_monthly_transactions(
    db: DemoSeedDatabase,
    runtime: DemoSeedRuntime,
    budget_plan: dict[str, list[float]],
) -> tuple[int, int]:
    """Return seed monthly transactions."""
    tx_count = 0
    tag_links = 0

    def _attach_tags(transaction_id: int, *tag_keys: str) -> None:
        """Return attach tags."""
        nonlocal tag_links
        for tag_key in tag_keys:
            if (tag := runtime.tag_rows.get(tag_key)) is None:
                continue
            db.add_transaction_tag(transaction_id, int(tag["id"]))
            tag_links += 1

    def _add_seed_transaction(
        *,
        month: int,
        day: int,
        tx_type: str,
        amount: float,
        category_key: str,
        description_key: str,
        tag_keys: tuple[str, ...],
    ) -> None:
        """Return add seed transaction."""
        nonlocal tx_count
        valid_day = min(day, calendar.monthrange(runtime.year, month)[1])
        tx = db.add_transaction(
            account_id=runtime.default_account_id,
            tx_type=tx_type,
            amount=round(amount, 2),
            category=str(runtime.category_rows[category_key]["name"]),
            description=str(runtime.descriptions[description_key]),
            tx_date=f"{runtime.year}-{month:02d}-{valid_day:02d}",
            note=runtime.seed_note,
        )
        tx_count += 1
        _attach_tags(int(tx["id"]), *tag_keys)

    deficit_months = {2, 8, 11}
    strong_surplus_months = {3, 6, 12}
    for month in range(1, 13):
        salary_actual = 1810.0 + (month * 12.0)
        freelance_actual = budget_plan["freelance"][month - 1] + (-20.0 if month % 2 else 35.0)
        item_sales_actual = budget_plan["item_sales"][month - 1] + (10.0 if month in {5, 9} else 0.0)
        rent_income_actual = budget_plan["rent_income"][month - 1]
        interest_income_actual = budget_plan["interest_income"][month - 1] + (2.0 if month in {6, 12} else 0.0)
        housing_actual = budget_plan["housing"][month - 1] + (5.0 if month in {6, 12} else 0.0)
        home_maintenance_actual = budget_plan["home_maintenance"][month - 1] + (5.0 if month in {3, 6, 9, 12} else 0.0)
        utilities_actual = budget_plan["utilities"][month - 1] + (3.0 if month % 4 == 0 else -2.0)
        telecom_actual = budget_plan["telecom"][month - 1]
        food_total = budget_plan["food"][month - 1] + (8.0 if month in {3, 7, 12} else -6.0)
        cleaning_actual = budget_plan["cleaning"][month - 1] + (2.0 if month in {4, 8, 12} else 0.0)
        transport_actual = budget_plan["transport"][month - 1] + (4.0 if month % 3 == 0 else -3.0)
        public_transport_actual = budget_plan["public_transport"][month - 1] + (3.0 if month % 2 == 0 else -1.0)
        health_actual = budget_plan["health"][month - 1] + (6.0 if month in {7, 12} else 0.0)
        health_insurance_actual = budget_plan["health_insurance"][month - 1]
        tuition_actual = budget_plan["tuition"][month - 1]
        books_actual = budget_plan["books"][month - 1] + (4.0 if budget_plan["books"][month - 1] > 0 else 0.0)
        life_insurance_actual = budget_plan["life_insurance"][month - 1]
        property_insurance_actual = budget_plan["property_insurance"][month - 1]
        credit_cards_actual = budget_plan["credit_cards"][month - 1] + (8.0 if month in {4, 9} else 0.0)
        personal_loans_actual = budget_plan["personal_loans"][month - 1]
        savings_actual = budget_plan["savings"][month - 1] + (10.0 if month in {6, 12} else 0.0)
        emergency_actual = budget_plan["emergency_fund"][month - 1]
        retirement_actual = budget_plan["retirement"][month - 1] + (5.0 if month in {6, 12} else 0.0)
        subscriptions_actual = budget_plan["subscriptions"][month - 1]
        restaurants_actual = budget_plan["restaurants"][month - 1] + (6.0 if month in {5, 8, 12} else -3.0)

        if month in deficit_months:
            salary_actual -= 380.0
            freelance_actual = max(40.0, freelance_actual - 120.0)
            home_maintenance_actual += 260.0
            health_actual += 180.0
            transport_actual += 55.0
            restaurants_actual += 35.0
            subscriptions_actual += 10.0
            savings_actual = max(30.0, savings_actual - 45.0)
            retirement_actual = max(15.0, retirement_actual - 20.0)
        elif month in strong_surplus_months:
            salary_actual += 120.0
            freelance_actual += 60.0
            interest_income_actual += 4.0
            savings_actual += 35.0
            emergency_actual += 25.0
            retirement_actual += 20.0
            restaurants_actual = max(20.0, restaurants_actual - 8.0)

        _add_seed_transaction(
            month=month,
            day=2,
            tx_type="income",
            amount=salary_actual,
            category_key="salary",
            description_key="salary",
            tag_keys=("fixed",),
        )
        _add_seed_transaction(
            month=month,
            day=7,
            tx_type="income",
            amount=freelance_actual,
            category_key="freelance",
            description_key="freelance",
            tag_keys=("variable",),
        )
        if budget_plan["bonus"][month - 1] > 0:
            _add_seed_transaction(
                month=month,
                day=10,
                tx_type="income",
                amount=budget_plan["bonus"][month - 1] + 25.0,
                category_key="bonus",
                description_key="bonus",
                tag_keys=("variable", "discretionary"),
            )
        if budget_plan["item_sales"][month - 1] > 0:
            _add_seed_transaction(
                month=month,
                day=11,
                tx_type="income",
                amount=item_sales_actual,
                category_key="item_sales",
                description_key="item_sales",
                tag_keys=("variable", "discretionary"),
            )
        if rent_income_actual > 0:
            _add_seed_transaction(
                month=month,
                day=15,
                tx_type="income",
                amount=rent_income_actual,
                category_key="rent_income",
                description_key="rent_income",
                tag_keys=("fixed",),
            )
        _add_seed_transaction(
            month=month,
            day=16,
            tx_type="income",
            amount=interest_income_actual,
            category_key="interest_income",
            description_key="interest_income",
            tag_keys=("fixed",),
        )

        _add_seed_transaction(
            month=month,
            day=4,
            tx_type="expense",
            amount=housing_actual,
            category_key="housing",
            description_key="housing",
            tag_keys=("fixed", "essential"),
        )
        _add_seed_transaction(
            month=month,
            day=6,
            tx_type="expense",
            amount=utilities_actual,
            category_key="utilities",
            description_key="utilities",
            tag_keys=("fixed", "essential"),
        )
        if home_maintenance_actual > 0:
            _add_seed_transaction(
                month=month,
                day=5,
                tx_type="expense",
                amount=home_maintenance_actual,
                category_key="home_maintenance",
                description_key="home_maintenance",
                tag_keys=("variable", "essential"),
            )
        _add_seed_transaction(
            month=month,
            day=8,
            tx_type="expense",
            amount=telecom_actual,
            category_key="telecom",
            description_key="telecom",
            tag_keys=("fixed", "essential"),
        )
        _add_seed_transaction(
            month=month,
            day=12,
            tx_type="expense",
            amount=round(food_total * 0.62, 2),
            category_key="food",
            description_key="food_a",
            tag_keys=("variable", "essential"),
        )
        _add_seed_transaction(
            month=month,
            day=19,
            tx_type="expense",
            amount=cleaning_actual,
            category_key="cleaning",
            description_key="food_b",
            tag_keys=("variable", "essential"),
        )
        _add_seed_transaction(
            month=month,
            day=14,
            tx_type="expense",
            amount=transport_actual,
            category_key="transport",
            description_key="transport",
            tag_keys=("variable", "essential"),
        )
        _add_seed_transaction(
            month=month,
            day=21,
            tx_type="expense",
            amount=public_transport_actual,
            category_key="public_transport",
            description_key="public_transport",
            tag_keys=("variable", "essential"),
        )
        if health_actual > 0:
            _add_seed_transaction(
                month=month,
                day=22,
                tx_type="expense",
                amount=health_actual,
                category_key="health",
                description_key="health",
                tag_keys=("variable", "essential"),
            )
        _add_seed_transaction(
            month=month,
            day=23,
            tx_type="expense",
            amount=health_insurance_actual,
            category_key="health_insurance",
            description_key="health_insurance",
            tag_keys=("fixed", "essential"),
        )
        _add_seed_transaction(
            month=month,
            day=24,
            tx_type="expense",
            amount=tuition_actual,
            category_key="tuition",
            description_key="tuition",
            tag_keys=("fixed", "essential"),
        )
        if books_actual > 0:
            _add_seed_transaction(
                month=month,
                day=25,
                tx_type="expense",
                amount=books_actual,
                category_key="books",
                description_key="books",
                tag_keys=("variable", "essential"),
            )
        _add_seed_transaction(
            month=month,
            day=20,
            tx_type="expense",
            amount=life_insurance_actual,
            category_key="life_insurance",
            description_key="life_insurance",
            tag_keys=("fixed", "essential"),
        )
        if property_insurance_actual > 0:
            _add_seed_transaction(
                month=month,
                day=9,
                tx_type="expense",
                amount=property_insurance_actual,
                category_key="property_insurance",
                description_key="property_insurance",
                tag_keys=("fixed", "essential"),
            )
        _add_seed_transaction(
            month=month,
            day=26,
            tx_type="expense",
            amount=credit_cards_actual,
            category_key="credit_cards",
            description_key="credit_cards",
            tag_keys=("fixed",),
        )
        _add_seed_transaction(
            month=month,
            day=27,
            tx_type="expense",
            amount=personal_loans_actual,
            category_key="personal_loans",
            description_key="personal_loans",
            tag_keys=("fixed",),
        )
        _add_seed_transaction(
            month=month,
            day=28,
            tx_type="expense",
            amount=subscriptions_actual,
            category_key="subscriptions",
            description_key="subscriptions",
            tag_keys=("variable", "discretionary"),
        )
        _add_seed_transaction(
            month=month,
            day=13,
            tx_type="expense",
            amount=restaurants_actual,
            category_key="restaurants",
            description_key="restaurants",
            tag_keys=("variable", "discretionary"),
        )
        _add_seed_transaction(
            month=month,
            day=29,
            tx_type="expense",
            amount=savings_actual,
            category_key="savings",
            description_key="savings",
            tag_keys=("fixed", "essential"),
        )
        _add_seed_transaction(
            month=month,
            day=18,
            tx_type="expense",
            amount=emergency_actual,
            category_key="emergency_fund",
            description_key="emergency_fund",
            tag_keys=("fixed", "essential"),
        )
        _add_seed_transaction(
            month=month,
            day=17,
            tx_type="expense",
            amount=retirement_actual,
            category_key="retirement",
            description_key="retirement",
            tag_keys=("fixed", "essential"),
        )

        if month in {5, 8, 12}:
            _add_seed_transaction(
                month=month,
                day=7,
                tx_type="expense",
                amount=round(25.0 + month, 2),
                category_key="health",
                description_key="health",
                tag_keys=("variable", "essential"),
            )

        if month in deficit_months:
            _add_seed_transaction(
                month=month,
                day=3,
                tx_type="expense",
                amount=185.0,
                category_key="home_maintenance",
                description_key="home_maintenance",
                tag_keys=("variable", "essential"),
            )
            _add_seed_transaction(
                month=month,
                day=11,
                tx_type="expense",
                amount=95.0,
                category_key="health",
                description_key="health",
                tag_keys=("variable", "essential"),
            )

        if month in {3, 6, 9, 12}:
            db.transfer_between_accounts(
                from_account_id=runtime.default_account_id,
                to_account_id=runtime.reserve_account_id,
                amount=125.0,
                note=runtime.seed_note,
                tx_date=f"{runtime.year}-{month:02d}-30",
                description=str(runtime.descriptions["transfer"]),
            )
            tx_count += 2

    return tx_count, tag_links
