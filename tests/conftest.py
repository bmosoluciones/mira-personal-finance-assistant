# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Shared pytest fixtures and configuration."""

from __future__ import annotations

import importlib as _importlib

import pytest

from mira.db.runtime import reset_active_database_guard_for_tests


def opengl_import_error() -> bool:
    """Return True when PySide6 Qt modules backed by OpenGL/EGL cannot be imported.

    Checks both PySide6.QtWidgets (requires libEGL) and PySide6.QtCharts.
    Use as the condition for @pytest.mark.skipif to skip tests that require
    a graphical environment::

        @pytest.mark.skipif(opengl_import_error(), reason="OpenGL not available")
        def test_something_with_qt(...): ...
    """
    for module in ("PySide6.QtWidgets", "PySide6.QtCharts"):
        try:
            _importlib.import_module(module)
        except Exception:
            return True
    return False


@pytest.fixture(autouse=True)
def _reset_database_singleton() -> None:
    """Reset the Database singleton guard after every test.

    Prevents a test that crashes before calling db.close() from leaving
    the process-wide connection guard set and blocking all subsequent tests.
    """
    yield
    reset_active_database_guard_for_tests()
