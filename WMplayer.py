"""Application entry point."""

from __future__ import annotations

import os
import sys

# Put the project directory first so `core` and `ui` imports work
# regardless of how the app is launched.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("WMplayer.WMplayer")
    except Exception:
        pass


def main() -> int:
    _set_windows_app_id()

    from PyQt6.QtWidgets import QApplication
    from ui.main_window import MainWindow

    QApplication.setApplicationName("WMplayer")
    QApplication.setOrganizationName("WMplayer")

    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
