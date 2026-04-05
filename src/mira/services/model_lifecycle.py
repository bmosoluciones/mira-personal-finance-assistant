# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Non-UI model lifecycle coordination for the desktop app."""

from __future__ import annotations

from dataclasses import dataclass

from mira.ai.model_registry import find_model_path_by_name
from mira.ai.pipeline import Pipeline
from mira.db.database import Database
from mira.ui.i18n import normalize_language, tr


@dataclass(frozen=True)
class ModelLifecycleState:
    """UI-ready description of the current assistant/chat engine state."""

    active_model_name: str
    active_model_path: str | None
    engine_info: str
    mode_visible: bool
    forced_mode: str | None
    mode_warning: str | None
    status_message: str | None


class ModelLifecycle:
    """Resolve model selection and keep interaction mode consistent."""

    def __init__(self, db: Database, pipeline: Pipeline) -> None:
        self._db = db
        self._pipeline = pipeline

    def resolve_model_path(self, active_runtime_path: str | None) -> str | None:
        selected_path = self._selected_model_path()
        if selected_path is not None:
            return selected_path

        runtime_model_path = str(active_runtime_path or "").strip()
        return runtime_model_path or None

    def reload_selected_model(self, active_runtime_path: str | None, interaction_mode: str) -> ModelLifecycleState:
        model_path = self.resolve_model_path(active_runtime_path)
        self._pipeline.reload_engine(model_path=model_path)
        return self._build_state(active_runtime_path=model_path, interaction_mode=interaction_mode)

    def sync_engine_info(self, active_runtime_path: str | None) -> ModelLifecycleState:
        interaction_mode = str(self._db.setting.get("llm_interaction_mode") or "assistant")
        return self._build_state(active_runtime_path=active_runtime_path, interaction_mode=interaction_mode)

    def _selected_model_name(self) -> str:
        return str(self._db.setting.get("preferred_model") or "").strip()

    def _selected_model_path(self) -> str | None:
        selected_model = self._selected_model_name()
        if not selected_model:
            return None

        model_path = find_model_path_by_name(selected_model)
        if model_path is None or not model_path.is_file():
            return None
        return str(model_path)

    def _language(self) -> str:
        return normalize_language(self._db.setting.get("language"))

    def _build_state(self, *, active_runtime_path: str | None, interaction_mode: str) -> ModelLifecycleState:
        language = self._language()
        parser_type = type(self._pipeline.engine).__name__
        chat_engine = getattr(self._pipeline, "chat_engine", None)
        chat_type = type(chat_engine).__name__ if chat_engine is not None else ""
        llm_ready = bool(getattr(self._pipeline, "llm_ready", False))
        selected_model_name = self._selected_model_name()
        selected_model_path = self._selected_model_path()
        active_model_name = selected_model_name if selected_model_path is not None else ""
        active_model_path = self.resolve_model_path(active_runtime_path)

        if llm_ready:
            engine_info = f"{parser_type} + {chat_type}".strip()
            status_message = None
            if active_model_name:
                engine_info = f"{engine_info} ({active_model_name})"
                status_message = tr(
                    "status.model_loading_selected",
                    language,
                    default="Loading selected LLM model: {model}",
                    params={"model": active_model_name},
                )
            elif active_model_path:
                engine_info = f"{engine_info} ({active_model_path})"
                status_message = tr(
                    "status.model_loading_cli",
                    language,
                    default="Using LLM model defined by CLI.",
                )
            return ModelLifecycleState(
                active_model_name=active_model_name,
                active_model_path=active_model_path,
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
            active_model_path=active_model_path,
            engine_info=parser_type,
            mode_visible=False,
            forced_mode=forced_mode,
            mode_warning=(
                tr(
                    "settings.mode.chat_unavailable",
                    language,
                    default="Chat mode requires an active GGUF model. Returning to assistant mode.",
                )
                if forced_mode is not None
                else None
            ),
            status_message=None,
        )
