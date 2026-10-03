# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Backward-compatible re-export. New code should import mira.i18n."""

from mira.i18n import SUPPORTED_LANGUAGES, normalize_language, tr

__all__ = ["SUPPORTED_LANGUAGES", "normalize_language", "tr"]
