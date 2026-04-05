# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""
Tag management dialog for MIRA Personal Finance.
Provides full CRUD for tags, including color selection and badge preview.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from mira.db.database import Database
from mira.ui.i18n import normalize_language, tr
from mira.ui.notifications import show_user_message


def _notify_warning(widget, title: str, message: str) -> None:
    show_user_message(widget, title, message, level="warning")


class TagManagerDialog(QDialog):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self._language = normalize_language(self.db.setting.get("language"))
        self.setWindowTitle(tr("tag_manager.title", self._language, default="Tag Management"))
        self.setMinimumWidth(420)
        self._layout = QVBoxLayout(self)
        self._list_widget = QListWidget()
        self._layout.addWidget(QLabel(tr("tags.title", self._language, default="Tags")))
        self._layout.addWidget(self._list_widget)
        self._refresh_list()
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton(tr("menu.tags.add", self._language, default="Create Tag"))
        self.edit_btn = QPushButton(tr("btn.edit", self._language, default="✏ Edit"))
        self.del_btn = QPushButton(tr("btn.delete", self._language, default="🗑 Delete"))
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.edit_btn)
        btn_layout.addWidget(self.del_btn)
        self._layout.addLayout(btn_layout)
        self.add_btn.clicked.connect(self._add_tag)
        self.edit_btn.clicked.connect(self._edit_tag)
        self.del_btn.clicked.connect(self._delete_tag)

    def _refresh_list(self):
        self._list_widget.clear()
        for tag in self.db.tag.list():
            item = QListWidgetItem(tag["name"])
            color = tag.get("color", "#888888")
            item.setBackground(QColor(color))
            item.setData(Qt.UserRole, tag)
            self._list_widget.addItem(item)

    def _add_tag(self):
        name, ok = QInputDialog.getText(
            self,
            tr("tag_manager.add.title", self._language, default="Add Tag"),
            tr("tag_manager.name", self._language, default="Name:"),
        )
        if not ok or not name.strip():
            return
        color = QColorDialog.getColor(
            QColor("#888888"), self, tr("tag_manager.color.select", self._language, default="Select Color")
        )
        if not color.isValid():
            return
        self.db.tag.create(name.strip(), color.name())
        self._refresh_list()

    def _edit_tag(self):
        item = self._list_widget.currentItem()
        if not item:
            _notify_warning(
                self,
                tr("tag_manager.edit.title", self._language, default="Edit Tag"),
                tr("tag_manager.select.edit", self._language, default="Select a tag to edit."),
            )
            return
        tag = item.data(Qt.UserRole)
        name, ok = QInputDialog.getText(
            self,
            tr("tag_manager.edit.title", self._language, default="Edit Tag"),
            tr("tag_manager.name", self._language, default="Name:"),
            text=tag["name"],
        )
        if not ok or not name.strip():
            return
        color = QColorDialog.getColor(
            QColor(tag["color"]), self, tr("tag_manager.color.select", self._language, default="Select Color")
        )
        if not color.isValid():
            return
        self.db.tag.update(tag["id"], name.strip(), color.name())
        self._refresh_list()

    def _delete_tag(self):
        item = self._list_widget.currentItem()
        if not item:
            _notify_warning(
                self,
                tr("tags.delete.title", self._language, default="Delete Tag"),
                tr("tag_manager.select.delete", self._language, default="Select a tag to delete."),
            )
            return
        tag = item.data(Qt.UserRole)
        confirm = QMessageBox.question(
            self,
            tr("tags.delete.title", self._language, default="Delete Tag"),
            tr("tags.delete.body", self._language, default="Delete tag '{name}'?", params={"name": tag["name"]}),
        )
        if confirm == QMessageBox.Yes:
            self.db.tag.delete(tag["id"])
            self._refresh_list()
