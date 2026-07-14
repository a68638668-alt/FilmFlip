from pathlib import Path
from collections import deque
import sys
from PySide6.QtCore import QObject, Qt, QSize, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QPixmap, QIcon, QGuiApplication, QImageReader, QDesktopServices, QPainter, QColor, QPen, QBrush, QPainterPath
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
    QGridLayout,
    QLineEdit,
    QSpinBox,
    QProgressDialog,
)

from dragdrop import ImageTable
import engine
from engine import find_images, build_preview, rename_images, undo_rename, rename_folder, undo_folder
from exif_utils import write_exif
from settings import load_settings, save_settings

try:
    from dialogs.rename_dialog import RenameDialog
    from dialogs.folder_dialog import FolderRenameDialog
except Exception:
    from dialog import RenameDialog, FolderRenameDialog

from dialogs.exif_dialog import ExifDialog
from dialogs.settings_dialog import SettingsDialog
from utils.design import polish_combo_box


def rename_finished(parent, count):
    QMessageBox.information(parent, "FilmFlip", f"{count}개의 이름 변경이 완료되었습니다.")


def rename_failed(parent, message):
    QMessageBox.critical(parent, "FilmFlip", f"작업 중 오류가 발생했습니다.\n\n{message}")


class ExifWriteWorker(QObject):
    """Write EXIF off the GUI thread so FilmFlip stays interactive."""

    progress = Signal(int, int, str)
    finished = Signal(object)

    def __init__(self, images, values):
        super().__init__()
        self.images = list(images)
        self.values = dict(values)

    @Slot()
    def run(self):
        try:
            result = write_exif(
                self.images,
                self.values,
                progress_callback=self.progress.emit,
            )
        except Exception as error:
            result = {"changed": 0, "skipped": 0, "errors": [str(error)]}
        self.finished.emit(result)


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

BASE_DIR = Path(__file__).resolve().parent
ICON_DIR = BASE_DIR / "assets" / "icons"

DARK_THEME_QSS = """
    QWidget { background: #28231f; color: #f2e8d9; }
    QLabel { background: transparent; }
    QLabel#appTitle, QLabel#centerTitle, QLabel#sectionTitle,
    QLabel#previewFileName, QLabel#summaryValue { color: #f7ead8; }
    QLabel#appSubtitle, QLabel#previewMeta, QLabel#smallMuted,
    QLabel#summaryKey { color: #c8b49d; }
    QFrame#lightCard, QFrame#centerCard { background: #302a25; border-color: #5a4b3e; }
    QFrame#tableHeaderCard, QFrame#previewCard { background: #373029; border-color: #5f5042; }
    QFrame#summaryCard, QFrame#softCard { background: #3a3129; border-color: #635243; }
    QFrame#summaryCell { border-color: rgba(225, 190, 145, 0.25); }
    QLabel#centerMuted, QLabel#fileTypeBadge { background: #453a31; color: #ead6b8; border-color: #6a5747; }
    QPushButton, QPushButton#toolbarButton, QPushButton#utilityButton {
        background: #3a322b; color: #f2dfc3; border-color: #695646;
    }
    QPushButton#toolbarButton:hover, QPushButton#utilityButton:hover { background: #4a3d32; }
    QPushButton#toolbarButton:disabled {
        background: #35302b; border-color: #5f5145;
    }
    QPushButton#toolbarButton:disabled QLabel#toolbarTitle { color: #f3e4d2; }
    QPushButton#toolbarButton:disabled QLabel#toolbarSubtitle { color: #d2bea6; }
    QLabel#toolbarTitle { color: #f7ead8; }
    QLabel#toolbarSubtitle { color: #c8b49d; }
    QComboBox, QLineEdit, QSpinBox { background: #211d19; color: #f3e2c7; border-color: #6a5747; }
    QComboBox QAbstractItemView { background: #211d19; color: #f3e2c7; selection-background-color: #745239; }
"""


def icon_path(name):
    return str(ICON_DIR / f"{name}.svg")


def app_icon(name, size=24, color=None):
    """Return a QIcon whose disabled mode is not auto-faded by Qt."""
    path = ICON_DIR / f"{name}.svg"
    icon = QIcon()
    if not path.exists():
        return icon
    pixmap = QIcon(str(path)).pixmap(QSize(size, size))
    if color and not pixmap.isNull():
        tinted = QPixmap(pixmap.size())
        tinted.fill(Qt.transparent)
        painter = QPainter(tinted)
        painter.drawPixmap(0, 0, pixmap)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), QColor(color))
        painter.end()
        pixmap = tinted
    for mode in (QIcon.Normal, QIcon.Disabled, QIcon.Active, QIcon.Selected):
        icon.addPixmap(pixmap, mode, QIcon.Off)
        icon.addPixmap(pixmap, mode, QIcon.On)
    return icon


class ImagePreviewDialog(QDialog):

    def __init__(self, images, index=0, parent=None):
        super().__init__(parent)

        self.images = images
        self.index = max(0, min(index, len(images) - 1))
        self.pixmap_cache = {}

        self.setWindowTitle("FilmFlip 미리보기")
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


class ToolbarButton(QPushButton):
    """Toolbar action with independently sized icon, title, and subtitle."""

    def __init__(self, icon_name, title, subtitle, parent=None):
        super().__init__(parent)
        self.setObjectName("toolbarButton")

        content = QHBoxLayout(self)
        content.setContentsMargins(12, 8, 12, 8)
        content.setSpacing(10)

        icon_label = QLabel()
        icon_label.setFixedSize(56, 56)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setPixmap(app_icon(icon_name, 50).pixmap(QSize(50, 50)))
        icon_label.setAttribute(Qt.WA_TransparentForMouseEvents)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)
        text_layout.setAlignment(Qt.AlignVCenter)

        title_label = QLabel(title)
        title_label.setObjectName("toolbarTitle")
        title_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("toolbarSubtitle")
        subtitle_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.title_label = title_label
        self.subtitle_label = subtitle_label

        text_layout.addWidget(title_label)
        text_layout.addWidget(subtitle_label)
        content.addWidget(icon_label)
        content.addLayout(text_layout, stretch=1)


class FilmFlipWindow(QWidget):

    def __init__(self):
        super().__init__()

        self.settings = load_settings()
        # 롤 정보는 현재 작업 중인 폴더에만 유효한 임시 상태다.
        # 이전 버전에서 저장한 값이 있더라도 앱을 다시 시작하면 복원하지 않는다.
        self.roll_metadata = {}
        if "roll_metadata" in self.settings:
            self.settings.pop("roll_metadata", None)
            save_settings(self.settings)
        self.dark_mode = self.settings.get("theme", "light") == "dark"

        self.setWindowTitle("FilmFlip v2.0")
        self.resize(1320, 800)
        self.setMinimumSize(1180, 720)
        self.setAcceptDrops(True)

        self.images = []
        self.current_folder = None
        self.thumbnail_cache = {}
        self.preview_cache = {}
        self.preview_metadata_cache = {}
        self.thumbnail_queue = deque()
        self.thumbnail_generation = 0
        self._exif_thread = None
        self._exif_worker = None
        self._exif_progress = None

        self.thumbnail_timer = QTimer(self)
        # 한 장씩 이벤트 루프에 양보하되 불필요한 대기 시간을 줄인다.
        self.thumbnail_timer.setInterval(4)
        self.thumbnail_timer.timeout.connect(self.process_thumbnail_queue)

        self.thumbnail_preset_key = self.settings.get(
            "thumbnail_size",
            DEFAULT_THUMBNAIL_PRESET,
        )
        if self.thumbnail_preset_key not in THUMBNAIL_PRESETS:
            self.thumbnail_preset_key = DEFAULT_THUMBNAIL_PRESET

        self.apply_thumbnail_preset(self.thumbnail_preset_key, save=False)

        self.apply_v2_style()
        self.light_style_sheet = self.styleSheet()

        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(18, 16, 18, 18)
        root_layout.setSpacing(12)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(16)
        top_layout.setContentsMargins(0, 0, 0, 2)

        brand_layout = QHBoxLayout()
        brand_layout.setSpacing(8)
        brand_layout.setContentsMargins(0, 0, 0, 0)

        logo = QLabel()
        logo.setFixedSize(86, 86)
        logo.setAlignment(Qt.AlignCenter)
        logo.setObjectName("logoBadge")
        # 기존 앱 아이콘을 우선 사용한다. film_roll.png 같은 임시 리소스가 있어도
        # 앱 아이콘/로고가 갑자기 바뀌지 않도록 icon.icns 또는 icon.png를 먼저 찾는다.
        logo_candidates = [
            BASE_DIR / "assets" / "icons" / "logo.svg",
            BASE_DIR / "assets" / "icons" / "film_roll.svg",
            BASE_DIR / "assets" / "film_roll.png",
            BASE_DIR / "assets" / "icon.png",
            BASE_DIR / "assets" / "app_icon.png",
            BASE_DIR / "assets" / "icon.icns",
        ]
        logo_pixmap = QPixmap()
        for logo_file in logo_candidates:
            if not logo_file.exists():
                continue
            if logo_file.suffix.lower() in (".icns", ".svg"):
                logo_pixmap = QIcon(str(logo_file)).pixmap(QSize(82, 82))
            else:
                logo_pixmap = QPixmap(str(logo_file))
            if not logo_pixmap.isNull():
                break
        if not logo_pixmap.isNull():
            logo.setPixmap(logo_pixmap.scaled(QSize(82, 82), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            logo.setText("🎞")

        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        brand_text.setAlignment(Qt.AlignVCenter)
        title = QLabel("FilmFlip")
        title.setObjectName("appTitle")
        title.setFixedHeight(41)
        subtitle = QLabel("필름 스캔 파일 관리 도구")
        subtitle.setObjectName("appSubtitle")
        subtitle.setFixedHeight(21)
        brand_text.addWidget(title)
        brand_text.addWidget(subtitle)

        brand_layout.addWidget(logo)
        brand_layout.addLayout(brand_text)
        brand_host = QWidget()
        brand_host.setLayout(brand_layout)
        brand_host.setFixedWidth(288)
        top_layout.addWidget(brand_host, stretch=0)

        toolbar_wrap = QFrame()
        toolbar_wrap.setObjectName("toolbarWrap")
        toolbar_layout = QHBoxLayout(toolbar_wrap)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(14)

        self.button = self.create_toolbar_button("folder", "폴더 선택", "폴더를 선택하세요")
        self.button.clicked.connect(self.select_folder)

        sort_subtitle = (
            "현재: 역순 정렬"
            if self.settings.get("default_sort", "reverse") == "reverse"
            else "현재: 원본 순서"
        )
        self.reverse_button = self.create_toolbar_button("reverse", "역순 변경", sort_subtitle)
        self.reverse_button.clicked.connect(self.reverse_rename)

        self.rename_button = self.create_toolbar_button("rename", "이름 변경", "파일명 및 폴더명 변경")
        self.rename_button.clicked.connect(self.rename_files)

        self.undo_button = self.create_toolbar_button("undo", "Undo", "마지막 작업 취소")
        self.undo_button.clicked.connect(self.undo_last)

        for top_button in [
            self.button,
            self.reverse_button,
            self.rename_button,
            self.undo_button,
        ]:
            toolbar_layout.addWidget(top_button)

        top_layout.addWidget(toolbar_wrap, stretch=1)

        utility_layout = QHBoxLayout()
        utility_layout.setSpacing(12)
        self.theme_button = self.create_utility_button("sun", "다크 모드로 변경")
        self.settings_button = self.create_utility_button("settings", "FilmFlip 기본 설정")
        self.theme_button.clicked.connect(self.toggle_theme)
        self.settings_button.clicked.connect(self.open_settings_dialog)
        utility_layout.addWidget(self.theme_button)
        utility_layout.addWidget(self.settings_button)
        top_layout.addLayout(utility_layout, stretch=0)

        main_layout = QHBoxLayout()
        main_layout.setSpacing(14)

        left_panel = self.create_left_panel()
        center_panel = self.create_center_panel()
        right_panel = self.create_right_panel()

        main_layout.addWidget(left_panel)
        main_layout.addWidget(center_panel, stretch=1)
        main_layout.addWidget(right_panel)

        root_layout.addLayout(top_layout)
        root_layout.addLayout(main_layout, stretch=1)

        self.setLayout(root_layout)
        self.apply_theme(save=False)
        self.update_status_bar()
        self.update_side_panels()

    def apply_v2_style(self):
        self.setStyleSheet(
            """
            QWidget {
                background: #f6f0e7;
                color: #211c17;
                font-family: "Apple SD Gothic Neo", "Helvetica Neue", "Segoe UI";
                font-size: 13px;
            }
            QLabel { background: transparent; }
            QLabel#appTitle {
                font-family: "Helvetica Neue", "Avenir Next", sans-serif;
                font-size: 35px;
                font-weight: 750;
                letter-spacing: -1.1px;
                color: #1d1915;
            }
            QLabel#appSubtitle {
                color: #574b40;
                font-size: 13px;
                font-weight: 650;
            }
            QLabel#logoBadge {
                background: transparent;
                border: 0px;
                color: #211812;
                font-size: 34px;
            }
            QFrame#toolbarWrap {
                background: transparent;
                border: 0px;
            }
            QFrame#darkPanel {
                background: #171510;
                border: 1px solid #211e18;
                border-radius: 10px;
            }
            QFrame#lightCard {
                background: #faf7f1;
                border: 1px solid #ddd3c5;
                border-radius: 10px;
            }
            QFrame#centerCard {
                background: #faf7f1;
                border: 1px solid #ddd3c5;
                border-radius: 10px;
            }
            QFrame#tableHeaderCard {
                background: #f8f2e8;
                border: 1px solid #ded4c7;
                border-radius: 8px;
            }
            QFrame#tableCard {
                background: #15120f;
                border: 1px solid #352a20;
                border-radius: 10px;
            }
            QFrame#folderPathBar {
                background: transparent;
                border: 0px;
            }
            QFrame#softCard {
                background: #eee4d6;
                border: 1px solid #d9cdbd;
                border-radius: 8px;
            }
            QFrame#previewCard {
                background: #faf7f1;
                border: 1px solid #ded4c7;
                border-radius: 8px;
            }
            QFrame#summaryCard {
                background: #f5ede1;
                border: 1px solid #ded1bf;
                border-radius: 8px;
            }
            QFrame#summaryCell {
                background: transparent;
                border-right: 1px solid rgba(110, 79, 44, 0.28);
                border-bottom: 1px solid rgba(110, 79, 44, 0.22);
            }
            QLabel#summaryKey {
                color: #6b543d;
                font-size: 11px;
                font-weight: 850;
            }
            QLabel#summaryValue {
                color: #2c1d14;
                font-size: 14px;
                font-weight: 900;
            }
            QLabel#sectionTitle {
                font-size: 17px;
                font-weight: 900;
                color: #39281c;
                letter-spacing: -0.2px;
            }
            QLabel#previewFileName {
                color: #2b2119;
                font-size: 15px;
                font-weight: 900;
                padding-top: 2px;
            }
            QLabel#previewMeta {
                color: #5d5146;
                font-size: 11px;
                font-weight: 650;
            }
            QLabel#fileTypeBadge {
                background: #f8f2e8;
                color: #4e3b2b;
                border: 1px solid #ddd2c3;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 10px;
                font-weight: 850;
            }
            QLabel#centerTitle {
                font-size: 18px;
                font-weight: 900;
                color: #302116;
            }
            QLabel#darkTitle {
                color: #f0d7ad;
                font-size: 16px;
                font-weight: 900;
                letter-spacing: -0.2px;
            }
            QLabel#darkLabel {
                color: #a99880;
                font-size: 11px;
                font-weight: 800;
            }
            QLabel#darkValue {
                color: #fff0d4;
                font-size: 13px;
                font-weight: 800;
            }
            QLabel#iconPill {
                background: transparent;
                border: 0px;
                color: #d99d57;
                font-size: 13px;
                font-weight: 900;
            }
            QLabel#smallMuted {
                color: #6f5a44;
                font-size: 11px;
                font-weight: 700;
                line-height: 130%;
            }
            QWidget#statusCell { background: transparent; }
            QLabel#statusText {
                background: transparent;
                color: #f2dfbd;
                font-size: 12px;
                font-weight: 850;
            }
            QLabel#centerMuted {
                background: #f8f2e8;
                color: #6f573f;
                border: 1px solid #ddd2c3;
                border-radius: 7px;
                padding: 7px 12px;
                font-size: 12px;
                font-weight: 900;
            }
            QLabel#rollCard {
                background: #ead8b9;
                color: #21160f;
                border: 1px solid #bb925e;
                border-radius: 8px;
                font-family: Menlo, Monaco, "SF Mono", Consolas, monospace;
                font-size: 15px;
                font-weight: 900;
                padding: 10px;
                line-height: 150%;
            }
            QPushButton {
                background: #f8f2e8;
                border: 1px solid #dcd1c1;
                border-radius: 8px;
                padding: 8px 12px;
                color: #2c1f16;
                font-weight: 850;
            }
            QPushButton:hover { background: #efd9bd; border-color: #b78f61; }
            QPushButton:pressed { background: #dfc19a; }
            QPushButton:disabled {
                color: #a39586;
                background: #e5d6c4;
                border-color: #d4c2ae;
            }
            QPushButton#toolbarButton {
                min-width: 178px;
                max-width: 178px;
                min-height: 76px;
                max-height: 76px;
                background: #f8f2e8;
                border: 1px solid #ded3c4;
                border-radius: 9px;
                padding: 0px;
            }
            QLabel#toolbarTitle {
                color: #251f19;
                font-size: 15px;
                font-weight: 900;
            }
            QLabel#toolbarSubtitle {
                color: #5b5045;
                font-size: 10px;
                font-weight: 650;
            }
            QPushButton#toolbarButton:hover { background: #eee5d9; }
            QPushButton#toolbarButton:disabled {
                background: #f8f2e8;
                border: 1px solid #ded3c4;
            }
            QPushButton#utilityButton {
                min-width: 46px;
                max-width: 46px;
                min-height: 46px;
                max-height: 46px;
                border-radius: 13px;
                background: #f8f2e8;
                border: 1px solid #ded3c4;
                padding: 0px;
            }
            QPushButton#primaryButton {
                background: #b44720;
                color: #fff2dc;
                border: 1px solid #943716;
                font-size: 15px;
                font-weight: 900;
                padding-left: 20px;
                padding-right: 18px;
            }
            QPushButton#darkButton {
                background: #18130f;
                color: #f1d8ae;
                border: 1px solid #493827;
            }
            QPushButton#darkButton:hover { background: #30271f; }
            QPushButton#exifButton {
                background: #2a231b;
                color: #f2ddb8;
                border: 1px solid #6d5235;
                border-radius: 9px;
                padding: 9px 12px;
                font-size: 13px;
                font-weight: 900;
                text-align: left;
            }
            QPushButton#exifButton:hover { background: #3a2e22; border-color: #b17e4a; }
            QComboBox {
                background: #241f18;
                color: #f2dfbd;
                border: 1px solid #4a3b29;
                border-radius: 12px;
                padding: 8px 38px 8px 10px;
                font-weight: 800;
            }
            QComboBox::drop-down {
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 34px;
                background: #30271f;
                border-left: 1px solid #4a3b29;
                border-top-right-radius: 11px;
                border-bottom-right-radius: 11px;
            }
            QComboBox::drop-down:hover { background: #4b3928; }
            QComboBox::down-arrow {
                image: url(filmflipicons:chevron_down_light.svg);
                width: 13px;
                height: 13px;
            }
            QComboBox:hover, QComboBox:focus {
                background: #392d21;
                border-color: #c59253;
            }
            QLineEdit#darkInput, QSpinBox#darkSpin {
                background: #241f18;
                color: #f2dfbd;
                border: 1px solid #4a3b29;
                border-radius: 7px;
                padding: 6px 9px;
                min-height: 20px;
                font-weight: 800;
            }
            QSpinBox#darkSpin { min-width: 54px; max-width: 64px; }
            QComboBox QAbstractItemView {
                background: #211d17;
                color: #f2dfbd;
                selection-background-color: #5a4228;
            }
            QComboBox QAbstractItemView::item:hover {
                background: #4b3928;
                color: #fff3df;
            }
            QTableWidget {
                background: #15120f;
                alternate-background-color: #1f1a15;
                color: #f2dfbd;
                gridline-color: #33291f;
                border: 0px;
                border-radius: 6px;
                selection-background-color: #35291f;
                selection-color: #fff4df;
                outline: 0;
            }
            QTableWidget::item {
                border-bottom: 1px solid #2d251d;
                padding: 8px;
            }
            QTableWidget::item:selected {
                background: #3b2d20;
                color: #fff4df;
                border-top: 1px solid #a97b4c;
                border-bottom: 1px solid #a97b4c;
            }
            QHeaderView::section {
                background: #15120f;
                color: #d9bd8d;
                border: 0px;
                border-bottom: 1px solid #3d3124;
                padding: 10px 8px;
                font-weight: 900;
            }
            QHeaderView:vertical {
                background: #15120f;
            }
            QHeaderView::section:vertical {
                background: #15120f;
                color: #f2eadf;
                border: 0px;
                border-bottom: 1px solid #33291f;
                padding: 4px;
                font-size: 12px;
                font-weight: 800;
            }
            QTableCornerButton::section { background: #15120f; border: 0px; }
            QScrollBar:vertical { background: #18130f; width: 12px; border-radius: 6px; margin: 2px; }
            QScrollBar::handle:vertical { background: #8d7655; min-height: 34px; border-radius: 6px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar:horizontal { background: #18130f; height: 12px; border-radius: 6px; margin: 2px; }
            QScrollBar::handle:horizontal { background: #8d7655; min-width: 34px; border-radius: 6px; }
            """
        )

    def create_toolbar_button(self, icon_name, title, subtitle):
        button = ToolbarButton(icon_name, title, subtitle)
        button.setFixedSize(178, 76)
        button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        return button

    def create_utility_button(self, icon_name, tooltip):
        button = QPushButton("")
        button.setObjectName("utilityButton")
        icon_file = ICON_DIR / f"{icon_name}.svg"
        if icon_file.exists():
            button.setIcon(app_icon(icon_name, 34))
            button.setIconSize(QSize(34, 34))
        else:
            button.setText("☀" if icon_name == "sun" else "⚙")
        button.setToolTip(tooltip)
        return button

    def apply_theme(self, save=True):
        self.setStyleSheet(
            self.light_style_sheet + (DARK_THEME_QSS if self.dark_mode else "")
        )
        title_color = "#f7ead8" if self.dark_mode else "#251f19"
        subtitle_color = "#d2bea6" if self.dark_mode else "#5b5045"
        for button in self.findChildren(ToolbarButton):
            button.title_label.setStyleSheet(f"color: {title_color};")
            button.subtitle_label.setStyleSheet(f"color: {subtitle_color};")
        if hasattr(self, "theme_button"):
            icon_name = "moon" if self.dark_mode else "sun"
            self.theme_button.setIcon(app_icon(icon_name, 34))
            self.theme_button.setIconSize(QSize(34, 34))
            self.theme_button.setToolTip(
                "일반 모드로 변경" if self.dark_mode else "다크 모드로 변경"
            )
        if hasattr(self, "thumbnail_combo"):
            polish_combo_box(self.thumbnail_combo, self.dark_mode)
        if save:
            self.settings["theme"] = "dark" if self.dark_mode else "light"
            save_settings(self.settings)

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.apply_theme()

    def open_settings_dialog(self):
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() != QDialog.Accepted:
            return

        previous_thumbnail = self.thumbnail_preset_key
        previous_sort = self.settings.get("default_sort", "reverse")
        self.settings.update(dialog.values())
        save_settings(self.settings)

        if hasattr(self.reverse_button, "subtitle_label"):
            subtitle = (
                "현재: 역순 정렬"
                if self.settings.get("default_sort", "reverse") == "reverse"
                else "현재: 원본 순서"
            )
            self.reverse_button.subtitle_label.setText(subtitle)

        self.dark_mode = self.settings.get("theme", "light") == "dark"
        self.apply_theme(save=False)

        new_thumbnail = self.settings.get("thumbnail_size", DEFAULT_THUMBNAIL_PRESET)
        if new_thumbnail != previous_thumbnail:
            self.apply_thumbnail_preset(new_thumbnail)
            if hasattr(self, "thumbnail_combo"):
                self.thumbnail_combo.blockSignals(True)
                self.thumbnail_combo.setCurrentIndex(
                    max(0, self.thumbnail_combo.findData(new_thumbnail))
                )
                self.thumbnail_combo.blockSignals(False)
            self.apply_thumbnail_table_settings()
            self.update_thumbnail_icons_for_current_size()
            self.restart_thumbnail_loading_for_current_size()

        # 롤 컷수·테마처럼 파일 순서와 무관한 설정을 저장할 때는
        # 테이블을 다시 만들지 않는다. 기존 썸네일이 잠시 "로딩 중"으로
        # 되돌아가는 현상을 막고 설정 반영도 즉시 끝낸다.
        if self.settings.get("default_sort", "reverse") != previous_sort:
            self.refresh_preview()
        else:
            self.update_side_panels()

    def create_svg_icon_label(self, icon_name, size=28):
        label = QLabel()
        label.setObjectName("iconPill")
        label.setFixedSize(size + 4, size + 4)
        label.setAlignment(Qt.AlignCenter)

        icon_file = ICON_DIR / f"{icon_name}.svg"
        if icon_file.exists():
            pixmap = app_icon(icon_name, size).pixmap(QSize(size, size))
            label.setPixmap(pixmap)
        else:
            label.setText("•")
        return label

    def create_left_panel(self):
        panel = QFrame()
        panel.setObjectName("darkPanel")
        panel.setFixedWidth(246)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(6)

        title = QLabel("롤 정보")
        title.setObjectName("darkTitle")
        layout.addWidget(title)

        self.roll_info_labels = {}
        rows = [
            ("camera", "camera", "카메라", "미입력"),
            ("lens", "lens", "렌즈", "미입력"),
            ("film", "film", "필름", "미입력"),
            ("iso", "iso", "ISO", "미입력"),
            ("date", "calendar", "촬영일", "미입력"),
            ("location", "location", "촬영장소", "미입력"),
            ("lab", "lab", "현상소", "미입력"),
            ("scanner", "scanner", "스캐너", "미입력"),
            ("memo", "memo", "메모", "미입력"),
        ]

        for key, icon, label, value in rows:
            layout.addLayout(self.create_roll_info_row(key, icon, label, value))

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #49422f;")
        layout.addWidget(line)

        exif_title = QLabel("EXIF 정보")
        exif_title.setObjectName("darkTitle")
        layout.addWidget(exif_title)

        self.exif_edit_button = QPushButton("EXIF 정보 변경")
        self.exif_edit_button.setObjectName("exifButton")
        self.exif_edit_button.setIcon(app_icon("edit", 28))
        self.exif_edit_button.setIconSize(QSize(28, 28))
        self.exif_edit_button.setMinimumHeight(46)
        self.exif_edit_button.clicked.connect(self.open_exif_editor)
        layout.addWidget(self.exif_edit_button)

        thumb_line = QFrame()
        thumb_line.setFrameShape(QFrame.HLine)
        thumb_line.setStyleSheet("color: #49422f;")
        layout.addWidget(thumb_line)

        thumbnail_title = QLabel("썸네일 크기")
        thumbnail_title.setObjectName("darkTitle")
        layout.addWidget(thumbnail_title)

        thumbnail_row = QHBoxLayout()
        thumbnail_row.setSpacing(8)
        thumbnail_row.addWidget(self.create_svg_icon_label("thumbnail", 28))
        self.thumbnail_combo = QComboBox()
        for key in ("small", "medium", "large"):
            self.thumbnail_combo.addItem(THUMBNAIL_PRESETS[key]["label"], key)
        self.thumbnail_combo.setCurrentIndex(
            max(0, self.thumbnail_combo.findData(self.thumbnail_preset_key))
        )
        self.thumbnail_combo.currentIndexChanged.connect(self.change_thumbnail_preset)
        polish_combo_box(self.thumbnail_combo, getattr(self, "dark_mode", False))
        thumbnail_row.addWidget(self.thumbnail_combo, stretch=1)
        layout.addLayout(thumbnail_row)
        layout.addStretch(1)

        self.roll_card_label = QLabel()
        self.roll_card_label.setObjectName("rollCard")
        self.roll_card_label.setAlignment(Qt.AlignCenter)
        self.roll_card_label.setMinimumHeight(78)
        self.roll_card_label.setWordWrap(False)
        layout.addWidget(self.roll_card_label)

        return panel

    def quick_naming_changed(self, _value=None):
        return

    def build_current_preview(self, reverse=None):
        if reverse is None:
            reverse = self.settings.get("default_sort", "reverse") == "reverse"
        prefix = ""
        digits = int(self.settings.get("quick_digits", 3) or 3)
        return build_preview(
            self.images,
            template=f"{prefix}{{n}}",
            reverse=reverse,
            digits=digits,
        )

    def create_roll_info_row(self, key, icon, label, value):
        row = QHBoxLayout()
        row.setSpacing(8)

        icon_label = self.create_svg_icon_label(icon)

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

    def open_exif_editor(self):
        if not self.images:
            QMessageBox.information(self, "EXIF 정보 변경", "먼저 이미지 폴더를 선택해주세요.")
            return

        if self._exif_thread is not None and self._exif_thread.isRunning():
            QMessageBox.information(self, "EXIF 정보 변경", "EXIF 정보를 저장하고 있습니다.")
            return

        dialog = ExifDialog(self.images, self)
        if dialog.exec() != QDialog.Accepted:
            return

        values = dialog.values()
        self.remember_roll_metadata({
            "date": values.get("datetime_original", "").replace(":", "-")[:10],
            "camera": " ".join(
                part for part in (values.get("make", ""), values.get("model", "")) if part
            ),
            "lens": values.get("lens_model", ""),
            "iso": values.get("iso", ""),
            "memo": values.get("description", "") or values.get("user_comment", ""),
        })

        progress = QProgressDialog("EXIF 정보를 저장하는 중…", "", 0, len(self.images), self)
        progress.setWindowTitle("EXIF 정보 변경")
        progress.setWindowModality(Qt.WindowModal)
        progress.setCancelButton(None)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        thread = QThread(self)
        worker = ExifWriteWorker(self.images, values)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progress.connect(self._update_exif_progress)
        worker.finished.connect(self._finish_exif_write)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_exif_task)

        self._exif_thread = thread
        self._exif_worker = worker
        self._exif_progress = progress
        self.exif_edit_button.setEnabled(False)
        progress.show()
        thread.start()

    @Slot(int, int, str)
    def _update_exif_progress(self, done, total, filename):
        if self._exif_progress is None:
            return
        self._exif_progress.setMaximum(max(total, 1))
        self._exif_progress.setValue(done)
        self._exif_progress.setLabelText(f"{filename}\n{done} / {total}장 처리 완료")

    @Slot(object)
    def _finish_exif_write(self, result):
        if self._exif_progress is not None:
            self._exif_progress.setValue(self._exif_progress.maximum())
            self._exif_progress.close()

        message = f"{result['changed']}장의 EXIF 정보를 변경했습니다."
        if result["skipped"]:
            message += f"\nJPEG가 아닌 {result['skipped']}장은 건너뛰었습니다."
        if result["errors"]:
            message += "\n\n" + "\n".join(result["errors"][:5])
            QMessageBox.warning(self, "EXIF 정보 변경", message)
        else:
            QMessageBox.information(self, "EXIF 정보 변경", message)

    @Slot()
    def _clear_exif_task(self):
        self._exif_thread = None
        self._exif_worker = None
        if self._exif_progress is not None:
            self._exif_progress.deleteLater()
            self._exif_progress = None
        self.exif_edit_button.setEnabled(True)

    def create_center_panel(self):
        panel = QFrame()
        panel.setObjectName("centerCard")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        table_header = QFrame()
        table_header.setObjectName("tableHeaderCard")
        header_layout = QHBoxLayout(table_header)
        header_layout.setContentsMargins(14, 8, 12, 8)
        header_layout.setSpacing(8)

        header_folder_icon = QLabel()
        header_folder_icon.setFixedSize(34, 34)
        header_folder_icon.setAlignment(Qt.AlignCenter)
        header_folder_icon.setPixmap(app_icon("folder", 30).pixmap(QSize(30, 30)))
        header_layout.addWidget(header_folder_icon)

        self.info = QLabel("현재 폴더: 폴더를 선택하세요")
        self.info.setObjectName("centerTitle")
        header_layout.addWidget(self.info, stretch=1)

        self.count_badge = QLabel("전체 0장")
        self.count_badge.setObjectName("centerMuted")
        header_layout.addWidget(self.count_badge)
        layout.addWidget(table_header)

        self.table = ImageTable()
        self.apply_thumbnail_table_settings()
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.verticalScrollBar().setSingleStep(36)
        self.table.orderChanged.connect(self.sync_order)
        self.table.cellDoubleClicked.connect(self.open_preview_from_row)
        self.table.rowDoubleClicked.connect(self.open_preview_from_row_only)
        self.table.itemSelectionChanged.connect(self.update_side_panels)

        table_card = QFrame()
        table_card.setObjectName("tableCard")
        table_layout = QVBoxLayout(table_card)
        # QTableWidget의 헤더/viewport는 별도 네이티브 레이어라 자체 radius나
        # 폴리곤 마스크를 쓰면 Retina에서 모서리가 도트처럼 보일 수 있다.
        # 매끄러운 외곽 카드 안으로 살짝 넣어 외곽선은 한 겹만 그린다.
        table_layout.setContentsMargins(3, 3, 3, 3)
        table_layout.setSpacing(0)
        table_layout.addWidget(self.table)
        layout.addWidget(table_card, stretch=1)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(12)

        self.status_bar = QFrame()
        self.status_bar.setObjectName("folderPathBar")
        self.status_bar.setMinimumHeight(44)
        status_layout = QHBoxLayout(self.status_bar)
        status_layout.setContentsMargins(10, 4, 10, 4)

        path_icon = QLabel()
        path_icon.setFixedSize(28, 28)
        path_icon.setAlignment(Qt.AlignCenter)
        path_icon.setPixmap(app_icon("folder", 24).pixmap(QSize(24, 24)))
        status_layout.addWidget(path_icon)

        self.folder_status = FolderStatusLabel()
        self.folder_status.setTextInteractionFlags(Qt.NoTextInteraction)
        self.folder_status.setCursor(Qt.PointingHandCursor)
        self.folder_status.clicked.connect(self.open_current_folder)
        self.folder_status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.count_status = QLabel()
        self.count_status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.folder_rename_button = QPushButton("폴더명 변경")
        self.folder_rename_button.setObjectName("darkButton")
        self.folder_rename_button.setIcon(app_icon("folder", 26))
        self.folder_rename_button.setIconSize(QSize(26, 26))
        self.folder_rename_button.setEnabled(False)
        self.folder_rename_button.setToolTip("현재 선택한 폴더 이름을 메타데이터 기준으로 변경합니다.")
        self.folder_rename_button.clicked.connect(self.rename_current_folder)
        self.folder_rename_button.setFixedSize(166, 48)

        status_layout.addWidget(self.folder_status, stretch=1)
        status_layout.addWidget(self.count_status)

        self.run_rename_button = QPushButton("이름 변경 실행")
        self.run_rename_button.setObjectName("primaryButton")
        self.run_rename_button.setIcon(app_icon("rename_run", 26))
        self.run_rename_button.setIconSize(QSize(26, 26))
        self.run_rename_button.setMinimumHeight(48)
        self.run_rename_button.setEnabled(False)
        self.run_rename_button.clicked.connect(self.rename_files)

        bottom_row.addWidget(self.status_bar, stretch=1)
        bottom_row.addSpacing(8)
        bottom_row.addWidget(self.folder_rename_button)
        layout.addLayout(bottom_row)

        return panel

    def create_right_panel(self):
        panel = QFrame()
        panel.setObjectName("lightCard")
        panel.setFixedWidth(300)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)

        title = QLabel("미리보기")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        preview_card = QFrame()
        preview_card.setObjectName("previewCard")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(10, 10, 10, 10)
        preview_layout.setSpacing(0)

        self.preview_image_label = QLabel("이미지를 선택하세요")
        self.preview_image_label.setAlignment(Qt.AlignCenter)
        self.preview_image_label.setFixedHeight(170)
        self.preview_image_label.setObjectName("softCard")
        self.preview_image_label.setScaledContents(False)
        preview_layout.addWidget(self.preview_image_label)
        layout.addWidget(preview_card)

        self.preview_name_label = QLabel("-")
        self.preview_name_label.setObjectName("previewFileName")
        layout.addWidget(self.preview_name_label)

        preview_meta_row = QHBoxLayout()
        self.preview_meta_label = QLabel("-")
        self.preview_meta_label.setObjectName("previewMeta")
        self.preview_type_badge = QLabel("-")
        self.preview_type_badge.setObjectName("fileTypeBadge")
        self.preview_type_badge.setAlignment(Qt.AlignCenter)
        preview_meta_row.addWidget(self.preview_meta_label, stretch=1)
        preview_meta_row.addWidget(self.preview_type_badge)
        layout.addLayout(preview_meta_row)

        summary_card = QFrame()
        summary_card.setObjectName("summaryCard")
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(14, 12, 14, 12)
        summary_layout.setSpacing(10)
        summary_title = QLabel("롤 요약")
        summary_title.setObjectName("sectionTitle")
        summary_layout.addWidget(summary_title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        self.roll_count_value = QLabel("0장")
        self.roll_sort_value = QLabel("-")
        self.roll_first_value = QLabel("-")
        self.roll_last_value = QLabel("-")
        summary_items = [
            ("파일 수", self.roll_count_value),
            ("정렬 방식", self.roll_sort_value),
            ("변경될 첫 파일명", self.roll_first_value),
            ("변경될 마지막 파일명", self.roll_last_value),
        ]
        for idx, (key, value_widget) in enumerate(summary_items):
            cell = QFrame()
            cell.setObjectName("summaryCell")
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(8, 4, 8, 6)
            cell_layout.setSpacing(3)
            key_label = QLabel(key)
            key_label.setObjectName("summaryKey")
            value_widget.setObjectName("summaryValue")
            value_widget.setWordWrap(True)
            cell_layout.addWidget(key_label)
            cell_layout.addWidget(value_widget)
            grid.addWidget(cell, idx // 2, idx % 2)
        summary_layout.addLayout(grid)
        layout.addWidget(summary_card)

        guide_card = QFrame()
        guide_card.setObjectName("previewCard")
        guide_layout = QVBoxLayout(guide_card)
        guide_layout.setContentsMargins(14, 12, 14, 12)
        self.status_hint_label = QLabel("변경된 순서는 이름변경시 적용됩니다.")
        self.status_hint_label.setObjectName("smallMuted")
        self.status_hint_label.setWordWrap(True)
        self.status_hint_label.setAlignment(Qt.AlignCenter)
        hint_row = QHBoxLayout()
        hint_row.addStretch(1)
        hint_icon = QLabel()
        hint_icon.setFixedSize(24, 24)
        hint_icon.setPixmap(app_icon("lightbulb", 21).pixmap(QSize(21, 21)))
        hint_row.addWidget(hint_icon)
        hint_row.addWidget(self.status_hint_label)
        hint_row.addStretch(1)
        guide_layout.addLayout(hint_row)
        layout.addStretch(1)
        layout.addWidget(guide_card)
        layout.addStretch(1)
        self.run_rename_button.setFixedHeight(48)
        self.run_rename_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self.run_rename_button)
        return panel

    def selected_row_index(self):
        row = self.table.currentRow() if hasattr(self, "table") else -1
        if row < 0 or row >= len(self.images):
            return 0
        return row

    def roll_base_count(self):
        return int(self.settings.get("roll_base_count", 36) or 36)

    def roll_progress_text(self):
        base_count = self.roll_base_count()
        if not self.images:
            return f"ROLL   00 / {base_count} EXP.\n░░░░░░░░░░"

        current = self.selected_row_index() + 1
        bar_count = 10
        filled = max(1, min(bar_count, round((current / max(base_count, 1)) * bar_count)))
        bar = "█" * filled + "░" * (bar_count - filled)
        overage = max(0, len(self.images) - base_count)
        extra = f"  +{overage}" if overage else ""
        return f"ROLL   {current} / {base_count} EXP.{extra}\n{bar}"

    def update_side_panels(self):
        if hasattr(self, "roll_card_label"):
            self.roll_card_label.setText(self.roll_progress_text())

        if hasattr(self, "roll_info_labels"):
            for key, value_widget in self.roll_info_labels.items():
                value = str(self.roll_metadata.get(key, "") or "").strip()
                value_widget.setText(value if value else "미입력")

        if hasattr(self, "count_badge"):
            self.count_badge.setText(f"전체 {len(self.images)}장")

        if hasattr(self, "roll_count_value"):
            if self.images:
                preview = self.build_current_preview()
                first_name = preview[0][2]
                last_name = preview[-1][2]
                self.roll_count_value.setText(f"{len(self.images)}장")
                sort_text = "역순" if self.settings.get("default_sort", "reverse") == "reverse" else "현재 순서"
                self.roll_sort_value.setText(sort_text)
                self.roll_first_value.setText(first_name)
                self.roll_last_value.setText(last_name)
            else:
                self.roll_count_value.setText("0장")
                self.roll_sort_value.setText("-")
                self.roll_first_value.setText("-")
                self.roll_last_value.setText("-")

        self.update_side_preview()

    def remember_roll_metadata(self, options):
        mapping = {
            "camera": "camera",
            "lens": "lens",
            "film": "film",
            "iso": "iso",
            "date": "date",
            "place": "location",
            "location": "location",
            "lab": "lab",
            "scanner": "scanner",
            "memo": "memo",
        }
        for source_key, target_key in mapping.items():
            if source_key not in options:
                continue
            value = str(options.get(source_key, "") or "").strip()
            self.roll_metadata[target_key] = value
        self.update_side_panels()

    def reset_roll_metadata(self):
        """Clear per-roll values without deleting reusable shooting presets."""
        self.roll_metadata = {}
        # Remove a legacy persisted value if an older settings file still has one.
        self.settings.pop("roll_metadata", None)
        self.update_side_panels()

    def update_side_preview(self):
        if not hasattr(self, "preview_image_label"):
            return

        if not self.images:
            self.preview_image_label.setPixmap(QPixmap())
            self.preview_image_label.setText("이미지를 선택하세요")
            self.preview_name_label.setText("-")
            self.preview_meta_label.setText("-")
            if hasattr(self, "preview_type_badge"):
                self.preview_type_badge.setText("-")
            if hasattr(self, "file_name_value"):
                self.file_name_value.setText("-")
                self.file_res_value.setText("-")
                self.file_type_value.setText("-")
            return

        row = self.selected_row_index()
        image = self.images[row]
        cache_key = str(image)
        pixmap = self.preview_cache.get(cache_key)
        original_size = self.preview_metadata_cache.get(cache_key)
        reader = None

        if original_size is None or pixmap is None:
            reader = QImageReader(str(image))
            reader.setAutoTransform(True)
            if original_size is None:
                original_size = reader.size()
                self.preview_metadata_cache[cache_key] = QSize(original_size)

        if pixmap is None:
            if reader is None:
                reader = QImageReader(str(image))
                reader.setAutoTransform(True)
            if original_size.isValid():
                reader.setScaledSize(
                    original_size.scaled(QSize(564, 320), Qt.KeepAspectRatio)
                )
            image_data = reader.read()
            pixmap = QPixmap.fromImage(image_data) if not image_data.isNull() else QPixmap()
            self.preview_cache[cache_key] = pixmap

        if pixmap.isNull():
            self.preview_image_label.setPixmap(QPixmap())
            self.preview_image_label.setText("미리보기를 불러올 수 없습니다.")
        else:
            scaled = pixmap.scaled(
                QSize(282, 160),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.preview_image_label.setText("")
            self.preview_image_label.setPixmap(scaled)

        self.preview_name_label.setText(image.name)
        size = original_size
        if size.isValid():
            pixels = size.width() * size.height()
            mp = pixels / 1_000_000
            meta_text = f"{size.width()} × {size.height()} ({mp:.1f}MP)"
            self.preview_meta_label.setText(meta_text)
            self.preview_type_badge.setText(image.suffix.upper().lstrip('.'))
            if hasattr(self, "file_name_value"):
                self.file_name_value.setText(image.name)
                self.file_res_value.setText(f"{size.width()} × {size.height()}")
                self.file_type_value.setText(image.suffix.upper().lstrip('.'))
        else:
            self.preview_meta_label.setText("해상도 정보 없음")
            self.preview_type_badge.setText(image.suffix.upper().lstrip('.'))
            if hasattr(self, "file_name_value"):
                self.file_name_value.setText(image.name)
                self.file_res_value.setText("-")
                self.file_type_value.setText(image.suffix.upper().lstrip('.'))

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
            self.folder_status.setText("현재 폴더: 없음")
            self.folder_status.setToolTip("폴더를 선택하면 전체 경로가 표시됩니다.")
            self.count_status.setText("")
            if hasattr(self, "folder_rename_button"):
                self.folder_rename_button.setEnabled(False)
            if hasattr(self, "run_rename_button"):
                self.run_rename_button.setEnabled(False)
            return

        self.folder_status.setText(f"현재 폴더: {self.current_folder.name}")
        self.folder_status.setToolTip(str(self.current_folder))
        self.count_status.setText(f"{len(self.images)}장")
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
            self.table.setCellWidget(row, 3, self.create_status_widget("변경 완료"))

    def create_status_widget(self, text="준비됨"):
        cell = QWidget()
        cell.setObjectName("statusCell")
        layout = QHBoxLayout(cell)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(5)
        layout.setAlignment(Qt.AlignCenter)

        icon_label = QLabel()
        icon_label.setFixedSize(17, 17)
        icon_label.setPixmap(app_icon("check", 15).pixmap(QSize(15, 15)))
        icon_label.setAlignment(Qt.AlignCenter)

        text_label = QLabel(text)
        text_label.setObjectName("statusText")
        text_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        layout.addWidget(icon_label)
        layout.addWidget(text_label)
        return cell

    def load_folder(self, folder, reset_roll_info=False):
        self.cancel_thumbnail_loading()
        next_folder = Path(folder)
        if reset_roll_info and self.current_folder != next_folder:
            self.reset_roll_metadata()
        self.current_folder = next_folder
        self.update_status_bar()
        self.info.setText("폴더를 읽는 중입니다...")
        self.set_controls_enabled(False)
        QApplication.processEvents()

        try:
            self.images = find_images(folder)
            self.remove_legacy_exif_backups()
        finally:
            self.set_controls_enabled(True)

        self.thumbnail_cache = {}
        self.preview_cache = {}
        self.preview_metadata_cache = {}
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

    def remove_legacy_exif_backups(self):
        """Remove only FilmFlip's old per-image EXIF backup files."""
        for image in self.images:
            backup_path = image.with_name(image.name + ".exif.bak")
            if not backup_path.exists():
                continue
            try:
                backup_path.unlink()
            except OSError:
                # A read-only folder should still open normally.
                pass

    def set_controls_enabled(self, enabled):
        self.button.setEnabled(enabled)
        self.reverse_button.setEnabled(enabled and len(self.images) > 0)
        self.rename_button.setEnabled(enabled and len(self.images) > 0)
        if hasattr(self, "run_rename_button"):
            self.run_rename_button.setEnabled(enabled and len(self.images) > 0)
        self.undo_button.setEnabled(enabled and self.undo_button.isEnabled())

    def cancel_thumbnail_loading(self):
        self.thumbnail_generation += 1
        self.thumbnail_queue.clear()

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
            item.setText("로딩 중")

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

    def film_frame_thumbnail(self, source_pixmap, target_size):
        if source_pixmap is None or source_pixmap.isNull():
            return source_pixmap

        w = target_size.width()
        h = target_size.height()
        device_ratio = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0

        frame = QPixmap(int(w * device_ratio), int(h * device_ratio))
        frame.setDevicePixelRatio(device_ratio)
        frame.fill(Qt.transparent)

        painter = QPainter(frame)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        film_color = QColor("#15120f")
        film_edge = QColor("#8a6339")
        rail_color = QColor("#3b2b1e")
        hole_color = QColor("#e6cfaa")
        hole_shadow = QColor("#090806")

        # 35mm 네거티브 한 프레임 비율을 따라 검은 베이스, 양쪽 레일,
        # 가로로 긴 8개의 퍼포레이션을 각각 그린다.
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(film_color))
        painter.drawRect(1, 1, w - 2, h - 2)

        perf_band = max(13, int(w * 0.092))
        inner_gap = max(4, int(w * 0.025))
        inner_x = perf_band + inner_gap
        inner_y = 6
        inner_w = max(1, w - (perf_band + inner_gap) * 2)
        inner_h = max(1, h - inner_y * 2)

        scaled = source_pixmap.scaled(
            QSize(inner_w, inner_h),
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )
        crop_x = max(0, (scaled.width() - inner_w) // 2)
        crop_y = max(0, (scaled.height() - inner_h) // 2)
        cropped = scaled.copy(crop_x, crop_y, inner_w, inner_h)

        painter.drawPixmap(inner_x, inner_y, cropped)

        hole_count = 8
        pitch = (h - 10) / hole_count
        hole_w = max(6, int(perf_band * 0.55))
        hole_h = max(4, int(pitch * 0.48))
        x_left = max(3, int((perf_band - hole_w) / 2))
        x_right = w - perf_band + x_left

        painter.setRenderHint(QPainter.Antialiasing, True)
        for index in range(hole_count):
            y = int(5 + index * pitch + (pitch - hole_h) / 2)
            painter.setBrush(QBrush(hole_shadow))
            painter.drawRoundedRect(x_left - 1, y - 1, hole_w + 2, hole_h + 2, 1.4, 1.4)
            painter.drawRoundedRect(x_right - 1, y - 1, hole_w + 2, hole_h + 2, 1.4, 1.4)
            painter.setBrush(QBrush(hole_color))
            painter.drawRoundedRect(x_left, y, hole_w, hole_h, 1.1, 1.1)
            painter.drawRoundedRect(x_right, y, hole_w, hole_h, 1.1, 1.1)

        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(film_edge, 1))
        painter.drawRect(1, 1, w - 2, h - 2)
        painter.setPen(QPen(rail_color, 1))
        painter.drawLine(perf_band, 3, perf_band, h - 3)
        painter.drawLine(w - perf_band, 3, w - perf_band, h - 3)
        painter.setPen(QPen(QColor("#a47743"), 1))
        painter.drawRect(inner_x - 1, inner_y - 1, inner_w + 1, inner_h + 1)
        painter.end()
        return frame

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
            pixmap = self.film_frame_thumbnail(pixmap, target_size)

        self.thumbnail_cache[cache_key] = pixmap
        return pixmap

    def thumbnail_preset_loading_order(self):
        # 화면에 보이지 않는 두 크기까지 미리 만들면 첫 폴더 로딩에서
        # 이미지 디코딩이 3배로 늘어난다. 현재 크기만 즉시 만들고,
        # 사용자가 다른 크기를 선택했을 때 해당 크기를 캐시한다.
        return [self.thumbnail_preset_key]

    def build_thumbnail_queue(self, preset_keys=None):
        generation = self.thumbnail_generation
        preset_keys = preset_keys or self.thumbnail_preset_loading_order()
        queue = deque()

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
            queue_item = self.thumbnail_queue.popleft()

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
            preview = self.build_current_preview()
            self.table.setRowCount(len(preview))

            for row, (image, old_name, new_name) in enumerate(preview):
                self.table.setRowHeight(row, self.row_height)

                # 캐시가 있으면 즉시 되살리고, 없는 경우에만 로딩 문구를
                # 표시한다. 설정 변경이나 정렬 후 캐시된 썸네일이 사라지지 않는다.
                self.table.setItem(row, 0, self.cached_thumbnail_item(image))

                old_item = QTableWidgetItem(old_name)
                old_item.setData(Qt.UserRole, str(image))

                new_item = QTableWidgetItem(new_name)
                new_item.setData(Qt.UserRole, str(image))

                self.table.setItem(row, 1, old_item)
                self.table.setItem(row, 2, new_item)
                self.table.setCellWidget(row, 3, self.create_status_widget("준비됨"))

            self.info.setText(
                f"{len(preview)}개의 이미지를 찾았습니다."
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
        self.remember_roll_metadata(options)
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
        preview = self.build_current_preview(reverse=True)

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
        if not self.images:
            return

        dialog = RenameDialog(self)

        if dialog.exec() != QDialog.Accepted:
            return

        options = dialog.values()
        self.remember_roll_metadata(options)

        preview = build_preview(
            self.images,
            template=options["template"],
            reverse=options["reverse"],
            digits=options.get("digits", 3),
            start=options.get("start", 1),
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

        self.load_folder(folder, reset_roll_info=True)
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
            self.load_folder(folder, reset_roll_info=True)
            self.undo_button.setEnabled(False)
            event.acceptProposedAction()
            return

        QMessageBox.warning(
            self,
            "FilmFlip",
            "폴더만 드롭할 수 있습니다.",
        )
        event.ignore()
