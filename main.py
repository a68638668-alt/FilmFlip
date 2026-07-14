import signal
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ui import FilmFlipWindow
from utils.design import FilmFlipProxyStyle

APP_NAME = "FilmFlip"
APP_VERSION = "2.0.0"


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
    app.setStyle(FilmFlipProxyStyle(app.style()))
    apply_app_metadata(app)

    # Let terminal Ctrl-C / SIGTERM close Qt cleanly during local development.
    # Without a small Python callback tick, macOS can leave the Qt event loop
    # running and a forced stop may be reported as a Python crash.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    signal_timer = QTimer(app)
    signal_timer.timeout.connect(lambda: None)
    signal_timer.start(200)

    window = FilmFlipWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
