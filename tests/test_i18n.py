# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Tests for UI translations."""

from mira.ui.i18n import normalize_language, tr


def test_language_defaults_to_english() -> None:
    assert normalize_language(None) == "en"
    assert normalize_language("pt") == "en"


def test_language_is_normalized_to_lowercase_supported_code() -> None:
    assert normalize_language("EN") == "en"


def test_spanish_translation_is_available() -> None:
    assert tr("menu.file", "es", default="File") == "Archivo"
    assert tr("menu.tools", "es", default="Tools") == "Herramientas"
    assert (
        tr("tools.compound_interest.title", "es", default="Compound Interest Calculator")
        == "Calculadora de Interés Compuesto"
    )
    assert tr("menu.tools.loan_amortization", "es", default="Loan Calculator") == "Calculadora de Préstamos"
    assert tr("menu.tools.goal_simulator", "es", default="Savings Goal Simulator") == "Simulador de Metas de Ahorro"


def test_english_falls_back_to_default() -> None:
    assert tr("menu.file", "en", default="File") == "File"
    assert tr("menu.tools", "en", default="Tools") == "Tools"
    assert (
        tr("tools.compound_interest.title", "en", default="Compound Interest Calculator")
        == "Compound Interest Calculator"
    )
    assert tr("menu.tools.loan_amortization", "en", default="Loan Calculator") == "Loan Calculator"
    assert tr("menu.tools.goal_simulator", "en", default="Savings Goal Simulator") == "Savings Goal Simulator"


def test_spanish_theme_translation_is_available() -> None:
    assert tr("settings.theme.dark", "es", default="Dark") == "Oscuro"


def test_category_tree_translation_is_available() -> None:
    assert tr("categories.col.name", "es", default="Category") == "Categoría"


def test_translation_falls_back_to_default_when_key_missing() -> None:
    assert tr("does.not.exist", "es", default="Fallback") == "Fallback"


def test_translation_falls_back_to_key_when_default_missing() -> None:
    assert tr("still.missing", "en") == "still.missing"


def test_translation_formats_params() -> None:
    text = tr(
        "reports.summary.template",
        "es",
        params={"preset": "este mes", "income": 100.0, "expense": 40.0, "net": 60.0},
    )
    assert "este mes" in text
    assert "100.00" in text
    assert "40.00" in text
    assert "60.00" in text


def test_new_ui_translation_keys_are_available() -> None:
    assert tr("tag_manager.title", "es", default="Tag Management") == "Gestión de etiquetas"
    assert tr("chat.clear", "es", default="Clear") == "Limpiar"
    assert tr("export.error.title", "es", default="Export Error") == "Error de exportación"


def test_tag_icon_labels_are_translated_in_both_languages() -> None:
    assert tr("tag.icon.shopping", "es", default="Shopping") == "🛒 Compras"
    assert tr("tag.icon.shopping", "en", default="Shopping") == "🛒 Shopping"
    assert tr("dialog.tags.icon.placeholder", "es", default="Select an icon") == "Selecciona un icono"
    assert tr("dialog.tags.icon.placeholder", "en", default="Select an icon") == "Select an icon"


def test_budget_navigation_translation_is_available() -> None:
    assert tr("nav.budget", "es", default="Budgets") == "🪣  Presupuestos"
    assert tr("nav.budget", "en", default="Budgets") == "🪣  Budgets"


def test_financial_tools_frequency_translations_available_in_both_languages() -> None:
    assert tr("tools.freq.monthly", "es", default="Monthly") == "Mensual"
    assert tr("tools.freq.quarterly", "es", default="Quarterly") == "Trimestral"
    assert tr("tools.freq.semiannual", "es", default="Semiannual") == "Semestral"
    assert tr("tools.freq.annual", "es", default="Annual") == "Anual"

    assert tr("tools.freq.monthly", "en", default="Monthly") == "Monthly"
    assert tr("tools.freq.quarterly", "en", default="Quarterly") == "Quarterly"
    assert tr("tools.freq.semiannual", "en", default="Semiannual") == "Semiannual"
    assert tr("tools.freq.annual", "en", default="Annual") == "Annual"


def test_financial_tools_amortization_method_translations_available_in_both_languages() -> None:
    assert tr("tools.loan.method.french", "es", default="French") == "Francés"
    assert tr("tools.loan.method.german", "es", default="German") == "Alemán"

    assert tr("tools.loan.method.french", "en", default="French") == "French"
    assert tr("tools.loan.method.german", "en", default="German") == "German"


def test_compound_interest_dialog_keys_translated_in_both_languages() -> None:
    assert tr("tools.compound_interest.initial_fund", "es") == "Fondo inicial"
    assert tr("tools.compound_interest.initial_fund", "en") == "Initial fund"
    assert tr("tools.compound_interest.capitalization", "es") == "Capitalización"
    assert tr("tools.compound_interest.capitalization", "en") == "Compounding frequency"
    assert tr("tools.compound_interest.col.period", "es") == "Periodo"
    assert tr("tools.compound_interest.col.period", "en") == "Period"
    assert tr("tools.compound_interest.chart.title", "es") == "Crecimiento del capital"
    assert tr("tools.compound_interest.chart.title", "en") == "Capital growth"


def test_loan_amortization_dialog_keys_translated_in_both_languages() -> None:
    assert tr("tools.loan_amortization.loan_amount", "es") == "Monto del préstamo"
    assert tr("tools.loan_amortization.loan_amount", "en") == "Loan amount"
    assert tr("tools.loan_amortization.method", "es") == "Método de amortización"
    assert tr("tools.loan_amortization.method", "en") == "Amortization method"
    assert tr("tools.loan_amortization.col.payment", "es") == "Cuota"
    assert tr("tools.loan_amortization.col.payment", "en") == "Payment"
    assert tr("tools.loan_amortization.chart.title", "es") == "Evolución del préstamo"
    assert tr("tools.loan_amortization.chart.title", "en") == "Loan evolution"


def test_goal_simulator_dialog_keys_translated_in_both_languages() -> None:
    assert tr("tools.goal_simulator.target_amount", "es") == "Monto objetivo"
    assert tr("tools.goal_simulator.target_amount", "en") == "Target amount"
    assert tr("tools.goal_simulator.btn_create_goal", "es") == "Crear meta de ahorro con este escenario"
    assert tr("tools.goal_simulator.btn_create_goal", "en") == "Create savings goal with this scenario"
    assert tr("tools.goal_simulator.status.reachable", "es") == "alcanzable"
    assert tr("tools.goal_simulator.status.reachable", "en") == "reachable"
    assert tr("tools.goal_simulator.status.unreachable", "es") == "no alcanzable"
    assert tr("tools.goal_simulator.status.unreachable", "en") == "not reachable"
    assert tr("tools.goal_simulator.dialog.unreachable_title", "es") == "Escenario no alcanzable"
    assert tr("tools.goal_simulator.dialog.unreachable_title", "en") == "Unreachable scenario"


def test_financial_tools_hardcoded_strings_replaced_by_tr() -> None:
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    checks = {
        "src/mira/ui/dialogs/financial/compound_interest.py": [
            '"Fondo inicial"',
            '"Tasa anual"',
            '"Capitalizacion"',
            '"Crecimiento del capital"',
            '"Saldo acumulado"',
            'f"${',
        ],
        "src/mira/ui/dialogs/financial/loan_amortization.py": [
            '"Monto del prestamo"',
            '"Tasa anual"',
            '"Frecuencia de pago"',
            '"Evolucion del prestamo"',
            'f"${',
        ],
        "src/mira/ui/dialogs/financial/goal_simulator.py": [
            '"Monto objetivo"',
            '"Frecuencia de ahorro"',
            '"Proyeccion de ahorro"',
            '"Crear meta de ahorro con este escenario"',
            'f"${',
        ],
    }

    for rel_path, forbidden_snippets in checks.items():
        content = (repo_root / rel_path).read_text(encoding="utf-8")
        for snippet in forbidden_snippets:
            assert snippet not in content, f"Untranslated/hardcoded snippet still present in {rel_path}: {snippet!r}"


def test_python_sources_decode_as_utf8() -> None:
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    for root_name in ("src", "tests"):
        for path in (repo_root / root_name).rglob("*.py"):
            path.read_text(encoding="utf-8")


def test_recently_fixed_visible_strings_are_marked_for_translation() -> None:
    from pathlib import Path

    checks = {
        "src/mira/ui/tag_manager.py": [
            'self.setWindowTitle("Gestión de Etiquetas")',
            'QPushButton("Crear etiqueta")',
        ],
        "src/mira/ui/main_window.py": [
            'QPushButton("Limpiar")',
            'QPushButton("Anterior")',
            'QPushButton("Siguiente")',
            'QMessageBox.critical(self, "Import Error"',
            'QMessageBox.critical(self, "Export Error"',
            'header = QLabel("MIRA")',
            'progress.setWindowTitle("MIRA")',
        ],
        "src/mira/ui/dialogs/crud.py": [
            'self.setWindowTitle("Editar Transacción" if tx else "Nueva Transacción")',
            'self._btn_expense = QPushButton("Gasto")',
            'self._btn_income = QPushButton("Ingreso")',
            'self._name_edit.setPlaceholderText("Account name…")',
            'self.setWindowTitle("Merge Categories")',
            'self.setWindowTitle("Nuevo presupuesto")',
        ],
        "src/mira/ui/views/dashboard.py": [
            'QMessageBox.information(self, "Edit Transaction", "Select a transaction first.")',
        ],
        "src/mira/ui/views/tags.py": [
            'QMessageBox.warning(self, "Validation", "Tag already exists.")',
        ],
        "src/mira/ui/views/recurring.py": [
            'layout.addWidget(_section_title("Recurring Transactions"))',
        ],
    }

    repo_root = Path(__file__).resolve().parents[1]
    for rel_path, forbidden_snippets in checks.items():
        content = (repo_root / rel_path).read_text(encoding="utf-8")
        for snippet in forbidden_snippets:
            assert snippet not in content, f"Untranslated UI snippet still present in {rel_path}: {snippet}"
