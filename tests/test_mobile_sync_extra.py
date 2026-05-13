# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

import pytest
import time
from datetime import timedelta
from mira.db.database import Database
from mira.services.mobile_sync import MobileSyncService, MobileSyncError, MobileSyncAuthError, MobileSyncConflictError, RateLimitRule
from mira.sync_utils import generate_ulid

@pytest.fixture
def db(tmp_path):
    database = Database(path=tmp_path / "sync-extra.db")
    database.connect()
    database.setting.seed_initial_data()
    yield database
    database.close()

def test_mobile_sync_service_push_catalog_validation(db):
    service = MobileSyncService(db)
    pairing = service.start_pairing()
    pair_res = service.pair_device({"pairing_token": pairing.pairing_token, "device_name": "Test"})
    token = pair_res["token"]

    with pytest.raises(MobileSyncError) as exc:
        service.push_catalog(token, {"operations": "not-a-list"})
    assert "operations" in str(exc.value)

def test_mobile_sync_service_push_transactions_validation(db):
    service = MobileSyncService(db)
    pairing = service.start_pairing()
    pair_res = service.pair_device({"pairing_token": pairing.pairing_token, "device_name": "Test"})
    token = pair_res["token"]

    with pytest.raises(MobileSyncError) as exc:
        service.push_transactions(token, {"operations": "not-a-list"})
    assert "operations" in str(exc.value)

def test_mobile_sync_rate_limiter(db):
    from mira.services.mobile_sync import _MobileSyncRateLimiter
    limiter = _MobileSyncRateLimiter()
    rule = RateLimitRule(max_requests=2, window=timedelta(seconds=10))
    key = ("test",)

    assert limiter.check(key, rule).allowed is True
    assert limiter.check(key, rule).allowed is True
    decision = limiter.check(key, rule)
    assert decision.allowed is False
    assert decision.retry_after_seconds > 0

    limiter.clear()
    assert limiter.check(key, rule).allowed is True

def test_mobile_sync_resolve_account_failures(db):
    service = MobileSyncService(db)
    pairing = service.start_pairing()
    token = service.pair_device({"pairing_token": pairing.pairing_token})["token"]

    # Missing sync_id
    payload = {"operations": [{"operation": "create", "transaction": {"amount": 100}}]}
    res = service.push_transactions(token, payload)
    assert res["results"][0]["status"] == "rejected"
    assert "sync_id" in res["results"][0]["reason"]

    # Unknown account_global_id
    payload = {"operations": [{"operation": "create", "sync_id": generate_ulid(), "transaction": {"amount": 100, "account_global_id": "missing", "type": "expense", "date": "2025-01-01"}}]}
    res = service.push_transactions(token, payload)
    assert res["results"][0]["status"] == "conflict"
    assert res["results"][0]["code"] == "unknown_account"

def test_mobile_sync_resolve_category_failures(db):
    service = MobileSyncService(db)
    pairing = service.start_pairing()
    token = service.pair_device({"pairing_token": pairing.pairing_token})["token"]
    acc = db.account.create("Acc", "bank")

    # Unknown category_global_id
    payload = {
        "operations": [
            {
                "operation": "create",
                "sync_id": generate_ulid(),
                "transaction": {
                    "amount": 100,
                    "type": "expense",
                    "date": "2025-01-01",
                    "account_global_id": acc["global_id"],
                    "category_global_id": "missing"
                }
            }
        ]
    }
    res = service.push_transactions(token, payload)
    assert res["results"][0]["status"] == "conflict"
    assert res["results"][0]["code"] == "unknown_category"

    # Category type mismatch
    cat_inc = db.category.create("Inc", "income")
    payload["operations"][0]["transaction"]["category_global_id"] = cat_inc["global_id"]
    res = service.push_transactions(token, payload)
    assert res["results"][0]["status"] == "conflict"

def test_mobile_sync_resolve_tag_failures(db):
    service = MobileSyncService(db)
    pairing = service.start_pairing()
    token = service.pair_device({"pairing_token": pairing.pairing_token})["token"]
    acc = db.account.create("Acc", "bank")

    payload = {
        "operations": [
            {
                "operation": "create",
                "sync_id": generate_ulid(),
                "transaction": {
                    "amount": 100,
                    "type": "expense",
                    "date": "2025-01-01",
                    "account_global_id": acc["global_id"],
                    "tag_ids": [9999]
                }
            }
        ]
    }
    res = service.push_transactions(token, payload)
    assert res["results"][0]["status"] == "conflict"
    assert res["results"][0]["code"] == "unknown_tag"

def test_mobile_sync_account_conflicts(db):
    service = MobileSyncService(db)
    pairing = service.start_pairing()
    token = service.pair_device({"pairing_token": pairing.pairing_token})["token"]

    acc1 = db.account.create("Acc1", "bank")
    acc2 = db.account.create("Acc2", "bank")

    # Name conflict on update
    payload = {
        "operations": [
            {
                "entity_type": "account",
                "operation": "update",
                "global_id": acc1["global_id"],
                "base_version": acc1["sync_version"],
                "payload": {"name": "Acc2", "type": "bank"}
            }
        ]
    }
    res = service.push_catalog(token, payload)
    assert res["results"][0]["status"] == "conflict"

    # Version conflict
    payload["operations"][0]["payload"]["name"] = "NewName"
    payload["operations"][0]["base_version"] = acc1["sync_version"] - 1
    res = service.push_catalog(token, payload)
    assert res["results"][0]["status"] == "conflict"

    # Create existing with same details (idempotency)
    payload = {
        "operations": [
            {
                "entity_type": "account",
                "operation": "create",
                "global_id": acc1["global_id"],
                "payload": {"name": "Acc1", "type": "bank", "currency": "USD"}
            }
        ]
    }
    res = service.push_catalog(token, payload)
    assert res["results"][0]["code"] == "already_synced"

def test_mobile_sync_category_conflicts(db):
    service = MobileSyncService(db)
    pairing = service.start_pairing()
    token = service.pair_device({"pairing_token": pairing.pairing_token})["token"]

    cat1 = db.category.create("Cat1", "expense")
    cat2 = db.category.create("Cat2", "expense")

    # Name conflict on create
    payload = {
        "operations": [
            {
                "entity_type": "category",
                "operation": "create",
                "global_id": generate_ulid(),
                "payload": {"name": "Cat1", "type": "expense"}
            }
        ]
    }
    res = service.push_catalog(token, payload)
    assert res["results"][0]["status"] == "conflict"

def test_mobile_sync_service_stop(db):
    service = MobileSyncService(db)
    service.start_pairing()
    service.stop()
    # If not active, it should raise error
    with pytest.raises(MobileSyncError) as exc:
        service.status_payload()
    assert "not active" in str(exc.value)

def test_mobile_sync_transaction_update_and_delete(db):
    service = MobileSyncService(db)
    pairing = service.start_pairing()
    token = service.pair_device({"pairing_token": pairing.pairing_token})["token"]
    acc = db.account.create("Acc", "bank")
    tx = db.transaction.create(amount=10, tx_type="expense", account_id=acc["id"])

    # 1. Update conflict (stale version)
    payload = {
        "operations": [
            {
                "operation": "update",
                "sync_id": tx["sync_id"],
                "base_version": tx["sync_version"] - 1,
                "transaction": {"amount": 20, "type": "expense", "date": "2025-01-01", "account_global_id": acc["global_id"]}
            }
        ]
    }
    res = service.push_transactions(token, payload)
    assert res["results"][0]["status"] == "conflict"

    # 2. Successful update
    payload["operations"][0]["base_version"] = tx["sync_version"]
    res = service.push_transactions(token, payload)
    assert res["results"][0]["status"] == "accepted"
    updated_tx = db.transaction.get(tx["id"])
    assert float(updated_tx["amount"]) == 20.0

    # 3. Successful delete
    del_payload = {
        "operations": [
            {
                "operation": "delete",
                "sync_id": tx["sync_id"],
                "base_version": updated_tx["sync_version"]
            }
        ]
    }
    res = service.push_transactions(token, del_payload)
    assert res["results"][0]["status"] == "accepted"
    assert db.transaction.get(tx["id"]) is None

def test_mobile_sync_category_updates(db):
    service = MobileSyncService(db)
    pairing = service.start_pairing()
    token = service.pair_device({"pairing_token": pairing.pairing_token})["token"]
    cat = db.category.create("CatOrig", "expense")

    # Update category
    payload = {
        "operations": [
            {
                "entity_type": "category",
                "operation": "update",
                "global_id": cat["global_id"],
                "base_version": cat["sync_version"],
                "payload": {"name": "CatNew", "type": "expense"}
            }
        ]
    }
    res = service.push_catalog(token, payload)
    assert res["results"][0]["status"] == "accepted"
    assert db.category.get(cat["id"])["name"] == "CatNew"

def test_mobile_sync_resolve_by_local_id(db):
    service = MobileSyncService(db)
    pairing = service.start_pairing()
    token = service.pair_device({"pairing_token": pairing.pairing_token})["token"]
    acc = db.account.create("Acc", "bank")
    cat = db.category.create("Cat", "expense")
    tag = db.tag.create("Tag")

    payload = {
        "operations": [
            {
                "operation": "create",
                "sync_id": generate_ulid(),
                "transaction": {
                    "amount": 100, "type": "expense", "date": "2025-01-01",
                    "account_id": acc["id"],
                    "category_id": cat["id"],
                    "tag_ids": [tag["id"]]
                }
            }
        ]
    }
    res = service.push_transactions(token, payload)
    assert res["results"][0]["status"] == "accepted"

def test_mobile_sync_unsupported_operation(db):
    service = MobileSyncService(db)
    pairing = service.start_pairing()
    token = service.pair_device({"pairing_token": pairing.pairing_token})["token"]

    payload = {
        "operations": [
            {
                "operation": "MAGIC",
                "sync_id": generate_ulid()
            }
        ]
    }
    res = service.push_transactions(token, payload)
    assert res["results"][0]["status"] == "rejected"
    assert "Unsupported" in res["results"][0]["reason"]
