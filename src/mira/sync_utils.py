# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Sync-related helpers shared by repositories, services, and migrations."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any

_CROCKFORD_BASE32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
SYNC_TIMESTAMP_FORMAT = "ISO 8601 UTC, whole seconds, trailing Z"


def _encode_crockford(value: int, length: int) -> str:
    encoded = ["0"] * length
    current = value
    for index in range(length - 1, -1, -1):
        encoded[index] = _CROCKFORD_BASE32[current & 0x1F]
        current >>= 5
    return "".join(encoded)


def utc_now() -> datetime:
    """Return utc now."""
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """Return the sync timestamp contract: ISO 8601 UTC with a trailing ``Z``."""
    return utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_utc_iso(value: Any) -> str:
    """Normalize SQLite/Peewee timestamp values to the sync timestamp contract."""
    match value:
        case datetime() as dt:
            normalized = dt.astimezone(timezone.utc) if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
            return normalized.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        case str() as raw if raw.strip():
            candidate = raw.strip().replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(candidate)
            except ValueError:
                return utc_now_iso()
            normalized = (
                parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
            )
            return normalized.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        case _:
            return utc_now_iso()


def generate_ulid(at: datetime | None = None) -> str:
    """Return generate ulid."""
    moment = utc_now() if at is None else at
    normalized = moment.astimezone(timezone.utc) if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)
    timestamp_ms = int(normalized.timestamp() * 1000)
    randomness = int.from_bytes(os.urandom(10), "big")
    return _encode_crockford(timestamp_ms, 10) + _encode_crockford(randomness, 16)
