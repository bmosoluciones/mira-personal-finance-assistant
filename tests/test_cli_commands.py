# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Tests for the headless finance commands behind mira-cli.

The important invariant here is that a structured caller never records a
movement against an account it named incorrectly: an unknown account must be an
error, not a silent fallback to the default one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mira import cli_commands
from mira.db.database import Database


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "cli-commands.db")
    database.connect()
    yield database
    database.close()


def _account_names(db: Database) -> list[str]:
    return [str(row["name"]) for row in db.account.list()]


def test_add_movement_records_against_the_named_account(db: Database) -> None:
    db.account.create("Cash", "cash", 100.0, "USD")

    result = cli_commands.add_movement(
        db,
        kind="add_expense",
        amount="12.50",
        account="Cash",
        description="Coffee",
        category=None,
        tx_date=None,
        note=None,
    )

    assert result["ok"] is True
    assert "Cash" in _account_names(db)
    assert db.transaction.list(limit=10)


def test_add_movement_rejects_an_unknown_account_without_writing(db: Database) -> None:
    db.account.create("Cash", "cash", 100.0, "USD")
    before = len(db.transaction.list(limit=50))

    with pytest.raises(ValueError, match="Account not found: No Existe"):
        cli_commands.add_movement(
            db,
            kind="add_expense",
            amount="12.50",
            account="No Existe",
            description=None,
            category=None,
            tx_date=None,
            note=None,
        )

    assert len(db.transaction.list(limit=50)) == before


def test_add_movement_rejects_an_empty_account_without_writing(db: Database) -> None:
    db.account.create("Cash", "cash", 100.0, "USD")
    before = len(db.transaction.list(limit=50))

    with pytest.raises(ValueError, match="account name is required"):
        cli_commands.add_movement(
            db,
            kind="add_expense",
            amount="5",
            account="   ",
            description=None,
            category=None,
            tx_date=None,
            note=None,
        )

    assert len(db.transaction.list(limit=50)) == before


def test_add_movement_rejects_an_unknown_kind_instead_of_no_oping(db: Database) -> None:
    db.account.create("Cash", "cash", 100.0, "USD")

    with pytest.raises(ValueError, match="Unsupported movement kind"):
        cli_commands.add_movement(
            db,
            kind="expense",
            amount="5",
            account="Cash",
            description=None,
            category=None,
            tx_date=None,
            note=None,
        )


def test_require_known_account_accepts_a_known_name(db: Database) -> None:
    db.account.create("Cash", "cash", 100.0, "USD")

    cli_commands._require_known_account(db, "Cash")


def test_transfer_moves_money_and_rejects_unknown_endpoints(db: Database) -> None:
    db.account.create("Banco", "bank", 500.0, "USD")
    db.account.create("Ahorro", "bank", 50.0, "USD")

    result = cli_commands.transfer(db, source="Banco", target="Ahorro", amount="25", tx_date=None, note=None)
    assert result["ok"] is True

    with pytest.raises(ValueError, match="Account not found"):
        cli_commands.transfer(db, source="Banco", target="No Existe", amount="25", tx_date=None, note=None)


def test_dump_renders_json_and_human_readable_forms(db: Database) -> None:
    payload = {"ok": True, "message": "Recorded", "data": {}}

    assert json.loads(cli_commands.dump(payload, as_json=True))["message"] == "Recorded"
    assert cli_commands.dump(payload, as_json=False) == "Recorded"
    assert cli_commands.dump({"ok": True, "transactions": []}, as_json=False) == "No transactions."
    rows = cli_commands.dump(
        {"ok": True, "transactions": [{"date": "2026-01-02", "type": "expense", "amount": "3.00", "description": "Tea"}]},
        as_json=False,
    )
    assert rows == "2026-01-02 expense 3.00 Tea"
    assert json.loads(cli_commands.dump({"ok": True, "summary": {"total": 1}}, as_json=False)) == {"total": 1}


def test_today_iso_is_an_iso_date() -> None:
    assert len(cli_commands.today_iso()) == 10
    assert cli_commands.today_iso()[4] == "-"


def test_commands_import_no_qt() -> None:
    source = Path(cli_commands.__file__).read_text(encoding="utf-8")

    assert "PySide6" not in source
