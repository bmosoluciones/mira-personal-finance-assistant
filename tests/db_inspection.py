# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import sqlite3
from typing import Any


def execute_sql(db: Any, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    with sqlite3.connect(db.path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(sql, params)
        rows = cursor.fetchall() if cursor.description is not None else []
        conn.commit()
    return rows


def fetch_all_dicts(db: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in execute_sql(db, sql, params)]


def fetch_one_dict(db: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    rows = fetch_all_dicts(db, sql, params)
    return rows[0] if rows else {}


def fetch_scalar(db: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
    row = fetch_one_dict(db, sql, params)
    return next(iter(row.values())) if row else None


def break_backend_connection_for_test(db: Any) -> None:
    db.close()


def backend_connection_state(db: Any) -> tuple[bool, bool]:
    missing_db = False
    missing_connection = False
    try:
        db._backend._require_db()
    except RuntimeError:
        missing_db = True
    try:
        db._backend._require_connection()
    except RuntimeError:
        missing_connection = True
    return (missing_db, missing_connection)
