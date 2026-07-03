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
    QSizePolicy,
    QPlainTextEdit,
)

from shooting_presets import load_shooting_presets, save_shooting_presets
from .common import (
    PRESET_FILE, PRESET_KEYS, TEMPLATE_LABELS, FIELD_LABELS, DEFAULT_PRESETS,
    DEFAULT_TEMPLATE, DEFAULT_FOLDER_TEMPLATE, _safe_component, _normalize_date,
    _normalize_memo, KoreanAwareLineEdit, PresetManageDialog, ShootingPresetManageDialog,
    TemplateListWidget, load_presets, save_presets, load_template_settings,
    save_template_settings, load_folder_template_settings, save_folder_template_settings,
)

class FolderRenameDialog(QDialog):
    def __init__(self, current_folder, parent=None):
        super().__init__(parent)

        self.current_folder = Path(current_folder)
        self.presets = load_presets()
        self.shooting_presets = load_shooting_presets()
        self.template_settings = load_folder_template_settings()
        self._preview_update_pending = False
        self._preview_updates_suspended = 0

        self.setWindowTitle("폴더명 변경")
        self.setMinimumWidth(680)

        layout = QVBoxLayout(self)

        current_group = QGroupBox("현재 폴더")
        current_layout = QVBoxLayout(current_group)
        self.current_name_label = QLabel(self.current_folder.name)
        self.current_name_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        current_layout.addWidget(self.current_name_label)
        layout.addWidget(current_group)

        preset_group = QGroupBox("촬영 프리셋")
        preset_layout = QHBoxLayout(preset_group)

        self.shooting_combo = QComboBox()
        self._reload_shooting_presets()

        self.add_shooting_button = QPushButton("💾 저장")
        self.edit_shooting_button = QPushButton("📝 수정")
        self.delete_shooting_button = QPushButton("🗑 삭제")
        self.manage_shooting_button = QPushButton("⚙️ 편집")

        for button in [
            self.add_shooting_button,
            self.edit_shooting_button,
            self.delete_shooting_button,
            self.manage_shooting_button,
        ]:
            button.setMinimumWidth(58)
            button.setMaximumWidth(78)

        self.add_shooting_button.setToolTip("현재 카메라/필름/현상소/장소/스캐너 값을 새 촬영 프리셋으로 저장")
        self.edit_shooting_button.setToolTip("선택한 촬영 프리셋을 현재 카메라/필름/현상소/장소/스캐너 값으로 수정")
        self.delete_shooting_button.setToolTip("선택한 촬영 프리셋 삭제")
        self.manage_shooting_button.setToolTip("촬영 프리셋 목록 편집 및 순서 변경")

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

        field_group = QGroupBox("폴더명에 사용할 정보")
        field_grid = QGridLayout(field_group)

        self.date_edit = KoreanAwareLineEdit()
        self.date_edit.setPlaceholderText("예: 2026-07-01")

        self.memo_edit = KoreanAwareLineEdit()
        self.memo_edit.setPlaceholderText("예: 남이섬, 홍길동, 아침스냅")

        self.camera_combo = self._create_combo("camera")
        self.film_combo = self._create_combo("film")
        self.lab_combo = self._create_combo("lab")
        self.place_combo = self._create_combo("place")
        self.scanner_combo = self._create_combo("scanner")

        field_grid.addWidget(QLabel(FIELD_LABELS["date"]), 0, 0)
        field_grid.addWidget(self.date_edit, 0, 1)
        field_grid.addWidget(QLabel(FIELD_LABELS["memo"]), 1, 0)
        field_grid.addWidget(self.memo_edit, 1, 1)

        self._add_preset_row(field_grid, 2, "camera", self.camera_combo)
        self._add_preset_row(field_grid, 3, "film", self.film_combo)
        self._add_preset_row(field_grid, 4, "lab", self.lab_combo)
        self._add_preset_row(field_grid, 5, "place", self.place_combo)
        self._add_preset_row(field_grid, 6, "scanner", self.scanner_combo)

        layout.addWidget(field_group)

        order_group = QGroupBox("폴더명 구성")
        order_layout = QVBoxLayout(order_group)

        help_label = QLabel("체크한 항목만 폴더명에 들어갑니다. ▲/▼로 순서를 바꿀 수 있습니다.")
        help_label.setWordWrap(True)
        order_layout.addWidget(help_label)

        self.template_list = TemplateListWidget()
        self.template_list.setMinimumHeight(190)
        order_layout.addWidget(self.template_list)

        move_buttons = QHBoxLayout()
        up_button = QPushButton("▲ 위로")
        down_button = QPushButton("▼ 아래로")
        reset_button = QPushButton("기본값")

        up_button.clicked.connect(self.template_list.move_current_up)
        down_button.clicked.connect(self.template_list.move_current_down)
        reset_button.clicked.connect(self.reset_template)

        move_buttons.addWidget(up_button)
        move_buttons.addWidget(down_button)
        move_buttons.addStretch()
        move_buttons.addWidget(reset_button)

        order_layout.addLayout(move_buttons)
        layout.addWidget(order_group)

        preview_group = QGroupBox("폴더명 미리보기")
        preview_layout = QGridLayout(preview_group)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.setHorizontalSpacing(12)
        preview_layout.setVerticalSpacing(8)

        self.current_preview_label = QLabel(self.current_folder.name)
        self.current_preview_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.current_preview_label.setWordWrap(False)
        self.current_preview_label.setMinimumHeight(28)
        self.current_preview_label.setStyleSheet("font-weight: 600;")

        self.new_preview_label = QLabel("")
        self.new_preview_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.new_preview_label.setWordWrap(False)
        self.new_preview_label.setMinimumHeight(28)
        self.new_preview_label.setStyleSheet("font-weight: 600;")

        preview_layout.addWidget(QLabel("현재 폴더명"), 0, 0)
        preview_layout.addWidget(self.current_preview_label, 0, 1)
        preview_layout.addWidget(QLabel("변경될 폴더명"), 1, 0)
        preview_layout.addWidget(self.new_preview_label, 1, 1)

        layout.addWidget(preview_group)

        for combo in [
            self.camera_combo,
            self.film_combo,
            self.lab_combo,
            self.place_combo,
            self.scanner_combo,
        ]:
            combo.currentIndexChanged.connect(self.request_update_preview)
            combo.lineEdit().textChanged.connect(self.request_update_preview)
            if hasattr(combo.lineEdit(), "composingTextChanged"):
                combo.lineEdit().composingTextChanged.connect(self.request_update_preview)

        self.date_edit.textChanged.connect(self.request_update_preview)
        self.memo_edit.textChanged.connect(self.request_update_preview)
        self.date_edit.composingTextChanged.connect(self.request_update_preview)
        self.memo_edit.composingTextChanged.connect(self.request_update_preview)
        self.template_list.itemChanged.connect(self.request_update_preview)
        self.template_list.orderChanged.connect(self.request_update_preview)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        cancel_button = buttons.button(QDialogButtonBox.Cancel)
        ok_button = buttons.button(QDialogButtonBox.Ok)
        if cancel_button:
            cancel_button.setText("취소")
        if ok_button:
            ok_button.setText("폴더명 변경")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load_template_list()
        self.update_preview()

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
        label = QLabel(FIELD_LABELS.get(key, PRESET_KEYS[key]))
        manage_button = QPushButton("⚙️ 관리")
        manage_button.setMinimumWidth(62)
        manage_button.setMaximumWidth(76)
        manage_button.setToolTip(f"{PRESET_KEYS[key]} 목록 저장/수정/삭제/순서 변경")
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

    def _set_combo_text(self, combo, value):
        combo.blockSignals(True)
        combo.setCurrentText(value or "")
        combo.blockSignals(False)

    def apply_shooting_preset(self):
        preset = self.shooting_combo.currentData()

        if not preset:
            return

        self._suspend_preview_updates()

        try:
            self._set_combo_text(self.camera_combo, preset.get("camera", ""))
            self._set_combo_text(self.film_combo, preset.get("film", ""))
            self._set_combo_text(self.lab_combo, preset.get("lab", ""))
            self._set_combo_text(self.place_combo, preset.get("place", ""))
            self._set_combo_text(self.scanner_combo, preset.get("scanner", ""))

            self.set_template_enabled("camera", bool(preset.get("camera")))
            self.set_template_enabled("film", bool(preset.get("film")))
            self.set_template_enabled("lab", bool(preset.get("lab")))
            self.set_template_enabled("place", bool(preset.get("place")))
            self.set_template_enabled("scanner", bool(preset.get("scanner")))
        finally:
            self._resume_preview_updates(update=True)

    def _current_shooting_values(self):
        for combo in (self.camera_combo, self.film_combo, self.lab_combo, self.place_combo, self.scanner_combo):
            self._commit_pending_combo_text(combo)

        return {
            "camera": self._combo_filename(self.camera_combo),
            "film": self._combo_filename(self.film_combo),
            "lab": self._combo_filename(self.lab_combo),
            "place": self._combo_filename(self.place_combo),
            "scanner": self._combo_filename(self.scanner_combo),
        }

    def _default_shooting_name(self):
        values = self._current_shooting_values()
        parts = [
            values["camera"],
            values["film"],
            values["lab"],
            values["place"],
            values["scanner"],
        ]
        parts = [part for part in parts if part]
        return " + ".join(parts) if parts else "새 촬영 프리셋"

    def add_shooting_preset(self):
        values = self._current_shooting_values()

        if not any(values.values()):
            QMessageBox.information(
                self,
                "FilmFlip",
                "카메라, 필름, 현상소, 장소, 스캐너 중 하나 이상을 먼저 선택해주세요.",
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

        preset = {
            "name": name,
            "camera": values["camera"],
            "film": values["film"],
            "lab": values["lab"],
            "place": values["place"],
            "scanner": values["scanner"],
        }

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

            self.shooting_presets[duplicate_index] = preset
        else:
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

        self.shooting_presets[index - 1] = {
            "name": name,
            "camera": values["camera"],
            "film": values["film"],
            "lab": values["lab"],
            "place": values["place"],
            "scanner": values["scanner"],
        }

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

    def set_template_enabled(self, key, enabled):
        for row in range(self.template_list.count()):
            item = self.template_list.item(row)

            if item.data(Qt.UserRole) == key:
                self.template_list.blockSignals(True)
                item.setCheckState(Qt.Checked if enabled else Qt.Unchecked)
                self.template_list.blockSignals(False)
                return

    def _load_template_list(self):
        self.template_list.blockSignals(True)
        self.template_list.clear()

        enabled = self.template_settings["enabled"]

        for key in self.template_settings["order"]:
            if key == "number":
                continue

            item = QListWidgetItem(f"☰ {FIELD_LABELS.get(key, TEMPLATE_LABELS[key])}")
            item.setData(Qt.UserRole, key)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if enabled.get(key, False) else Qt.Unchecked)
            self.template_list.addItem(item)

        self.template_list.blockSignals(False)

    def reset_template(self):
        self.template_settings = {
            "order": list(DEFAULT_FOLDER_TEMPLATE["order"]),
            "enabled": dict(DEFAULT_FOLDER_TEMPLATE["enabled"]),
        }
        self._load_template_list()
        self.update_preview()

    def _current_template_settings(self):
        order = []
        enabled = {}

        for row in range(self.template_list.count()):
            item = self.template_list.item(row)
            key = item.data(Qt.UserRole)

            if key not in TEMPLATE_LABELS or key == "number":
                continue

            order.append(key)
            enabled[key] = item.checkState() == Qt.Checked

        return {
            "order": order,
            "enabled": enabled,
        }

    def _commit_pending_combo_text(self, combo):
        line_edit = combo.lineEdit() if combo and combo.isEditable() else None
        if line_edit:
            line_edit.clearFocus()
            QApplication.processEvents()

    def _combo_text(self, combo):
        if combo and combo.isEditable() and combo.lineEdit():
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

    def _line_text(self, line_edit):
        if hasattr(line_edit, "composed_text"):
            return line_edit.composed_text()
        return line_edit.text()

    def _line_filename(self, line_edit):
        return _safe_component(self._line_text(line_edit))

    def _components_map(self):
        return {
            "date": _normalize_date(self._line_filename(self.date_edit)),
            "camera": self._combo_filename(self.camera_combo),
            "film": self._combo_filename(self.film_combo),
            "lab": self._combo_filename(self.lab_combo),
            "place": self._combo_filename(self.place_combo),
            "scanner": self._combo_filename(self.scanner_combo),
            "memo": _normalize_memo(self._line_filename(self.memo_edit)),
        }

    def _template(self):
        settings = self._current_template_settings()
        components = self._components_map()
        parts = []

        for key in settings["order"]:
            if not settings["enabled"].get(key, False):
                continue

            value = components.get(key, "")
            if value:
                parts.append(value)

        return "_".join(parts)

    def update_preview(self):
        self._preview_update_pending = False

        folder_name = self._template()

        if not folder_name:
            folder_name = self.current_folder.name

        if self.current_preview_label.text() != self.current_folder.name:
            self.current_preview_label.setText(self.current_folder.name)

        if self.new_preview_label.text() != folder_name:
            self.new_preview_label.setText(folder_name)

    def values(self):
        for combo in (self.camera_combo, self.film_combo, self.lab_combo, self.place_combo, self.scanner_combo):
            self._commit_pending_combo_text(combo)

        for line_edit in (self.date_edit, self.memo_edit):
            line_edit.clearFocus()

        QApplication.processEvents()

        settings = self._current_template_settings()
        save_folder_template_settings(settings)

        return {
            "template": self._template(),
            "template_settings": settings,
        }




