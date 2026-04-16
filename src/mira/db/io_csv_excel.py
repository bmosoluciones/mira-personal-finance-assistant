# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

if TYPE_CHECKING:
    from openpyxl.cell.cell import Cell as _OpenpyxlCell

from mira.db.money import MONEY_ZERO, MoneyLike, money_to_decimal

logger = logging.getLogger(__name__)

_CSV_IMPORT_ROW_ERRORS = (KeyError, TypeError, ValueError, OverflowError)


class _DatabaseIOProtocol(Protocol):
    def get_transactions(
        self,
        *,
        limit: int = 50,
        tx_type: str | None = None,
        account_id: int | None = None,
        since_date: str | None = None,
        until_date: str | None = None,
        category: str | None = None,
        payment_method: str | None = None,
        min_amount: MoneyLike | None = None,
        max_amount: MoneyLike | None = None,
        search: str | None = None,
        tag_id: int | None = None,
        include_children: bool = False,
    ) -> list[dict]: ...

    def get_transactions_tags_bulk(self, transaction_ids: list[int]) -> dict[int, list[dict]]: ...

    def get_budget_comparison(self, budget_id: int, granularity: str = "quarterly") -> dict[str, object]: ...

    def get_or_create_account(self, name: str) -> dict: ...

    def get_setting(self, key: str) -> str | None: ...

    def add_transaction(
        self,
        *,
        account_id: int,
        tx_type: str,
        amount: MoneyLike,
        description: str | None = None,
        category: str | None = None,
        subcategory: str | None = None,
        payment_method: str = "cash",
        receipt_path: str | None = None,
        tx_date: str | None = None,
        note: str | None = None,
        to_account_id: int | None = None,
        is_transfer: int = 0,
        exchange_rate: float | None = None,
        converted_amount: MoneyLike | None = None,
        category_id: int | None = None,
        source: str | None = None,
    ) -> dict: ...

    def get_or_create_tag(self, name: str) -> dict: ...

    def get_tag_by_name(self, name: str) -> dict | None: ...

    def add_tag(self, name: str, color: str = "#888888", icon: str = "") -> dict: ...

    def add_transaction_tag(self, transaction_id: int, tag_id: int) -> None: ...

    def set_transaction_tags(self, transaction_id: int, tag_ids: list[int]) -> None: ...


def export_transactions_csv(
    db: _DatabaseIOProtocol,
    filepath: str,
    *,
    tx_type: str | None = None,
    account_id: int | None = None,
    since_date: str | None = None,
    until_date: str | None = None,
    category: str | None = None,
    search: str | None = None,
) -> int:
    """Export filtered transactions to a CSV file. Returns row count."""
    txs = db.get_transactions(
        limit=1_000_000,
        tx_type=tx_type,
        account_id=account_id,
        since_date=since_date,
        until_date=until_date,
        category=category,
        search=search,
    )
    columns = [
        "id",
        "date",
        "type",
        "amount",
        "account_name",
        "category",
        "subcategory",
        "payment_method",
        "description",
        "note",
        "receipt_path",
        "tags",
    ]
    tx_ids = [tx["id"] for tx in txs]
    tags_map = db.get_transactions_tags_bulk(tx_ids) if tx_ids else {}
    for tx in txs:
        tag_list = tags_map.get(tx["id"], [])
        tx["tags"] = ", ".join(t["name"] for t in tag_list)
    with open(filepath, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(txs)
    return len(txs)


def _variance_signal(section: str, variance: float) -> str:
    if abs(variance) < 0.005:
        return "neutral"
    if section == "income":
        return "positive" if variance > 0 else "negative"
    if section == "expense":
        return "negative" if variance > 0 else "positive"
    return "positive" if variance > 0 else "negative"


def _wc(cell: Any) -> "_OpenpyxlCell":
    """Cast an openpyxl cell to a writable Cell (stubs return Union[Cell, ReadOnlyCell, MergedCell])."""
    return cast("_OpenpyxlCell", cell)


def export_budget_comparison_excel(
    db: _DatabaseIOProtocol,
    filepath: str | Path,
    budget_id: int,
    *,
    granularity: str = "quarterly",
) -> int:
    """Export the real-vs-budget comparison to an Excel workbook. Returns exported row count."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    comparison = db.get_budget_comparison(budget_id, granularity=granularity)
    budget = cast(dict[str, Any], comparison["budget"])
    periods = cast(list[dict[str, Any]], comparison["periods"])
    rows = cast(list[dict[str, Any]], comparison["rows"])
    totals = cast(dict[str, Any], comparison["totals"])
    excluded_transactions = int(cast(Any, comparison["excluded_transactions"]))

    headers = ["Categoría"]
    for period in periods:
        label = str(period["label"])
        headers.extend([f"{label} Real", f"{label} PPTO", f"{label} Var"])
    headers.extend(["Año Real", "Año PPTO", "Año Var"])

    incomes = [row for row in rows if row["type"] == "income"]
    expenses = [row for row in rows if row["type"] == "expense"]
    structure = [
        ("section", "Ingresos"),
        *[("category", row) for row in incomes],
        ("total_income", None),
        ("section", "Gastos"),
        *[("category", row) for row in expenses],
        ("total_expense", None),
        ("balance", None),
    ]

    target = Path(filepath).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Real vs PPTO"
    sheet.freeze_panes = "A9"

    title = f"Reporte Real vs Presupuesto | {budget['code']} | {budget['year']} | {budget['currency']}"
    sheet.cell(1, 1, title)
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))

    meta_rows: list[tuple[str, str | int | None]] = [
        ("Presupuesto", str(budget["code"])),
        ("Año", int(budget["year"])),
        ("Moneda", str(budget["currency"])),
        (
            "Vista",
            {
                "monthly": "Mensual",
                "quarterly": "Trimestral",
                "semiannual": "Semestral",
                "annual": "Anual",
            }.get(granularity, granularity),
        ),
        ("Transacciones excluidas", excluded_transactions),
    ]
    for row_idx, (label, value) in enumerate(meta_rows, start=2):
        sheet.cell(row_idx, 1, label)
        sheet.cell(row_idx, 2, value)

    title_fill = PatternFill("solid", fgColor="263140")
    header_fill = PatternFill("solid", fgColor="2F3640")
    section_fill = PatternFill("solid", fgColor="263140")
    income_total_fill = PatternFill("solid", fgColor="21332E")
    expense_total_fill = PatternFill("solid", fgColor="352826")
    balance_fill = PatternFill("solid", fgColor="223042")
    positive_fill = PatternFill("solid", fgColor="173B36")
    negative_fill = PatternFill("solid", fgColor="472624")
    neutral_fill = PatternFill("solid", fgColor="30363D")

    title_font = Font(color="F0F3F7", bold=True, size=14)
    white_font = Font(color="FFFFFF", bold=True)
    section_font = Font(color="D6DEE8", bold=True)
    positive_font = Font(color="7FE7D2", bold=True)
    negative_font = Font(color="FFB0A3", bold=True)
    neutral_font = Font(color="C4CCD5", bold=True)

    thin_border = Border(
        left=Side(style="thin", color="4A5563"),
        right=Side(style="thin", color="4A5563"),
        top=Side(style="thin", color="4A5563"),
        bottom=Side(style="thin", color="4A5563"),
    )

    _wc(sheet["A1"]).fill = title_fill
    _wc(sheet["A1"]).font = title_font
    _wc(sheet["A1"]).alignment = Alignment(horizontal="left", vertical="center")

    for row_idx in range(2, 7):
        _wc(sheet.cell(row_idx, 1)).font = Font(bold=True)

    header_row = 8
    for col_idx, header in enumerate(headers, start=1):
        cell = _wc(sheet.cell(header_row, col_idx, header))
        cell.fill = header_fill
        cell.font = white_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border

    row_idx = 9
    for kind, payload in structure:
        if kind == "section":
            for col_idx in range(1, len(headers) + 1):
                cell = _wc(sheet.cell(row_idx, col_idx))
                cell.fill = section_fill
                cell.border = thin_border
            section_cell = _wc(sheet.cell(row_idx, 1, str(payload)))
            section_cell.font = section_font
            row_idx += 1
            continue

        if kind == "category":
            category = cast(dict[str, Any], payload)
            section = str(category["type"])
            sheet.cell(row_idx, 1, str(category["name"]))
            col_idx = 2
            for period in cast(list[dict[str, Any]], category["periods"]):
                sheet.cell(row_idx, col_idx, float(period["real"]))
                sheet.cell(row_idx, col_idx + 1, float(period["budget"]))
                variance_cell = _wc(sheet.cell(row_idx, col_idx + 2, float(period["variance"])))
                signal = _variance_signal(section, float(period["variance"]))
                variance_cell.fill = {
                    "positive": positive_fill,
                    "negative": negative_fill,
                    "neutral": neutral_fill,
                }[signal]
                variance_cell.font = {
                    "positive": positive_font,
                    "negative": negative_font,
                    "neutral": neutral_font,
                }[signal]
                col_idx += 3
            sheet.cell(row_idx, col_idx, float(category["annual_real"]))
            sheet.cell(row_idx, col_idx + 1, float(category["annual_budget"]))
            annual_variance_cell = _wc(sheet.cell(row_idx, col_idx + 2, float(category["annual_variance"])))
            annual_signal = _variance_signal(section, float(category["annual_variance"]))
            annual_variance_cell.fill = {
                "positive": positive_fill,
                "negative": negative_fill,
                "neutral": neutral_fill,
            }[annual_signal]
            annual_variance_cell.font = {
                "positive": positive_font,
                "negative": negative_font,
                "neutral": neutral_font,
            }[annual_signal]
        else:
            total_key = "income" if kind == "total_income" else "expense" if kind == "total_expense" else "balance"
            row_fill = (
                income_total_fill
                if kind == "total_income"
                else expense_total_fill if kind == "total_expense" else balance_fill
            )
            title_text = (
                "Subtotal ingresos"
                if kind == "total_income"
                else "Subtotal gastos" if kind == "total_expense" else "Balance"
            )
            period_totals = cast(list[dict[str, Any]], totals[total_key])
            annual_totals = cast(dict[str, Any], totals[f"{total_key}_annual"])
            title_cell = _wc(sheet.cell(row_idx, 1, title_text))
            title_cell.font = section_font
            col_idx = 2
            for period in period_totals:
                sheet.cell(row_idx, col_idx, float(period["real"]))
                sheet.cell(row_idx, col_idx + 1, float(period["budget"]))
                variance_cell = _wc(sheet.cell(row_idx, col_idx + 2, float(period["variance"])))
                signal = _variance_signal(total_key, float(period["variance"]))
                variance_cell.fill = {
                    "positive": positive_fill,
                    "negative": negative_fill,
                    "neutral": neutral_fill,
                }[signal]
                variance_cell.font = {
                    "positive": positive_font,
                    "negative": negative_font,
                    "neutral": neutral_font,
                }[signal]
                col_idx += 3
            sheet.cell(row_idx, col_idx, float(annual_totals["real"]))
            sheet.cell(row_idx, col_idx + 1, float(annual_totals["budget"]))
            annual_variance_cell = _wc(sheet.cell(row_idx, col_idx + 2, float(annual_totals["variance"])))
            annual_signal = _variance_signal(total_key, float(annual_totals["variance"]))
            annual_variance_cell.fill = {
                "positive": positive_fill,
                "negative": negative_fill,
                "neutral": neutral_fill,
            }[annual_signal]
            annual_variance_cell.font = {
                "positive": positive_font,
                "negative": negative_font,
                "neutral": neutral_font,
            }[annual_signal]
            for col_idx in range(1, len(headers) + 1):
                cell = _wc(sheet.cell(row_idx, col_idx))
                if not cell.fill.fill_type:
                    cell.fill = row_fill
                if col_idx != 1 and not cell.font.bold:
                    cell.font = Font(color="F0F3F7", bold=True)

        for col_idx in range(1, len(headers) + 1):
            cell = _wc(sheet.cell(row_idx, col_idx))
            cell.border = thin_border
            if col_idx > 1:
                cell.alignment = Alignment(horizontal="right", vertical="center")
                cell.number_format = "#,##0.00"
        row_idx += 1

    sheet.auto_filter.ref = f"A{header_row}:{get_column_letter(len(headers))}{row_idx - 1}"
    for col_idx in range(1, len(headers) + 1):
        sheet.column_dimensions[get_column_letter(col_idx)].width = 24 if col_idx == 1 else 14

    workbook.save(target)
    return len(structure)


def import_transactions_csv(db: _DatabaseIOProtocol, filepath: str) -> tuple[int, int]:
    """Import transactions from a CSV file. Returns (imported, errors)."""
    imported = 0
    errors = 0
    with open(filepath, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                account_name = (row.get("account_name") or "General").strip() or "General"
                account = db.get_or_create_account(account_name)
                tx_type = row["type"].strip().lower()
                if tx_type not in ("income", "expense"):
                    raise ValueError(f"Invalid type: {tx_type}")
                amount = money_to_decimal(row["amount"])
                if amount is None:
                    raise ValueError("Amount is required")
                if amount <= MONEY_ZERO:
                    raise ValueError("Amount must be positive")
                tx = db.add_transaction(
                    account_id=account["id"],
                    tx_type=tx_type,
                    amount=amount,
                    description=row.get("description") or None,
                    category=row.get("category") or None,
                    subcategory=row.get("subcategory") or None,
                    payment_method=(row.get("payment_method") or "cash"),
                    tx_date=row.get("date") or None,
                    note=row.get("note") or None,
                    receipt_path=row.get("receipt_path") or None,
                )
                tags_str = (row.get("tags") or "").strip()
                if tags_str:
                    tag_ids: list[int] = []
                    for tag_name in tags_str.split(","):
                        tag_name = tag_name.strip()
                        if not tag_name:
                            continue
                        tag = db.get_tag_by_name(tag_name)
                        if tag is None:
                            tag = db.add_tag(tag_name)
                        tag_ids.append(int(tag["id"]))
                    if tag_ids:
                        db.set_transaction_tags(int(tx["id"]), tag_ids)
                imported += 1
            except _CSV_IMPORT_ROW_ERRORS as exc:
                logger.warning("CSV import error on row %r: %s", row, exc)
                errors += 1
    return imported, errors
