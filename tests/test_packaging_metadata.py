# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Keep requirements.txt honest about what pyproject.toml declares."""

from __future__ import annotations

import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CORE_EXTRAS = ("gui",)


def _requirement_name(requirement: str) -> str:
    return requirement.split(";", 1)[0].strip().split("[", 1)[0].strip().lower()


def _declared() -> tuple[set[str], set[str]]:
    data = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    core = {_requirement_name(item) for item in project["dependencies"]}
    extras = project["optional-dependencies"]
    optional = {_requirement_name(item) for name in _CORE_EXTRAS for item in extras[name]}
    development = {_requirement_name(item) for item in extras["dev"]}
    return core | optional | development, {item.split(";", 1)[0].strip() for item in extras["docs"]}


def _requirements_txt() -> set[str]:
    lines = (_REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")}


def test_requirements_txt_matches_pyproject() -> None:
    """requirements.txt is the dev environment, so it must cover exactly that."""
    declared, docs_extra = _declared()

    listed = _requirements_txt()
    missing = {item for item in declared if not any(_requirement_name(requirement) == item for requirement in listed)}
    assert missing == set(), f"requirements.txt is missing {sorted(missing)}"

    extra = {item for item in listed if _requirement_name(item) not in declared}
    assert extra == set(), f"requirements.txt lists what pyproject.toml does not: {sorted(extra)}"
    assert docs_extra.isdisjoint(_requirement_name(item) for item in listed)


def test_requirements_txt_never_installs_a_runtime_only_extra() -> None:
    """mcp was declared as an extra nobody imports; keep such entries out."""
    listed = " ".join(_requirements_txt()).lower()

    assert "mcp" not in listed


def test_pyproject_gui_extra_is_not_a_global_dependency() -> None:
    data = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = " ".join(data["project"]["dependencies"]).lower()
    gui_extra = " ".join(data["project"]["optional-dependencies"]["gui"]).lower()

    assert "pyside6" not in dependencies
    assert "qt-material" not in dependencies
    assert "pyside6" in gui_extra
    assert "qt-material" in gui_extra
