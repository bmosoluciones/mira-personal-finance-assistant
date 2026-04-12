# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Full AI pipeline for MIRA.

Orchestrates:
  1. Normalizer - deterministic text cleanup
  2. Transaction parser - deterministic extraction for structured actions
  3. Validator - strict schema checking
  4. Executor - database operations
  5. Optional local chat engine - GGUF-backed conversational mode
"""

from __future__ import annotations

import json
import logging
import re
import threading

from mira.ai.base_engine import BaseEngine
from mira.ai.engine import get_chat_engine
from mira.ai.parser_engine import TransactionParserEngine
from mira.ai.executor import ActionResult, Executor
from mira.ai.normalizer import normalise
from mira.ai.validator import validate
from mira.db.database import Database
from mira.ui.i18n import tr

logger = logging.getLogger(__name__)

_EXPECTED_NORMALIZER_ERRORS = (AttributeError, TypeError, ValueError)
_EXPECTED_PARSER_ERRORS = (json.JSONDecodeError, RuntimeError, TypeError, ValueError)
_EXPECTED_EXECUTOR_ERRORS = (RuntimeError, TypeError, ValueError)
_EXPECTED_CHAT_ERRORS = (OSError, RuntimeError, TypeError, ValueError)
_EXPECTED_ENGINE_RELOAD_ERRORS = (ImportError, OSError, RuntimeError, TypeError, ValueError)

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
_CHAT_UNAVAILABLE_MESSAGES = {
    "en": (
        "Chat mode is unavailable because there is no active GGUF model. "
        "You can keep using assistant mode to record and review your finances."
    ),
    "es": (
        "El modo chat no está disponible porque no hay un modelo GGUF activo. "
        "Puedes seguir usando el modo asistente para registrar y consultar tus finanzas."
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
        model_path: str | None = None,
    ) -> None:
        self._db = db
        self._parser: BaseEngine = engine or TransactionParserEngine(
            default_currency=db.setting.get_default_currency(),
        )
        self._chat_engine: BaseEngine | None = get_chat_engine(model_path, language=self._chat_language())
        self._executor = Executor(db)
        self._model_path = model_path
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

    def process_chat(self, user_input: str) -> ActionResult:
        """Process text in free-form chat mode."""
        try:
            with self._engine_lock:
                if self._chat_engine is None:
                    raise RuntimeError("chat unavailable")
                self._chat_engine.set_language(self._chat_language(user_input))
                response = self._chat_engine.chat(user_input)
        except _EXPECTED_CHAT_ERRORS as exc:
            logger.warning("Chat mode failed: %s", exc)
            return ActionResult(
                success=False,
                action="chat",
                message=self._chat_unavailable_message(user_input),
            )
        return ActionResult(success=True, action="chat", message=response)

    def reload_engine(self, model_path: str | None) -> None:
        """Hot-reload the optional chat engine when the selected model changes."""
        with self._engine_lock:
            if self._chat_engine is not None:
                self._chat_engine.shutdown()

            self._model_path = model_path
            try:
                self._chat_engine = get_chat_engine(model_path, language=self._chat_language())
            except _EXPECTED_ENGINE_RELOAD_ERRORS as exc:
                logger.warning("Failed to reload chat engine: %s", exc)
                self._chat_engine = None

    def _parser_error_result(self, user_input: str | None = None) -> ActionResult:
        return ActionResult(success=False, action="none", message=self._parser_error_message(user_input))

    def _chat_language(self, user_input: str | None = None) -> str:
        if user_input:
            normalized_input = " ".join(str(user_input).casefold().split())
            words = set(re.findall(r"\w+", normalized_input, flags=re.UNICODE))
            if re.search(r"[áéíóúñ¿¡]", normalized_input) or _SPANISH_HINT_WORDS.intersection(words):
                return "es"
        return "es" if str(self._db.setting.get("language") or "en").strip().lower() == "es" else "en"

    def _parser_error_message(self, user_input: str | None = None) -> str:
        language = self._chat_language(user_input)
        return tr(
            "chat.parser.error",
            language,
            default=_PARSER_ERROR_MESSAGES[language],
        )

    def _chat_unavailable_message(self, user_input: str | None = None) -> str:
        language = self._chat_language(user_input)
        return tr(
            "chat.unavailable",
            language,
            default=_CHAT_UNAVAILABLE_MESSAGES[language],
        )

    @property
    def engine(self) -> BaseEngine:
        return self._parser

    @property
    def chat_engine(self) -> BaseEngine | None:
        return self._chat_engine

    @property
    def llm_ready(self) -> bool:
        return self._chat_engine is not None

    def shutdown(self) -> None:
        with self._engine_lock:
            if self._chat_engine is not None:
                self._chat_engine.shutdown()
