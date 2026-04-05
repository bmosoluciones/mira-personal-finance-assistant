# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""
Unit tests for tag CRUD and tag-based transaction filtering.
"""

import pytest
from mira.db.database import Database


@pytest.fixture
def db(tmp_path):
    d = Database(path=tmp_path / "test_tags.db")
    d.connect()
    yield d
    d.close()


def test_tag_crud(db):
    # Create
    tag = db.tag.create("Trabajo", color="#FF0000")
    assert tag["name"] == "Trabajo"
    assert tag["color"] == "#FF0000"
    # Read
    tags = db.tag.list()
    assert any(t["name"] == "Trabajo" for t in tags)
    # Update
    db.tag.update(tag["id"], "Trabajo Editado", "#00FF00")
    tag2 = db.tag.get(tag["id"])
    assert tag2["name"] == "Trabajo Editado"
    assert tag2["color"] == "#00FF00"
    # Delete
    db.tag.delete(tag["id"])
    assert db.tag.get(tag["id"]) is None


def test_transaction_tag_filtering(db):
    # Setup tags and transactions
    tag1 = db.tag.create("Familia", color="#123456")
    tag2 = db.tag.create("Transporte", color="#654321")
    acc = db.account.get_or_create("Cuenta Test")
    cat = db.category.create("Alimentación", "expense")
    tx1 = db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=100,
        description="Supermercado",
        category=cat["name"],
        tx_date="2026-03-16",
        note="",
        subcategory=None,
        payment_method="cash",
        receipt_path=None,
        exchange_rate=None,
        converted_amount=None,
    )
    tx2 = db.transaction.create(
        account_id=acc["id"],
        tx_type="income",
        amount=200,
        description="Salario",
        category=None,
        tx_date="2026-03-16",
        note="",
        subcategory=None,
        payment_method="cash",
        receipt_path=None,
        exchange_rate=None,
        converted_amount=None,
    )
    db.tag.add_to_transaction(tx1["id"], tag1["id"])
    db.tag.add_to_transaction(tx2["id"], tag1["id"])
    db.tag.add_to_transaction(tx2["id"], tag2["id"])
    # get_transactions_tags_bulk returns dict[int, list[dict]] where each
    # tag dict has "id" (the tag id), "name", "color", etc.
    bulk = db.tag.list_bulk_for_transactions([tx1["id"], tx2["id"]])
    # Filter by tag1 (Familia): should return both tx1 and tx2
    tx_ids_tag1 = [tx_id for tx_id, tags in bulk.items() if any(t["id"] == tag1["id"] for t in tags)]
    assert set(tx_ids_tag1) == {tx1["id"], tx2["id"]}
    # Filter by tag2 (Transporte): should return only tx2
    tx_ids_tag2 = [tx_id for tx_id, tags in bulk.items() if any(t["id"] == tag2["id"] for t in tags)]
    assert set(tx_ids_tag2) == {tx2["id"]}
