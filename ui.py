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

        self.setWindowTitle("FilmFlip v2.0-dev")
        self.resize(1280, 760)
        self.setMinimumSize(1120, 680)
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

        self.apply_v2_style()

        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(18, 18, 18, 16)
        root_layout.setSpacing(14)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(14)

        brand_layout = QHBoxLayout()
        brand_layout.setSpacing(12)

        logo = QLabel("🎞")
        logo.setFixedSize(58, 58)
        logo.setAlignment(Qt.AlignCenter)
        logo.setObjectName("logoBadge")

        brand_text = QVBoxLayout()
        brand_text.setSpacing(2)
        title = QLabel("FilmFlip")
        title.setObjectName("appTitle")
        subtitle = QLabel("필름 스캔 파일 관리 도구")
        subtitle.setObjectName("appSubtitle")
        brand_text.addWidget(title)
        brand_text.addWidget(subtitle)

        brand_layout.addWidget(logo)
        brand_layout.addLayout(brand_text)
        top_layout.addLayout(brand_layout)
        top_layout.addStretch(1)

        self.button = self.create_toolbar_button("📁", "폴더 선택", "폴더를 선택하세요")
        self.button.clicked.connect(self.select_folder)

        self.reverse_button = self.create_toolbar_button("↻", "역순 변경", "현재: 역순 정렬")
        self.reverse_button.setEnabled(False)
        self.reverse_button.clicked.connect(self.reverse_rename)

        self.rename_button = self.create_toolbar_button("✎", "이름 변경", "파일명 및 폴더명 변경")
        self.rename_button.setEnabled(False)
        self.rename_button.clicked.connect(self.rename_files)

        self.undo_button = self.create_toolbar_button("↩", "Undo", "마지막 작업 취소")
        self.undo_button.setEnabled(False)
        self.undo_button.clicked.connect(self.undo_last)

        for top_button in [
            self.button,
            self.reverse_button,
            self.rename_button,
            self.undo_button,
        ]:
            top_layout.addWidget(top_button)

        main_layout = QHBoxLayout()
        main_layout.setSpacing(16)

        left_panel = self.create_left_panel()
        center_panel = self.create_center_panel()
        right_panel = self.create_right_panel()

        main_layout.addWidget(left_panel)
        main_layout.addWidget(center_panel, stretch=1)
        main_layout.addWidget(right_panel)

        root_layout.addLayout(top_layout)
        root_layout.addLayout(main_layout, stretch=1)

        self.setLayout(root_layout)
        self.update_status_bar()
        self.update_side_panels()

    def apply_v2_style(self):
        self.setStyleSheet(
            """
            QWidget {
                background: #f4efe4;
                color: #2f261b;
                font-size: 14px;
            }
            QLabel#appTitle {
                font-size: 34px;
                font-weight: 800;
                color: #20170f;
            }
            QLabel#appSubtitle {
                color: #6f614f;
                font-size: 14px;
            }
            QLabel#logoBadge {
                background: #efe4d2;
                border: 1px solid #ddcfbb;
                border-radius: 14px;
                font-size: 30px;
            }
            QFrame#darkPanel {
                background: #242218;
                border: 1px solid #3a3526;
                border-radius: 8px;
            }
            QFrame#lightCard {
                background: #fbf6eb;
                border: 1px solid #ded2bf;
                border-radius: 8px;
            }
            QFrame#softCard {
                background: #f0e3cf;
                border: 1px solid #dccab0;
                border-radius: 8px;
            }
            QLabel#sectionTitle {
                font-size: 18px;
                font-weight: 700;
                color: #4c3725;
            }
            QLabel#darkTitle {
                color: #ead7ba;
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#darkLabel {
                color: #b9a98f;
                font-size: 12px;
            }
            QLabel#darkValue {
                color: #fff8eb;
                font-size: 14px;
                font-weight: 600;
            }
            QLabel#smallMuted {
                color: #7e705d;
                font-size: 12px;
            }
            QLabel#rollCard {
                background: #efe1c5;
                color: #7a4f2b;
                border: 1px solid #d4b98d;
                border-radius: 6px;
                font-family: Georgia, Times New Roman, serif;
                font-size: 22px;
                font-weight: 700;
                padding: 10px;
            }
            QPushButton {
                background: #f3eadc;
                border: 1px solid #d9c7ad;
                border-radius: 8px;
                padding: 8px 12px;
                color: #3a2c1e;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #eadbc5;
            }
            QPushButton:disabled {
                color: #aa9f91;
                background: #eee6d8;
            }
            QPushButton#toolbarButton {
                min-width: 150px;
                min-height: 58px;
                text-align: left;
            }
            QPushButton#primaryButton {
                background: #a94e2f;
                color: #fff7e8;
                border: 1px solid #8f3e25;
                font-size: 16px;
                font-weight: 800;
            }
            QPushButton#darkButton {
                background: #2b281e;
                color: #fff3da;
                border: 1px solid #4a432f;
            }
            QComboBox {
                background: #f7efe2;
                border: 1px solid #d6c7b2;
                border-radius: 6px;
                padding: 5px 8px;
            }
            QTableWidget {
                background: #242218;
                color: #f6eddb;
                gridline-color: #373326;
                border: 1px solid #373326;
                border-radius: 8px;
                selection-background-color: #403928;
                selection-color: #fff4df;
            }
            QHeaderView::section {
                background: #242218;
                color: #ead7ba;
                border: 0px;
                border-bottom: 1px solid #3a3526;
                padding: 8px;
                font-weight: 700;
            }
            QScrollBar:vertical {
                background: #2a271d;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #817662;
                min-height: 34px;
                border-radius: 6px;
            }
            """
        )

    def create_toolbar_button(self, icon, title, subtitle):
        button = QPushButton(f"{icon}  {title}\n   {subtitle}")
        button.setObjectName("toolbarButton")
        button.setMinimumHeight(62)
        button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        return button

    def create_left_panel(self):
        panel = QFrame()
        panel.setObjectName("darkPanel")
        panel.setFixedWidth(250)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("▣ 롤 정보")
        title.setObjectName("darkTitle")
        layout.addWidget(title)

        self.roll_info_labels = {}
        rows = [
            ("camera", "◉", "카메라", "미입력"),
            ("lens", "◎", "렌즈", "미입력"),
            ("film", "▰", "필름", "미입력"),
            ("iso", "ISO", "ISO", "미입력"),
            ("date", "▣", "촬영일", "미입력"),
            ("location", "⌖", "촬영장소", "미입력"),
            ("lab", "△", "현상소", "미입력"),
            ("scanner", "▱", "스캐너", "미입력"),
            ("memo", "✧", "메모", "미입력"),
        ]

        for key, icon, label, value in rows:
            layout.addLayout(self.create_roll_info_row(key, icon, label, value))

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #49422f;")
        layout.addWidget(line)

        preset_title = QLabel("네이밍 프리셋")
        preset_title.setObjectName("darkTitle")
        layout.addWidget(preset_title)

        self.thumbnail_combo = QComboBox()
        self.thumbnail_combo.setToolTip("썸네일 크기를 변경합니다.")
        for key, preset in THUMBNAIL_PRESETS.items():
            self.thumbnail_combo.addItem(preset["label"], key)
        current_index = self.thumbnail_combo.findData(self.thumbnail_preset_key)
        if current_index >= 0:
            self.thumbnail_combo.setCurrentIndex(current_index)
        self.thumbnail_combo.currentIndexChanged.connect(self.change_thumbnail_preset)

        thumb_label = QLabel("썸네일 크기")
        thumb_label.setObjectName("darkLabel")
        layout.addWidget(thumb_label)
        layout.addWidget(self.thumbnail_combo)

        layout.addStretch(1)

        self.roll_card_label = QLabel()
        self.roll_card_label.setObjectName("rollCard")
        self.roll_card_label.setAlignment(Qt.AlignCenter)
        self.roll_card_label.setMinimumHeight(96)
        layout.addWidget(self.roll_card_label)

        return panel

    def create_roll_info_row(self, key, icon, label, value):
        row = QHBoxLayout()
        row.setSpacing(8)

        icon_label = QLabel(icon)
        icon_label.setObjectName("darkLabel")
        icon_label.setFixedWidth(28)
        icon_label.setAlignment(Qt.AlignCenter)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(1)
        label_widget = QLabel(label)
        label_widget.setObjectName("darkLabel")
        value_widget = QLabel(value)
        value_widget.setObjectName("darkValue")
        value_widget.setWordWrap(True)

        self.roll_info_labels[key] = value_widget

        text_layout.addWidget(label_widget)
        text_layout.addWidget(value_widget)

        row.addWidget(icon_label)
        row.addLayout(text_layout, stretch=1)
        return row

    def create_center_panel(self):
        panel = QFrame()
        panel.setObjectName("lightCard")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        folder_row = QHBoxLayout()
        self.info = QLabel("폴더를 선택하거나 폴더를 이 창으로 드래그하세요.")
        self.info.setObjectName("sectionTitle")
        folder_row.addWidget(self.info, stretch=1)

        self.count_badge = QLabel("전체 0장")
        self.count_badge.setObjectName("smallMuted")
        folder_row.addWidget(self.count_badge)
        layout.addLayout(folder_row)

        self.table = ImageTable()
        self.apply_thumbnail_table_settings()
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.verticalScrollBar().setSingleStep(36)
        self.table.orderChanged.connect(self.sync_order)
        self.table.cellDoubleClicked.connect(self.open_preview_from_row)
        self.table.rowDoubleClicked.connect(self.open_preview_from_row_only)
        self.table.itemSelectionChanged.connect(self.update_side_panels)

        layout.addWidget(self.table, stretch=1)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(12)

        self.status_bar = QFrame()
        self.status_bar.setObjectName("lightCard")
        self.status_bar.setMinimumHeight(44)
        status_layout = QHBoxLayout(self.status_bar)
        status_layout.setContentsMargins(10, 4, 10, 4)

        self.folder_status = FolderStatusLabel()
        self.folder_status.setTextInteractionFlags(Qt.NoTextInteraction)
        self.folder_status.setCursor(Qt.PointingHandCursor)
        self.folder_status.clicked.connect(self.open_current_folder)
        self.folder_status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.count_status = QLabel()
        self.count_status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.folder_rename_button = QPushButton("폴더명 변경")
        self.folder_rename_button.setEnabled(False)
        self.folder_rename_button.setToolTip("현재 선택한 폴더 이름을 메타데이터 기준으로 변경합니다.")
        self.folder_rename_button.clicked.connect(self.rename_current_folder)

        status_layout.addWidget(self.folder_status, stretch=1)
        status_layout.addWidget(self.folder_rename_button)
        status_layout.addWidget(self.count_status)

        open_folder_button = QPushButton("📁 폴더 열기")
        open_folder_button.setObjectName("darkButton")
        open_folder_button.clicked.connect(self.open_current_folder)

        self.run_rename_button = QPushButton("🧰 이름 변경 실행")
        self.run_rename_button.setObjectName("primaryButton")
        self.run_rename_button.setEnabled(False)
        self.run_rename_button.clicked.connect(self.rename_files)

        bottom_row.addWidget(self.status_bar, stretch=1)
        bottom_row.addWidget(open_folder_button)
        bottom_row.addWidget(self.run_rename_button)
        layout.addLayout(bottom_row)

        return panel

    def create_right_panel(self):
        panel = QFrame()
        panel.setObjectName("lightCard")
        panel.setFixedWidth(280)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 16, 14, 16)
        layout.setSpacing(12)

        title = QLabel("⌜ 미리보기")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self.preview_image_label = QLabel("이미지를 선택하세요")
        self.preview_image_label.setAlignment(Qt.AlignCenter)
        self.preview_image_label.setMinimumHeight(190)
        self.preview_image_label.setObjectName("softCard")
        layout.addWidget(self.preview_image_label)

        self.preview_name_label = QLabel("-")
        self.preview_name_label.setObjectName("sectionTitle")
        layout.addWidget(self.preview_name_label)

        self.preview_meta_label = QLabel("-")
        self.preview_meta_label.setObjectName("smallMuted")
        layout.addWidget(self.preview_meta_label)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        layout.addWidget(line)

        summary_title = QLabel("롤 요약")
        summary_title.setObjectName("sectionTitle")
        layout.addWidget(summary_title)

        self.summary_label = QLabel()
        self.summary_label.setObjectName("softCard")
        self.summary_label.setMinimumHeight(120)
        self.summary_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.status_hint_label = QLabel("💡 변경된 순서는 이름 변경 시 적용됩니다.")
        self.status_hint_label.setObjectName("softCard")
        self.status_hint_label.setWordWrap(True)
        layout.addWidget(self.status_hint_label)

        layout.addStretch(1)
        return panel

    def selected_row_index(self):
        row = self.table.currentRow() if hasattr(self, "table") else -1
        if row < 0 or row >= len(self.images):
            return 0
        return row

    def roll_base_count(self):
        return int(self.settings.get("roll_base_count", 36) or 36)

    def roll_progress_text(self):
        if not self.images:
            return "ROLL\n\n░░░░░░░░░░\n\n0 / 36 EXP."

        base_count = self.roll_base_count()
        current = self.selected_row_index() + 1
        bar_count = 10
        filled = max(1, min(bar_count, round((current / max(base_count, 1)) * bar_count)))
        bar = "█" * filled + "░" * (bar_count - filled)
        extra = ""
        if current > base_count:
            extra = f"  +{current - base_count}"
        return f"ROLL\n\n{bar}\n\n{current} / {base_count} EXP.{extra}"

    def update_side_panels(self):
        if hasattr(self, "roll_card_label"):
            self.roll_card_label.setText(self.roll_progress_text())

        if hasattr(self, "count_badge"):
            self.count_badge.setText(f"전체 {len(self.images)}장")

        if hasattr(self, "summary_label"):
            if self.images:
                first_name = build_preview(self.images)[0][2]
                last_name = build_preview(self.images)[-1][2]
                self.summary_label.setText(
                    f"파일 수\n{len(self.images)}장\n\n"
                    f"정렬 방식\n역순\n\n"
                    f"변경될 첫 파일명\n{first_name}\n\n"
                    f"변경될 마지막 파일명\n{last_name}"
                )
            else:
                self.summary_label.setText("파일 수\n0장\n\n정렬 방식\n-")

        self.update_side_preview()

    def update_side_preview(self):
        if not hasattr(self, "preview_image_label"):
            return

        if not self.images:
            self.preview_image_label.setPixmap(QPixmap())
            self.preview_image_label.setText("이미지를 선택하세요")
            self.preview_name_label.setText("-")
            self.preview_meta_label.setText("-")
            return

        row = self.selected_row_index()
        image = self.images[row]
        pixmap = QPixmap(str(image))

        if pixmap.isNull():
            self.preview_image_label.setPixmap(QPixmap())
            self.preview_image_label.setText("미리보기를 불러올 수 없습니다.")
        else:
            scaled = pixmap.scaled(
                QSize(250, 190),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.preview_image_label.setText("")
            self.preview_image_label.setPixmap(scaled)

        self.preview_name_label.setText(image.name)
        reader = QImageReader(str(image))
        size = reader.size()
        if size.isValid():
            pixels = size.width() * size.height()
            mp = pixels / 1_000_000
            self.preview_meta_label.setText(
                f"{size.width()} × {size.height()} ({mp:.1f}MP)   {image.suffix.upper().lstrip('.')}"
            )
        else:
            self.preview_meta_label.setText(image.suffix.upper().lstrip('.'))

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

    def update_thumbnail_icons_for_current_size(self):
        """
        썸네일 크기 변경 시 테이블 전체를 다시 만들지 않고
        현재 행의 아이콘만 교체한다.
        캐시에 없는 썸네일은 QTimer 큐에서 뒤이어 생성된다.
        """

        self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)

        try:
            for row, image in enumerate(self.images):
                if row >= self.table.rowCount():
                    break

                self.table.setRowHeight(row, self.row_height)
                item = self.table.item(row, 0)

                if item is None:
                    item = self.placeholder_thumbnail_item(image)
                    self.table.setItem(row, 0, item)

                item.setData(Qt.UserRole, str(image))
                pixmap = self.thumbnail_cache.get(
                    self.thumbnail_cache_key(image)
                )

                if pixmap is not None and not pixmap.isNull():
                    item.setText("")
                    item.setIcon(QIcon(pixmap))
                else:
                    item.setIcon(QIcon())
                    item.setText("로딩 중")
                    item.setTextAlignment(Qt.AlignCenter)
        finally:
            self.table.setUpdatesEnabled(True)
            self.table.blockSignals(False)

    def change_thumbnail_preset(self, _index):
        preset_key = self.thumbnail_combo.currentData()
        if not preset_key or preset_key == self.thumbnail_preset_key:
            return

        self.apply_thumbnail_preset(preset_key)
        self.apply_thumbnail_table_settings()

        if self.images:
            self.update_thumbnail_icons_for_current_size()
            self.restart_thumbnail_loading_for_current_size()

    def update_status_bar(self):
        if self.current_folder is None:
            self.folder_status.setText("📂 현재 폴더: 없음")
            self.folder_status.setToolTip("폴더를 선택하면 전체 경로가 표시됩니다.")
            self.count_status.setText("")
            if hasattr(self, "folder_rename_button"):
                self.folder_rename_button.setEnabled(False)
            if hasattr(self, "run_rename_button"):
                self.run_rename_button.setEnabled(False)
            return

        self.folder_status.setText(f"📂 현재 폴더: {self.current_folder.name}")
        self.folder_status.setToolTip(str(self.current_folder))
        self.count_status.setText(f"📸 {len(self.images)}장")
        if hasattr(self, "folder_rename_button"):
            self.folder_rename_button.setEnabled(True)
        if hasattr(self, "run_rename_button"):
            self.run_rename_button.setEnabled(len(self.images) > 0)
        self.update_side_panels()

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
        if hasattr(self, "run_rename_button"):
            self.run_rename_button.setEnabled(enabled and len(self.images) > 0)
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

    def thumbnail_size_for_preset(self, preset_key=None):
        preset_key = preset_key or self.thumbnail_preset_key
        preset = THUMBNAIL_PRESETS.get(
            preset_key,
            THUMBNAIL_PRESETS[DEFAULT_THUMBNAIL_PRESET],
        )
        return preset["size"]

    def thumbnail_cache_key(self, image, preset_key=None):
        size = self.thumbnail_size_for_preset(preset_key)
        return f"{size.width()}x{size.height()}:{image}"

    def make_thumbnail(self, image, preset_key=None):
        image_path = str(image)
        target_size = self.thumbnail_size_for_preset(preset_key)
        cache_key = self.thumbnail_cache_key(image, preset_key)
        pixmap = self.thumbnail_cache.get(cache_key)

        if pixmap is not None:
            return pixmap

        # v1.2.1 성능 개선:
        # 썸네일 크기별 캐시를 분리해서 작게/보통/크게 전환 시
        # 이미 생성된 썸네일은 다시 만들지 않고 바로 재사용한다.
        reader = QImageReader(image_path)
        reader.setAutoTransform(True)

        original_size = reader.size()
        if original_size.isValid():
            scaled_size = original_size.scaled(
                target_size * 2,
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
                target_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )

        self.thumbnail_cache[cache_key] = pixmap
        return pixmap

    def thumbnail_preset_loading_order(self):
        preset_keys = [self.thumbnail_preset_key]

        for key in THUMBNAIL_PRESETS:
            if key != self.thumbnail_preset_key:
                preset_keys.append(key)

        return preset_keys

    def build_thumbnail_queue(self, preset_keys=None):
        generation = self.thumbnail_generation
        preset_keys = preset_keys or self.thumbnail_preset_loading_order()
        queue = []

        for preset_key in preset_keys:
            update_table = preset_key == self.thumbnail_preset_key
            for row, image in enumerate(self.images):
                cache_key = self.thumbnail_cache_key(image, preset_key)
                if cache_key in self.thumbnail_cache:
                    continue

                queue.append((generation, row, image, preset_key, update_table))

        return queue

    def start_thumbnail_loading(self):
        self.cancel_thumbnail_loading()
        self.thumbnail_queue = self.build_thumbnail_queue()

        if self.thumbnail_queue:
            self.thumbnail_timer.start()

    def restart_thumbnail_loading_for_current_size(self):
        self.cancel_thumbnail_loading()
        self.thumbnail_queue = self.build_thumbnail_queue()

        if self.thumbnail_queue:
            self.thumbnail_timer.start()

    def process_thumbnail_queue(self):
        if not self.thumbnail_queue:
            self.thumbnail_timer.stop()
            return

        current_generation = self.thumbnail_generation
        processed = 0

        while self.thumbnail_queue and processed < THUMBNAIL_BATCH_SIZE:
            queue_item = self.thumbnail_queue.pop(0)

            if len(queue_item) == 3:
                # v1.1 큐 형식과 호환
                generation, row, image = queue_item
                preset_key = self.thumbnail_preset_key
                update_table = True
            else:
                generation, row, image, preset_key, update_table = queue_item

            if generation != current_generation:
                continue

            pixmap = self.make_thumbnail(image, preset_key)

            if update_table and preset_key == self.thumbnail_preset_key:
                if row < 0 or row >= self.table.rowCount():
                    continue

                item = self.table.item(row, 0)

                if item is None:
                    continue

                if item.data(Qt.UserRole) != str(image):
                    continue

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

        if self.images:
            self.table.setCurrentCell(0, 0)

        self.start_thumbnail_loading()

        if not self.images:
            self.info.setText("이미지가 없습니다.")

        self.update_status_bar()
        self.update_side_panels()

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
            order_was_changed = new_images != self.images
            self.images = new_images

            # 행 이동 직후 전체 테이블을 다시 그리지 않는다.
            # macOS/Windows 모두에서 드래그/이동 후 줄어드는 행 높이만 복구한다.
            self.table.setUpdatesEnabled(False)
            try:
                for row in range(self.table.rowCount()):
                    self.table.setRowHeight(row, self.row_height)
            finally:
                self.table.setUpdatesEnabled(True)

            if order_was_changed:
                self.info.setText("변경된 순서는 이름변경시 적용됩니다.")
                self.update_side_panels()

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
