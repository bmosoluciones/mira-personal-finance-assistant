# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import importlib
import sys

import pytest

from conftest import opengl_import_error

pytestmark = pytest.mark.skipif(
    opengl_import_error(),
    reason="PySide6.QtWidgets requires libEGL (not available in headless environments)",
)


def test_dialogs_package_reexports_existing_and_financial_dialogs() -> None:
    dialogs_module = importlib.import_module("mira.ui.dialogs")
    financial_module = importlib.import_module("mira.ui.dialogs.financial")

    try:
        assert hasattr(dialogs_module, "InitialSetupDialog")
        assert dialogs_module.CompoundInterestDialog is financial_module.CompoundInterestDialog
        assert dialogs_module.LoanAmortizationDialog is financial_module.LoanAmortizationDialog
        assert dialogs_module.GoalScenarioDialog is financial_module.GoalScenarioDialog
    finally:
        for module_name in ("PySide6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"):
            sys.modules.pop(module_name, None)
