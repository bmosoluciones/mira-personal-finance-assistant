# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Local-network transaction sync services for mobile helpers."""

from __future__ import annotations

from collections import deque
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
import json
import logging
from math import ceil
from pathlib import Path
from secrets import choice, token_urlsafe
import socket
import ssl
import tempfile
import threading
from types import TracebackType
from typing import Any, Callable, NoReturn
from urllib.parse import parse_qs, urlparse

from mira.db.database import Database
from mira.db.model import SCHEMA_VERSION
from mira.sync_utils import normalize_utc_iso, utc_now, utc_now_iso

logger = logging.getLogger(__name__)

_PAIRING_CODE_DIGITS = "0123456789"
_PAIRING_TOKEN_MIN_LENGTH = 12
_SERVICE_TYPE = "_mira-mobile-sync._tcp.local."
_SERVICE_NAME = "MIRA Mobile Sync"
_PROFILE_SETTINGS_SYNC_VERSION_KEY = "mobile_profile_settings_sync_version"
_PROFILE_SETTINGS_UPDATED_AT_KEY = "mobile_profile_settings_updated_at"
_PROFILE_SETTINGS_LAST_MODIFIED_BY_DEVICE_ID_KEY = "mobile_profile_settings_last_modified_by_device_id"
_SYNC_REQUIRED_CAPABILITIES = (
    "master-data",
    "transactions-push",
)
_SYNC_OPTIONAL_CAPABILITIES = (
    "snapshot",
    "catalog-push",
    "transactions-changes",
    "transactions-ack",
)
_SYNC_TRANSPORT_CAPABILITIES = (
    "secure-transport-tls-pinned",
)
_SYNC_CAPABILITIES = [
    *_SYNC_REQUIRED_CAPABILITIES,
    *_SYNC_OPTIONAL_CAPABILITIES,
    *_SYNC_TRANSPORT_CAPABILITIES,
]
_RATE_LIMIT_WINDOW = timedelta(minutes=1)
_ANONYMOUS_TOKEN_KEY = "<anonymous>"


@dataclass(frozen=True)
class RateLimitRule:
    """Represent the RateLimitRule class."""

    max_requests: int
    window: timedelta
    include_token: bool = False


@dataclass(frozen=True)
class RateLimitDecision:
    """Represent the RateLimitDecision class."""

    allowed: bool
    retry_after_seconds: int = 0


@dataclass(frozen=True)
class PairingState:
    """Represent the PairingState class."""

    pairing_code: str
    pairing_token: str
    expires_at: datetime
    issued_at: datetime


@dataclass(frozen=True)
class AuthSession:
    """Represent the AuthSession class."""

    device_id: str
    token: str
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class MobileSyncServerEvent:
    """Represent the MobileSyncServerEvent class."""

    kind: str
    title: str
    message: str
    level: str
    created_at: str


@dataclass(frozen=True)
class MobileSyncServerStatus:
    """Represent the MobileSyncServerStatus class."""

    service_name: str
    protocol_version: str
    host: str
    port: int
    pairing_code: str
    pairing_token: str
    pairing_expires_at: str
    advertisement_enabled: bool
    advertised_addresses: tuple[str, ...]
    transport_scheme: str
    tls_fingerprint_sha256: str
    lan_warning: str | None = None
    pairing_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedPushPayload:
    """Represent the ResolvedPushPayload class."""

    tx_type: str
    account_id: int
    account_global_id: str
    to_account_id: int | None
    to_account_global_id: str | None
    is_transfer: bool
    amount: Any
    tx_date: str
    category_name: str | None
    category_id: int | None
    category_global_id: str | None
    payment_method: str
    description: str | None
    note: str | None
    exchange_rate: float | None
    converted_amount: Any
    tag_ids: list[int]
    tag_global_ids: list[str]
    master_data_base_at: str | None


class MobileSyncError(RuntimeError):
    """Represent the MobileSyncError class."""

    status_code = HTTPStatus.BAD_REQUEST
    error_code = "validation_error"

    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        status_code: HTTPStatus | None = None,
        details: dict[str, Any] | None = None,
        canonical: dict[str, Any] | None = None,
    ) -> None:
        """Initialize."""
        super().__init__(message)
        self.error_code = error_code or self.error_code
        self.status_code = status_code or self.status_code
        self.details = details
        self.canonical = canonical


class MobileSyncAuthError(MobileSyncError):
    """Represent the MobileSyncAuthError class."""

    status_code = HTTPStatus.UNAUTHORIZED
    error_code = "authorization_failed"


class MobileSyncForbiddenError(MobileSyncError):
    """Represent the MobileSyncForbiddenError class."""

    status_code = HTTPStatus.FORBIDDEN
    error_code = "lan_only"


class MobileSyncConflictError(MobileSyncError):
    """Represent the MobileSyncConflictError class."""

    status_code = HTTPStatus.CONFLICT
    error_code = "version_conflict"


class MobileSyncRateLimitError(MobileSyncError):
    """Represent the MobileSyncRateLimitError class."""

    status_code = HTTPStatus.TOO_MANY_REQUESTS
    error_code = "rate_limited"

    def __init__(self, *, retry_after_seconds: int) -> None:
        """Initialize."""
        self.retry_after_seconds = max(1, int(retry_after_seconds))
        super().__init__(
            "Too many mobile sync requests. Retry after the rate-limit window resets.",
            details={"retry_after_seconds": self.retry_after_seconds},
        )


@dataclass(frozen=True)
class LocalAddressSelection:
    """Represent the LocalAddressSelection class."""

    preferred_host: str
    advertised_addresses: tuple[str, ...]

    @property
    def has_non_loopback_lan(self) -> bool:
        """Return has non loopback lan."""
        return any(not ip_address(address).is_loopback for address in self.advertised_addresses)


_RATE_LIMIT_RULES: dict[str, RateLimitRule] = {
    "/api/mobile/v1/pair": RateLimitRule(max_requests=5, window=_RATE_LIMIT_WINDOW),
    "/api/mobile/v1/status": RateLimitRule(max_requests=120, window=_RATE_LIMIT_WINDOW),
    "/api/mobile/v1/master-data": RateLimitRule(max_requests=120, window=_RATE_LIMIT_WINDOW),
    "/api/mobile/v1/snapshot": RateLimitRule(max_requests=120, window=_RATE_LIMIT_WINDOW),
    "/api/mobile/v1/catalog/push": RateLimitRule(
        max_requests=60,
        window=_RATE_LIMIT_WINDOW,
        include_token=True,
    ),
    "/api/mobile/v1/transactions/changes": RateLimitRule(max_requests=120, window=_RATE_LIMIT_WINDOW),
    "/api/mobile/v1/transactions/ack": RateLimitRule(max_requests=120, window=_RATE_LIMIT_WINDOW),
    "/api/mobile/v1/transactions/push": RateLimitRule(
        max_requests=30,
        window=_RATE_LIMIT_WINDOW,
        include_token=True,
    ),
}


class _MobileSyncRateLimiter:
    def __init__(self, *, now_provider: Callable[[], datetime] = utc_now) -> None:
        """Initialize."""
        self._now_provider = now_provider
        self._requests: dict[tuple[str, ...], deque[datetime]] = {}
        self._lock = threading.RLock()

    def check(self, key: tuple[str, ...], rule: RateLimitRule) -> RateLimitDecision:
        """Return check."""
        now = self._now_provider()
        cutoff = now - rule.window
        with self._lock:
            bucket = self._requests.setdefault(key, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= rule.max_requests:
                retry_after = ceil(((bucket[0] + rule.window) - now).total_seconds())
                return RateLimitDecision(allowed=False, retry_after_seconds=max(1, retry_after))
            bucket.append(now)
            return RateLimitDecision(allowed=True)

    def clear(self) -> None:
        """Return clear."""
        with self._lock:
            self._requests.clear()


class MobileSyncService:
    """Represent the MobileSyncService class."""

    protocol_version = "1"

    def __init__(
        self,
        db: Database,
        *,
        pairing_ttl: timedelta = timedelta(minutes=10),
        session_ttl: timedelta = timedelta(hours=2),
        event_sink: Callable[[MobileSyncServerEvent], None] | None = None,
    ) -> None:
        """Initialize."""
        self._db = db
        self._pairing_ttl = pairing_ttl
        self._session_ttl = session_ttl
        self._event_sink = event_sink
        self._pairing_state: PairingState | None = None
        self._sessions: dict[str, AuthSession] = {}
        self._lock = threading.RLock()

    @property
    def has_active_sessions(self) -> bool:
        """Return has active sessions."""
        with self._lock:
            self._purge_expired_sessions()
            return bool(self._sessions)

    def start_pairing(self) -> PairingState:
        """Return start pairing."""
        with self._lock:
            issued_at = utc_now()
            self._pairing_state = PairingState(
                pairing_code=self._generate_pairing_code(),
                pairing_token=token_urlsafe(18),
                issued_at=issued_at,
                expires_at=issued_at + self._pairing_ttl,
            )
            self._purge_expired_sessions()
            return self._pairing_state

    def stop(self) -> None:
        """Return stop."""
        with self._lock:
            self._pairing_state = None
            self._sessions.clear()

    def status_payload(self) -> dict[str, Any]:
        """Return status payload."""
        with self._lock:
            pairing_state = self._require_pairing_state()
            return {
                "service_name": _SERVICE_NAME,
                "protocol_version": self.protocol_version,
                "pairing_required": True,
                "pairing_active": True,
                "pairing_expires_at": normalize_utc_iso(pairing_state.expires_at),
                "master_data_updated_at": self._current_master_data_updated_at(),
                "capabilities": _SYNC_CAPABILITIES,
            }

    def pair_device(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return pair device."""
        with self._lock:
            pairing_state = self._require_pairing_state()
            self._purge_expired_sessions()
            self._validate_pairing_secret(payload, pairing_state)

            device = self._db.sync.register_device(
                device_id=self._normalized_optional_string(payload.get("device_id")),
                device_name=self._normalized_optional_string(payload.get("device_name")) or "MIRA Mobile Helper",
                platform=self._normalized_optional_string(payload.get("platform")) or "android",
                app_id=self._normalized_optional_string(payload.get("app_id")) or "mira-mobile-helper",
            )
            issued_at = utc_now()
            session = AuthSession(
                device_id=str(device["device_id"]),
                token=token_urlsafe(24),
                issued_at=issued_at,
                expires_at=issued_at + self._session_ttl,
            )
            self._sessions[session.token] = session

        self._emit_event(
            "pairing.accepted",
            (
                f"Nuevo emparejamiento movil: {device['device_name']} ({device['platform']}). "
                "La sesion local ya puede sincronizar transacciones."
            ),
        )
        return {
            "device": device,
            "token": session.token,
            "token_expires_at": normalize_utc_iso(session.expires_at),
            "protocol_version": self.protocol_version,
            "capabilities": self.status_payload()["capabilities"],
        }

    def master_data_payload(self, token: str) -> dict[str, Any]:
        """Return master data payload."""
        self._require_session(token)
        return {
            "generated_at": normalize_utc_iso(utc_now()),
            "schema_version": SCHEMA_VERSION,
            "default_currency": self._db.setting.get_default_currency(),
            "master_data_updated_at": self._current_master_data_updated_at(),
            "accounts": self._db.account.list(),
            "categories": self._db.category.list(),
            "tags": self._db.tag.list(),
            "savings_goals": self._db.savings_goal.list(),
        }

    def snapshot_payload(self, token: str) -> dict[str, Any]:
        """Return snapshot payload."""
        payload = self.master_data_payload(token)
        payload["protocol_version"] = self.protocol_version
        payload["profile_settings"] = self._profile_settings_payload()
        return payload

    def push_catalog(self, token: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Return push catalog."""
        session = self._require_session(token)
        operations_raw = payload.get("operations")
        if not isinstance(operations_raw, list):
            raise MobileSyncError("The request body must include an 'operations' list.")

        results: list[dict[str, Any]] = []
        for item in operations_raw:
            client_mutation_id = self._normalized_optional_string(item.get("client_mutation_id"))
            entity_type = str(item.get("entity_type") or "").strip()
            try:
                result = self._apply_catalog_push_item(session.device_id, item)
            except MobileSyncError as exc:
                results.append(
                    {
                        "client_mutation_id": client_mutation_id,
                        "entity_type": entity_type,
                        "status": "conflict" if exc.status_code == HTTPStatus.CONFLICT else "rejected",
                        "code": exc.error_code,
                        "reason": str(exc),
                        "details": exc.details,
                        "canonical": exc.canonical,
                    }
                )
            except ValueError as exc:
                results.append(
                    {
                        "client_mutation_id": client_mutation_id,
                        "entity_type": entity_type,
                        "status": "rejected",
                        "code": "validation_error",
                        "reason": str(exc),
                    }
                )
            else:
                result["client_mutation_id"] = client_mutation_id
                result["entity_type"] = entity_type
                results.append(result)

        accepted_count = sum(1 for item in results if item["status"] == "accepted")
        rejected_count = sum(1 for item in results if item["status"] == "rejected")
        conflict_count = sum(1 for item in results if item["status"] == "conflict")
        return {
            "results": results,
            "accepted_count": accepted_count,
            "rejected_count": rejected_count,
            "conflict_count": conflict_count,
            "master_data_updated_at": self._current_master_data_updated_at(),
        }

    def push_transactions(self, token: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Return push transactions."""
        session = self._require_session(token)
        operations_raw = payload.get("operations")
        if not isinstance(operations_raw, list):
            raise MobileSyncError("The request body must include an 'operations' list.")

        master_data_base_at = self._normalized_optional_string(payload.get("master_data_base_at"))
        results: list[dict[str, Any]] = []
        with self._push_atomic_context():
            for item in operations_raw:
                client_mutation_id = self._normalized_optional_string(item.get("client_mutation_id"))
                try:
                    result = self._apply_push_item(
                        session.device_id,
                        item,
                        master_data_base_at=master_data_base_at,
                    )
                except MobileSyncError as exc:
                    results.append(
                        {
                            "client_mutation_id": client_mutation_id,
                            "status": "conflict" if exc.status_code == HTTPStatus.CONFLICT else "rejected",
                            "code": exc.error_code,
                            "reason": str(exc),
                            "details": exc.details,
                            "canonical": exc.canonical,
                        }
                    )
                except ValueError as exc:
                    results.append(
                        {
                            "client_mutation_id": client_mutation_id,
                            "status": "rejected",
                            "code": "validation_error",
                            "reason": str(exc),
                        }
                    )
                else:
                    result["client_mutation_id"] = client_mutation_id
                    results.append(result)

        accepted_count = sum(1 for item in results if item["status"] == "accepted")
        rejected_count = sum(1 for item in results if item["status"] == "rejected")
        conflict_count = sum(1 for item in results if item["status"] == "conflict")
        if results:
            summary_level = "warning" if rejected_count or conflict_count else "info"
            self._emit_event(
                "transactions.push",
                (
                    "Sincronizacion movil completada. "
                    f"Aceptadas: {accepted_count}. Rechazadas: {rejected_count}. Conflictos: {conflict_count}."
                ),
                level=summary_level,
            )
        return {
            "results": results,
            "accepted_count": accepted_count,
            "rejected_count": rejected_count,
            "conflict_count": conflict_count,
            "master_data_updated_at": self._current_master_data_updated_at(),
        }

    def changes_payload(self, token: str, *, after_event_id: int, limit: int = 500) -> dict[str, Any]:
        """Return changes payload."""
        self._require_session(token)
        changes = self._db.sync.list_transaction_changes(after_event_id=after_event_id, limit=limit)
        last_event_id = after_event_id if not changes else int(changes[-1]["event_id"])
        return {
            "changes": changes,
            "last_event_id": last_event_id,
            "master_data_updated_at": self._current_master_data_updated_at(),
        }

    def ack_payload(self, token: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Return ack payload."""
        session = self._require_session(token)
        cursor = int(payload.get("last_acked_event_id") or 0)
        device = self._db.sync.ack_device_cursor(session.device_id, cursor)
        return {
            "device": device,
            "last_acked_event_id": int(device["last_acked_event_id"]),
        }

    def _profile_settings_payload(self) -> dict[str, Any]:
        number_thousands_separator = self._db.setting.get("number_thousands_separator") or ","
        number_decimal_separator = self._db.setting.get("number_decimal_separator") or "."
        updated_at = normalize_utc_iso(
            self._db.setting.get(_PROFILE_SETTINGS_UPDATED_AT_KEY) or self._current_master_data_updated_at()
        )
        sync_version = int(self._db.setting.get(_PROFILE_SETTINGS_SYNC_VERSION_KEY) or 1)
        last_modified_by_device_id = (
            self._db.setting.get(_PROFILE_SETTINGS_LAST_MODIFIED_BY_DEVICE_ID_KEY)
            or self._db.setting.get_local_desktop_device_id()
        )
        return {
            "default_currency": self._db.setting.get_default_currency(),
            "number_format": {
                "thousands_separator": number_thousands_separator,
                "decimal_separator": number_decimal_separator,
            },
            "sync_version": sync_version,
            "updated_at": updated_at,
            "last_modified_by_device_id": last_modified_by_device_id,
        }

    def _canonical_catalog_entity(self, entity_type: str, global_id: str | None) -> dict[str, Any] | None:
        normalized_global_id = self._normalized_optional_string(global_id)
        if entity_type == "profile_settings":
            return self._profile_settings_payload()
        if not normalized_global_id:
            return None
        match entity_type:
            case "account":
                return self._db.account.find_by_global_id(normalized_global_id)
            case "category":
                return self._db.category.find_by_global_id(normalized_global_id)
            case "tag":
                return self._db.tag.find_by_global_id(normalized_global_id)
            case _:
                return None

    def _resolve_parent_category_id(self, parent_global_id: str | None) -> int | None:
        normalized_parent_global_id = self._normalized_optional_string(parent_global_id)
        if not normalized_parent_global_id:
            return None
        parent = self._db.category.find_by_global_id(normalized_parent_global_id)
        if parent is None:
            raise MobileSyncError(
                "The selected parent category no longer exists on the desktop database.",
                error_code="unknown_category",
            )
        return int(parent["id"])

    def _apply_catalog_push_item(self, device_id: str, item: dict[str, Any]) -> dict[str, Any]:
        operation = str(item.get("operation") or "").strip().lower()
        entity_type = str(item.get("entity_type") or "").strip()
        global_id = self._normalized_optional_string(item.get("global_id"))
        base_version = int(item.get("base_version") or 0)
        payload = item.get("payload")

        if entity_type == "profile_settings":
            return self._apply_profile_settings_operation(device_id, operation, base_version, payload)

        if not global_id:
            raise MobileSyncError("Catalog operations require a global_id.")
        if not isinstance(payload, dict) and operation != "delete":
            raise MobileSyncError("Catalog payload must be an object.")

        match entity_type:
            case "account":
                return self._apply_account_operation(device_id, operation, global_id, base_version, payload)
            case "category":
                return self._apply_category_operation(device_id, operation, global_id, base_version, payload)
            case "tag":
                return self._apply_tag_operation(device_id, operation, global_id, base_version, payload)
            case _:
                raise MobileSyncError(f"Unsupported catalog entity type: {entity_type!r}")

    def _apply_account_operation(
        self,
        device_id: str,
        operation: str,
        global_id: str,
        base_version: int,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        existing = self._db.account.find_by_global_id(global_id)
        if operation == "delete":
            if existing is None:
                return {"status": "accepted", "code": "already_deleted", "canonical": None}
            if int(existing.get("sync_version") or 0) != int(base_version):
                raise MobileSyncConflictError(
                    "The desktop account version changed before this update was applied.",
                    canonical=existing,
                )
            self._db.account.delete(int(existing["id"]))
            return {"status": "accepted", "code": "accepted", "canonical": None}

        assert payload is not None
        name = self._normalized_optional_string(payload.get("name"))
        if not name:
            raise MobileSyncError("Account payload must include name.")
        account_type = self._normalized_optional_string(payload.get("account_type")) or "bank"
        currency = (self._normalized_optional_string(payload.get("currency")) or self._db.setting.get_default_currency()).upper()
        is_default = bool(payload.get("is_default"))
        existing_by_name = self._db.account.find_by_name(name)

        if operation == "create":
            if existing is not None:
                if (
                    self._normalized_optional_string(existing.get("name")) == name
                    and self._normalized_optional_string(existing.get("account_type")) == account_type
                    and self._normalized_optional_string(existing.get("currency")) == currency
                    and bool(existing.get("is_default")) == is_default
                ):
                    return {"status": "accepted", "code": "already_synced", "canonical": existing}
                raise MobileSyncConflictError(
                    "An account with this global_id already exists on the desktop database.",
                    canonical=existing,
                )
            if existing_by_name is not None and str(existing_by_name.get("global_id")) != global_id:
                raise MobileSyncConflictError(
                    "An account with the same normalized name already exists on the desktop database.",
                    canonical=existing_by_name,
                )
            created = self._db.account.create(
                name,
                account_type,
                0,
                currency,
                global_id=global_id,
                device_id=device_id,
                is_default=is_default,
            )
            return {"status": "accepted", "code": "accepted", "canonical": created}

        if existing is None:
            raise MobileSyncConflictError(
                "The account does not exist on the desktop database.",
                canonical=None,
            )
        if int(existing.get("sync_version") or 0) != int(base_version):
            raise MobileSyncConflictError(
                "The desktop account version changed before this update was applied.",
                canonical=existing,
            )
        if existing_by_name is not None and int(existing_by_name["id"]) != int(existing["id"]):
            raise MobileSyncConflictError(
                "An account with the same normalized name already exists on the desktop database.",
                canonical=existing_by_name,
            )
        self._db.account.update(
            int(existing["id"]),
            name,
            account_type,
            currency,
            device_id=device_id,
            is_default=is_default,
        )
        return {
            "status": "accepted",
            "code": "accepted",
            "canonical": self._db.account.find_by_global_id(global_id),
        }

    def _apply_category_operation(
        self,
        device_id: str,
        operation: str,
        global_id: str,
        base_version: int,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        existing = self._db.category.find_by_global_id(global_id)
        if operation == "delete":
            if existing is None:
                return {"status": "accepted", "code": "already_deleted", "canonical": None}
            if int(existing.get("sync_version") or 0) != int(base_version):
                raise MobileSyncConflictError(
                    "The desktop category version changed before this update was applied.",
                    canonical=existing,
                )
            self._db.category.delete(int(existing["id"]))
            return {"status": "accepted", "code": "accepted", "canonical": None}

        assert payload is not None
        name = self._normalized_optional_string(payload.get("name"))
        if not name:
            raise MobileSyncError("Category payload must include name.")
        cat_type = self._normalized_optional_string(payload.get("type")) or "expense"
        color = self._normalized_optional_string(payload.get("color")) or "#888888"
        icon = self._normalized_optional_string(payload.get("icon")) or ""
        is_savings = bool(payload.get("is_savings"))
        parent_id = self._resolve_parent_category_id(self._normalized_optional_string(payload.get("parent_global_id")))
        existing_by_name = self._db.category.find_by_name(name, cat_type)

        if operation == "create":
            if existing is not None:
                if (
                    self._normalized_optional_string(existing.get("name")) == name
                    and self._normalized_optional_string(existing.get("type")) == cat_type
                ):
                    return {"status": "accepted", "code": "already_synced", "canonical": existing}
                raise MobileSyncConflictError(
                    "A category with this global_id already exists on the desktop database.",
                    canonical=existing,
                )
            if existing_by_name is not None and str(existing_by_name.get("global_id")) != global_id:
                raise MobileSyncConflictError(
                    "A category with the same normalized name already exists on the desktop database.",
                    canonical=existing_by_name,
                )
            created = self._db.category.create(
                name,
                cat_type,
                color=color,
                parent_id=parent_id,
                is_savings=is_savings,
                icon=icon,
                global_id=global_id,
                device_id=device_id,
            )
            return {"status": "accepted", "code": "accepted", "canonical": created}

        if existing is None:
            raise MobileSyncConflictError(
                "The category does not exist on the desktop database.",
                canonical=None,
            )
        if int(existing.get("sync_version") or 0) != int(base_version):
            raise MobileSyncConflictError(
                "The desktop category version changed before this update was applied.",
                canonical=existing,
            )
        if existing_by_name is not None and int(existing_by_name["id"]) != int(existing["id"]):
            raise MobileSyncConflictError(
                "A category with the same normalized name already exists on the desktop database.",
                canonical=existing_by_name,
            )
        self._db.category.update(
            int(existing["id"]),
            name,
            cat_type,
            color=color,
            is_savings=is_savings,
            parent_id=parent_id,
            icon=icon,
            device_id=device_id,
        )
        return {
            "status": "accepted",
            "code": "accepted",
            "canonical": self._db.category.find_by_global_id(global_id),
        }

    def _apply_tag_operation(
        self,
        device_id: str,
        operation: str,
        global_id: str,
        base_version: int,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        existing = self._db.tag.find_by_global_id(global_id)
        if operation == "delete":
            if existing is None:
                return {"status": "accepted", "code": "already_deleted", "canonical": None}
            if int(existing.get("sync_version") or 0) != int(base_version):
                raise MobileSyncConflictError(
                    "The desktop tag version changed before this update was applied.",
                    canonical=existing,
                )
            self._db.tag.delete(int(existing["id"]))
            return {"status": "accepted", "code": "accepted", "canonical": None}

        assert payload is not None
        name = self._normalized_optional_string(payload.get("name"))
        if not name:
            raise MobileSyncError("Tag payload must include name.")
        color = self._normalized_optional_string(payload.get("color")) or "#888888"
        icon = self._normalized_optional_string(payload.get("icon")) or ""
        existing_by_name = self._db.tag.find_by_name(name)

        if operation == "create":
            if existing is not None:
                if self._normalized_optional_string(existing.get("name")) == name:
                    return {"status": "accepted", "code": "already_synced", "canonical": existing}
                raise MobileSyncConflictError(
                    "A tag with this global_id already exists on the desktop database.",
                    canonical=existing,
                )
            if existing_by_name is not None and str(existing_by_name.get("global_id")) != global_id:
                raise MobileSyncConflictError(
                    "A tag with the same normalized name already exists on the desktop database.",
                    canonical=existing_by_name,
                )
            created = self._db.tag.create(
                name,
                color=color,
                icon=icon,
                global_id=global_id,
                device_id=device_id,
            )
            return {"status": "accepted", "code": "accepted", "canonical": created}

        if existing is None:
            raise MobileSyncConflictError(
                "The tag does not exist on the desktop database.",
                canonical=None,
            )
        if int(existing.get("sync_version") or 0) != int(base_version):
            raise MobileSyncConflictError(
                "The desktop tag version changed before this update was applied.",
                canonical=existing,
            )
        if existing_by_name is not None and int(existing_by_name["id"]) != int(existing["id"]):
            raise MobileSyncConflictError(
                "A tag with the same normalized name already exists on the desktop database.",
                canonical=existing_by_name,
            )
        self._db.tag.update(
            int(existing["id"]),
            name,
            color,
            icon=icon,
            device_id=device_id,
        )
        return {
            "status": "accepted",
            "code": "accepted",
            "canonical": self._db.tag.find_by_global_id(global_id),
        }

    def _apply_profile_settings_operation(
        self,
        device_id: str,
        operation: str,
        base_version: int,
        payload: Any,
    ) -> dict[str, Any]:
        if operation != "update":
            raise MobileSyncError("Profile settings currently support only update operations.")
        if not isinstance(payload, dict):
            raise MobileSyncError("Profile settings payload must be an object.")

        canonical = self._profile_settings_payload()
        current_version = int(canonical.get("sync_version") or 1)
        if current_version != int(base_version) and not (current_version == 1 and int(base_version) == 0):
            raise MobileSyncConflictError(
                "The desktop profile settings changed before this update was applied.",
                canonical=canonical,
            )

        default_currency = (self._normalized_optional_string(payload.get("default_currency")) or self._db.setting.get_default_currency()).upper()
        _nf = payload.get("number_format")
        number_format: dict[str, object] = _nf if isinstance(_nf, dict) else {}
        thousands_separator = self._normalized_optional_string(number_format.get("thousands_separator")) or ","
        decimal_separator = self._normalized_optional_string(number_format.get("decimal_separator")) or "."
        if thousands_separator == decimal_separator:
            raise MobileSyncError("Thousands and decimal separators must be different.")

        next_version = max(current_version, int(base_version or 0)) + 1
        updated_at = normalize_utc_iso(utc_now())
        self._db.setting.set("default_currency", default_currency)
        self._db.setting.set("number_thousands_separator", thousands_separator)
        self._db.setting.set("number_decimal_separator", decimal_separator)
        self._db.setting.set(_PROFILE_SETTINGS_SYNC_VERSION_KEY, str(next_version))
        self._db.setting.set(_PROFILE_SETTINGS_UPDATED_AT_KEY, updated_at)
        self._db.setting.set(_PROFILE_SETTINGS_LAST_MODIFIED_BY_DEVICE_ID_KEY, device_id)
        self._db.setting.set("master_data_updated_at", updated_at)
        return {
            "status": "accepted",
            "code": "accepted",
            "canonical": self._profile_settings_payload(),
        }

    def _apply_push_item(
        self,
        device_id: str,
        item: dict[str, Any],
        *,
        master_data_base_at: str | None,
    ) -> dict[str, Any]:
        operation = str(item.get("operation") or "").strip().lower()
        sync_id = self._normalized_optional_string(item.get("sync_id"))
        base_version = int(item.get("base_version") or 0)
        payload = item.get("transaction")
        item_master_data_base_at = (
            self._normalized_optional_string(item.get("master_data_base_at")) or master_data_base_at
        )
        match operation:
            case "create":
                if not sync_id:
                    raise MobileSyncError("Create operations require a transaction sync_id.")
                return self._apply_create(device_id, sync_id, payload, base_version, item_master_data_base_at)
            case "update":
                if not sync_id:
                    raise MobileSyncError("Update operations require a transaction sync_id.")
                return self._apply_update(device_id, sync_id, payload, base_version, item_master_data_base_at)
            case "delete":
                if not sync_id:
                    raise MobileSyncError("Delete operations require a transaction sync_id.")
                return self._apply_delete(device_id, sync_id, base_version)
            case _:
                raise MobileSyncError(f"Unsupported transaction operation: {operation!r}")

    def _apply_create(
        self,
        device_id: str,
        sync_id: str,
        payload: Any,
        base_version: int,
        master_data_base_at: str | None,
    ) -> dict[str, Any]:
        if base_version not in {0, 1}:
            raise MobileSyncConflictError(
                "Create operation uses a non-zero base_version.",
                canonical=self._canonical_state(sync_id),
            )

        existing = self._db.sync.get_transaction_by_sync_id(sync_id)
        if existing is not None:
            data = self._validated_push_payload(payload, master_data_base_at=master_data_base_at)
            canonical = self._canonical_transaction(sync_id)
            if canonical is not None and self._is_equivalent_transaction_payload(data, canonical):
                return {
                    "status": "accepted",
                    "code": "already_synced",
                    "transaction": canonical,
                }
            raise MobileSyncConflictError(
                "A transaction with this sync_id already exists.",
                canonical=self._canonical_state(sync_id),
            )
        if self._db.sync.get_tombstone(sync_id) is not None:
            raise MobileSyncConflictError(
                "A transaction with this sync_id already exists as a tombstone.",
                canonical=self._canonical_state(sync_id),
            )

        data = self._validated_push_payload(payload, master_data_base_at=master_data_base_at)
        created = self._db.transaction.create(
            account_id=data.account_id,
            tx_type=data.tx_type,
            amount=data.amount,
            description=data.description,
            category=data.category_name,
            category_id=data.category_id,
            tx_date=data.tx_date,
            note=data.note,
            payment_method=data.payment_method,
            to_account_id=data.to_account_id,
            is_transfer=int(data.is_transfer),
            exchange_rate=data.exchange_rate,
            converted_amount=data.converted_amount,
            sync_id=sync_id,
            device_id=device_id,
            source="mobile_sync",
        )
        if data.tag_ids:
            self._db.tag.set_for_transaction(
                int(created["id"]),
                data.tag_ids,
                device_id=device_id,
                touch_sync=False,
            )
        return {
            "status": "accepted",
            "code": "accepted",
            "transaction": self._canonical_transaction(sync_id),
        }

    def _apply_update(
        self,
        device_id: str,
        sync_id: str,
        payload: Any,
        base_version: int,
        master_data_base_at: str | None,
    ) -> dict[str, Any]:
        existing = self._db.sync.get_transaction_by_sync_id(sync_id)
        if existing is None:
            raise MobileSyncConflictError(
                "The transaction does not exist on the desktop database.",
                canonical=self._canonical_state(sync_id),
            )
        if int(existing.get("sync_version") or 0) != int(base_version):
            raise MobileSyncConflictError(
                "The desktop transaction version changed before this update was applied.",
                canonical=self._canonical_state(sync_id),
            )

        data = self._validated_push_payload(payload, master_data_base_at=master_data_base_at)
        updated = self._db.transaction.update(
            int(existing["id"]),
            account_id=data.account_id,
            tx_type=data.tx_type,
            amount=data.amount,
            description=data.description,
            category=data.category_name,
            category_id=data.category_id,
            tx_date=data.tx_date,
            note=data.note,
            payment_method=data.payment_method,
            to_account_id=data.to_account_id,
            is_transfer=int(data.is_transfer),
            exchange_rate=data.exchange_rate,
            converted_amount=data.converted_amount,
            sync_id=sync_id,
            device_id=device_id,
        )
        self._db.tag.set_for_transaction(
            int(updated["id"]),
            data.tag_ids,
            device_id=device_id,
            touch_sync=False,
        )
        return {
            "status": "accepted",
            "code": "accepted",
            "transaction": self._canonical_transaction(sync_id),
        }

    def _apply_delete(self, device_id: str, sync_id: str, base_version: int) -> dict[str, Any]:
        tombstone = self._db.sync.get_tombstone(sync_id)
        if tombstone is not None and self._db.sync.get_transaction_by_sync_id(sync_id) is None:
            if int(base_version or tombstone["last_deleted_version"]) > int(tombstone["last_deleted_version"]):
                raise MobileSyncConflictError(
                    "The desktop transaction was already deleted at a different version.",
                    canonical=self._canonical_state(sync_id),
                )
            return {
                "status": "accepted",
                "code": "already_deleted",
                "transaction": None,
                "tombstone": tombstone,
            }

        existing = self._db.sync.get_transaction_by_sync_id(sync_id)
        if existing is None:
            raise MobileSyncConflictError(
                "The transaction no longer exists on the desktop database.",
                canonical=self._canonical_state(sync_id),
            )
        if int(existing.get("sync_version") or 0) != int(base_version):
            raise MobileSyncConflictError(
                "The desktop transaction version changed before this delete was applied.",
                canonical=self._canonical_state(sync_id),
            )

        self._db.transaction.delete(int(existing["id"]), device_id=device_id)
        return {
            "status": "accepted",
            "code": "accepted",
            "transaction": None,
            "tombstone": self._db.sync.get_tombstone(sync_id),
        }

    def _canonical_transaction(self, sync_id: str) -> dict[str, Any] | None:
        transaction = self._db.sync.get_transaction_by_sync_id(sync_id)
        if transaction is None:
            return None
        tags = self._db.tag.list_for_transaction(int(transaction["id"]))
        account_id = transaction.get("account_id")
        to_account_id = transaction.get("to_account_id")
        category_id = transaction.get("category_id")
        account = None if account_id is None else self._db.account.get(int(account_id))
        to_account = None if to_account_id is None else self._db.account.get(int(to_account_id))
        category = None if category_id is None else self._db.category.get(int(category_id))
        transaction["tag_ids"] = [int(tag["id"]) for tag in tags]
        transaction["tag_global_ids"] = [
            str(tag["global_id"]) for tag in tags if str(tag.get("global_id") or "").strip()
        ]
        transaction["account_global_id"] = None if account is None else account.get("global_id")
        transaction["to_account_global_id"] = None if to_account is None else to_account.get("global_id")
        transaction["category_global_id"] = None if category is None else category.get("global_id")
        return transaction

    def _canonical_state(self, sync_id: str) -> dict[str, Any]:
        return {
            "transaction": self._canonical_transaction(sync_id),
            "tombstone": self._db.sync.get_tombstone(sync_id),
        }

    def _validated_push_payload(
        self,
        payload: Any,
        *,
        master_data_base_at: str | None,
    ) -> ResolvedPushPayload:
        if not isinstance(payload, dict):
            raise MobileSyncError("Transaction payload must be an object.")

        tx_type = str(payload.get("tx_type") or payload.get("type") or "").strip().lower()
        if tx_type not in {"income", "expense"}:
            raise MobileSyncError("Mobile sync currently supports only income and expense transactions.")

        tx_date = str(payload.get("tx_date") or payload.get("date") or "").strip()
        if not tx_date:
            raise MobileSyncError("Transaction payload must include tx_date.")

        amount = payload.get("amount")
        if amount is None:
            raise MobileSyncError("Transaction payload must include amount.")

        account = self._resolve_required_account(payload, master_data_base_at=master_data_base_at)
        payment_method = str(payload.get("payment_method") or "cash").strip() or "cash"
        is_transfer = bool(payload.get("is_transfer")) or payment_method in {"transfer", "credit_payment"}
        to_account = self._resolve_optional_account(
            payload,
            master_data_base_at=master_data_base_at,
            field_name="to_account",
        )
        if is_transfer and to_account is None:
            raise MobileSyncError("Transfer transactions require to_account_global_id.")
        if to_account is not None and int(to_account["id"]) == int(account["id"]):
            raise MobileSyncError("Origin and destination accounts must be different.")
        category = self._resolve_optional_category(
            payload,
            tx_type=tx_type,
            master_data_base_at=master_data_base_at,
        )
        tags = self._resolve_tags(payload, master_data_base_at=master_data_base_at)

        return ResolvedPushPayload(
            tx_type=tx_type,
            account_id=int(account["id"]),
            account_global_id=str(account["global_id"]),
            to_account_id=None if to_account is None else int(to_account["id"]),
            to_account_global_id=None if to_account is None else str(to_account["global_id"]),
            is_transfer=is_transfer,
            amount=amount,
            tx_date=tx_date,
            category_name=None if category is None else str(category["name"]),
            category_id=None if category is None else int(category["id"]),
            category_global_id=None if category is None else str(category["global_id"]),
            payment_method=payment_method,
            description=self._normalized_optional_string(payload.get("description")),
            note=self._normalized_optional_string(payload.get("note")),
            exchange_rate=payload.get("exchange_rate"),
            converted_amount=payload.get("converted_amount"),
            tag_ids=[int(tag["id"]) for tag in tags],
            tag_global_ids=[str(tag["global_id"]) for tag in tags],
            master_data_base_at=master_data_base_at,
        )

    def _resolve_optional_account(
        self,
        payload: dict[str, Any],
        *,
        master_data_base_at: str | None,
        field_name: str = "account",
    ) -> dict[str, Any] | None:
        account_global_id = self._normalized_optional_string(payload.get(f"{field_name}_global_id"))
        if account_global_id:
            if (account := self._db.account.find_by_global_id(account_global_id)) is not None:
                return account
            self._raise_unknown_reference(
                "unknown_account",
                "The selected account no longer exists on the desktop database.",
                global_id=account_global_id,
                master_data_base_at=master_data_base_at,
            )

        account_id = payload.get(f"{field_name}_id")
        if account_id is not None:
            if (account := self._db.account.get(int(account_id))) is not None:
                return account
            self._raise_unknown_reference(
                "unknown_account",
                "The selected account no longer exists on the desktop database.",
                local_id=int(account_id),
                master_data_base_at=master_data_base_at,
            )
        return None

    def _resolve_required_account(
        self,
        payload: dict[str, Any],
        *,
        master_data_base_at: str | None,
    ) -> dict[str, Any]:
        account = self._resolve_optional_account(payload, master_data_base_at=master_data_base_at)
        if account is not None:
            return account
        raise MobileSyncError("Transaction payload must include account_global_id.", error_code="validation_error")

    def _resolve_optional_category(
        self,
        payload: dict[str, Any],
        *,
        tx_type: str,
        master_data_base_at: str | None,
    ) -> dict[str, Any] | None:
        category_global_id = self._normalized_optional_string(payload.get("category_global_id"))
        if category_global_id:
            category = self._db.category.find_by_global_id(category_global_id)
            if category is None or str(category.get("type") or "") != tx_type:
                self._raise_unknown_reference(
                    "unknown_category",
                    "The selected category no longer exists on the desktop database.",
                    global_id=category_global_id,
                    master_data_base_at=master_data_base_at,
                )
            return category

        category_id = payload.get("category_id")
        if category_id is not None:
            category = self._db.category.get(int(category_id))
            if category is None or str(category.get("type") or "") != tx_type:
                self._raise_unknown_reference(
                    "unknown_category",
                    "The selected category no longer exists on the desktop database.",
                    local_id=int(category_id),
                    master_data_base_at=master_data_base_at,
                )
            return category

        category_name = self._normalized_optional_string(payload.get("category"))
        if category_name:
            category = self._db.category.find_by_name(category_name, tx_type)
            if category is None:
                self._raise_unknown_reference(
                    "unknown_category",
                    "The selected category no longer exists on the desktop database.",
                    name=category_name,
                    master_data_base_at=master_data_base_at,
                )
            return category
        return None

    def _resolve_tags(
        self,
        payload: dict[str, Any],
        *,
        master_data_base_at: str | None,
    ) -> list[dict[str, Any]]:
        resolved: list[dict[str, Any]] = []
        tag_global_ids_raw = payload.get("tag_global_ids")
        match tag_global_ids_raw:
            case None:
                pass
            case list() as tag_global_ids:
                for global_id in dict.fromkeys(str(item).strip() for item in tag_global_ids if str(item).strip()):
                    tag = self._db.tag.find_by_global_id(global_id)
                    if tag is None:
                        self._raise_unknown_reference(
                            "unknown_tag",
                            "One or more tags no longer exist on the desktop database.",
                            global_id=global_id,
                            master_data_base_at=master_data_base_at,
                        )
                    resolved.append(tag)
                return resolved
            case _:
                raise MobileSyncError("tag_global_ids must be a list when provided.")

        tag_ids_raw = payload.get("tag_ids")
        match tag_ids_raw:
            case None:
                return resolved
            case list() as tag_ids:
                for local_id in dict.fromkeys(int(item) for item in tag_ids):
                    tag = self._db.tag.get(local_id)
                    if tag is None:
                        self._raise_unknown_reference(
                            "unknown_tag",
                            "One or more tags no longer exist on the desktop database.",
                            local_id=local_id,
                            master_data_base_at=master_data_base_at,
                        )
                    resolved.append(tag)
                return resolved
            case _:
                raise MobileSyncError("tag_ids must be a list when provided.")

    def _raise_unknown_reference(
        self,
        reference_code: str,
        message: str,
        *,
        global_id: str | None = None,
        local_id: int | None = None,
        name: str | None = None,
        master_data_base_at: str | None,
    ) -> NoReturn:
        current_master_data_updated_at = self._current_master_data_updated_at()
        details = {
            "reference_code": reference_code,
            "global_id": global_id,
            "local_id": local_id,
            "name": name,
            "current_master_data_updated_at": current_master_data_updated_at,
            "client_master_data_base_at": master_data_base_at,
        }
        if master_data_base_at and normalize_utc_iso(master_data_base_at) < normalize_utc_iso(
            current_master_data_updated_at
        ):
            raise MobileSyncError(
                "The mobile master data snapshot is stale. Refresh master data and retry.",
                error_code="master_data_stale",
                status_code=HTTPStatus.CONFLICT,
                details=details,
            )
        raise MobileSyncError(
            message,
            error_code=reference_code,
            status_code=HTTPStatus.CONFLICT,
            details=details,
        )

    def _validate_pairing_secret(self, payload: dict[str, Any], pairing_state: PairingState) -> None:
        if utc_now() > pairing_state.expires_at:
            raise MobileSyncAuthError(
                "The pairing code has expired.",
                error_code="pairing_expired",
            )

        pairing_token = self._normalized_optional_string(payload.get("pairing_token"))
        if pairing_token:
            if len(pairing_token) < _PAIRING_TOKEN_MIN_LENGTH:
                raise MobileSyncAuthError(
                    "Malformed pairing token.",
                    error_code="validation_error",
                )
            if pairing_token != pairing_state.pairing_token:
                raise MobileSyncAuthError("Invalid pairing token.", error_code="authorization_failed")
            return

        pairing_code = self._normalized_optional_string(payload.get("pairing_code"))
        if not pairing_code:
            raise MobileSyncAuthError(
                "Pairing requires a pairing_code or pairing_token.",
                error_code="validation_error",
            )
        if pairing_code != pairing_state.pairing_code:
            raise MobileSyncAuthError("Invalid pairing code.", error_code="authorization_failed")

    def _require_pairing_state(self) -> PairingState:
        pairing_state = self._pairing_state
        if pairing_state is None:
            raise MobileSyncError("The mobile sync service is not active.")
        if utc_now() > pairing_state.expires_at:
            raise MobileSyncAuthError(
                "The pairing code expired. Start sync again from the desktop menu.",
                error_code="pairing_expired",
            )
        return pairing_state

    def _require_session(self, token: str) -> AuthSession:
        with self._lock:
            self._purge_expired_sessions()
            session = self._sessions.get(token)
            if session is None:
                raise MobileSyncAuthError("Missing or expired mobile sync session.")
            return session

    def _purge_expired_sessions(self) -> None:
        now = utc_now()
        expired_tokens = [token for token, session in self._sessions.items() if now > session.expires_at]
        for token in expired_tokens:
            self._sessions.pop(token, None)

    def _current_master_data_updated_at(self) -> str:
        return normalize_utc_iso(self._db.setting.get_master_data_updated_at())

    def _push_atomic_context(self):
        backend = getattr(self._db, "_backend", None)
        atomic = getattr(backend, "_atomic", None)
        return atomic() if callable(atomic) else nullcontext()

    def _emit_event(self, kind: str, message: str, *, level: str = "info") -> None:
        if self._event_sink is None:
            return
        self._event_sink(
            MobileSyncServerEvent(
                kind=kind,
                title=_SERVICE_NAME,
                message=message,
                level=level,
                created_at=utc_now_iso(),
            )
        )

    @staticmethod
    def _normalized_optional_string(value: object) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @staticmethod
    def _decimal_text(value: Any) -> str | None:
        if value is None:
            return None
        return str(Decimal(str(value)).normalize())

    def _is_equivalent_transaction_payload(self, data: ResolvedPushPayload, canonical: dict[str, Any]) -> bool:
        return all(
            (
                str(canonical.get("type") or "") == data.tx_type,
                int(canonical.get("account_id") or 0) == data.account_id,
                int(canonical.get("to_account_id") or 0) == int(data.to_account_id or 0),
                bool(canonical.get("is_transfer")) == data.is_transfer,
                str(canonical.get("date") or "") == data.tx_date,
                self._decimal_text(canonical.get("amount")) == self._decimal_text(data.amount),
                self._decimal_text(canonical.get("exchange_rate")) == self._decimal_text(data.exchange_rate),
                self._decimal_text(canonical.get("converted_amount")) == self._decimal_text(data.converted_amount),
                self._normalized_optional_string(canonical.get("description")) == data.description,
                self._normalized_optional_string(canonical.get("note")) == data.note,
                self._normalized_optional_string(canonical.get("payment_method")) == data.payment_method,
                self._normalized_optional_string(canonical.get("category")) == data.category_name,
                sorted(int(item) for item in canonical.get("tag_ids") or []) == sorted(data.tag_ids),
            )
        )

    @staticmethod
    def _generate_pairing_code() -> str:
        return "".join(choice(_PAIRING_CODE_DIGITS) for _ in range(6))


class _ZeroconfPublisher:
    def __init__(self) -> None:
        """Initialize."""
        self._zeroconf: Any = None
        self._service_info: Any = None

    def start(self, *, port: int, properties: dict[str, str]) -> tuple[bool, tuple[str, ...]]:
        """Return start."""
        try:
            from zeroconf import IPVersion, ServiceInfo, Zeroconf  # noqa: PLC0415  # type: ignore[import-not-found]
        except ImportError:
            logger.info("zeroconf dependency not installed; LAN announcement disabled")
            return False, tuple(_discover_local_addresses())

        addresses = _discover_local_addresses()
        packed_addresses = [socket.inet_aton(address) for address in addresses]
        self._zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
        self._service_info = ServiceInfo(
            _SERVICE_TYPE,
            f"{_SERVICE_NAME}.{_SERVICE_TYPE}",
            addresses=packed_addresses,
            port=port,
            properties={key: value.encode("utf-8") for key, value in properties.items()},
            server=f"{socket.gethostname()}.local.",
        )
        self._zeroconf.register_service(self._service_info)
        return True, tuple(addresses)

    def stop(self) -> None:
        """Return stop."""
        if self._zeroconf is None or self._service_info is None:
            return
        try:
            self._zeroconf.unregister_service(self._service_info)
        finally:
            self._zeroconf.close()
            self._zeroconf = None
            self._service_info = None


def _is_lan_or_loopback_address(host: str) -> bool:
    candidate = str(host or "").strip()
    if not candidate:
        return False
    try:
        parsed = ip_address(candidate.split("%", maxsplit=1)[0])
    except ValueError:
        try:
            resolved = socket.gethostbyname(candidate)
        except OSError:
            return False
        parsed = ip_address(resolved)
    if parsed.is_unspecified or parsed.is_multicast:
        return False
    return bool(parsed.is_loopback or parsed.is_private or parsed.is_link_local)


def _address_priority(host: str) -> int:
    parsed = ip_address(host)
    match parsed:
        case _ if parsed.is_loopback:
            return 2
        case _ if parsed.is_link_local:
            return 1
        case _ if parsed.is_private:
            return 0
        case _:
            return 3


def _ordered_unique_addresses(candidates: list[str]) -> tuple[str, ...]:
    filtered = [
        address for address in dict.fromkeys(candidates) if "." in address and _is_lan_or_loopback_address(address)
    ]
    if not filtered:
        return ("127.0.0.1",)
    prioritized = [address for address in filtered if _address_priority(address) == 0]
    link_local = [address for address in filtered if _address_priority(address) == 1]
    loopback = [address for address in filtered if _address_priority(address) == 2]
    return tuple(prioritized + link_local + loopback)


def _discover_socket_local_addresses() -> list[str]:
    candidates: list[str] = []
    probe_targets = (
        ("192.168.255.255", 9),
        ("10.255.255.255", 9),
        ("172.16.255.255", 9),
    )
    for host, port in probe_targets:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect((host, port))
            local_host, _ = sock.getsockname()
            if local_host:
                candidates.append(local_host)
        except OSError:
            continue
        finally:
            sock.close()
    return candidates


def _discover_local_addresses() -> list[str]:
    candidates: list[str] = []
    candidates.extend(_discover_socket_local_addresses())
    try:
        _, _, host_addresses = socket.gethostbyname_ex(socket.gethostname())
        candidates.extend(host_addresses)
    except OSError:
        pass
    return list(_ordered_unique_addresses(candidates))


def _select_local_address_info(candidates: tuple[str, ...] | list[str]) -> LocalAddressSelection:
    ordered = _ordered_unique_addresses(list(candidates))
    preferred_host = next((address for address in ordered if not ip_address(address).is_loopback), ordered[0])
    return LocalAddressSelection(preferred_host=preferred_host, advertised_addresses=ordered)


def _json_default(value: Any) -> Any:
    match value:
        case datetime() | date():
            return normalize_utc_iso(value)
        case Decimal() as amount:
            return float(amount)
        case Path() as path:
            return str(path)
        case _:
            return str(value)


class _MobileSyncRequestHandler(BaseHTTPRequestHandler):
    server_version = "MIRAMobileSync/1.0"

    @property
    def sync_server(self) -> "MobileSyncServer":
        """Return sync server."""
        return self.server.sync_server  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: object) -> None:
        """Return log message."""
        logger.debug("mobile-sync %s - %s", self.address_string(), format % args)

    def do_GET(self) -> None:  # noqa: N802
        """Return do GET."""
        try:
            self._ensure_lan_client()
            parsed = urlparse(self.path)
            match parsed.path:
                case "/api/mobile/v1/status":
                    self._ensure_rate_limit(parsed.path)
                    self._write_json(HTTPStatus.OK, self.sync_server.service.status_payload())
                case "/api/mobile/v1/master-data":
                    self._ensure_rate_limit(parsed.path)
                    token = self._bearer_token()
                    self._write_json(HTTPStatus.OK, self.sync_server.service.master_data_payload(token))
                case "/api/mobile/v1/snapshot":
                    self._ensure_rate_limit(parsed.path)
                    token = self._bearer_token()
                    self._write_json(HTTPStatus.OK, self.sync_server.service.snapshot_payload(token))
                case "/api/mobile/v1/transactions/changes":
                    self._ensure_rate_limit(parsed.path)
                    token = self._bearer_token()
                    query = parse_qs(parsed.query)
                    after_event_id = int((query.get("after_event_id") or ["0"])[0] or 0)
                    limit = int((query.get("limit") or ["500"])[0] or 500)
                    self._write_json(
                        HTTPStatus.OK,
                        self.sync_server.service.changes_payload(token, after_event_id=after_event_id, limit=limit),
                    )
                case _:
                    self._write_json(HTTPStatus.NOT_FOUND, {"error": "Endpoint not found", "error_code": "not_found"})
        except MobileSyncError as exc:
            self._write_error(exc)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected mobile sync GET failure")
            self._write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": str(exc), "error_code": "internal_error"},
            )

    def do_POST(self) -> None:  # noqa: N802
        """Return do POST."""
        try:
            self._ensure_lan_client()
            parsed = urlparse(self.path)
            match parsed.path:
                case "/api/mobile/v1/pair":
                    self._ensure_rate_limit(parsed.path)
                    payload = self._read_json_body()
                    self._write_json(HTTPStatus.OK, self.sync_server.service.pair_device(payload))
                case "/api/mobile/v1/transactions/push":
                    token = self._optional_bearer_token()
                    self._ensure_rate_limit(parsed.path, token=token)
                    token = self._require_bearer_token(token)
                    payload = self._read_json_body()
                    self._write_json(HTTPStatus.OK, self.sync_server.service.push_transactions(token, payload))
                case "/api/mobile/v1/catalog/push":
                    token = self._optional_bearer_token()
                    self._ensure_rate_limit(parsed.path, token=token)
                    token = self._require_bearer_token(token)
                    payload = self._read_json_body()
                    self._write_json(HTTPStatus.OK, self.sync_server.service.push_catalog(token, payload))
                case "/api/mobile/v1/transactions/ack":
                    self._ensure_rate_limit(parsed.path)
                    token = self._bearer_token()
                    payload = self._read_json_body()
                    self._write_json(HTTPStatus.OK, self.sync_server.service.ack_payload(token, payload))
                case _:
                    self._write_json(HTTPStatus.NOT_FOUND, {"error": "Endpoint not found", "error_code": "not_found"})
        except MobileSyncError as exc:
            self._write_error(exc)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected mobile sync POST failure")
            self._write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": str(exc), "error_code": "internal_error"},
            )

    def _ensure_lan_client(self) -> None:
        client_host = str(self.client_address[0] or "").strip()
        if _is_lan_or_loopback_address(client_host):
            return
        raise MobileSyncForbiddenError(
            "The mobile sync service only accepts loopback and LAN requests.",
            error_code="lan_only",
        )

    def _ensure_rate_limit(self, path: str, *, token: str | None = None) -> None:
        client_host = str(self.client_address[0] or "").strip()
        self.sync_server.check_rate_limit(path, client_host=client_host, token=token)

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise MobileSyncError("Invalid JSON body.") from exc
        if not isinstance(decoded, dict):
            raise MobileSyncError("The request body must be a JSON object.")
        return decoded

    def _bearer_token(self) -> str:
        return self._require_bearer_token(self._optional_bearer_token())

    def _optional_bearer_token(self) -> str | None:
        header = str(self.headers.get("Authorization") or "").strip()
        prefix = "Bearer "
        if not header.startswith(prefix):
            return None
        token = header[len(prefix) :].strip()
        return token

    @staticmethod
    def _require_bearer_token(token: str | None) -> str:
        if token is None:
            raise MobileSyncAuthError("Authorization header is missing.")
        if not token:
            raise MobileSyncAuthError("Authorization token is missing.")
        return token

    def _write_error(self, exc: MobileSyncError) -> None:
        payload: dict[str, Any] = {
            "error": str(exc),
            "error_code": exc.error_code,
        }
        if isinstance(exc, MobileSyncRateLimitError):
            payload["retry_after_seconds"] = exc.retry_after_seconds
        if exc.details is not None:
            payload["details"] = exc.details
        if exc.canonical is not None:
            payload["canonical"] = exc.canonical
        self._write_json(exc.status_code, payload)

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, default=_json_default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class MobileSyncServer:
    """Represent the MobileSyncServer class."""

    def __init__(self, db: Database) -> None:
        """Initialize."""
        self._events: deque[MobileSyncServerEvent] = deque(maxlen=50)
        self._events_lock = threading.RLock()
        self._lifecycle_lock = threading.RLock()
        self._pairing_timeout_timer: threading.Timer | None = None
        self.service = MobileSyncService(db, event_sink=self._record_event)
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._publisher = _ZeroconfPublisher()
        self._rate_limiter = _MobileSyncRateLimiter()
        self._tls_context: ssl.SSLContext | None = None
        self._tls_dir: tempfile.TemporaryDirectory[str] | None = None
        self._tls_fingerprint_sha256: str = ""
        self._status: MobileSyncServerStatus | None = None

    @property
    def is_running(self) -> bool:
        """Return is running."""
        return self._httpd is not None

    @property
    def status(self) -> MobileSyncServerStatus | None:
        """Return status."""
        return self._status

    def drain_events(self) -> list[MobileSyncServerEvent]:
        """Return drain events."""
        with self._events_lock:
            events = list(self._events)
            self._events.clear()
            return events

    def check_rate_limit(self, path: str, *, client_host: str, token: str | None = None) -> None:
        """Return check rate limit."""
        rule = _RATE_LIMIT_RULES.get(path)
        if rule is None:
            return
        normalized_host = str(client_host or "").strip() or "unknown"
        key: tuple[str, ...]
        if rule.include_token:
            key = (path, normalized_host, str(token or _ANONYMOUS_TOKEN_KEY))
        else:
            key = (path, normalized_host)
        decision = self._rate_limiter.check(key, rule)
        if not decision.allowed:
            raise MobileSyncRateLimitError(retry_after_seconds=decision.retry_after_seconds)

    def start(self) -> MobileSyncServerStatus:
        """Return start."""
        with self._lifecycle_lock:
            pairing_state = self.service.start_pairing()
            local_addresses = tuple(_discover_local_addresses())
            if self._httpd is None:
                httpd = ThreadingHTTPServer(("0.0.0.0", 0), _MobileSyncRequestHandler)
                httpd.daemon_threads = True
                httpd.sync_server = self  # type: ignore[attr-defined]
                self._configure_tls(httpd, local_addresses)
                self._httpd = httpd
                self._thread = threading.Thread(
                    target=httpd.serve_forever,
                    daemon=True,
                    name="mira-mobile-sync",
                )
                self._thread.start()

            assert self._httpd is not None
            self._publisher.stop()
            advertised, addresses = self._publisher.start(
                port=int(self._httpd.server_port),
                properties={
                    "protocol_version": self.service.protocol_version,
                    "pairing_required": "1",
                    "transport_scheme": "https",
                    "tls_fingerprint_sha256": self._tls_fingerprint_sha256,
                },
            )
            address_selection = _select_local_address_info(addresses)
            pairing_payload = self._build_pairing_payload(
                host=address_selection.preferred_host,
                port=int(self._httpd.server_port),
                pairing_state=pairing_state,
                addresses=address_selection.advertised_addresses,
                tls_fingerprint_sha256=self._tls_fingerprint_sha256,
            )
            lan_warning = None
            if not address_selection.has_non_loopback_lan:
                lan_warning = (
                    "No se detecto una direccion LAN privada util. "
                    "El QR seguira disponible, pero otro dispositivo podria no alcanzar este escritorio."
                )
            self._status = MobileSyncServerStatus(
                service_name=_SERVICE_NAME,
                protocol_version=self.service.protocol_version,
                host=address_selection.preferred_host,
                port=int(self._httpd.server_port),
                pairing_code=pairing_state.pairing_code,
                pairing_token=pairing_state.pairing_token,
                pairing_expires_at=normalize_utc_iso(pairing_state.expires_at),
                advertisement_enabled=advertised,
                advertised_addresses=address_selection.advertised_addresses,
                transport_scheme="https",
                tls_fingerprint_sha256=self._tls_fingerprint_sha256,
                lan_warning=lan_warning,
                pairing_payload=pairing_payload,
            )
            self._schedule_pairing_timeout(pairing_state.expires_at)
            self._record_event(
                MobileSyncServerEvent(
                    kind="session.started",
                    title=_SERVICE_NAME,
                    message=(
                        "Sincronizacion movil activa. "
                        f"Codigo temporal: {pairing_state.pairing_code}. "
                        f"Direcciones LAN: {', '.join(address_selection.advertised_addresses)}. "
                        f"Puerto: {int(self._httpd.server_port)}."
                    ),
                    level="info",
                    created_at=utc_now_iso(),
                )
            )
            if lan_warning:
                self._record_event(
                    MobileSyncServerEvent(
                        kind="session.lan_warning",
                        title=_SERVICE_NAME,
                        message=lan_warning,
                        level="warning",
                        created_at=utc_now_iso(),
                    )
                )
            return self._status

    def stop(self) -> None:
        """Return stop."""
        with self._lifecycle_lock:
            self._cancel_pairing_timeout()
            self.service.stop()
            self._rate_limiter.clear()
            self._publisher.stop()
            if self._httpd is not None:
                self._httpd.shutdown()
                self._httpd.server_close()
            if self._thread is not None and self._thread is not threading.current_thread():
                self._thread.join(timeout=2.0)
            self._httpd = None
            self._thread = None
            self._status = None
            self._tls_context = None
            if self._tls_dir is not None:
                self._tls_dir.cleanup()
            self._tls_dir = None
            self._tls_fingerprint_sha256 = ""

    def __enter__(self) -> "MobileSyncServer":
        """Return context manager."""
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Return exit context manager."""
        del exc_type, exc, tb
        self.stop()

    def _record_event(self, event: MobileSyncServerEvent) -> None:
        with self._events_lock:
            self._events.append(event)

    def _build_pairing_payload(
        self,
        *,
        host: str,
        port: int,
        pairing_state: PairingState,
        addresses: tuple[str, ...],
        tls_fingerprint_sha256: str,
    ) -> dict[str, Any]:
        return {
            "protocol_version": self.service.protocol_version,
            "api_base_url": f"https://{host}:{port}/api/mobile/v1",
            "host": host,
            "port": port,
            "transport_scheme": "https",
            "tls_fingerprint_sha256": tls_fingerprint_sha256,
            "pairing_code": pairing_state.pairing_code,
            "pairing_token": pairing_state.pairing_token,
            "pairing_expires_at": normalize_utc_iso(pairing_state.expires_at),
            "advertised_addresses": list(addresses),
        }

    def _configure_tls(self, httpd: ThreadingHTTPServer, addresses: tuple[str, ...]) -> None:
        from cryptography import x509  # noqa: PLC0415
        from cryptography.hazmat.primitives import hashes, serialization  # noqa: PLC0415
        from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: PLC0415
        from cryptography.x509.oid import NameOID  # noqa: PLC0415

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "MIRA Mobile Sync Local")])
        now = utc_now()
        san_entries: list[x509.GeneralName] = [x509.DNSName("localhost")]
        for address in dict.fromkeys(addresses):
            try:
                san_entries.append(x509.IPAddress(ip_address(address)))
            except ValueError:
                continue

        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(hours=12))
            .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
            .sign(private_key=key, algorithm=hashes.SHA256())
        )
        cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
        key_pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )

        temp_dir = tempfile.TemporaryDirectory(prefix="mira-mobile-sync-tls-")
        cert_path = Path(temp_dir.name) / "cert.pem"
        key_path = Path(temp_dir.name) / "key.pem"
        cert_path.write_bytes(cert_pem)
        key_path.write_bytes(key_pem)

        tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls_context.minimum_version = ssl.TLSVersion.TLSv1_2
        tls_context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
        if hasattr(httpd, "socket"):
            httpd.socket = tls_context.wrap_socket(httpd.socket, server_side=True)

        self._tls_context = tls_context
        self._tls_dir = temp_dir
        self._tls_fingerprint_sha256 = certificate.fingerprint(hashes.SHA256()).hex()

    def _schedule_pairing_timeout(self, expires_at: datetime) -> None:
        self._cancel_pairing_timeout()
        delay_seconds = max(1.0, (expires_at - utc_now()).total_seconds())
        self._pairing_timeout_timer = threading.Timer(delay_seconds, self._expire_if_unpaired)
        self._pairing_timeout_timer.daemon = True
        self._pairing_timeout_timer.start()

    def _cancel_pairing_timeout(self) -> None:
        timer = self._pairing_timeout_timer
        if timer is not None:
            timer.cancel()
        self._pairing_timeout_timer = None

    def _expire_if_unpaired(self) -> None:
        with self._lifecycle_lock:
            if self.service.has_active_sessions:
                return
        self._record_event(
            MobileSyncServerEvent(
                kind="session.expired",
                title=_SERVICE_NAME,
                message="La ventana de emparejamiento movil expiro sin conexiones y el servicio local se detuvo.",
                level="warning",
                created_at=utc_now_iso(),
            )
        )
        self.stop()
