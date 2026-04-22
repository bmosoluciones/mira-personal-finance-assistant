# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Domain-specific exceptions for database operations."""

from __future__ import annotations


class BudgetError(Exception):
    """Base exception for budget domain errors."""


class DuplicateBudgetCodeError(BudgetError):
    """Raised when a budget code is already registered."""


class BudgetValidationError(BudgetError, ValueError):
    """Raised when budget input data does not satisfy business rules."""


class CategoryError(Exception):
    """Base exception for category domain errors."""


class DuplicateCategoryNameError(CategoryError):
    """Raised when a category name is already registered."""


class TagError(Exception):
    """Base exception for tag domain errors."""


class DuplicateTagNameError(TagError):
    """Raised when a tag name is already registered."""


class DatabaseSchemaError(RuntimeError):
    """Raised when a database file uses an incompatible on-disk schema."""


class MasterDataSyncConflictError(RuntimeError):
    """Raised when optimistic master-data versioning cannot be reconciled."""
