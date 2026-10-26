# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Consent rules for the independent MCP server."""

from mira.db.database import Database
from mira.mcp_consent import mcp_enabled


def test_mcp_requires_enablement_and_acknowledgment(tmp_path) -> None:
    db = Database(path=tmp_path / "mcp-consent.db")
    db.connect()
    try:
        assert mcp_enabled(db) is False
        db.setting.set("mcp_enabled", "1")
        assert mcp_enabled(db) is False
        db.setting.set("mcp_third_party_ack", "1")
        assert mcp_enabled(db) is True
    finally:
        db.close()
