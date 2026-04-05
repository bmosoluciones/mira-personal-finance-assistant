# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

from mira.ai.executor import ActionResult
from mira.app.application_controller import ApplicationController


class _FakeDb:
    pass


def test_application_controller_maps_report_action() -> None:
    controller = ApplicationController(_FakeDb(), object())

    directive = controller.handle_result(
        ActionResult(success=True, action="report", message="Reporte listo", data={"kind": "cash_flow"})
    )

    assert directive.kind == "show_report"
    assert directive.chat_message == "Reporte listo"
    assert directive.report_payload == {"kind": "cash_flow"}
    assert directive.show_quick_actions is False
    assert directive.refresh_all is True


def test_application_controller_maps_data_analysis_action() -> None:
    controller = ApplicationController(_FakeDb(), object())

    directive = controller.handle_result(
        ActionResult(
            success=True,
            action="data_analysis",
            message="Abrir analisis",
            data={"period": {"preset": "last_month"}},
        )
    )

    assert directive.kind == "run_analysis"
    assert directive.chat_message == "Abrir analisis"
    assert directive.analysis_period == {"preset": "last_month"}
    assert directive.show_quick_actions is False


def test_application_controller_maps_other_actions_to_message() -> None:
    controller = ApplicationController(_FakeDb(), object())

    directive = controller.handle_result(ActionResult(success=False, action="none", message="Sin accion"))

    assert directive.kind == "message"
    assert directive.chat_message == "Sin accion"
    assert directive.show_quick_actions is True
    assert directive.report_payload is None
    assert directive.analysis_period is None
