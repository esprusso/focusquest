"""Allow running FocusQuest as a module: python -m focusquest."""

import sys

from PyQt6.QtWidgets import QApplication

from .database.db import init_db
from .app import FocusQuestApp


def main() -> None:
    init_db()
    print("FocusQuest ready!")

    app = QApplication(sys.argv)
    app.setApplicationName("FocusQuest")
    app.setOrganizationName("FocusQuest")
    app.setQuitOnLastWindowClosed(False)

    # Dock icon (generated placeholder — accent purple circle)
    from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
    icon = QPixmap(256, 256)
    icon.fill(QColor(0, 0, 0, 0))
    p = QPainter(icon)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#CBA6F7"))
    p.setPen(QColor("#CBA6F7").darker(120))
    p.drawEllipse(16, 16, 224, 224)
    p.end()
    app.setWindowIcon(QIcon(icon))

    window = FocusQuestApp()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
