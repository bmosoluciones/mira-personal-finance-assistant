# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Database bootstrap helpers independent from Database class."""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol, cast

from mira.db.helpers import (
    CURRENCY_SEED,
    canonical_account_type,
    localized_default_account_name,
    localized_default_savings_name,
    normalize_language,
)
from mira.db.demo_seed import (
    build_demo_seed_catalog,
    build_budget_plan,
    build_demo_seed_result,
    build_demo_seed_runtime,
    ensure_seed_accounts,
    ensure_seed_goals,
    normalize_demo_seed_language,
    reset_seed_artifacts,
    resolve_seed_categories,
    resolve_seed_tags,
    seed_budget_plan,
    seed_monthly_transactions,
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
        "other_active_income": "Otros Ingresos Activos",
        "business_income": "Ingresos de Negocio",
        "passive_income": "Ingresos Pasivos",
        "transfers_received": "Transferencias y Regalos Recibidos",
        "other_income": "Otros Ingresos",
        # income sub-categories
        "net_salary": "Sueldo Neto (Nómina)",
        "bonuses": "Bonos y Comisiones",
        "freelance": "Honorarios Freelance",
        "item_sales": "Venta de Artículos",
        "rent_collected": "Alquileres Cobrados",
        "investment_interest": "Intereses de Inversiones",
        "overtime_tips": "Horas Extra y Propinas",
        "business_revenue": "Ventas del Negocio",
        "business_dividends": "Dividendos de Negocio",
        "royalties": "Regalías y Afiliados",
        "reimbursements": "Reembolsos",
        "gifts_received": "Regalos y Donaciones Recibidos",
        "asset_sales": "Venta de Activos y Bienes",
        "prizes_lottery": "Premios y Loterías",
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
        "personal_shopping": "Compras Personales",
        "family_social": "Familia y Social",
        "pets": "Mascotas",
        "business_expenses": "Gastos de Negocio",
        "donations": "Donaciones y Caridad",
        "miscellaneous": "Gastos Varios",
        # expense sub-categories
        "rent_mortgage": "Alquiler o Hipoteca",
        "home_maintenance": "Mantenimiento y Reparaciones",
        "electricity": "Electricidad, Gas y Agua",
        "internet_phone": "Internet y Telefonía",
        "groceries": "Supermercado y Despensa",
        "hygiene_cleaning": "Artículos de Higiene y Limpieza",
        "fuel_tolls": "Combustible y Peajes",
        "public_transport": "Bus, Metro o Taxi",
        "vehicle_maintenance": "Mantenimiento del Vehículo",
        "health_insurance": "Seguro Médico",
        "pharmacy": "Farmacia y Consultas",
        "medical_exams": "Exámenes y Laboratorio",
        "tuition": "Matrículas y Mensualidades",
        "books_courses": "Libros y Cursos",
        "life_insurance": "Seguro de Vida",
        "vehicle_home_insurance": "Seguro de Vehículo/Hogar",
        "credit_cards": "Tarjetas de Crédito",
        "personal_loans": "Préstamos Personales",
        "taxes_fees": "Impuestos y Honorarios Profesionales",
        "emergency_fund": "Fondo de Emergencia",
        "retirement": "Plan de Retiro o Inversiones",
        "investment_savings": "Ahorro para Inversión",
        "specific_goals": "Metas de Ahorro Específicas",
        "subscriptions": "Suscripciones y Ocio",
        "restaurants": "Restaurantes y Salidas",
        "travel_vacations": "Viajes y Vacaciones",
        "cinema_events": "Cine y Eventos",
        "hobbies_games": "Pasatiempos y Juegos",
        "clothing_footwear": "Ropa y Calzado",
        "electronics_accessories": "Electrónica y Accesorios",
        "furniture_home_goods": "Muebles y Artículos del Hogar",
        "childcare_family_support": "Apoyo Familiar y Cuidado de Hijos",
        "gifts_social_events": "Regalos y Eventos Sociales",
        "pet_care": "Comida y Accesorios para Mascotas",
        "veterinarian": "Veterinario",
        "business_operations": "Operaciones del Negocio",
        "charitable_giving": "Donativos y Diezmos",
        "fines_penalties": "Multas y Sanciones",
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
        "other_active_income": "Other Active Income",
        "business_income": "Business Income",
        "passive_income": "Passive Income",
        "transfers_received": "Transfers and Gifts Received",
        "other_income": "Other Income",
        # income sub-categories
        "net_salary": "Net Salary (Payroll)",
        "bonuses": "Bonuses and Commissions",
        "freelance": "Freelance Fees",
        "item_sales": "Item Sales",
        "rent_collected": "Rent Collected",
        "investment_interest": "Investment Interest",
        "overtime_tips": "Overtime and Tips",
        "business_revenue": "Business Revenue",
        "business_dividends": "Business Dividends",
        "royalties": "Royalties and Affiliates",
        "reimbursements": "Reimbursements",
        "gifts_received": "Gifts and Donations Received",
        "asset_sales": "Asset and Property Sales",
        "prizes_lottery": "Prizes and Lottery",
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
        "personal_shopping": "Personal Shopping",
        "family_social": "Family and Social",
        "pets": "Pets",
        "business_expenses": "Business Expenses",
        "donations": "Donations and Charity",
        "miscellaneous": "Miscellaneous",
        # expense sub-categories
        "rent_mortgage": "Rent or Mortgage",
        "home_maintenance": "Maintenance and Repairs",
        "electricity": "Electricity, Gas and Water",
        "internet_phone": "Internet and Phone",
        "groceries": "Groceries and Pantry",
        "hygiene_cleaning": "Hygiene and Cleaning Supplies",
        "fuel_tolls": "Fuel and Tolls",
        "public_transport": "Bus, Metro or Taxi",
        "vehicle_maintenance": "Vehicle Maintenance",
        "health_insurance": "Health Insurance",
        "pharmacy": "Pharmacy and Consultations",
        "medical_exams": "Medical Exams and Lab",
        "tuition": "Tuition and Monthly Fees",
        "books_courses": "Books and Courses",
        "life_insurance": "Life Insurance",
        "vehicle_home_insurance": "Vehicle/Home Insurance",
        "credit_cards": "Credit Cards",
        "personal_loans": "Personal Loans",
        "taxes_fees": "Taxes and Professional Fees",
        "emergency_fund": "Emergency Fund",
        "retirement": "Retirement or Investments Plan",
        "investment_savings": "Investment Savings",
        "specific_goals": "Specific Savings Goals",
        "subscriptions": "Subscriptions and Leisure",
        "restaurants": "Restaurants and Outings",
        "travel_vacations": "Travel and Vacations",
        "cinema_events": "Cinema and Events",
        "hobbies_games": "Hobbies and Games",
        "clothing_footwear": "Clothing and Footwear",
        "electronics_accessories": "Electronics and Accessories",
        "furniture_home_goods": "Furniture and Home Goods",
        "childcare_family_support": "Childcare and Family Support",
        "gifts_social_events": "Gifts and Social Events",
        "pet_care": "Pet Food and Supplies",
        "veterinarian": "Veterinarian",
        "business_operations": "Business Operations",
        "charitable_giving": "Charitable Giving",
        "fines_penalties": "Fines and Penalties",
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
    """Represent the _BootstrapDatabaseProtocol class."""

    def get_default_currency(self) -> str:
        """Return get default currency."""
        ...

    def get_account_by_id(self, account_id: int) -> dict[str, Any] | None:
        """Return get account by id."""
        ...

    def get_account_by_name(self, name: str) -> dict[str, Any] | None:
        """Return get account by name."""
        ...

    def add_account(
        self,
        name: str,
        account_type: str = "bank",
        opening_balance: MoneyLike = 0,
        currency: str | None = None,
    ) -> dict[str, Any]:
        """Return add account."""
        ...

    def get_default_account(self) -> dict[str, Any] | None:
        """Return get default account."""
        ...

    def get_or_create_account(self, name: str) -> dict[str, Any]:
        """Return get or create account."""
        ...

    def set_default_account(self, account_id: int) -> None:
        """Return set default account."""
        ...

    def get_category_by_name(self, name: str, cat_type: str | None = None) -> dict[str, Any] | None:
        """Return get category by name."""
        ...

    def add_category(
        self,
        name: str,
        cat_type: str,
        color: str = "#888888",
        parent_id: int | None = None,
        is_savings: bool = False,
        icon: str = "",
    ) -> dict[str, Any]:
        """Return add category."""
        ...

    def update_category(
        self,
        cat_id: int,
        name: str,
        cat_type: str,
        color: str = "#888888",
        is_savings: bool = False,
        parent_id: int | None = None,
        icon: str = "",
    ) -> None:
        """Return update category."""
        ...

    def _linked_savings_goal_for_category(self, category_id: int) -> dict[str, Any] | None:
        """Return linked savings goal for category."""
        ...

    def _is_savings_goals_parent_category(self, category_id: int) -> bool:
        """Return whether savings goals parent category."""
        ...

    def set_setting(self, key: str, value: str) -> None:
        """Return set setting."""
        ...

    def get_setting(self, key: str) -> str | None:
        """Return get setting."""
        ...

    def get_tag_by_name(self, name: str) -> dict[str, Any] | None:
        """Return get tag by name."""
        ...

    def add_tag(self, name: str, color: str = "#888888", icon: str = "") -> dict[str, Any]:
        """Return add tag."""
        ...

    def get_savings_goal_by_name(self, name: str) -> dict[str, Any] | None:
        """Return get savings goal by name."""
        ...

    def add_savings_goal(
        self,
        name: str,
        target_amount: MoneyLike,
        target_date: str | None = None,
        *,
        currency: str | None = None,
        category_name: str | None = None,
    ) -> dict[str, Any]:
        """Return add savings goal."""
        ...

    def _ensure_goal_linked_savings_category(self, name: str) -> dict[str, Any]:
        """Return ensure goal linked savings category."""
        ...

    def delete_transaction(self, tx_id: int) -> None:
        """Return delete transaction."""
        ...

    def get_budget_by_code(self, code: str) -> dict[str, Any] | None:
        """Return get budget by code."""
        ...

    def delete_budget(self, budget_id: int) -> None:
        """Return delete budget."""
        ...

    def create_budget(self, code: str, year: int, currency: str | None = None) -> dict[str, Any]:
        """Return create budget."""
        ...

    def upsert_budget_amount(self, budget_id: int, category_id: int, year: int, month: int, amount: MoneyLike) -> None:
        """Return upsert budget amount."""
        ...

    def add_transaction_tag(self, transaction_id: int, tag_id: int) -> None:
        """Return add transaction tag."""
        ...

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
    ) -> dict[str, Any]:
        """Return add transaction."""
        ...

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
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return transfer between accounts."""
        ...


def seed_currencies() -> None:
    """Return seed currencies."""
    for entry in CURRENCY_SEED:
        Currency.insert(code=entry.code, name=entry.name, region=entry.region.value).on_conflict_ignore().execute()


def seed_default_settings() -> None:
    """Return seed default settings."""
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
    """Return seed default account."""
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
    """Return default category seed rows."""
    return [
        # ── Income parent groups ──────────────────────────────────────────
        (_cn(lang, "salary_compensation"), "income", "#4EC9B0", False, "💼", None),
        (_cn(lang, "services_sales"), "income", "#6A9FB5", False, "🧾", None),
        (_cn(lang, "rent_interest"), "income", "#C586C0", False, "🏦", None),
        (_cn(lang, "other_active_income"), "income", "#9CDCFE", False, "⏱️", None),
        (_cn(lang, "business_income"), "income", "#DCDCAA", False, "🏢", None),
        (_cn(lang, "passive_income"), "income", "#B5CEA8", False, "📊", None),
        (_cn(lang, "transfers_received"), "income", "#D7BA7D", False, "📥", None),
        (_cn(lang, "other_income"), "income", "#8B949E", False, "💡", None),
        # ── Income sub-categories ─────────────────────────────────────────
        (_cn(lang, "net_salary"), "income", "#3FB950", False, "💰", _cn(lang, "salary_compensation")),
        (_cn(lang, "bonuses"), "income", "#D7BA7D", False, "🎁", _cn(lang, "salary_compensation")),
        (_cn(lang, "overtime_tips"), "income", "#4FC1FF", False, "⏰", _cn(lang, "other_active_income")),
        (_cn(lang, "freelance"), "income", "#9CDCFE", False, "🧑‍💻", _cn(lang, "services_sales")),
        (_cn(lang, "item_sales"), "income", "#B5CEA8", False, "🛍️", _cn(lang, "services_sales")),
        (_cn(lang, "rent_collected"), "income", "#CE9178", False, "🏠", _cn(lang, "rent_interest")),
        (_cn(lang, "investment_interest"), "income", "#D19A66", False, "📈", _cn(lang, "rent_interest")),
        (_cn(lang, "business_revenue"), "income", "#E5C07B", False, "🛒", _cn(lang, "business_income")),
        (_cn(lang, "business_dividends"), "income", "#C678DD", False, "💹", _cn(lang, "business_income")),
        (_cn(lang, "royalties"), "income", "#4FA3D1", False, "©️", _cn(lang, "passive_income")),
        (_cn(lang, "reimbursements"), "income", "#86A9FF", False, "↩️", _cn(lang, "transfers_received")),
        (_cn(lang, "gifts_received"), "income", "#F0A45D", False, "🎀", _cn(lang, "transfers_received")),
        (_cn(lang, "asset_sales"), "income", "#8EC07C", False, "🏷️", _cn(lang, "other_income")),
        (_cn(lang, "prizes_lottery"), "income", "#FF6B6B", False, "🏆", _cn(lang, "other_income")),
        # ── Expense parent groups ─────────────────────────────────────────
        (_cn(lang, "housing"), "expense", "#F48771", False, "🏠", None),
        (_cn(lang, "utilities"), "expense", "#C586C0", False, "💡", None),
        (_cn(lang, "food"), "expense", "#F14C4C", False, "🍽️", None),
        (_cn(lang, "transport"), "expense", "#C74E39", False, "🚌", None),
        (_cn(lang, "health"), "expense", "#CE9178", False, "🏥", None),
        (_cn(lang, "education"), "expense", "#DCDCAA", False, "🎓", None),
        (_cn(lang, "insurance"), "expense", "#D19A66", False, "🛡️", None),
        (_cn(lang, "debt_repayment"), "expense", "#FF6B6B", False, "💳", None),
        (_cn(lang, "savings"), "expense", "#3FB950", True, "🐷", None),
        (_cn(lang, "entertainment"), "expense", "#569CD6", False, "🎉", None),
        (_cn(lang, "personal_shopping"), "expense", "#F0A45D", False, "🛍️", None),
        (_cn(lang, "family_social"), "expense", "#D7BA7D", False, "👨‍👩‍👧", None),
        (_cn(lang, "pets"), "expense", "#8EC07C", False, "🐾", None),
        (_cn(lang, "business_expenses"), "expense", "#4EC9B0", False, "🏢", None),
        (_cn(lang, "donations"), "expense", "#C586C0", False, "❤️", None),
        (_cn(lang, "miscellaneous"), "expense", "#8B949E", False, "📦", None),
        # ── Expense sub-categories: Housing ───────────────────────────────
        (_cn(lang, "rent_mortgage"), "expense", "#E06C75", False, "🏘️", _cn(lang, "housing")),
        (_cn(lang, "home_maintenance"), "expense", "#D16969", False, "🧰", _cn(lang, "housing")),
        # ── Expense sub-categories: Utilities ─────────────────────────────
        (_cn(lang, "electricity"), "expense", "#4FC1FF", False, "💧", _cn(lang, "utilities")),
        (_cn(lang, "internet_phone"), "expense", "#569CD6", False, "📶", _cn(lang, "utilities")),
        # ── Expense sub-categories: Food ──────────────────────────────────
        (_cn(lang, "groceries"), "expense", "#DCDCAA", False, "🛒", _cn(lang, "food")),
        (_cn(lang, "hygiene_cleaning"), "expense", "#8B949E", False, "🧴", _cn(lang, "food")),
        (_cn(lang, "restaurants"), "expense", "#B146C2", False, "🍔", _cn(lang, "food")),
        # ── Expense sub-categories: Transport ─────────────────────────────
        (_cn(lang, "fuel_tolls"), "expense", "#FF6B6B", False, "⛽", _cn(lang, "transport")),
        (_cn(lang, "public_transport"), "expense", "#9CDCFE", False, "🚕", _cn(lang, "transport")),
        (_cn(lang, "vehicle_maintenance"), "expense", "#C74E39", False, "🔧", _cn(lang, "transport")),
        # ── Expense sub-categories: Health ────────────────────────────────
        (_cn(lang, "health_insurance"), "expense", "#D7BA7D", False, "🩺", _cn(lang, "health")),
        (_cn(lang, "pharmacy"), "expense", "#B5CEA8", False, "💊", _cn(lang, "health")),
        (_cn(lang, "medical_exams"), "expense", "#CE9178", False, "🔬", _cn(lang, "health")),
        # ── Expense sub-categories: Education ─────────────────────────────
        (_cn(lang, "tuition"), "expense", "#E5C07B", False, "🏫", _cn(lang, "education")),
        (_cn(lang, "books_courses"), "expense", "#86A9FF", False, "📚", _cn(lang, "education")),
        # ── Expense sub-categories: Insurance ─────────────────────────────
        (_cn(lang, "life_insurance"), "expense", "#F0A45D", False, "❤️", _cn(lang, "insurance")),
        (_cn(lang, "vehicle_home_insurance"), "expense", "#8EC07C", False, "🚗", _cn(lang, "insurance")),
        # ── Expense sub-categories: Debt Repayment ────────────────────────
        (_cn(lang, "credit_cards"), "expense", "#E06C75", False, "💳", _cn(lang, "debt_repayment")),
        (_cn(lang, "personal_loans"), "expense", "#C678DD", False, "🧾", _cn(lang, "debt_repayment")),
        (_cn(lang, "taxes_fees"), "expense", "#D16969", False, "📋", _cn(lang, "debt_repayment")),
        # ── Expense sub-categories: Savings (is_savings=True) ─────────────
        (_cn(lang, "emergency_fund"), "expense", "#2EA043", True, "🆘", _cn(lang, "savings")),
        (_cn(lang, "retirement"), "expense", "#1F8B4C", True, "📈", _cn(lang, "savings")),
        (_cn(lang, "investment_savings"), "expense", "#3FB950", True, "💹", _cn(lang, "savings")),
        (_cn(lang, "specific_goals"), "expense", "#2EA043", True, "🎯", _cn(lang, "savings")),
        # ── Expense sub-categories: Entertainment ─────────────────────────
        (_cn(lang, "subscriptions"), "expense", "#4FA3D1", False, "🎮", _cn(lang, "entertainment")),
        (_cn(lang, "travel_vacations"), "expense", "#569CD6", False, "✈️", _cn(lang, "entertainment")),
        (_cn(lang, "cinema_events"), "expense", "#C678DD", False, "🎬", _cn(lang, "entertainment")),
        (_cn(lang, "hobbies_games"), "expense", "#9CDCFE", False, "🎲", _cn(lang, "entertainment")),
        # ── Expense sub-categories: Personal Shopping ─────────────────────
        (_cn(lang, "clothing_footwear"), "expense", "#F0A45D", False, "👗", _cn(lang, "personal_shopping")),
        (_cn(lang, "electronics_accessories"), "expense", "#4EC9B0", False, "📱", _cn(lang, "personal_shopping")),
        (_cn(lang, "furniture_home_goods"), "expense", "#D19A66", False, "🛋️", _cn(lang, "personal_shopping")),
        # ── Expense sub-categories: Family and Social ─────────────────────
        (_cn(lang, "childcare_family_support"), "expense", "#D7BA7D", False, "👶", _cn(lang, "family_social")),
        (_cn(lang, "gifts_social_events"), "expense", "#F48771", False, "🎁", _cn(lang, "family_social")),
        # ── Expense sub-categories: Pets ──────────────────────────────────
        (_cn(lang, "pet_care"), "expense", "#8EC07C", False, "🐶", _cn(lang, "pets")),
        (_cn(lang, "veterinarian"), "expense", "#B5CEA8", False, "🏥", _cn(lang, "pets")),
        # ── Expense sub-categories: Business Expenses ─────────────────────
        (_cn(lang, "business_operations"), "expense", "#4EC9B0", False, "⚙️", _cn(lang, "business_expenses")),
        # ── Expense sub-categories: Donations ─────────────────────────────
        (_cn(lang, "charitable_giving"), "expense", "#C586C0", False, "🙏", _cn(lang, "donations")),
        # ── Expense sub-categories: Miscellaneous ─────────────────────────
        (_cn(lang, "fines_penalties"), "expense", "#FF6B6B", False, "⚠️", _cn(lang, "miscellaneous")),
    ]


def ensure_default_categories(db: _BootstrapDatabaseProtocol, lang: str, *, update_existing_metadata: bool) -> None:
    """Return ensure default categories."""
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
    language = normalize_demo_seed_language(db.get_setting("language"))

    seed_initial_data(
        db,
        include_default_categories=True,
        language=language,
        update_existing_category_metadata=False,
    )

    catalog = build_demo_seed_catalog(
        language=language,
        catalog_data=_DEMO_CATALOG_DATA,
        translate=_cn,
    )
    category_rows = resolve_seed_categories(db, catalog)  # type: ignore[arg-type]
    tag_rows = resolve_seed_tags(db, catalog)  # type: ignore[arg-type]
    default_account, reserve_account = ensure_seed_accounts(db, catalog)  # type: ignore[arg-type]
    ensure_seed_goals(db, year=year, category_rows=category_rows)  # type: ignore[arg-type]
    seed_note, budget_code = reset_seed_artifacts(db, year=year, transaction_model=Transaction)  # type: ignore[arg-type]

    budget = db.create_budget(budget_code, year, db.get_default_currency())
    budget_id = int(budget["id"])
    budget_plan = build_budget_plan()
    seed_budget_plan(
        db,  # type: ignore[arg-type]
        budget_id=budget_id,
        year=year,
        category_rows=category_rows,
        budget_plan=budget_plan,
    )
    tx_count, tag_links = seed_monthly_transactions(
        db,  # type: ignore[arg-type]
        build_demo_seed_runtime(
            year=year,
            budget_id=budget_id,
            default_account=default_account,
            reserve_account=reserve_account,
            seed_note=seed_note,
            category_rows=category_rows,
            tag_rows=tag_rows,
            descriptions=catalog.descriptions,
        ),
        budget_plan,
    )

    return build_demo_seed_result(
        year=year,
        budget_code=budget_code,
        budget_id=budget_id,
        transactions_created=tx_count,
        tag_links_created=tag_links,
        language=language,
    )
