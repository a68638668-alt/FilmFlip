from PySide6.QtCore import QMimeData, Qt, Signal, QTimer
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
)


class ImageTable(QTableWidget):
    """FilmFlip 메인 이미지 테이블.

    v1.1 performance notes:
    - 행 높이를 매번 전체 순회로 재설정하지 않는다.
    - 드롭 처리 중에는 화면 업데이트를 잠시 멈춰 깜빡임/버벅임을 줄인다.
    - 드래그 시작 상태를 exec 이후 초기화해 중복 드래그 시도를 줄인다.
    """

    orderChanged = Signal()
    rowMoveRequested = Signal(int, int)
    rowDoubleClicked = Signal(int)

    MIME_TYPE = "application/x-filmflip-row"
    THUMBNAIL_COLUMN_WIDTH = 156
    ROW_HEIGHT = 122

    def __init__(self):
        super().__init__()

        self._drag_start_position = None
        self._drag_source_row = -1

        self.setColumnCount(4)
        self.setHorizontalHeaderLabels(
            [
                "썸네일",
                "현재 파일명",
                "변경될 파일명",
                "상태",
            ]
        )

        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.setColumnWidth(0, self.THUMBNAIL_COLUMN_WIDTH)
        self.setColumnWidth(3, 122)

        vertical_header = self.verticalHeader()
        vertical_header.setVisible(False)
        vertical_header.setDefaultSectionSize(self.ROW_HEIGHT)
        vertical_header.setMinimumSectionSize(self.ROW_HEIGHT)

        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)

        # Qt 기본 InternalMove는 셀 위 드롭 시 아이템이 비는 경우가 있어
        # 기본 이동은 쓰지 않고, 아래 이벤트에서 행 이동을 직접 처리한다.
        self.setDragEnabled(False)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setDragDropOverwriteMode(False)
        self.setDefaultDropAction(Qt.MoveAction)

        self.setAlternatingRowColors(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scrollbar_hide_timer = QTimer(self)
        self._scrollbar_hide_timer.setSingleShot(True)
        self._scrollbar_hide_timer.setInterval(850)
        self._scrollbar_hide_timer.timeout.connect(self._hide_scrollbars)
        # 썸네일 위에서 마우스를 움직일 때마다 hover 스타일이
        # 셀 전체 repaint를 유발할 수 있어 선택 색상만 유지한다.
        self.setStyleSheet(
            """
            QTableWidget::item:selected {
                background-color: #3b2d20;
            }
            """
        )

    def wheelEvent(self, event):
        """Reveal the scrollbar only while the user is actively scrolling."""
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        super().wheelEvent(event)
        self._scrollbar_hide_timer.start()

    def _hide_scrollbars(self):
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def _event_pos(self, event):
        try:
            return event.position().toPoint()
        except AttributeError:
            return event.pos()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_position = self._event_pos(event)
            self._drag_source_row = self.rowAt(self._drag_start_position.y())

            if self._drag_source_row >= 0:
                self.selectRow(self._drag_source_row)

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start_position = None
        self._drag_source_row = -1
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if not event.buttons() & Qt.LeftButton:
            return super().mouseMoveEvent(event)

        if self._drag_start_position is None or self._drag_source_row < 0:
            return super().mouseMoveEvent(event)

        distance = (self._event_pos(event) - self._drag_start_position).manhattanLength()
        if distance < QApplication.startDragDistance():
            return super().mouseMoveEvent(event)

        mime = QMimeData()
        mime.setData(self.MIME_TYPE, str(self._drag_source_row).encode("utf-8"))

        drag = QDrag(self)
        drag.setMimeData(mime)

        try:
            drag.exec(Qt.MoveAction)
        finally:
            self._drag_start_position = None
            self._drag_source_row = -1

    def mouseDoubleClickEvent(self, event):
        row = self.rowAt(self._event_pos(event).y())
        if row >= 0:
            self.rowDoubleClicked.emit(row)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(self.MIME_TYPE):
            event.setDropAction(Qt.MoveAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(self.MIME_TYPE):
            event.setDropAction(Qt.MoveAction)
            event.accept()
        else:
            event.ignore()

    def _drop_insert_row(self, y_position):
        """
        드롭 위치를 행 삽입 위치로 변환한다.
        - 행 위쪽 절반: 해당 행 앞에 삽입
        - 행 아래쪽 절반: 해당 행 뒤에 삽입
        - 테이블 빈 공간: 맨 아래 삽입
        """
        target_row = self.rowAt(y_position)

        if target_row < 0:
            return self.rowCount()

        row_rect = self.visualRect(self.model().index(target_row, 0))
        if y_position > row_rect.center().y():
            return target_row + 1

        return target_row

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(self.MIME_TYPE):
            event.ignore()
            return

        try:
            source_row = int(bytes(event.mimeData().data(self.MIME_TYPE)).decode("utf-8"))
        except Exception:
            event.ignore()
            return

        if source_row < 0 or source_row >= self.rowCount():
            event.ignore()
            return

        drop_pos = self._event_pos(event)
        insert_row = self._drop_insert_row(drop_pos.y())
        insert_row = max(0, min(insert_row, self.rowCount()))

        # 자기 자신 위치에 다시 놓은 경우는 아무 것도 하지 않는다.
        if insert_row == source_row or insert_row == source_row + 1:
            self.selectRow(source_row)
            event.setDropAction(Qt.MoveAction)
            event.accept()
            return

        destination_row = insert_row - 1 if insert_row > source_row else insert_row
        destination_row = max(0, min(destination_row, self.rowCount() - 1))

        event.setDropAction(Qt.MoveAction)
        event.accept()

        # QTableWidget의 셀 위젯을 removeRow 중에 옮기면 macOS Qt가 이미
        # 삭제 예약한 네이티브 위젯을 다시 참조해 종료될 수 있다. 드롭 이벤트가
        # 끝난 다음 상위 창이 이미지 목록을 바꾸고 테이블을 안전하게 재생성한다.
        QTimer.singleShot(
            0,
            lambda source=source_row, destination=destination_row:
                self.rowMoveRequested.emit(source, destination),
        )
