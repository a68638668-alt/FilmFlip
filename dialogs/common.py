from settings import get_data_file
import json
import re
from pathlib import Path

from PySide6.QtCore import QDate, QDateTime, QEvent, QTime, Qt, Signal, QTimer
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QMessageBox,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QRadioButton,
    QDialogButtonBox,
    QFormLayout,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QGridLayout,
    QGroupBox,
    QAbstractItemView,
    QInputDialog,
    QApplication,
    QSizePolicy,
    QPlainTextEdit,
    QDateEdit,
    QDateTimeEdit,
)


from shooting_presets import load_shooting_presets, save_shooting_presets
from utils.design import set_button_icon

PRESET_FILE = get_data_file("filmflip_presets.json")

PRESET_KEYS = {
    "camera": "카메라",
    "film": "필름",
    "lab": "현상소",
    "place": "장소",
    "scanner": "스캐너",
}

TEMPLATE_LABELS = {
    "date": "날짜",
    "camera": "카메라",
    "film": "필름",
    "lab": "현상소",
    "place": "장소",
    "scanner": "스캐너",
    "memo": "메모",
    "number": "번호",
}

FIELD_LABELS = {
    "date": "날짜",
    "camera": "카메라",
    "film": "필름",
    "lab": "현상소",
    "place": "장소",
    "scanner": "스캐너",
    "memo": "메모",
    "number": "번호",
}

DEFAULT_PRESETS = {
    "camera": [],
    "film": [],
    "lab": [],
    "place": [],
    "scanner": [],
}

DEFAULT_TEMPLATE = {
    "order": ["date", "camera", "film", "lab", "place", "scanner", "memo", "number"],
    "enabled": {
        "date": False,
        "camera": True,
        "film": True,
        "lab": True,
        "place": True,
        "scanner": False,
        "memo": False,
        "number": True,
    },
}


DEFAULT_FOLDER_TEMPLATE = {
    "order": ["date", "memo", "place", "camera", "film", "lab", "scanner"],
    "enabled": {
        "date": True,
        "camera": False,
        "film": False,
        "lab": False,
        "place": False,
        "scanner": False,
        "memo": True,
    },
}


_INVALID_FILENAME_TRANSLATION = str.maketrans("", "", '/\\:*?"<>|')
_WHITESPACE_PATTERN = re.compile(r"\s+")


def _safe_component(text):
    """
    파일명에 쓰기 어려운 문자만 정리한다.
    - 앞뒤 공백 제거
    - 경로 구분자/금지 문자 제거
    - 내부 공백은 사용자가 의도한 값일 수 있어 그대로 둔다
    """
    return (text or "").strip().translate(_INVALID_FILENAME_TRANSLATION).strip()


def _normalize_date(text):
    """날짜 입력값은 사용자가 적은 형태를 최대한 유지한다."""
    return _safe_component(text)


def _normalize_memo(text):
    """메모는 파일명에서 공백 없이 붙여 쓴다."""
    text = _safe_component(text)
    return _WHITESPACE_PATTERN.sub("", text)


class KoreanAwareLineEdit(QLineEdit):
    """
    macOS/Windows 한글 IME 조합 중인 마지막 글자를 미리보기에 반영하기 위한 입력창.
    QLineEdit.text()는 조합 중인 글자를 아직 확정 텍스트로 돌려주지 않을 수 있어서,
    inputMethodEvent의 preedit 문자열을 잠시 보관해 미리보기 계산에만 사용한다.
    """

    composingTextChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._preedit_text = ""

    def inputMethodEvent(self, event):
        self._preedit_text = event.preeditString() or ""
        super().inputMethodEvent(event)
        self.composingTextChanged.emit()
        QTimer.singleShot(0, self.composingTextChanged.emit)
        QTimer.singleShot(30, self.composingTextChanged.emit)

    def keyReleaseEvent(self, event):
        super().keyReleaseEvent(event)
        QTimer.singleShot(0, self.composingTextChanged.emit)

    def focusOutEvent(self, event):
        self._preedit_text = ""
        super().focusOutEvent(event)
        self.composingTextChanged.emit()

    def composed_text(self):
        base = self.text()
        preedit = self._preedit_text

        if not preedit:
            return base

        # Qt가 환경에 따라 preedit까지 text()에 포함해 돌려주는 경우가 있다.
        # 기존에는 `preedit in base`까지 중복 처리했는데, 이 조건 때문에
        # "아침스냅아침"처럼 같은 한글 조각을 반복 입력할 때 뒤쪽 조합 문자가
        # 미리보기에서 빠지는 문제가 생겼다.
        # 따라서 현재 확정 텍스트의 끝이 조합 문자열과 완전히 같을 때만 중복으로 본다.
        if base.endswith(preedit):
            return base

        cursor = max(0, min(self.cursorPosition(), len(base)))
        return base[:cursor] + preedit + base[cursor:]


class FilmDateEdit(QDateEdit):
    """Optional shooting-date picker with an empty state and calendar popup."""

    textChanged = Signal(str)
    composingTextChanged = Signal()
    EMPTY_DATE = QDate(1900, 1, 1)

    def __init__(self, value="", parent=None):
        super().__init__(parent)
        self.setObjectName("filmDateEdit")
        self.setCalendarPopup(True)
        self.setDisplayFormat("yyyy-MM-dd")
        self.setMinimumDate(self.EMPTY_DATE)
        self.setMaximumDate(QDate(2199, 12, 31))
        self.setSpecialValueText("날짜 선택")
        normalized = str(value or "").strip().replace(":", "-")[:10]
        parsed = QDate.fromString(normalized, "yyyy-MM-dd")
        self.setDate(parsed if parsed.isValid() else self.EMPTY_DATE)
        today = QDate.currentDate()
        current = parsed if parsed.isValid() else today
        self.calendarWidget().setCurrentPage(current.year(), current.month())
        self.dateChanged.connect(self._date_changed)
        self.lineEdit().installEventFilter(self)
        self.lineEdit().setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.ClickFocus)
        QTimer.singleShot(0, self._clear_section_highlight)

    def _clear_section_highlight(self):
        """Keep Qt from painting the year section as a blue text selection."""
        self.setCurrentSection(QDateTimeEdit.NoSection)
        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.deselect()

    def _date_changed(self, _date):
        self.textChanged.emit(self.text())
        self.composingTextChanged.emit()
        QTimer.singleShot(0, self._clear_section_highlight)

    def text(self):
        if self.date() == self.EMPTY_DATE:
            return ""
        return self.date().toString("yyyy-MM-dd")

    def setPlaceholderText(self, text):
        self.setSpecialValueText(text or "날짜 선택")

    def clear(self):
        self.setDate(self.EMPTY_DATE)

    def _calendar_click_event(self, event):
        if self.date() == self.EMPTY_DATE:
            self.setDate(QDate.currentDate())
        local_position = event.position()
        local_position.setX(max(1, self.width() - 5))
        local_position.setY(self.height() / 2)
        return QMouseEvent(
            event.type(),
            local_position,
            event.globalPosition(),
            event.button(),
            event.buttons(),
            event.modifiers(),
            event.pointingDevice(),
        )

    def eventFilter(self, watched, event):
        if watched is self.lineEdit() and event.type() == QEvent.FocusIn:
            QTimer.singleShot(0, self._clear_section_highlight)
        if watched is self.lineEdit() and event.type() in (
            QEvent.MouseButtonPress,
            QEvent.MouseButtonRelease,
        ) and event.button() == Qt.LeftButton:
            mapped_event = self._calendar_click_event(event)
            if event.type() == QEvent.MouseButtonPress:
                QDateEdit.mousePressEvent(self, mapped_event)
            else:
                QDateEdit.mouseReleaseEvent(self, mapped_event)
            QTimer.singleShot(0, self._clear_section_highlight)
            return True
        return super().eventFilter(watched, event)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        QTimer.singleShot(0, self._clear_section_highlight)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._clear_section_highlight)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            event = self._calendar_click_event(event)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            event = self._calendar_click_event(event)
        super().mouseReleaseEvent(event)
        QTimer.singleShot(0, self._clear_section_highlight)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.clear()
            event.accept()
            return
        super().keyPressEvent(event)


class FilmDateTimeEdit(QDateTimeEdit):
    """Optional EXIF date/time picker that keeps a real empty state."""

    EMPTY_DATETIME = QDateTime(QDate(1900, 1, 1), QTime(0, 0, 0))

    def __init__(self, value="", parent=None):
        super().__init__(parent)
        self.setObjectName("filmDateTimeEdit")
        self.setCalendarPopup(True)
        self.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.setMinimumDateTime(self.EMPTY_DATETIME)
        self.setMaximumDate(QDate(2199, 12, 31))
        self.setSpecialValueText("촬영 일시 선택")

        normalized = str(value or "").replace(":", "-", 2)
        parsed = QDateTime.fromString(normalized, "yyyy-MM-dd HH:mm:ss")
        self.setDateTime(parsed if parsed.isValid() else self.EMPTY_DATETIME)
        current = parsed if parsed.isValid() else QDateTime.currentDateTime()
        self.calendarWidget().setCurrentPage(current.date().year(), current.date().month())

    def text(self):
        if self.dateTime() == self.EMPTY_DATETIME:
            return ""
        return self.dateTime().toString("yyyy-MM-dd HH:mm:ss")

    def clear(self):
        self.setDateTime(self.EMPTY_DATETIME)

    def setPlaceholderText(self, text):
        self.setSpecialValueText(text or "촬영 일시 선택")

    def _calendar_click_event(self, event):
        local_position = event.position()
        if event.button() == Qt.LeftButton:
            if self.dateTime() == self.EMPTY_DATETIME:
                self.setDateTime(QDateTime.currentDateTime())
            local_position.setX(max(1, self.width() - 5))
        return QMouseEvent(
            event.type(),
            local_position,
            event.globalPosition(),
            event.button(),
            event.buttons(),
            event.modifiers(),
            event.pointingDevice(),
        )

    def mousePressEvent(self, event):
        super().mousePressEvent(self._calendar_click_event(event))

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(self._calendar_click_event(event))

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.clear()
            event.accept()
            return
        super().keyPressEvent(event)




def _set_dialog_button_width(button, minimum=92, maximum=128):
    """관리창 버튼 폭을 macOS/Windows에서 비슷하게 보이도록 정리한다."""
    button.setMinimumWidth(minimum)
    button.setMaximumWidth(maximum)

def _normalize_entry(entry):
    if isinstance(entry, dict):
        display = _safe_component(entry.get("display", ""))
        filename = _safe_component(entry.get("filename", ""))
    else:
        display = _safe_component(str(entry))
        filename = display

    if not display and filename:
        display = filename

    if not filename and display:
        filename = display

    if not display or not filename:
        return None

    return {
        "display": display,
        "filename": filename,
    }


def _read_json():
    if not PRESET_FILE.exists():
        return {}

    try:
        data = json.loads(PRESET_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json(data):
    PRESET_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_presets():
    data = _read_json()
    presets = {}

    for key in DEFAULT_PRESETS:
        items = []

        for raw in data.get(key, []):
            entry = _normalize_entry(raw)
            if entry and entry not in items:
                items.append(entry)

        presets[key] = items

    return presets


def save_presets(presets):
    data = _read_json()

    for key in DEFAULT_PRESETS:
        items = []

        for raw in presets.get(key, []):
            entry = _normalize_entry(raw)
            if entry and entry not in items:
                items.append(entry)

        data[key] = items

    _write_json(data)


def load_template_settings():
    data = _read_json()
    raw = data.get("template", {})

    order = raw.get("order", DEFAULT_TEMPLATE["order"])
    enabled = raw.get("enabled", DEFAULT_TEMPLATE["enabled"])

    valid_keys = list(TEMPLATE_LABELS.keys())

    cleaned_order = []
    for key in order:
        if key in valid_keys and key not in cleaned_order:
            cleaned_order.append(key)

    for key in valid_keys:
        if key not in cleaned_order:
            cleaned_order.append(key)

    cleaned_enabled = {}
    for key in valid_keys:
        cleaned_enabled[key] = bool(enabled.get(key, DEFAULT_TEMPLATE["enabled"][key]))

    # 번호가 빠지면 파일명이 중복되기 쉬워서 항상 켜둔다.
    cleaned_enabled["number"] = True

    return {
        "order": cleaned_order,
        "enabled": cleaned_enabled,
    }


def save_template_settings(settings):
    data = _read_json()
    data["template"] = settings
    _write_json(data)


def load_folder_template_settings():
    data = _read_json()
    raw = data.get("folder_template", {})

    order = raw.get("order", DEFAULT_FOLDER_TEMPLATE["order"])
    enabled = raw.get("enabled", DEFAULT_FOLDER_TEMPLATE["enabled"])

    valid_keys = [key for key in TEMPLATE_LABELS.keys() if key != "number"]

    cleaned_order = []
    for key in order:
        if key in valid_keys and key not in cleaned_order:
            cleaned_order.append(key)

    for key in valid_keys:
        if key not in cleaned_order:
            cleaned_order.append(key)

    cleaned_enabled = {}
    for key in valid_keys:
        cleaned_enabled[key] = bool(enabled.get(key, DEFAULT_FOLDER_TEMPLATE["enabled"][key]))

    return {
        "order": cleaned_order,
        "enabled": cleaned_enabled,
    }


def save_folder_template_settings(settings):
    data = _read_json()
    data["folder_template"] = settings
    _write_json(data)


class PresetEditDialog(QDialog):
    def __init__(self, title, entry=None, parent=None):
        super().__init__(parent)

        self.setWindowTitle(title)
        self.setMinimumWidth(360)

        entry = entry or {}

        layout = QVBoxLayout(self)
        form = QFormLayout()

        value = entry.get("display") or entry.get("filename") or ""

        self.value_edit = QLineEdit(value)
        self.value_edit.setPlaceholderText("예: KodakVision3_250D")

        form.addRow("이름", self.value_edit)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Cancel).setText("취소")
        buttons.button(QDialogButtonBox.Ok).setText("확인")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        # 한글 IME 조합 중인 마지막 글자가 저장에서 빠지는 경우를 줄이기 위해
        # 확인 버튼 처리 전에 입력 포커스를 먼저 정리한다.
        self.value_edit.clearFocus()
        QApplication.processEvents()
        super().accept()

    def values(self):
        self.value_edit.clearFocus()
        QApplication.processEvents()
        value = _safe_component(self.value_edit.text())

        return {
            "display": value,
            "filename": value,
        }

    def accept(self):
        values = self.values()

        if not values["display"]:
            QMessageBox.warning(
                self,
                "FilmFlip",
                "이름을 입력해주세요.",
            )
            return

        super().accept()


class ShootingPresetNameDialog(QDialog):
    def __init__(self, title, name="", parent=None):
        super().__init__(parent)

        self.setWindowTitle(title)
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit(name)
        self.name_edit.setPlaceholderText("예: FM2 + Colorplus200 + 다크룸")
        form.addRow("이름", self.name_edit)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Cancel).setText("취소")
        buttons.button(QDialogButtonBox.Ok).setText("저장")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def value(self):
        self.name_edit.clearFocus()
        QApplication.processEvents()
        return _safe_component(self.name_edit.text())

    def accept(self):
        if not self.value():
            QMessageBox.warning(
                self,
                "FilmFlip",
                "프리셋 이름을 입력해주세요.",
            )
            return

        super().accept()


class PresetManageDialog(QDialog):
    def __init__(self, label, items, parent=None):
        super().__init__(parent)

        self.setWindowTitle(f"{label} 관리")
        self.setMinimumWidth(420)
        self.items = [dict(item) for item in items]

        layout = QVBoxLayout(self)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        button_row = QHBoxLayout()

        add_button = QPushButton("＋ 추가")
        edit_button = set_button_icon(QPushButton("수정"), "edit")
        delete_button = set_button_icon(QPushButton("삭제"), "trash")
        up_button = QPushButton("▲ 위로")
        down_button = QPushButton("▼ 아래로")

        for button in (add_button, edit_button, delete_button, up_button, down_button):
            _set_dialog_button_width(button)

        add_button.clicked.connect(self.add_item)
        edit_button.clicked.connect(self.edit_item)
        delete_button.clicked.connect(self.delete_item)
        up_button.clicked.connect(self.move_item_up)
        down_button.clicked.connect(self.move_item_down)

        button_row.addWidget(add_button)
        button_row.addWidget(edit_button)
        button_row.addWidget(delete_button)
        button_row.addStretch()
        button_row.addWidget(up_button)
        button_row.addWidget(down_button)

        layout.addLayout(button_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Cancel).setText("취소")
        buttons.button(QDialogButtonBox.Ok).setText("선택")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.list_widget.itemDoubleClicked.connect(lambda _item: self.accept())

        self.refresh_list()

    def refresh_list(self):
        self.list_widget.clear()

        for entry in self.items:
            item = QListWidgetItem(entry["display"])
            item.setData(Qt.UserRole, entry)
            self.list_widget.addItem(item)

    def add_item(self):
        dialog = PresetEditDialog("새 항목 추가", parent=self)

        if dialog.exec() != QDialog.Accepted:
            return

        entry = dialog.values()

        if entry not in self.items:
            self.items.append(entry)
            self.refresh_list()
            self.list_widget.setCurrentRow(len(self.items) - 1)

    def edit_item(self):
        row = self.list_widget.currentRow()

        if row < 0:
            return

        current = self.items[row]
        dialog = PresetEditDialog("항목 수정", current, self)

        if dialog.exec() != QDialog.Accepted:
            return

        self.items[row] = dialog.values()
        self.refresh_list()
        self.list_widget.setCurrentRow(row)

    def delete_item(self):
        row = self.list_widget.currentRow()

        if row < 0:
            return

        entry = self.items[row]

        reply = QMessageBox.question(
            self,
            "FilmFlip",
            f"'{entry['display']}' 항목을 삭제할까요?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        del self.items[row]
        self.refresh_list()

        if self.items:
            self.list_widget.setCurrentRow(min(row, len(self.items) - 1))

    def move_item_up(self):
        row = self.list_widget.currentRow()

        if row <= 0:
            return

        self.items[row - 1], self.items[row] = self.items[row], self.items[row - 1]
        self.refresh_list()
        self.list_widget.setCurrentRow(row - 1)

    def move_item_down(self):
        row = self.list_widget.currentRow()

        if row < 0 or row >= len(self.items) - 1:
            return

        self.items[row + 1], self.items[row] = self.items[row], self.items[row + 1]
        self.refresh_list()
        self.list_widget.setCurrentRow(row + 1)

    def selected_entry(self):
        row = self.list_widget.currentRow()

        if 0 <= row < len(self.items):
            return dict(self.items[row])

        # 선택 없이 창을 닫은 경우에는 현재 입력값을 자동으로 바꾸지 않는다.
        return None

    def values(self):
        return [dict(item) for item in self.items]


class ShootingPresetManageDialog(QDialog):
    def __init__(self, presets, parent=None):
        super().__init__(parent)

        self.setWindowTitle("촬영 프리셋 관리")
        self.setMinimumWidth(460)
        self.presets = [dict(preset) for preset in presets]

        layout = QVBoxLayout(self)

        guide = QLabel("저장된 촬영 프리셋을 선택한 뒤 ▲/▼ 버튼으로 순서를 바꿀 수 있습니다.")
        layout.addWidget(guide)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_widget.setAlternatingRowColors(True)
        layout.addWidget(self.list_widget)

        button_row = QHBoxLayout()

        up_button = QPushButton("▲ 위로")
        down_button = QPushButton("▼ 아래로")
        rename_button = set_button_icon(QPushButton("이름 수정"), "edit")
        delete_button = set_button_icon(QPushButton("삭제"), "trash")

        for button in (up_button, down_button, rename_button, delete_button):
            _set_dialog_button_width(button)

        up_button.clicked.connect(self.move_current_up)
        down_button.clicked.connect(self.move_current_down)
        rename_button.clicked.connect(self.rename_current)
        delete_button.clicked.connect(self.delete_current)

        button_row.addWidget(up_button)
        button_row.addWidget(down_button)
        button_row.addStretch()
        button_row.addWidget(rename_button)
        button_row.addWidget(delete_button)

        layout.addLayout(button_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Cancel).setText("취소")
        buttons.button(QDialogButtonBox.Ok).setText("저장")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.refresh_list()

    def _preset_label(self, preset):
        # 관리창 목록에는 사용자가 저장한 프리셋 이름만 보여준다.
        # 카메라/필름/현상소 값까지 같이 보여주면 같은 문구가 반복되어 지저분해 보인다.
        return preset.get("name", "") or "이름 없음"

    def _preset_detail(self, preset):
        parts = [
            preset.get("camera", ""),
            preset.get("film", ""),
            preset.get("lab", ""),
            preset.get("place", ""),
            preset.get("scanner", ""),
        ]
        parts = [part for part in parts if part]
        return " / ".join(parts)

    def refresh_list(self):
        current_row = self.list_widget.currentRow()
        self.list_widget.clear()

        for preset in self.presets:
            item = QListWidgetItem(self._preset_label(preset))
            detail = self._preset_detail(preset)
            if detail:
                item.setToolTip(detail)
            item.setData(Qt.UserRole, dict(preset))
            self.list_widget.addItem(item)

        if self.presets:
            self.list_widget.setCurrentRow(min(max(current_row, 0), len(self.presets) - 1))

    def move_current_up(self):
        row = self.list_widget.currentRow()

        if row <= 0:
            return

        self.presets[row - 1], self.presets[row] = self.presets[row], self.presets[row - 1]
        self.refresh_list()
        self.list_widget.setCurrentRow(row - 1)

    def move_current_down(self):
        row = self.list_widget.currentRow()

        if row < 0 or row >= len(self.presets) - 1:
            return

        self.presets[row + 1], self.presets[row] = self.presets[row], self.presets[row + 1]
        self.refresh_list()
        self.list_widget.setCurrentRow(row + 1)

    def rename_current(self):
        row = self.list_widget.currentRow()

        if row < 0:
            return

        current = self.presets[row]
        dialog = ShootingPresetNameDialog(
            "촬영 프리셋 이름 수정",
            current.get("name", ""),
            self,
        )

        if dialog.exec() != QDialog.Accepted:
            return

        name = dialog.value()

        duplicated = any(
            index != row and preset.get("name", "") == name
            for index, preset in enumerate(self.presets)
        )

        if duplicated:
            QMessageBox.warning(
                self,
                "FilmFlip",
                f"'{name}' 프리셋이 이미 있습니다.",
            )
            return

        self.presets[row] = dict(current)
        self.presets[row]["name"] = name
        self.refresh_list()
        self.list_widget.setCurrentRow(row)

    def delete_current(self):
        row = self.list_widget.currentRow()

        if row < 0:
            return

        preset = self.presets[row]
        reply = QMessageBox.question(
            self,
            "FilmFlip",
            f"'{preset.get('name', '')}' 프리셋을 삭제할까요?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        del self.presets[row]
        self.refresh_list()

    def selected_name(self):
        row = self.list_widget.currentRow()

        if 0 <= row < len(self.presets):
            return self.presets[row].get("name", "")

        return ""

    def values(self):
        return [dict(preset) for preset in self.presets]


class TemplateListWidget(QListWidget):
    orderChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # 드래그 이동은 macOS/Windows Qt 환경에서 항목이 사라지는 문제가 있어
        # ▲/▼ 버튼으로만 순서를 변경한다.
        self.setDragDropMode(QAbstractItemView.NoDragDrop)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setAlternatingRowColors(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._scrollbar_hide_timer = QTimer(self)
        self._scrollbar_hide_timer.setSingleShot(True)
        self._scrollbar_hide_timer.setInterval(850)
        self._scrollbar_hide_timer.timeout.connect(self._hide_scrollbars)

    def wheelEvent(self, event):
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        super().wheelEvent(event)
        self._scrollbar_hide_timer.start()

    def _hide_scrollbars(self):
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def move_current_up(self):
        row = self.currentRow()

        if row <= 0:
            return

        item = self.takeItem(row)
        self.insertItem(row - 1, item)
        self.setCurrentRow(row - 1)
        self.orderChanged.emit()

    def move_current_down(self):
        row = self.currentRow()

        if row < 0 or row >= self.count() - 1:
            return

        item = self.takeItem(row)
        self.insertItem(row + 1, item)
        self.setCurrentRow(row + 1)
        self.orderChanged.emit()
