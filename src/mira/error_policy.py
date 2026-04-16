# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Centralized mapping from exceptions to user-facing messages."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from sqlite3 import Error

from mira.db.errors import BudgetError
from mira.ui.i18n import normalize_language, tr


@dataclass(frozen=True)
class ErrorDescriptor:
    """Represent the ErrorDescriptor class."""

    title: str

    message: str
    level: str = "error"


def describe(error: Exception, *, language: str = "en") -> ErrorDescriptor:
    """Convert internal exceptions into consistent UI copy."""
    lang = normalize_language(language)

    match error:
        case BudgetError():
            return ErrorDescriptor(
                title=tr("error.budget.title", lang, default="Budget Error"),
                message=str(error),
                level="warning",
            )

        case Error():
            return ErrorDescriptor(
                title=tr("error.database.title", lang, default="Database Error"),
                message=str(error),
            )

        case csv.Error():
            return ErrorDescriptor(
                title=tr("error.csv.title", lang, default="CSV Error"),
                message=str(error),
            )

        case UnicodeError():
            return ErrorDescriptor(
                title=tr("error.encoding.title", lang, default="Encoding Error"),
                message=str(error),
            )

        case OSError():
            return ErrorDescriptor(
                title=tr("error.file.title", lang, default="File Error"),
                message=str(error),
            )

        case ValueError():
            return ErrorDescriptor(
                title=tr("error.invalid_data.title", lang, default="Invalid Data"),
                message=str(error),
                level="warning",
            )

        case RuntimeError():
            return ErrorDescriptor(
                title=tr("error.operation_failed.title", lang, default="Operation Failed"),
                message=str(error),
            )

        case _:
            return ErrorDescriptor(
                title=tr("error.unexpected.title", lang, default="Unexpected Error"),
                message=str(error),
            )
