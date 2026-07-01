from pathlib import Path
import sys
from PySide6.QtCore import Qt, QSize, QTimer, QUrl, Signal
from PySide6.QtGui import QPixmap, QIcon, QGuiApplication, QImageReader, QDesktopServices
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
    QApplication,
    QComboBox,
    QFrame,
    QAbstractItemView,
)

from dragdrop import ImageTable
import engine
from engine import find_images, build_preview, rename_images, undo_rename, rename_folder, undo_folder
from settings import load_settings, save_settings

from dialog import (
    RenameDialog,
    FolderRenameDialog,
    rename_finished,
    rename_failed,
)


THUMBNAIL_SIZE = QSize(140, 105)
ROW_HEIGHT = 122
THUMBNAIL_BATCH_SIZE = 1

THUMBNAIL_PRESETS = {
    "small": {
        "label": "작게",
        "size": QSize(110, 82),
        "row_height": 98,
        "column_width": 126,
    },
    "medium": {
        "label": "보통",
        "size": QSize(140, 105),
        "row_height": 122,
        "column_width": 156,
    },
    "large": {
        "label": "크게",
        "size": QSize(170, 128),
        "row_height": 148,
        "column_width": 186,
    },
}
DEFAULT_THUMBNAIL_PRESET = "medium"


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
            pixmap = QPixmap(str(image))
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


class FolderStatusLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
            return

        super().mousePressEvent(event)


class FilmFlipWindow(QWidget):

    def __init__(self):
        super().__init__()

        self.settings = load_settings()

        self.setWindowTitle("🎞 FilmFlip v1.2")
        self.resize(900, 650)
        self.setAcceptDrops(True)

        self.images = []
        self.current_folder = None
        self.thumbnail_cache = {}
        self.thumbnail_queue = []
        self.thumbnail_generation = 0

        self.thumbnail_timer = QTimer(self)
        self.thumbnail_timer.setInterval(12)
        self.thumbnail_timer.timeout.connect(self.process_thumbnail_queue)

        self.thumbnail_preset_key = self.settings.get(
            "thumbnail_size",
            DEFAULT_THUMBNAIL_PRESET,
        )
        if self.thumbnail_preset_key not in THUMBNAIL_PRESETS:
            self.thumbnail_preset_key = DEFAULT_THUMBNAIL_PRESET

        self.apply_thumbnail_preset(self.thumbnail_preset_key, save=False)

        layout = QVBoxLayout()

        title = QLabel("🎞 FilmFlip")
        title.setStyleSheet(
            """
            font-size:30px;
            font-weight:bold;
            """
        )

        subtitle = QLabel("필름스캔 파일정리 도구")

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

        # 상단 작업 버튼은 썸네일 설정 영역 전까지 자연스럽게 닿도록
        # 고정 폭을 조금 넓혀 배치한다.
        for top_button in [
            self.button,
            self.reverse_button,
            self.rename_button,
        ]:
            top_button.setFixedWidth(200)
            top_button.setSizePolicy(
                QSizePolicy.Fixed,
                QSizePolicy.Fixed,
            )

        self.undo_button.setFixedWidth(180)
        self.undo_button.setSizePolicy(
            QSizePolicy.Fixed,
            QSizePolicy.Fixed,
        )

        self.info = QLabel(
            "폴더를 선택하거나 폴더를 이 창으로 드래그하세요."
        )

        self.table = ImageTable()
        self.apply_thumbnail_table_settings()
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.verticalScrollBar().setSingleStep(36)
        self.table.orderChanged.connect(self.sync_order)
        self.table.cellDoubleClicked.connect(self.open_preview_from_row)
        self.table.rowDoubleClicked.connect(self.open_preview_from_row_only)

        buttons = QHBoxLayout()
        buttons.setSpacing(16)
        buttons.addWidget(self.button)
        buttons.addWidget(self.reverse_button)
        buttons.addWidget(self.rename_button)
        buttons.addWidget(self.undo_button)
        buttons.addStretch(1)

        self.thumbnail_combo = QComboBox()
        self.thumbnail_combo.setMaximumWidth(90)
        self.thumbnail_combo.setToolTip("썸네일 크기를 변경합니다.")
        for key, preset in THUMBNAIL_PRESETS.items():
            self.thumbnail_combo.addItem(preset["label"], key)
        current_index = self.thumbnail_combo.findData(self.thumbnail_preset_key)
        if current_index >= 0:
            self.thumbnail_combo.setCurrentIndex(current_index)
        self.thumbnail_combo.currentIndexChanged.connect(self.change_thumbnail_preset)

        thumbnail_label = QLabel("썸네일")
        buttons.addWidget(thumbnail_label)
        buttons.addWidget(self.thumbnail_combo)

        self.status_bar = QFrame()
        self.status_bar.setFrameShape(QFrame.StyledPanel)
        self.status_bar.setMinimumHeight(34)

        status_layout = QHBoxLayout(self.status_bar)
        status_layout.setContentsMargins(10, 4, 10, 4)

        self.folder_status = FolderStatusLabel()
        self.folder_status.setTextInteractionFlags(Qt.NoTextInteraction)
        self.folder_status.setCursor(Qt.PointingHandCursor)
        self.folder_status.clicked.connect(self.open_current_folder)
        self.folder_status.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Preferred,
        )

        self.count_status = QLabel()
        self.count_status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.folder_rename_button = QPushButton("폴더명 변경")
        self.folder_rename_button.setEnabled(False)
        self.folder_rename_button.setToolTip("현재 선택한 폴더 이름을 메타데이터 기준으로 변경합니다.")
        self.folder_rename_button.clicked.connect(self.rename_current_folder)

        status_layout.addWidget(self.folder_status, stretch=1)
        status_layout.addWidget(self.folder_rename_button)
        status_layout.addWidget(self.count_status)
        self.update_status_bar()

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(10)
        layout.addLayout(buttons)
        layout.addWidget(self.info)
        layout.addWidget(self.table)
        layout.addWidget(self.status_bar)

        self.setLayout(layout)

    def apply_thumbnail_preset(self, preset_key, save=True):
        preset = THUMBNAIL_PRESETS.get(
            preset_key,
            THUMBNAIL_PRESETS[DEFAULT_THUMBNAIL_PRESET],
        )

        self.thumbnail_preset_key = preset_key
        self.thumbnail_size = preset["size"]
        self.row_height = preset["row_height"]
        self.thumbnail_column_width = preset["column_width"]

        if save:
            self.settings["thumbnail_size"] = preset_key
            save_settings(self.settings)

    def apply_thumbnail_table_settings(self):
        if not hasattr(self, "table"):
            return

        self.table.setUpdatesEnabled(False)
        try:
            self.table.setIconSize(self.thumbnail_size)
            self.table.setColumnWidth(0, self.thumbnail_column_width)
            self.table.ROW_HEIGHT = self.row_height
            self.table.THUMBNAIL_COLUMN_WIDTH = self.thumbnail_column_width

            vertical_header = self.table.verticalHeader()
            vertical_header.setDefaultSectionSize(self.row_height)
            vertical_header.setMinimumSectionSize(self.row_height)

            for row in range(self.table.rowCount()):
                self.table.setRowHeight(row, self.row_height)
        finally:
            self.table.setUpdatesEnabled(True)

    def change_thumbnail_preset(self, _index):
        preset_key = self.thumbnail_combo.currentData()
        if not preset_key or preset_key == self.thumbnail_preset_key:
            return

        self.apply_thumbnail_preset(preset_key)
        self.apply_thumbnail_table_settings()

        if self.images:
            self.refresh_preview()

    def update_status_bar(self):
        if self.current_folder is None:
            self.folder_status.setText("📂 현재 폴더: 없음")
            self.folder_status.setToolTip("폴더를 선택하면 전체 경로가 표시됩니다.")
            self.count_status.setText("")
            if hasattr(self, "folder_rename_button"):
                self.folder_rename_button.setEnabled(False)
            return

        self.folder_status.setText(f"📂 현재 폴더: {self.current_folder.name}")
        self.folder_status.setToolTip(str(self.current_folder))
        self.count_status.setText(f"📸 {len(self.images)}장")
        if hasattr(self, "folder_rename_button"):
            self.folder_rename_button.setEnabled(True)

    def open_current_folder(self):
        if self.current_folder is None:
            return

        if not self.current_folder.exists():
            QMessageBox.warning(
                self,
                "FilmFlip",
                "현재 폴더를 찾을 수 없습니다.",
            )
            return

        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.current_folder))
        )

    def mark_rename_completed(self):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 2)
            if item is None:
                item = QTableWidgetItem()
                self.table.setItem(row, 2, item)

            item.setText("✔ 변경 완료")
            item.setTextAlignment(Qt.AlignCenter)

    def load_folder(self, folder):
        self.cancel_thumbnail_loading()
        self.current_folder = Path(folder)
        self.update_status_bar()
        self.info.setText("📂 폴더를 읽는 중입니다...")
        self.set_controls_enabled(False)
        QApplication.processEvents()

        try:
            self.images = find_images(folder)
        finally:
            self.set_controls_enabled(True)

        self.thumbnail_cache = {}
        self.refresh_preview()
        self.update_status_bar()

        enabled = len(self.images) > 0
        self.reverse_button.setEnabled(enabled)
        self.rename_button.setEnabled(enabled)

        if not enabled:
            QMessageBox.information(
                self,
                "FilmFlip",
                "이미지가 없습니다.",
            )

    def set_controls_enabled(self, enabled):
        self.button.setEnabled(enabled)
        self.reverse_button.setEnabled(enabled and len(self.images) > 0)
        self.rename_button.setEnabled(enabled and len(self.images) > 0)
        self.undo_button.setEnabled(enabled and self.undo_button.isEnabled())

    def cancel_thumbnail_loading(self):
        self.thumbnail_generation += 1
        self.thumbnail_queue = []

        if self.thumbnail_timer.isActive():
            self.thumbnail_timer.stop()

    def placeholder_thumbnail_item(self, image):
        item = QTableWidgetItem("로딩 중")
        item.setData(Qt.UserRole, str(image))
        item.setTextAlignment(Qt.AlignCenter)
        return item

    def cached_thumbnail_item(self, image):
        item = QTableWidgetItem()
        item.setData(Qt.UserRole, str(image))
        item.setTextAlignment(Qt.AlignCenter)

        pixmap = self.thumbnail_cache.get(self.thumbnail_cache_key(image))

        if pixmap is not None and not pixmap.isNull():
            item.setIcon(QIcon(pixmap))
        else:
            item.setText("이미지")

        return item

    def thumbnail_cache_key(self, image):
        return f"{self.thumbnail_size.width()}x{self.thumbnail_size.height()}:{image}"

    def make_thumbnail(self, image):
        image_path = str(image)
        cache_key = self.thumbnail_cache_key(image)
        pixmap = self.thumbnail_cache.get(cache_key)

        if pixmap is not None:
            return pixmap

        # v1.1 성능/화질 보정:
        # QPixmap 원본 전체 로딩 후 FastTransformation으로 줄이면 빠르지만
        # 작은 썸네일에서 화질이 크게 무너질 수 있다.
        # QImageReader로 필요한 크기 근처까지 줄여 읽고, 마지막 축소는
        # SmoothTransformation으로 처리해서 체감 속도와 품질을 같이 잡는다.
        reader = QImageReader(image_path)
        reader.setAutoTransform(True)

        original_size = reader.size()
        if original_size.isValid():
            scaled_size = original_size.scaled(
                self.thumbnail_size * 2,
                Qt.KeepAspectRatio,
            )
            reader.setScaledSize(scaled_size)

        image_data = reader.read()

        if image_data.isNull():
            pixmap = QPixmap(image_path)
        else:
            pixmap = QPixmap.fromImage(image_data)

        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                self.thumbnail_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )

        self.thumbnail_cache[cache_key] = pixmap
        return pixmap

    def start_thumbnail_loading(self):
        self.cancel_thumbnail_loading()

        generation = self.thumbnail_generation
        self.thumbnail_queue = [
            (generation, row, image)
            for row, image in enumerate(self.images)
        ]

        if self.thumbnail_queue:
            self.thumbnail_timer.start()

    def process_thumbnail_queue(self):
        if not self.thumbnail_queue:
            self.thumbnail_timer.stop()
            return

        current_generation = self.thumbnail_generation
        processed = 0

        while self.thumbnail_queue and processed < THUMBNAIL_BATCH_SIZE:
            generation, row, image = self.thumbnail_queue.pop(0)

            if generation != current_generation:
                continue

            if row < 0 or row >= self.table.rowCount():
                continue

            item = self.table.item(row, 0)

            if item is None:
                continue

            if item.data(Qt.UserRole) != str(image):
                continue

            pixmap = self.make_thumbnail(image)

            if pixmap is not None and not pixmap.isNull():
                item.setText("")
                item.setIcon(QIcon(pixmap))
            else:
                item.setText("이미지")

            self.table.setRowHeight(row, self.row_height)
            processed += 1

        if not self.thumbnail_queue:
            self.thumbnail_timer.stop()

    def refresh_preview(self):
        """
        self.images를 기준으로 테이블을 다시 그린다.
        현재 파일명 컬럼에는 실제 원본 파일 경로를 UserRole에 저장해서
        순서 동기화가 표시 텍스트와 섞이지 않게 한다.

        v1.1 성능 개선:
        - 테이블 텍스트를 먼저 빠르게 표시한다.
        - 썸네일은 QTimer로 조금씩 나눠 생성해 폴더 열기 체감 멈춤을 줄인다.
        - 전체 테이블 갱신 중에는 repaint를 잠시 막아 깜빡임과 버벅임을 줄인다.
        """

        self.cancel_thumbnail_loading()

        self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)

        try:
            preview = build_preview(self.images)
            self.table.setRowCount(len(preview))

            for row, (image, old_name, new_name) in enumerate(preview):
                self.table.setRowHeight(row, self.row_height)

                self.table.setItem(
                    row,
                    0,
                    self.placeholder_thumbnail_item(image),
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

        finally:
            self.table.setUpdatesEnabled(True)
            self.table.blockSignals(False)

        self.start_thumbnail_loading()

        if not self.images:
            self.info.setText("이미지가 없습니다.")

        self.update_status_bar()

    def sync_order(self):
        """
        테이블에서 사용자가 바꾼 행 순서를 self.images에 반영한다.
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

            # 행 이동 직후 전체 테이블을 다시 그리지 않는다.
            # macOS/Windows 모두에서 드래그/이동 후 줄어드는 행 높이만 복구한다.
            self.table.setUpdatesEnabled(False)
            try:
                for row in range(self.table.rowCount()):
                    self.table.setRowHeight(row, self.row_height)
            finally:
                self.table.setUpdatesEnabled(True)

    def open_preview_from_row_only(self, row):
        self.open_preview_from_row(row, 0)

    def open_preview_from_row(self, row, _column):
        if row < 0 or row >= len(self.images):
            return

        dialog = ImagePreviewDialog(
            self.images,
            row,
            self,
        )
        dialog.exec()

    def rename_current_folder(self):
        if self.current_folder is None:
            return

        dialog = FolderRenameDialog(self.current_folder, self)

        if dialog.exec() != QDialog.Accepted:
            return

        options = dialog.values()
        new_name = options.get("template", "").strip()

        if not new_name:
            QMessageBox.warning(
                self,
                "FilmFlip",
                "새 폴더명이 비어 있습니다.",
            )
            return

        if new_name == self.current_folder.name:
            QMessageBox.information(
                self,
                "FilmFlip",
                "현재 폴더명과 같습니다.",
            )
            return

        reply = QMessageBox.question(
            self,
            "FilmFlip",
            f"폴더명을 변경할까요?\n\n{self.current_folder.name}\n→ {new_name}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        try:
            new_folder = rename_folder(self.current_folder, new_name)
            self.current_folder = new_folder
            self.settings["last_folder"] = str(new_folder)
            save_settings(self.settings)
            self.load_folder(new_folder)
            self.mark_rename_completed()
            self.info.setText(f"✔ 폴더명 변경 완료: {new_folder.name}")
            self.undo_button.setEnabled(True)

        except Exception as error:
            rename_failed(self, str(error))

    def reverse_rename(self):
        preview = build_preview(self.images)

        if not preview:
            return

        try:
            rename_images(preview)
            rename_finished(self, len(preview))
            self.load_folder(preview[0][0].parent)
            self.mark_rename_completed()
            self.info.setText(f"✔ 파일 이름 변경 완료 ({len(preview)}개)")
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
            self.mark_rename_completed()
            self.info.setText(f"✔ 파일 이름 변경 완료 ({len(preview)}개)")
            self.undo_button.setEnabled(True)

        except Exception as error:
            rename_failed(self, str(error))

    def undo_last(self):
        has_file_undo = bool(engine.LAST_UNDO)
        has_folder_undo = bool(getattr(engine, "LAST_FOLDER_UNDO", None))

        if not has_file_undo and not has_folder_undo:
            return

        try:
            if has_folder_undo:
                restored_folder = undo_folder(engine.LAST_FOLDER_UNDO)
                engine.LAST_FOLDER_UNDO = None
                self.undo_button.setEnabled(False)

                if restored_folder is not None:
                    self.current_folder = restored_folder
                    self.settings["last_folder"] = str(restored_folder)
                    save_settings(self.settings)
                    self.load_folder(restored_folder)
                    self.info.setText(f"↩ 폴더명 Undo 완료: {restored_folder.name}")
                return

            if not self.images:
                return

            folder = self.images[0].parent
            undo_rename(folder, engine.LAST_UNDO)
            engine.LAST_UNDO = []
            self.undo_button.setEnabled(False)
            self.load_folder(folder)
            self.info.setText("↩ 파일명 Undo 완료")

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
            self.settings["last_folder"] = folder
            save_settings(self.settings)
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
