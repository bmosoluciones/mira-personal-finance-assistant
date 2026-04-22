# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import ssl
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from mira.db.database import Database
from mira.services.mobile_sync import (
    MobileSyncAuthError,
    MobileSyncRateLimitError,
    MobileSyncServer,
    MobileSyncService,
    _discover_local_addresses,
    _is_lan_or_loopback_address,
    _select_local_address_info,
)
from mira.sync_utils import generate_ulid


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "mobile-sync.db")
    database.connect()
    yield database
    database.close()


class _FakeHttpServer:
    def __init__(self, _address, _handler) -> None:
        self.server_port = 43123
        self.daemon_threads = False
        self.sync_server = None
        self.serve_forever_calls = 0
        self.shutdown_calls = 0
        self.server_close_calls = 0

    def serve_forever(self) -> None:
        self.serve_forever_calls += 1

    def shutdown(self) -> None:
        self.shutdown_calls += 1

    def server_close(self) -> None:
        self.server_close_calls += 1


def _assert_sync_timestamp(value: object) -> None:
    timestamp = str(value or "")
    assert "T" in timestamp
    assert timestamp.endswith("Z")


def _request_json(
    method: str,
    url: str,
    *,
    payload: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, object]]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = Request(url, data=body, method=method, headers=request_headers)
    request_context = ssl._create_unverified_context() if url.startswith("https://") else None
    try:
        with urlopen(request, timeout=2.0, context=request_context) as response:  # noqa: S310 - local test server only
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return int(exc.code), json.loads(exc.read().decode("utf-8"))


def _pair_service(service: MobileSyncService, *, use_token: bool = True) -> dict[str, object]:
    pairing = service.start_pairing()
    payload = {
        "device_name": "Pixel test",
        "platform": "android",
        "app_id": "mira-mobile-helper",
    }
    if use_token:
        payload["pairing_token"] = pairing.pairing_token
    else:
        payload["pairing_code"] = pairing.pairing_code
    return service.pair_device(payload)


def test_mobile_sync_service_supports_pair_master_data_push_changes_and_ack(db: Database) -> None:
    account = db.account.create("Caja movil", "bank", 50.0, "USD")
    category = db.category.create("Cafe", "expense")
    tag = db.tag.create("Urgente")
    service = MobileSyncService(db)

    pair_payload = _pair_service(service)
    token = str(pair_payload["token"])
    device_id = str(pair_payload["device"]["device_id"])

    master_data = service.master_data_payload(token)
    assert master_data["master_data_updated_at"]
    _assert_sync_timestamp(master_data["master_data_updated_at"])
    _assert_sync_timestamp(account["updated_at"])
    _assert_sync_timestamp(category["updated_at"])
    _assert_sync_timestamp(tag["updated_at"])
    assert any(str(row["global_id"]) == str(account["global_id"]) for row in master_data["accounts"])
    assert any(str(row["global_id"]) == str(category["global_id"]) for row in master_data["categories"])
    assert any(str(row["global_id"]) == str(tag["global_id"]) for row in master_data["tags"])

    sync_id = generate_ulid()
    push_payload = service.push_transactions(
        token,
        {
            "master_data_base_at": master_data["master_data_updated_at"],
            "operations": [
                {
                    "client_mutation_id": "create-1",
                    "operation": "create",
                    "sync_id": sync_id,
                    "base_version": 0,
                    "master_data_base_at": master_data["master_data_updated_at"],
                    "transaction": {
                        "tx_type": "expense",
                        "account_global_id": str(account["global_id"]),
                        "amount": 12.5,
                        "tx_date": "2026-04-09",
                        "description": "Cafe on the go",
                        "category_global_id": str(category["global_id"]),
                        "payment_method": "cash",
                        "tag_global_ids": [str(tag["global_id"])],
                    },
                }
            ],
        },
    )
    assert push_payload["results"][0]["status"] == "accepted"
    assert push_payload["results"][0]["code"] == "accepted"

    created = db.transaction.get_by_sync_id(sync_id)
    assert created is not None
    assert created["description"] == "Cafe on the go"
    assert int(created["sync_version"]) == 1
    _assert_sync_timestamp(created["updated_at"])
    assert [int(item["id"]) for item in db.tag.list_for_transaction(int(created["id"]))] == [int(tag["id"])]

    report = db.report.get_mira_master_report(year=2026, month=4)
    assert float(report["kpis"]["expense_operational"]) >= 12.5

    changes_payload = service.changes_payload(token, after_event_id=0)
    assert changes_payload["last_event_id"] >= 1
    matching_changes = [change for change in changes_payload["changes"] if change["transaction_sync_id"] == sync_id]
    assert len(matching_changes) == 1
    transaction_payload = matching_changes[0]["transaction"]
    assert "global_id" not in transaction_payload
    assert transaction_payload["account_global_id"] == str(account["global_id"])
    assert transaction_payload["category_global_id"] == str(category["global_id"])
    assert transaction_payload["tag_global_ids"] == [str(tag["global_id"])]
    _assert_sync_timestamp(transaction_payload["updated_at"])
    assert int(matching_changes[0]["transaction_version"]) == 1

    ack_payload = service.ack_payload(token, {"last_acked_event_id": changes_payload["last_event_id"]})
    assert int(ack_payload["last_acked_event_id"]) == int(changes_payload["last_event_id"])
    device = db.sync.get_device(device_id)
    assert device is not None
    assert int(device["last_acked_event_id"]) == int(changes_payload["last_event_id"])


def test_mobile_sync_service_deduplicates_replayed_create_operations(db: Database) -> None:
    account = db.account.create("Replay", "bank", 25.0, "USD")
    category = db.category.create("Food", "expense")
    service = MobileSyncService(db)
    token = str(_pair_service(service)["token"])
    master_data = service.master_data_payload(token)
    sync_id = generate_ulid()
    payload = {
        "master_data_base_at": master_data["master_data_updated_at"],
        "operations": [
            {
                "client_mutation_id": "create-1",
                "operation": "create",
                "sync_id": sync_id,
                "base_version": 0,
                "transaction": {
                    "tx_type": "expense",
                    "account_global_id": str(account["global_id"]),
                    "amount": 8.5,
                    "tx_date": "2026-04-09",
                    "description": "Replay me",
                    "category_global_id": str(category["global_id"]),
                    "payment_method": "cash",
                },
            }
        ],
    }

    first = service.push_transactions(token, payload)
    second = service.push_transactions(token, payload)

    assert first["results"][0]["status"] == "accepted"
    assert second["results"][0]["status"] == "accepted"
    assert second["results"][0]["code"] == "already_synced"
    assert len([tx for tx in db.transaction.list(limit=20) if tx["sync_id"] == sync_id]) == 1


def test_mobile_sync_snapshot_includes_profile_settings_and_category_parent_links(db: Database) -> None:
    parent = db.category.create("Hogar", "expense")
    child = db.category.create("Renta", "expense", parent_id=int(parent["id"]))
    db.setting.set("default_currency", "NIO")
    db.setting.set("number_thousands_separator", ".")
    db.setting.set("number_decimal_separator", ",")
    service = MobileSyncService(db)

    token = str(_pair_service(service)["token"])
    snapshot = service.snapshot_payload(token)

    assert snapshot["protocol_version"] == service.protocol_version
    assert snapshot["profile_settings"]["default_currency"] == "NIO"
    assert snapshot["profile_settings"]["number_format"] == {
        "thousands_separator": ".",
        "decimal_separator": ",",
    }
    child_row = next(item for item in snapshot["categories"] if str(item["global_id"]) == str(child["global_id"]))
    assert child_row["parent_id"] == child["parent_id"]
    assert child_row["parent_global_id"] == str(parent["global_id"])


def test_mobile_sync_service_supports_catalog_push_and_profile_settings_updates(db: Database) -> None:
    service = MobileSyncService(db)
    token = str(_pair_service(service)["token"])
    account_global_id = generate_ulid()
    parent_category_global_id = generate_ulid()
    child_category_global_id = generate_ulid()
    tag_global_id = generate_ulid()

    response = service.push_catalog(
        token,
        {
            "operations": [
                {
                    "client_mutation_id": "account-create",
                    "entity_type": "account",
                    "operation": "create",
                    "global_id": account_global_id,
                    "base_version": 0,
                    "payload": {
                        "name": "Cuenta movil",
                        "account_type": "bank",
                        "currency": "USD",
                        "is_default": True,
                    },
                },
                {
                    "client_mutation_id": "category-parent",
                    "entity_type": "category",
                    "operation": "create",
                    "global_id": parent_category_global_id,
                    "base_version": 0,
                    "payload": {
                        "name": "Servicios",
                        "type": "expense",
                        "color": "#123456",
                    },
                },
                {
                    "client_mutation_id": "category-child",
                    "entity_type": "category",
                    "operation": "create",
                    "global_id": child_category_global_id,
                    "base_version": 0,
                    "payload": {
                        "name": "Internet",
                        "type": "expense",
                        "color": "#654321",
                        "parent_global_id": parent_category_global_id,
                    },
                },
                {
                    "client_mutation_id": "tag-create",
                    "entity_type": "tag",
                    "operation": "create",
                    "global_id": tag_global_id,
                    "base_version": 0,
                    "payload": {
                        "name": "Casa",
                        "color": "#00AA88",
                    },
                },
                {
                    "client_mutation_id": "profile-settings",
                    "entity_type": "profile_settings",
                    "operation": "update",
                    "global_id": "profile_settings",
                    "base_version": 0,
                    "payload": {
                        "default_currency": "NIO",
                        "number_format": {
                            "thousands_separator": ".",
                            "decimal_separator": ",",
                        },
                    },
                },
            ]
        },
    )

    assert response["accepted_count"] == 5
    assert response["conflict_count"] == 0
    assert response["rejected_count"] == 0
    account = db.account.find_by_global_id(account_global_id)
    parent = db.category.find_by_global_id(parent_category_global_id)
    child = db.category.find_by_global_id(child_category_global_id)
    tag = db.tag.find_by_global_id(tag_global_id)
    assert account is not None
    assert parent is not None
    assert child is not None
    assert tag is not None
    assert child["parent_id"] == parent["id"]
    assert db.setting.get_default_currency() == "NIO"
    profile_result = next(item for item in response["results"] if item["entity_type"] == "profile_settings")
    assert profile_result["canonical"]["sync_version"] >= 2
    assert profile_result["canonical"]["last_modified_by_device_id"]
    _assert_sync_timestamp(profile_result["canonical"]["updated_at"])


def test_mobile_sync_service_preserves_transfer_metadata_in_push_and_changes(db: Database) -> None:
    origin = db.account.create("Origen", "bank", 100.0, "USD")
    destination = db.account.create("Destino", "bank", 40.0, "USD")
    service = MobileSyncService(db)
    token = str(_pair_service(service)["token"])
    master_data = service.master_data_payload(token)
    sync_id = generate_ulid()

    push_payload = service.push_transactions(
        token,
        {
            "master_data_base_at": master_data["master_data_updated_at"],
            "operations": [
                {
                    "client_mutation_id": "transfer-1",
                    "operation": "create",
                    "sync_id": sync_id,
                    "base_version": 0,
                    "transaction": {
                        "tx_type": "expense",
                        "account_global_id": str(origin["global_id"]),
                        "to_account_global_id": str(destination["global_id"]),
                        "is_transfer": True,
                        "payment_method": "transfer",
                        "amount": 25,
                        "tx_date": "2026-04-09",
                        "description": "Transferencia interna",
                    },
                }
            ],
        },
    )

    assert push_payload["results"][0]["status"] == "accepted"
    created = db.transaction.get_by_sync_id(sync_id)
    assert created is not None
    assert int(created["to_account_id"]) == int(destination["id"])
    assert int(created["is_transfer"]) == 1

    changes_payload = service.changes_payload(token, after_event_id=0)
    change = next(item for item in changes_payload["changes"] if item["transaction_sync_id"] == sync_id)
    assert change["transaction"]["to_account_global_id"] == str(destination["global_id"])
    assert bool(change["transaction"]["is_transfer"]) is True
    assert change["transaction"]["payment_method"] == "transfer"


def test_mobile_sync_service_rejects_missing_category_when_master_data_is_stale(db: Database) -> None:
    account = db.account.create("Wallet", "cash", 30.0, "USD")
    category = db.category.create("Transient", "expense")
    service = MobileSyncService(db)
    token = str(_pair_service(service)["token"])
    master_data = service.master_data_payload(token)

    db.category.delete(int(category["id"]))
    client_snapshot_at = datetime.fromisoformat(str(master_data["master_data_updated_at"]).replace("Z", "+00:00"))
    stale_master_data_at = (client_snapshot_at + timedelta(seconds=1)).astimezone(timezone.utc)
    db.setting.set(
        "master_data_updated_at",
        stale_master_data_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )

    push_payload = service.push_transactions(
        token,
        {
            "master_data_base_at": master_data["master_data_updated_at"],
            "operations": [
                {
                    "client_mutation_id": "stale-category",
                    "operation": "create",
                    "sync_id": generate_ulid(),
                    "base_version": 0,
                    "transaction": {
                        "tx_type": "expense",
                        "account_global_id": str(account["global_id"]),
                        "amount": 4,
                        "tx_date": "2026-04-09",
                        "description": "Legacy category",
                        "category_global_id": str(category["global_id"]),
                    },
                }
            ],
        },
    )

    result = push_payload["results"][0]
    assert result["status"] == "conflict"
    assert result["code"] == "master_data_stale"
    assert result["details"]["reference_code"] == "unknown_category"


def test_mobile_sync_service_rejects_expired_pairing_tokens(db: Database) -> None:
    service = MobileSyncService(db, pairing_ttl=timedelta(milliseconds=10))
    pairing = service.start_pairing()
    time.sleep(0.03)

    with pytest.raises(MobileSyncAuthError) as exc_info:
        service.pair_device(
            {
                "pairing_token": pairing.pairing_token,
                "device_name": "Expired",
                "platform": "android",
                "app_id": "mira-mobile-helper",
            }
        )

    assert "expired" in str(exc_info.value).lower()
    assert exc_info.value.error_code == "pairing_expired"


def test_mobile_sync_service_rejects_updates_with_stale_base_version(db: Database) -> None:
    account = db.account.create("Checking", "bank", 100.0, "USD")
    category = db.category.create("Bills", "expense")
    tx = db.transaction.create(
        account_id=int(account["id"]),
        tx_type="expense",
        amount=8.0,
        description="Existing",
        category_id=int(category["id"]),
        category=str(category["name"]),
        tx_date="2026-04-09",
    )
    service = MobileSyncService(db)
    token = str(_pair_service(service)["token"])
    master_data = service.master_data_payload(token)

    push_payload = service.push_transactions(
        token,
        {
            "master_data_base_at": master_data["master_data_updated_at"],
            "operations": [
                {
                    "client_mutation_id": "update-stale",
                    "operation": "update",
                    "sync_id": str(tx["sync_id"]),
                    "base_version": 0,
                    "transaction": {
                        "tx_type": "expense",
                        "account_global_id": str(account["global_id"]),
                        "amount": 9.0,
                        "tx_date": "2026-04-09",
                        "description": "Stale mobile update",
                        "category_global_id": str(category["global_id"]),
                        "payment_method": "cash",
                    },
                }
            ],
        },
    )
    result = push_payload["results"][0]
    assert result["status"] == "conflict"
    assert result["code"] == "version_conflict"
    assert result["canonical"]["transaction"]["sync_id"] == str(tx["sync_id"])


def test_mobile_sync_service_push_batch_uses_single_atomic_context(
    db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account = db.account.create("Batch", "bank", 10.0, "USD")
    category = db.category.create("Snacks", "expense")
    service = MobileSyncService(db)
    token = str(_pair_service(service)["token"])
    master_data = service.master_data_payload(token)
    entered: list[str] = []

    @contextmanager
    def _counting_atomic():
        entered.append("entered")
        yield

    monkeypatch.setattr(service, "_push_atomic_context", _counting_atomic)

    operations = [
        {
            "client_mutation_id": f"batch-{index}",
            "operation": "create",
            "sync_id": generate_ulid(),
            "base_version": 0,
            "transaction": {
                "tx_type": "expense",
                "account_global_id": str(account["global_id"]),
                "amount": 1 + index,
                "tx_date": "2026-04-09",
                "description": f"Batch {index}",
                "category_global_id": str(category["global_id"]),
            },
        }
        for index in range(50)
    ]

    push_payload = service.push_transactions(
        token,
        {
            "master_data_base_at": master_data["master_data_updated_at"],
            "operations": operations,
        },
    )

    assert entered == ["entered"]
    assert push_payload["accepted_count"] == 50


def test_mobile_sync_service_uses_standard_transaction_pipeline_for_mobile_creates(
    db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account = db.account.create("Pipeline", "bank", 20.0, "USD")
    category = db.category.create("Coffee", "expense")
    service = MobileSyncService(db)
    token = str(_pair_service(service)["token"])
    master_data = service.master_data_payload(token)
    calls: list[str] = []

    def _fake_select_best_operation_message(tx: dict[str, object], *, source: str | None = None):
        calls.append(f"{tx['description']}:{source}")
        return None, None

    monkeypatch.setattr(db._backend, "select_best_operation_message", _fake_select_best_operation_message)

    service.push_transactions(
        token,
        {
            "master_data_base_at": master_data["master_data_updated_at"],
            "operations": [
                {
                    "client_mutation_id": "pipeline",
                    "operation": "create",
                    "sync_id": generate_ulid(),
                    "base_version": 0,
                    "transaction": {
                        "tx_type": "expense",
                        "account_global_id": str(account["global_id"]),
                        "amount": 5,
                        "tx_date": "2026-04-09",
                        "description": "Pipeline coffee",
                        "category_global_id": str(category["global_id"]),
                    },
                }
            ],
        },
    )

    assert calls == ["Pipeline coffee:mobile_sync"]


def test_mobile_sync_server_start_and_stop_with_fake_http_server(
    db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publisher_starts: list[tuple[int, dict[str, str]]] = []

    def _fake_publisher_start(self, *, port: int, properties: dict[str, str]) -> tuple[bool, tuple[str, ...]]:
        publisher_starts.append((port, properties))
        return True, ("192.168.1.20", "127.0.0.1")

    monkeypatch.setattr("mira.services.mobile_sync.ThreadingHTTPServer", _FakeHttpServer)
    monkeypatch.setattr("mira.services.mobile_sync._ZeroconfPublisher.start", _fake_publisher_start)
    monkeypatch.setattr("mira.services.mobile_sync._ZeroconfPublisher.stop", lambda self: None)

    server = MobileSyncServer(db)
    status = server.start()
    fake_httpd = server._httpd
    try:
        assert status.port == 43123
        assert status.advertisement_enabled is True
        assert status.host == "192.168.1.20"
        assert status.advertised_addresses == ("192.168.1.20", "127.0.0.1")
        assert status.pairing_payload["api_base_url"] == "https://192.168.1.20:43123/api/mobile/v1"
        assert status.transport_scheme == "https"
        assert len(str(status.tls_fingerprint_sha256)) == 64
        assert status.pairing_payload["transport_scheme"] == "https"
        assert len(str(status.pairing_payload["tls_fingerprint_sha256"])) == 64
        assert status.pairing_payload["pairing_code"] == status.pairing_code
        assert status.pairing_payload["pairing_token"] == status.pairing_token
        assert status.lan_warning is None
        assert publisher_starts == [
            (
                43123,
                {
                    "protocol_version": server.service.protocol_version,
                    "pairing_required": "1",
                    "transport_scheme": "https",
                    "tls_fingerprint_sha256": status.tls_fingerprint_sha256,
                },
            )
        ]
    finally:
        server.stop()

    assert fake_httpd is not None
    assert fake_httpd.shutdown_calls == 1
    assert fake_httpd.server_close_calls == 1


def test_mobile_sync_http_pair_rate_limits_repeated_attempts(
    db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "mira.services.mobile_sync._ZeroconfPublisher.start",
        lambda self, *, port, properties: (False, ("127.0.0.1",)),
    )
    monkeypatch.setattr("mira.services.mobile_sync._ZeroconfPublisher.stop", lambda self: None)

    server = MobileSyncServer(db)
    status = server.start()
    try:
        url = f"https://127.0.0.1:{status.port}/api/mobile/v1/pair"
        payload = {
            "pairing_token": "invalid-token-for-limit",
            "device_name": "Rate limit",
            "platform": "android",
            "app_id": "mira-mobile-helper",
        }
        for _ in range(5):
            status_code, response = _request_json("POST", url, payload=payload)
            assert status_code == 401
            assert response["error_code"] == "authorization_failed"

        status_code, response = _request_json("POST", url, payload=payload)

        assert status_code == 429
        assert response["error_code"] == "rate_limited"
        assert int(response["retry_after_seconds"]) >= 1
        assert response["details"] == {"retry_after_seconds": response["retry_after_seconds"]}
    finally:
        server.stop()


def test_mobile_sync_http_push_rate_limits_by_ip_and_token(
    db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "mira.services.mobile_sync._ZeroconfPublisher.start",
        lambda self, *, port, properties: (False, ("127.0.0.1",)),
    )
    monkeypatch.setattr("mira.services.mobile_sync._ZeroconfPublisher.stop", lambda self: None)

    server = MobileSyncServer(db)
    status = server.start()
    try:
        base_url = f"https://127.0.0.1:{status.port}/api/mobile/v1"
        pair_status, pair_response = _request_json(
            "POST",
            f"{base_url}/pair",
            payload={
                "pairing_token": status.pairing_token,
                "device_name": "Rate limited helper",
                "platform": "android",
                "app_id": "mira-mobile-helper",
            },
        )
        assert pair_status == 200
        token = str(pair_response["token"])
        headers = {"Authorization": f"Bearer {token}"}

        for _ in range(30):
            status_code, response = _request_json(
                "POST",
                f"{base_url}/transactions/push",
                payload={"operations": []},
                headers=headers,
            )
            assert status_code == 200
            assert response["accepted_count"] == 0

        status_code, response = _request_json(
            "POST",
            f"{base_url}/transactions/push",
            payload={"operations": []},
            headers=headers,
        )

        assert status_code == 429
        assert response["error_code"] == "rate_limited"
        assert int(response["retry_after_seconds"]) >= 1

        status_code, response = _request_json("GET", f"{base_url}/status")
        assert status_code == 200
        assert response["pairing_active"] is True
    finally:
        server.stop()


def test_mobile_sync_http_supports_snapshot_and_catalog_push(
    db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "mira.services.mobile_sync._ZeroconfPublisher.start",
        lambda self, *, port, properties: (False, ("127.0.0.1",)),
    )
    monkeypatch.setattr("mira.services.mobile_sync._ZeroconfPublisher.stop", lambda self: None)

    server = MobileSyncServer(db)
    status = server.start()
    try:
        base_url = f"https://127.0.0.1:{status.port}/api/mobile/v1"
        pair_status, pair_response = _request_json(
            "POST",
            f"{base_url}/pair",
            payload={
                "pairing_token": status.pairing_token,
                "device_name": "HTTP mobile",
                "platform": "android",
                "app_id": "mira-mobile",
            },
        )
        assert pair_status == 200
        token = str(pair_response["token"])
        headers = {"Authorization": f"Bearer {token}"}

        snapshot_status, snapshot = _request_json("GET", f"{base_url}/snapshot", headers=headers)
        assert snapshot_status == 200
        assert snapshot["protocol_version"] == server.service.protocol_version
        assert "profile_settings" in snapshot

        catalog_status, catalog_response = _request_json(
            "POST",
            f"{base_url}/catalog/push",
            payload={"operations": []},
            headers=headers,
        )
        assert catalog_status == 200
        assert catalog_response["accepted_count"] == 0
        assert catalog_response["conflict_count"] == 0
        assert catalog_response["rejected_count"] == 0
    finally:
        server.stop()


def test_mobile_sync_push_rate_limit_key_includes_token(db: Database) -> None:
    server = MobileSyncServer(db)
    path = "/api/mobile/v1/transactions/push"

    for _ in range(30):
        server.check_rate_limit(path, client_host="127.0.0.1", token="token-a")
    with pytest.raises(MobileSyncRateLimitError) as exc_info:
        server.check_rate_limit(path, client_host="127.0.0.1", token="token-a")

    assert exc_info.value.error_code == "rate_limited"
    assert exc_info.value.retry_after_seconds >= 1
    server.check_rate_limit(path, client_host="127.0.0.1", token="token-b")


def test_mobile_sync_server_stops_after_pairing_timeout_without_sessions(
    db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("mira.services.mobile_sync.ThreadingHTTPServer", _FakeHttpServer)
    monkeypatch.setattr(
        "mira.services.mobile_sync._ZeroconfPublisher.start",
        lambda self, *, port, properties: (False, ("127.0.0.1",)),
    )
    monkeypatch.setattr("mira.services.mobile_sync._ZeroconfPublisher.stop", lambda self: None)

    server = MobileSyncServer(db)
    server.service._pairing_ttl = timedelta(milliseconds=50)
    server.start()

    deadline = time.time() + 1.0
    while server.is_running and time.time() < deadline:
        time.sleep(0.02)

    assert server.is_running is False


def test_transaction_delete_creates_tombstone_and_delete_change(db: Database) -> None:
    account = db.account.create("Delete me", "bank", 25.0, "USD")
    tx = db.transaction.create(
        account_id=int(account["id"]),
        tx_type="expense",
        amount=5.0,
        description="Pending delete",
        tx_date="2026-04-09",
    )

    db.transaction.delete(int(tx["id"]))

    assert db.transaction.get_by_sync_id(str(tx["sync_id"])) is None
    tombstone = db.sync.get_tombstone(str(tx["sync_id"]))
    assert tombstone is not None
    assert int(tombstone["last_deleted_version"]) == int(tx["sync_version"]) + 1

    changes = db.sync.list_transaction_changes(after_event_id=0)
    assert any(
        change["operation"] == "delete" and change["transaction_sync_id"] == str(tx["sync_id"]) for change in changes
    )


def test_mobile_sync_rejects_public_addresses_for_lan_only_mode() -> None:
    assert _is_lan_or_loopback_address("127.0.0.1") is True
    assert _is_lan_or_loopback_address("192.168.1.22") is True
    assert _is_lan_or_loopback_address("8.8.8.8") is False


def test_select_local_address_info_prefers_private_ipv4_over_link_local_and_loopback() -> None:
    selection = _select_local_address_info(("127.0.0.1", "169.254.10.5", "192.168.1.24", "10.0.0.9"))

    assert selection.preferred_host == "192.168.1.24"
    assert selection.advertised_addresses == ("192.168.1.24", "10.0.0.9", "169.254.10.5", "127.0.0.1")
    assert selection.has_non_loopback_lan is True


def test_discover_local_addresses_combines_udp_probe_and_hostname_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("mira.services.mobile_sync._discover_socket_local_addresses", lambda: ["10.0.0.9"])
    monkeypatch.setattr(
        "mira.services.mobile_sync.socket.gethostbyname_ex",
        lambda _hostname: ("mira", [], ["127.0.0.1", "10.0.0.9", "192.168.1.24"]),
    )

    addresses = _discover_local_addresses()

    assert addresses == ["10.0.0.9", "192.168.1.24", "127.0.0.1"]


def test_discover_local_addresses_falls_back_to_loopback_when_every_probe_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("mira.services.mobile_sync._discover_socket_local_addresses", lambda: [])

    def _raise_hostname_error(_hostname: str) -> tuple[str, list[str], list[str]]:
        raise OSError("hostname lookup failed")

    monkeypatch.setattr("mira.services.mobile_sync.socket.gethostbyname_ex", _raise_hostname_error)

    assert _discover_local_addresses() == ["127.0.0.1"]


def test_mobile_sync_server_marks_loopback_only_pairing_as_warning(
    db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("mira.services.mobile_sync.ThreadingHTTPServer", _FakeHttpServer)
    monkeypatch.setattr(
        "mira.services.mobile_sync._ZeroconfPublisher.start",
        lambda self, *, port, properties: (False, ("127.0.0.1",)),
    )
    monkeypatch.setattr("mira.services.mobile_sync._ZeroconfPublisher.stop", lambda self: None)

    server = MobileSyncServer(db)
    try:
        status = server.start()
        events = server.drain_events()
        assert status.host == "127.0.0.1"
        assert status.lan_warning is not None
        assert "LAN privada" in status.lan_warning
        assert any(event.kind == "session.lan_warning" for event in events)
    finally:
        server.stop()
