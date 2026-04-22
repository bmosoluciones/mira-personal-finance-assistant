# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Master data sync utilities for desktop-mobile synchronization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mira.sync_utils import generate_ulid, utc_now_iso

MASTER_DATA_UPDATED_AT_SETTING = "master_data_updated_at"
LOCAL_DESKTOP_DEVICE_ID_SETTING = "local_desktop_device_id"
DEFAULT_MASTER_DATA_DEVICE_ID = "desktop-local"
MASTER_DATA_SYNC_UPDATE_RETRIES = 3


@dataclass(frozen=True)
class MasterDataSyncMetadata:
    """Represent the MasterDataSyncMetadata class."""

    global_id: str
    sync_version: int
    updated_at: str
    device_id: str


def normalize_master_data_device_id(device_id: str | None) -> str:
    """Return normalize master data device id."""
    normalized = str(device_id or DEFAULT_MASTER_DATA_DEVICE_ID).strip()
    return normalized or DEFAULT_MASTER_DATA_DEVICE_ID


def build_new_master_data_sync_metadata(
    *,
    global_id: str | None = None,
    device_id: str | None = None,
) -> MasterDataSyncMetadata:
    """Return build new master data sync metadata."""
    normalized_global_id = str(global_id or "").strip() or generate_ulid()
    normalized_device_id = normalize_master_data_device_id(device_id)
    return MasterDataSyncMetadata(
        global_id=normalized_global_id,
        sync_version=1,
        updated_at=utc_now_iso(),
        device_id=normalized_device_id,
    )


def build_next_master_data_sync_metadata(
    current_row: dict[str, Any],
    *,
    global_id: str | None = None,
    device_id: str | None = None,
) -> MasterDataSyncMetadata:
    """Return build next master data sync metadata."""
    current_global_id = (
        str(current_row.get("global_id") or "").strip() or str(global_id or "").strip() or generate_ulid()
    )
    current_version = int(current_row.get("sync_version") or 1)
    normalized_device_id = normalize_master_data_device_id(device_id)
    return MasterDataSyncMetadata(
        global_id=current_global_id,
        sync_version=current_version + 1,
        updated_at=utc_now_iso(),
        device_id=normalized_device_id,
    )
