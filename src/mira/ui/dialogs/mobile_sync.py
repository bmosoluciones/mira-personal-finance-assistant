# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Desktop dialog for local mobile sync sessions."""

from __future__ import annotations

import json

from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mira.services.mobile_sync import MobileSyncServerStatus
from mira.ui.i18n import tr


def _serialize_pairing_payload_for_qr(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


class PairingQrWidget(QFrame):
    """Represent the PairingQrWidget class."""

    def __init__(self, *, language: str, parent: QWidget | None = None) -> None:
        """Initialize."""
        super().__init__(parent)
        self._language = language
        self._payload_text = ""
        self._matrix: tuple[tuple[bool, ...], ...] = tuple()
        self._message = tr(
            "mobile.sync.dialog.qr_placeholder",
            language,
            default="Start mobile sync to generate a QR pairing code.",
        )
        self.setMinimumHeight(220)
        self.setStyleSheet("background:#FFFFFF; border:1px solid #D6DEE8; border-radius:12px;")

    def payload_text(self) -> str:
        """Return payload text."""
        return self._payload_text

    def set_payload(self, payload_text: str) -> None:
        """Return set payload."""
        self._payload_text = payload_text.strip()
        self._matrix = tuple()
        if not self._payload_text:
            self._message = tr(
                "mobile.sync.dialog.qr_placeholder",
                self._language,
                default="Start mobile sync to generate a QR pairing code.",
            )
        else:
            try:
                import segno  # noqa: PLC0415  # type: ignore[import-not-found]
            except ImportError:
                self._message = tr(
                    "mobile.sync.dialog.qr_unavailable",
                    self._language,
                    default="QR rendering dependency is unavailable. Use the code or JSON payload instead.",
                )
            else:
                qr_code = segno.make(self._payload_text, error="m")
                self._matrix = tuple(tuple(bool(module) for module in row) for row in qr_code.matrix)
                self._message = ""
        if updater := getattr(self, "update", None):
            updater()

    def paintEvent(self, _event) -> None:  # noqa: N802
        """Return paintEvent."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(self.rect(), QColor("#FFFFFF"))
        if not self._matrix:
            alignment = 0
            painter.setPen(QColor("#5A6B7B"))
            painter.drawText(self.rect(), alignment, self._message)
            return

        try:
            from PySide6.QtCore import QRect  # noqa: PLC0415
        except ImportError:
            return

        quiet_zone = 4
        module_count = len(self._matrix) + quiet_zone * 2
        available_side = max(32, min(self.width(), self.height()) - 24)
        module_size = max(3, available_side // module_count)
        qr_side = module_size * module_count
        left = max(0, (self.width() - qr_side) // 2)
        top = max(0, (self.height() - qr_side) // 2)

        painter.fillRect(QRect(left, top, qr_side, qr_side), QColor("#FFFFFF"))
        for row_index, row in enumerate(self._matrix):
            for column_index, is_dark in enumerate(row):
                if not is_dark:
                    continue
                x_pos = left + (column_index + quiet_zone) * module_size
                y_pos = top + (row_index + quiet_zone) * module_size
                painter.fillRect(QRect(x_pos, y_pos, module_size, module_size), QColor("#000000"))


class MobileSyncSessionDialog(QDialog):
    """Represent the MobileSyncSessionDialog class."""

    def __init__(self, *, language: str, parent: QWidget | None = None) -> None:
        """Initialize."""
        super().__init__(parent)
        self._language = language
        self.setModal(False)
        self.setWindowTitle(tr("mobile.sync.dialog.title", language, default="Mobile Sync Session"))
        self.resize(560, 520)

        layout = QVBoxLayout(self)
        self._summary_label = QLabel(
            tr(
                "mobile.sync.dialog.summary",
                language,
                default=(
                    "Use this session to pair the Android helper over the local network. "
                    "The desktop keeps being the source of truth."
                ),
            )
        )
        self._summary_label.setWordWrap(True)
        layout.addWidget(self._summary_label)

        details_group = QGroupBox(tr("mobile.sync.dialog.details", language, default="Session Details"))
        details_layout = QFormLayout(details_group)
        self._pairing_code_value = QLabel("-")
        self._pairing_code_value.setTextInteractionFlags(self._pairing_code_value.textInteractionFlags())
        self._expires_at_value = QLabel("-")
        self._addresses_value = QLabel("-")
        self._port_value = QLabel("-")
        self._zeroconf_value = QLabel("-")
        self._api_base_url_value = QLabel("-")
        self._api_base_url_value.setWordWrap(True)
        details_layout.addRow(
            tr("mobile.sync.dialog.code", language, default="Pairing code:"), self._pairing_code_value
        )
        details_layout.addRow(tr("mobile.sync.dialog.expires", language, default="Expires at:"), self._expires_at_value)
        details_layout.addRow(
            tr("mobile.sync.dialog.addresses", language, default="LAN addresses:"), self._addresses_value
        )
        details_layout.addRow(tr("mobile.sync.dialog.port", language, default="Port:"), self._port_value)
        details_layout.addRow(tr("mobile.sync.dialog.zeroconf", language, default="Zeroconf:"), self._zeroconf_value)
        details_layout.addRow(
            tr("mobile.sync.dialog.api_base", language, default="API base URL:"), self._api_base_url_value
        )
        layout.addWidget(details_group)

        qr_group = QGroupBox(tr("mobile.sync.dialog.qr", language, default="Pairing QR"))
        qr_layout = QVBoxLayout(qr_group)
        qr_hint = QLabel(
            tr(
                "mobile.sync.dialog.qr_hint",
                language,
                default="Scan this QR from the mobile helper or keep using the manual fallback below.",
            )
        )
        qr_hint.setWordWrap(True)
        qr_layout.addWidget(qr_hint)
        self._qr_widget = PairingQrWidget(language=language)
        qr_layout.addWidget(self._qr_widget)
        self._warning_label = QLabel("")
        self._warning_label.setWordWrap(True)
        qr_layout.addWidget(self._warning_label)
        layout.addWidget(qr_group)

        payload_group = QGroupBox(tr("mobile.sync.dialog.payload", language, default="Pairing Payload"))
        payload_layout = QVBoxLayout(payload_group)
        payload_hint = QLabel(
            tr(
                "mobile.sync.dialog.payload_hint",
                language,
                default=(
                    "This serialized payload is the data the mobile helper uses for pairing. "
                    "Keep it local to your LAN session."
                ),
            )
        )
        payload_hint.setWordWrap(True)
        payload_layout.addWidget(payload_hint)
        self._payload_box = QPlainTextEdit()
        self._payload_box.setReadOnly(True)
        payload_layout.addWidget(self._payload_box)
        layout.addWidget(payload_group, stretch=1)

        actions_row = QHBoxLayout()
        self.refresh_button = QPushButton(tr("mobile.sync.dialog.refresh", language, default="New pairing code"))
        self.stop_button = QPushButton(tr("mobile.sync.dialog.stop", language, default="Stop service"))
        actions_row.addWidget(self.refresh_button)
        actions_row.addWidget(self.stop_button)
        actions_row.addStretch(1)
        layout.addLayout(actions_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.close)
        layout.addWidget(buttons)

        self.set_status(None)

    def set_status(self, status: MobileSyncServerStatus | None) -> None:
        """Return set status."""
        if status is None:
            inactive_text = tr(
                "mobile.sync.dialog.inactive",
                self._language,
                default="The local mobile sync service is not active.",
            )
            self._summary_label.setText(inactive_text)
            self._pairing_code_value.setText("-")
            self._expires_at_value.setText("-")
            self._addresses_value.setText("-")
            self._port_value.setText("-")
            self._zeroconf_value.setText("-")
            self._api_base_url_value.setText("-")
            self._qr_widget.set_payload("")
            self._warning_label.setText("")
            self._payload_box.setPlainText("{}")
            return

        addresses = ", ".join(status.advertised_addresses) if status.advertised_addresses else status.host
        zeroconf_state = tr(
            "mobile.sync.zeroconf.enabled" if status.advertisement_enabled else "mobile.sync.zeroconf.disabled",
            self._language,
            default="enabled" if status.advertisement_enabled else "disabled",
        )
        self._summary_label.setText(
            tr(
                "mobile.sync.dialog.summary_active",
                self._language,
                default=(
                    "Android helper pairing is ready on the local network. "
                    "Use the temporary code or the serialized pairing payload."
                ),
            )
        )
        self._pairing_code_value.setText(status.pairing_code)
        self._expires_at_value.setText(status.pairing_expires_at)
        self._addresses_value.setText(addresses)
        self._port_value.setText(str(status.port))
        self._zeroconf_value.setText(zeroconf_state)
        self._api_base_url_value.setText(str(status.pairing_payload.get("api_base_url") or "-"))
        qr_payload = _serialize_pairing_payload_for_qr(status.pairing_payload)
        self._qr_widget.set_payload(qr_payload)
        self._warning_label.setText(status.lan_warning or "")
        self._payload_box.setPlainText(json.dumps(status.pairing_payload, indent=2, ensure_ascii=True))
