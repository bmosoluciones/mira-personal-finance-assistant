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
        (
            "Salario y Remuneración" if lang == "es" else "Salary and Compensation",
            "income",
            "#4EC9B0",
            False,
            "💼",
            None,
        ),
        (
            "Sueldo Neto (Nómina)" if lang == "es" else "Net Salary (Payroll)",
            "income",
            "#3FB950",
            False,
            "💰",
            "Salario y Remuneración" if lang == "es" else "Salary and Compensation",
        ),
        (
            "Bonos y Comisiones" if lang == "es" else "Bonuses and Commissions",
            "income",
            "#D7BA7D",
            False,
            "🎁",
            "Salario y Remuneración" if lang == "es" else "Salary and Compensation",
        ),
        (
            "Servicios y Ventas" if lang == "es" else "Services and Sales",
            "income",
            "#6A9FB5",
            False,
            "🧾",
            None,
        ),
        (
            "Honorarios Freelance" if lang == "es" else "Freelance Fees",
            "income",
            "#9CDCFE",
            False,
            "🧑‍💻",
            "Servicios y Ventas" if lang == "es" else "Services and Sales",
        ),
        (
            "Venta de Artículos" if lang == "es" else "Item Sales",
            "income",
            "#B5CEA8",
            False,
            "🛍️",
            "Servicios y Ventas" if lang == "es" else "Services and Sales",
        ),
        (
            "Rentas e Intereses" if lang == "es" else "Rent and Interest",
            "income",
            "#C586C0",
            False,
            "🏦",
            None,
        ),
        (
            "Alquileres Cobrados" if lang == "es" else "Rent Collected",
            "income",
            "#CE9178",
            False,
            "🏠",
            "Rentas e Intereses" if lang == "es" else "Rent and Interest",
        ),
        (
            "Intereses de Inversiones" if lang == "es" else "Investment Interest",
            "income",
            "#D19A66",
            False,
            "📈",
            "Rentas e Intereses" if lang == "es" else "Rent and Interest",
        ),
        ("Vivienda" if lang == "es" else "Housing", "expense", "#F48771", False, "🏠", None),
        (
            "Alquiler o Hipoteca" if lang == "es" else "Rent or Mortgage",
            "expense",
            "#E06C75",
            False,
            "🏘️",
            "Vivienda" if lang == "es" else "Housing",
        ),
        (
            "Mantenimiento y Reparaciones" if lang == "es" else "Maintenance and Repairs",
            "expense",
            "#D16969",
            False,
            "🧰",
            "Vivienda" if lang == "es" else "Housing",
        ),
        (
            "Servicios Básicos" if lang == "es" else "Utilities",
            "expense",
            "#C586C0",
            False,
            "💡",
            None,
        ),
        (
            "Electricidad, Gas y Agua" if lang == "es" else "Electricity, Gas and Water",
            "expense",
            "#4FC1FF",
            False,
            "💧",
            "Servicios Básicos" if lang == "es" else "Utilities",
        ),
        (
            "Internet y Telefonía" if lang == "es" else "Internet and Phone",
            "expense",
            "#569CD6",
            False,
            "📶",
            "Servicios Básicos" if lang == "es" else "Utilities",
        ),
        (
            "Alimentación" if lang == "es" else "Food",
            "expense",
            "#F14C4C",
            False,
            "🍽️",
            None,
        ),
        (
            "Supermercado y Despensa" if lang == "es" else "Groceries and Pantry",
            "expense",
            "#DCDCAA",
            False,
            "🛒",
            "Alimentación" if lang == "es" else "Food",
        ),
        (
            "Artículos de Higiene y Limpieza" if lang == "es" else "Hygiene and Cleaning Supplies",
            "expense",
            "#8B949E",
            False,
            "🧴",
            "Alimentación" if lang == "es" else "Food",
        ),
        (
            "Transporte" if lang == "es" else "Transport",
            "expense",
            "#C74E39",
            False,
            "🚌",
            None,
        ),
        (
            "Combustible y Peajes" if lang == "es" else "Fuel and Tolls",
            "expense",
            "#FF6B6B",
            False,
            "⛽",
            "Transporte" if lang == "es" else "Transport",
        ),
        (
            "Bus, Metro o Taxi" if lang == "es" else "Bus, Metro or Taxi",
            "expense",
            "#9CDCFE",
            False,
            "🚕",
            "Transporte" if lang == "es" else "Transport",
        ),
        ("Salud" if lang == "es" else "Health", "expense", "#CE9178", False, "🏥", None),
        (
            "Seguro Médico" if lang == "es" else "Health Insurance",
            "expense",
            "#D7BA7D",
            False,
            "🩺",
            "Salud" if lang == "es" else "Health",
        ),
        (
            "Farmacia y Consultas" if lang == "es" else "Pharmacy and Consultations",
            "expense",
            "#B5CEA8",
            False,
            "💊",
            "Salud" if lang == "es" else "Health",
        ),
        (
            "Estudio" if lang == "es" else "Education",
            "expense",
            "#DCDCAA",
            False,
            "🎓",
            None,
        ),
        (
            "Matrículas y Mensualidades" if lang == "es" else "Tuition and Monthly Fees",
            "expense",
            "#E5C07B",
            False,
            "🏫",
            "Estudio" if lang == "es" else "Education",
        ),
        (
            "Libros y Cursos" if lang == "es" else "Books and Courses",
            "expense",
            "#86A9FF",
            False,
            "📚",
            "Estudio" if lang == "es" else "Education",
        ),
        ("Seguros" if lang == "es" else "Insurance", "expense", "#D19A66", False, "🛡️", None),
        (
            "Seguro de Vida" if lang == "es" else "Life Insurance",
            "expense",
            "#F0A45D",
            False,
            "❤️",
            "Seguros" if lang == "es" else "Insurance",
        ),
        (
            "Seguro de Vehículo/Hogar" if lang == "es" else "Vehicle/Home Insurance",
            "expense",
            "#8EC07C",
            False,
            "🚗",
            "Seguros" if lang == "es" else "Insurance",
        ),
        (
            "Amortización de Deuda" if lang == "es" else "Debt Repayment",
            "expense",
            "#FF6B6B",
            False,
            "💳",
            None,
        ),
        (
            "Tarjetas de Crédito" if lang == "es" else "Credit Cards",
            "expense",
            "#E06C75",
            False,
            "💳",
            "Amortización de Deuda" if lang == "es" else "Debt Repayment",
        ),
        (
            "Préstamos Personales" if lang == "es" else "Personal Loans",
            "expense",
            "#C678DD",
            False,
            "🧾",
            "Amortización de Deuda" if lang == "es" else "Debt Repayment",
        ),
        ("Ahorro" if lang == "es" else "Savings", "expense", "#3FB950", True, "🐷", None),
        (
            "Fondo de Emergencia" if lang == "es" else "Emergency Fund",
            "expense",
            "#2EA043",
            True,
            "🆘",
            "Ahorro" if lang == "es" else "Savings",
        ),
        (
            "Plan de Retiro o Inversiones" if lang == "es" else "Retirement or Investments Plan",
            "expense",
            "#1F8B4C",
            True,
            "📈",
            "Ahorro" if lang == "es" else "Savings",
        ),
        (
            "Entretenimiento" if lang == "es" else "Entertainment",
            "expense",
            "#569CD6",
            False,
            "🎉",
            None,
        ),
        (
            "Suscripciones y Ocio" if lang == "es" else "Subscriptions and Leisure",
            "expense",
            "#4FA3D1",
            False,
            "🎮",
            "Entretenimiento" if lang == "es" else "Entertainment",
        ),
        (
            "Restaurantes y Salidas" if lang == "es" else "Restaurants and Outings",
            "expense",
            "#B146C2",
            False,
            "🍔",
            "Entretenimiento" if lang == "es" else "Entertainment",
        ),
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
            ("Fijo" if lang == "es" else "Fixed", "#4EC9B0", "📌"),
            ("Variable" if lang == "es" else "Variable", "#6A9FB5", "📊"),
            ("Necesario" if lang == "es" else "Essential", "#D7BA7D", "✅"),
            ("Discrecional" if lang == "es" else "Discretionary", "#C586C0", "🎯"),
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

    if language == "es":
        catalog = {
            "main_account": "Cuenta principal",
            "reserve_account": "Cuenta reserva",
            "categories": {
                "salary": ("Sueldo Neto (Nómina)", "income"),
                "freelance": ("Honorarios Freelance", "income"),
                "bonus": ("Bonos y Comisiones", "income"),
                "item_sales": ("Venta de Artículos", "income"),
                "rent_income": ("Alquileres Cobrados", "income"),
                "interest_income": ("Intereses de Inversiones", "income"),
                "housing": ("Alquiler o Hipoteca", "expense"),
                "home_maintenance": ("Mantenimiento y Reparaciones", "expense"),
                "utilities": ("Electricidad, Gas y Agua", "expense"),
                "telecom": ("Internet y Telefonía", "expense"),
                "food": ("Supermercado y Despensa", "expense"),
                "cleaning": ("Artículos de Higiene y Limpieza", "expense"),
                "transport": ("Combustible y Peajes", "expense"),
                "public_transport": ("Bus, Metro o Taxi", "expense"),
                "health": ("Farmacia y Consultas", "expense"),
                "health_insurance": ("Seguro Médico", "expense"),
                "tuition": ("Matrículas y Mensualidades", "expense"),
                "books": ("Libros y Cursos", "expense"),
                "life_insurance": ("Seguro de Vida", "expense"),
                "property_insurance": ("Seguro de Vehículo/Hogar", "expense"),
                "credit_cards": ("Tarjetas de Crédito", "expense"),
                "personal_loans": ("Préstamos Personales", "expense"),
                "savings": ("Ahorro", "expense"),
                "emergency_fund": ("Fondo de Emergencia", "expense"),
                "retirement": ("Plan de Retiro o Inversiones", "expense"),
                "subscriptions": ("Suscripciones y Ocio", "expense"),
                "restaurants": ("Restaurantes y Salidas", "expense"),
            },
            "tags": {
                "fixed": "Fijo",
                "variable": "Variable",
                "essential": "Necesario",
                "discretionary": "Discrecional",
            },
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
        }
    else:
        catalog = {
            "main_account": "Main account",
            "reserve_account": "Reserve account",
            "categories": {
                "salary": ("Net Salary (Payroll)", "income"),
                "freelance": ("Freelance Fees", "income"),
                "bonus": ("Bonuses and Commissions", "income"),
                "item_sales": ("Item Sales", "income"),
                "rent_income": ("Rent Collected", "income"),
                "interest_income": ("Investment Interest", "income"),
                "housing": ("Rent or Mortgage", "expense"),
                "home_maintenance": ("Maintenance and Repairs", "expense"),
                "utilities": ("Electricity, Gas and Water", "expense"),
                "telecom": ("Internet and Phone", "expense"),
                "food": ("Groceries and Pantry", "expense"),
                "cleaning": ("Hygiene and Cleaning Supplies", "expense"),
                "transport": ("Fuel and Tolls", "expense"),
                "public_transport": ("Bus, Metro or Taxi", "expense"),
                "health": ("Pharmacy and Consultations", "expense"),
                "health_insurance": ("Health Insurance", "expense"),
                "tuition": ("Tuition and Monthly Fees", "expense"),
                "books": ("Books and Courses", "expense"),
                "life_insurance": ("Life Insurance", "expense"),
                "property_insurance": ("Vehicle/Home Insurance", "expense"),
                "credit_cards": ("Credit Cards", "expense"),
                "personal_loans": ("Personal Loans", "expense"),
                "savings": ("Savings", "expense"),
                "emergency_fund": ("Emergency Fund", "expense"),
                "retirement": ("Retirement or Investments Plan", "expense"),
                "subscriptions": ("Subscriptions and Leisure", "expense"),
                "restaurants": ("Restaurants and Outings", "expense"),
            },
            "tags": {
                "fixed": "Fixed",
                "variable": "Variable",
                "essential": "Essential",
                "discretionary": "Discretionary",
            },
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
