# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Upgrade existing installations after retiring desktop chat."""

import sqlite3

from mira.db.database import Database
from mira.db.model import SCHEMA_VERSION


def _legacy_database(path) -> None:
    db = Database(path=path)
    db.connect()
    db.setting.set("llm_provider", "openai_compatible")
    db.setting.set("llm_model", "old-model")
    db.setting.set("llm_interaction_mode", "chat")
    db.setting.set("mcp_enabled", "1")
    db.setting.set("mcp_third_party_ack", "1")
    db.close()
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA user_version = 5")


def test_upgrade_removes_chat_settings_and_secret_but_preserves_mcp(tmp_path) -> None:
    path = tmp_path / "mira.db"
    _legacy_database(path)
    secret = tmp_path / "llm-secrets.json"
    secret.write_text('{"api_key": "old-key"}', encoding="utf-8")

    db = Database(path=path)
    db.connect()
    try:
        assert db.setting.get("llm_provider") is None
        assert db.setting.get("llm_model") is None
        assert db.setting.get("llm_interaction_mode") is None
        assert db.setting.get("mcp_enabled") == "1"
        assert db.setting.get("mcp_third_party_ack") == "1"
        assert not secret.exists()
        with sqlite3.connect(path) as conn:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    finally:
        db.close()


def test_restore_old_backup_removes_chat_settings(tmp_path) -> None:
    backup = tmp_path / "old.db"
    _legacy_database(backup)
    target = tmp_path / "profile" / "mira.db"
    target.parent.mkdir()
    db = Database(path=target)
    db.connect()
    secret = target.parent / "llm-secrets.json"
    secret.write_text('{"api_key": "old-key"}', encoding="utf-8")
    try:
        db.backup.restore(backup)
        assert db.setting.get("llm_provider") is None
        assert db.setting.get("mcp_enabled") == "1"
        assert not secret.exists()
    finally:
        db.close()
