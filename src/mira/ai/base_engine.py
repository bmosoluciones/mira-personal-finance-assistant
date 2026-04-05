# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Abstract AI engine contract for MIRA."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseEngine(ABC):
    """Abstract base class for MIRA's AI engines."""

    @abstractmethod
    def parse(self, user_input: str) -> dict[str, Any]:
        """Parse *user_input* and return a structured action dict."""

    def chat(self, user_input: str) -> str:
        """Return a free-form assistant response for chat mode."""
        raise NotImplementedError("This engine does not support chat mode")

    def set_language(self, language: str) -> None:
        """Update the active chat language when the engine supports it."""
        _ = language

    def shutdown(self) -> None:
        """Release optional engine resources when the implementation needs it."""
