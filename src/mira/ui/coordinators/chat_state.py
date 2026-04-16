# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Pure state holder for chat history navigation."""

from __future__ import annotations


class ChatState:
    """Track chat history and batch-focused navigation."""

    def __init__(self) -> None:
        """Initialize the ChatState instance."""
        self._messages: list[str] = []
        self._index = -1
        self._pending_batch_start: int | None = None

    @property
    def messages(self) -> list[str]:
        """Return messages."""
        return self._messages

    @property
    def current_index(self) -> int:
        """Return current index."""
        return self._index

    @property
    def pending_batch_start(self) -> int | None:
        """Return pending batch start."""
        return self._pending_batch_start

    @property
    def message_count(self) -> int:
        """Return message count."""
        return len(self._messages)

    @property
    def has_current(self) -> bool:
        """Return whether  current."""
        return self.current() is not None

    @property
    def can_prev(self) -> bool:
        """Return whether can prev."""
        return self._index > 0

    @property
    def can_next(self) -> bool:
        """Return whether can next."""
        return 0 <= self._index < len(self._messages) - 1

    def append_block(self, block: str) -> bool:
        """Return append block."""
        started_new_batch = self._pending_batch_start is None
        pending_batch_start = self._pending_batch_start
        if pending_batch_start is None:
            pending_batch_start = len(self._messages)
            self._pending_batch_start = pending_batch_start
        self._messages.append(block)
        self._index = pending_batch_start
        return started_new_batch

    def reset_pending_batch(self) -> None:
        """Return reset pending batch."""
        self._pending_batch_start = None

    def current(self) -> str | None:
        """Return current."""
        if not self._messages or self._index < 0:
            return None
        self._index = max(0, min(self._index, len(self._messages) - 1))
        return self._messages[self._index]

    def current_message(self) -> str | None:
        """Return current message."""
        return self.current()

    def prev(self) -> str | None:
        """Return prev."""
        if self._index > 0:
            self._index -= 1
        return self.current()

    def next(self) -> str | None:
        """Return next."""
        if 0 <= self._index < len(self._messages) - 1:
            self._index += 1
        return self.current()

    def clear(self) -> None:
        """Return clear."""
        self._messages.clear()
        self._index = -1
        self._pending_batch_start = None
