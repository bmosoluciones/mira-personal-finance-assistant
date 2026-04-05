# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""MIRA – Personal Finance Assistant."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import tomllib

_PACKAGE_NAME = "mira-personal-finance-assistant"


def _detect_local_version() -> str | None:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if not pyproject_path.is_file():
        return None
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = data.get("project", {})
    detected = project.get("version")
    if isinstance(detected, str) and detected.strip():
        return detected.strip()
    return None


def _detect_version() -> str:
    local_version = _detect_local_version()
    if local_version is not None:
        return local_version
    try:
        return version(_PACKAGE_NAME)
    except PackageNotFoundError:
        return "0.0.0"


__version__ = _detect_version()
