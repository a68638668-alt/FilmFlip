from settings import get_data_file
import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QTimer
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
)


from shooting_presets import load_shooting_presets, save_shooting_presets

PRESET_FILE = get_data_file("filmflip_presets.json")

PRESET_KEYS = {
    "camera": "카메라",
    "film": "필름",
    "lab": "현상소",
    "place": "장소",
}

TEMPLATE_LABELS = {
    "camera": "카메라",
    "film": "필름",
    "lab": "현상소",
    "place": "장소",
    "number": "번호",
}

DEFAULT_PRESETS = {
    "camera": [],
    "film": [],
    "lab": [],
    "place": [],
}

DEFAULT_TEMPLATE = {
    "order": ["camera", "film", "lab", "place", "number"],
    "enabled": {
        "camera": True,
        "film": True,
        "lab": True,
        "place": True,
        "number": True,
    },
}


_INVALID_FILENAME_TRANSLATION = str.maketrans("", "", '/\\:*?"<>|')


def _safe_component(text):
    """
    파일명에 쓰기 어려운 문자만 정리한다.
    - 앞뒤 공백 제거
    - 경로 구분자/금지 문자 제거
    - 내부 공백은 사용자가 의도한 값일 수 있어 그대로 둔다
    """
    return (text or "").strip().translate(_INVALID_FILENAME_TRANSLATION).strip()




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

        # Qt가 환경에 따라 preedit까지 text()에 포함해 돌려주는 경우가 있어 중복을 피한다.
        if base.endswith(preedit) or preedit in base:
            return base

        cursor = max(0, min(self.cursorPosition(), len(base)))
        return base[:cursor] + preedit + base[cursor:]


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
        edit_button = QPushButton("✏ 수정")
        delete_button = QPushButton("🗑 삭제")
        up_button = QPushButton("▲ 위로")
        down_button = QPushButton("▼ 아래로")

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

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

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

        if self.items:
            return dict(self.items[-1])

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
        rename_button = QPushButton("✏ 이름 수정")
        delete_button = QPushButton("🗑 삭제")

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

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
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
        name, ok = QInputDialog.getText(
            self,
            "촬영 프리셋 이름 수정",
            "프리셋 이름",
            text=current.get("name", ""),
        )

        if not ok:
            return

        name = _safe_component(name)

        if not name:
            return

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


class RenameDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("이름 변경")
        self.setMinimumWidth(560)

        self.presets = load_presets()
        self.shooting_presets = load_shooting_presets()
        self.template_settings = load_template_settings()

        # 프리셋 적용/체크 변경 중 미리보기가 여러 번 연속 갱신되면
        # 이름 변경 창을 열 때와 입력할 때 체감 반응이 느려질 수 있다.
        # 짧게 묶어서 한 번만 갱신한다.
        self._preview_update_pending = False
        self._preview_updates_suspended = 0

        layout = QVBoxLayout(self)

        description = QLabel(
            "카메라, 필름, 현상소, 장소를 선택하면\n"
            "번호는 자동으로 001부터 붙습니다."
        )
        layout.addWidget(description)

        preset_group = QGroupBox("촬영 프리셋")
        preset_layout = QHBoxLayout(preset_group)

        self.shooting_combo = QComboBox()
        self.shooting_combo.addItem("없음", None)
        self._reload_shooting_presets()

        self.add_shooting_button = QPushButton("＋")
        self.edit_shooting_button = QPushButton("✏")
        self.delete_shooting_button = QPushButton("🗑")
        self.manage_shooting_button = QPushButton("⚙")

        self.add_shooting_button.setFixedWidth(42)
        self.edit_shooting_button.setFixedWidth(42)
        self.delete_shooting_button.setFixedWidth(42)
        self.manage_shooting_button.setFixedWidth(42)

        self.add_shooting_button.setToolTip("촬영 프리셋 추가")
        self.edit_shooting_button.setToolTip("선택한 촬영 프리셋 수정")
        self.delete_shooting_button.setToolTip("선택한 촬영 프리셋 삭제")
        self.manage_shooting_button.setToolTip("촬영 프리셋 순서 관리")

        self.shooting_combo.currentIndexChanged.connect(self.apply_shooting_preset)
        self.add_shooting_button.clicked.connect(self.add_shooting_preset)
        self.edit_shooting_button.clicked.connect(self.edit_shooting_preset)
        self.delete_shooting_button.clicked.connect(self.delete_shooting_preset)
        self.manage_shooting_button.clicked.connect(self.manage_shooting_presets)

        preset_layout.addWidget(self.shooting_combo)
        preset_layout.addWidget(self.add_shooting_button)
        preset_layout.addWidget(self.edit_shooting_button)
        preset_layout.addWidget(self.delete_shooting_button)
        preset_layout.addWidget(self.manage_shooting_button)

        layout.addWidget(preset_group)

        grid = QGridLayout()

        self.camera_combo = self._create_combo("camera")
        self.film_combo = self._create_combo("film")
        self.lab_combo = self._create_combo("lab")
        self.place_combo = self._create_combo("place")

        self._add_preset_row(grid, 0, "camera", self.camera_combo)
        self._add_preset_row(grid, 1, "film", self.film_combo)
        self._add_preset_row(grid, 2, "lab", self.lab_combo)
        self._add_preset_row(grid, 3, "place", self.place_combo)

        layout.addLayout(grid)

        order_group = QGroupBox("파일명 구성")
        order_layout = QVBoxLayout(order_group)

        guide = QLabel("체크로 사용 여부를 정하고, ▲/▼ 버튼으로 순서를 바꿀 수 있습니다.")
        order_layout.addWidget(guide)

        self.template_list = TemplateListWidget()
        self.template_list.setMaximumHeight(170)
        order_layout.addWidget(self.template_list)

        move_buttons = QHBoxLayout()

        up_button = QPushButton("▲ 위로")
        down_button = QPushButton("▼ 아래로")
        reset_button = QPushButton("기본값 복원")

        up_button.clicked.connect(self.template_list.move_current_up)
        down_button.clicked.connect(self.template_list.move_current_down)
        reset_button.clicked.connect(self.reset_template)

        move_buttons.addWidget(up_button)
        move_buttons.addWidget(down_button)
        move_buttons.addStretch()
        move_buttons.addWidget(reset_button)

        order_layout.addLayout(move_buttons)

        layout.addWidget(order_group)
        self._load_template_list()

        self.normal_radio = QRadioButton("현재 순서 유지 (기본)")
        self.normal_radio.setChecked(True)

        self.reverse_radio = QRadioButton("역순")
        self.reverse_radio.setChecked(False)

        layout.addWidget(self.normal_radio)
        layout.addWidget(self.reverse_radio)

        self.example = QLabel()
        self.example.setMinimumHeight(80)
        layout.addWidget(self.example)

        for combo in [
            self.camera_combo,
            self.film_combo,
            self.lab_combo,
            self.place_combo,
        ]:
            combo.currentIndexChanged.connect(self.request_update_preview)
            combo.lineEdit().textChanged.connect(self.request_update_preview)
            if hasattr(combo.lineEdit(), "composingTextChanged"):
                combo.lineEdit().composingTextChanged.connect(self.request_update_preview)

        self.reverse_radio.toggled.connect(self.request_update_preview)
        self.template_list.itemChanged.connect(self.request_update_preview)
        self.template_list.orderChanged.connect(self.request_update_preview)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addWidget(buttons)

        self.update_preview()

    def _suspend_preview_updates(self):
        self._preview_updates_suspended += 1

    def _resume_preview_updates(self, update=True):
        self._preview_updates_suspended = max(0, self._preview_updates_suspended - 1)

        if update:
            self.request_update_preview()

    def request_update_preview(self, *args):
        if self._preview_updates_suspended:
            return

        if self._preview_update_pending:
            return

        self._preview_update_pending = True
        QTimer.singleShot(0, self.update_preview)

    def _reload_shooting_presets(self, keep_name=""):
        self.shooting_combo.blockSignals(True)
        self.shooting_combo.clear()
        self.shooting_combo.addItem("없음", None)

        selected_index = 0

        for preset in self.shooting_presets:
            self.shooting_combo.addItem(preset.get("name", ""), dict(preset))

            if keep_name and preset.get("name", "") == keep_name:
                selected_index = self.shooting_combo.count() - 1

        self.shooting_combo.setCurrentIndex(selected_index)
        self.shooting_combo.blockSignals(False)

    def _set_combo_text(self, combo, value):
        combo.blockSignals(True)
        combo.setCurrentText(value or "")
        combo.blockSignals(False)

    def set_template_enabled(self, key, enabled):
        for row in range(self.template_list.count()):
            item = self.template_list.item(row)

            if item.data(Qt.UserRole) == key:
                self.template_list.blockSignals(True)
                item.setCheckState(Qt.Checked if enabled else Qt.Unchecked)
                self.template_list.blockSignals(False)
                return

    def apply_shooting_preset(self):
        preset = self.shooting_combo.currentData()

        if not preset:
            return

        self._suspend_preview_updates()

        try:
            self._set_combo_text(self.camera_combo, preset.get("camera", ""))
            self._set_combo_text(self.film_combo, preset.get("film", ""))
            self._set_combo_text(self.lab_combo, preset.get("lab", ""))

            # 프리셋에 값이 있는 항목은 파일명 구성에서 자동 체크
            self.set_template_enabled("camera", bool(preset.get("camera")))
            self.set_template_enabled("film", bool(preset.get("film")))
            self.set_template_enabled("lab", bool(preset.get("lab")))
            self.set_template_enabled("number", True)
        finally:
            # 장소는 촬영마다 달라지는 값이라 프리셋에서 건드리지 않는다.
            self._resume_preview_updates(update=True)

    def _current_shooting_values(self):
        for combo in (self.camera_combo, self.film_combo, self.lab_combo):
            self._commit_pending_combo_text(combo)

        return {
            "camera": self._combo_filename(self.camera_combo),
            "film": self._combo_filename(self.film_combo),
            "lab": self._combo_filename(self.lab_combo),
        }

    def _default_shooting_name(self):
        values = self._current_shooting_values()
        parts = [
            values["camera"],
            values["film"],
            values["lab"],
        ]
        parts = [part for part in parts if part]
        return " + ".join(parts) if parts else "새 촬영 프리셋"

    def add_shooting_preset(self):
        values = self._current_shooting_values()

        if not any(values.values()):
            QMessageBox.information(
                self,
                "FilmFlip",
                "카메라, 필름, 현상소 중 하나 이상을 먼저 선택해주세요.",
            )
            return

        name, ok = QInputDialog.getText(
            self,
            "촬영 프리셋 추가",
            "프리셋 이름",
            text=self._default_shooting_name(),
        )

        if not ok:
            return

        name = _safe_component(name)

        if not name:
            return

        duplicate_index = next(
            (
                i for i, preset in enumerate(self.shooting_presets)
                if preset.get("name", "") == name
            ),
            None,
        )

        if duplicate_index is not None:
            reply = QMessageBox.question(
                self,
                "FilmFlip",
                f"'{name}' 프리셋이 이미 있습니다.\n덮어쓸까요?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )

            if reply != QMessageBox.Yes:
                return

            self.shooting_presets[duplicate_index] = {
                "name": name,
                "camera": values["camera"],
                "film": values["film"],
                "lab": values["lab"],
            }
            save_shooting_presets(self.shooting_presets)
            self._reload_shooting_presets(name)
            self.apply_shooting_preset()
            self.update_preview()
            return

        preset = {
            "name": name,
            "camera": values["camera"],
            "film": values["film"],
            "lab": values["lab"],
        }

        self.shooting_presets.append(preset)
        save_shooting_presets(self.shooting_presets)
        self._reload_shooting_presets(name)
        self.apply_shooting_preset()
        self.update_preview()

    def edit_shooting_preset(self):
        index = self.shooting_combo.currentIndex()

        if index <= 0:
            return

        preset = self.shooting_combo.currentData()

        if not preset:
            return

        name, ok = QInputDialog.getText(
            self,
            "촬영 프리셋 수정",
            "프리셋 이름",
            text=preset.get("name", ""),
        )

        if not ok:
            return

        name = _safe_component(name)

        if not name:
            return

        duplicate_index = next(
            (
                i for i, preset in enumerate(self.shooting_presets)
                if i != index - 1 and preset.get("name", "") == name
            ),
            None,
        )

        if duplicate_index is not None:
            QMessageBox.warning(
                self,
                "FilmFlip",
                f"'{name}' 프리셋이 이미 있습니다.",
            )
            return

        values = self._current_shooting_values()

        new_preset = {
            "name": name,
            "camera": values["camera"],
            "film": values["film"],
            "lab": values["lab"],
        }

        self.shooting_presets[index - 1] = new_preset
        save_shooting_presets(self.shooting_presets)
        self._reload_shooting_presets(name)
        self.apply_shooting_preset()
        self.update_preview()

    def delete_shooting_preset(self):
        index = self.shooting_combo.currentIndex()

        if index <= 0:
            return

        preset = self.shooting_combo.currentData()

        if not preset:
            return

        reply = QMessageBox.question(
            self,
            "FilmFlip",
            f"'{preset.get('name', '')}' 프리셋을 삭제할까요?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        del self.shooting_presets[index - 1]
        save_shooting_presets(self.shooting_presets)
        self._reload_shooting_presets()
        self.update_preview()

    def manage_shooting_presets(self):
        current_name = ""
        current_preset = self.shooting_combo.currentData()

        if current_preset:
            current_name = current_preset.get("name", "")

        dialog = ShootingPresetManageDialog(self.shooting_presets, self)

        if dialog.exec() != QDialog.Accepted:
            return

        selected_name = dialog.selected_name() or current_name
        self.shooting_presets = dialog.values()
        save_shooting_presets(self.shooting_presets)
        self._reload_shooting_presets(selected_name)
        self.apply_shooting_preset()
        self.update_preview()

    def move_shooting_preset_up(self):
        index = self.shooting_combo.currentIndex()

        if index <= 1:
            return

        preset_index = index - 1
        preset = self.shooting_presets[preset_index]

        self.shooting_presets[preset_index - 1], self.shooting_presets[preset_index] = (
            self.shooting_presets[preset_index],
            self.shooting_presets[preset_index - 1],
        )

        save_shooting_presets(self.shooting_presets)
        self._reload_shooting_presets(preset.get("name", ""))

    def move_shooting_preset_down(self):
        index = self.shooting_combo.currentIndex()

        if index <= 0:
            return

        preset_index = index - 1

        if preset_index >= len(self.shooting_presets) - 1:
            return

        preset = self.shooting_presets[preset_index]

        self.shooting_presets[preset_index + 1], self.shooting_presets[preset_index] = (
            self.shooting_presets[preset_index],
            self.shooting_presets[preset_index + 1],
        )

        save_shooting_presets(self.shooting_presets)
        self._reload_shooting_presets(preset.get("name", ""))

    def _create_combo(self, key):
        combo = QComboBox()
        combo.setEditable(True)
        combo.setLineEdit(KoreanAwareLineEdit())
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.lineEdit().setPlaceholderText(f"{PRESET_KEYS[key]} 선택 또는 직접 입력")
        self._reload_combo(combo, key)
        return combo

    def _reload_combo(self, combo, key, keep_text=""):
        if not keep_text:
            keep_text = combo.currentText() if combo.count() else ""

        combo.blockSignals(True)
        combo.clear()

        for entry in self.presets.get(key, []):
            combo.addItem(entry["display"], entry["filename"])

        combo.setCurrentText(keep_text)
        combo.blockSignals(False)

    def _add_preset_row(self, grid, row, key, combo):
        label = QLabel(PRESET_KEYS[key])
        manage_button = QPushButton("⚙")
        manage_button.setFixedWidth(42)
        manage_button.clicked.connect(
            lambda _checked=False, preset_key=key, target_combo=combo:
            self.manage_presets(preset_key, target_combo)
        )

        grid.addWidget(label, row, 0)
        grid.addWidget(combo, row, 1)
        grid.addWidget(manage_button, row, 2)

    def manage_presets(self, key, combo):
        dialog = PresetManageDialog(
            PRESET_KEYS[key],
            self.presets.get(key, []),
            self,
        )

        if dialog.exec() != QDialog.Accepted:
            return

        selected = dialog.selected_entry()

        self.presets[key] = dialog.values()
        save_presets(self.presets)

        keep_text = selected["display"] if selected else ""
        self._reload_combo(combo, key, keep_text)

        self.update_preview()

    def _load_template_list(self):
        self.template_list.blockSignals(True)
        self.template_list.clear()

        enabled = self.template_settings["enabled"]

        for key in self.template_settings["order"]:
            item = QListWidgetItem(f"☰ {TEMPLATE_LABELS[key]}")
            item.setData(Qt.UserRole, key)
            item.setFlags(
                item.flags()
                | Qt.ItemIsUserCheckable
            )
            item.setCheckState(Qt.Checked if enabled.get(key, True) else Qt.Unchecked)

            if key == "number":
                # 번호를 끄면 파일명이 중복될 수 있어 항상 켜둔다.
                item.setCheckState(Qt.Checked)

            self.template_list.addItem(item)

        self.template_list.blockSignals(False)

    def reset_template(self):
        self.template_settings = {
            "order": list(DEFAULT_TEMPLATE["order"]),
            "enabled": dict(DEFAULT_TEMPLATE["enabled"]),
        }
        self._load_template_list()
        self.update_preview()

    def _current_template_settings(self):
        order = []
        enabled = {}

        for row in range(self.template_list.count()):
            item = self.template_list.item(row)
            key = item.data(Qt.UserRole)

            if key not in TEMPLATE_LABELS:
                continue

            order.append(key)
            enabled[key] = item.checkState() == Qt.Checked

        enabled["number"] = True

        return {
            "order": order,
            "enabled": enabled,
        }

    def _commit_pending_combo_text(self, combo):
        line_edit = combo.lineEdit() if combo and combo.isEditable() else None
        if line_edit:
            # macOS/Windows 한글 IME에서 마지막 조합 글자가 currentText에 늦게 반영되는 경우 방지
            line_edit.clearFocus()
            QApplication.processEvents()

    def _combo_text(self, combo):
        if combo and combo.isEditable() and combo.lineEdit():
            # macOS/Windows 한글 IME에서 마지막 글자가 아직 조합 중이면
            # QLineEdit.text()에 포함되지 않을 수 있어 preedit 문자열까지 반영한다.
            line_edit = combo.lineEdit()
            if hasattr(line_edit, "composed_text"):
                return line_edit.composed_text()
            return line_edit.text()

        return combo.currentText() if combo else ""

    def _combo_filename(self, combo):
        text = _safe_component(self._combo_text(combo))

        if not text:
            return ""

        index = combo.findText(text)

        if index >= 0:
            filename = combo.itemData(index, Qt.UserRole)
            if filename:
                return _safe_component(filename)

        return text

    def _components_map(self):
        return {
            "camera": self._combo_filename(self.camera_combo),
            "film": self._combo_filename(self.film_combo),
            "lab": self._combo_filename(self.lab_combo),
            "place": self._combo_filename(self.place_combo),
            "number": "{n}",
        }

    def _template(self):
        settings = self._current_template_settings()
        components = self._components_map()
        parts = []

        for key in settings["order"]:
            if not settings["enabled"].get(key, True):
                continue

            value = components.get(key, "")
            if value:
                parts.append(value)

        if "{n}" not in parts:
            parts.append("{n}")

        return "_".join(parts)

    def update_preview(self):
        self._preview_update_pending = False

        template = self._template()
        nums = ["003", "002", "001"] if self.reverse_radio.isChecked() else ["001", "002", "003"]

        preview_text = "미리보기\n" + "\n".join(
            template.replace("{n}", number) + ".jpg"
            for number in nums
        )

        if self.example.text() != preview_text:
            self.example.setText(preview_text)

    def values(self):
        for combo in (self.camera_combo, self.film_combo, self.lab_combo, self.place_combo):
            self._commit_pending_combo_text(combo)

        components = self._components_map()
        settings = self._current_template_settings()

        save_template_settings(settings)

        return {
            "camera": components["camera"],
            "film": components["film"],
            "lab": components["lab"],
            "place": components["place"],
            "template": self._template(),
            "reverse": self.reverse_radio.isChecked(),
            "template_settings": settings,
        }



def confirm_rename(parent, count):
    reply = QMessageBox.question(
        parent,
        "FilmFlip",
        f"총 {count}개의 파일명을 변경합니다.\n\n계속하시겠습니까?",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    return reply == QMessageBox.Yes


def rename_finished(parent, count):
    QMessageBox.information(
        parent,
        "FilmFlip",
        f"✅ {count}개의 파일명을 변경했습니다.",
    )


def no_images(parent):
    QMessageBox.information(
        parent,
        "FilmFlip",
        "이미지가 없습니다.",
    )


def rename_failed(parent, error):
    QMessageBox.critical(
        parent,
        "FilmFlip",
        f"오류가 발생했습니다.\n\n{error}",
    )
