from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase

from ui.theme.petrel_theme import FONT_FAMILY, FONT_SIZE_NORMAL, STYLESHEET


class Theme:
    LIGHT = "light"


def get_stylesheet(theme=Theme.LIGHT):
    return STYLESHEET


def apply_theme(app, theme=Theme.LIGHT):
    font_dir = Path(__file__).resolve().parents[1] / "resources" / "fonts"

    if font_dir.exists():
        for font_path in font_dir.glob("Poppins-*.ttf"):
            QFontDatabase.addApplicationFont(str(font_path))

    app.setFont(QFont(FONT_FAMILY, FONT_SIZE_NORMAL))
    app.setStyleSheet(STYLESHEET)