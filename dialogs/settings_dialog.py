import re

from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QVBoxLayout,
    QLabel,
)

from utils.design import dialog_theme_override, icon_text_widget, polish_combo_boxes


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = dict(settings)
        self.setWindowTitle("FilmFlip 설정")
        self.setFixedWidth(520)
        self.setStyleSheet(self._style() + dialog_theme_override(getattr(parent, "dark_mode", False)))

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(8)

        view_group = QGroupBox("화면")
        view_form = QFormLayout(view_group)
        view_form.setContentsMargins(12, 10, 12, 10)
        view_form.setSpacing(8)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("일반 모드", "light")
        self.theme_combo.addItem("다크 모드", "dark")
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(settings.get("theme", "light"))))

        self.thumbnail_combo = QComboBox()
        self.thumbnail_combo.addItem("작게", "small")
        self.thumbnail_combo.addItem("보통", "medium")
        self.thumbnail_combo.addItem("크게", "large")
        self.thumbnail_combo.setCurrentIndex(max(0, self.thumbnail_combo.findData(settings.get("thumbnail_size", "medium"))))

        view_form.addRow(icon_text_widget("테마", "sun", 22), self.theme_combo)
        view_form.addRow(icon_text_widget("썸네일 크기", "thumbnail", 22), self.thumbnail_combo)
        root.addWidget(view_group)

        workflow_group = QGroupBox("작업 기본값")
        workflow_form = QFormLayout(workflow_group)
        workflow_form.setContentsMargins(12, 10, 12, 10)
        workflow_form.setSpacing(8)

        self.roll_count_combo = QComboBox()
        self.roll_count_combo.setEditable(True)
        self.roll_count_combo.lineEdit().setValidator(QIntValidator(1, 999, self))
        for label, count in (("24컷", 24), ("27컷", 27), ("36컷", 36), ("72컷 (하프)", 72)):
            self.roll_count_combo.addItem(label, count)
        current_count = int(settings.get("roll_base_count", 36) or 36)
        index = self.roll_count_combo.findData(current_count)
        if index >= 0:
            self.roll_count_combo.setCurrentIndex(index)
        else:
            self.roll_count_combo.setEditText(str(current_count))
        self.roll_count_combo.setToolTip("24·27·36·72컷을 선택하거나 실제 기준 컷수를 직접 입력할 수 있습니다.")

        self.sort_combo = QComboBox()
        self.sort_combo.addItem("역순", "reverse")
        self.sort_combo.addItem("현재 순서 유지", "normal")
        self.sort_combo.setCurrentIndex(max(0, self.sort_combo.findData(settings.get("default_sort", "reverse"))))

        self.remember_checkbox = QCheckBox("마지막으로 선택한 폴더 기억")
        self.remember_checkbox.setChecked(bool(settings.get("remember_last_folder", True)))

        workflow_form.addRow(icon_text_widget("롤 기준 컷수", "film_roll", 22), self.roll_count_combo)
        workflow_form.addRow(icon_text_widget("기본 정렬", "reverse", 22), self.sort_combo)
        workflow_form.addRow("", self.remember_checkbox)
        roll_help = QLabel("목록보다 많이 촬영된 컷은 메인 ROLL 카드에 +초과 컷수로 표시됩니다.")
        roll_help.setObjectName("settingsHint")
        roll_help.setWordWrap(True)
        workflow_form.addRow("", roll_help)
        root.addWidget(workflow_group)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        save_button = buttons.button(QDialogButtonBox.Save)
        cancel_button = buttons.button(QDialogButtonBox.Cancel)
        save_button.setText("저장")
        save_button.setObjectName("primaryDialogButton")
        cancel_button.setText("취소")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        polish_combo_boxes(self, getattr(parent, "dark_mode", False))

    def values(self):
        roll_match = re.search(r"\d+", self.roll_count_combo.currentText())
        roll_count = int(roll_match.group()) if roll_match else 36
        roll_count = max(1, min(999, roll_count))
        return {
            "theme": self.theme_combo.currentData(),
            "thumbnail_size": self.thumbnail_combo.currentData(),
            "roll_base_count": roll_count,
            "default_sort": self.sort_combo.currentData(),
            "remember_last_folder": self.remember_checkbox.isChecked(),
        }

    @staticmethod
    def _style():
        return """
            QDialog { background: #f5efe6; color: #241b14; font-family: "Apple SD Gothic Neo", "Helvetica Neue", "Segoe UI"; font-size: 12px; }
            QLabel { background: transparent; }
            QGroupBox { background: rgba(234,224,211,.78); border: 1px solid #d8cab7; border-radius: 10px; margin-top: 12px; padding-top: 8px; font-weight: 850; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
            QComboBox { background: #fffaf1; color: #241b14; border: 1px solid #d4c6b3; border-radius: 7px; padding: 6px 9px; min-height: 20px; min-width: 220px; }
            QComboBox { padding-right: 40px; }
            QComboBox::drop-down { subcontrol-origin: border; subcontrol-position: top right; width: 36px; background: #ead2b3; border-left: 1px solid #b7824d; border-top-right-radius: 6px; border-bottom-right-radius: 6px; }
            QComboBox::drop-down:hover { background: #dcb785; border-left-color: #9e6837; }
            QComboBox::down-arrow { image: url(filmflipicons:chevron_down.svg); width: 13px; height: 13px; }
            QComboBox:hover, QComboBox:focus { background: #fff1dc; border-color: #c39158; }
            QComboBox QAbstractItemView { background: #fffaf1; color: #241b14; border: 1px solid #d4c6b3; selection-background-color: #ead6bc; selection-color: #241b14; }
            QComboBox QAbstractItemView::item { min-height: 26px; padding: 4px 8px; color: #241b14; }
            QComboBox QAbstractItemView::item:hover { background: #efdcc1; }
            QLabel#settingsHint { color: #765f49; font-size: 11px; padding-top: 2px; }
            QPushButton { background: #f7ead8; border: 1px solid #d2bc9e; border-radius: 9px; padding: 7px 14px; color: #2c2118; font-weight: 850; min-width: 92px; }
            QPushButton#primaryDialogButton { background: #ad4c2d; color: #fff4df; border-color: #81351f; }
        """
