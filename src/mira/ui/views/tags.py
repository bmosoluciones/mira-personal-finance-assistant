# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Tags feature view."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mira.app.view_services import TagsViewService, TagsViewState
from mira.db.database import Database
from mira.db.errors import DuplicateTagNameError
from mira.ui.i18n import normalize_language, tr
from mira.ui.views._shared import (
    _TABLE_STYLE,
    _make_toolbar_btn,
    _notify_warning,
    _section_title,
    _select_row_at_pos,
    _sub_title,
    _tr_db,
)


class TagsView(QWidget):
    """Tags (etiquetas transversales) management view."""

    def __init__(
        self,
        db: Database,
        parent: QWidget | None = None,
        service: TagsViewService | None = None,
    ) -> None:
        """Initialize the TagsView instance."""
        super().__init__(parent)
        self._db = db
        self._service = service or TagsViewService(db)
        self._language = normalize_language(self._db.setting.get("language"))
        self._tags: list[dict] = []
        self._build_ui()
        self.refresh()

    def _t(self, key: str, default: str, *, params: dict[str, object] | None = None) -> str:
        """Return t."""
        return tr(key, self._language, default=default, params=params)

    def _build_ui(self) -> None:
        """Return build ui."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        self._title_label = _section_title(self._t("tags.title", "Tags"))
        layout.addWidget(self._title_label)

        frame = QFrame()
        frame.setStyleSheet("QFrame{border-radius:6px;border:none;}")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(12, 10, 12, 10)
        frame_layout.setSpacing(6)

        header = QHBoxLayout()
        self._subtitle_label = _sub_title(self._t("tags.subtitle", "Transaction Tags"))
        header.addWidget(self._subtitle_label)
        header.addStretch()
        self._btn_add = _make_toolbar_btn(self._t("btn.add", "+ Add"))
        self._btn_edit = _make_toolbar_btn(self._t("btn.edit", "✏ Edit"))
        self._btn_del = _make_toolbar_btn(self._t("btn.delete", "🗑 Delete"))
        for button in [self._btn_add, self._btn_edit, self._btn_del]:
            header.addWidget(button)
        frame_layout.addLayout(header)

        self._table = QTableWidget(0, 3)
        self._table.setStyleSheet(_TABLE_STYLE)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        frame_layout.addWidget(self._table, 1)

        layout.addWidget(frame, 1)

        self._btn_add.clicked.connect(self._on_add)
        self._btn_edit.clicked.connect(self._on_edit)
        self._btn_del.clicked.connect(self._on_delete)
        self._table.doubleClicked.connect(self._on_edit)
        self._table.customContextMenuRequested.connect(self._open_context_menu)

    def open_add_dialog(self) -> None:
        """Return open add dialog."""
        self._on_add()

    def _selected_tag(self) -> dict | None:
        """Return selected tag."""
        row = self._table.currentRow()
        if row < 0 or row >= len(self._tags):
            return None
        return self._tags[row]

    def _make_color_swatch(self, color_value: str) -> QWidget:
        """Return make color swatch."""
        container = QWidget(self._table)
        container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        swatch = QLabel()
        swatch.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        swatch.setFixedSize(18, 18)
        swatch_color = QColor(color_value)
        if not swatch_color.isValid():
            swatch_color = QColor("#888888")
        swatch.setToolTip(swatch_color.name().upper())
        swatch.setStyleSheet(f"background:{swatch_color.name()};border:1px solid #69707A;border-radius:4px;")
        layout.addWidget(swatch)
        return container

    def refresh(self) -> None:
        """Return refresh."""
        self._language = normalize_language(self._db.setting.get("language"))
        self._apply_state(self._service.load_state())

    def _apply_state(self, state: TagsViewState) -> None:
        """Return apply state."""
        self._tags = list(state.tags)
        self._title_label.setText(self._t("tags.title", "Tags"))
        self._subtitle_label.setText(self._t("tags.subtitle", "Transaction Tags"))
        self._btn_add.setText(self._t("btn.add", "+ Add"))
        self._btn_edit.setText(self._t("btn.edit", "✏ Edit"))
        self._btn_del.setText(self._t("btn.delete", "🗑 Delete"))
        self._table.setHorizontalHeaderLabels(
            [
                self._t("tags.col.name", "Tag"),
                self._t("tags.col.txns_month", "Txns (month)"),
                self._t("tags.col.color", "Color"),
            ]
        )

        self._table.setRowCount(len(self._tags))
        for row, tag in enumerate(self._tags):
            tag_id = int(tag["id"])
            label = f"{tag.get('icon', '')} {tag['name']}".strip()
            name_item = QTableWidgetItem(label)
            name_item.setData(Qt.ItemDataRole.UserRole, tag_id)
            self._table.setItem(row, 0, name_item)

            count_item = QTableWidgetItem(str(state.monthly_counts.get(tag_id, 0)))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 1, count_item)

            color_value = str(tag.get("color") or "#888888")
            color_item = QTableWidgetItem("")
            color_item.setFlags(color_item.flags() & ~Qt.ItemFlag.ItemIsEditable & ~Qt.ItemFlag.ItemIsSelectable)
            self._table.setItem(row, 2, color_item)
            self._table.setCellWidget(row, 2, self._make_color_swatch(color_value))

    def _on_add(self) -> None:
        """Return on add."""
        from mira.ui.dialogs import TagDialog

        dlg = TagDialog(self._db, parent=self)
        if dlg.exec() == TagDialog.DialogCode.Accepted:
            data = dlg.get_data()
            try:
                self._service.create(name=data["name"], color=data["color"], icon=data.get("icon") or "")
            except DuplicateTagNameError:
                _notify_warning(
                    self,
                    _tr_db(self._db, "validation.title", "Validation"),
                    _tr_db(self._db, "tags.validation.exists", "Tag already exists."),
                )
                return
            except ValueError as exc:
                _notify_warning(self, _tr_db(self._db, "validation.title", "Validation"), str(exc))
                return
            self.refresh()

    def _on_edit(self) -> None:
        """Return on edit."""
        from mira.ui.dialogs import TagDialog

        tag = self._selected_tag()
        if tag is None:
            return
        dlg = TagDialog(self._db, tag=tag, parent=self)
        if dlg.exec() == TagDialog.DialogCode.Accepted:
            data = dlg.get_data()
            try:
                self._service.update(
                    int(tag["id"]),
                    name=data["name"],
                    color=data["color"],
                    icon=data.get("icon") or "",
                )
            except DuplicateTagNameError:
                _notify_warning(
                    self,
                    _tr_db(self._db, "validation.title", "Validation"),
                    _tr_db(self._db, "tags.validation.exists", "Tag already exists."),
                )
                return
            except ValueError as exc:
                _notify_warning(self, _tr_db(self._db, "validation.title", "Validation"), str(exc))
                return
            self.refresh()

    def _on_delete(self) -> None:
        """Return on delete."""
        tag = self._selected_tag()
        if tag is None:
            return
        reply = QMessageBox.question(
            self,
            self._t("tags.delete.title", "Delete Tag"),
            self._t(
                "tags.delete.body",
                "Delete tag '{name}'?\n\nThis action cannot be undone.",
                params={"name": str(tag["name"])},
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._service.delete(int(tag["id"]))
            self.refresh()

    def _open_context_menu(self, pos: QPoint) -> None:
        """Return open context menu."""
        if not _select_row_at_pos(self._table, pos):
            return
        menu = QMenu(self)
        act_edit = menu.addAction(self._t("btn.edit", "✏ Edit"))
        act_delete = menu.addAction(self._t("btn.delete", "🗑 Delete"))
        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen is act_edit:
            self._on_edit()
        elif chosen is act_delete:
            self._on_delete()
