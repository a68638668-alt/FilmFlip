import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ui import FilmFlipWindow

APP_NAME = "FilmFlip"
APP_VERSION = "1.1"


def resource_path(*parts: str) -> Path:
    """Return a path that works in source runs and PyInstaller builds."""
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base_dir.joinpath(*parts)


def apply_app_metadata(app: QApplication) -> None:
    QCoreApplication.setApplicationName(APP_NAME)
    QCoreApplication.setApplicationVersion(APP_VERSION)
    QCoreApplication.setOrganizationName(APP_NAME)

    icon_name = "icon.icns" if sys.platform == "darwin" else "icon.ico"
    icon_path = resource_path("assets", icon_name)

    # Missing icons should not prevent local dev runs or Windows/macOS builds from opening.
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))


def main() -> None:
    app = QApplication(sys.argv)
    apply_app_metadata(app)

    window = FilmFlipWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
