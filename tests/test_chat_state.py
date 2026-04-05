# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

from mira.ui.coordinators.chat_state import ChatState


def test_append_block_keeps_focus_on_first_message_of_pending_batch() -> None:
    state = ChatState()

    assert state.append_block("uno") is True
    assert state.append_block("dos") is False

    assert state.messages == ["uno", "dos"]
    assert state.message_count == 2
    assert state.current_index == 0
    assert state.current() == "uno"
    assert state.current_message() == "uno"
    assert state.can_prev is False
    assert state.can_next is True

    state.reset_pending_batch()
    assert state.append_block("tres") is True
    assert state.current() == "tres"
    assert state.current_index == 2


def test_navigation_and_clear_are_bounded() -> None:
    state = ChatState()
    state.append_block("uno")
    state.reset_pending_batch()
    state.append_block("dos")
    state.reset_pending_batch()
    state.append_block("tres")
    state.reset_pending_batch()

    assert state.current() == "tres"
    assert state.prev() == "dos"
    assert state.prev() == "uno"
    assert state.prev() == "uno"
    assert state.next() == "dos"
    assert state.next() == "tres"
    assert state.next() == "tres"
    assert state.can_prev is True
    assert state.can_next is False
    assert state.has_current is True

    state.clear()
    assert state.messages == []
    assert state.current() is None
    assert state.current_index == -1
    assert state.pending_batch_start is None
    assert state.message_count == 0
    assert state.has_current is False
