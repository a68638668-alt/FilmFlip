import json
from pathlib import Path

from PySide6.QtCore import Qt
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
)


PRESET_FILE = Path(__file__).with_name("filmflip_presets.json")

PRESET_KEYS = {
    "camera": "카메라",
    "film": "필름",
    "lab": "현상소",
    "place": "장소",
}


DEFAULT_PRESETS = {
    "camera": [],
    "film": [],
    "lab": [],
    "place": [],
}


def _safe_component(text):
    """
    파일명에 쓰기 어려운 문자만 정리한다.
    - 앞뒤 공백 제거
    - 경로 구분자/금지 문자 제거
    - 내부 공백은 사용자가 의도한 값일 수 있어 그대로 둔다
    """
    text = (text or "").strip()

    for char in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
        text = text.replace(char, "")

    return text.strip()


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


def load_presets():
    if not PRESET_FILE.exists():
        return {key: [] for key in DEFAULT_PRESETS}

    try:
        data = json.loads(PRESET_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {key: [] for key in DEFAULT_PRESETS}

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
    cleaned = {}

    for key in DEFAULT_PRESETS:
        items = []

        for raw in presets.get(key, []):
            entry = _normalize_entry(raw)
            if entry and entry not in items:
                items.append(entry)

        cleaned[key] = items

    PRESET_FILE.write_text(
        json.dumps(cleaned, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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

    def values(self):
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

        add_button.clicked.connect(self.add_item)
        edit_button.clicked.connect(self.edit_item)
        delete_button.clicked.connect(self.delete_item)

        button_row.addWidget(add_button)
        button_row.addWidget(edit_button)
        button_row.addWidget(delete_button)

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

    def selected_entry(self):
        row = self.list_widget.currentRow()

        if 0 <= row < len(self.items):
            return dict(self.items[row])

        if self.items:
            return dict(self.items[-1])

        return None

    def values(self):
        return [dict(item) for item in self.items]


class RenameDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("이름 변경")
        self.setMinimumWidth(520)

        self.presets = load_presets()

        layout = QVBoxLayout(self)

        description = QLabel(
            "카메라, 필름, 현상소, 장소를 선택하면\n"
            "번호는 자동으로 001부터 붙습니다."
        )
        layout.addWidget(description)

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
            combo.currentIndexChanged.connect(self.update_preview)
            combo.lineEdit().textChanged.connect(self.update_preview)

        self.reverse_radio.toggled.connect(self.update_preview)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addWidget(buttons)

        self.update_preview()

    def _create_combo(self, key):
        combo = QComboBox()
        combo.setEditable(True)
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

    def _combo_filename(self, combo):
        text = _safe_component(combo.currentText())

        if not text:
            return ""

        index = combo.findText(text)

        if index >= 0:
            filename = combo.itemData(index, Qt.UserRole)
            if filename:
                return _safe_component(filename)

        return text

    def _components(self):
        return [
            self._combo_filename(self.camera_combo),
            self._combo_filename(self.film_combo),
            self._combo_filename(self.lab_combo),
            self._combo_filename(self.place_combo),
        ]

    def _template(self):
        parts = [part for part in self._components() if part]
        parts.append("{n}")
        return "_".join(parts)

    def update_preview(self):
        template = self._template()
        nums = ["003", "002", "001"] if self.reverse_radio.isChecked() else ["001", "002", "003"]

        self.example.setText(
            "미리보기\n" + "\n".join(
                template.replace("{n}", number) + ".jpg"
                for number in nums
            )
        )

    def values(self):
        camera, film, lab, place = self._components()

        return {
            "camera": camera,
            "film": film,
            "lab": lab,
            "place": place,
            "template": self._template(),
            "reverse": self.reverse_radio.isChecked(),
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
