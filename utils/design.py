from pathlib import Path

from PySide6.QtCore import QDir, QEvent, QObject, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QProxyStyle,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleFactory,
    QStyleOptionViewItem,
    QWidget,
)

BASE_DIR = Path(__file__).resolve().parent.parent
QDir.addSearchPath("filmflipicons", str(BASE_DIR / "assets" / "icons"))

FIELD_ICON_NAMES = {
    "date": "calendar",
    "camera": "camera",
    "lens": "lens",
    "film": "film",
    "iso": "iso",
    "lab": "lab",
    "place": "location",
    "location": "location",
    "scanner": "scanner",
    "memo": "memo",
    "number": "rename",
}

def asset_path(*parts):
    return BASE_DIR / "assets" / Path(*parts)

def icon_path(name):
    return asset_path("icons", f"{name}.svg")


def app_icon(name, size=24):
    """Load one SVG consistently in every Qt icon state."""
    path = icon_path(name)
    icon = QIcon()
    if not path.exists():
        return icon

    pixmap = QIcon(str(path)).pixmap(QSize(size, size))
    for mode in (QIcon.Normal, QIcon.Disabled, QIcon.Active, QIcon.Selected):
        icon.addPixmap(pixmap, mode, QIcon.Off)
        icon.addPixmap(pixmap, mode, QIcon.On)
    return icon


def set_button_icon(button, name, size=20):
    button.setIcon(app_icon(name, size))
    button.setIconSize(QSize(size, size))
    return button


class FilmFlipProxyStyle(QProxyStyle):
    """Replace Qt's dated native message symbols with FilmFlip icons."""

    MESSAGE_ICONS = {
        QStyle.SP_MessageBoxInformation: "message_info",
        QStyle.SP_MessageBoxWarning: "message_warning",
        QStyle.SP_MessageBoxCritical: "message_error",
        QStyle.SP_MessageBoxQuestion: "message_question",
    }

    def standardIcon(self, standard_icon, option=None, widget=None):
        icon_name = self.MESSAGE_ICONS.get(standard_icon)
        if icon_name:
            return app_icon(icon_name, 64)
        return super().standardIcon(standard_icon, option, widget)


class ComboPopupDelegate(QStyledItemDelegate):
    """Paint popup colors consistently instead of relying on the OS palette."""

    def __init__(
        self,
        hover_color,
        selected_color,
        foreground_color,
        background_color,
        parent=None,
    ):
        super().__init__(parent)
        self.hover_color = QColor(hover_color)
        self.selected_color = QColor(selected_color)
        self.foreground_color = QColor(foreground_color)
        self.background_color = QColor(background_color)

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        for group in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
            opt.palette.setColor(group, QPalette.Text, self.foreground_color)
            opt.palette.setColor(group, QPalette.WindowText, self.foreground_color)
            opt.palette.setColor(group, QPalette.HighlightedText, self.foreground_color)
            opt.palette.setColor(group, QPalette.Base, self.background_color)
            opt.palette.setColor(group, QPalette.Window, self.background_color)

        # Windows의 네이티브 팝업 팔레트가 다크 모드 색상을 덮어쓰더라도
        # 각 행의 기본 배경과 글자가 항상 같은 명암 조합으로 그려지게 한다.
        painter.fillRect(opt.rect, self.background_color)
        hovered = bool(opt.state & QStyle.State_MouseOver)
        selected = bool(opt.state & QStyle.State_Selected)
        fill = self.hover_color if hovered else self.selected_color if selected else None
        if fill is not None:
            fill_rect = opt.rect.adjusted(4, 0, -4, 0)
            fill_height = min(fill_rect.height(), opt.fontMetrics.height() + 2)
            # macOS의 한글 글리프는 행의 기하학적 중앙보다 살짝 위에 보인다.
            # 배경도 글자의 시각적 중심에 맞춰 1px 위로 보정한다.
            vertical_gap = max(0, opt.rect.height() - fill_height)
            fill_top = opt.rect.top() + vertical_gap // 2 - 1
            fill_rect.setTop(max(opt.rect.top(), fill_top))
            fill_rect.setHeight(fill_height)
            painter.save()
            painter.setPen(Qt.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(fill_rect, 5, 5)
            painter.restore()

        # QStyledItemDelegate의 기본 텍스트 그리기는 부모 QSS의 더 구체적인
        # ::item 색상 규칙을 다시 가져올 수 있다. Windows에서는 이 때문에
        # 일반 모드의 어두운 글자가 다크 팝업에 남으므로 텍스트를 직접 그린다.
        text_rect = opt.rect.adjusted(12, 0, -10, 0)
        if not opt.icon.isNull():
            icon_size = opt.decorationSize if opt.decorationSize.isValid() else QSize(16, 16)
            icon_rect = text_rect
            icon_rect.setWidth(icon_size.width())
            icon_rect.setHeight(icon_size.height())
            icon_rect.moveTop(opt.rect.top() + (opt.rect.height() - icon_size.height()) // 2)
            opt.icon.paint(painter, icon_rect, Qt.AlignCenter)
            text_rect.setLeft(icon_rect.right() + 7)

        painter.save()
        painter.setPen(self.foreground_color)
        painter.setFont(opt.font)
        painter.drawText(
            text_rect,
            Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
            opt.text,
        )
        painter.restore()


class ComboPopupSizer(QObject):
    """Keep short combo lists from opening as oversized blank panels."""

    def __init__(self, combo, parent=None):
        super().__init__(parent)
        self.combo = combo

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Show:
            QTimer.singleShot(0, self.adjust_popup)
        return super().eventFilter(watched, event)

    def adjust_popup(self):
        view = self.combo.view()
        visible_rows = min(self.combo.count(), self.combo.maxVisibleItems())
        row_height = max(25, view.sizeHintForRow(0)) if visible_rows else 25
        view_height = visible_rows * row_height + 8
        view.setFixedHeight(view_height)
        popup = view.window()
        popup.setFixedHeight(view_height + 8)


def polish_combo_box(combo, dark_mode=False):
    """Give a combo popup a visible, platform-independent hover state."""
    view = combo.view()
    old_sizer = getattr(combo, "_filmflip_popup_sizer", None)
    if old_sizer is not None:
        view.window().removeEventFilter(old_sizer)
        old_sizer.deleteLater()
    old_delegate = getattr(combo, "_filmflip_popup_delegate", None)
    combo.setMaxVisibleItems(5)
    view.setMaximumHeight(133)
    fusion_style = QStyleFactory.create("Fusion")
    if fusion_style is not None:
        view.setStyle(fusion_style)
    view.setMouseTracking(True)
    view.viewport().setMouseTracking(True)
    if dark_mode:
        background = "#211d17"
        foreground = "#f2dfbd"
        hover = "#5a4228"
        selected = "#6b4c31"
        border = "#6a5747"
    else:
        background = "#fffaf1"
        foreground = "#241b14"
        hover = "#efd6b5"
        selected = "#dfbd91"
        border = "#d4c6b3"

    popup_palette = view.palette()
    for group in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
        popup_palette.setColor(group, QPalette.Text, QColor(foreground))
        popup_palette.setColor(group, QPalette.WindowText, QColor(foreground))
        popup_palette.setColor(group, QPalette.HighlightedText, QColor(foreground))
        popup_palette.setColor(group, QPalette.Base, QColor(background))
        popup_palette.setColor(group, QPalette.Window, QColor(background))
        popup_palette.setColor(group, QPalette.Highlight, QColor(selected))
    view.setPalette(popup_palette)
    view.viewport().setPalette(popup_palette)
    view.window().setPalette(popup_palette)
    view.viewport().setAutoFillBackground(True)
    view.setStyleSheet(
        f"QAbstractItemView {{ background: {background}; color: {foreground}; "
        f"border: 1px solid {border}; outline: 0px; padding: 3px; "
        f"selection-background-color: {selected}; selection-color: {foreground}; }} "
        "QAbstractItemView::item { min-height: 21px; padding: 2px 8px; "
        f"border: 0px; border-radius: 5px; margin: 0px 2px; color: {foreground}; }} "
        f"QAbstractItemView::item:hover {{ background-color: {hover}; color: {foreground}; }} "
        f"QAbstractItemView::item:selected {{ background-color: {selected}; color: {foreground}; }}"
    )
    delegate = ComboPopupDelegate(hover, selected, foreground, background, view)
    view.setItemDelegate(delegate)
    if old_delegate is not None:
        old_delegate.deleteLater()
    sizer = ComboPopupSizer(combo, view.window())
    view.window().installEventFilter(sizer)
    combo._filmflip_popup_delegate = delegate
    combo._filmflip_popup_sizer = sizer
    return combo


def polish_combo_boxes(root, dark_mode=False):
    for combo in root.findChildren(QComboBox):
        polish_combo_box(combo, dark_mode)


def icon_text_widget(text, icon_name, size=22):
    """Return a compact field label with a full-color SVG icon."""
    widget = QWidget()
    widget.setObjectName("iconTextWidget")
    widget.setAutoFillBackground(False)
    widget.setStyleSheet(
        "QWidget#iconTextWidget { background: transparent; border: 0px; } "
        "QWidget#iconTextWidget QLabel { background: transparent; border: 0px; padding: 0px; }"
    )
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(7)

    icon_label = QLabel()
    icon_label.setFixedSize(size, size)
    icon_label.setAlignment(Qt.AlignCenter)
    icon_label.setPixmap(app_icon(icon_name, size).pixmap(QSize(size, size)))

    text_label = QLabel(text)
    text_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    text_label.setStyleSheet("background: transparent; border: 0px; padding: 0px; font-weight: 750;")

    layout.addWidget(icon_label)
    layout.addWidget(text_label)
    widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
    return widget


def field_icon_name(key):
    return FIELD_ICON_NAMES.get(key, "memo")


def dialog_theme_override(dark_mode):
    if not dark_mode:
        return ""
    return """
        QDialog { background: #27231f; color: #f4eadc; }
        QLabel { color: #f4eadc; }
        QGroupBox { background: #342e28; border-color: #5a4b3e; color: #f3dfbf; }
        QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QDateEdit, QDateTimeEdit {
            background: #1f1b18; color: #f7ebda; border-color: #665544;
        }
        QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QPlainTextEdit:hover, QDateEdit:hover, QDateTimeEdit:hover,
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus, QDateEdit:focus, QDateTimeEdit:focus {
            background: #352a22; color: #fff0dc; border-color: #b78958;
        }
        QComboBox QAbstractItemView {
            background: #1f1b18; color: #f7ebda; border: 1px solid #665544;
            selection-background-color: #75543a; selection-color: #fff7eb;
        }
        QComboBox QAbstractItemView::item { color: #f7ebda; }
        QComboBox QAbstractItemView::item:hover { background: #60452f; color: #fff7eb; }
        QComboBox QAbstractItemView::item:selected { background: #75543a; color: #fff7eb; }
        QComboBox::drop-down {
            background: #302821; border-left: 1px solid #665544;
            border-top-right-radius: 6px; border-bottom-right-radius: 6px;
        }
        QComboBox::down-arrow { image: url(filmflipicons:chevron_down_light.svg); width: 13px; height: 13px; }
        QDateEdit::drop-down {
            background: #302821; border-left: 1px solid #665544;
            border-top-right-radius: 6px; border-bottom-right-radius: 6px;
        }
        QDateEdit::down-arrow { image: url(filmflipicons:calendar.svg); width: 17px; height: 17px; }
        QListWidget { background: #15120f; color: #f7ebda; border-color: #5a4b3e; }
        QPushButton { background: #3b322a; color: #f4dfbf; border-color: #705a44; }
        QPushButton:hover { background: #4a3b30; }
        QCheckBox, QRadioButton { color: #f4eadc; }
    """

def load_qss():
    qss_path = asset_path("styles", "filmflip.qss")
    try:
        return qss_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
