# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Small PySide6 doubles for headless unit tests."""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import importlib.util
import sys
from types import ModuleType, SimpleNamespace


class BoundSignal:
    """Minimal signal implementation with ``connect`` and ``emit``."""

    def __init__(self) -> None:
        self.callbacks: list[object] = []

    def connect(self, callback, connection_type=None) -> None:
        self.callbacks.append(callback)

    def disconnect(self, callback=None) -> None:
        if callback is None:
            self.callbacks.clear()
        else:
            self.callbacks = [c for c in self.callbacks if c is not callback]

    def emit(self, *args) -> None:
        for callback in list(self.callbacks):
            callback(*args)


class Signal:
    """Descriptor that provides a per-instance :class:`BoundSignal`."""

    def __init__(self, *_args) -> None:
        self._storage_name = ""

    def __set_name__(self, _owner, name: str) -> None:
        self._storage_name = f"__signal_{name}"

    def __get__(self, instance, _owner):
        if instance is None:
            return self
        signal = instance.__dict__.get(self._storage_name)
        if signal is None:
            signal = BoundSignal()
            instance.__dict__[self._storage_name] = signal
        return signal


class QThread:
    def __init__(self) -> None:
        self.started = False

    def start(self) -> None:
        self.started = True

    def isRunning(self) -> bool:
        return False

    def wait(self) -> None:
        pass

    def quit(self) -> None:
        pass


class QWidget:
    def __init__(self, parent=None) -> None:
        self._parent = parent
        self._window = None
        self.closed = False

    def parentWidget(self):
        return self._parent

    def window(self):
        return self._window if self._window is not None else self

    def close(self) -> None:
        self.closed = True


class QListWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._row = 0
        self.block_calls: list[bool] = []

    def currentRow(self) -> int:
        return self._row

    def blockSignals(self, value: bool) -> None:
        self.block_calls.append(value)

    def setCurrentRow(self, row: int) -> None:
        self._row = row


class QStackedWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._widgets: list[object] = []
        self._current_index = 0

    def addWidget(self, widget) -> None:
        self._widgets.append(widget)

    def setCurrentIndex(self, index: int) -> None:
        self._current_index = index

    def currentWidget(self):
        return self._widgets[self._current_index]


class QFrame(QWidget):
    class Shape:
        StyledPanel = 1
        NoFrame = 0

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.frame_shape = None
        self.style_sheet = ""
        self.minimum_height = None

    def setFrameShape(self, shape) -> None:
        self.frame_shape = shape

    def setStyleSheet(self, style: str) -> None:
        self.style_sheet = style

    def setMinimumHeight(self, value: int) -> None:
        self.minimum_height = value


class QLabel(QWidget):
    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(parent)
        self._text = text
        self.word_wrap = False
        self.style_sheet = ""
        self.visible = True
        self.font = None

    def setText(self, text: str) -> None:
        self._text = text

    def text(self) -> str:
        return self._text

    def setWordWrap(self, value: bool) -> None:
        self.word_wrap = value

    def setStyleSheet(self, style: str) -> None:
        self.style_sheet = style

    def setVisible(self, value: bool) -> None:
        self.visible = value

    def setFont(self, font) -> None:
        self.font = font


class QPushButton(QWidget):
    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(parent)
        self._text = text
        self.clicked = BoundSignal()
        self.style_sheet = ""
        self.enabled = True

    def setStyleSheet(self, style: str) -> None:
        self.style_sheet = style

    def setEnabled(self, value: bool) -> None:
        self.enabled = value


class QScrollArea(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.widget_resizable = False
        self.frame_shape = None
        self.horizontal_policy = None
        self.vertical_policy = None
        self.style_sheet = ""
        self.widget = None

    def setWidgetResizable(self, value: bool) -> None:
        self.widget_resizable = value

    def setFrameShape(self, shape) -> None:
        self.frame_shape = shape

    def setHorizontalScrollBarPolicy(self, policy) -> None:
        self.horizontal_policy = policy

    def setVerticalScrollBarPolicy(self, policy) -> None:
        self.vertical_policy = policy

    def setStyleSheet(self, style: str) -> None:
        self.style_sheet = style

    def setWidget(self, widget) -> None:
        self.widget = widget


class QVBoxLayout:
    def __init__(self, parent=None) -> None:
        self.parent = parent
        self.items: list[tuple[str, object, object | None]] = []
        self.margins = None
        self.spacing = None

    def setContentsMargins(self, left: int, top: int, right: int, bottom: int) -> None:
        self.margins = (left, top, right, bottom)

    def setSpacing(self, value: int) -> None:
        self.spacing = value

    def addWidget(self, widget, stretch: int | None = None) -> None:
        self.items.append(("widget", widget, stretch))

    def addLayout(self, layout) -> None:
        self.items.append(("layout", layout, None))


class QHBoxLayout(QVBoxLayout):
    def addStretch(self, stretch: int = 0) -> None:
        self.items.append(("stretch", stretch, None))

    def addSpacing(self, value: int) -> None:
        self.items.append(("spacing", value, None))


class QFormLayout:
    def __init__(self) -> None:
        self.rows: list[tuple[object, object]] = []
        self.label_alignment = None

    def setLabelAlignment(self, alignment) -> None:
        self.label_alignment = alignment

    def addRow(self, label, widget) -> None:
        self.rows.append((label, widget))


class QAbstractItemView:
    class EditTrigger:
        NoEditTriggers = 0


class QHeaderView:
    class ResizeMode:
        Stretch = 1

    def __init__(self) -> None:
        self.mode = None

    def setSectionResizeMode(self, mode) -> None:
        self.mode = mode


class QTableWidgetItem:
    def __init__(self, text: str = "") -> None:
        self._text = text
        self._data: dict[int, object] = {}
        self.foreground = None

    def text(self) -> str:
        return self._text

    def setForeground(self, value) -> None:
        self.foreground = value

    def setData(self, role: int, value) -> None:
        self._data[role] = value

    def data(self, role: int):
        return self._data.get(role)


class QTableWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.edit_triggers = None
        self.column_count = 0
        self.headers: list[str] = []
        self._header = QHeaderView()
        self.row_count = 0
        self.items: dict[tuple[int, int], QTableWidgetItem] = {}
        self.current_cell = None
        self.selected_row = None
        self.item_at = None

    def setEditTriggers(self, triggers) -> None:
        self.edit_triggers = triggers

    def setColumnCount(self, count: int) -> None:
        self.column_count = count

    def setHorizontalHeaderLabels(self, labels: list[str]) -> None:
        self.headers = labels

    def horizontalHeader(self) -> QHeaderView:
        return self._header

    def setRowCount(self, count: int) -> None:
        self.row_count = count

    def setItem(self, row: int, column: int, item: QTableWidgetItem) -> None:
        self.items[(row, column)] = item

    def itemAt(self, _pos):
        return self.item_at

    def setCurrentCell(self, row: int, column: int) -> None:
        self.current_cell = (row, column)

    def selectRow(self, row: int) -> None:
        self.selected_row = row


class QDialog(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.window_title = ""
        self.size = None
        self.accepted = False

    def setWindowTitle(self, title: str) -> None:
        self.window_title = title

    def resize(self, width: int, height: int) -> None:
        self.size = (width, height)

    def accept(self) -> None:
        self.accepted = True


class QDialogButtonBox(QWidget):
    class StandardButton:
        Close = 0

    def __init__(self, _buttons=None, parent=None) -> None:
        super().__init__(parent)
        self.accepted = BoundSignal()
        self.rejected = BoundSignal()
        self._button = QPushButton()

    def button(self, _button) -> QPushButton:
        return self._button


class QDoubleSpinBox(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._value = 0.0
        self.enabled = True
        self.valueChanged = BoundSignal()

    def setRange(self, _minimum: float, _maximum: float) -> None:
        return None

    def setDecimals(self, _value: int) -> None:
        return None

    def setSuffix(self, _text: str) -> None:
        return None

    def setValue(self, value: float) -> None:
        self._value = value

    def value(self) -> float:
        return self._value

    def setEnabled(self, value: bool) -> None:
        self.enabled = value


class QComboBox(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.items: list[str] = []
        self._item_data: list[object] = []
        self.currentIndexChanged = BoundSignal()
        self._current_index = -1
        self._current_text = ""

    def addItem(self, text: str, userData=None) -> None:
        self.items.append(text)
        self._item_data.append(userData)
        if self._current_index < 0:
            self._current_index = 0
            self._current_text = text

    def addItems(self, items: list[str]) -> None:
        for item in items:
            self.addItem(item)

    def currentText(self) -> str:
        return self._current_text

    def currentData(self):
        if 0 <= self._current_index < len(self._item_data):
            return self._item_data[self._current_index]
        return None

    def currentIndex(self) -> int:
        return self._current_index

    def setCurrentIndex(self, index: int) -> None:
        self._current_index = index
        if 0 <= index < len(self.items):
            self._current_text = self.items[index]
        elif index < 0:
            self._current_text = ""

    def setCurrentText(self, value: str) -> None:
        self._current_text = value
        if value in self.items:
            self._current_index = self.items.index(value)

    def count(self) -> int:
        return len(self.items)

    def itemData(self, index: int):
        if 0 <= index < len(self._item_data):
            return self._item_data[index]
        return None

    def findText(self, value: str) -> int:
        try:
            return self.items.index(value)
        except ValueError:
            return -1


class _StubIndex:
    """Minimal QModelIndex stub for QStandardItemModel."""

    def __init__(self, row: int, col: int, model: "QStandardItemModel") -> None:
        self._row = row
        self._col = col
        self._model = model

    def isValid(self) -> bool:
        return 0 <= self._row < self._model.rowCount()

    def row(self) -> int:
        return self._row

    def data(self, role=None):
        item = self._model._rows[self._row] if 0 <= self._row < len(self._model._rows) else None
        if item is None:
            return None
        if role is None or role == 0:  # DisplayRole
            return item.text()
        return item._user_data.get(role)


class QStandardItem:
    def __init__(self, text: str = "") -> None:
        self._text = text
        self._user_data: dict = {}

    def text(self) -> str:
        return self._text

    def setData(self, value, role) -> None:
        self._user_data[role] = value

    def data(self, role):
        return self._user_data.get(role)


class QStandardItemModel:
    def __init__(self, rows: int = 0, cols: int = 1, parent=None) -> None:
        self._rows: list[QStandardItem] = []
        self.rowsInserted = BoundSignal()
        self.rowsRemoved = BoundSignal()
        self.modelReset = BoundSignal()

    def appendRow(self, item: "QStandardItem") -> None:
        self._rows.append(item)

    def rowCount(self, parent=None) -> int:
        return len(self._rows)

    def index(self, row: int, col: int, parent=None) -> "_StubIndex":
        return _StubIndex(row, col, self)

    def item(self, row: int, col: int = 0) -> "QStandardItem | None":
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def data(self, index: "_StubIndex", role=None):
        return index.data(role)

    def clear(self) -> None:
        self._rows.clear()


class QSortFilterProxyModel:
    """Minimal stub: no actual filtering – returns all rows from source."""

    def __init__(self, parent=None) -> None:
        self._source: "QStandardItemModel | None" = None
        self._filter = ""

    def setSourceModel(self, model: "QStandardItemModel") -> None:
        self._source = model

    def setFilterCaseSensitivity(self, cs) -> None:
        pass

    def setFilterKeyColumn(self, col: int) -> None:
        pass

    def setFilterRegularExpression(self, expr) -> None:
        if hasattr(expr, "pattern"):
            self._filter = expr.pattern()
        else:
            self._filter = str(expr)

    def rowCount(self, parent=None) -> int:
        return self._source.rowCount() if self._source else 0

    def index(self, row: int, col: int, parent=None) -> "_StubIndex":
        return _StubIndex(row, col, self._source) if self._source else _StubIndex(-1, col, QStandardItemModel())

    def mapToSource(self, proxy_idx: "_StubIndex") -> "_StubIndex":
        return proxy_idx

    def mapFromSource(self, source_idx: "_StubIndex") -> "_StubIndex":
        return source_idx


class QRegularExpression:
    class PatternOption:
        CaseInsensitiveOption = 2

    def __init__(self, pattern: str = "", options=None) -> None:
        self._pattern = pattern

    def pattern(self) -> str:
        return self._pattern


class QCheckBox(QWidget):
    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(parent)
        self._text = text
        self._checked = False
        self.toggled = BoundSignal()

    def setChecked(self, value: bool) -> None:
        self._checked = value

    def isChecked(self) -> bool:
        return self._checked


class QDateEdit(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._date = QDate(2000, 1, 1)
        self.dateChanged = BoundSignal()
        self.style_sheet = ""
        self.display_format = ""
        self.calendar_popup = False

    def setCalendarPopup(self, value: bool) -> None:
        self.calendar_popup = value

    def setDisplayFormat(self, value: str) -> None:
        self.display_format = value

    def setStyleSheet(self, style: str) -> None:
        self.style_sheet = style

    def setDate(self, value: "QDate") -> None:
        self._date = value
        self.dateChanged.emit(value)

    def date(self) -> "QDate":
        return self._date


class QApplication:
    _instance = None
    process_events_calls = 0

    def __init__(self, _args=None) -> None:
        QApplication._instance = self

    @staticmethod
    def instance():
        return QApplication._instance

    @staticmethod
    def processEvents() -> None:
        QApplication.process_events_calls += 1


class QProgressDialog(QDialog):
    def __init__(self, label: str, cancel: str, minimum: int, maximum: int, parent=None) -> None:
        super().__init__(parent)
        self.label = label
        self.cancel_text = cancel
        self.minimum = minimum
        self.maximum = maximum
        self.window_modality = None
        self.minimum_duration = None
        self.value = 0
        self.cancel_button = object()
        self.canceled = BoundSignal()
        self.shown = False

    def setWindowModality(self, modality) -> None:
        self.window_modality = modality

    def setMinimumDuration(self, duration: int) -> None:
        self.minimum_duration = duration

    def setValue(self, value: int) -> None:
        self.value = value

    def show(self) -> None:
        self.shown = True

    def setCancelButton(self, button) -> None:
        self.cancel_button = button

    def setLabelText(self, text: str) -> None:
        self.label = text


class QMessageBox:
    StandardButton = SimpleNamespace(Yes=1, No=2)
    question_result = StandardButton.Yes
    calls: list[tuple[str, object | None, str, str]] = []

    @classmethod
    def critical(cls, parent, title: str, text: str) -> None:
        cls.calls.append(("error", parent, title, text))

    @classmethod
    def warning(cls, parent, title: str, text: str) -> None:
        cls.calls.append(("warning", parent, title, text))

    @classmethod
    def information(cls, parent, title: str, text: str) -> None:
        cls.calls.append(("info", parent, title, text))

    @classmethod
    def question(cls, parent, title: str, text: str, _buttons):
        cls.calls.append(("question", parent, title, text))
        return cls.question_result


@dataclass
class Rect:
    left: int = 0
    top: int = 0
    right: int = 100
    bottom: int = 30

    def adjusted(self, dx1: int, dy1: int, dx2: int, dy2: int) -> "Rect":
        return Rect(self.left + dx1, self.top + dy1, self.right + dx2, self.bottom + dy2)

    def width(self) -> int:
        return self.right - self.left


class QColor:
    def __init__(self, value: str) -> None:
        self.value = value

    def lighter(self, factor: int):
        return QColor(f"{self.value}|lighter{factor}")


class QPalette:
    class ColorRole:
        WindowText = 0

    def color(self, _role):
        return QColor("#DDD")


class QBrush:
    def __init__(self, color) -> None:
        self.color = color


class QFont:
    class Weight:
        DemiBold = 600
        Bold = 700

    def __init__(self, family="Arial", size=10, weight=None) -> None:
        if isinstance(family, QFont):
            self.family = family.family
            self.size = family.size
            self.weight = family.weight
            return
        self.family = family
        self.size = size
        self.weight = weight

    def setWeight(self, value) -> None:
        self.weight = value


class QValidator:
    class State:
        Invalid = 0
        Intermediate = 1
        Acceptable = 2


class QPainter:
    class RenderHint:
        Antialiasing = 1

    def __init__(self) -> None:
        self.operations: list[tuple[str, object]] = []

    def save(self) -> None:
        self.operations.append(("save",))

    def restore(self) -> None:
        self.operations.append(("restore",))

    def fillRect(self, rect, color) -> None:
        self.operations.append(("fillRect", rect, color))

    def setPen(self, value) -> None:
        self.operations.append(("setPen", value))

    def drawRect(self, rect) -> None:
        self.operations.append(("drawRect", rect))

    def setFont(self, value) -> None:
        self.operations.append(("setFont", value))

    def drawText(self, rect, alignment, text: str) -> None:
        self.operations.append(("drawText", rect, alignment, text))

    def setRenderHint(self, hint, value) -> None:
        self.operations.append(("setRenderHint", hint, value))

    def setBrush(self, value) -> None:
        self.operations.append(("setBrush", value))

    def drawRoundedRect(self, rect, x_radius: int, y_radius: int) -> None:
        self.operations.append(("drawRoundedRect", rect, x_radius, y_radius))


class _ItemDataRole:
    TextAlignmentRole = 1
    DisplayRole = 2
    UserRole = 1000


class _AlignmentFlag:
    AlignLeft = 1
    AlignRight = 2
    AlignVCenter = 4
    AlignBottom = 8


class _ScrollBarPolicy:
    ScrollBarAlwaysOff = 0
    ScrollBarAsNeeded = 1


class _WindowModality:
    WindowModal = 1


class _ConnectionType:
    QueuedConnection = 3
    DirectConnection = 1
    AutoConnection = 0
    BlockingQueuedConnection = 5
    UniqueConnection = 128


class Qt:
    ItemDataRole = _ItemDataRole
    AlignmentFlag = _AlignmentFlag
    ScrollBarPolicy = _ScrollBarPolicy
    WindowModality = _WindowModality
    ConnectionType = _ConnectionType


class QDate:
    def __init__(self, year: int, month: int, day: int) -> None:
        self.year = year
        self.month = month
        self.day = day

    def toString(self, _fmt: str) -> str:
        return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"


class QPoint:
    def __init__(self, x: int = 0, y: int = 0) -> None:
        self.x = x
        self.y = y


class QStyle:
    class StateFlag:
        State_Selected = 1


class QStyledItemDelegate:
    def __init__(self) -> None:
        self.super_paint_calls = 0

    def paint(self, _painter, _option, _index) -> None:
        self.super_paint_calls += 1


class _Legend:
    def __init__(self) -> None:
        self.visible = False

    def setVisible(self, value: bool) -> None:
        self.visible = value


class QChart:
    def __init__(self) -> None:
        self._legend = _Legend()
        self.title = ""
        self.series: list[object] = []
        self.axes: list[tuple[object, object]] = []

    def legend(self) -> _Legend:
        return self._legend

    def setTitle(self, title: str) -> None:
        self.title = title

    def addSeries(self, series) -> None:
        self.series.append(series)

    def addAxis(self, axis, alignment) -> None:
        self.axes.append((axis, alignment))


class QBarCategoryAxis:
    def __init__(self) -> None:
        self.categories: list[str] = []

    def append(self, categories) -> None:
        self.categories.extend(list(categories))


class QBarSet:
    def __init__(self, name: str) -> None:
        self.name = name
        self.values: list[float] = []
        self.color = None

    def setColor(self, color) -> None:
        self.color = color

    def append(self, value: float) -> None:
        self.values.append(value)


class QBarSeries:
    def __init__(self) -> None:
        self.sets: list[QBarSet] = []
        self.axes: list[object] = []

    def append(self, bar_set: QBarSet) -> None:
        self.sets.append(bar_set)

    def attachAxis(self, axis) -> None:
        self.axes.append(axis)


class QChartView(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.render_hints: list[object] = []
        self.minimum_height = None
        self.chart = None

    def setRenderHint(self, hint) -> None:
        self.render_hints.append(hint)

    def setMinimumHeight(self, value: int) -> None:
        self.minimum_height = value

    def setChart(self, chart) -> None:
        self.chart = chart


class QLineSeries:
    def __init__(self) -> None:
        self.name = ""
        self.points: list[tuple[float, float]] = []
        self.axes: list[object] = []

    def setName(self, name: str) -> None:
        self.name = name

    def append(self, x: float, y: float) -> None:
        self.points.append((x, y))

    def attachAxis(self, axis) -> None:
        self.axes.append(axis)


class QPieSlice:
    def __init__(self, label: str, value: float) -> None:
        self._label = label
        self.value = value
        self.brush = None
        self.label_visible = False
        self.clicked = BoundSignal()

    def setBrush(self, brush) -> None:
        self.brush = brush

    def setLabelVisible(self, value: bool) -> None:
        self.label_visible = value

    def label(self) -> str:
        return self._label


class QPieSeries:
    def __init__(self) -> None:
        self.slices: list[QPieSlice] = []
        self.hole_size = 0.0

    def append(self, label: str, value: float) -> QPieSlice:
        slice_item = QPieSlice(label, value)
        self.slices.append(slice_item)
        return slice_item

    def setHoleSize(self, value: float) -> None:
        self.hole_size = value


class QValueAxis:
    def __init__(self) -> None:
        self.label_format = ""
        self.title = ""
        self.range = None

    def setLabelFormat(self, value: str) -> None:
        self.label_format = value

    def setTitleText(self, title: str) -> None:
        self.title = title

    def setRange(self, minimum: float, maximum: float) -> None:
        self.range = (minimum, maximum)


class QAction:
    def __init__(self, text: str, parent=None) -> None:
        self._text = text
        self.parent = parent
        self.triggered = BoundSignal()
        self.shortcut = None
        self.checkable = False
        self.checked = False

    def text(self) -> str:
        return self._text

    def setShortcut(self, shortcut: str) -> None:
        self.shortcut = shortcut

    def setCheckable(self, value: bool) -> None:
        self.checkable = value

    def setChecked(self, value: bool) -> None:
        self.checked = value

    def isCheckable(self) -> bool:
        return self.checkable

    def isChecked(self) -> bool:
        return self.checked

    def trigger(self) -> None:
        self.triggered.emit()


def install_fake_pyside(monkeypatch):
    """Install fake PySide6 modules into ``sys.modules`` for one test."""

    pyside = ModuleType("PySide6")
    qtcore = ModuleType("PySide6.QtCore")
    qtgui = ModuleType("PySide6.QtGui")
    qtwidgets = ModuleType("PySide6.QtWidgets")
    qtcharts = ModuleType("PySide6.QtCharts")

    qtcore.QThread = QThread
    qtcore.Signal = Signal
    qtcore.QDate = QDate
    qtcore.QPoint = QPoint
    qtcore.Qt = Qt
    qtcore.QRegularExpression = QRegularExpression
    qtcore.QSortFilterProxyModel = QSortFilterProxyModel

    qtgui.QAction = QAction
    qtgui.QBrush = QBrush
    qtgui.QColor = QColor
    qtgui.QFont = QFont
    qtgui.QPalette = QPalette
    qtgui.QPainter = QPainter
    qtgui.QValidator = QValidator
    qtgui.QStandardItem = QStandardItem
    qtgui.QStandardItemModel = QStandardItemModel

    qtwidgets.QAbstractItemView = QAbstractItemView
    qtwidgets.QApplication = QApplication
    qtwidgets.QCheckBox = QCheckBox
    qtwidgets.QComboBox = QComboBox
    qtwidgets.QDateEdit = QDateEdit
    qtwidgets.QDialog = QDialog
    qtwidgets.QDialogButtonBox = QDialogButtonBox
    qtwidgets.QDoubleSpinBox = QDoubleSpinBox
    qtwidgets.QFormLayout = QFormLayout
    qtwidgets.QFrame = QFrame
    qtwidgets.QHBoxLayout = QHBoxLayout
    qtwidgets.QHeaderView = QHeaderView
    qtwidgets.QLabel = QLabel
    qtwidgets.QListWidget = QListWidget
    qtwidgets.QMessageBox = QMessageBox
    qtwidgets.QProgressDialog = QProgressDialog
    qtwidgets.QPushButton = QPushButton
    qtwidgets.QScrollArea = QScrollArea
    qtwidgets.QStackedWidget = QStackedWidget
    qtwidgets.QStyle = QStyle
    qtwidgets.QStyledItemDelegate = QStyledItemDelegate
    qtwidgets.QTableWidget = QTableWidget
    qtwidgets.QTableWidgetItem = QTableWidgetItem
    qtwidgets.QVBoxLayout = QVBoxLayout
    qtwidgets.QWidget = QWidget

    qtcharts.QChart = QChart
    qtcharts.QBarCategoryAxis = QBarCategoryAxis
    qtcharts.QBarSeries = QBarSeries
    qtcharts.QBarSet = QBarSet
    qtcharts.QChartView = QChartView
    qtcharts.QLineSeries = QLineSeries
    qtcharts.QPieSeries = QPieSeries
    qtcharts.QValueAxis = QValueAxis

    pyside.QtCore = qtcore
    pyside.QtGui = qtgui
    pyside.QtWidgets = qtwidgets
    pyside.QtCharts = qtcharts

    monkeypatch.setitem(sys.modules, "PySide6", pyside)
    monkeypatch.setitem(sys.modules, "PySide6.QtCore", qtcore)
    monkeypatch.setitem(sys.modules, "PySide6.QtGui", qtgui)
    monkeypatch.setitem(sys.modules, "PySide6.QtWidgets", qtwidgets)
    monkeypatch.setitem(sys.modules, "PySide6.QtCharts", qtcharts)

    QMessageBox.calls.clear()
    QMessageBox.question_result = QMessageBox.StandardButton.Yes
    QApplication.process_events_calls = 0
    QApplication._instance = None
    return SimpleNamespace(QtCore=qtcore, QtGui=qtgui, QtWidgets=qtwidgets, QtCharts=qtcharts, Rect=Rect)


def fresh_import(monkeypatch, module_name: str, *, clear_prefixes: tuple[str, ...] = ()):
    """Import *module_name* after clearing it and related modules from cache."""

    prefixes = tuple(clear_prefixes) + (module_name,)
    for name in list(sys.modules):
        if any(name == prefix or name.startswith(f"{prefix}.") for prefix in prefixes):
            monkeypatch.delitem(sys.modules, name, raising=False)
    return importlib.import_module(module_name)


def load_module_from_path(monkeypatch, module_name: str, path: str):
    """Load a module directly from *path* without importing its package."""

    monkeypatch.delitem(sys.modules, module_name, raising=False)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
