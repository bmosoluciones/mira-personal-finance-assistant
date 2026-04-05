# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import pytest

from mira.db.database import Database


@pytest.fixture
def db(tmp_path):
    d = Database(path=tmp_path / "test_regressions.db")
    d.connect()
    yield d
    d.close()


def test_filter_by_tag_does_not_exclude_untagged_when_no_filter(db):
    acc = db.account.get_or_create("General")
    tagged = db.transaction.create(account_id=acc["id"], tx_type="expense", amount=10, description="tagged")
    untagged = db.transaction.create(account_id=acc["id"], tx_type="expense", amount=20, description="untagged")
    tag = db.tag.create("hogar")
    db.tag.add_to_transaction(tagged["id"], tag["id"])

    txs = db.transaction.list(limit=100)
    ids = {tx["id"] for tx in txs}

    assert tagged["id"] in ids
    assert untagged["id"] in ids


def test_filter_by_tag_returns_only_matching(db):
    acc = db.account.get_or_create("General")
    tx1 = db.transaction.create(account_id=acc["id"], tx_type="expense", amount=10, description="a")
    tx2 = db.transaction.create(account_id=acc["id"], tx_type="expense", amount=20, description="b")
    tag = db.tag.create("transporte")
    db.tag.add_to_transaction(tx1["id"], tag["id"])

    txs = db.transaction.list(limit=100, tag_id=tag["id"])

    assert {tx["id"] for tx in txs} == {tx1["id"]}
    assert tx2["id"] not in {tx["id"] for tx in txs}


def test_combined_filters_tag_and_category(db):
    acc = db.account.get_or_create("General")
    food = db.category.create("Food", "expense")
    travel = db.category.create("Travel", "expense")
    tx1 = db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=10,
        description="a",
        category=food["name"],
    )
    tx2 = db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=20,
        description="b",
        category=travel["name"],
    )
    tag = db.tag.create("shared")
    db.tag.add_to_transaction(tx1["id"], tag["id"])
    db.tag.add_to_transaction(tx2["id"], tag["id"])

    txs = db.transaction.list(limit=100, tag_id=tag["id"], category=food["name"])

    assert [tx["id"] for tx in txs] == [tx1["id"]]


def test_descendants_returns_full_tree(db):
    root = db.category.create("Root", "expense")
    db.category.create("Child", "expense", parent_id=root["id"])

    names = db.category.descendant_names(root["id"])

    assert set(names) == {"Root", "Child"}


def test_descendants_single_node(db):
    root = db.category.create("Solo", "expense")
    assert db.category.descendant_names(root["id"]) == ["Solo"]


def test_cannot_create_third_level_category(db):
    root = db.category.create("Root", "expense")
    child = db.category.create("Child", "expense", parent_id=root["id"])

    with pytest.raises(ValueError, match="maximum depth"):
        db.category.create("Grandchild", "expense", parent_id=child["id"])


def test_reparent_with_children_cannot_create_third_level_hierarchy(db):
    x = db.category.create("X", "expense")
    b = db.category.create("B", "expense")
    c = db.category.create("C", "expense", parent_id=b["id"])

    assert c["parent_id"] == b["id"]

    with pytest.raises(ValueError, match="maximum depth"):
        db.category.update(b["id"], b["name"], b["type"], b["color"], parent_id=x["id"])


def test_icon_validation_is_permissive_but_bounded(db):
    complex_icon = "👨🏽‍💻"
    cat = db.category.create("Valid Icon", "expense", icon=complex_icon)
    tag = db.tag.create("Valid Tag Icon", icon=complex_icon)

    assert cat["icon"] == complex_icon
    assert tag["icon"] == complex_icon

    too_long_icon = "x" * 33
    with pytest.raises(ValueError, match="cannot exceed 32"):
        db.category.create("Invalid", "expense", icon=too_long_icon)
    with pytest.raises(ValueError, match="cannot exceed 32"):
        db.tag.create("Invalid", icon=too_long_icon)
