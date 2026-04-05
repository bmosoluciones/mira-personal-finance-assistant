# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import csv
from sqlite3 import Error as SqliteError

import pytest

from mira.db.errors import BudgetValidationError
from mira.error_policy import ErrorDescriptor, describe


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (BudgetValidationError("budget"), ErrorDescriptor("Budget Error", "budget", "warning")),
        (SqliteError("db"), ErrorDescriptor("Database Error", "db")),
        (csv.Error("csv"), ErrorDescriptor("CSV Error", "csv")),
        (
            UnicodeDecodeError("utf-8", b"x", 0, 1, "bad"),
            ErrorDescriptor("Encoding Error", "'utf-8' codec can't decode byte 0x78 in position 0: bad"),
        ),
        (OSError("disk"), ErrorDescriptor("File Error", "disk")),
        (ValueError("bad"), ErrorDescriptor("Invalid Data", "bad", "warning")),
        (RuntimeError("boom"), ErrorDescriptor("Operation Failed", "boom")),
        (Exception("unexpected"), ErrorDescriptor("Unexpected Error", "unexpected")),
    ],
)
def test_describe_maps_exceptions_to_consistent_descriptors(error: Exception, expected: ErrorDescriptor) -> None:
    assert describe(error) == expected
