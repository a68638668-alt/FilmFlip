from PySide6.QtWidgets import QMessageBox


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
    QMessageBox.information(
        parent,
        "FilmFlip",
        f"✅ {count}개의 파일명을 변경했습니다.",
    )


def no_images(parent):
    QMessageBox.information(
        parent,
        "FilmFlip",
        "이미지가 없습니다.",
    )


def rename_failed(parent, error):
    QMessageBox.critical(
        parent,
        "FilmFlip",
        f"오류가 발생했습니다.\n\n{error}",
    )