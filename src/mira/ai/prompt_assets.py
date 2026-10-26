# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Exact-example lookup for the deterministic transaction parser."""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Any

from mira.ai.normalizer import normalise


def _normalize_exact_example_key(text: str) -> str:
    """Return normalize exact example key."""
    return " ".join(text.strip().casefold().split())


def _normalize_pipeline_exact_example_key(text: str) -> str:
    """Return normalize pipeline exact example key."""
    normalized = normalise(text)
    return " ".join(normalized.strip().casefold().split())


def _parse_example_float(raw: str | None) -> float | None:
    """Return parse example float."""
    value = str(raw or "").strip()
    if not value:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def _parse_example_list(raw: str | None) -> list[str] | None:
    """Return parse example list."""
    value = str(raw or "").strip()
    if not value:
        return None
    return [item.strip() for item in value.split("|") if item.strip()] or None


@lru_cache(maxsize=1)
def _load_exact_example_action_maps() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Return load exact example action maps."""
    examples_path = Path(__file__).with_name("nl_examples.csv")
    if not examples_path.is_file():
        return {}, {}

    exact_actions: dict[str, dict[str, Any]] = {}
    pipeline_actions: dict[str, dict[str, Any]] = {}
    with examples_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            text = str(row.get("Frase") or "").strip()
            label = str(row.get("Tipo") or "").strip().lower()
            action = str(row.get("Accion") or "").strip() or None
            amount = _parse_example_float(row.get("Cantidad"))
            currency = str(row.get("Moneda") or "").strip().upper() or None
            category = str(row.get("Categoria") or "").strip().lower() or None
            account = str(row.get("Cuenta") or "").strip() or None
            exchange_rate = _parse_example_float(row.get("TipoCambio"))
            converted_amount = _parse_example_float(row.get("CantidadConvertida"))
            report_type = str(row.get("TipoReporte") or "").strip() or None
            period_preset = str(row.get("PeriodoPreset") or "").strip() or None
            period_from = str(row.get("PeriodoFrom") or "").strip() or None
            period_to = str(row.get("PeriodoTo") or "").strip() or None
            categories_filter = _parse_example_list(row.get("CategoriasFiltro"))
            accounts_filter = _parse_example_list(row.get("CuentasFiltro"))
            min_amount = _parse_example_float(row.get("MontoMin"))
            max_amount = _parse_example_float(row.get("MontoMax"))
            text_filter = str(row.get("TextoFiltro") or "").strip() or None
            message = str(row.get("Mensaje") or "").strip() or None

            if not text:
                continue

            if action is None:
                if label in {"gasto", "expense"}:
                    action = "add_expense"
                elif label in {"ingreso", "income"}:
                    action = "add_income"
                else:
                    continue

            if exchange_rate is None and action in {"add_income", "add_expense"} and amount is not None:
                exchange_rate = 1.0
            if converted_amount is None and amount is not None:
                if exchange_rate is not None:
                    converted_amount = round(amount * exchange_rate, 2)
                elif action in {"add_income", "add_expense"}:
                    converted_amount = amount

            filters = None
            if (
                categories_filter is not None
                or accounts_filter is not None
                or min_amount is not None
                or max_amount is not None
                or text_filter is not None
            ):
                filters = {
                    "categories": categories_filter,
                    "accounts": accounts_filter,
                    "min_amount": min_amount,
                    "max_amount": max_amount,
                    "text": text_filter,
                }

            period = None
            if period_preset or period_from or period_to:
                period = {"preset": period_preset, "from": period_from, "to": period_to}

            action_payload = {
                "action": action,
                "amount": amount,
                "description": text if action in {"add_income", "add_expense"} else None,
                "category": category,
                "account": account,
                "base_currency": currency,
                "exchange_rate": exchange_rate,
                "converted_amount": converted_amount,
                "report_type": report_type,
                "period": period,
                "filters": filters,
                "message": message,
            }
            exact_actions[_normalize_exact_example_key(text)] = action_payload
            # Multiple different phrases can collapse to the same normalized key.
            # Keep the first-seen mapping to avoid non-deterministic overwrites.
            pipeline_actions.setdefault(_normalize_pipeline_exact_example_key(text), dict(action_payload))
    return exact_actions, pipeline_actions


def _load_exact_example_actions() -> dict[str, dict[str, Any]]:
    """Return load exact example actions."""
    return _load_exact_example_action_maps()[0]


def _load_pipeline_exact_example_actions() -> dict[str, dict[str, Any]]:
    """Return load pipeline exact example actions."""
    return _load_exact_example_action_maps()[1]


def _clear_exact_example_action_caches() -> None:
    """Return clear exact example action caches."""
    _load_exact_example_action_maps.cache_clear()


_load_exact_example_actions.cache_clear = _clear_exact_example_action_caches  # type: ignore[attr-defined]
_load_pipeline_exact_example_actions.cache_clear = _clear_exact_example_action_caches  # type: ignore[attr-defined]


def _exact_example_action(user_input: str) -> dict[str, Any] | None:
    """Return exact example action."""
    exact_actions = _load_exact_example_actions()
    action = exact_actions.get(_normalize_exact_example_key(user_input))
    if action is None:
        pipeline_actions = _load_pipeline_exact_example_actions()
        action = pipeline_actions.get(_normalize_pipeline_exact_example_key(user_input))
    if action is None:
        return None
    return dict(action)


class PromptAssets:
    """Exact-example provider for the deterministic parser."""

    def get_exact_action(self, user_input: str) -> dict[str, Any] | None:
        """Return get exact action."""
        return _exact_example_action(user_input)
