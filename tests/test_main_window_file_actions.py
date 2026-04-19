# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

from mira.ui.main_window_support import resolve_transaction_export_path


def test_resolve_transaction_export_path_defaults_to_csv_without_extension() -> None:
    assert resolve_transaction_export_path("transactions", "Transaction Files (*.csv *.xlsx)") == "transactions.csv"


def test_resolve_transaction_export_path_uses_xlsx_for_excel_filter() -> None:
    assert resolve_transaction_export_path("transactions", "Excel Files (*.xlsx)") == "transactions.xlsx"


def test_resolve_transaction_export_path_preserves_explicit_extension() -> None:
    assert resolve_transaction_export_path("transactions.xlsx", "CSV Files (*.csv)") == "transactions.xlsx"
