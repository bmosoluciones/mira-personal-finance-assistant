# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import pytest
from openpyxl import Workbook

from mira.app.view_services import ReconciliationViewService
from mira.db.database import Database


@pytest.fixture
def db(tmp_path):
    database = Database(path=tmp_path / "test.db")
    database.connect()
    yield database
    database.close()


def _write_reconciliation_workbook(path, headers: list[str], rows: list[list[object]]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Statement"
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    workbook.save(path)


@pytest.mark.parametrize(
    "headers",
    [
        ["fecha", "referencia", "descripcion", "ingreso", "gastos"],
        ["date", "reference", "description", "income", "expense"],
        ["Date", "referencia", "description", "income", "gastos"],
    ],
)
def test_reconciliation_parse_excel_accepts_bilingual_headers(db, tmp_path, headers: list[str]) -> None:
    filepath = tmp_path / "statement.xlsx"
    _write_reconciliation_workbook(
        filepath,
        headers,
        [["2026-04-01", "REF-01", "Deposit", "100.00", None]],
    )

    preview = ReconciliationViewService(db).parse_excel(str(filepath))

    assert preview.has_blocking_error is False
    assert len(preview.valid_rows) == 1
    assert preview.valid_rows[0].date == "2026-04-01"
    assert preview.valid_rows[0].reference == "REF-01"


def test_reconciliation_parse_excel_accepts_date_as_first_column(db, tmp_path) -> None:
    filepath = tmp_path / "date_first.xlsx"
    _write_reconciliation_workbook(
        filepath,
        ["Date", "Reference", "Description", "Income", "Expense"],
        [["2026-04-02", "REF-02", "Payroll", "500.00", None]],
    )

    preview = ReconciliationViewService(db).parse_excel(str(filepath))

    assert len(preview.valid_rows) == 1
    assert preview.valid_rows[0].date == "2026-04-02"


def test_reconciliation_parse_excel_reports_missing_columns_after_alias_resolution(db, tmp_path) -> None:
    filepath = tmp_path / "missing.xlsx"
    _write_reconciliation_workbook(
        filepath,
        ["Date", "Reference", "Description", "Income"],
        [["2026-04-03", "REF-03", "Deposit", "50.00"]],
    )

    preview = ReconciliationViewService(db).parse_excel(str(filepath))

    assert preview.has_blocking_error is True
    assert preview.missing_columns == ("expense",)
