# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Service-layer helpers for non-UI orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .database_io import DatabaseIOService
    from .model_lifecycle import ModelLifecycle, ModelLifecycleState

__all__ = ["DatabaseIOService", "ModelLifecycle", "ModelLifecycleState"]


def __getattr__(name: str) -> Any:
    """Return getattr  ."""
    if name == "DatabaseIOService":
        from .database_io import DatabaseIOService

        return DatabaseIOService
    if name in {"ModelLifecycle", "ModelLifecycleState"}:
        from .model_lifecycle import ModelLifecycle, ModelLifecycleState

        return {
            "ModelLifecycle": ModelLifecycle,
            "ModelLifecycleState": ModelLifecycleState,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
