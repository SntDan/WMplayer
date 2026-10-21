"""Application entry point."""

from __future__ import annotations

import os
import sys

# Put the project directory first so `core` and `ui` imports work
# regardless of how the app is launched.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def main() -> int:
    from core.windows_identity import configure_windows_identity

    configure_windows_identity()

    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication

    from ui.main_window import MainWindow

    QApplication.setApplicationName("WMplayer")
    QApplication.setOrganizationName("WMplayer")

    # Let Qt 6 configure per-monitor DPI awareness before creating any windows.
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(os.path.join(_HERE, "assets", "wmplayer.ico")))
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
