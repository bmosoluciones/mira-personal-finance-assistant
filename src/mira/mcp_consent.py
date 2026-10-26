# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Consent check shared by the CLI and MCP server."""

from __future__ import annotations

from mira.db.database import Database


def mcp_enabled(db: Database) -> bool:
    """Return whether the user enabled MCP and accepted its access notice."""
    return str(db.setting.get("mcp_enabled") or "0") == "1" and str(db.setting.get("mcp_third_party_ack") or "0") == "1"
