# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Application service for post-download model activation."""

from __future__ import annotations

from dataclasses import dataclass

from mira.db.database import Database
from mira.services import ModelLifecycle, ModelLifecycleState


@dataclass(frozen=True)
class ModelDownloadResult:
    """Outcome of completing a default model download."""

    downloaded_path: str
    preferred_model_name: str
    lifecycle_state: ModelLifecycleState
    refresh_settings: bool = True


class ModelDownloadService:
    """Persist the downloaded model and reload the active engine."""

    def __init__(self, db: Database, model_lifecycle: ModelLifecycle) -> None:
        """Initialize the ModelDownloadService instance."""
        self._db = db
        self._model_lifecycle = model_lifecycle

    def complete_default_download(
        self,
        filename: str,
        downloaded_path: str,
        active_runtime_path: str | None,
        interaction_mode: str,
    ) -> ModelDownloadResult:
        """Return complete default download."""
        preferred_model_name = str(filename or "").strip()
        self._db.setting.set("preferred_model", preferred_model_name)
        lifecycle_state = self._model_lifecycle.reload_selected_model(active_runtime_path, interaction_mode)
        return ModelDownloadResult(
            downloaded_path=downloaded_path,
            preferred_model_name=preferred_model_name,
            lifecycle_state=lifecycle_state,
        )
