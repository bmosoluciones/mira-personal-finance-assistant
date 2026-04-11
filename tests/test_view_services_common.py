# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

from mira.app.view_services._common import (
    ANALYTICS_PALETTE,
    AnalyticsSemanticRole,
    WaterfallStepKind,
    try_parse_waterfall_step_kind,
)


def test_analytics_palette_preserves_expected_multicolor_sequence() -> None:
    assert ANALYTICS_PALETTE.multicolor == (
        "#2EC4B6",
        "#4D96FF",
        "#FF6B6B",
        "#F4A261",
        "#8AC926",
        "#00B8D9",
        "#FF9F1C",
        "#FF4D8D",
    )
    assert ANALYTICS_PALETTE.palette_hex(0) == "#2EC4B6"
    assert ANALYTICS_PALETTE.palette_hex(7) == "#FF4D8D"
    assert ANALYTICS_PALETTE.palette_hex(8) == "#2EC4B6"
    assert ANALYTICS_PALETTE.palette_hex(9) == "#4D96FF"


def test_analytics_palette_preserves_semantic_and_waterfall_hex_values() -> None:
    assert ANALYTICS_PALETTE.semantic_hex(AnalyticsSemanticRole.INCOME) == "#2EC4B6"
    assert ANALYTICS_PALETTE.semantic_hex(AnalyticsSemanticRole.EXPENSE) == "#FF6B6B"
    assert ANALYTICS_PALETTE.semantic_hex(AnalyticsSemanticRole.NET) == "#4D96FF"
    assert ANALYTICS_PALETTE.semantic_hex(AnalyticsSemanticRole.SECONDARY) == "#00B8D9"
    assert ANALYTICS_PALETTE.semantic_hex(AnalyticsSemanticRole.SAVINGS) == "#8AC926"
    assert ANALYTICS_PALETTE.waterfall_hex(WaterfallStepKind.INCOME_TOTAL) == "#2EC4B6"
    assert ANALYTICS_PALETTE.waterfall_hex(WaterfallStepKind.EXPENSE) == "#FF6B6B"
    assert ANALYTICS_PALETTE.waterfall_hex(WaterfallStepKind.FINANCING) == "#F4A261"
    assert ANALYTICS_PALETTE.waterfall_hex(WaterfallStepKind.SAVINGS_ALLOCATION) == "#8AC926"
    assert ANALYTICS_PALETTE.waterfall_hex(WaterfallStepKind.FINAL_TOTAL) == "#00B8D9"


def test_try_parse_waterfall_step_kind_handles_known_and_unknown_values() -> None:
    assert try_parse_waterfall_step_kind("income_total") is WaterfallStepKind.INCOME_TOTAL
    assert try_parse_waterfall_step_kind("FINAL_TOTAL") is WaterfallStepKind.FINAL_TOTAL
    assert try_parse_waterfall_step_kind("unknown") is None
    assert try_parse_waterfall_step_kind(None) is None
