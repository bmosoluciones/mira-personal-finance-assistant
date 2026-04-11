# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

from pathlib import Path

import mira as mira_module


def _patch_repo_root(monkeypatch, repo_root: Path) -> None:
    class _FakePath:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def resolve(self) -> Path:
            return repo_root / "src" / "mira" / "__init__.py"

    monkeypatch.setattr(mira_module, "Path", _FakePath)


def test_detect_local_version_reads_pyproject_from_repo_root(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "src" / "mira").mkdir(parents=True)
    (repo_root / "pyproject.toml").write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")
    _patch_repo_root(monkeypatch, repo_root)

    assert mira_module._detect_local_version() == "1.2.3"


def test_detect_local_version_returns_none_for_missing_or_blank_version(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "src" / "mira").mkdir(parents=True)
    _patch_repo_root(monkeypatch, repo_root)

    assert mira_module._detect_local_version() is None

    (repo_root / "pyproject.toml").write_text('[project]\nversion = "   "\n', encoding="utf-8")
    assert mira_module._detect_local_version() is None


def test_detect_version_falls_back_to_installed_metadata(monkeypatch) -> None:
    monkeypatch.setattr(mira_module, "_detect_local_version", lambda: None)
    monkeypatch.setattr(mira_module, "version", lambda _package_name: "9.9.9")

    assert mira_module._detect_version() == "9.9.9"


def test_detect_version_returns_zero_when_package_metadata_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(mira_module, "_detect_local_version", lambda: None)

    def _raise(_package_name: str) -> str:
        raise mira_module.PackageNotFoundError()

    monkeypatch.setattr(mira_module, "version", _raise)

    assert mira_module._detect_version() == "0.0.0"
