# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Peewee models for the MIRA SQLite database."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from peewee import (
    AutoField,
    BooleanField,
    CharField,
    CompositeKey,
    DateField,
    DateTimeField,
    FloatField,
    ForeignKeyField,
    IntegerField,
    Model,
    Proxy,
    SQL,
    SqliteDatabase,
    TextField,
)

DB_PROXY: Proxy = Proxy()
SCHEMA_VERSION = 4


@dataclass(frozen=True)
class SchemaInspection:
    """Represent the SchemaInspection class."""

    status: str

    user_version: int | None
    tables: frozenset[str]
    error: str | None = None


@dataclass(frozen=True)
class SchemaIndexSpec:
    """Represent the SchemaIndexSpec class."""

    name: str

    table: str
    columns: tuple[str, ...]
    unique: bool = False
    where: str | None = None


class BaseModel(Model):
    """Represent the BaseModel class."""

    class Meta:
        """Represent the Meta class."""

        database = DB_PROXY


class Account(BaseModel):
    """Represent the Account class."""

    id = AutoField()

    name = CharField(unique=True)
    # Monetary values are stored as exact integer cents in SQLite to avoid
    # floating-point drift in balances, reports, and budget aggregates.
    balance = IntegerField(column_name="balance_cents", default=0)
    account_type = CharField(default="bank")
    currency = CharField(default="USD")
    is_default = BooleanField(default=False)
    created_at = DateTimeField(default=datetime.now)

    class Meta:
        """Represent the Meta class."""

        table_name = "accounts"


class Transaction(BaseModel):
    """Represent the Transaction class."""

    id = AutoField()

    account = ForeignKeyField(
        Account, backref="transactions", null=True, column_name="account_id", on_delete="SET NULL"
    )
    type = CharField()
    amount = IntegerField(column_name="amount_cents")
    description = TextField(null=True)
    category = CharField(null=True)
    category_id = IntegerField(
        null=True,
        constraints=[SQL("REFERENCES categories(id) ON DELETE SET NULL")],
    )
    subcategory = CharField(null=True)
    note = TextField(null=True)
    payment_method = CharField(default="cash")
    receipt_path = TextField(null=True)
    to_account_id = IntegerField(
        null=True,
        constraints=[SQL("REFERENCES accounts(id) ON DELETE SET NULL")],
    )
    is_transfer = BooleanField(default=False)
    exchange_rate = FloatField(null=True)
    converted_amount = IntegerField(column_name="converted_amount_cents", null=True)
    is_reconciled = BooleanField(default=False)
    reconciled_at = DateTimeField(null=True)
    date = DateField(default=date.today)
    created_at = DateTimeField(default=datetime.now)

    class Meta:
        """Represent the Meta class."""

        table_name = "transactions"


class Bucket(BaseModel):
    """Represent the Bucket class."""

    id = AutoField()

    name = CharField(unique=True)
    budget_amount = IntegerField(column_name="budget_amount_cents")
    spent_amount = IntegerField(column_name="spent_amount_cents", default=0)
    period = CharField(default="monthly")
    start_day = IntegerField(default=1)
    end_day = IntegerField(default=31)
    alert_threshold = FloatField(default=0.75)

    class Meta:
        """Represent the Meta class."""

        table_name = "buckets"


class Setting(BaseModel):
    """Represent the Setting class."""

    key = CharField(primary_key=True)

    value = TextField(null=True)

    class Meta:
        """Represent the Meta class."""

        table_name = "settings"


class Currency(BaseModel):
    """Represent the Currency class."""

    code = CharField(primary_key=True)

    name = CharField()
    region = CharField(default="americas")

    class Meta:
        """Represent the Meta class."""

        table_name = "currencies"


class Category(BaseModel):
    """Represent the Category class."""

    id = AutoField()

    name = CharField(unique=True)
    type = CharField()
    color = CharField(default="#888888")
    icon = CharField(default="")
    is_savings = BooleanField(default=False)
    parent_id = IntegerField(null=True)

    class Meta:
        """Represent the Meta class."""

        table_name = "categories"


class Tag(BaseModel):
    """Represent the Tag class."""

    id = AutoField()

    name = CharField(unique=True)
    icon = CharField(default="")
    color = CharField(default="#888888")
    created_at = DateTimeField(default=datetime.now)

    class Meta:
        """Represent the Meta class."""

        table_name = "tags"


class TransactionTag(BaseModel):
    """Represent the TransactionTag class."""

    transaction_id = IntegerField(
        constraints=[SQL("REFERENCES transactions(id) ON DELETE CASCADE")],
    )
    tag = ForeignKeyField(Tag, backref="transaction_links", column_name="tag_id", on_delete="CASCADE")

    class Meta:
        """Represent the Meta class."""

        table_name = "transaction_tags"

        primary_key = CompositeKey("transaction_id", "tag")


class RecurringTransaction(BaseModel):
    """Represent the RecurringTransaction class."""

    id = AutoField()

    account = ForeignKeyField(
        Account,
        backref="recurring_transactions",
        null=True,
        column_name="account_id",
        on_delete="SET NULL",
    )
    type = CharField()
    amount = IntegerField(column_name="amount_cents")
    description = TextField(null=True)
    category = CharField(null=True)
    category_id = IntegerField(
        null=True,
        constraints=[SQL("REFERENCES categories(id) ON DELETE SET NULL")],
    )
    note = TextField(null=True)
    day_of_month = IntegerField(default=1)

    class Meta:
        """Represent the Meta class."""

        table_name = "recurring_transactions"


class RecurringTransactionTag(BaseModel):
    """Represent the RecurringTransactionTag class."""

    recurring_id = IntegerField(
        constraints=[SQL("REFERENCES recurring_transactions(id) ON DELETE CASCADE")],
    )
    tag = ForeignKeyField(Tag, backref="recurring_links", column_name="tag_id", on_delete="CASCADE")

    class Meta:
        """Represent the Meta class."""

        table_name = "recurring_transaction_tags"

        primary_key = CompositeKey("recurring_id", "tag")


class BudgetMaster(BaseModel):
    """Represent the BudgetMaster class."""

    id = AutoField()

    code = CharField(unique=True)
    year = IntegerField()
    is_default_year = BooleanField(default=False)
    currency = CharField(default="USD")
    created_at = DateTimeField(default=datetime.now)

    class Meta:
        """Represent the Meta class."""

        table_name = "budget_master"


class BudgetDetail(BaseModel):
    """Represent the BudgetDetail class."""

    id = AutoField()

    budget = ForeignKeyField(BudgetMaster, backref="details", column_name="budget_id", on_delete="CASCADE")
    category = ForeignKeyField(Category, backref="budget_details", column_name="category_id", on_delete="CASCADE")
    year = IntegerField()
    month = IntegerField()
    amount = IntegerField(column_name="amount_cents", default=0)

    class Meta:
        """Represent the Meta class."""

        table_name = "budget_detail"

        indexes = ((("budget", "category", "year", "month"), True),)


class SavingsGoal(BaseModel):
    """Represent the SavingsGoal class."""

    id = AutoField()

    name = CharField(unique=True)
    target_amount = IntegerField(column_name="target_amount_cents")
    current_amount = IntegerField(column_name="current_amount_cents", default=0)
    currency = CharField(default="NIO")
    category_id = IntegerField(
        null=True,
        constraints=[SQL("REFERENCES categories(id) ON DELETE SET NULL")],
    )
    target_date = CharField(null=True)
    created_at = DateTimeField(default=datetime.now)

    class Meta:
        """Represent the Meta class."""

        table_name = "savings_goals"


class InsightEvent(BaseModel):
    """Represent the InsightEvent class."""

    id = AutoField()

    user_id = IntegerField(default=1)
    transaction_id = IntegerField()
    insight_code = CharField()
    message = TextField()
    priority = IntegerField(default=0)
    created_at = DateTimeField(default=datetime.now)
    period_key = CharField()
    extra_context = TextField(null=True)

    class Meta:
        """Represent the Meta class."""

        table_name = "insight_events"


class AchievementEvent(BaseModel):
    """Represent the AchievementEvent class."""

    id = AutoField()

    user_id = IntegerField(default=1)
    transaction_id = IntegerField()
    achievement_code = CharField()
    message = TextField()
    priority = IntegerField(default=0)
    created_at = DateTimeField(default=datetime.now)
    period_key = CharField()
    extra_context = TextField(null=True)

    class Meta:
        """Represent the Meta class."""

        table_name = "achievement_events"


class AchievementCounter(BaseModel):
    """Represent the AchievementCounter class."""

    id = AutoField()

    user_id = IntegerField(default=1)
    counter_key = CharField()
    counter_value = IntegerField(default=0)
    updated_at = DateTimeField(default=datetime.now)

    class Meta:
        """Represent the Meta class."""

        table_name = "achievement_counters"

        indexes = ((("user_id", "counter_key"), True),)


class MessageEvent(BaseModel):
    """Represent the MessageEvent class."""

    id = AutoField()

    user_id = IntegerField(default=1)
    message_code = CharField()
    message_type = CharField()
    source_event_type = CharField()
    source_event_id = IntegerField(null=True)
    period_key = CharField(null=True)
    reference_date = DateField(null=True)
    context_category_id = IntegerField(null=True)
    context_amount = IntegerField(column_name="context_amount_cents", null=True)
    context_source = CharField(null=True)
    shown_at = DateTimeField(default=datetime.now)
    priority = IntegerField(default=0)
    message_text = TextField()

    class Meta:
        """Represent the Meta class."""

        table_name = "message_events"


class ReconciliationGroup(BaseModel):
    """Represent the ReconciliationGroup class."""

    id = CharField(primary_key=True)

    account = ForeignKeyField(
        Account,
        backref="reconciliation_groups",
        column_name="account_id",
        on_delete="CASCADE",
    )
    date_from = DateField()
    date_to = DateField()
    created_at = DateTimeField(default=datetime.now)

    class Meta:
        """Represent the Meta class."""

        table_name = "reconciliation_groups"


class ReconciliationMatch(BaseModel):
    """Represent the ReconciliationMatch class."""

    id = CharField(primary_key=True)

    reconciliation_group = ForeignKeyField(
        ReconciliationGroup,
        backref="matches",
        column_name="reconciliation_group_id",
        on_delete="CASCADE",
    )
    system_transaction = ForeignKeyField(
        Transaction,
        backref="reconciliation_matches",
        column_name="system_transaction_id",
        on_delete="CASCADE",
    )
    external_reference = CharField(null=True)
    external_date = DateField()
    external_description = TextField(null=True)
    external_amount = IntegerField(column_name="external_amount_cents")
    external_item_key = CharField()

    class Meta:
        """Represent the Meta class."""

        table_name = "reconciliation_matches"


class SchemaVersion(BaseModel):
    """Represent the SchemaVersion class."""

    version = IntegerField(primary_key=True)

    applied_at = DateTimeField(default=datetime.now)
    status = CharField(default="applied")

    class Meta:
        """Represent the Meta class."""

        table_name = "schema_version"


class IncomeExpenseRelation(BaseModel):
    """Represent the IncomeExpenseRelation class."""

    id = AutoField()

    income_category = ForeignKeyField(
        Category,
        backref="expense_relations",
        column_name="income_category_id",
        on_delete="CASCADE",
    )
    expense_category = ForeignKeyField(
        Category,
        backref="income_relation",
        column_name="expense_category_id",
        on_delete="CASCADE",
    )
    created_at = DateTimeField(default=datetime.now)

    class Meta:
        """Represent the Meta class."""

        table_name = "income_expense_relations"

        indexes = ((("expense_category",), True),)


ALL_MODELS = [
    Account,
    Transaction,
    Bucket,
    Setting,
    Currency,
    Category,
    Tag,
    TransactionTag,
    SavingsGoal,
    RecurringTransaction,
    RecurringTransactionTag,
    BudgetMaster,
    BudgetDetail,
    InsightEvent,
    AchievementEvent,
    AchievementCounter,
    MessageEvent,
    ReconciliationGroup,
    ReconciliationMatch,
    IncomeExpenseRelation,
    SchemaVersion,
]

EXPECTED_TABLES = frozenset(model._meta.table_name for model in ALL_MODELS)  # type: ignore[attr-defined]

# Keep index names explicit for backwards compatibility with existing checks.
# Peewee handles table creation, but these indexes require stable names and,
# for some cases, partial-index predicates.
SCHEMA_INDEX_SPECS: tuple[SchemaIndexSpec, ...] = (
    SchemaIndexSpec("idx_transactions_account_id", "transactions", ("account_id",)),
    SchemaIndexSpec("idx_transactions_date", "transactions", ("date",)),
    SchemaIndexSpec("idx_transactions_type", "transactions", ("type",)),
    SchemaIndexSpec("idx_transactions_category", "transactions", ("category",)),
    SchemaIndexSpec("idx_transactions_category_id", "transactions", ("category_id",)),
    SchemaIndexSpec("idx_transactions_date_type", "transactions", ("date", "type")),
    SchemaIndexSpec("idx_transactions_is_reconciled", "transactions", ("is_reconciled",)),
    SchemaIndexSpec("idx_transactions_reconciled_at", "transactions", ("reconciled_at",)),
    SchemaIndexSpec("idx_budget_detail_budget_id", "budget_detail", ("budget_id",)),
    SchemaIndexSpec("idx_budget_detail_category_id", "budget_detail", ("category_id",)),
    SchemaIndexSpec(
        "idx_budget_master_default_per_year",
        "budget_master",
        ("year",),
        unique=True,
        where="is_default_year = 1",
    ),
    SchemaIndexSpec(
        "uq_accounts_single_default",
        "accounts",
        ("is_default",),
        unique=True,
        where="is_default = 1",
    ),
    SchemaIndexSpec("idx_categories_type", "categories", ("type",)),
    SchemaIndexSpec("idx_categories_is_savings", "categories", ("is_savings",)),
    SchemaIndexSpec("idx_categories_parent_id", "categories", ("parent_id",)),
    SchemaIndexSpec("idx_transaction_tags_transaction_id", "transaction_tags", ("transaction_id",)),
    SchemaIndexSpec("idx_transaction_tags_tag_id", "transaction_tags", ("tag_id",)),
    SchemaIndexSpec("idx_recurring_transaction_tags_recurring_id", "recurring_transaction_tags", ("recurring_id",)),
    SchemaIndexSpec("idx_recurring_transaction_tags_tag_id", "recurring_transaction_tags", ("tag_id",)),
    SchemaIndexSpec("idx_insight_events_tx", "insight_events", ("transaction_id",)),
    SchemaIndexSpec("idx_insight_events_period", "insight_events", ("period_key", "insight_code")),
    SchemaIndexSpec("idx_insight_events_created_at", "insight_events", ("created_at",)),
    SchemaIndexSpec("idx_achievement_events_tx", "achievement_events", ("transaction_id",)),
    SchemaIndexSpec("idx_achievement_events_period", "achievement_events", ("period_key", "achievement_code")),
    SchemaIndexSpec("idx_message_events_code_type", "message_events", ("message_code", "message_type")),
    SchemaIndexSpec("idx_message_events_source", "message_events", ("source_event_type", "source_event_id")),
    SchemaIndexSpec("idx_message_events_reference_date", "message_events", ("reference_date",)),
    SchemaIndexSpec("idx_message_events_period_category", "message_events", ("period_key", "context_category_id")),
    SchemaIndexSpec("idx_message_events_shown_at", "message_events", ("shown_at",)),
    SchemaIndexSpec(
        "uq_message_events_tx_type",
        "message_events",
        ("source_event_type", "source_event_id", "message_type"),
        unique=True,
        where="source_event_type = 'transaction' AND source_event_id IS NOT NULL",
    ),
    SchemaIndexSpec(
        "uq_message_events_daily_reference",
        "message_events",
        ("source_event_type", "message_type", "reference_date"),
        unique=True,
        where=("source_event_type = 'app_start' AND message_type = 'daily_context' " "AND reference_date IS NOT NULL"),
    ),
    SchemaIndexSpec(
        "idx_income_expense_relations_income",
        "income_expense_relations",
        ("income_category_id",),
    ),
    SchemaIndexSpec(
        "uq_income_expense_relations_expense",
        "income_expense_relations",
        ("expense_category_id",),
        unique=True,
    ),
    SchemaIndexSpec(
        "idx_reconciliation_groups_account_range",
        "reconciliation_groups",
        ("account_id", "date_from", "date_to"),
    ),
    SchemaIndexSpec(
        "idx_reconciliation_matches_group",
        "reconciliation_matches",
        ("reconciliation_group_id",),
    ),
    SchemaIndexSpec(
        "idx_reconciliation_matches_transaction",
        "reconciliation_matches",
        ("system_transaction_id",),
    ),
    SchemaIndexSpec(
        "idx_reconciliation_matches_external_key",
        "reconciliation_matches",
        ("external_item_key",),
    ),
    SchemaIndexSpec(
        "uq_reconciliation_matches_group_tx_external",
        "reconciliation_matches",
        ("reconciliation_group_id", "system_transaction_id", "external_item_key"),
        unique=True,
    ),
)


def _build_create_index_sql(index_spec: SchemaIndexSpec) -> str:
    """Return build create index sql."""
    unique_sql = "UNIQUE " if index_spec.unique else ""
    columns_sql = ", ".join(index_spec.columns)
    where_sql = f" WHERE {index_spec.where}" if index_spec.where else ""
    return (
        f"CREATE {unique_sql}INDEX IF NOT EXISTS {index_spec.name} " f"ON {index_spec.table}({columns_sql}){where_sql}"
    )


def create_peewee_database(path: str) -> SqliteDatabase:
    """Return create peewee database."""
    return SqliteDatabase(
        path,
        pragmas={"journal_mode": "wal", "foreign_keys": 1},
        check_same_thread=False,
    )


def bind_database(database: SqliteDatabase) -> None:
    """Return bind database."""
    DB_PROXY.initialize(database)


_LEGACY_V1_REQUIRED_TABLES = frozenset(
    {
        "accounts",
        "transactions",
        "buckets",
        "settings",
        "currencies",
        "categories",
        "tags",
        "transaction_tags",
        "savings_goals",
        "recurring_transactions",
        "recurring_transaction_tags",
        "budget_master",
        "budget_detail",
        "insight_events",
        "achievement_events",
        "achievement_counters",
        "message_events",
    }
)


def _table_columns(conn: sqlite3.Connection, table: str) -> frozenset[str]:
    """Return table columns."""
    return frozenset(str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _is_legacy_v1_float_schema(conn: sqlite3.Connection, tables: frozenset[str]) -> bool:
    """Return whether legacy v1 float schema."""
    if not _LEGACY_V1_REQUIRED_TABLES.issubset(tables):
        return False
    accounts_columns = _table_columns(conn, "accounts")
    transaction_columns = _table_columns(conn, "transactions")
    bucket_columns = _table_columns(conn, "buckets")
    recurring_columns = _table_columns(conn, "recurring_transactions")
    goal_columns = _table_columns(conn, "savings_goals")
    budget_columns = _table_columns(conn, "budget_detail")
    message_columns = _table_columns(conn, "message_events")
    return (
        "balance" in accounts_columns
        and "balance_cents" not in accounts_columns
        and "amount" in transaction_columns
        and "amount_cents" not in transaction_columns
        and "budget_amount" in bucket_columns
        and "budget_amount_cents" not in bucket_columns
        and "amount" in recurring_columns
        and "amount_cents" not in recurring_columns
        and "target_amount" in goal_columns
        and "target_amount_cents" not in goal_columns
        and "amount" in budget_columns
        and "amount_cents" not in budget_columns
        and "context_amount" in message_columns
        and "context_amount_cents" not in message_columns
    )


def inspect_database_schema_details(
    path: str | Path,
    *,
    current_version: int = SCHEMA_VERSION,
    min_migratable_version: int | None = None,
) -> SchemaInspection:
    """Inspect a database file and classify its schema compatibility."""
    target = Path(path).expanduser()
    if not target.exists():
        return SchemaInspection(status="missing", user_version=None, tables=frozenset())

    minimum_version = current_version if min_migratable_version is None else min_migratable_version

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(target)
        tables = frozenset(
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        )
        if not tables:
            return SchemaInspection(status="empty", user_version=0, tables=tables)

        quick_check_row = conn.execute("PRAGMA quick_check").fetchone()
        quick_check = str(quick_check_row[0]).strip().lower() if quick_check_row else ""
        if quick_check != "ok":
            return SchemaInspection(
                status="invalid",
                user_version=None,
                tables=tables,
                error=f"PRAGMA quick_check returned {quick_check or 'no result'!r}.",
            )

        stored_user_version = int(conn.execute("PRAGMA user_version").fetchone()[0] or 0)
        if stored_user_version == 0 and _is_legacy_v1_float_schema(conn, tables):
            stored_user_version = 1
    except sqlite3.DatabaseError as exc:
        return SchemaInspection(status="invalid", user_version=None, tables=frozenset(), error=str(exc))
    finally:
        if conn is not None:
            conn.close()

    recognized_tables = tables & EXPECTED_TABLES
    if not recognized_tables:
        return SchemaInspection(
            status="invalid",
            user_version=stored_user_version,
            tables=tables,
            error="The file does not contain recognizable MIRA tables.",
        )

    missing_tables = EXPECTED_TABLES.difference(tables)
    if stored_user_version == current_version:
        if missing_tables:
            return SchemaInspection(
                status="invalid",
                user_version=stored_user_version,
                tables=tables,
                error=f"Missing required MIRA tables: {', '.join(sorted(missing_tables))}.",
            )
        return SchemaInspection(status="current", user_version=stored_user_version, tables=tables)

    if minimum_version <= stored_user_version < current_version:
        return SchemaInspection(status="migratable", user_version=stored_user_version, tables=tables)

    return SchemaInspection(status="legacy", user_version=stored_user_version, tables=tables)


def inspect_database_schema(
    path: str | Path,
    *,
    current_version: int = SCHEMA_VERSION,
    min_migratable_version: int | None = None,
) -> str:
    """Return a coarse-grained compatibility status for a database file."""
    return inspect_database_schema_details(
        path,
        current_version=current_version,
        min_migratable_version=min_migratable_version,
    ).status


def initialize_schema(database: SqliteDatabase) -> None:
    """Return initialize schema."""
    database.create_tables(ALL_MODELS, safe=True)
    # Schema v2 intentionally uses *_cents columns for all persisted money.
    # Keep explicit index names and partial predicates from one declarative source.
    for index_spec in SCHEMA_INDEX_SPECS:
        database.execute_sql(_build_create_index_sql(index_spec))
    database.execute_sql("DROP INDEX IF EXISTS uq_message_events_daily")
    SchemaVersion.insert(
        version=SCHEMA_VERSION, applied_at=datetime.now(), status="applied"
    ).on_conflict_ignore().execute()
    database.execute_sql(f"PRAGMA user_version = {SCHEMA_VERSION}")
