# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Database bootstrap helpers independent from Database class."""

from __future__ import annotations

import calendar
from datetime import date
from typing import Any, Protocol, cast

from mira.db.helpers import (
    _CURRENCY_SEED,
    canonical_account_type,
    localized_default_account_name,
    localized_default_savings_name,
    normalize_language,
)
from mira.db.model import Account, Currency, RecurringTransaction, SavingsGoal, Setting, Transaction
from mira.db.money import MoneyLike, money_to_cents

# ---------------------------------------------------------------------------
# Localized category and tag name catalogue.
# Add a new language code here to extend i18n support without touching code.
# ---------------------------------------------------------------------------
_CATEGORY_NAMES: dict[str, dict[str, str]] = {
    "es": {
        # income parent groups
        "salary_compensation": "Salario y Remuneración",
        "services_sales": "Servicios y Ventas",
        "rent_interest": "Rentas e Intereses",
        # income sub-categories
        "net_salary": "Sueldo Neto (Nómina)",
        "bonuses": "Bonos y Comisiones",
        "freelance": "Honorarios Freelance",
        "item_sales": "Venta de Artículos",
        "rent_collected": "Alquileres Cobrados",
        "investment_interest": "Intereses de Inversiones",
        # expense parent groups
        "housing": "Vivienda",
        "utilities": "Servicios Básicos",
        "food": "Alimentación",
        "transport": "Transporte",
        "health": "Salud",
        "education": "Estudio",
        "insurance": "Seguros",
        "debt_repayment": "Amortización de Deuda",
        "savings": "Ahorro",
        "entertainment": "Entretenimiento",
        # expense sub-categories
        "rent_mortgage": "Alquiler o Hipoteca",
        "home_maintenance": "Mantenimiento y Reparaciones",
        "electricity": "Electricidad, Gas y Agua",
        "internet_phone": "Internet y Telefonía",
        "groceries": "Supermercado y Despensa",
        "hygiene_cleaning": "Artículos de Higiene y Limpieza",
        "fuel_tolls": "Combustible y Peajes",
        "public_transport": "Bus, Metro o Taxi",
        "health_insurance": "Seguro Médico",
        "pharmacy": "Farmacia y Consultas",
        "tuition": "Matrículas y Mensualidades",
        "books_courses": "Libros y Cursos",
        "life_insurance": "Seguro de Vida",
        "vehicle_home_insurance": "Seguro de Vehículo/Hogar",
        "credit_cards": "Tarjetas de Crédito",
        "personal_loans": "Préstamos Personales",
        "emergency_fund": "Fondo de Emergencia",
        "retirement": "Plan de Retiro o Inversiones",
        "subscriptions": "Suscripciones y Ocio",
        "restaurants": "Restaurantes y Salidas",
        # tags
        "tag_fixed": "Fijo",
        "tag_variable": "Variable",
        "tag_essential": "Necesario",
        "tag_discretionary": "Discrecional",
    },
    "en": {
        # income parent groups
        "salary_compensation": "Salary and Compensation",
        "services_sales": "Services and Sales",
        "rent_interest": "Rent and Interest",
        # income sub-categories
        "net_salary": "Net Salary (Payroll)",
        "bonuses": "Bonuses and Commissions",
        "freelance": "Freelance Fees",
        "item_sales": "Item Sales",
        "rent_collected": "Rent Collected",
        "investment_interest": "Investment Interest",
        # expense parent groups
        "housing": "Housing",
        "utilities": "Utilities",
        "food": "Food",
        "transport": "Transport",
        "health": "Health",
        "education": "Education",
        "insurance": "Insurance",
        "debt_repayment": "Debt Repayment",
        "savings": "Savings",
        "entertainment": "Entertainment",
        # expense sub-categories
        "rent_mortgage": "Rent or Mortgage",
        "home_maintenance": "Maintenance and Repairs",
        "electricity": "Electricity, Gas and Water",
        "internet_phone": "Internet and Phone",
        "groceries": "Groceries and Pantry",
        "hygiene_cleaning": "Hygiene and Cleaning Supplies",
        "fuel_tolls": "Fuel and Tolls",
        "public_transport": "Bus, Metro or Taxi",
        "health_insurance": "Health Insurance",
        "pharmacy": "Pharmacy and Consultations",
        "tuition": "Tuition and Monthly Fees",
        "books_courses": "Books and Courses",
        "life_insurance": "Life Insurance",
        "vehicle_home_insurance": "Vehicle/Home Insurance",
        "credit_cards": "Credit Cards",
        "personal_loans": "Personal Loans",
        "emergency_fund": "Emergency Fund",
        "retirement": "Retirement or Investments Plan",
        "subscriptions": "Subscriptions and Leisure",
        "restaurants": "Restaurants and Outings",
        # tags
        "tag_fixed": "Fixed",
        "tag_variable": "Variable",
        "tag_essential": "Essential",
        "tag_discretionary": "Discretionary",
    },
}


def _cn(lang: str, key: str) -> str:
    """Return the localized category or tag name for *key* in *lang*.

    Falls back to the English name when the language is not supported.
    """
    names = _CATEGORY_NAMES.get(lang) or _CATEGORY_NAMES["en"]
    return names.get(key) or _CATEGORY_NAMES["en"].get(key) or key


# ---------------------------------------------------------------------------
# Demo data seeding catalogue (account names + transaction descriptions).
# Category and tag names are resolved via _cn() from _CATEGORY_NAMES above.
# ---------------------------------------------------------------------------
_DEMO_CATALOG_DATA: dict[str, dict[str, Any]] = {
    "es": {
        "main_account": "Cuenta principal",
        "reserve_account": "Cuenta reserva",
        "descriptions": {
            "salary": "Salario mensual",
            "freelance": "Proyecto freelance",
            "bonus": "Bonificación del periodo",
            "item_sales": "Venta puntual de artículos",
            "rent_income": "Cobro de alquiler",
            "interest_income": "Intereses abonados",
            "housing": "Pago de vivienda",
            "home_maintenance": "Mantenimiento del hogar",
            "utilities": "Servicios básicos del hogar",
            "telecom": "Internet y telefonía",
            "food_a": "Supermercado quincenal",
            "food_b": "Compra de higiene y limpieza",
            "transport": "Combustible y peajes",
            "public_transport": "Transporte público del mes",
            "health": "Farmacia y consultas",
            "health_insurance": "Seguro médico",
            "tuition": "Pago de estudios",
            "books": "Material educativo",
            "life_insurance": "Seguro de vida",
            "property_insurance": "Seguro del vehículo u hogar",
            "credit_cards": "Pago de tarjeta de crédito",
            "personal_loans": "Abono a préstamo personal",
            "savings": "Aporte a ahorro",
            "emergency_fund": "Aporte al fondo de emergencia",
            "retirement": "Aporte a retiro e inversiones",
            "subscriptions": "Suscripciones del mes",
            "restaurants": "Restaurantes y salidas",
            "transfer": "Transferencia a reserva",
        },
    },
    "en": {
        "main_account": "Main account",
        "reserve_account": "Reserve account",
        "descriptions": {
            "salary": "Monthly salary",
            "freelance": "Freelance project",
            "bonus": "Periodic bonus",
            "item_sales": "One-off item sale",
            "rent_income": "Rent collection",
            "interest_income": "Interest earned",
            "housing": "Housing payment",
            "home_maintenance": "Home maintenance",
            "utilities": "Home utilities",
            "telecom": "Internet and phone",
            "food_a": "Grocery run",
            "food_b": "Cleaning and hygiene supplies",
            "transport": "Fuel and tolls",
            "public_transport": "Public transport commute",
            "health": "Pharmacy and consultations",
            "health_insurance": "Health insurance",
            "tuition": "Education payment",
            "books": "Learning materials",
            "life_insurance": "Life insurance",
            "property_insurance": "Vehicle or home insurance",
            "credit_cards": "Credit card payment",
            "personal_loans": "Personal loan payment",
            "savings": "Savings contribution",
            "emergency_fund": "Emergency fund contribution",
            "retirement": "Retirement and investing contribution",
            "subscriptions": "Monthly subscriptions",
            "restaurants": "Restaurants and outings",
            "transfer": "Transfer to reserve",
        },
    },
}


class _BootstrapDatabaseProtocol(Protocol):
    def get_default_currency(self) -> str: ...

    def get_account_by_id(self, account_id: int) -> dict[str, Any] | None: ...

    def get_account_by_name(self, name: str) -> dict[str, Any] | None: ...

    def add_account(
        self,
        name: str,
        account_type: str = "bank",
        opening_balance: MoneyLike = 0,
        currency: str | None = None,
    ) -> dict[str, Any]: ...

    def get_default_account(self) -> dict[str, Any] | None: ...

    def get_or_create_account(self, name: str) -> dict[str, Any]: ...

    def set_default_account(self, account_id: int) -> None: ...

    def get_category_by_name(self, name: str, cat_type: str | None = None) -> dict[str, Any] | None: ...

    def add_category(
        self,
        name: str,
        cat_type: str,
        color: str = "#888888",
        parent_id: int | None = None,
        is_savings: bool = False,
        icon: str = "",
    ) -> dict[str, Any]: ...

    def update_category(
        self,
        cat_id: int,
        name: str,
        cat_type: str,
        color: str = "#888888",
        is_savings: bool = False,
        parent_id: int | None = None,
        icon: str = "",
    ) -> None: ...

    def _linked_savings_goal_for_category(self, category_id: int) -> dict[str, Any] | None: ...

    def _is_savings_goals_parent_category(self, category_id: int) -> bool: ...

    def set_setting(self, key: str, value: str) -> None: ...

    def get_setting(self, key: str) -> str | None: ...

    def get_tag_by_name(self, name: str) -> dict[str, Any] | None: ...

    def add_tag(self, name: str, color: str = "#888888", icon: str = "") -> dict[str, Any]: ...

    def get_savings_goal_by_name(self, name: str) -> dict[str, Any] | None: ...

    def add_savings_goal(
        self,
        name: str,
        target_amount: MoneyLike,
        target_date: str | None = None,
        *,
        currency: str | None = None,
        category_name: str | None = None,
    ) -> dict[str, Any]: ...

    def _ensure_goal_linked_savings_category(self, name: str) -> dict[str, Any]: ...

    def delete_transaction(self, tx_id: int) -> None: ...

    def get_budget_by_code(self, code: str) -> dict[str, Any] | None: ...

    def delete_budget(self, budget_id: int) -> None: ...

    def create_budget(self, code: str, year: int, currency: str | None = None) -> dict[str, Any]: ...

    def upsert_budget_amount(
        self, budget_id: int, category_id: int, year: int, month: int, amount: MoneyLike
    ) -> None: ...

    def add_transaction_tag(self, transaction_id: int, tag_id: int) -> None: ...

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
    ) -> dict[str, Any]: ...

    def transfer_between_accounts(
        self,
        from_account_id: int,
        to_account_id: int,
        amount: MoneyLike,
        *,
        note: str | None = None,
        tx_date: str | None = None,
        exchange_rate: float | None = None,
        converted_amount: MoneyLike | None = None,
        description: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]: ...


def seed_currencies() -> None:
    for code, name, region in _CURRENCY_SEED:
        Currency.insert(code=code, name=name, region=region).on_conflict_ignore().execute()


def seed_default_settings() -> None:
    defaults = {
        "username": "Usuario",
        "language": "en",
        "theme": "dark_teal.xml",
        "default_currency": "USD",
        "preferred_model": "",
        "model_download_offer_shown": "0",
        "llm_interaction_mode": "assistant",
        "number_thousands_separator": ",",
        "number_decimal_separator": ".",
        "max_tags_per_transaction": "10",
    }
    for key, value in defaults.items():
        Setting.insert(key=key, value=value).on_conflict_ignore().execute()


def seed_default_account() -> None:
    Account.insert(
        name="General",
        balance=0,
        currency="USD",
        is_default=True,
        account_type="bank",
    ).on_conflict_ignore().execute()


def _reuse_pristine_bootstrap_account(
    db: _BootstrapDatabaseProtocol,
    *,
    name: str,
    account_type: str,
    opening_balance: MoneyLike,
    currency: str,
) -> dict[str, Any] | None:
    """Reuse the initial bootstrap account during onboarding when it is still untouched."""

    if Account.select().count() != 1:
        return None

    bootstrap = Account.get_or_none(Account.name == "General")
    if bootstrap is None or not bool(bootstrap.is_default):
        return None

    if int(bootstrap.balance or 0) != 0:
        return None

    if Transaction.select().count() != 0 or RecurringTransaction.select().count() != 0:
        return None

    selected_currency = currency.strip().upper() or db.get_default_currency()
    (
        Account.update(
            name=name,
            account_type=canonical_account_type(account_type),
            balance=money_to_cents(opening_balance),
            currency=selected_currency,
        )
        .where(Account.id == bootstrap.id)
        .execute()
    )
    updated = db.get_account_by_id(int(bootstrap.id))
    if updated is None:
        raise RuntimeError("Failed to update bootstrap account")
    return updated


def default_category_seed_rows(lang: str) -> list[tuple[str, str, str, bool, str, str | None]]:
    return [
        (_cn(lang, "salary_compensation"), "income", "#4EC9B0", False, "💼", None),
        (_cn(lang, "net_salary"), "income", "#3FB950", False, "💰", _cn(lang, "salary_compensation")),
        (_cn(lang, "bonuses"), "income", "#D7BA7D", False, "🎁", _cn(lang, "salary_compensation")),
        (_cn(lang, "services_sales"), "income", "#6A9FB5", False, "🧾", None),
        (_cn(lang, "freelance"), "income", "#9CDCFE", False, "🧑‍💻", _cn(lang, "services_sales")),
        (_cn(lang, "item_sales"), "income", "#B5CEA8", False, "🛍️", _cn(lang, "services_sales")),
        (_cn(lang, "rent_interest"), "income", "#C586C0", False, "🏦", None),
        (_cn(lang, "rent_collected"), "income", "#CE9178", False, "🏠", _cn(lang, "rent_interest")),
        (_cn(lang, "investment_interest"), "income", "#D19A66", False, "📈", _cn(lang, "rent_interest")),
        (_cn(lang, "housing"), "expense", "#F48771", False, "🏠", None),
        (_cn(lang, "rent_mortgage"), "expense", "#E06C75", False, "🏘️", _cn(lang, "housing")),
        (_cn(lang, "home_maintenance"), "expense", "#D16969", False, "🧰", _cn(lang, "housing")),
        (_cn(lang, "utilities"), "expense", "#C586C0", False, "💡", None),
        (_cn(lang, "electricity"), "expense", "#4FC1FF", False, "💧", _cn(lang, "utilities")),
        (_cn(lang, "internet_phone"), "expense", "#569CD6", False, "📶", _cn(lang, "utilities")),
        (_cn(lang, "food"), "expense", "#F14C4C", False, "🍽️", None),
        (_cn(lang, "groceries"), "expense", "#DCDCAA", False, "🛒", _cn(lang, "food")),
        (_cn(lang, "hygiene_cleaning"), "expense", "#8B949E", False, "🧴", _cn(lang, "food")),
        (_cn(lang, "transport"), "expense", "#C74E39", False, "🚌", None),
        (_cn(lang, "fuel_tolls"), "expense", "#FF6B6B", False, "⛽", _cn(lang, "transport")),
        (_cn(lang, "public_transport"), "expense", "#9CDCFE", False, "🚕", _cn(lang, "transport")),
        (_cn(lang, "health"), "expense", "#CE9178", False, "🏥", None),
        (_cn(lang, "health_insurance"), "expense", "#D7BA7D", False, "🩺", _cn(lang, "health")),
        (_cn(lang, "pharmacy"), "expense", "#B5CEA8", False, "💊", _cn(lang, "health")),
        (_cn(lang, "education"), "expense", "#DCDCAA", False, "🎓", None),
        (_cn(lang, "tuition"), "expense", "#E5C07B", False, "🏫", _cn(lang, "education")),
        (_cn(lang, "books_courses"), "expense", "#86A9FF", False, "📚", _cn(lang, "education")),
        (_cn(lang, "insurance"), "expense", "#D19A66", False, "🛡️", None),
        (_cn(lang, "life_insurance"), "expense", "#F0A45D", False, "❤️", _cn(lang, "insurance")),
        (_cn(lang, "vehicle_home_insurance"), "expense", "#8EC07C", False, "🚗", _cn(lang, "insurance")),
        (_cn(lang, "debt_repayment"), "expense", "#FF6B6B", False, "💳", None),
        (_cn(lang, "credit_cards"), "expense", "#E06C75", False, "💳", _cn(lang, "debt_repayment")),
        (_cn(lang, "personal_loans"), "expense", "#C678DD", False, "🧾", _cn(lang, "debt_repayment")),
        (_cn(lang, "savings"), "expense", "#3FB950", True, "🐷", None),
        (_cn(lang, "emergency_fund"), "expense", "#2EA043", True, "🆘", _cn(lang, "savings")),
        (_cn(lang, "retirement"), "expense", "#1F8B4C", True, "📈", _cn(lang, "savings")),
        (_cn(lang, "entertainment"), "expense", "#569CD6", False, "🎉", None),
        (_cn(lang, "subscriptions"), "expense", "#4FA3D1", False, "🎮", _cn(lang, "entertainment")),
        (_cn(lang, "restaurants"), "expense", "#B146C2", False, "🍔", _cn(lang, "entertainment")),
    ]


def ensure_default_categories(db: _BootstrapDatabaseProtocol, lang: str, *, update_existing_metadata: bool) -> None:
    category_ids: dict[tuple[str, str], int] = {}
    for name, cat_type, color, is_savings, icon, parent_ref in default_category_seed_rows(lang):
        parent_id = None if parent_ref is None else category_ids[(parent_ref, cat_type)]
        existing = db.get_category_by_name(name, cat_type)
        if existing is None:
            created = db.add_category(
                name=name,
                cat_type=cat_type,
                color=color,
                parent_id=parent_id,
                is_savings=is_savings,
                icon=icon,
            )
            category_ids[(name, cat_type)] = int(created["id"])
            continue

        if update_existing_metadata:
            updates: dict[str, object] = {}
            is_linked_to_goal = db._linked_savings_goal_for_category(int(existing["id"])) is not None
            is_reserved_parent = db._is_savings_goals_parent_category(int(existing["id"]))
            if existing.get("parent_id") != parent_id and not is_linked_to_goal and not is_reserved_parent:
                updates["parent_id"] = parent_id
            if is_savings and int(existing.get("is_savings") or 0) == 0:
                updates["is_savings"] = True
            if str(existing.get("icon") or "") != icon:
                updates["icon"] = icon
            if str(existing.get("color") or "") != color:
                updates["color"] = color
            if updates:
                db.update_category(
                    int(existing["id"]),
                    str(existing["name"]),
                    str(existing["type"]),
                    str(updates.get("color", existing["color"])),
                    is_savings=bool(updates.get("is_savings", int(existing.get("is_savings") or 0) == 1)),
                    parent_id=cast(int | None, updates.get("parent_id", existing.get("parent_id"))),
                    icon=str(updates.get("icon", existing.get("icon") or "")),
                )
        category_ids[(name, cat_type)] = int(existing["id"])


def seed_initial_data(
    db: _BootstrapDatabaseProtocol,
    *,
    include_default_categories: bool = True,
    account_names: list[str] | None = None,
    account_specs: list[dict[str, Any]] | None = None,
    language: str = "en",
    update_existing_category_metadata: bool = True,
) -> None:
    """Populate the database with initial data after first-run setup.

    *account_specs* controls account creation during onboarding:
      - ``None``  → fall back to the legacy *account_names* behaviour.
      - ``[]``    → create a single localised default account automatically.
      - ``[...]`` → create each specified account; the first is marked default.
    """
    lang = normalize_language(language)
    db.set_setting("language", lang)
    default_account_name = localized_default_account_name(lang)
    default_savings_name = localized_default_savings_name(lang)

    if account_specs is not None:
        specs = list(account_specs)
        if not specs:
            specs = [
                {
                    "name": default_account_name,
                    "account_type": "bank",
                    "opening_balance": 0.0,
                    "currency": db.get_default_currency(),
                }
            ]
        first_id: int | None = None
        for spec in specs:
            name = str(spec.get("name") or "").strip()
            if not name:
                continue
            if db.get_account_by_name(name) is None:
                account_type = str(spec.get("account_type") or "bank")
                opening_balance = float(spec.get("opening_balance") or 0.0)
                currency = str(spec.get("currency") or db.get_default_currency())
                acc = None
                if first_id is None:
                    acc = _reuse_pristine_bootstrap_account(
                        db,
                        name=name,
                        account_type=account_type,
                        opening_balance=opening_balance,
                        currency=currency,
                    )
                if acc is None:
                    acc = db.add_account(
                        name=name,
                        account_type=account_type,
                        opening_balance=opening_balance,
                        currency=currency,
                    )
                if first_id is None:
                    first_id = acc["id"]
        if first_id is not None:
            db.set_default_account(first_id)
    elif account_names is not None:
        names = account_names if account_names else [default_account_name]
        legacy_first_id: int | None = None
        for name in names:
            if db.get_account_by_name(name) is None:
                acc = None
                if legacy_first_id is None:
                    acc = _reuse_pristine_bootstrap_account(
                        db,
                        name=name,
                        account_type="bank",
                        opening_balance=0.0,
                        currency=db.get_default_currency(),
                    )
                if acc is None:
                    acc = db.add_account(
                        name=name,
                        account_type="bank",
                        opening_balance=0.0,
                        currency=db.get_default_currency(),
                    )
                if legacy_first_id is None:
                    legacy_first_id = acc["id"]
        if legacy_first_id is not None:
            db.set_default_account(legacy_first_id)

    if include_default_categories:
        had_default_savings_category = db.get_category_by_name(default_savings_name, "expense") is not None
        ensure_default_categories(db, lang, update_existing_metadata=update_existing_category_metadata)
        default_tags = [
            (_cn(lang, "tag_fixed"), "#4EC9B0", "📌"),
            (_cn(lang, "tag_variable"), "#6A9FB5", "📊"),
            (_cn(lang, "tag_essential"), "#D7BA7D", "✅"),
            (_cn(lang, "tag_discretionary"), "#C586C0", "🎯"),
        ]
        for tag_name, tag_color, tag_icon in default_tags:
            if db.get_tag_by_name(tag_name) is None:
                db.add_tag(tag_name, color=tag_color, icon=tag_icon)

        default_savings_goal = db.get_savings_goal_by_name(default_savings_name)
        if default_savings_goal is None:
            if not had_default_savings_category:
                db.add_savings_goal(
                    name=default_savings_name,
                    target_amount=1000.0,
                    target_date=None,
                    currency=db.get_default_currency(),
                    category_name=default_savings_name,
                )
        else:
            savings_category = db._ensure_goal_linked_savings_category(default_savings_name)
            (
                SavingsGoal.update(
                    currency=db.get_default_currency(),
                    category_id=int(savings_category["id"]),
                )
                .where(SavingsGoal.id == int(default_savings_goal["id"]))
                .execute()
            )


def seed_demo_data(db: _BootstrapDatabaseProtocol, *, reference_date: date | None = None) -> dict[str, Any]:
    """Populate the current-year database with realistic demo budget and transactions."""
    current = reference_date or date.today()
    year = int(current.year)
    language = (db.get_setting("language") or "en").strip().lower()
    if language not in {"es", "en"}:
        language = "en"

    seed_initial_data(
        db,
        include_default_categories=True,
        language=language,
        update_existing_category_metadata=False,
    )

    _demo_data = _DEMO_CATALOG_DATA.get(language, _DEMO_CATALOG_DATA["en"])
    catalog: dict[str, Any] = {
        "main_account": _demo_data["main_account"],
        "reserve_account": _demo_data["reserve_account"],
        "categories": {
            "salary": (_cn(language, "net_salary"), "income"),
            "freelance": (_cn(language, "freelance"), "income"),
            "bonus": (_cn(language, "bonuses"), "income"),
            "item_sales": (_cn(language, "item_sales"), "income"),
            "rent_income": (_cn(language, "rent_collected"), "income"),
            "interest_income": (_cn(language, "investment_interest"), "income"),
            "housing": (_cn(language, "rent_mortgage"), "expense"),
            "home_maintenance": (_cn(language, "home_maintenance"), "expense"),
            "utilities": (_cn(language, "electricity"), "expense"),
            "telecom": (_cn(language, "internet_phone"), "expense"),
            "food": (_cn(language, "groceries"), "expense"),
            "cleaning": (_cn(language, "hygiene_cleaning"), "expense"),
            "transport": (_cn(language, "fuel_tolls"), "expense"),
            "public_transport": (_cn(language, "public_transport"), "expense"),
            "health": (_cn(language, "pharmacy"), "expense"),
            "health_insurance": (_cn(language, "health_insurance"), "expense"),
            "tuition": (_cn(language, "tuition"), "expense"),
            "books": (_cn(language, "books_courses"), "expense"),
            "life_insurance": (_cn(language, "life_insurance"), "expense"),
            "property_insurance": (_cn(language, "vehicle_home_insurance"), "expense"),
            "credit_cards": (_cn(language, "credit_cards"), "expense"),
            "personal_loans": (_cn(language, "personal_loans"), "expense"),
            "savings": (_cn(language, "savings"), "expense"),
            "emergency_fund": (_cn(language, "emergency_fund"), "expense"),
            "retirement": (_cn(language, "retirement"), "expense"),
            "subscriptions": (_cn(language, "subscriptions"), "expense"),
            "restaurants": (_cn(language, "restaurants"), "expense"),
        },
        "tags": {
            "fixed": _cn(language, "tag_fixed"),
            "variable": _cn(language, "tag_variable"),
            "essential": _cn(language, "tag_essential"),
            "discretionary": _cn(language, "tag_discretionary"),
        },
        "descriptions": _demo_data["descriptions"],
    }

    category_rows: dict[str, dict[str, Any]] = {}
    missing_categories: list[str] = []
    for key, (name, cat_type) in cast(dict[str, tuple[str, str]], catalog["categories"]).items():
        category = db.get_category_by_name(name, cat_type)
        if category is None:
            missing_categories.append(name)
            continue
        category_rows[key] = category
    if missing_categories:
        raise ValueError(
            "Seed requires the default category catalog for the database language. Missing: "
            + ", ".join(missing_categories)
        )

    tag_rows: dict[str, dict[str, Any]] = {}
    for key, name in cast(dict[str, str], catalog["tags"]).items():
        tag = db.get_tag_by_name(name)
        if tag is not None:
            tag_rows[key] = tag

    default_account = db.get_default_account()
    if default_account is None:
        main_name = str(catalog["main_account"])
        default_account = db.get_account_by_name(main_name) or db.get_or_create_account(main_name)
        db.set_default_account(int(default_account["id"]))

    reserve_name = str(catalog["reserve_account"])
    reserve_account = db.get_account_by_name(reserve_name)
    if reserve_account is None:
        reserve_account = db.add_account(
            name=reserve_name,
            account_type="bank",
            opening_balance=0.0,
            currency=db.get_default_currency(),
        )

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

    seed_note = f"mira_cli_seed:{year}"
    budget_code = f"mira_cli_seed_{year}"

    seeded_ids = [
        int(tx.id)
        for tx in Transaction.select(Transaction.id)
        .where(Transaction.note == seed_note)
        .order_by(Transaction.id.desc())
    ]
    for tx_id in seeded_ids:
        db.delete_transaction(tx_id)

    existing_budget = db.get_budget_by_code(budget_code)
    if existing_budget is not None:
        db.delete_budget(int(existing_budget["id"]))

    budget = db.create_budget(budget_code, year, db.get_default_currency())
    budget_id = int(budget["id"])

    budget_plan: dict[str, list[float]] = {
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

    for month in range(1, 13):
        for key, monthly_amounts in budget_plan.items():
            db.upsert_budget_amount(
                budget_id,
                int(category_rows[key]["id"]),
                year,
                month,
                float(monthly_amounts[month - 1]),
            )

    tx_count = 0
    tag_links = 0

    def _attach_tags(transaction_id: int, *tag_keys: str) -> None:
        nonlocal tag_links
        for tag_key in tag_keys:
            tag = tag_rows.get(tag_key)
            if tag is None:
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
        nonlocal tx_count
        valid_day = min(day, calendar.monthrange(year, month)[1])
        tx = db.add_transaction(
            account_id=int(default_account["id"]),
            tx_type=tx_type,
            amount=round(amount, 2),
            category=str(category_rows[category_key]["name"]),
            description=str(cast(dict[str, str], catalog["descriptions"])[description_key]),
            tx_date=f"{year}-{month:02d}-{valid_day:02d}",
            note=seed_note,
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
                from_account_id=int(default_account["id"]),
                to_account_id=int(reserve_account["id"]),
                amount=125.0,
                note=seed_note,
                tx_date=f"{year}-{month:02d}-30",
                description=str(cast(dict[str, str], catalog["descriptions"])["transfer"]),
            )
            tx_count += 2

    return {
        "year": year,
        "budget_code": budget_code,
        "budget_id": budget_id,
        "transactions_created": tx_count,
        "tag_links_created": tag_links,
        "language": language,
    }
