import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ui import FilmFlipWindow


def main():
    app = QApplication(sys.argv)

    BASE_DIR = Path(__file__).resolve().parent

    if sys.platform == "darwin":
        app.setWindowIcon(QIcon(str(BASE_DIR / "assets" / "icon.icns")))
    else:
        app.setWindowIcon(QIcon(str(BASE_DIR / "assets" / "icon.ico")))

    window = FilmFlipWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()