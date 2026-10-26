# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Abstract parser engine contract for MIRA."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseEngine(ABC):
    """Abstract base class for MIRA's transaction parser engines."""

    @abstractmethod
    def parse(self, user_input: str) -> dict[str, Any]:
        """Parse *user_input* and return a structured action dict."""

    def set_default_currency(self, currency: str | None) -> None:
        """Update the user's default currency when the engine supports it."""
        _ = currency

    def shutdown(self) -> None:
        """Release optional engine resources when the implementation needs it."""
