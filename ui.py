from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QFileDialog,
    QMessageBox,
    QTableWidgetItem,
    QHBoxLayout,
)

from dragdrop import ImageTable
from engine import find_images, build_preview


class FilmFlipWindow(QWidget):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("🎞 FilmFlip v0.6")
        self.resize(800, 600)

        self.setAcceptDrops(True)

        self.images = []

        layout = QVBoxLayout()

        title = QLabel("🎞 FilmFlip")
        title.setStyleSheet("""
            font-size:30px;
            font-weight:bold;
        """)

        subtitle = QLabel("필름 스캔 파일 역순 정렬")

        self.button = QPushButton("📂 폴더 선택")
        self.button.setMinimumHeight(45)
        self.button.clicked.connect(self.select_folder)

        self.info = QLabel(
            "폴더를 선택하거나 폴더를 이 창으로 드래그하세요."
        )

        self.table = ImageTable()
        self.table.orderChanged.connect(self.refresh_preview)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(10)
        layout.addWidget(self.button)
        layout.addWidget(self.info)
        layout.addWidget(self.table)

        self.setLayout(layout)

    def load_folder(self, folder):

        self.images = find_images(folder)

        self.refresh_preview()

        if len(self.images) == 0:
            QMessageBox.information(
                self,
                "FilmFlip",
                "이미지가 없습니다.",
            )

    def refresh_preview(self):

        preview = build_preview(self.images)

        self.table.setRowCount(len(preview))

        for row, (_, old_name, new_name) in enumerate(preview):

            self.table.setItem(
                row,
                0,
                QTableWidgetItem(old_name),
            )

            self.table.setItem(
                row,
                1,
                QTableWidgetItem(new_name),
            )

        self.info.setText(
            f"📷 {len(preview)}개의 이미지를 찾았습니다."
        )

    def select_folder(self):

        folder = QFileDialog.getExistingDirectory(
            self,
            "폴더 선택",
        )

        if not folder:
            return

        self.load_folder(folder)

    def dragEnterEvent(self, event):

        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()

            if len(urls) == 1 and urls[0].isLocalFile():
                event.acceptProposedAction()
                return

        event.ignore()

    def dragMoveEvent(self, event):

        event.acceptProposedAction()

    def dropEvent(self, event):

        import os

        url = event.mimeData().urls()[0]
        folder = url.toLocalFile()

        if os.path.isdir(folder):
            self.load_folder(folder)
        else:
            QMessageBox.warning(
                self,
                "FilmFlip",
                "폴더만 드롭할 수 있습니다.",
            )

        event.acceptProposedAction()