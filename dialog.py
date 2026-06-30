
from PySide6.QtWidgets import (
    QMessageBox,
    QDialog,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QDialogButtonBox,
)


class RenameDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Rename Options")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("파일명 형식"))

        self.template_edit = QLineEdit("{n}")
        layout.addWidget(self.template_edit)

        self.reverse_radio = QRadioButton("역순 (FilmFlip 기본)")
        self.reverse_radio.setChecked(True)

        self.normal_radio = QRadioButton("현재 순서 유지")

        layout.addWidget(self.reverse_radio)
        layout.addWidget(self.normal_radio)

        self.example = QLabel("예시\n001.jpg\n002.jpg\n003.jpg")
        layout.addWidget(self.example)

        self.template_edit.textChanged.connect(self.update_preview)
        self.reverse_radio.toggled.connect(self.update_preview)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addWidget(buttons)

        self.update_preview()

    def update_preview(self):
        template = self.template_edit.text().strip() or "{n}"

        if "{n}" not in template:
            self.example.setText("⚠️ {n}을 포함해야 합니다.")
            return

        nums = ["003","002","001"] if self.reverse_radio.isChecked() else ["001","002","003"]
        self.example.setText(
            "예시\n" + "\n".join(template.replace("{n}",n)+".jpg" for n in nums)
        )

    def values(self):
        return {
            "template": self.template_edit.text().strip() or "{n}",
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
    QMessageBox.information(parent,"FilmFlip",f"✅ {count}개의 파일명을 변경했습니다.")


def no_images(parent):
    QMessageBox.information(parent,"FilmFlip","이미지가 없습니다.")


def rename_failed(parent,error):
    QMessageBox.critical(parent,"FilmFlip",f"오류가 발생했습니다.\n\n{error}")
