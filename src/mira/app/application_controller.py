# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Application-level result interpretation for the desktop UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from mira.ai.executor import ActionResult
from mira.db.database import Database


@dataclass(frozen=True)
class ApplicationDirective:
    """Semantic UI-agnostic instruction derived from an action result."""

    kind: Literal["message", "show_report", "run_analysis"]
    chat_message: str | None = None
    report_payload: dict[str, Any] | None = None
    analysis_period: dict[str, Any] | None = None
    show_quick_actions: bool = False
    refresh_all: bool = True


class ApplicationController:
    """Translate pipeline results into semantic application directives."""

    def __init__(self, db: Database, pipeline: object) -> None:
        self._db = db
        self._pipeline = pipeline

    def handle_result(self, result: ActionResult) -> ApplicationDirective:
        chat_message = str(result.message or "").strip() or None
        show_quick_actions = result.action == "none"

        if result.action == "report":
            payload = result.data if isinstance(result.data, dict) else None
            return ApplicationDirective(
                kind="show_report",
                chat_message=chat_message,
                report_payload=payload,
                show_quick_actions=show_quick_actions,
            )

        if result.action == "data_analysis":
            period = result.data.get("period") if isinstance(result.data, dict) else None
            analysis_period = period if isinstance(period, dict) else None
            return ApplicationDirective(
                kind="run_analysis",
                chat_message=chat_message,
                analysis_period=analysis_period,
                show_quick_actions=show_quick_actions,
            )

        return ApplicationDirective(
            kind="message",
            chat_message=chat_message,
            show_quick_actions=show_quick_actions,
        )
