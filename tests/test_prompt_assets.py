# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Tests for parser prompt assets and exact-example lookups."""

from __future__ import annotations

import csv
from pathlib import Path

from mira.ai import prompt_assets as prompt_assets_module
from mira.ai.prompt_assets import PromptAssets


def test_build_parser_prompt_includes_system_prompt_examples_and_user_input() -> None:
    prompt = PromptAssets().build_parser_prompt("show me my expenses")

    assert prompt.startswith(prompt_assets_module._SYSTEM_PROMPT)
    assert "User: I received my salary of 3000" in prompt
    assert "User: show me my expenses" in prompt
    assert prompt.endswith("Assistant:")


def test_get_exact_action_returns_copy(monkeypatch) -> None:
    stored = {"hello": {"action": "none", "message": "hi"}}
    monkeypatch.setattr(
        prompt_assets_module,
        "_load_exact_example_actions",
        lambda: stored,
    )

    assets = PromptAssets()
    action = assets.get_exact_action("hello")

    assert action == {"action": "none", "message": "hi"}
    assert action is not stored["hello"]


def test_exact_example_helpers_parse_numbers_lists_and_normalized_lookup(monkeypatch) -> None:
    assert prompt_assets_module._parse_example_float("12,5") == 12.5
    assert prompt_assets_module._parse_example_float("oops") is None
    assert prompt_assets_module._parse_example_list("food | rent | ") == ["food", "rent"]
    assert prompt_assets_module._parse_example_list("") is None

    monkeypatch.setattr(
        prompt_assets_module,
        "_load_exact_example_actions",
        lambda: {"hello world": {"action": "none", "message": "ok"}},
    )

    assert PromptAssets().get_exact_action("  HeLLo   WORLD  ") == {"action": "none", "message": "ok"}


def test_load_exact_example_actions_parses_csv_filters_and_defaults(monkeypatch, tmp_path: Path) -> None:
    csv_path = tmp_path / "nl_examples.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "Frase",
                "Tipo",
                "Accion",
                "Cantidad",
                "Moneda",
                "Categoria",
                "Cuenta",
                "TipoCambio",
                "CantidadConvertida",
                "TipoReporte",
                "PeriodoPreset",
                "PeriodoFrom",
                "PeriodoTo",
                "CategoriasFiltro",
                "CuentasFiltro",
                "MontoMin",
                "MontoMax",
                "TextoFiltro",
                "Mensaje",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "Frase": "  Pague 12,5 de cafe  ",
                "Tipo": "gasto",
                "Cantidad": "12,5",
                "Moneda": "usd",
                "Categoria": "Food",
            }
        )
        writer.writerow(
            {
                "Frase": "Resumen del ultimo mes",
                "Tipo": "consulta",
                "Accion": "report",
                "TipoReporte": "expenses",
                "PeriodoPreset": "last_month",
                "CategoriasFiltro": "food|transport",
                "CuentasFiltro": "cash|card",
                "MontoMin": "10",
                "MontoMax": "30",
                "TextoFiltro": "uber",
                "Mensaje": "listo",
            }
        )

    monkeypatch.setattr(prompt_assets_module, "__file__", str(tmp_path / "prompt_assets.py"))
    prompt_assets_module._load_exact_example_actions.cache_clear()
    try:
        actions = prompt_assets_module._load_exact_example_actions()
    finally:
        prompt_assets_module._load_exact_example_actions.cache_clear()

    expense = actions[prompt_assets_module._normalize_exact_example_key("Pague 12,5 de cafe")]
    report = actions[prompt_assets_module._normalize_exact_example_key("Resumen del ultimo mes")]

    assert expense == {
        "action": "add_expense",
        "amount": 12.5,
        "description": "Pague 12,5 de cafe",
        "category": "food",
        "account": None,
        "base_currency": "USD",
        "exchange_rate": 1.0,
        "converted_amount": 12.5,
        "report_type": None,
        "period": None,
        "filters": None,
        "message": None,
    }
    assert report["period"] == {"preset": "last_month", "from": None, "to": None}
    assert report["filters"] == {
        "categories": ["food", "transport"],
        "accounts": ["cash", "card"],
        "min_amount": 10.0,
        "max_amount": 30.0,
        "text": "uber",
    }
    assert report["message"] == "listo"
