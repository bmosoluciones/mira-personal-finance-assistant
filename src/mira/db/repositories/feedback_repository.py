# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Module documentation."""

from __future__ import annotations


import json
import logging
from dataclasses import dataclass, asdict
from datetime import date
from typing import TYPE_CHECKING, Any, cast

from peewee import JOIN, SQL, fn

from mira.finance_summary import build_savings_lookup, is_savings_transaction
from mira.db.helpers import (
    FEEDBACK_MILESTONES,
    MessagePriority,
)
from mira.db.model import (
    AchievementCounter,
    AchievementEvent,
    Category,
    InsightEvent,
    MessageEvent,
    Transaction,
)
from mira.reports.mira_master import shift_month
from mira.transaction_kinds import TransactionType, analytics_included_expr, is_analytics_excluded_transaction
from mira.ui.i18n import tr


@dataclass(frozen=True, slots=True)
class MessageCandidate:
    """A candidate message to be shown to the user.

    Encapsulates the data needed to evaluate, prioritize, and display
    insights and achievements.
    """

    code: str  # Unique message identifier (e.g., 'income_goal_80')
    message_type: str  # 'realtime_insight' or 'achievement'
    message: str  # The localized text to display
    priority: int = 0  # Higher values are selected first
    specificity: int = 0  # Tie-breaker for same-priority messages
    cooldown_scope: str | None = None  # 'day', 'period', or 'period_category'
    category_id: int | None = None  # Optional context for category-specific messages
    amount: float | None = None  # Optional numeric amount for the event
    counter_updates: list[tuple[str, int]] | None = None  # Achievement counters to increment

    def to_dict(self) -> dict[str, Any]:
        """Return to dict."""
        return asdict(self)


logger = logging.getLogger(__name__)


class FeedbackRepository:
    """Represent the FeedbackRepository class."""

    if TYPE_CHECKING:

        def get_setting(self, key: str) -> str | None:
            """Return get setting."""

        def set_setting(self, key: str, value: str) -> None:
            """Return set setting."""

        def _database_language(self) -> str:
            """Return database language."""

        def get_default_budget_for_year(self, year: int) -> dict[str, Any] | None:
            """Return get default budget for year."""

        def get_savings_goals(self) -> list[dict[str, Any]]:
            """Return get savings goals."""

        def _money_to_cents(self, value: object, *, allow_none: bool = False) -> int | None:
            """Return money to cents."""

        def _month_window(self, year: int, month: int) -> tuple[str, str]:
            """Return month window."""

        def _cents_to_money(self, value: object, *, allow_none: bool = False) -> Any:
            """Return cents to money."""

        def get_categories(
            self,
            cat_type: str | None = None,
            *,
            include_savings: bool = True,
        ) -> list[dict[str, Any]]:
            """Return get categories."""

        def build_monthly_context(self, tx: dict[str, Any]) -> dict[str, Any]:
            """Return build monthly context."""

    _MAX_COUNTER_STEP = 1_000_000

    def pop_daily_contextual_message(self, *, on_date: date | None = None) -> dict[str, Any] | None:
        """Return pop daily contextual message."""
        today = on_date or date.today()
        today_key = today.isoformat()
        if (self.get_setting("_last_daily_message") or "").strip() == today_key:
            return None

        language = self._database_language()
        candidates: list[MessageCandidate] = []
        current_year = int(today.year)

        if self.get_default_budget_for_year(current_year) is None:
            candidates.append(
                MessageCandidate(
                    code="daily_budget_missing",
                    message_type="daily_context",
                    priority=90,
                    message=tr("feedback.daily_budget_missing", language),
                )
            )

        if today.day > 10 and not self.get_savings_goals():
            candidates.append(
                MessageCandidate(
                    code="daily_no_savings_goal",
                    message_type="daily_context",
                    priority=70,
                    message=tr("feedback.daily_no_savings_goal", language),
                )
            )

        month_start = today.replace(day=1)
        month_tx_total = int(
            Transaction.select(fn.COUNT(Transaction.id))
            .where(
                analytics_included_expr(Transaction) & (Transaction.date >= month_start) & (Transaction.date <= today)
            )
            .scalar()
            or 0
        )
        if today.day > 20 and month_tx_total == 0:
            candidates.append(
                MessageCandidate(
                    code="daily_no_transactions",
                    message_type="daily_context",
                    priority=80,
                    message=tr("feedback.daily_no_transactions", language),
                )
            )

        if not candidates:
            return None
        selected = self.resolve_single_message(
            candidates,
            source_event_type="app_start",
            source_event_id=None,
            period_key=f"{today.year:04d}-{today.month:02d}",
            reference_date=today_key,
            source="app_start",
        )
        if selected is None:
            return None
        self.set_setting("_last_daily_message", today_key)
        return {**selected, "date": today_key}

    def _crossed_up(self, prev_value: float, new_value: float, threshold: float) -> bool:
        """Return crossed up."""
        return prev_value < threshold <= new_value

    def _get_setting_int(self, key: str, default: int = 0) -> int:
        """Return get setting int."""
        raw_value = self.get_setting(key)
        try:
            return int(str(raw_value).strip()) if raw_value is not None else default
        except (TypeError, ValueError):
            return default

    def get_achievement_counter(self, counter_key: str) -> int:
        """Return get achievement counter."""
        row = AchievementCounter.get_or_none(
            (AchievementCounter.user_id == 1) & (AchievementCounter.counter_key == counter_key)
        )
        if row is None:
            return 0
        return int(row.counter_value or 0)

    def increment_achievement_counter(self, counter_key: str, *, step: int = 1) -> tuple[int, int]:
        """Return increment achievement counter."""
        delta = int(step)
        if delta <= 0:
            raise ValueError("step must be a positive integer")
        if delta > self._MAX_COUNTER_STEP:
            raise ValueError(f"step must be <= {self._MAX_COUNTER_STEP}")
        AchievementCounter.insert(
            user_id=1,
            counter_key=counter_key,
            counter_value=delta,
        ).on_conflict(
            conflict_target=[AchievementCounter.user_id, AchievementCounter.counter_key],
            update={
                AchievementCounter.counter_value: AchievementCounter.counter_value + delta,
                AchievementCounter.updated_at: SQL("CURRENT_TIMESTAMP"),
            },
        ).execute()
        current_row = AchievementCounter.get_or_none(
            (AchievementCounter.user_id == 1) & (AchievementCounter.counter_key == counter_key)
        )
        current_value = int(current_row.counter_value or 0) if current_row is not None else 0
        previous_value = current_value - delta
        return previous_value, current_value

    def _message_in_cooldown(
        self,
        candidate: MessageCandidate,
        *,
        period_key: str | None = None,
        reference_date: str | None = None,
    ) -> bool:
        """Return message in cooldown."""
        if not (cooldown_scope := str(candidate.cooldown_scope or "").strip().lower()):
            return False

        query = MessageEvent.select(MessageEvent.id).where(
            (MessageEvent.message_code == candidate.code) & (MessageEvent.message_type == candidate.message_type)
        )

        match cooldown_scope:
            case "day" if reference_date:
                query = query.where(MessageEvent.reference_date == reference_date)
            case "period" if period_key:
                query = query.where(MessageEvent.period_key == period_key)
            case "period_category" if period_key:
                query = query.where(MessageEvent.period_key == period_key)
                if (category_id := candidate.category_id) is not None:
                    query = query.where(MessageEvent.context_category_id == int(category_id))
            case _:
                return False

        return query.limit(1).exists()

    def _build_message_context_fields(
        self,
        candidate: MessageCandidate,
        *,
        source: str | None = None,
        reference_date: str | None = None,
    ) -> dict[str, Any]:
        """Return build message context fields."""
        raw_source = str(source).strip() if source is not None else ""
        raw_reference_date = str(reference_date).strip() if reference_date is not None else ""
        return {
            "context_category_id": candidate.category_id,
            "context_amount": self._money_to_cents(candidate.amount, allow_none=True),
            "context_source": raw_source or None,
            "reference_date": raw_reference_date or None,
        }

    def resolve_candidate(
        self,
        candidates: list[MessageCandidate],
        *,
        period_key: str | None = None,
        reference_date: str | None = None,
    ) -> MessageCandidate | None:
        """Return resolve candidate."""
        if len(candidates) > 20:
            logger.warning("message resolver received %s candidates; expected a smaller set", len(candidates))
        valid_candidates: list[MessageCandidate] = []
        for candidate in candidates:
            if not (candidate.code.strip() and candidate.message_type.strip() and candidate.message.strip()):
                continue
            if self._message_in_cooldown(candidate, period_key=period_key, reference_date=reference_date):
                continue
            valid_candidates.append(candidate)
        if not valid_candidates:
            return None
        valid_candidates.sort(
            key=lambda item: (
                item.priority,
                item.specificity,
            ),
            reverse=True,
        )
        return valid_candidates[0]

    def persist_message_event(
        self,
        selected: MessageCandidate,
        *,
        source_event_type: str,
        source_event_id: int | None,
        period_key: str | None = None,
        reference_date: str | None = None,
        source: str | None = None,
    ) -> bool:
        """Return persist message event."""
        inserted = (
            MessageEvent.insert(
                user_id=1,
                message_code=selected.code,
                message_type=selected.message_type,
                source_event_type=source_event_type,
                source_event_id=source_event_id,
                period_key=period_key,
                priority=selected.priority,
                message_text=selected.message,
                **self._build_message_context_fields(
                    selected,
                    source=source,
                    reference_date=reference_date,
                ),
            )
            .on_conflict_ignore()
            .execute()
        )
        if not inserted:
            logger.info(
                "message event ignored by deduplication: code=%s type=%s source_event_type=%s source_event_id=%s",
                selected.code,
                selected.message_type,
                source_event_type,
                source_event_id,
            )
            return False
        return True

    def resolve_single_message(
        self,
        candidates: list[MessageCandidate],
        *,
        source_event_type: str,
        source_event_id: int | None,
        period_key: str | None = None,
        reference_date: str | None = None,
        source: str | None = None,
        persist: bool = True,
    ) -> dict[str, Any] | None:
        """Return resolve single message."""
        selected = self.resolve_candidate(
            candidates,
            period_key=period_key,
            reference_date=reference_date,
        )
        if selected is None:
            return None
        if persist and not self.persist_message_event(
            selected,
            source_event_type=source_event_type,
            source_event_id=source_event_id,
            period_key=period_key,
            reference_date=reference_date,
            source=source,
        ):
            return None
        return selected.to_dict()

    def evaluate_income_kpis(self, tx: dict[str, Any], context: dict[str, Any]) -> list[MessageCandidate]:
        """Return evaluate income kpis."""
        amount = float(tx.get("amount") or 0.0)
        goal = float(context["income_goal"])
        prev_income = float(context["income_actual_prev"])
        current_income = float(context["income_actual"])
        language = self._database_language()
        candidates: list[MessageCandidate] = []

        if goal > 0 and self._crossed_up(prev_income, current_income, goal):
            candidates.append(
                MessageCandidate(
                    code="income_goal_100",
                    message_type="realtime_insight",
                    message=tr("feedback.income_goal_100", language),
                    priority=int(MessagePriority.INSIGHT_CRITICAL) - 5,
                    specificity=50,
                )
            )
        if goal > 0 and self._crossed_up((prev_income / goal) * 100.0, (current_income / goal) * 100.0, 80.0):
            candidates.append(
                MessageCandidate(
                    code="income_goal_80",
                    message_type="realtime_insight",
                    message=tr("feedback.income_goal_80", language),
                    priority=int(MessagePriority.INSIGHT_WARNING) - 10,
                    specificity=40,
                )
            )
        if goal > 0 and self._crossed_up((prev_income / goal) * 100.0, (current_income / goal) * 100.0, 110.0):
            candidates.append(
                MessageCandidate(
                    code="income_goal_110",
                    message_type="realtime_insight",
                    message=tr("feedback.income_goal_110", language),
                    priority=int(MessagePriority.INSIGHT_WARNING) + 5,
                    specificity=45,
                )
            )
        if goal > 0 and ((prev_income / goal) * 100.0) < 50.0 and ((current_income / goal) * 100.0) >= 60.0:
            candidates.append(
                MessageCandidate(
                    code="income_recovery",
                    message_type="realtime_insight",
                    message=tr("feedback.income_recovery", language),
                    priority=int(MessagePriority.INSIGHT_INFO),
                    specificity=35,
                )
            )
        income_avg_prev = context.get("income_avg_prev")
        if income_avg_prev is not None and float(income_avg_prev) > 0 and amount > (float(income_avg_prev) * 2.0):
            candidates.append(
                MessageCandidate(
                    code="income_unusual_high",
                    message_type="realtime_insight",
                    message=tr("feedback.income_unusual_high", language),
                    priority=int(MessagePriority.INSIGHT_INFO) - 5,
                    specificity=20,
                    cooldown_scope="day",
                )
            )
        return candidates

    def evaluate_expense_kpis(self, tx: dict[str, Any], context: dict[str, Any]) -> list[MessageCandidate]:
        """Return evaluate expense kpis."""
        amount = float(tx.get("amount") or 0.0)
        language = self._database_language()
        category_name = context.get("category_name") or (tx.get("category") or "esta categoría")
        category_budget = float(context["category_budget"])
        category_prev = float(context["category_spent_prev"])
        category_current = float(context["category_spent"])
        expense_budget = float(context["expense_budget"])
        expense_prev = float(context["expense_actual_prev"])
        expense_current = float(context["expense_actual"])
        candidates: list[MessageCandidate] = []

        if category_budget > 0 and self._crossed_up(category_prev, category_current, category_budget):
            candidates.append(
                MessageCandidate(
                    code="expense_category_100",
                    message_type="realtime_insight",
                    message=tr("feedback.expense_category_100", language, params={"category_name": category_name}),
                    priority=int(MessagePriority.INSIGHT_CRITICAL),
                    specificity=50,
                )
            )
        if category_budget > 0 and self._crossed_up(
            (category_prev / category_budget) * 100.0, (category_current / category_budget) * 100.0, 90.0
        ):
            candidates.append(
                MessageCandidate(
                    code="expense_category_90",
                    message_type="realtime_insight",
                    message=tr("feedback.expense_category_90", language, params={"category_name": category_name}),
                    priority=int(MessagePriority.INSIGHT_WARNING),
                    specificity=40,
                    cooldown_scope="period_category",
                    category_id=context.get("category_id"),
                )
            )
        if expense_budget > 0 and self._crossed_up(expense_prev, expense_current, expense_budget):
            candidates.append(
                MessageCandidate(
                    code="expense_total_100",
                    message_type="realtime_insight",
                    message=tr("feedback.expense_total_100", language),
                    priority=int(MessagePriority.INSIGHT_CRITICAL) - 2,
                    specificity=45,
                )
            )
        month_progress = float(context["day_of_month"]) / float(context["month_days"])
        if (
            expense_budget > 0
            and month_progress < 0.5
            and ((expense_prev / expense_budget) * 100.0) < 70.0
            and ((expense_current / expense_budget) * 100.0) >= 70.0
        ):
            candidates.append(
                MessageCandidate(
                    code="expense_high_pace",
                    message_type="realtime_insight",
                    message=tr("feedback.expense_high_pace", language),
                    priority=int(MessagePriority.INSIGHT_WARNING) - 5,
                    specificity=30,
                )
            )
        expense_avg_prev = context.get("expense_category_avg_prev")
        if expense_avg_prev is not None and float(expense_avg_prev) > 0 and amount > (float(expense_avg_prev) * 2.0):
            candidates.append(
                MessageCandidate(
                    code="expense_unusual_high",
                    message_type="realtime_insight",
                    message=tr("feedback.expense_unusual_high", language, params={"category_name": category_name}),
                    priority=int(MessagePriority.INSIGHT_INFO),
                    specificity=20,
                    cooldown_scope="day",
                )
            )
        return candidates

    def _achievement_already_emitted(self, achievement_code: str, *, period_key: str | None = None) -> bool:
        """Return achievement already emitted."""
        query = AchievementEvent.select(AchievementEvent.id).where(
            AchievementEvent.achievement_code == achievement_code
        )
        if period_key is not None:
            query = query.where(AchievementEvent.period_key == period_key)
        return query.exists()

    def get_month_savings_amount(self, year: int, month: int) -> float:
        """Return get month savings amount."""
        month_start, month_end = self._month_window(year, month)
        query = (
            Transaction.select(fn.COALESCE(fn.SUM(Transaction.amount), 0.0).alias("savings_total"))
            .join(Category, JOIN.LEFT_OUTER, on=(Transaction.category_id == Category.id))
            .where(
                analytics_included_expr(Transaction)
                & (Transaction.type == "expense")
                & (fn.COALESCE(Category.is_savings, 0) == 1)
                & (Transaction.date >= month_start)
                & (Transaction.date <= month_end)
            )
        )
        return float(self._cents_to_money(query.scalar()) or 0.0)

    def evaluate_operation_achievements(
        self,
        tx: dict[str, Any],
        context: dict[str, Any],
        *,
        source: str | None = None,
    ) -> list[MessageCandidate]:
        """Return evaluate operation achievements."""
        if is_analytics_excluded_transaction(tx):
            return []
        language = self._database_language()
        tx_type = str(tx.get("type") or "")
        amount = float(tx.get("amount") or 0.0)
        period_key = str(context["period_key"])
        candidates: list[MessageCandidate] = []

        # --- Usage and learning achievements ---
        if source == "nl_assistant":
            nl_prev = self.get_achievement_counter("nl_transactions")
            nl_current = nl_prev + 1
            for milestone in FEEDBACK_MILESTONES.nl_transactions:
                if nl_prev < milestone <= nl_current:
                    candidates.append(
                        MessageCandidate(
                            code=f"achievement_nl_transactions_{milestone}",
                            message_type="achievement",
                            message=tr(
                                "feedback.achievement_nl_transactions",
                                language,
                                params={"milestone": milestone},
                            ),
                            priority=int(MessagePriority.ACHIEVEMENT_LOW) + 10,
                            cooldown_scope="period",
                        )
                    )

        report_views = self.get_achievement_counter("mira_report_views")
        for milestone in FEEDBACK_MILESTONES.mira_report_views:
            if report_views >= milestone and not self._achievement_already_emitted(
                f"achievement_mira_report_views_{milestone}"
            ):
                candidates.append(
                    MessageCandidate(
                        code=f"achievement_mira_report_views_{milestone}",
                        message_type="achievement",
                        message=tr(
                            "feedback.achievement_mira_report_views",
                            language,
                            params={"milestone": milestone},
                        ),
                        priority=int(MessagePriority.ACHIEVEMENT_LOW),
                        cooldown_scope="period",
                    )
                )

        savings_lookup = build_savings_lookup(self.get_categories(TransactionType.EXPENSE))
        if tx_type == TransactionType.EXPENSE and is_savings_transaction(tx, savings_lookup):
            savings_prev = self.get_achievement_counter("savings_contributions")
            savings_current = savings_prev + 1
            for milestone in FEEDBACK_MILESTONES.savings_contributions:
                if savings_prev < milestone <= savings_current:
                    candidates.append(
                        MessageCandidate(
                            code=f"achievement_savings_contributions_{milestone}",
                            message_type="achievement",
                            message=tr(
                                "feedback.achievement_savings_contributions",
                                language,
                                params={"milestone": milestone},
                            ),
                            priority=int(MessagePriority.ACHIEVEMENT_MEDIUM),
                            cooldown_scope="period",
                            counter_updates=[("savings_contributions", 1)],
                        )
                    )

        # --- Financial improvement achievements (conservative) ---
        goal = float(context["income_goal"])
        prev_income = float(context["income_actual_prev"])
        current_income = float(context["income_actual"])
        if tx_type == TransactionType.INCOME and goal > 0 and self._crossed_up(prev_income, current_income, goal):
            candidates.append(
                MessageCandidate(
                    code="achievement_income_goal_met",
                    message_type="achievement",
                    message=tr("feedback.achievement_income_goal_met", language),
                    priority=int(MessagePriority.ACHIEVEMENT_CRITICAL),
                    cooldown_scope="period",
                )
            )

        if tx_type == TransactionType.INCOME:
            historical_avg = float(
                self._cents_to_money(
                    Transaction.select(fn.COALESCE(fn.AVG(Transaction.amount), 0.0))
                    .where(
                        analytics_included_expr(Transaction)
                        & (Transaction.type == TransactionType.INCOME)
                        & (Transaction.id != int(tx["id"]))
                    )
                    .scalar()
                )
                or 0.0
            )
            if historical_avg > 0 and amount > historical_avg * 1.3:
                candidates.append(
                    MessageCandidate(
                        code="achievement_income_above_historical_avg",
                        message_type="achievement",
                        message=tr("feedback.achievement_income_above_historical_avg", language),
                        priority=int(MessagePriority.ACHIEVEMENT_HIGH) + 5,
                        cooldown_scope="day",
                    )
                )

        current_savings = float(context["savings_actual"])
        previous_savings = max(0.0, current_savings - amount) if tx_type == TransactionType.EXPENSE else current_savings
        if tx_type == TransactionType.EXPENSE and self._crossed_up(previous_savings, current_savings, 0.01):
            candidates.append(
                MessageCandidate(
                    code="achievement_saved_this_month",
                    message_type="achievement",
                    message=tr("feedback.achievement_saved_this_month", language),
                    priority=int(MessagePriority.ACHIEVEMENT_HIGH),
                    cooldown_scope="period",
                )
            )

        year = int(context["year"])
        month = int(context["month"])
        prev_year, prev_month = shift_month(year, month, -1)
        prev_prev_year, prev_prev_month = shift_month(year, month, -2)
        prev_month_savings = self.get_month_savings_amount(prev_year, prev_month)
        prev_prev_month_savings = self.get_month_savings_amount(prev_prev_year, prev_prev_month)
        if current_savings > prev_month_savings and not self._achievement_already_emitted(
            "achievement_savings_vs_previous_month", period_key=period_key
        ):
            candidates.append(
                MessageCandidate(
                    code="achievement_savings_vs_previous_month",
                    message_type="achievement",
                    message=tr("feedback.achievement_savings_vs_previous_month", language),
                    priority=int(MessagePriority.ACHIEVEMENT_HIGH) + 15,
                    cooldown_scope="period",
                )
            )
        if (
            current_savings > 0
            and prev_month_savings > 0
            and prev_prev_month_savings > 0
            and not self._achievement_already_emitted("achievement_savings_three_month_streak", period_key=period_key)
        ):
            candidates.append(
                MessageCandidate(
                    code="achievement_savings_three_month_streak",
                    message_type="achievement",
                    message=tr("feedback.achievement_savings_three_month_streak", language),
                    priority=int(MessagePriority.ACHIEVEMENT_CRITICAL) + 5,
                    cooldown_scope="period",
                )
            )

        return candidates

    def select_best_operation_message(
        self,
        tx: dict[str, Any],
        *,
        source: str | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """Return select best operation message."""
        if is_analytics_excluded_transaction(tx):
            return None, None
        is_nl_transaction = source == "nl_assistant"
        context = self.build_monthly_context(tx)
        achievement_candidates = self.evaluate_operation_achievements(tx, context, source=source)
        tx_type = str(tx.get("type") or "")
        insight_candidates = (
            self.evaluate_income_kpis(tx, context)
            if tx_type == TransactionType.INCOME
            else self.evaluate_expense_kpis(tx, context)
        )
        all_candidates = achievement_candidates + insight_candidates
        selected = self.resolve_single_message(
            all_candidates,
            source_event_type="transaction",
            source_event_id=int(tx["id"]),
            period_key=str(context["period_key"]),
            reference_date=str(tx.get("date") or ""),
            source=source,
        )
        if selected is None:
            if is_nl_transaction:
                self.increment_achievement_counter("nl_transactions")
            return None, None
        if is_nl_transaction:
            self.increment_achievement_counter("nl_transactions")
        if selected["message_type"] == "achievement":
            for counter_key, step in cast(list[tuple[str, int]], selected.get("counter_updates") or []):
                self.increment_achievement_counter(str(counter_key), step=int(step))
            AchievementEvent.create(
                user_id=1,
                transaction_id=int(tx["id"]),
                achievement_code=str(selected["code"]),
                message=str(selected["message"]),
                priority=int(selected.get("priority") or 0),
                period_key=str(context["period_key"]),
                extra_context=json.dumps({"source": source}, ensure_ascii=False),
            )
            return selected, None
        InsightEvent.create(
            user_id=1,
            transaction_id=int(tx["id"]),
            insight_code=str(selected["code"]),
            message=str(selected["message"]),
            priority=int(selected.get("priority") or 0),
            period_key=str(context["period_key"]),
            extra_context=json.dumps(
                {
                    "category_id": context.get("category_id"),
                    "category_name": context.get("category_name"),
                    "amount": float(tx.get("amount") or 0.0),
                },
                ensure_ascii=False,
            ),
        )
        return None, selected
