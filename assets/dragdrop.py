from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
)


class ImageTable(QTableWidget):

    from PySide6.QtCore import Signal
    orderChanged = Signal()
    rowDoubleClicked = Signal(int)

    MIME_TYPE = "application/x-filmflip-row"

    def __init__(self):
        super().__init__()

        self._drag_start_position = None
        self._drag_source_row = -1

        self.setColumnCount(3)
        self.setHorizontalHeaderLabels(
            [
                "썸네일",
                "현재 파일명",
                "변경될 파일명",
            ]
        )

        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.setColumnWidth(0, 156)

        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(122)

        self.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )
        self.setSelectionMode(
            QAbstractItemView.SingleSelection
        )

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
        self.setStyleSheet(
            """
            QTableWidget::item:selected {
                background-color: #3f5f8f;
            }
            QTableWidget::item:hover {
                background-color: #333333;
            }
            """
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_position = event.position().toPoint()
            self._drag_source_row = self.rowAt(
                self._drag_start_position.y()
            )

            if self._drag_source_row >= 0:
                self.selectRow(self._drag_source_row)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not event.buttons() & Qt.LeftButton:
            return super().mouseMoveEvent(event)

        if self._drag_start_position is None:
            return super().mouseMoveEvent(event)

        distance = (
            event.position().toPoint()
            - self._drag_start_position
        ).manhattanLength()

        if distance < QApplication.startDragDistance():
            return super().mouseMoveEvent(event)

        if self._drag_source_row < 0:
            return super().mouseMoveEvent(event)

        mime = QMimeData()
        mime.setData(
            self.MIME_TYPE,
            str(self._drag_source_row).encode("utf-8"),
        )

        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.MoveAction)

    def mouseDoubleClickEvent(self, event):
        try:
            pos=event.position().toPoint()
        except AttributeError:
            pos=event.pos()
        row=self.rowAt(pos.y())
        if row>=0:
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

        row_rect = self.visualRect(
            self.model().index(target_row, 0)
        )

        if y_position > row_rect.center().y():
            return target_row + 1

        return target_row

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(self.MIME_TYPE):
            event.ignore()
            return

        try:
            source_row = int(
                bytes(
                    event.mimeData().data(self.MIME_TYPE)
                ).decode("utf-8")
            )
        except Exception:
            event.ignore()
            return

        try:
            drop_pos = event.position().toPoint()
        except AttributeError:
            drop_pos = event.pos()

        if source_row < 0 or source_row >= self.rowCount():
            event.ignore()
            return

        insert_row = self._drop_insert_row(drop_pos.y())
        insert_row = max(0, min(insert_row, self.rowCount()))

        # 자기 자신 위치에 다시 놓은 경우는 아무 것도 하지 않는다.
        if insert_row == source_row or insert_row == source_row + 1:
            self.selectRow(source_row)
            event.setDropAction(Qt.MoveAction)
            event.accept()
            return

        row_items = []

        for column in range(self.columnCount()):
            row_items.append(self.takeItem(source_row, column))

        self.removeRow(source_row)

        if insert_row > source_row:
            insert_row -= 1

        insert_row = max(0, min(insert_row, self.rowCount()))
        self.insertRow(insert_row)
        self.setRowHeight(insert_row, 122)

        for column, item in enumerate(row_items):
            if item is not None:
                self.setItem(insert_row, column, item)

        self.selectRow(insert_row)
        for row in range(self.rowCount()):
            self.setRowHeight(row,122)
        event.setDropAction(Qt.MoveAction)
        event.accept()
        self.orderChanged.emit()
