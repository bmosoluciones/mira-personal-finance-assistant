# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

from mira.services.mobile_sync import MobileSyncServerStatus
from tests.qt_stubs import install_fake_pyside, load_module_from_path

_ROOT = Path(__file__).resolve().parents[1]


def test_mobile_sync_dialog_updates_qr_payload_and_lan_warning(monkeypatch) -> None:
    install_fake_pyside(monkeypatch)

    class _FakeQrCode:
        matrix = (
            (1, 0),
            (0, 1),
        )

    monkeypatch.setitem(
        sys.modules,
        "segno",
        SimpleNamespace(make=lambda _payload, error="m": _FakeQrCode()),
    )

    module = load_module_from_path(
        monkeypatch,
        "test_mobile_sync_dialog_module",
        str(_ROOT / "src" / "mira" / "ui" / "dialogs" / "mobile_sync.py"),
    )
    dialog = module.MobileSyncSessionDialog(language="en")
    status = MobileSyncServerStatus(
        service_name="MIRA Mobile Sync",
        protocol_version="1",
        host="127.0.0.1",
        port=43123,
        pairing_code="123456",
        pairing_token="pair-token",
        pairing_expires_at="2026-04-09T12:00:00Z",
        advertisement_enabled=False,
        advertised_addresses=("127.0.0.1",),
        transport_scheme="https",
        tls_fingerprint_sha256="a" * 64,
        lan_warning="LAN warning",
        pairing_payload={
            "protocol_version": "1",
            "api_base_url": "https://127.0.0.1:43123/api/mobile/v1",
            "host": "127.0.0.1",
            "port": 43123,
            "transport_scheme": "https",
            "tls_fingerprint_sha256": "a" * 64,
            "pairing_code": "123456",
            "pairing_token": "pair-token",
            "pairing_expires_at": "2026-04-09T12:00:00Z",
            "advertised_addresses": ["127.0.0.1"],
        },
    )

    dialog.set_status(status)

    assert dialog._qr_widget.payload_text() == module._serialize_pairing_payload_for_qr(status.pairing_payload)
    assert dialog._qr_widget._matrix == ((True, False), (False, True))
    assert dialog._warning_label.text() == "LAN warning"
    assert '"pairing_code": "123456"' in dialog._payload_box.toPlainText()

    dialog.set_status(None)

    assert dialog._qr_widget.payload_text() == ""
    assert dialog._warning_label.text() == ""
