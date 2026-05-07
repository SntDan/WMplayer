"""
程序入口
========
运行方式:
  python walkman.py
"""

from __future__ import annotations

import os
import sys

# 把脚本所在目录(即 music_player/)放到 sys.path 最前面,
# 这样 `import core` / `import ui` 在任何启动方式下都能找到。
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def main() -> int:
    from PyQt6.QtWidgets import QApplication
    from ui.main_window import MainWindow

    QApplication.setApplicationName("Music Player")
    QApplication.setOrganizationName("MusicPlayer")

    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
