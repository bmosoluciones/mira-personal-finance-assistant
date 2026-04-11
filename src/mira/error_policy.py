# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Centralized mapping from exceptions to user-facing messages."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from sqlite3 import Error
from mira.db.errors import BudgetError


@dataclass(frozen=True)
class ErrorDescriptor:
    title: str
    message: str
    level: str = "error"


def describe(error: Exception) -> ErrorDescriptor:
    """Convert internal exceptions into consistent UI copy."""

    match error:
        case BudgetError():
            return ErrorDescriptor(
                title="Budget Error",
                message=str(error),
                level="warning",
            )

        case Error():
            return ErrorDescriptor(
                title="Database Error",
                message=str(error),
            )

        case csv.Error():
            return ErrorDescriptor(
                title="CSV Error",
                message=str(error),
            )

        case UnicodeError():
            return ErrorDescriptor(
                title="Encoding Error",
                message=str(error),
            )

        case OSError():
            return ErrorDescriptor(
                title="File Error",
                message=str(error),
            )

        case ValueError():
            return ErrorDescriptor(
                title="Invalid Data",
                message=str(error),
                level="warning",
            )

        case RuntimeError():
            return ErrorDescriptor(
                title="Operation Failed",
                message=str(error),
            )

        case _:
            return ErrorDescriptor(
                title="Unexpected Error",
                message=str(error),
            )
