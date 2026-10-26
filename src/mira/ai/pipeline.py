# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Full AI pipeline for MIRA.

Orchestrates:
  1. Normalizer - deterministic text cleanup
  2. Transaction parser - deterministic extraction for structured actions
  3. Validator - strict schema checking
  4. Executor - database operations
"""

from __future__ import annotations

import json
import logging
import re
import threading

from mira.ai.base_engine import BaseEngine
from mira.ai.executor import ActionResult, Executor
from mira.ai.normalizer import normalise
from mira.ai.parser_engine import TransactionParserEngine
from mira.ai.validator import validate
from mira.db.database import Database
from mira.i18n import tr

logger = logging.getLogger(__name__)

_EXPECTED_NORMALIZER_ERRORS = (AttributeError, TypeError, ValueError)
_EXPECTED_PARSER_ERRORS = (json.JSONDecodeError, RuntimeError, TypeError, ValueError)
_EXPECTED_EXECUTOR_ERRORS = (RuntimeError, TypeError, ValueError)

_PARSER_ERROR_MESSAGES = {
    "en": (
        "Sorry, I couldn't process your request. "
        "Please try something like:\n"
        '  - "received 500 salary"\n'
        '  - "spent 30 on groceries"\n'
        '  - "report"'
    ),
    "es": (
        "Disculpa, no pude procesar tu solicitud. "
        "Por favor intenta con algo como:\n"
        '  - "recibi 500 de salario"\n'
        '  - "gaste 30 en comida"\n'
        '  - "reporte"'
    ),
}
_SPANISH_HINT_WORDS = {
    "abone",
    "aboné",
    "ahorro",
    "comida",
    "cuenta",
    "finanzas",
    "gaste",
    "gasté",
    "gasto",
    "gastos",
    "gracias",
    "hola",
    "ingreso",
    "modelo",
    "pague",
    "pagué",
    "recibi",
    "recibí",
    "reporte",
    "saldo",
    "salario",
    "tarjeta",
}


class Pipeline:
    """End-to-end natural-language -> action pipeline."""

    def __init__(
        self,
        db: Database,
        engine: BaseEngine | None = None,
    ) -> None:
        """Initialize the Pipeline instance."""
        self._db = db
        self._parser: BaseEngine = engine or TransactionParserEngine(
            default_currency=db.setting.get_default_currency(),
        )
        self._executor = Executor(db)
        self._engine_lock = threading.RLock()

    def process(self, user_input: str) -> ActionResult:
        """Process a raw user string through assistant mode."""
        try:
            cleaned = normalise(user_input)
            logger.debug("Normalised input: %r -> %r", user_input, cleaned)
        except _EXPECTED_NORMALIZER_ERRORS as exc:
            logger.warning("Normaliser failed: %s", exc)
            cleaned = user_input

        try:
            with self._engine_lock:
                raw = self._parser.parse(cleaned)
            logger.debug("Parser output: %r", raw)
        except _EXPECTED_PARSER_ERRORS as exc:
            logger.warning("Parser failed: %s", exc)
            return self._parser_error_result(cleaned)

        result = validate(raw, default_base_currency=self._db.setting.get_default_currency())
        if not result.valid:
            logger.warning("Validation failed: %s", result.error)
            return self._parser_error_result(cleaned)

        action = dict(result.action or {})

        try:
            return self._executor.execute(action)
        except _EXPECTED_EXECUTOR_ERRORS as exc:
            logger.error("Executor failed: %s", exc)
            return self._parser_error_result(cleaned)

    def reload_engine(self) -> None:
        """Refresh the parser's default currency after settings change."""
        with self._engine_lock:
            self._parser.set_default_currency(self._db.setting.get_default_currency())

    def _parser_error_result(self, user_input: str | None = None) -> ActionResult:
        """Return parser error result."""
        return ActionResult(success=False, action="none", message=self._parser_error_message(user_input))

    def _chat_language(self, user_input: str | None = None) -> str:
        """Return chat language."""
        if user_input:
            normalized_input = " ".join(str(user_input).casefold().split())
            words = set(re.findall(r"\w+", normalized_input, flags=re.UNICODE))
            if re.search(r"[áéíóúñ¿¡]", normalized_input) or _SPANISH_HINT_WORDS.intersection(words):
                return "es"
        return "es" if str(self._db.setting.get("language") or "en").strip().lower() == "es" else "en"

    def _parser_error_message(self, user_input: str | None = None) -> str:
        """Return parser error message."""
        language = self._chat_language(user_input)
        return tr(
            "chat.parser.error",
            language,
            default=_PARSER_ERROR_MESSAGES[language],
        )

    @property
    def engine(self) -> BaseEngine:
        """Return engine."""
        return self._parser

    def shutdown(self) -> None:
        """Release parser resources if the engine provides any."""
        with self._engine_lock:
            self._parser.shutdown()
