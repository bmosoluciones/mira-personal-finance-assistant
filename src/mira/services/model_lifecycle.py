# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Non-UI model lifecycle coordination for the desktop app."""

from __future__ import annotations

from dataclasses import dataclass

from mira.ai.llm_config import load_llm_config
from mira.ai.pipeline import Pipeline
from mira.db.database import Database
from mira.i18n import normalize_language, tr


@dataclass(frozen=True)
class ModelLifecycleState:
    """UI-ready description of the current assistant/chat engine state."""

    active_model_name: str
    engine_info: str
    mode_visible: bool
    forced_mode: str | None
    mode_warning: str | None
    status_message: str | None


class ModelLifecycle:
    """Resolve model selection and keep interaction mode consistent."""

    def __init__(self, db: Database, pipeline: Pipeline) -> None:
        """Initialize the ModelLifecycle instance."""
        self._db = db
        self._pipeline = pipeline

    def reload_selected_model(self, interaction_mode: str) -> ModelLifecycleState:
        """Reload the HTTP chat client from saved settings."""
        self._pipeline.reload_engine()
        return self._build_state(interaction_mode=interaction_mode)

    def sync_engine_info(self, cli_model_name: str | None = None) -> ModelLifecycleState:
        """Return sync engine info."""
        interaction_mode = str(self._db.setting.get("llm_interaction_mode") or "assistant")
        return self._build_state(cli_model_name=cli_model_name, interaction_mode=interaction_mode)

    def _chat_allowed(self) -> bool:
        """Return whether chat may run against the configured provider."""
        return load_llm_config(self._db).chat_allowed

    def _selected_model_name(self) -> str:
        """Return the configured remote model name when chat is allowed."""
        config = load_llm_config(self._db)
        return config.model if config.chat_allowed else ""

    def _language(self) -> str:
        """Return language."""
        return normalize_language(self._db.setting.get("language"))

    def _build_state(self, *, interaction_mode: str, cli_model_name: str | None = None) -> ModelLifecycleState:
        """Return build state."""
        language = self._language()
        parser_type = type(self._pipeline.engine).__name__
        chat_engine = getattr(self._pipeline, "chat_engine", None)
        chat_type = type(chat_engine).__name__ if chat_engine is not None else ""
        llm_ready = bool(getattr(self._pipeline, "llm_ready", False))
        active_model_name = self._selected_model_name()
        if not active_model_name and llm_ready:
            # Chat is off, so the only model in play is the deprecated CLI one.
            active_model_name = str(cli_model_name or "").strip()

        if llm_ready:
            engine_info = f"{parser_type} + {chat_type}".strip()
            status_message = None
            if active_model_name:
                engine_info = f"{engine_info} ({active_model_name})"
                status_message = tr(
                    "status.model_loading_selected" if self._chat_allowed() else "status.model_loading_cli",
                    language,
                    default="Loading selected LLM model: {model}",
                    params={"model": active_model_name},
                )
            return ModelLifecycleState(
                active_model_name=active_model_name,
                engine_info=engine_info,
                mode_visible=True,
                forced_mode=None,
                mode_warning=None,
                status_message=status_message,
            )

        forced_mode = "assistant" if interaction_mode == "chat" else None
        if forced_mode is not None:
            self._db.setting.set("llm_interaction_mode", forced_mode)

        return ModelLifecycleState(
            active_model_name=active_model_name,
            engine_info=parser_type,
            mode_visible=False,
            forced_mode=forced_mode,
            mode_warning=(
                tr("settings.mode.chat_unavailable", language)
                if forced_mode is not None
                else None
            ),
            status_message=None,
        )
