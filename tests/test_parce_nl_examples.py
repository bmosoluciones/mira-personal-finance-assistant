# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Regression tests for parsing natural-language examples from nl_examples.csv."""

from __future__ import annotations

import csv
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from mira.ai.parser_engine import TransactionParserEngine
from mira.ai.pipeline import Pipeline
from mira.ai.validator import validate
from mira.db.database import Database

_NL_EXAMPLES_PATH = Path(__file__).resolve().parents[1] / "src" / "mira" / "ai" / "nl_examples.csv"


def _system_default_currency() -> str:
    with tempfile.TemporaryDirectory() as tmp_dir:
        db = Database(path=Path(tmp_dir) / "parse_nl_examples.db")
        db.connect()
        try:
            return db.setting.get_default_currency()
        finally:
            db.close()


DEFAULT_CURRENCY = _system_default_currency()


def _to_float(raw: str | None) -> float | None:
    value = str(raw or "").strip()
    if not value:
        return None
    return float(value.replace(",", "."))


def _to_decimal(raw: str | None) -> Decimal | None:
    value = str(raw or "").strip()
    if not value:
        return None
    return Decimal(value.replace(",", ".")).quantize(Decimal("0.01"))


def _to_list(raw: str | None) -> list[str] | None:
    value = str(raw or "").strip()
    if not value:
        return None
    return [item.strip() for item in value.split("|") if item.strip()] or None


def _load_examples_from_csv() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    with _NL_EXAMPLES_PATH.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            text = str(row.get("Frase") or "").strip()
            action = str(row.get("Accion") or "").strip()
            if not text or not action:
                continue
            rows.append(
                {
                    "text": text,
                    "action": action,
                    "amount": _to_float(row.get("Cantidad")),
                    "amount_decimal": _to_decimal(row.get("Cantidad")),
                    "currency": str(row.get("Moneda") or "").strip().upper() or None,
                    "category": str(row.get("Categoria") or "").strip().lower() or None,
                    "account": str(row.get("Cuenta") or "").strip() or None,
                    "exchange_rate": _to_float(row.get("TipoCambio")),
                    "converted_amount": _to_float(row.get("CantidadConvertida")),
                    "converted_amount_decimal": _to_decimal(row.get("CantidadConvertida")),
                    "report_type": str(row.get("TipoReporte") or "").strip() or None,
                    "period": {
                        "preset": str(row.get("PeriodoPreset") or "").strip() or None,
                        "from": str(row.get("PeriodoFrom") or "").strip() or None,
                        "to": str(row.get("PeriodoTo") or "").strip() or None,
                    },
                    "filters": {
                        "categories": _to_list(row.get("CategoriasFiltro")),
                        "accounts": _to_list(row.get("CuentasFiltro")),
                        "min_amount": _to_float(row.get("MontoMin")),
                        "min_amount_decimal": _to_decimal(row.get("MontoMin")),
                        "max_amount": _to_float(row.get("MontoMax")),
                        "max_amount_decimal": _to_decimal(row.get("MontoMax")),
                        "text": str(row.get("TextoFiltro") or "").strip() or None,
                    },
                }
            )

    return rows


def _assert_filters(actual: dict[str, Any] | None, expected: dict[str, Any]) -> None:
    expected_has_data = any(value is not None for value in expected.values())
    if not expected_has_data:
        assert actual is None
        return

    assert actual is not None
    assert actual.get("categories") == expected["categories"]
    assert actual.get("accounts") == expected["accounts"]
    assert (
        actual.get("min_amount") == expected["min_amount_decimal"]
        if expected["min_amount_decimal"] is not None
        else actual.get("min_amount") is None
    )
    assert (
        actual.get("max_amount") == expected["max_amount_decimal"]
        if expected["max_amount_decimal"] is not None
        else actual.get("max_amount") is None
    )
    assert actual.get("text") == expected["text"]


def _assert_period(actual: dict[str, Any] | None, expected: dict[str, Any]) -> None:
    expected_has_data = any(value is not None for value in expected.values())
    if not expected_has_data:
        assert actual is None
        return

    assert actual is not None
    assert actual.get("preset") == expected["preset"]
    assert actual.get("from") == expected["from"]
    assert actual.get("to") == expected["to"]


def _monetary_example_chunk(chunk_name: str) -> list[dict[str, Any]]:
    monetary_rows = [row for row in _load_examples_from_csv() if row["action"] in {"add_income", "add_expense"}]
    total = len(monetary_rows)
    window = min(60, total)
    if chunk_name == "head":
        return monetary_rows[:window]
    if chunk_name == "middle":
        start = max(0, (total // 2) - (window // 2))
        return monetary_rows[start : start + window]
    if chunk_name == "tail":
        return monetary_rows[max(0, total - window) :]
    raise ValueError(f"Unsupported chunk: {chunk_name}")


def test_parce_nl_examples_business_fields_regression() -> None:
    parser = TransactionParserEngine()

    for row in _load_examples_from_csv():
        raw = parser.parse(row["text"])
        result = validate(raw, default_base_currency=DEFAULT_CURRENCY)
        assert result.valid, f"{row['text']}: {result.error}"
        assert result.action is not None

        action_json = result.action
        assert action_json["action"] == row["action"], row["text"]

        if row["amount_decimal"] is not None:
            assert action_json["amount"] == row["amount_decimal"], row["text"]
        if row["currency"] is not None:
            assert action_json["base_currency"] == row["currency"], row["text"]
        if row["category"] is not None:
            assert action_json["category"] == row["category"], row["text"]
        if row["account"] is not None:
            assert action_json["account"] == row["account"], row["text"]
        if row["exchange_rate"] is not None:
            assert action_json["exchange_rate"] == pytest.approx(row["exchange_rate"]), row["text"]
        if row["converted_amount_decimal"] is not None:
            assert action_json["converted_amount"] == row["converted_amount_decimal"], row["text"]
        if row["report_type"] is not None:
            assert action_json["report_type"] == row["report_type"], row["text"]

        _assert_period(action_json.get("period"), row["period"])
        _assert_filters(action_json.get("filters"), row["filters"])


def test_parce_nl_examples_missing_amount_expense_asks_amount_and_currency() -> None:
    raw = TransactionParserEngine().parse("gasté en comida")
    assert raw["action"] == "none"
    msg = str(raw.get("message") or "").lower()
    assert "monto" in msg
    assert "moneda" in msg


def test_parce_nl_examples_missing_amount_income_asks_amount_and_currency() -> None:
    raw = TransactionParserEngine().parse("recibí salario")
    assert raw["action"] == "none"
    msg = str(raw.get("message") or "").lower()
    assert "monto" in msg
    assert "moneda" in msg


@pytest.mark.full
@pytest.mark.parametrize("chunk_name", ["head", "middle", "tail"])
def test_parce_nl_examples_create_transactions_end_to_end(tmp_path: Path, chunk_name: str) -> None:
    monetary_rows = _monetary_example_chunk(chunk_name)

    for index, row in enumerate(monetary_rows):
        db = Database(path=tmp_path / f"parse_nl_examples_full_{chunk_name}_{index}.db")
        db.connect()
        try:
            pipeline = Pipeline(db=db, engine=TransactionParserEngine())
            result = pipeline.process(row["text"])
            assert result.success is True, row["text"]
            assert result.action == row["action"], row["text"]

            current_transactions = db.transaction.list(limit=1_000_000)
            assert len(current_transactions) == 1, row["text"]

            tx = current_transactions[0]
            expected_amount = row["converted_amount_decimal"] or row["amount_decimal"]
            assert tx["amount"] == expected_amount, row["text"]
            assert tx["type"] == ("income" if row["action"] == "add_income" else "expense"), row["text"]
            if row["exchange_rate"] is not None:
                assert float(tx.get("exchange_rate") or 0.0) == pytest.approx(row["exchange_rate"]), row["text"]
            if row["converted_amount_decimal"] is not None:
                assert tx["converted_amount"] == row["converted_amount_decimal"], row["text"]
        finally:
            db.close()
