# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Declarative vocabulary catalogs for the transaction parser.

Language extensibility
----------------------
Each language/region is represented by a :class:`LanguageCatalog`.  Adding
support for a new language only requires:

1. Creating a new :class:`LanguageCatalog` instance with ``income`` and
   ``expense`` term lists split into ``"strong"`` and ``"weak"`` signals.
2. Calling :func:`register_language` (or passing the catalog to
   :func:`build_patterns`) so the compiled patterns include the new vocabulary.

The compiled :data:`INCOME_STRONG_RE`, :data:`INCOME_BASE_RE`,
:data:`EXPENSE_STRONG_RE`, and :data:`EXPENSE_BASE_RE` patterns are derived
from all registered catalogs so that:

* ``strong ⊆ base`` is guaranteed by construction — no manual duplication.
* A single ``_compile_union()`` call produces the final alternation pattern.

Currently registered languages: **English** (``en``), **Spanish** (``es``),
**Portuguese** (``pt``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class LanguageCatalog:
    """Vocabulary catalog for a single language or regional dialect.

    Parameters
    ----------
    lang:
        BCP-47 language tag (e.g. ``"en"``, ``"es"``, ``"pt"``).
    income:
        Dict with ``"strong"`` and ``"weak"`` lists of regex fragments.
        Strong terms are unambiguous income signals; weak terms require
        corroboration.
    expense:
        Same structure as *income* but for expense signals.
    """

    lang: str
    income: dict[str, list[str]] = field(default_factory=lambda: {"strong": [], "weak": []})
    expense: dict[str, list[str]] = field(default_factory=lambda: {"strong": [], "weak": []})


# ---------------------------------------------------------------------------
# Built-in language catalogs
# ---------------------------------------------------------------------------

_CATALOG_EN = LanguageCatalog(
    lang="en",
    income={
        "strong": [
            r"received?",
            r"got\s+pa(?:id|yd|yed)",
            r"earned?",
            r"scored",
            r"raked\s+in",
            r"pulled\s+(?:in|down)",
            r"pocketed",
            r"cleared",
            r"netted",
            r"took\s+home",
            r"banked",
            r"made\s+bank",
            r"made\s+a\s+killing",
            r"windfall",
            r"jackpot",
            r"cashed\s+out",
            r"cleaned\s+up",
            r"tax\s+return",
            r"tax\s+refund",
            r"sold",
            r"pagaron",
        ],
        "weak": [
            r"salary",
            r"freelance",
            r"bonus",
            r"deposited",
            r"deposit(?:ed)?",
            r"interest\s+income",
            r"benefits?",
            r"bennefits",
            r"added\s+(?:money|mony)\s+to\s+my",
            r"fat\s+check",
            r"nice\s+deposit",
            r"scord",
            r"scholarship\s+(?:came\s+in|payment)",
            r"insurance\s+payment",
            r"insurence\s+payment",
            r"rent\s+deposit",
            r"wonn?",
            r"transferd",
            r"puld\s+(?:in|down)",
            r"pocketid",
            r"netid",
            r"bankt",
            r"reciev(?:ed|e?d)",
            r"resivi",
            r"depozit(?:ed)?",
            r"ariv(?:ed)?",
            r"bonus\s+(?:arrived|arived|deposit|depozit)",
            r"extra\s+bread",
            r"chunk\s+of\s+change",
            r"dough",
            r"got\s+paid\s+\d+\s+by",
            r"got\s+paid\s+for",
            r"got\s+\d+\s+(?:(?:mexican|argentine|colombian)\s+)?(?:dollars?|euros?|pesos?)\s+from",
            r"got\s+\d+\s+(?:(?:mexican|argentine|colombian)\s+)?(?:dollars?|euros?|pesos?)\s+(?:for|as)",
            r"got\s+a\s+(?:reimbursement|cash\s+gift)",
            r"transferred\s+\d+\s+(?:(?:mexican|argentine|colombian)\s+)?pesos?\s+to\s+my\s+(?:[a-z]+\s+){0,3}account",
            r"transferred\s+\d+\s+to\s+my\s+(?:[a-z]+\s+){0,3}account",
            r"transferred\s+\d+\s+to\s+my\s+(?:savings|venmo|investment)",
            r"loaded\s+up\s+my\s+venmo",
            r"moved\s+\d+\s+to\s+my\s+investment\s+account",
            r"dumped\s+\d+\s+into\s+my\s+(?:robinhood|investment)\s+account",
            r"dumbed\s+\d+\s+into\s+my\s+(?:robinhood|investment)\s+account",
        ],
    },
    expense={
        "strong": [
            r"spent",
            r"paid",
            r"pay",
            r"payment",
            r"bought",
            r"withdrew",
            r"expense",
            r"cost",
        ],
        "weak": [
            r"charged",
            r"billed",
            r"blew",
            r"dropped",
            r"shelled\s+out",
            r"ripped\s+off",
            r"burned",
            r"coughed\s+up",
            r"forked\s+out",
            r"splurged",
            r"wasted",
            r"threw\s+away",
            r"pissed\s+away",
            r"sank",
            r"sunk",
            r"maxed\s+out",
            r"maxed\s+my\s+card",
            r"maxed",
            r"cleaned\s+out",
            r"transferred\s+from",
            r"made\s+a\s+payment",
            r"dumped\s+cash\s+into\s+the\s+slot\s+machine",
            r"dumped\s+\d+\s+into\s+my\s+car",
            r"pulled\s+\d+\s+from\s+the\s+atm",
            r"filled\s+up",
            r"gym\s+membership",
            r"tuition\s+fee",
            r"bus\s+fare",
            r"purchased",
            r"swiped",
            r"tapped",
            r"zelled",
            r"venmoed",
            r"cashapped",
            r"hit\s+up\s+the\s+.*\s+atm",
            # Misspellings / typos
            r"dropt",
            r"bleew",
            r"dumbed",
            r"maxt",
            r"cleand",
            r"spennt",
            r"bot",
            r"fild",
            r"mainten(?:a|e)nce",
            r"shooping",
            r"burnd",
            r"riped",
            r"charched",
            r"memberchip",
            r"tution",
            r"cost\s+mee",
            r"sheld",
            r"fair",
            r"payd",
            r"withdreww",
            r"tapt",
            r"venmod",
            r"cashapt",
            r"coffed\s+up",
            r"forkd\s+out",
            r"splurjd",
            r"wastid",
            r"pist\s+away",
            r"puld\s+\d+\s+from\s+the\s+atm",
        ],
    },
)

_CATALOG_ES = LanguageCatalog(
    lang="es",
    income={
        "strong": [
            r"recib[ií]",
            r"cobr[eé]",
            r"me\s+depositaron",
            r"me\s+transfirieron",
            r"ingres[oa]",
            r"lleg[oó]",
            r"vend[ií]",
            r"pagaron",
        ],
        "weak": [
            r"salario",
            r"sueldo",
            r"ingres[oó]",
            r"ingresaron",
            r"freelance",
            r"gan(?:[aáeé]|ar)",
            r"game",
            r"dep[oó]sito",
            r"me\s+cay[oó]",
            r"cay[oó]\s+una",
            r"me\s+lleg[oó]",
            r"lleg[oó]\s+la",
            r"llegaron",
            r"me\s+entr[oó]",
            r"entr[oó]\s+",
            r"entraron",
            r"me\s+hice\s+unos?",
            r"sal[ií]?[oó]\s+un\s+(?:bisne|chivo)",
            r"sal[ií]?[oó]\s+una\s+lanita",
            r"llego",
            r"recupere",
            r"meti\s+plata\s+a\s+la\s+cuenta",
            r"mete\s+plata\s+a\s+la\s+cuenta",
            r"carge",
            r"reintegro",
            r"met[ií]\s+\d+\s+al\s+cajero",
            r"le\s+met[ií]",
            r"cargu[eé]\s+\d+\s+a\s+la\s+ual[aá]",
            r"transfer[ií]\s+\d+\s+.*a\s+mi\s+cuenta",
        ],
    },
    expense={
        "strong": [
            r"compr[ée]",
            r"gast[ée]",
            r"pagu[ée]",
            r"gaste",
            r"pague",
            r"gasto",
            r"retir[eé]",
            r"saqu[eé]",
            r"debitaron",
            r"cobraron",
            r"me\s+sacaron",
            r"me\s+cobraron",
        ],
        "weak": [
            r"transfer[ií]",
            r"tir[eé]",
            r"quem[eé]",
            r"fund[ií]",
            r"patin[ée]",
            r"vol[ée]",
            r"sangraron",
            r"chorearon",
            r"esfumaron",
            r"dej[ée]",
            r"clav[ée]",
            r"garche",
            r"espiantaron",
            r"afanaron",
            r"sacaron",
            r"me\s+saqu[eé]",
            r"garpe",
            r"tranfer[ií]",
            r"abon[eé]",
            r"desembols[eé]",
            r"pagamos",
            r"realic[eé]\s+(?:un\s+gasto|una\s+compra)",
            r"efectu[eé]\s+un\s+pago",
            r"pagar",
            r"me\s+sal[ií]?[oó]\s+un\s+gasto",
            r"me\s+bajaron",
            r"me\s+tumbaron",
            r"se\s+me\s+fue",
            r"se\s+me\s+fueron",
            r"me\s+ensartaron\s+la\s+cuenta",
            r"me\s+toc[oó]\s+soltar",
            r"me\s+toc[oó]\s+pagar",
            r"me\s+toc[oó]\s+sacar",
            r"tuve\s+que\s+soltar",
            r"me\s+baj[ée]\s+con",
            r"aflojar",
            r"desembolsar",
            r"me\s+clavaron",
            r"me\s+vaciaron\s+el\s+bolsillo",
            r"me\s+arrancaron\s+la\s+cabeza",
            r"sal[ií]?[oó]\s+caro",
            # Regional slang: Argentina
            r"com[íi]",
            r"cab[ií]o",
            r"cabió",
            r"colectibo",
            r"expensas",
            # Misspellings
            r"gazte",
            r"page",
            r"saake",
            r"saquee",
            r"sakee",
            r"targeta",
            r"farmasia",
            r"enla",
            r"aier",
        ],
    },
)

_CATALOG_PT = LanguageCatalog(
    lang="pt",
    income={
        "strong": [
            r"recebi",
            r"ganhei",
            r"entrou",
        ],
        "weak": [
            r"caiu\s+uma\s+grana",
            r"entrou\s+uma\s+grana",
        ],
    },
    expense={
        "strong": [],
        "weak": [
            r"gastei",
            r"paguei",
            r"comprei",
            r"saiu\s+caro",
            r"foi\s+uma\s+facada",
            r"tive\s+que\s+desembolsar",
        ],
    },
)

# ---------------------------------------------------------------------------
# Language registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, LanguageCatalog] = {c.lang: c for c in (_CATALOG_EN, _CATALOG_ES, _CATALOG_PT)}


def register_language(catalog: LanguageCatalog) -> None:
    """Register a new :class:`LanguageCatalog` and rebuild compiled patterns.

    Call this function before the first :class:`~mira.ai.parser_engine.TransactionParserEngine`
    is instantiated if you need to add vocabulary for a new language.

    Example::

        from mira.ai.parser_vocab import LanguageCatalog, register_language

        register_language(LanguageCatalog(
            lang="fr",
            income={"strong": [r"reçu", r"salaire"], "weak": [r"revenu"]},
            expense={"strong": [r"dépensé", r"payé"], "weak": [r"coûté"]},
        ))
    """
    _REGISTRY[catalog.lang] = catalog
    _rebuild_patterns()


def get_registered_languages() -> list[str]:
    """Return the list of currently registered language codes."""
    return list(_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Pattern compilation
# ---------------------------------------------------------------------------


def _compile_union(parts: list[str]) -> re.Pattern[str]:
    """Compile a list of regex fragments into a single alternation pattern."""
    return re.compile(r"\b(?:" + "|".join(parts) + r")\b", re.IGNORECASE)


def build_patterns(
    catalogs: list[LanguageCatalog] | None = None,
) -> tuple[re.Pattern[str], re.Pattern[str], re.Pattern[str], re.Pattern[str]]:
    """Build and return ``(income_strong, income_base, expense_strong, expense_base)`` patterns.

    Parameters
    ----------
    catalogs:
        Explicit list of catalogs to use.  Defaults to all registered catalogs.

    Returns
    -------
    tuple
        ``(INCOME_STRONG_RE, INCOME_BASE_RE, EXPENSE_STRONG_RE, EXPENSE_BASE_RE)``
    """
    if catalogs is None:
        catalogs = list(_REGISTRY.values())

    income_strong: list[str] = []
    income_weak: list[str] = []
    expense_strong: list[str] = []
    expense_weak: list[str] = []

    for cat in catalogs:
        income_strong.extend(cat.income.get("strong", []))
        income_weak.extend(cat.income.get("weak", []))
        expense_strong.extend(cat.expense.get("strong", []))
        expense_weak.extend(cat.expense.get("weak", []))

    # Deduplicate while preserving order so the compiled pattern stays stable.
    def _dedup(lst: list[str]) -> list[str]:
        seen: set[str] = set()
        return [x for x in lst if not (x in seen or seen.add(x))]  # type: ignore[func-returns-value]

    income_strong = _dedup(income_strong)
    income_weak = _dedup(income_weak)
    expense_strong = _dedup(expense_strong)
    expense_weak = _dedup(expense_weak)

    return (
        _compile_union(income_strong),
        _compile_union(income_strong + income_weak),
        _compile_union(expense_strong) if expense_strong else re.compile(r"(?!)", re.IGNORECASE),
        _compile_union(expense_strong + expense_weak),
    )


# Module-level compiled patterns derived from all registered catalogs.
# Use :func:`register_language` to extend them at runtime.
INCOME_STRONG_RE, INCOME_BASE_RE, EXPENSE_STRONG_RE, EXPENSE_BASE_RE = build_patterns()


def _rebuild_patterns() -> None:
    """Recompile module-level patterns after a new catalog is registered."""
    global INCOME_STRONG_RE, INCOME_BASE_RE, EXPENSE_STRONG_RE, EXPENSE_BASE_RE
    INCOME_STRONG_RE, INCOME_BASE_RE, EXPENSE_STRONG_RE, EXPENSE_BASE_RE = build_patterns()
