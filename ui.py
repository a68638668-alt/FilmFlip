from pathlib import Path
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QFileDialog,
    QMessageBox,
    QTableWidgetItem,
    QHBoxLayout,
    QDialog,
    QSizePolicy,
)

from dragdrop import ImageTable
import engine
from engine import find_images, build_preview, rename_images, undo_rename
from settings import load_settings, save_settings

from dialog import (
    RenameDialog,
    rename_finished,
    rename_failed,
)


class ImagePreviewDialog(QDialog):

    def __init__(self, images, index=0, parent=None):
        super().__init__(parent)

        self.images = images
        self.index = max(0, min(index, len(images) - 1))
        self.pixmap_cache = {}

        self.setWindowTitle("FilmFlip Preview")
        BASE_DIR = Path(__file__).resolve().parent
        if sys.platform == "darwin":
            self.setWindowIcon(QIcon(str(BASE_DIR / "assets" / "icon.icns")))
        else:
            self.setWindowIcon(QIcon(str(BASE_DIR / "assets" / "icon.ico")))
        self.resize(1000, 750)

        layout = QVBoxLayout()

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(600, 450)
        self.image_label.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )

        self.name_label = QLabel()
        self.name_label.setAlignment(Qt.AlignCenter)

        self.help_label = QLabel(
            "←/→ 이전·다음   |   ESC 닫기"
        )
        self.help_label.setAlignment(Qt.AlignCenter)
        self.help_label.setStyleSheet("color: #888;")

        layout.addWidget(self.image_label, stretch=1)
        layout.addWidget(self.name_label)
        layout.addWidget(self.help_label)

        self.setLayout(layout)
        self.update_image()

    def current_image(self):
        if not self.images:
            return None

        return self.images[self.index]

    def original_pixmap(self, image):
        cache_key = str(image)
        pixmap = self.pixmap_cache.get(cache_key)

        if pixmap is None:
            pixmap = QPixmap(cache_key)
            self.pixmap_cache[cache_key] = pixmap

        return pixmap

    def update_image(self):
        image = self.current_image()

        if image is None:
            return

        pixmap = self.original_pixmap(image)

        if pixmap.isNull():
            self.image_label.setText("이미지를 불러올 수 없습니다.")
            self.name_label.setText(image.name)
            return

        target_size = self.image_label.size()

        if target_size.width() <= 0 or target_size.height() <= 0:
            target_size = QSize(900, 650)

        scaled = pixmap.scaled(
            target_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )

        self.image_label.setPixmap(scaled)
        self.name_label.setText(
            f"{self.index + 1} / {len(self.images)}   {image.name}"
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_image()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            return

        if event.key() == Qt.Key_Right:
            if self.images:
                self.index = (self.index + 1) % len(self.images)
                self.update_image()
            return

        if event.key() == Qt.Key_Left:
            if self.images:
                self.index = (self.index - 1) % len(self.images)
                self.update_image()
            return

        super().keyPressEvent(event)


class FilmFlipWindow(QWidget):

    def __init__(self):
        super().__init__()

        self.settings = load_settings()

        self.setWindowTitle("🎞 FilmFlip v1.0")
        self.resize(900, 650)
        self.setAcceptDrops(True)

        self.images = []
        self.thumbnail_cache = {}

        layout = QVBoxLayout()

        title = QLabel("🎞 FilmFlip")
        title.setStyleSheet(
            """
            font-size:30px;
            font-weight:bold;
            """
        )

        subtitle = QLabel("필름 스캔 파일 역순 정렬")

        self.button = QPushButton("📂 폴더 선택")
        self.button.setMinimumHeight(45)
        self.button.clicked.connect(self.select_folder)

        self.reverse_button = QPushButton("🔄 역순 변경")
        self.reverse_button.setMinimumHeight(45)
        self.reverse_button.setEnabled(False)
        self.reverse_button.clicked.connect(self.reverse_rename)

        self.rename_button = QPushButton("✏️ 이름 변경")
        self.rename_button.setMinimumHeight(45)
        self.rename_button.setEnabled(False)
        self.rename_button.clicked.connect(self.rename_files)

        self.undo_button = QPushButton("↩ Undo")
        self.undo_button.setMinimumHeight(45)
        self.undo_button.setEnabled(False)
        self.undo_button.clicked.connect(self.undo_last)

        self.info = QLabel(
            "폴더를 선택하거나 폴더를 이 창으로 드래그하세요."
        )

        self.table = ImageTable()
        self.table.setColumnWidth(0, 156)
        self.table.setIconSize(QSize(140, 105))
        self.table.orderChanged.connect(self.sync_order)
        self.table.cellDoubleClicked.connect(self.open_preview_from_row)

        buttons = QHBoxLayout()
        buttons.addWidget(self.button)
        buttons.addWidget(self.reverse_button)
        buttons.addWidget(self.rename_button)
        buttons.addWidget(self.undo_button)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(10)
        layout.addLayout(buttons)
        layout.addWidget(self.info)
        layout.addWidget(self.table)

        self.setLayout(layout)

    def load_folder(self, folder):
        self.images = find_images(folder)
        self.thumbnail_cache = {}
        self.refresh_preview()

        enabled = len(self.images) > 0
        self.reverse_button.setEnabled(enabled)
        self.rename_button.setEnabled(enabled)

        if not enabled:
            QMessageBox.information(
                self,
                "FilmFlip",
                "이미지가 없습니다.",
            )

    def thumbnail_item(self, image):
        cache_key = str(image)
        pixmap = self.thumbnail_cache.get(cache_key)

        if pixmap is None:
            pixmap = QPixmap(cache_key)

            if not pixmap.isNull():
                pixmap = pixmap.scaled(QSize(140, 105),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )

            self.thumbnail_cache[cache_key] = pixmap

        item = QTableWidgetItem()
        item.setData(Qt.UserRole, str(image))

        if pixmap is not None and not pixmap.isNull():
            item.setIcon(QIcon(pixmap))
        else:
            item.setText("이미지")

        return item

    def refresh_preview(self):
        """
        self.images를 기준으로 테이블을 다시 그린다.
        현재 파일명 컬럼에는 실제 원본 파일 경로를 UserRole에 저장해서
        드래그 후 순서 동기화가 표시 텍스트와 섞이지 않게 한다.
        """

        self.table.blockSignals(True)

        preview = build_preview(self.images)
        self.table.setRowCount(len(preview))

        for row, (image, old_name, new_name) in enumerate(preview):
            self.table.setRowHeight(row, 122)

            self.table.setItem(
                row,
                0,
                self.thumbnail_item(image),
            )

            old_item = QTableWidgetItem(
                f"{row + 1}. {old_name}"
            )
            old_item.setData(Qt.UserRole, str(image))

            new_item = QTableWidgetItem(new_name)
            new_item.setData(Qt.UserRole, str(image))

            self.table.setItem(row, 1, old_item)
            self.table.setItem(row, 2, new_item)

        self.info.setText(
            f"📷 {len(preview)}개의 이미지를 찾았습니다."
        )

        self.table.blockSignals(False)

    def sync_order(self):
        """
        테이블에서 사용자가 드래그로 바꾼 행 순서를 self.images에 반영한다.
        표시 텍스트가 아니라 Qt.UserRole에 저장한 실제 파일 경로로 매칭한다.
        """

        path_map = {
            str(image): image
            for image in self.images
        }

        new_images = []

        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)

            if item is None:
                continue

            image_path = item.data(Qt.UserRole)

            if image_path in path_map:
                new_images.append(path_map[image_path])

        if len(new_images) == len(self.images):
            self.images = new_images
            # 드래그 직후에는 테이블을 다시 그리지 않아 반응속도를 유지한다.

    def open_preview_from_row(self, row, _column):
        if row < 0 or row >= len(self.images):
            return

        dialog = ImagePreviewDialog(
            self.images,
            row,
            self,
        )
        dialog.exec()

    def reverse_rename(self):
        preview = build_preview(self.images)

        if not preview:
            return

        try:
            rename_images(preview)
            rename_finished(self, len(preview))
            self.load_folder(preview[0][0].parent)
            self.undo_button.setEnabled(True)

        except Exception as error:
            rename_failed(self, str(error))

    def rename_files(self):
        dialog = RenameDialog(self)

        if dialog.exec() != QDialog.Accepted:
            return

        options = dialog.values()

        preview = build_preview(
            self.images,
            template=options["template"],
            reverse=options["reverse"],
        )

        if not preview:
            return

        try:
            rename_images(preview)
            rename_finished(self, len(preview))
            self.load_folder(preview[0][0].parent)
            self.undo_button.setEnabled(True)

        except Exception as error:
            rename_failed(self, str(error))

    def undo_last(self):
        if not self.images or not engine.LAST_UNDO:
            return

        try:
            folder = self.images[0].parent
            undo_rename(folder, engine.LAST_UNDO)
            self.undo_button.setEnabled(False)
            self.load_folder(folder)

        except Exception as error:
            rename_failed(self, str(error))

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "폴더 선택",
        )

        if not folder:
            return

        self.settings["last_folder"] = folder
        save_settings(self.settings)

        self.load_folder(folder)
        self.undo_button.setEnabled(False)

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

        urls = event.mimeData().urls()

        if not urls:
            event.ignore()
            return

        folder = urls[0].toLocalFile()

        if os.path.isdir(folder):
            self.load_folder(folder)
            self.undo_button.setEnabled(False)
            event.acceptProposedAction()
            return

        QMessageBox.warning(
            self,
            "FilmFlip",
            "폴더만 드롭할 수 있습니다.",
        )
        event.ignore()
