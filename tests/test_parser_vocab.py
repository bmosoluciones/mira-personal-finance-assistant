# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Unit tests for mira.ai.parser_vocab.

Covers:
- LanguageCatalog dataclass construction
- get_registered_languages / register_language
- build_patterns: strong ⊆ base by construction
- Compiled pattern correctness for each built-in language
- Runtime language extension via register_language
"""

from __future__ import annotations

import pytest

import mira.ai.parser_vocab as vocab
from mira.ai.parser_vocab import LanguageCatalog, build_patterns, get_registered_languages, register_language

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_patterns(lang_codes: list[str]):
    """Build patterns from the named built-in catalogs only (isolated)."""
    catalogs = [vocab._REGISTRY[code] for code in lang_codes if code in vocab._REGISTRY]
    return build_patterns(catalogs)


# ---------------------------------------------------------------------------
# LanguageCatalog
# ---------------------------------------------------------------------------


class TestLanguageCatalog:
    def test_default_fields_are_empty_lists(self):
        cat = LanguageCatalog(lang="xx")
        assert cat.income == {"strong": [], "weak": []}
        assert cat.expense == {"strong": [], "weak": []}

    def test_custom_fields_are_stored(self):
        cat = LanguageCatalog(
            lang="de",
            income={"strong": [r"erhalten"], "weak": [r"gehalt"]},
            expense={"strong": [r"bezahlt"], "weak": [r"ausgegeben"]},
        )
        assert cat.lang == "de"
        assert r"erhalten" in cat.income["strong"]
        assert r"gehalt" in cat.income["weak"]
        assert r"bezahlt" in cat.expense["strong"]
        assert r"ausgegeben" in cat.expense["weak"]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestLanguageRegistry:
    def test_builtin_languages_are_registered(self):
        langs = get_registered_languages()
        assert "en" in langs
        assert "es" in langs
        assert "pt" in langs

    def test_register_new_language_appears_in_list(self):
        # Use a unique tag so parallel tests don't collide
        tag = "_test_register_zz"
        register_language(
            LanguageCatalog(
                lang=tag, income={"strong": [r"testincome"], "weak": []}, expense={"strong": [], "weak": []}
            )
        )
        assert tag in get_registered_languages()
        # Cleanup – restore original registry state
        vocab._REGISTRY.pop(tag, None)
        vocab._rebuild_patterns()

    def test_register_language_updates_compiled_patterns(self):
        tag = "_test_update_yy"
        unique_term = r"xyzabcuniqueincome123"
        register_language(
            LanguageCatalog(lang=tag, income={"strong": [unique_term], "weak": []}, expense={"strong": [], "weak": []})
        )
        try:
            assert vocab.INCOME_STRONG_RE.search("xyzabcuniqueincome123 received 500")
        finally:
            vocab._REGISTRY.pop(tag, None)
            vocab._rebuild_patterns()

    def test_registering_same_lang_replaces_previous(self):
        tag = "_test_replace_vv"
        register_language(
            LanguageCatalog(lang=tag, income={"strong": [r"termA"], "weak": []}, expense={"strong": [], "weak": []})
        )
        register_language(
            LanguageCatalog(lang=tag, income={"strong": [r"termB"], "weak": []}, expense={"strong": [], "weak": []})
        )
        try:
            langs = get_registered_languages()
            assert langs.count(tag) == 1
        finally:
            vocab._REGISTRY.pop(tag, None)
            vocab._rebuild_patterns()


# ---------------------------------------------------------------------------
# build_patterns: strong ⊆ base by construction
# ---------------------------------------------------------------------------


class TestBuildPatterns:
    def test_strong_subset_of_base_income(self):
        inc_strong, inc_base, _, _ = build_patterns()
        # Every term that matches strong must also match base.
        test_terms = [
            "received 100",
            "got paid 200",
            "earned 300",
            "scored 400",
            "recibí 500",
            "recebi 600",
            "ganhei 700",
        ]
        for term in test_terms:
            if inc_strong.search(term):
                assert inc_base.search(term), f"strong matched {term!r} but base did not"

    def test_strong_subset_of_base_expense(self):
        _, _, exp_strong, exp_base = build_patterns()
        test_terms = [
            "spent 100",
            "paid 200",
            "bought 300",
            "withdrew 400",
            "gast\xe9 500",
            "compr\xe9 600",
            "pagu\xe9 700",
        ]
        for term in test_terms:
            if exp_strong.search(term):
                assert exp_base.search(term), f"strong matched {term!r} but base did not"

    def test_custom_catalog_terms_compile_into_patterns(self):
        cat = LanguageCatalog(
            lang="_tmp_build",
            income={"strong": [r"magic_income_term"], "weak": [r"weak_income_term"]},
            expense={"strong": [r"magic_expense_term"], "weak": [r"weak_expense_term"]},
        )
        inc_strong, inc_base, exp_strong, exp_base = build_patterns([cat])
        assert inc_strong.search("magic_income_term 100")
        assert inc_base.search("weak_income_term 100")
        assert exp_strong.search("magic_expense_term 50")
        assert exp_base.search("weak_expense_term 50")

    def test_empty_expense_strong_list_does_not_raise(self):
        cat = LanguageCatalog(
            lang="_tmp_empty",
            income={"strong": [r"income_only"], "weak": []},
            expense={"strong": [], "weak": [r"some_expense"]},
        )
        inc_strong, inc_base, exp_strong, exp_base = build_patterns([cat])
        assert inc_strong.search("income_only 100")
        assert exp_base.search("some_expense 50")
        # exp_strong should not match anything meaningful
        assert not exp_strong.search("income_only 100")


# ---------------------------------------------------------------------------
# Built-in English vocabulary
# ---------------------------------------------------------------------------


class TestEnglishVocabulary:
    @pytest.mark.parametrize(
        "text",
        [
            "I received 500 dollars",
            "got paid 2000 last week",
            "earned 300 from freelance",
            "scored 150 at the poker table",
            "raked in 1000 this month",
            "pocketed 400 after taxes",
            "banked 750 from consulting",
            "made bank last quarter",
            "tax return of 800",
        ],
    )
    def test_english_income_strong_terms(self, text: str):
        assert vocab.INCOME_STRONG_RE.search(text), f"expected strong income match for: {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "salary of 3000",
            "bonus payment received",
            "freelance gig paid out",
            "interest income this month",
        ],
    )
    def test_english_income_weak_terms(self, text: str):
        # weak terms match base but may not match strong
        assert vocab.INCOME_BASE_RE.search(text), f"expected base income match for: {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "spent 50 on coffee",
            "paid 120 for rent",
            "payment of 300 made",
            "bought groceries for 80",
            "withdrew 200 from ATM",
        ],
    )
    def test_english_expense_strong_terms(self, text: str):
        assert vocab.EXPENSE_STRONG_RE.search(text), f"expected strong expense match for: {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "blew 200 on a jacket",
            "shelled out 90 for dinner",
            "splurged on shoes 150",
            "maxed out my card",
            "filled up the tank 60",
        ],
    )
    def test_english_expense_weak_terms(self, text: str):
        assert vocab.EXPENSE_BASE_RE.search(text), f"expected base expense match for: {text!r}"


# ---------------------------------------------------------------------------
# Built-in Spanish vocabulary
# ---------------------------------------------------------------------------


class TestSpanishVocabulary:
    @pytest.mark.parametrize(
        "text",
        [
            "recibí 500 de salario",
            "cobré 300 del cliente",
            "me depositaron 1000 pesos",
            "me transfirieron 200",
            "ingreso de sueldo 3000",
            "llegó el pago 800",
            "vendi el coche por 5000",
            "vendí artesanías por 3000",
        ],
    )
    def test_spanish_income_strong_terms(self, text: str):
        assert vocab.INCOME_STRONG_RE.search(text), f"expected strong income match for: {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "salario de 3000",
            "sueldo mensual 4500",
            "me cayó una lana de 500",
            "me entró una plata 800",
            "llegaron los mangos 260",
            "ingresó el sueldo 3000",
        ],
    )
    def test_spanish_income_weak_terms(self, text: str):
        assert vocab.INCOME_BASE_RE.search(text), f"expected base income match for: {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "compré ropa por 150",
            "gasté 80 en comida",
            "pagué 200 de arriendo",
            "retiré 500 del banco",
            "debitaron 120 de mi cuenta",
            "me sacaron 70 de multa",
        ],
    )
    def test_spanish_expense_strong_terms(self, text: str):
        assert vocab.EXPENSE_STRONG_RE.search(text), f"expected strong expense match for: {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "me salió un gasto de 300",
            "me bajaron 150 del sueldo",
            "se me fue el pisto 90",
            "me tumbaron feria 220",
            "aflojar 100 para la renta",
            "me vaciaron el bolsillo 77",
        ],
    )
    def test_spanish_expense_weak_terms(self, text: str):
        assert vocab.EXPENSE_BASE_RE.search(text), f"expected base expense match for: {text!r}"


# ---------------------------------------------------------------------------
# Built-in Portuguese vocabulary
# ---------------------------------------------------------------------------


class TestPortugueseVocabulary:
    @pytest.mark.parametrize(
        "text",
        [
            "recebi 500 de salário",
            "ganhei 300 no freelance",
            "entrou o pagamento 200",
        ],
    )
    def test_portuguese_income_strong_terms(self, text: str):
        assert vocab.INCOME_STRONG_RE.search(text), f"expected strong income match for: {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "gastei 30 em comida",
            "paguei 100 de aluguel",
            "comprei roupa 80",
            "saiu caro 120",
            "foi uma facada 55",
        ],
    )
    def test_portuguese_expense_weak_terms(self, text: str):
        assert vocab.EXPENSE_BASE_RE.search(text), f"expected base expense match for: {text!r}"


# ---------------------------------------------------------------------------
# Language extension (runtime registration)
# ---------------------------------------------------------------------------


class TestLanguageExtension:
    def test_new_language_income_terms_are_matched(self):
        tag = "_test_ext_fr"
        register_language(
            LanguageCatalog(
                lang=tag,
                income={"strong": [r"reçu", r"salaire"], "weak": [r"revenu"]},
                expense={"strong": [r"dépensé", r"payé"], "weak": [r"coûté"]},
            )
        )
        try:
            assert vocab.INCOME_STRONG_RE.search("reçu 100 euros")
            assert vocab.INCOME_STRONG_RE.search("salaire 3000")
            assert vocab.INCOME_BASE_RE.search("revenu mensuel 2000")
            assert vocab.EXPENSE_STRONG_RE.search("dépensé 50 au restaurant")
            assert vocab.EXPENSE_BASE_RE.search("coûté 30 euros")
        finally:
            vocab._REGISTRY.pop(tag, None)
            vocab._rebuild_patterns()

    def test_removing_language_updates_patterns(self):
        tag = "_test_remove_ww"
        unique = r"unique_term_zzz"
        register_language(
            LanguageCatalog(lang=tag, income={"strong": [unique], "weak": []}, expense={"strong": [], "weak": []})
        )
        assert vocab.INCOME_STRONG_RE.search("unique_term_zzz 999")
        vocab._REGISTRY.pop(tag, None)
        vocab._rebuild_patterns()
        assert not vocab.INCOME_STRONG_RE.search("unique_term_zzz 999")

    def test_compiled_pattern_is_case_insensitive(self):
        tag = "_test_case_uu"
        register_language(
            LanguageCatalog(lang=tag, income={"strong": [r"MixedCase"], "weak": []}, expense={"strong": [], "weak": []})
        )
        try:
            assert vocab.INCOME_STRONG_RE.search("mixedcase 100")
            assert vocab.INCOME_STRONG_RE.search("MIXEDCASE 100")
            assert vocab.INCOME_STRONG_RE.search("MixedCase 100")
        finally:
            vocab._REGISTRY.pop(tag, None)
            vocab._rebuild_patterns()
