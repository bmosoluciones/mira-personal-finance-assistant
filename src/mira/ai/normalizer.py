# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Text normalizer for MIRA.

Pre-processes raw user input before it is passed to the LLM, applying
deterministic regex corrections to improve model accuracy.

Steps applied (in order):
1. Strip surrounding whitespace and collapse internal whitespace.
2. Lower-case the text.
3. Normalise currency symbols and shorthand to plain numbers
   (e.g. "$1,500.00" → "1500.00", "1.5k" → "1500").
4. Expand common abbreviations and typo corrections.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _collapse_whitespace(text: str) -> str:
    """Return collapse whitespace."""
    return re.sub(r"\s+", " ", text.strip())


def _normalise_currency(text: str) -> str:
    """Strip currency symbols and thousand-separators; keep decimal point."""
    # Remove leading currency symbols: $, €, £, ¥
    text = re.sub(r"[$€£¥]\s*", "", text)
    # Remove thousand separators (e.g. 1,500 → 1500) — only when followed by digits
    text = re.sub(r"(\d),(\d{3})\b", r"\1\2", text)
    return text


def _normalise_k_suffix(text: str) -> str:
    """Expand numeric 'k' shorthand: 1.5k → 1500, 2k → 2000."""

    def _expand(m: re.Match) -> str:
        """Return expand."""
        return str(int(float(m.group(1)) * 1000))

    return re.sub(r"(\d+(?:\.\d+)?)\s*k\b", _expand, text, flags=re.IGNORECASE)


# Common word expansions / typo corrections applied *after* lowercasing.
_SUBSTITUTIONS: list[tuple[re.Pattern, str]] = [
    # Explicit currency words
    (re.compile(r"\b(\d+(?:\.\d+)?)\s+dollars?\b", re.IGNORECASE), r"\1"),
    (re.compile(r"\b(\d+(?:\.\d+)?)\s+euros?\b", re.IGNORECASE), r"\1"),
    (re.compile(r"\b(\d+(?:\.\d+)?)\s+pesos?\b", re.IGNORECASE), r"\1"),
    (re.compile(r"\b(\d+(?:\.\d+)?)\s+usd\b", re.IGNORECASE), r"\1"),
    (re.compile(r"\b(\d+(?:\.\d+)?)\s+eur\b", re.IGNORECASE), r"\1"),
    # Income synonyms → "received"
    (
        re.compile(
            r"\b(earn(?:ed)?|got paid|cobr[eé]|ingres(?:o|[oóé])|gan[eé]|gane|game|recib[ií]|deposit[eé]|depósito|recebi|ganhei)\b",
            re.IGNORECASE,
        ),
        "received",
    ),
    # Common Spanish number words
    (re.compile(r"\bmil\b", re.IGNORECASE), "1000"),
    # Expense synonyms → "spent"
    (
        re.compile(
            r"\b(pay(?:ed)?|paid|pagu[eé]|compr[eé]|gast[eé]|bought|retir[eé]|transfer[ií]|gastei|paguei|comprei)\b",
            re.IGNORECASE,
        ),
        "spent",
    ),
    # Report synonyms → "report"
    (
        re.compile(r"\b(resumen|reporte|balance|summary|show me|m[uú]estrame)\b", re.IGNORECASE),
        "report",
    ),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalise(text: str) -> str:
    """Return a cleaned, normalised version of *text*.

    Parameters
    ----------
    text:
        Raw user input string.

    Returns
    -------
    str
        Cleaned string ready to be sent to the LLM engine.
    """
    text = _collapse_whitespace(text)
    text = _normalise_currency(text)
    text = _normalise_k_suffix(text)
    for pattern, replacement in _SUBSTITUTIONS:
        text = pattern.sub(replacement, text)
    text = _collapse_whitespace(text)
    return text
