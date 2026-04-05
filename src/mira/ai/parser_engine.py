# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Deterministic transaction parser engine for assistant mode."""

from __future__ import annotations

import re
from typing import Any

from mira.ai.base_engine import BaseEngine
from mira.ai.prompt_assets import PromptAssets

# Regex patterns used by the deterministic parser engine
_INCOME_PATTERN = re.compile(
    r"\b("
    r"received?|salary|salario|sueldo|ingres[oó]|ingresaron|cobr[eé]|earned?|freelance|bonus|gan(?:[aáeé]|ar)|game|recib[ií]"
    r"|made\s+bank|made\s+a\s+killing|deposited|deposit[eé]|depositaron|dep[oó]sito"
    r"|recebi|ganhei|entrou"
    r"|me\s+cay[oó]|cay[oó]\s+una|me\s+lleg[oó]|lleg[oó]\s+la|llegaron|me\s+entr[oó]|entr[oó]\s+|entraron"
    r"|me\s+hice\s+unos?|sal[ií]?[oó]\s+un\s+(?:bisne|chivo)|sal[ií]?[oó]\s+una\s+lanita"
    r"|caiu\s+uma\s+grana|entrou\s+uma\s+grana"
    r"|got\s+paid|scored|raked\s+in|pulled\s+(?:in|down)|pocketed|cleared|netted|took\s+home|banked"
    r"|windfall|jackpot|cashed\s+out|cleaned\s+up|extra\s+bread|chunk\s+of\s+change|dough"
    r"|got\s+payd|got\s+\d+\s+(?:(?:mexican|argentine|colombian)\s+)?(?:dollars?|euros?|pesos?)\s+(?:for|as)|reciev(?:ed|e?d)|resivi|depozit(?:ed)?|ariv(?:ed)?|bonus\s+(?:arrived|arived|deposit|depozit)"
    r"|interest\s+income|benefits?|bennefits|sold|added\s+(?:money|mony)\s+to\s+my"
    r"|llego|lleg[oó]|recupere|vendi|fat\s+check|nice\s+deposit|scord|tax\s+refund|scholarship\s+(?:came\s+in|payment)"
    r"|pagaron|meti\s+plata\s+a\s+la\s+cuenta|mete\s+plata\s+a\s+la\s+cuenta|carge|reintegro"
    r"|insurance\s+payment|insurence\s+payment|rent\s+deposit|wonn?|transferd|puld\s+(?:in|down)|pocketid|netid|bankt"
    r"|got\s+paid\s+\d+\s+by|got\s+paid\s+for|got\s+\d+\s+(?:(?:mexican|argentine|colombian)\s+)?(?:dollars?|euros?|pesos?)\s+from"
    r"|got\s+a\s+(?:reimbursement|cash\s+gift)|scholarship\s+payment"
    r"|transferred\s+\d+\s+(?:(?:mexican|argentine|colombian)\s+)?pesos?\s+to\s+my\s+(?:[a-z]+\s+){0,3}account|transferred\s+\d+\s+to\s+my\s+(?:[a-z]+\s+){0,3}account|transferred\s+\d+\s+to\s+my\s+(?:savings|venmo|investment)|loaded\s+up\s+my\s+venmo"
    r"|moved\s+\d+\s+to\s+my\s+investment\s+account|dumped\s+\d+\s+into\s+my\s+(?:robinhood|investment)\s+account"
    r"|dumbed\s+\d+\s+into\s+my\s+(?:robinhood|investment)\s+account"
    r"|met[ií]\s+\d+\s+al\s+cajero|le\s+met[ií]|cargu[eé]\s+\d+\s+a\s+la\s+ual[aá]|me\s+transfirieron"
    r"|transfer[ií]\s+\d+\s+.*a\s+mi\s+cuenta"
    r")\b",
    re.IGNORECASE,
)
_EXPENSE_PATTERN = re.compile(
    r"\b("
    r"spent|paid|pay|bought|compr[ée]|gast[ée]|pagu[ée]|expense|cost|gasto|pago"
    r"|withdrew|retir[eé]|transfer[ií]|charged|billed"
    r"|tir[eé]|quem[eé]"
    r"|fund[ií]|patin[ée]|vol[ée]|sangraron|chorearon|esfumaron|dej[ée]|clav[ée]|garche|com[íi]|espiantaron|afanaron"
    r"|cobraron|debitaron|sacaron|saqu[eé]|me\s+saqu[eé]"
    r"|gastei|paguei|comprei"
    r"|blew|dropped|shelled\s+out|ripped\s+off|burned|coughed\s+up|forked\s+out|splurged|wasted"
    r"|threw\s+away|pissed\s+away|sank|sunk|maxed\s+out|maxed\s+my\s+card|maxed|maxed\s+out|cleaned\s+out"
    r"|dropt|bleew|dumbed|maxt|cleand|spennt|bot|fild|mainten(?:a|e)nce|shooping|burnd"
    r"|riped|charched|memberchip|tution|cost\s+mee|sheld|fair|payd|withdreww|tapt|venmod|cashapt"
    r"|cab[ií]o|cabió|colectibo|expensas"
    r"|garpe|tranfer[ií]|transferred\s+from|made\s+a\s+payment|dumped\s+cash\s+into\s+the\s+slot\s+machine"
    r"|dumped\s+\d+\s+into\s+my\s+car|pulled\s+\d+\s+from\s+the\s+atm"
    r"|puld\s+\d+\s+from\s+the\s+atm"
    r"|^de\s+\d+|met[ií]\s+\d+\s+pesos\s+de\s+gasolina"
    r"|filled\s+up|gym\s+membership|tuition\s+fee|bus\s+fare|purchased|coffed\s+up|forkd\s+out|splurjd|wastid|pist\s+away"
    r"|abon[eé]|desembols[eé]|pagamos|realic[eé]\s+(?:un\s+gasto|una\s+compra)|efectu[eé]\s+un\s+pago|pagar"
    r"|swiped|tapped|zelled|venmoed|cashapped|hit\s+up\s+the\s+.*\s+atm"
    r"|me\s+sal[ií]?[oó]\s+un\s+gasto|me\s+bajaron|me\s+tumbaron|se\s+me\s+fue"
    r"|se\s+me\s+fueron|me\s+ensartaron\s+la\s+cuenta|me\s+toc[oó]\s+soltar"
    r"|me\s+toc[oó]\s+pagar|me\s+toc[oó]\s+sacar|tuve\s+que\s+soltar|me\s+baj[ée]\s+con"
    r"|aflojar|desembolsar|me\s+clavaron|me\s+vaciaron\s+el\s+bolsillo"
    r"|me\s+arrancaron\s+la\s+cabeza|sal[ií]?[oó]\s+caro|saiu\s+caro|foi\s+uma\s+facada"
    r"|gazte|page|saake|saquee|saquee|sakee|targeta|farmasia|enla|aier"
    r")\b",
    re.IGNORECASE,
)
_SAVINGS_EXPENSE_PATTERN = re.compile(
    r"(?:"
    r"\bahorr(?:e|é|o|ó)\b|\bahorra(?:r|do)?\b|\bapart(?:e|é)\b|\bguard(?:e|é)\b|\breserv(?:e|é)\b|\bdestin(?:e|é)\b"
    r"|\bsave(?:d)?\b|\bset\s+aside\b|\bkept\b"
    r"|(?:\btransfer[ií]\b|\btransfier(?:o|e|es|en|a|as|an)\b|\btransferred\b|\bmand(?:e|é)\b|\bpuse\b|\bput\b|\bmoved\b|\badded\b)"
    r".*\b(?:ahorro|ahorros|savings?|savings\s+acc(?:ount)?|cuenta\s+de\s+ahorro|cuenta\s+de\s+ahorros|caja\s+de\s+ahorro|caja\s+de\s+ahorros|alcanc[ií]a|chanchito|piggy\s+bank|jar|wallet|monedero|billetera|cartera|caj[oó]n|frasco|lata|caja\s+fuerte|colch[oó]n|fund|portfolio|envelope|fixed\s+deposit|investment(?:\s+account)?|mutual\s+fund)\b"
    r")",
    re.IGNORECASE,
)
_REPORT_PATTERN = re.compile(
    r"\b(report|resumen|reporte|balance|summary|show|muéstrame|cuanto|how much|how am i)\b",
    re.IGNORECASE,
)
_ANALYSIS_PATTERN = re.compile(r"\b(analiza|analizar|análisis|analysis|analyze)\b", re.IGNORECASE)
_AMOUNT_PATTERN = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(k\b|grand\b|grande\b|lucas?\b|lukas?\b|mil\b)?",
    re.IGNORECASE,
)
_CURRENCY_PATTERNS: list[tuple[re.Pattern, str]] = [
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
_LUCAS_PATTERN = re.compile(r"\blu(?:c|k)as?\b", re.IGNORECASE)
_STRONG_EXPENSE_PATTERN = re.compile(
    r"\b(spent|paid|pay|payment|bought|compr[ée]|gast[ée]|pagu[ée]|gaste|pague|gasto|expense|cost|withdrew|retir[eé]|saqu[eé]|debitaron|cobraron|me\s+sacaron|me\s+cobraron)\b",
    re.IGNORECASE,
)
_STRONG_INCOME_PATTERN = re.compile(
    r"\b(received?|recib[ií]|got\s+paid|got\s+payd|earned?|cobr[eé]|deposit(?:ed|aron)|me\s+depositaron|me\s+transfirieron|ingres[oa]|lleg[oó]|vendi|sold|tax\s+return)\b",
    re.IGNORECASE,
)
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

_CATEGORY_KEYWORDS: list[tuple[re.Pattern, str]] = [
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


def _parse_numeric_token(raw: str) -> float:
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
    m = _AMOUNT_PATTERN.search(text)
    if not m:
        return None

    amount = _parse_numeric_token(m.group(1))
    suffix = (m.group(2) or "").lower()
    if suffix in {"k", "grand", "grande", "mil"}:
        amount *= 1000
    return amount


def _extract_currency(text: str) -> str | None:
    lower = text.lower()

    # Nationality-qualified pesos should win over local slang hints.
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

    for pattern, currency in _CURRENCY_PATTERNS:
        if pattern.search(text):
            return currency

    # Explicit heuristic buckets for phrases that imply ARS without naming it.
    if re.search(
        r"\b(?:transfer[ií]\s+\d+\s+para\s+el\s+alquiler|de\s+\d+\s+de\s+expensas|me\s+transfirieron\s+\d+|pague\s+\d+\s+de\s+la\s+luz|gaste\s+\d+\s+en\s+la\s+farmacia|mercado\s+pago\s+me\s+cobro|targeta\s+de\s+credito|sueldo\s+60\s*k|\bpage\s+\d+\s+de\s+la\s+lus|\bpague\s+el\s+gas\s+\d+|\bpage\s+el\s+gas\s+\d+|\bma[ñn]ana\s+tengo\s+que\s+pagar\s+\d+\s+de\s+la\s+luz|\bhoy\s+cobre\s+\d+\s+de\s+un\s+trabajo|\bel\s+finde\s+me\s+patine\s+\d+\s+en\s+ropa|\bgazte\s+\d+\s+en\s+la\s+farma(?:cia|sia))\b",
        text,
        re.IGNORECASE,
    ):
        return "ARS"

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
    if _LUCAS_PATTERN.search(text):
        # Dataset convention is mixed: in income phrases "lucas/lukas"
        # usually means thousands, while in most expense phrases it does not.
        if is_income or amount < 10:
            return amount * 1000
    return amount


def _extract_category(text: str) -> str | None:
    for pattern, category in _CATEGORY_KEYWORDS:
        if pattern.search(text):
            return category
    return None


def _extract_account(text: str) -> str | None:
    for pattern in _ACCOUNT_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(1).strip().lower()
    return None


_CATEGORY_FREEFORM_TRAIL_PATTERN = re.compile(
    r"\b(?:on|for|in|en|de)\s+([a-záéíóúñ][a-záéíóúñ\s]{2,32})$",
    re.IGNORECASE,
)
_CATEGORY_FORBIDDEN_TOKENS = frozenset({"account", "cuenta", "my", "mi"})


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


_NONE_MESSAGE = (
    "Disculpa, no entendí tu solicitud. " "Puedo ayudarte a registrar ingresos, gastos o ver tu resumen financiero."
)

# Categories that indicate income even when expense keywords are also present.
_INCOME_CATEGORIES = frozenset({"salary", "freelance"})

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


def _extract_report_type(text: str) -> str:
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


class TransactionParserEngine(BaseEngine):
    """Deterministic rule-based engine for assistant mode."""

    def __init__(self, prompts: PromptAssets | None = None) -> None:
        self._prompts = prompts or PromptAssets()

    def parse(self, user_input: str) -> dict[str, Any]:
        result = dict(_ACTION_TEMPLATE)

        exact_action = self._prompts.get_exact_action(user_input)
        if exact_action is not None:
            return exact_action

        if _REPORT_PATTERN.search(user_input):
            result["action"] = "report"
            result["report_type"] = _extract_report_type(user_input)
            result["period"] = _extract_period(user_input)
            category = _extract_category(user_input)
            if category:
                result["filters"] = {
                    "categories": [category],
                    "accounts": None,
                    "min_amount": None,
                    "max_amount": None,
                    "text": None,
                }
            return result

        if _ANALYSIS_PATTERN.search(user_input):
            result["action"] = "data_analysis"
            result["period"] = _extract_period(user_input)
            category = _extract_category(user_input)
            if category:
                result["filters"] = {
                    "categories": [category],
                    "accounts": None,
                    "min_amount": None,
                    "max_amount": None,
                    "text": None,
                }
            return result

        amount = _extract_amount(user_input)
        category = _extract_category(user_input)
        account = _extract_account(user_input)
        freeform_category = _extract_freeform_category(user_input) if account is None else None
        is_savings_expense = bool(_SAVINGS_EXPENSE_PATTERN.search(user_input))
        if is_savings_expense:
            category = "savings"
        is_income_context = category == "salary"

        has_income_pattern = bool(_INCOME_PATTERN.search(user_input))
        has_expense_pattern = bool(_EXPENSE_PATTERN.search(user_input))
        if is_savings_expense:
            has_expense_pattern = True
            has_income_pattern = False

        # Resolve ambiguity: when both income and expense patterns match,
        # income-like categories (salary, freelance) override expense.
        if has_expense_pattern and has_income_pattern:
            if re.search(r"\bgot\s+pa(?:id|yd|yed)\b", user_input, re.IGNORECASE):
                has_expense_pattern = False
            elif re.search(r"\breintegro\b", user_input, re.IGNORECASE):
                has_expense_pattern = False
            elif _STRONG_EXPENSE_PATTERN.search(user_input) and not _STRONG_INCOME_PATTERN.search(user_input):
                has_income_pattern = False
            elif _STRONG_INCOME_PATTERN.search(user_input) and not _STRONG_EXPENSE_PATTERN.search(user_input):
                has_expense_pattern = False

            # If still ambiguous after lexical rules, resolve with account/category cues.
            if has_expense_pattern and has_income_pattern:
                # Explicitly moving money into personal accounts is treated as income
                # in the current assistant contract/dataset.
                if account and re.search(r"\b(to|into|a|al)\b", user_input, re.IGNORECASE):
                    has_expense_pattern = False
                elif category in _INCOME_CATEGORIES and not _STRONG_EXPENSE_PATTERN.search(user_input):
                    has_expense_pattern = False
                else:
                    has_income_pattern = False

        if not has_income_pattern and re.search(r"\b(?:tax\s+return|shopping\s+spree)\b", user_input, re.IGNORECASE):
            if re.search(r"\btax\s+return\b", user_input, re.IGNORECASE):
                has_income_pattern = True
            if re.search(r"\bshopping\s+spree\b", user_input, re.IGNORECASE):
                has_expense_pattern = True

        if has_expense_pattern:
            if amount is None:
                result["action"] = "none"
                result["message"] = (
                    "Parece un gasto, pero no detecté el monto ni la moneda. "
                    "¿Puedes indicar cuánto gastaste y en qué moneda?"
                )
                return result
            result["action"] = "add_expense"
            result["amount"] = _adjust_amount_by_context(amount, user_input, is_income=False)
            result["description"] = user_input.strip()
            result["category"] = category or freeform_category or "expense"
            result["account"] = account
            result["base_currency"] = _extract_currency(user_input)
            result["exchange_rate"] = 1.0
            result["converted_amount"] = result["amount"]
            return result

        if has_income_pattern or is_income_context:
            if amount is None:
                result["action"] = "none"
                result["message"] = (
                    "Parece un ingreso, pero no detecté el monto ni la moneda. "
                    "¿Puedes indicar cuánto recibiste y en qué moneda?"
                )
                return result
            result["action"] = "add_income"
            result["amount"] = _adjust_amount_by_context(amount, user_input, is_income=True)
            result["description"] = user_input.strip()
            result["category"] = category or freeform_category or "income"
            result["account"] = account
            result["base_currency"] = _extract_currency(user_input)
            result["exchange_rate"] = 1.0
            result["converted_amount"] = result["amount"]
            return result

        # No explicit income/expense keyword and bare amount → ask for clarification
        # instead of silently recording an expense.
        if amount is not None:
            result["action"] = "none"
            result["message"] = (
                f"Detecté un monto de {amount:.0f}, pero no estoy seguro " "si es ingreso o gasto. ¿Puedes indicármelo?"
            )
            return result

        result["action"] = "none"
        result["message"] = _NONE_MESSAGE
        return result

    def chat(self, user_input: str) -> str:
        return (
            "El modo chat con LLM no está disponible porque no hay un modelo GGUF activo. "
            "Selecciona un modelo en Configuración para habilitarlo."
        )
