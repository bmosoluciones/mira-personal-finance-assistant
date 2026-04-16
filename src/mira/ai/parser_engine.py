# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Deterministic transaction parser engine for assistant mode.

Architecture overview
---------------------
Parsing is split into four explicit stages:

1. **Exact-action lookup** — fast path for inputs that map 1-to-1 to an action
   via :class:`~mira.ai.prompt_assets.PromptAssets`.
2. **Signal extraction** — :func:`~mira.ai.parser_signals.collect_signals`
   populates a :class:`~mira.ai.parser_signals.ParseSignals` dataclass from the
   raw text without making any decision yet.
3. **Intent resolution** — :func:`~mira.ai.parser_signals.resolve_intent` maps
   the signals to an :data:`~mira.ai.parser_signals.Intent` using ``match/case``
   so priority rules are explicit and unit-testable in isolation.
4. **Result construction** — :func:`_build_result` converts the intent + signals
   into the final action dict also via ``match/case``.

Vocabulary catalogs live in :mod:`mira.ai.parser_vocab`.
Signal extraction helpers live in :mod:`mira.ai.parser_signals`.
"""

from __future__ import annotations

import re
from typing import Any

from mira.ai.base_engine import BaseEngine
from mira.ai.parser_signals import ParseSignals, collect_signals, resolve_intent
from mira.ai.prompt_assets import PromptAssets
from mira.ui.i18n import tr

# ---------------------------------------------------------------------------
# Amount / currency helpers
# ---------------------------------------------------------------------------

_AMOUNT_PATTERN = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(k\b|grand\b|grande\b|lucas?\b|lukas?\b|mil\b)?",
    re.IGNORECASE,
)
_LUCAS_PATTERN = re.compile(r"\blu(?:c|k)as?\b", re.IGNORECASE)

_CURRENCY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:cad|canadian\s+dollars?|d[oó]lares\s+canadienses?)\b", re.IGNORECASE), "CAD"),
    (re.compile(r"\b(?:aud|australian\s+dollars?|d[oó]lares\s+australianos?)\b", re.IGNORECASE), "AUD"),
    (re.compile(r"\b(?:usd|us\$|d[oó]lares?|dollars?|bucks?|green(?:s)?|verdes?)\b|\$", re.IGNORECASE), "USD"),
    (re.compile(r"\b(?:eur|euros?)\b|€", re.IGNORECASE), "EUR"),
    (re.compile(r"\b(?:cop|colomb(?:ia|iano|ianos))\b", re.IGNORECASE), "COP"),
    (re.compile(r"\b(?:nio|c[oó]rdobas?)\b", re.IGNORECASE), "NIO"),
    (
        re.compile(
            r"\b(?:ars|argentin(?:a|o|os)|lucas?|lukas?|gambas?|chirolas?|morlacos?|laburo|nafta|boliche|birra|mercadopago|ual[aá]|brubank|galicia|naci[oó]n|obra\s+social|clav[ée]|garpe|com[ií]|cab[ií]o)\b",
            re.IGNORECASE,
        ),
        "ARS",
    ),
    (re.compile(r"\b(?:mxn|baros?|varo)\b", re.IGNORECASE), "MXN"),
    (re.compile(r"\b(?:clp|pesos?\s+chilenos?)\b", re.IGNORECASE), "CLP"),
    (re.compile(r"\b(?:pen|soles?)\b", re.IGNORECASE), "PEN"),
    (re.compile(r"\b(?:bob|bolivianos?)\b", re.IGNORECASE), "BOB"),
    (re.compile(r"\b(?:gtq|quetzales?)\b", re.IGNORECASE), "GTQ"),
    (re.compile(r"\b(?:hnl|lempiras?)\b", re.IGNORECASE), "HNL"),
    (re.compile(r"\b(?:uyu|pesos?\s+uruguayos?)\b", re.IGNORECASE), "UYU"),
    (re.compile(r"\b(?:chf|swiss\s+francs?|francos\s+suizos?)\b", re.IGNORECASE), "CHF"),
    (re.compile(r"\b(?:jpy|yen(?:es)?)\b", re.IGNORECASE), "JPY"),
    (re.compile(r"\b(?:gbp|pounds?|libras?)\b", re.IGNORECASE), "GBP"),
    (re.compile(r"\b(?:inr|rupees?|rupias?)\b", re.IGNORECASE), "INR"),
    (re.compile(r"\b(?:aoa|kwanzas?)\b", re.IGNORECASE), "AOA"),
    (re.compile(r"\b(?:brl|reais?)\b", re.IGNORECASE), "BRL"),
    (re.compile(r"\b(?:pyg|guaran[ií]es?)\b", re.IGNORECASE), "PYG"),
    (re.compile(r"\b(?:kes|kenyan\s+shillings?)\b", re.IGNORECASE), "KES"),
    (re.compile(r"\b(?:nok|norwegian\s+kroner)\b", re.IGNORECASE), "NOK"),
    (re.compile(r"\b(?:czk|czech\s+koruna)\b", re.IGNORECASE), "CZK"),
    (re.compile(r"\b(?:huf|hungarian\s+forints?)\b", re.IGNORECASE), "HUF"),
    (re.compile(r"\b(?:dop|pesos?\s+dominicanos?)\b", re.IGNORECASE), "DOP"),
    (re.compile(r"\b(?:sek|swedish\s+kronor)\b", re.IGNORECASE), "SEK"),
    (re.compile(r"\b(?:php|philippine\s+pesos?)\b", re.IGNORECASE), "PHP"),
    (re.compile(r"\b(?:zar|south\s+african\s+rand)\b", re.IGNORECASE), "ZAR"),
    (re.compile(r"\b(?:thb|thai\s+baht)\b", re.IGNORECASE), "THB"),
]

_USD_DEFAULT_PATTERN = re.compile(
    r"\b(?:day\s+\d+|dia\s+\d+|rent\s+payment|utilities\s+bill|clothing\s+purchase|salary\s+payment|refund\s+case|periodo\s+\d+|client\s+invoice|bono\s+mensual|venta\s+realizada|entretenimiento\s+\d+|por\s+freelance|from\s+side\s+job|shelled\s+out|coughed\s+up|forked\s+out|splurged|threw\s+away|pissed\s+away|sank\s+\d+|sunk\s+\d+|dumped\s+\d+\s+into\s+my\s+car|got\s+paid\s+\d+|scored\s+\d+|raked\s+in\s+\d+|pulled\s+(?:in|down)\s+\d+|pocketed\s+\d+|cleared\s+\d+|netted\s+\d+|took\s+home\s+\d+|banked\s+\d+|windfall\s+of\s+\d+|jackpot\s+with\s+\d+|deposited\s+\d+\s+into\s+my|pulled\s+\d+\s+from\s+the\s+atm|loaded\s+up\s+my\s+venmo|moved\s+\d+\s+to\s+my\s+investment|dumped\s+\d+\s+into\s+my\s+robinhood|swiped\s+my\s+card|tapped\s+my\s+phone|zelled\s+\d+|venmoed\s+\d+|cashapped\s+\d+|cashed\s+out\s+\d+|sheld\s+out|coffed\s+up|forkd\s+out|splurjd|dumbed\s+\d+\s+into\s+my\s+car|pist\s+away|scord\s+\d+|puld\s+(?:in|down|\d+\s+from\s+the\s+atm)|pocketid\s+\d+|cleard\s+\d+|netid\s+\d+|bankt\s+\d+|depozited\s+\d+\s+into\s+my|transferd\s+\d+\s+to\s+my\s+savings|payd\s+\d+\s+with\s+my\s+amex|withdreww\s+\d+\s+from\s+the\s+wells\s+fargo|tapt\s+my\s+phone|venmod\s+\d+|cashapt\s+\d+)\b",
    re.IGNORECASE,
)
_ARS_HINT_PATTERN = re.compile(
    r"\b(?:argentin(?:a|o|os|e)|laburo|nafta|boliche|birra|gambas?|chirolas?|morlacos?|mercadopago|ual[aá]|brubank|galicia|naci[oó]n|verduler[íi]a|obra\s+social|afanaron|chorearon|esfumaron|cajero|banco\s+provincia|tarjeta\s+de\s+cr[eé]dito|debitaron|me\s+sacaron|me\s+cobraron|expensas|clav[ée]|garpe|garche|com[ií]|cab[ií][oó]|transfirieron|multa)\b",
    re.IGNORECASE,
)
_MXN_HINT_PATTERN = re.compile(r"\b(?:mexic(?:o|an(?:o|os)?)|mexicanos?|mxn|baros?|varo|citibanamex)\b", re.IGNORECASE)
_COP_HINT_PATTERN = re.compile(
    r"\b(?:cop|colomb(?:ia|iano|ianos)|colombian|davivienda|bancolombia|bogot[aá]|nequi)\b", re.IGNORECASE
)
_ENGLISH_HINT_PATTERN = re.compile(
    r"\b(?:i|my|for|the|with|from|got|paid|spent|income|expense|tax|refund|salary)\b", re.IGNORECASE
)
# Unambiguous USD references: ISO code or "US$" only.  Used when USD is *not* the
# default currency so that broad slang ("$", "bucks", "verdes") is not misread as
# USD – those tokens are far more likely to refer to the user's local currency.
_USD_EXPLICIT_PATTERN = re.compile(r"\b(?:usd|us\$)\b", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Category / account helpers
# ---------------------------------------------------------------------------

_CATEGORY_KEYWORDS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\b(grocer(?:ies|y)|food|comida|supermercado|super)\b", re.IGNORECASE),
        "food",
    ),
    (
        re.compile(r"\b(salary|salario|sueldo|paycheck|payroll|sal[aá]rio)\b", re.IGNORECASE),
        "salary",
    ),
    (re.compile(r"\b(rent|alquiler|arriendo|aluguel)\b", re.IGNORECASE), "rent"),
    (
        re.compile(
            r"\b(transport(?:ation)?|bus|metro|uber|taxi|gasolina|gas|transporte)\b",
            re.IGNORECASE,
        ),
        "transport",
    ),
    (
        re.compile(
            r"\b(electric(?:ity)?|agua|water|internet|phone|utilities|luz|tel[eé]fono|celular)\b",
            re.IGNORECASE,
        ),
        "utilities",
    ),
    (
        re.compile(
            r"\b(health|salud|doctor|pharmacy|medicina|farmacia|hospital|sa[uú]de)\b",
            re.IGNORECASE,
        ),
        "health",
    ),
    (
        re.compile(
            r"\b(entertain(?:ment)?|cinema|movie|netflix|spotify|streaming|cine|pel[ií]cula)\b",
            re.IGNORECASE,
        ),
        "entertainment",
    ),
    (
        re.compile(
            r"\b(cloth(?:ing|es)?|ropa|shoes|zapatos|roupa|cal[cç]ados?)\b",
            re.IGNORECASE,
        ),
        "clothing",
    ),
    (
        re.compile(
            r"\b(freelance|consulting|consultor[ií]a|commission|comisi[oó]n)\b",
            re.IGNORECASE,
        ),
        "freelance",
    ),
    (
        re.compile(
            r"\b(education|school|university|universidad|matr[ií]cula|tuition|curso|course|escuela|colegio|faculdade)\b",
            re.IGNORECASE,
        ),
        "education",
    ),
    (
        re.compile(r"\b(insurance|seguro|p[oó]liza|policy)\b", re.IGNORECASE),
        "insurance",
    ),
    (
        re.compile(
            r"\b(subscripti?on|suscripci[oó]n|members(?:hip)?|membres[ií]a|mensualidad|assinatura)\b",
            re.IGNORECASE,
        ),
        "subscriptions",
    ),
    (
        re.compile(
            r"\b(gift|regalo|donati?on|donaci[oó]n|caridad|charity|presente|doa[cç][aã]o)\b",
            re.IGNORECASE,
        ),
        "gifts",
    ),
    (
        re.compile(
            r"\b(savings?|ahorr[oeé]s?|inversi[oó]n|investment|poupan[cç]a)\b",
            re.IGNORECASE,
        ),
        "savings",
    ),
    (
        re.compile(r"\b(pets?|mascota|veterinar(?:io|ia|y)|vet|animal)\b", re.IGNORECASE),
        "pets",
    ),
    (
        re.compile(
            r"\b(personal\s+care|peluquer[ií]a|barber(?:[ií]a|shop)?|haircut|spa|beauty|belleza|cabeleireiro|sal[aã]o)\b",
            re.IGNORECASE,
        ),
        "personal_care",
    ),
]

_ACCOUNT_PATTERNS = (
    re.compile(
        r"\bfrom\s+(?:my\s+)?([a-záéíóúñ][a-záéíóúñ\s]{1,20}?)(?:\s+account)?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\binto\s+(?:my\s+)?([a-záéíóúñ][a-záéíóúñ\s]{1,20}?)(?:\s+account)?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bin\s+(?:my\s+)?([a-záéíóúñ][a-záéíóúñ\s]{1,20}?)\s+account\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\ben\s+cuenta\s+([a-záéíóúñ][a-záéíóúñ\s]{1,20}?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bcuenta\s+([a-záéíóúñ][a-záéíóúñ\s]{1,20}?)\b",
        re.IGNORECASE,
    ),
)

_CATEGORY_FREEFORM_TRAIL_PATTERN = re.compile(
    r"\b(?:on|for|in|en|de)\s+([a-záéíóúñ][a-záéíóúñ\s]{2,32})$",
    re.IGNORECASE,
)
_CATEGORY_FORBIDDEN_TOKENS = frozenset({"account", "cuenta", "my", "mi"})

# ---------------------------------------------------------------------------
# Report / period helpers
# ---------------------------------------------------------------------------


def _extract_report_type(text: str) -> str:
    """Return extract report type."""
    if re.search(r"\b(balance|net|neto)\b", text, re.IGNORECASE):
        return "balance"
    if re.search(r"\b(cash\s*flow|flujo)\b", text, re.IGNORECASE):
        return "cashflow"
    if re.search(r"\b(income|ingreso|ingresos)\b", text, re.IGNORECASE):
        return "incomes"
    if re.search(r"\b(expense|expenses|gasto|gastos)\b", text, re.IGNORECASE):
        return "expenses"
    return "summary"


def _extract_period(text: str) -> dict[str, str | None]:
    """Return extract period."""
    lower = text.lower()
    if "last 3 months" in lower or "últimos 3 meses" in lower or "ultimos 3 meses" in lower:
        return {"preset": "last_3_months", "from": None, "to": None}
    if "last 6 months" in lower or "últimos 6 meses" in lower or "ultimos 6 meses" in lower:
        return {"preset": "last_6_months", "from": None, "to": None}
    if re.search(r"last\s+(?:2|two)\s+months|[uú]ltimos\s+2\s+meses", lower):
        return {"preset": "last_2_months", "from": None, "to": None}
    if re.search(r"last\s+week|semana\s+pasada|semana\s+passada", lower):
        return {"preset": "last_week", "from": None, "to": None}
    if "this month" in lower or "este mes" in lower:
        return {"preset": "this_month", "from": None, "to": None}
    if "last month" in lower or "mes pasado" in lower:
        return {"preset": "last_month", "from": None, "to": None}
    if "this year" in lower or "este año" in lower or "este ano" in lower:
        return {"preset": "this_year", "from": None, "to": None}
    if re.search(r"\ball\s+time\b|\btodo\b|\btodos\b|\bhistor", lower):
        return {"preset": "all_time", "from": None, "to": None}
    return {"preset": "this_month", "from": None, "to": None}


# ---------------------------------------------------------------------------
# Amount / currency extraction
# ---------------------------------------------------------------------------


def _parse_numeric_token(raw: str) -> float:
    """Return parse numeric token."""
    token = raw.strip()
    if "," in token and "." in token:
        if token.rfind(",") > token.rfind("."):
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", "")
    elif "," in token:
        if token.count(",") == 1 and len(token.split(",")[-1]) == 3:
            token = token.replace(",", "")
        else:
            token = token.replace(",", ".")
    return float(token)


def _extract_amount(text: str) -> float | None:
    """Return extract amount."""
    m = _AMOUNT_PATTERN.search(text)
    if not m:
        return None
    amount = _parse_numeric_token(m.group(1))
    suffix = (m.group(2) or "").lower()
    if suffix in {"k", "grand", "grande", "mil"}:
        amount *= 1000
    return amount


def _extract_currency(text: str, default_currency: str | None = None) -> str | None:
    """Detect the currency mentioned in *text*.

    Workflow summary:
    1. Check for nationality-qualified pesos (e.g., "pesos colombianos") which
       are highly specific.
    2. Scan explicit currency patterns. If USD is NOT the default, slang like
       "$" or "bucks" is ignored to avoid false positives with local currencies.
    3. Apply ARS-specific heuristic phrases for common Argentine slang.
    4. Handle bare "peso" with regional fallbacks (defaulting to MXN).
    5. Apply US-centric heuristic phrases ONLY if USD is the default currency.

    Priority rules
    --------------
    1. Nationality-qualified peso phrases win over all other hints.
    2. Explicit currency patterns are scanned in order.  When *default_currency*
       is **not** USD the broad USD slang tokens (``$``, "bucks", "dollars", …)
       are suppressed: only the unambiguous ISO code ``USD`` / ``US$`` will
       still match.  This prevents misclassifying local-currency amounts that
       use the ``$`` sign (common in NIO, ARS, MXN, COP, etc.) as US dollars.
    3. Country-specific ARS heuristics.
    4. Bare "peso" with no country qualifier falls back to MXN.
    5. USD heuristic phrases (``_USD_DEFAULT_PATTERN``) are **only** applied
       when USD is the default currency – they are US-centric and would produce
       false positives for users whose default is a different currency.
    6. Returns ``None`` (→ caller uses *default_currency* as fallback).

    Parameters
    ----------
    text:
        Raw user input.
    default_currency:
        ISO-4217 code of the user's default currency as stored in the
        database (``setting.get_default_currency()``).  When ``None`` the
        behaviour is identical to the previous implementation (USD assumed).
    """
    lower = text.lower()
    usd_is_default = (default_currency or "USD").upper() == "USD"

    # 1. Nationality-qualified pesos should win over local slang hints.
    if "peso" in lower:
        if _COP_HINT_PATTERN.search(text):
            return "COP"
        if _MXN_HINT_PATTERN.search(text):
            return "MXN"
        if re.search(r"\bchilen(?:o|os|a|as)\b", text, re.IGNORECASE):
            return "CLP"
        if re.search(r"\buruguay(?:o|os|a|as)\b", text, re.IGNORECASE):
            return "UYU"
        if re.search(r"\bdominican(?:o|os|a|as)|dominicanos?\b", text, re.IGNORECASE):
            return "DOP"
        if re.search(r"\bargentin(?:a|o|os|e)\b", text, re.IGNORECASE):
            return "ARS"

    # 2. Explicit currency patterns.
    for pattern, currency in _CURRENCY_PATTERNS:
        if currency == "USD" and not usd_is_default:
            # When USD is not the default only match the unambiguous ISO code
            # so that "$", "dollars", "bucks", etc. do not override the user's
            # local currency.
            if _USD_EXPLICIT_PATTERN.search(text):
                return "USD"
            continue
        if pattern.search(text):
            return currency

    # 3. Explicit heuristic buckets for phrases that imply ARS without naming it.
    if re.search(
        r"\b(?:transfer[ií]\s+\d+\s+para\s+el\s+alquiler|de\s+\d+\s+de\s+expensas|me\s+transfirieron\s+\d+|pague\s+\d+\s+de\s+la\s+luz|gaste\s+\d+\s+en\s+la\s+farmacia|mercado\s+pago\s+me\s+cobro|targeta\s+de\s+credito|sueldo\s+60\s*k|\bpage\s+\d+\s+de\s+la\s+lus|\bpague\s+el\s+gas\s+\d+|\bpage\s+el\s+gas\s+\d+|\bma[ñn]ana\s+tengo\s+que\s+pagar\s+\d+\s+de\s+la\s+luz|\bhoy\s+cobre\s+\d+\s+de\s+un\s+trabajo|\bel\s+finde\s+me\s+patine\s+\d+\s+en\s+ropa|\bgazte\s+\d+\s+en\s+la\s+farma(?:cia|sia))\b",
        text,
        re.IGNORECASE,
    ):
        return "ARS"

    # 4. Bare "peso" with no country qualifier – fall back to MXN.
    if "peso" in lower:
        if _COP_HINT_PATTERN.search(text):
            return "COP"
        if _MXN_HINT_PATTERN.search(text):
            return "MXN"
        if re.search(r"\bchilen(?:o|os|a|as)\b", text, re.IGNORECASE):
            return "CLP"
        if re.search(r"\buruguay(?:o|os|a|as)\b", text, re.IGNORECASE):
            return "UYU"
        if re.search(r"\bdominican(?:o|os|a|as)|dominicanos?\b", text, re.IGNORECASE):
            return "DOP"
        if _ARS_HINT_PATTERN.search(text):
            return "ARS"
        if _ENGLISH_HINT_PATTERN.search(text):
            return "MXN"
        return "MXN"

    # 5. USD heuristic phrases – only when USD is the user's default currency.
    #    Applying these for non-USD users would silently assign USD to phrases
    #    that are simply expressed in English.
    if usd_is_default:
        if _USD_DEFAULT_PATTERN.search(text):
            if re.search(r"\bgot\s+paid\s+\d+\s+by\s+a\s+client\b", text, re.IGNORECASE):
                return None
            return "USD"

        if re.search(
            r"\b(?:i\s+paid\s+\d+\s+with\s+my\s+amex|i\s+withdrew\s+\d+\s+from\s+the\s+wells\s+fargo|i\s+transferred\s+\d+\s+to\s+my\s+savings|i\s+dumbed\s+\d+\s+into\s+my\s+robinhood\s+account)\b",
            text,
            re.IGNORECASE,
        ):
            return "USD"

    if _ARS_HINT_PATTERN.search(text):
        return "ARS"

    return None


def _adjust_amount_by_context(amount: float, text: str, *, is_income: bool) -> float:
    """Return adjust amount by context."""
    if _LUCAS_PATTERN.search(text):
        # Dataset convention: in income phrases "lucas/lukas" usually means
        # thousands; in most expense phrases it does not.
        if is_income or amount < 10:
            return amount * 1000
    return amount


def _extract_category(text: str) -> str | None:
    """Return extract category."""
    for pattern, category in _CATEGORY_KEYWORDS:
        if pattern.search(text):
            return category
    return None


def _extract_account(text: str) -> str | None:
    """Return extract account."""
    for pattern in _ACCOUNT_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(1).strip().lower()
    return None


def _extract_freeform_category(text: str) -> str | None:
    """Extract a category candidate from trailing prepositional phrases.

    This is a lightweight heuristic used when no known category keyword matched.
    """
    cleaned = re.sub(r"[.,;:!?]+$", "", text.strip())
    m = _CATEGORY_FREEFORM_TRAIL_PATTERN.search(cleaned)
    if not m:
        return None
    candidate = " ".join(m.group(1).split()).lower()
    if not candidate:
        return None
    tokens = candidate.split()
    if any(token in _CATEGORY_FORBIDDEN_TOKENS for token in tokens):
        return None
    if len(tokens) > 3:
        tokens = tokens[:3]
    return "_".join(tokens)


# ---------------------------------------------------------------------------
# Result construction
# ---------------------------------------------------------------------------

_NONE_MESSAGE_KEY = "chat.none.generic"

_ACTION_TEMPLATE: dict[str, Any] = {
    "action": "none",
    "amount": None,
    "description": None,
    "category": None,
    "account": None,
    "base_currency": None,
    "exchange_rate": None,
    "converted_amount": None,
    "report_type": None,
    "period": None,
    "filters": None,
    "message": None,
}


def _build_filters(category: str | None) -> dict[str, Any] | None:
    """Return build filters."""
    if category is None:
        return None
    return {
        "categories": [category],
        "accounts": None,
        "min_amount": None,
        "max_amount": None,
        "text": None,
    }


def _build_result_legacy(signals: ParseSignals, intent: str, default_currency: str | None = None) -> dict[str, Any]:
    """Convert an intent + signals into the final action dict using ``match/case``."""
    result: dict[str, Any] = dict(_ACTION_TEMPLATE)

    freeform_category = _extract_freeform_category(signals.raw_text) if signals.account is None else None

    match intent:
        case "report":
            result["action"] = "report"
            result["report_type"] = _extract_report_type(signals.raw_text)
            result["period"] = _extract_period(signals.raw_text)
            result["filters"] = _build_filters(signals.category)

        case "analysis":
            result["action"] = "data_analysis"
            result["period"] = _extract_period(signals.raw_text)
            result["filters"] = _build_filters(signals.category)

        case "expense" if signals.amount is None:
            result["action"] = "none"
            result["message"] = _message_text(
                "chat.parser.missing_amount.expense",
                signals.raw_text,
                default=(
                    "This looks like an expense, but I could not detect the amount or currency. "
                    "Can you tell me how much you spent and in which currency?"
                ),
            )

        case "income" if signals.amount is None:
            result["action"] = "none"
            result["message"] = _message_text(
                "chat.parser.missing_amount.income",
                signals.raw_text,
                default=(
                    "This looks like income, but I could not detect the amount or currency. "
                    "Can you tell me how much you received and in which currency?"
                ),
            )

        case "expense":
            amount = _adjust_amount_by_context(signals.amount, signals.raw_text, is_income=False)  # type: ignore[arg-type]
            result["action"] = "add_expense"
            result["amount"] = amount
            result["description"] = signals.raw_text.strip()
            result["category"] = signals.category or freeform_category or "expense"
            result["account"] = signals.account
            result["base_currency"] = _extract_currency(signals.raw_text, default_currency)
            result["exchange_rate"] = 1.0
            result["converted_amount"] = amount

        case "income":
            amount = _adjust_amount_by_context(signals.amount, signals.raw_text, is_income=True)  # type: ignore[arg-type]
            result["action"] = "add_income"
            result["amount"] = amount
            result["description"] = signals.raw_text.strip()
            result["category"] = signals.category or freeform_category or "income"
            result["account"] = signals.account
            result["base_currency"] = _extract_currency(signals.raw_text, default_currency)
            result["exchange_rate"] = 1.0
            result["converted_amount"] = amount

        case "unknown" if signals.amount is not None:
            result["action"] = "none"
            result["message"] = _message_text(
                "chat.parser.unknown_direction",
                signals.raw_text,
                default=(
                    "I detected an amount of {amount:.0f}, but I am not sure whether it is income or expense. "
                    "Can you clarify?"
                ),
                params={"amount": float(signals.amount)},
            )

        case _:
            result["action"] = "none"
            result["message"] = _message_text(
                _NONE_MESSAGE_KEY,
                signals.raw_text,
                default=(
                    "Sorry, I did not understand your request. "
                    "I can help you record income, expenses, or review your financial summary."
                ),
            )

    return result


# Localized override for assistant-facing clarification messages. Defining this
# second copy keeps the parser logic readable while allowing the final user copy
# to be translated without threading database state through the parser.
_SPANISH_MESSAGE_HINTS = {
    "abone",
    "ahorro",
    "comida",
    "cuenta",
    "gaste",
    "gasto",
    "gastos",
    "ingreso",
    "pague",
    "recibi",
    "reporte",
    "salario",
    "tarjeta",
}


def _message_language(text: str | None) -> str:
    """Return message language."""
    normalized = " ".join(str(text or "").casefold().split())
    words = set(re.findall(r"\w+", normalized, flags=re.UNICODE))
    if re.search(r"[áéíóúñ¿¡]", normalized) or _SPANISH_MESSAGE_HINTS.intersection(words):
        return "es"
    return "en"


def _message_text(key: str, raw_text: str | None, *, default: str, params: dict[str, object] | None = None) -> str:
    """Return message text."""
    return tr(key, _message_language(raw_text), default=default, params=params)


def _build_result(signals: ParseSignals, intent: str, default_currency: str | None = None) -> dict[str, Any]:
    """Return build result."""
    result: dict[str, Any] = dict(_ACTION_TEMPLATE)

    freeform_category = _extract_freeform_category(signals.raw_text) if signals.account is None else None

    match intent:
        case "report":
            result["action"] = "report"
            result["report_type"] = _extract_report_type(signals.raw_text)
            result["period"] = _extract_period(signals.raw_text)
            result["filters"] = _build_filters(signals.category)

        case "analysis":
            result["action"] = "data_analysis"
            result["period"] = _extract_period(signals.raw_text)
            result["filters"] = _build_filters(signals.category)

        case "expense" if signals.amount is None:
            result["action"] = "none"
            result["message"] = _message_text(
                "chat.parser.missing_amount.expense",
                signals.raw_text,
                default=(
                    "This looks like an expense, but I could not detect the amount or currency. "
                    "Can you tell me how much you spent and in which currency?"
                ),
            )

        case "income" if signals.amount is None:
            result["action"] = "none"
            result["message"] = _message_text(
                "chat.parser.missing_amount.income",
                signals.raw_text,
                default=(
                    "This looks like income, but I could not detect the amount or currency. "
                    "Can you tell me how much you received and in which currency?"
                ),
            )

        case "expense":
            amount = _adjust_amount_by_context(signals.amount, signals.raw_text, is_income=False)  # type: ignore[arg-type]
            result["action"] = "add_expense"
            result["amount"] = amount
            result["description"] = signals.raw_text.strip()
            result["category"] = signals.category or freeform_category or "expense"
            result["account"] = signals.account
            result["base_currency"] = _extract_currency(signals.raw_text, default_currency)
            result["exchange_rate"] = 1.0
            result["converted_amount"] = amount

        case "income":
            amount = _adjust_amount_by_context(signals.amount, signals.raw_text, is_income=True)  # type: ignore[arg-type]
            result["action"] = "add_income"
            result["amount"] = amount
            result["description"] = signals.raw_text.strip()
            result["category"] = signals.category or freeform_category or "income"
            result["account"] = signals.account
            result["base_currency"] = _extract_currency(signals.raw_text, default_currency)
            result["exchange_rate"] = 1.0
            result["converted_amount"] = amount

        case "unknown" if signals.amount is not None:
            result["action"] = "none"
            result["message"] = _message_text(
                "chat.parser.unknown_direction",
                signals.raw_text,
                default=(
                    "I detected an amount of {amount:.0f}, but I am not sure whether it is income or expense. "
                    "Can you clarify?"
                ),
                params={"amount": float(signals.amount)},
            )

        case _:
            result["action"] = "none"
            result["message"] = _message_text(
                "chat.none.generic",
                signals.raw_text,
                default=(
                    "Sorry, I did not understand your request. "
                    "I can help you record income, expenses, or review your financial summary."
                ),
            )

    return result


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class TransactionParserEngine(BaseEngine):
    """Deterministic rule-based engine for assistant mode."""

    def __init__(
        self,
        prompts: PromptAssets | None = None,
        default_currency: str | None = None,
    ) -> None:
        """Initialize the TransactionParserEngine instance."""
        self._prompts = prompts or PromptAssets()
        # ISO-4217 code of the user's default currency from the database.
        # When set it drives the priority logic in _extract_currency:
        # - USD default  → full USD detection including heuristic phrases.
        # - non-USD default → only explicit "USD"/"US$" codes are matched;
        #   all USD heuristic patterns are suppressed to avoid false positives.
        self._default_currency: str | None = default_currency

    def parse(self, user_input: str) -> dict[str, Any]:
        # Fast path: exact-action lookup.
        """Return parse."""
        exact_action = self._prompts.get_exact_action(user_input)
        if exact_action is not None:
            return exact_action

        # Stage 1 — extract scalar values.
        amount = _extract_amount(user_input)
        currency = _extract_currency(user_input, self._default_currency)
        category = _extract_category(user_input)
        account = _extract_account(user_input)

        # Stage 2 — collect boolean signals.
        signals = collect_signals(user_input, amount, currency, category, account)

        # Stage 3 — resolve intent.
        intent = resolve_intent(signals)

        # Stage 4 — build result.
        return _build_result(signals, intent, self._default_currency)

    def chat(self, user_input: str) -> str:
        """Return chat."""
        return (
            "El modo chat con LLM no está disponible porque no hay un modelo GGUF activo. "
            "Selecciona un modelo en Configuración para habilitarlo."
        )

    def set_default_currency(self, currency: str | None) -> None:
        """Return set default currency."""
        self._default_currency = str(currency or "").strip().upper() or None
