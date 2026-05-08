"""
主题模块
========
集中管理颜色 / 字号 / 间距,方便后续切换皮肤。
"""

from PyQt6.QtGui import QColor


class Theme:
    # 与草图一致:黑底,白色为布局/文字,红色为按钮
    BG = QColor("#000000")
    PANEL_BG = QColor("#000000")
    BORDER = QColor("#FFFFFF")
    TEXT = QColor("#FFFFFF")
    TEXT_DIM = QColor("#9E9E9E")
    ACCENT = QColor("#E63946")           # 红色 - 功能性按钮
    ACCENT_HOVER = QColor("#FF5A66")
    PROGRESS_BG = QColor("#3A3A3A")
    PROGRESS_FG = QColor("#FFFFFF")
    LIST_HIGHLIGHT = QColor("#1F1F1F")
    LIST_SELECTED = QColor("#2C2C2C")
    LIST_PLAYING = QColor("#E63946")


# 共用按钮样式(深色面板上的次级按钮: 添加文件夹/扫描/浏览…等)
BTN_QSS = (
    "QPushButton{background:#1a1a1a; border:1px solid #333; "
    "padding:4px 10px; border-radius:4px; color:#FFF;}"
    "QPushButton:hover{background:#2a2a2a; border-color:#E63946;}"
    "QPushButton:disabled{color:#555;}"
)

# 红底主操作按钮(返回/播放全部/确定 等)
PRIMARY_BTN_QSS = (
    "QPushButton{background:#E63946; color:#FFF; border:none; "
    "padding:6px 12px; border-radius:4px; font-weight:bold;}"
    "QPushButton:hover{background:#d62828;}"
)


GLOBAL_QSS = """
QWidget {
    background-color: #000000;
    color: #FFFFFF;
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
}

QToolTip {
    background-color: #1F1F1F;
    color: #FFFFFF;
    border: 1px solid #333333;
    padding: 4px 8px;
}

QListWidget {
    background-color: #000000;
    border: 1px solid #FFFFFF;
    border-style: solid;
    border-color: #FFFFFF;
    border-width: 1px;
    outline: 0;
    padding: 4px;
}
QListWidget::item {
    padding: 0;
    border-radius: 0;
    margin: 0;
}
QListWidget::item:hover {
    background-color: #1F1F1F;
}
QListWidget::item:selected {
    background-color: #2C2C2C;
    color: #FFFFFF;
}

QScrollBar:vertical {
    background: transparent;
    width: 4px;
    margin: 2px 0;
}
QScrollBar::handle:vertical {
    background: #1f1f1f;
    border-radius: 2px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: #333333;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
    background: transparent;
}
QScrollBar:horizontal {
    background: transparent;
    height: 4px;
    margin: 0 2px;
}
QScrollBar::handle:horizontal {
    background: #1f1f1f;
    border-radius: 2px;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover {
    background: #333333;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
    background: transparent;
}

QPushButton {
    background: transparent;
    border: none;
    color: #FFFFFF;
}
QPushButton:hover {
    color: #FF5A66;
}

QSlider::groove:horizontal {
    height: 4px;
    background: #3A3A3A;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: #FFFFFF;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #FFFFFF;
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}
QSlider::handle:horizontal:hover {
    background: #FF5A66;
}

QDialog {
    background-color: #0a0a0a;
}
QLineEdit, QSpinBox, QComboBox {
    background-color: #1a1a1a;
    border: 1px solid #333333;
    padding: 4px 6px;
    border-radius: 3px;
}
QCheckBox {
    spacing: 8px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #555555;
    border-radius: 3px;
    background: #0a0a0a;
}
QCheckBox::indicator:checked {
    background: #E63946;
    border: 1px solid #E63946;
}
"""
