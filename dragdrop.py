from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
)


class ImageTable(QTableWidget):

    orderChanged = Signal()

    def __init__(self):
        super().__init__()

        self.setColumnCount(2)
        self.setHorizontalHeaderLabels(
            [
                "현재 파일명",
                "변경될 파일명",
            ]
        )

        self.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )

        self.verticalHeader().setVisible(False)

        self.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )

        self.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )

        self.setSelectionMode(
            QAbstractItemView.SingleSelection
        )

        self.setDragDropMode(
            QAbstractItemView.InternalMove
        )

        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)

        self.setDropIndicatorShown(True)
        self.setDragDropOverwriteMode(False)

        # 행 선택이 보기 편하게
        self.setAlternatingRowColors(True)

    def dropEvent(self, event):
        super().dropEvent(event)
        self.orderChanged.emit()