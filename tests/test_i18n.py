# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Tests for UI translations."""

from collections.abc import Sequence

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
    assert tr("menu.file.import_csv", "es", default="Import transactions…") == "Importar transacciones…"
    assert tr("menu.file.export_csv", "en", default="Export transactions…") == "Export transactions…"
    assert "*.csv" in tr("file.filter.transactions_all", "es")
    assert "*.xlsx" in tr("file.filter.transactions_all", "en")
    assert tr("transactions.file_error.unsupported_extension", "es", params={"extension": ".xls"}).startswith(
        "La extensión"
    )


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


def test_python_sources_do_not_contain_common_mojibake_sequences() -> None:
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    suspicious_sequences = (
        "\u00c3",
        "\u00c2",
        "\u00e2\u20ac",
        "\u00e2\u20ac\u201d",
        "\u00e2\u20ac\u201c",
        "\u00f0\u0178",
        "\ufffd",
    )

    for root_name in ("src", "tests"):
        for path in (repo_root / root_name).rglob("*.py"):
            content = path.read_text(encoding="utf-8")
            for sequence in suspicious_sequences:
                assert sequence not in content, f"Possible mojibake found in {path}: {sequence!r}"


def test_chat_and_report_translation_keys_are_available_in_both_languages() -> None:
    assert tr("quick.template.add_income", "es") == "recibi 0 de "
    assert tr("quick.template.add_income", "en") == "received 0 from "
    assert tr("quick.template.add_expense", "es") == "gaste 0 en "
    assert tr("quick.template.add_expense", "en") == "spent 0 on "
    assert tr("quick.template.report", "es") == "reporte"
    assert tr("quick.template.report", "en") == "report"
    assert tr("chat.report.header", "es") == "Reporte ({report_type}) - periodo: {period}"
    assert tr("chat.report.header", "en") == "Report ({report_type}) - period: {period}"
    assert tr("chat.income.recorded", "es").startswith("Ingreso registrado:")
    assert tr("chat.income.recorded", "en").startswith("Income recorded:")
    assert tr("chat.expense.recorded", "es").startswith("Gasto registrado:")
    assert tr("chat.expense.recorded", "en").startswith("Expense recorded:")
    assert tr("reports.load_error", "es") == "No se pudo cargar el reporte. Revisa los filtros e intenta de nuevo."
    assert tr("reports.load_error", "en") == "The report could not be loaded. Review the filters and try again."
    assert (
        tr("mira.analysis.load_error", "es")
        == "No se pudo cargar el analisis MIRA. Revisa el periodo e intenta de nuevo."
    )
    assert (
        tr("mira.analysis.load_error", "en")
        == "The MIRA analysis could not be loaded. Review the period and try again."
    )


def test_src_user_visible_literals_are_wrapped_for_translation() -> None:
    import ast
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    constructor_names = {"QLabel", "QPushButton", "QCheckBox", "QRadioButton", "QAction"}
    method_names = {
        "addItem",
        "setHtml",
        "setLabelText",
        "setPlaceholderText",
        "setStatusTip",
        "setText",
        "setToolTip",
        "setWindowTitle",
        "showMessage",
    }
    translation_calls = {"tr", "_t", "_component_tr", "_executor_tr", "_message_text", "_report_text", "translate"}
    findings: list[str] = []

    def _needs_translation(text: str) -> bool:
        normalized = text.strip()
        if not any(ch.isalpha() for ch in normalized):
            return False
        letters = "".join(ch for ch in normalized if ch.isalpha())
        return not (letters.isupper() and len(letters) <= 5)

    def _is_translation_call(node: ast.AST) -> bool:
        if not isinstance(node, ast.Call):
            return False
        match node.func:
            case ast.Name(id=name):
                return name in translation_calls
            case ast.Attribute(attr=name):
                return name in translation_calls
        return False

    def _literal_string(node: ast.AST) -> str | None:
        if _is_translation_call(node):
            return None
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    for path in (repo_root / "src").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        path_parts = set(path.parts)
        is_chat_or_ui_file = {"ai", "ui"}.intersection(path_parts) != set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in constructor_names and node.args:
                    text = _literal_string(node.args[0])
                    if text and _needs_translation(text):
                        findings.append(f"{path}:{node.lineno}: constructor literal {text!r}")

                if isinstance(node.func, ast.Attribute):
                    if node.func.attr in method_names and node.args:
                        text = _literal_string(node.args[0])
                        if text and _needs_translation(text):
                            findings.append(f"{path}:{node.lineno}: method literal {text!r}")

                    if (
                        isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "QMessageBox"
                        and node.func.attr in {"critical", "information", "question", "warning"}
                    ):
                        for arg_index in (1, 2):
                            if len(node.args) > arg_index:
                                text = _literal_string(node.args[arg_index])
                                if text and _needs_translation(text):
                                    findings.append(f"{path}:{node.lineno}: message box literal {text!r}")

                if is_chat_or_ui_file:
                    for keyword in node.keywords:
                        if keyword.arg == "message":
                            text = _literal_string(keyword.value)
                            if text and _needs_translation(text):
                                findings.append(f"{path}:{node.lineno}: message literal {text!r}")

    assert findings == [], "\n".join(findings)


def test_translation_keys_referenced_from_src_exist_in_english_and_spanish() -> None:
    import ast
    from pathlib import Path

    from mira.ui import i18n as i18n_module

    repo_root = Path(__file__).resolve().parents[1]
    referenced_keys: set[str] = set()

    def _string_arg(args: Sequence[ast.AST], index: int) -> str | None:
        if len(args) <= index:
            return None
        node = args[index]
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    for path in (repo_root / "src").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            func_name = None
            match node.func:
                case ast.Name(id=name):
                    func_name = name
                case ast.Attribute(attr=name):
                    func_name = name

            key = None
            if func_name in {"tr", "translate"}:
                key = _string_arg(node.args, 0)
            elif func_name in {"_tr_db", "_transfer_tr", "_component_tr", "_executor_tr", "_message_text"}:
                key = _string_arg(node.args, 1)

            if key and "." in key:
                referenced_keys.add(key)

    missing: list[str] = []
    for key in sorted(referenced_keys):
        if key not in i18n_module._TRANSLATIONS["en"]:
            missing.append(f"missing en: {key}")
        if key not in i18n_module._TRANSLATIONS["es"]:
            missing.append(f"missing es: {key}")

    assert missing == [], "\n".join(missing)


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
