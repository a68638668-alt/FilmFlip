from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from exif_utils import SUPPORTED_EXIF_SUFFIXES, read_exif
from utils.design import dialog_theme_override, icon_text_widget
from .common import FilmDateEdit


class ExifDialog(QDialog):
    """Edit only values that map to real JPEG EXIF tags."""

    FIELD_ROWS = [
        ("datetime_original", "촬영일", "calendar", "날짜 선택"),
        ("make", "카메라 제조사", "camera", "예: Nikon"),
        ("model", "카메라 모델", "camera", "예: Nikon FM2"),
        ("lens_model", "렌즈 모델", "lens", "예: Nikkor 50mm F1.4 AI"),
    ]

    EXPOSURE_ROWS = [
        ("iso", "ISO", "iso", "예: 400"),
        ("aperture", "조리개", "lens", "예: 1.4"),
        ("shutter_speed", "셔터 속도", "reverse", "예: 1/125"),
        ("focal_length", "초점 거리", "lens", "예: 50"),
    ]

    TEXT_ROWS = [
        ("artist", "촬영자", "camera", "예: 홍길동"),
        ("copyright", "저작권", "memo", "예: © 2026 FilmFlip"),
        ("description", "이미지 설명", "memo", "예: 남이섬 아침 스냅"),
        ("user_comment", "사용자 메모", "memo", "EXIF UserComment"),
    ]

    def __init__(self, images, parent=None):
        super().__init__(parent)
        self.images = [Path(image) for image in images]
        self.supported_images = [
            image for image in self.images
            if image.suffix.lower() in SUPPORTED_EXIF_SUFFIXES
        ]
        initial = read_exif(self.supported_images[0]) if self.supported_images else {}

        self.setWindowTitle("EXIF 정보 변경")
        self.resize(720, 760)
        self.setMinimumSize(680, 700)
        self.setStyleSheet(self._style() + dialog_theme_override(getattr(parent, "dark_mode", False)))

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(7)

        target_group = QGroupBox("적용 대상")
        target_layout = QHBoxLayout(target_group)
        target_layout.setContentsMargins(10, 8, 10, 8)
        target_layout.addWidget(icon_text_widget("현재 폴더", "folder", 24))
        folder_name = self.supported_images[0].parent.name if self.supported_images else "JPEG 없음"
        target_layout.addWidget(QLabel(folder_name), stretch=1)
        target_layout.addWidget(QLabel(f"JPEG {len(self.supported_images)}장 / 전체 {len(self.images)}장"))
        root.addWidget(target_group)

        self.edits = {}
        root.addWidget(self._field_group("카메라 및 촬영 정보", self.FIELD_ROWS, initial))
        root.addWidget(self._field_group("노출 정보", self.EXPOSURE_ROWS, initial))
        root.addWidget(self._field_group("저작권 및 설명", self.TEXT_ROWS, initial))

        options_group = QGroupBox("적용 옵션")
        options_layout = QVBoxLayout(options_group)
        options_layout.setContentsMargins(10, 8, 10, 8)
        options_layout.setSpacing(5)
        self.keep_blank_checkbox = QCheckBox("빈 칸은 기존 EXIF 값을 유지")
        self.keep_blank_checkbox.setChecked(True)
        options_layout.addWidget(self.keep_blank_checkbox)
        root.addWidget(options_group)

        note = QLabel("JPEG/JPG 파일의 실제 EXIF에 적용됩니다. PNG 등은 자동으로 건너뜁니다.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #7a6047; font-weight: 650; padding: 2px;")
        root.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_button = buttons.button(QDialogButtonBox.Ok)
        cancel_button = buttons.button(QDialogButtonBox.Cancel)
        ok_button.setText("EXIF 정보 적용")
        ok_button.setObjectName("primaryDialogButton")
        ok_button.setEnabled(bool(self.supported_images))
        cancel_button.setText("취소")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _field_group(self, title, rows, initial):
        group = QGroupBox(title)
        grid = QGridLayout(group)
        grid.setContentsMargins(10, 9, 10, 9)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)

        for row, (key, label, icon, placeholder) in enumerate(rows):
            if key == "datetime_original":
                edit = FilmDateEdit(initial.get(key, ""))
                edit.setObjectName("exifDateEdit")
            else:
                edit = QLineEdit(str(initial.get(key, "") or ""))
            edit.setPlaceholderText(placeholder)
            self.edits[key] = edit
            grid.addWidget(icon_text_widget(label, icon, 22), row, 0)
            grid.addWidget(edit, row, 1)
        return group

    def values(self):
        values = {key: edit.text().strip() for key, edit in self.edits.items()}
        values["keep_blank"] = self.keep_blank_checkbox.isChecked()
        return values

    @staticmethod
    def _style():
        return """
            QDialog { background: #f5efe6; color: #241b14; font-family: "Apple SD Gothic Neo", "Helvetica Neue", "Segoe UI"; font-size: 12px; }
            QLabel { background: transparent; }
            QGroupBox { background: rgba(234,224,211,.78); border: 1px solid #d8cab7; border-radius: 10px; margin-top: 12px; padding-top: 8px; font-weight: 850; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
            QLineEdit, QDateEdit { background: #fffaf1; color: #241b14; border: 1px solid #d4c6b3; border-radius: 7px; padding: 5px 8px; min-height: 20px; }
            QDateEdit#exifDateEdit { padding-right: 8px; }
            QDateEdit#exifDateEdit::drop-down { width: 34px; background: transparent; border: 0px; }
            QDateEdit#exifDateEdit::down-arrow { image: none; width: 0px; height: 0px; }
            QLineEdit:hover, QLineEdit:focus, QDateEdit:hover, QDateEdit:focus { background: #fff1dc; border-color: #c39158; }
            QCheckBox { background: transparent; border: 0px; padding: 3px; }
            QPushButton { background: #f7ead8; border: 1px solid #d2bc9e; border-radius: 9px; padding: 7px 14px; color: #2c2118; font-weight: 850; min-width: 92px; }
            QPushButton#primaryDialogButton { background: #ad4c2d; color: #fff4df; border-color: #81351f; min-width: 145px; }
        """
