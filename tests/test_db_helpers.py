# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

from pathlib import Path

import pytest

from mira.db.helpers import (
    CURRENCY_CODES,
    CURRENCY_SEED,
    FEEDBACK_MILESTONES,
    SAVINGS_GOALS_DEFAULTS,
    AccountType,
    CurrencyRegion,
    MessagePriority,
    canonical_account_type,
    delete_database_file,
    fold_text,
    get_default_db_path,
    parse_account_type,
)


def test_canonical_account_type_maps_card_to_credit() -> None:
    assert canonical_account_type("card") == "credit"
    assert parse_account_type("cash") is AccountType.CASH


def test_parse_account_type_accepts_enum_and_defaults_to_bank() -> None:
    assert parse_account_type(AccountType.CREDIT) is AccountType.CREDIT
    assert parse_account_type("") is AccountType.BANK
    assert canonical_account_type(None) == AccountType.BANK.value


def test_canonical_account_type_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        canonical_account_type("investment")


def test_fold_text_normalizes_case_accents_and_spacing() -> None:
    assert fold_text("  Crédito   Débito ") == "credito debito"


def test_currency_codes_are_derived_from_typed_currency_seed() -> None:
    assert CURRENCY_SEED
    assert CURRENCY_SEED[0].code == "USD"
    assert CURRENCY_SEED[0].region is CurrencyRegion.AMERICAS
    assert CURRENCY_SEED[-1].region is CurrencyRegion.EUROPE
    assert CURRENCY_CODES == tuple(entry.code for entry in CURRENCY_SEED)


def test_savings_defaults_and_feedback_enums_preserve_expected_values() -> None:
    assert SAVINGS_GOALS_DEFAULTS.name_for("es") == "Metas de ahorro"
    assert SAVINGS_GOALS_DEFAULTS.name_for("fr") == "Savings Goals"
    assert SAVINGS_GOALS_DEFAULTS.all_names() == ("Metas de ahorro", "Savings Goals")
    assert SAVINGS_GOALS_DEFAULTS.color == "#2E8B57"
    assert int(MessagePriority.ACHIEVEMENT_CRITICAL) == 320
    assert int(MessagePriority.INSIGHT_WARNING) == 80
    assert FEEDBACK_MILESTONES.nl_transactions == (100, 500, 1000, 3000, 5000)
    assert FEEDBACK_MILESTONES.mira_report_views == (10, 100, 500, 1000)
    assert FEEDBACK_MILESTONES.savings_contributions == (1, 10, 50, 100)


def test_get_default_db_path_uses_xdg_data_home(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))

    path = get_default_db_path()

    assert path == tmp_path / "xdg-data" / "mira" / "mira.db"
    assert path.parent.is_dir()


def test_get_default_db_path_falls_back_to_local_share(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr("mira.db.helpers.sys.platform", "linux")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    path = get_default_db_path()

    assert isinstance(path, Path)
    assert path == tmp_path / ".local" / "share" / "mira" / "mira.db"
    assert path.parent.is_dir()


def test_get_default_db_path_uses_windows_appdata_when_no_legacy_db(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    monkeypatch.setattr("mira.db.helpers.sys.platform", "win32")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    path = get_default_db_path()

    assert path == tmp_path / "AppData" / "Roaming" / "mira" / "mira.db"
    assert path.parent.is_dir()


def test_get_default_db_path_ignores_legacy_windows_db(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    monkeypatch.setattr("mira.db.helpers.sys.platform", "win32")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    legacy_path = tmp_path / ".mira" / "mira.db"
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text("legacy-db", encoding="utf-8")

    path = get_default_db_path()

    expected_path = tmp_path / "AppData" / "Roaming" / "mira" / "mira.db"
    assert path == expected_path
    assert not expected_path.exists()
    assert legacy_path.exists()


def test_get_default_db_path_keeps_existing_appdata_db_and_ignores_legacy(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    monkeypatch.setattr("mira.db.helpers.sys.platform", "win32")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    appdata_db_path = tmp_path / "AppData" / "Roaming" / "mira" / "mira.db"
    appdata_db_path.parent.mkdir(parents=True)
    appdata_db_path.write_text("appdata-db", encoding="utf-8")

    legacy_path = tmp_path / ".mira" / "mira.db"
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text("legacy-db", encoding="utf-8")

    path = get_default_db_path()

    assert path == appdata_db_path
    assert path.read_text(encoding="utf-8") == "appdata-db"
    assert legacy_path.exists()


def test_get_default_db_path_uses_macos_fallback(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr("mira.db.helpers.sys.platform", "darwin")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    path = get_default_db_path()

    assert path == tmp_path / "Library" / "Application Support" / "mira" / "mira.db"
    assert path.parent.is_dir()


def test_delete_database_file_removes_main_file_and_sqlite_sidecars(tmp_path) -> None:
    source = tmp_path / "mira.db"
    wal = tmp_path / "mira.db-wal"
    shm = tmp_path / "mira.db-shm"
    source.write_text("main", encoding="utf-8")
    wal.write_text("wal", encoding="utf-8")
    shm.write_text("shm", encoding="utf-8")

    delete_database_file(source)

    assert not source.exists()
    assert not wal.exists()
    assert not shm.exists()
