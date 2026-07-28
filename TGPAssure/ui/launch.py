from __future__ import annotations

from pathlib import Path

from core.infrastructure.resource_paths import resource_path

from PySide6.QtCore import Qt, QTimer, QRect, QPoint, QSize, QElapsedTimer
from PySide6.QtGui import (
    QColor, QFont, QLinearGradient, QRadialGradient, QPainter, QPixmap,
    QGuiApplication, QMouseEvent, QResizeEvent,
)
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget, QSplashScreen, QFrame, QGraphicsDropShadowEffect,
    QScrollArea, QSizePolicy,
)


# ----------------------------------------------------------------------------
# Splash screen — workstation-style launcher
# ----------------------------------------------------------------------------

SPLASH_WIDTH = 440
SPLASH_HEIGHT = 455
# Keep the launcher visible long enough for branding/status to be readable.
# If startup itself takes longer than this, the splash remains until startup is ready.
MIN_SPLASH_VISIBLE_MS = 5000


class StartupSplash(QSplashScreen):
    """Compact branded launcher inspired by classic geoscience workstations.

    The composition intentionally uses only TGPAssure branding/assets: a dark
    graphite panel, logo/wordmark, diagonal gold accent, project imagery, and a
    small status line. No third-party branding is embedded.
    """

    def __init__(self) -> None:
        pixmap = self._build_launcher(SPLASH_WIDTH, SPLASH_HEIGHT)
        super().__init__(pixmap)
        self.setWindowFlag(Qt.WindowStaysOnTopHint)
        self.setWindowFlag(Qt.FramelessWindowHint)

        self.status_label = QLabel("Initializing…", self)
        self.status_label.setGeometry(34, self.height() - 88, self.width() - 68, 20)
        self.status_label.setStyleSheet(
            "color:#E7C85D; background:transparent; font-size:9pt; font-weight:600;"
        )

        self.progress_value = 0
        self._allow_close = False
        self._pending_finish_widget = None
        self._visible_timer = QElapsedTimer()
        self._visible_timer.start()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_progress)
        # About 4.7 s to reach 100%, matching the 5 s minimum splash time.
        self.timer.start(140)

    @staticmethod
    def _load_logo() -> QPixmap:
        """Load the high-resolution branding logo used inside the launcher.

        logo.ico is intentionally NOT used here. The ICO is reserved for the
        Windows executable/application icon; raster artwork in the launcher
        should come from logo.png to avoid blurred upscaling.
        """
        path = resource_path("assets", "logo", "logo.png")
        pix = QPixmap(str(path))
        return pix if not pix.isNull() else QPixmap()

    @staticmethod
    def _load_background() -> QPixmap:
        for path in (
            resource_path("assets", "poster", "background.png"),
            resource_path("assets", "poster", "poster.png"),
            resource_path("assets", "poster", "splash.png"),
        ):
            pix = QPixmap(str(path))
            if not pix.isNull():
                return pix
        return QPixmap()

    @classmethod
    def _build_launcher(cls, width: int, height: int) -> QPixmap:
        canvas = QPixmap(width, height)
        canvas.fill(Qt.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Main graphite card.
        panel = QRect(8, 8, width - 16, height - 16)
        gradient = QLinearGradient(panel.topLeft(), panel.bottomLeft())
        gradient.setColorAt(0.0, QColor("#696A6D"))
        gradient.setColorAt(0.52, QColor("#4F5053"))
        gradient.setColorAt(1.0, QColor("#393A3C"))
        painter.setPen(QColor("#343537"))
        painter.setBrush(gradient)
        painter.drawRect(panel)

        # Lower-right geological/project image area.
        bg = cls._load_background()
        image_rect = QRect(width // 2 - 18, height // 2 + 14, width // 2 + 10, height // 2 - 30)
        if not bg.isNull():
            scaled = bg.scaled(image_rect.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            crop_x = max(0, (scaled.width() - image_rect.width()) // 2)
            crop_y = max(0, (scaled.height() - image_rect.height()) // 2)
            painter.drawPixmap(image_rect, scaled.copy(crop_x, crop_y, image_rect.width(), image_rect.height()))
            painter.fillRect(image_rect, QColor(30, 30, 30, 58))

        # Diagonal signature line separating graphite and image.
        painter.setPen(QColor("#D9A51B"))
        painter.setBrush(QColor("#D9A51B"))
        points = [
            QPoint(9, height - 104),
            QPoint(width - 9, height // 2 - 8),
            QPoint(width - 9, height // 2 + 1),
            QPoint(9, height - 95),
        ]
        from PySide6.QtGui import QPolygon
        painter.drawPolygon(QPolygon(points))

        # Brand block.
        logo = cls._load_logo()
        logo_rect = QRect(38, 42, 58, 58)
        if not logo.isNull():
            painter.drawPixmap(logo_rect, logo.scaled(logo_rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            painter.fillRect(logo_rect, QColor("#D9A51B"))
            painter.setPen(Qt.white)
            painter.setFont(QFont("Segoe UI", 23, QFont.Bold))
            painter.drawText(logo_rect, Qt.AlignCenter, "T")

        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(QFont("Segoe UI", 29, QFont.Bold))
        painter.drawText(QRect(108, 38, 280, 54), Qt.AlignVCenter | Qt.AlignLeft, "TGPAssure")

        painter.setPen(QColor("#F2F2F2"))
        painter.setFont(QFont("Segoe UI", 12, QFont.Normal))
        painter.drawText(QRect(38, 102, 350, 42), Qt.AlignLeft | Qt.AlignTop, "Geophysical assurance — confident decisions")

        painter.setPen(QColor(245, 245, 245, 225))
        painter.setFont(QFont("Segoe UI", 8, QFont.Normal))
        painter.drawText(
            QRect(240, height - 76, 165, 42),
            Qt.AlignRight | Qt.AlignBottom,
            "TGPAssure E&P Software Platform\nTethyan Geophysical Prospecting",
        )
        painter.setPen(QColor(235, 235, 235, 175))
        painter.setFont(QFont("Segoe UI", 7))
        painter.drawText(QRect(38, height - 42, 180, 18), Qt.AlignLeft | Qt.AlignVCenter, "Enterprise geoscience workstation")

        painter.end()
        return canvas

    def _update_progress(self) -> None:
        self.progress_value = min(100, self.progress_value + 3)
        if self.progress_value < 25:
            text = "Initializing services…"
        elif self.progress_value < 50:
            text = "Loading geophysical modules…"
        elif self.progress_value < 75:
            text = "Preparing project workspace…"
        elif self.progress_value < 100:
            text = "Restoring application state…"
        else:
            text = "Launching TGPAssure…"
            self.timer.stop()
        self.status_label.setText(text)

    def _remaining_minimum_time_ms(self) -> int:
        if not self._visible_timer.isValid():
            return 0
        return max(0, MIN_SPLASH_VISIBLE_MS - int(self._visible_timer.elapsed()))

    def _close_now(self) -> None:
        self._allow_close = True
        super().close()

    def close(self) -> bool:
        """Respect a minimum visible duration even when startup finishes fast."""
        if self._allow_close:
            return super().close()

        remaining = self._remaining_minimum_time_ms()
        if remaining > 0:
            QTimer.singleShot(remaining, self._close_now)
            return False

        self._allow_close = True
        return super().close()

    def finish(self, widget: QWidget) -> None:
        """Delay QSplashScreen.finish() until the minimum branding time expires."""
        remaining = self._remaining_minimum_time_ms()
        if remaining > 0:
            self._pending_finish_widget = widget
            QTimer.singleShot(remaining, self._finish_pending)
            return
        super().finish(widget)

    def _finish_pending(self) -> None:
        widget = self._pending_finish_widget
        self._pending_finish_widget = None
        if widget is not None:
            super().finish(widget)
        else:
            self._close_now()

    def set_stage(self, message: str) -> None:
        self.status_label.setText(str(message))


# ----------------------------------------------------------------------------
# Tutorial dialog — responsive, draggable, resizable
# ----------------------------------------------------------------------------

RESIZE_MARGIN = 8


class TutorialDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle('Welcome to TGPAssure')
        self.setMinimumSize(640, 460)
        self.resize(860, 580)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)

        # -- drag / resize state --
        self._drag_pos: QPoint | None = None
        self._resize_edge: str | None = None
        self._resizing = False

        outer_margin = 16
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(outer_margin, outer_margin, outer_margin, outer_margin)

        self.container = QFrame(self)
        self.container.setObjectName('container')
        self.container.setMouseTracking(True)
        self.container.setStyleSheet("""
            QFrame#container {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #FFFFFF, stop: 1 #F8FAFC);
                border-radius: 20px;
                border: 1px solid rgba(255, 255, 255, 0.2);
            }
        """)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 10)
        self.container.setGraphicsEffect(shadow)
        main_layout.addWidget(self.container)

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # -- header (draggable) --
        self.header = QWidget()
        self.header.setMinimumHeight(90)
        self.header.setMaximumHeight(120)
        self.header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.header.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #0B1F33, stop: 1 #145E8C);
                border-top-left-radius: 20px;
                border-top-right-radius: 20px;
            }
        """)
        self.header.mousePressEvent = self._header_mouse_press
        self.header.mouseMoveEvent = self._header_mouse_move
        self.header.mouseReleaseEvent = self._header_mouse_release

        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(36, 20, 24, 20)

        title_widget = QWidget()
        title_layout = QVBoxLayout(title_widget)
        title_layout.setSpacing(4)
        title_layout.setContentsMargins(0, 0, 0, 0)

        self.main_title = QLabel('🚀 TGPAssure')
        self.main_title.setStyleSheet("""
            color: white;
            font-size: 24px;
            font-weight: 800;
            letter-spacing: 1px;
        """)

        self.subtitle = QLabel('GEOPHYSICAL DATA ASSURANCE PLATFORM')
        self.subtitle.setStyleSheet("color: #8BB8D0; font-size: 11px; font-weight: 400; letter-spacing: 2px;")

        title_layout.addWidget(self.main_title)
        title_layout.addWidget(self.subtitle)

        close_btn = QPushButton('✕')
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 15px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(255, 50, 50, 0.3);
                border-color: #FF6B6B;
            }
        """)
        close_btn.clicked.connect(self.reject)

        header_layout.addWidget(title_widget)
        header_layout.addStretch()
        header_layout.addWidget(close_btn, 0, Qt.AlignTop)

        layout.addWidget(self.header)

        # -- content pages (scrollable, responsive) --
        self._pages = QStackedWidget()
        self._pages.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._pages.setStyleSheet("QStackedWidget { background: transparent; }")

        self._icon_labels: list[QLabel] = []
        self._heading_labels: list[QLabel] = []

        pages_data = [
            ('📁', 'Your Confidential Workspace',
             'Create a project with its discipline, survey area, coordinate system, classification, and '
             'processing context. Project metadata stays in your selected project folder.',
             '#0B6FA4'),
            ('📊', 'Bring in Survey Data',
             'Use Upload Data in Project Data to import SEG-Y, SEG-D, navigation, velocity, and seismic '
             'processing deliverables. Imported files stay visible in the project explorer.',
             '#107C10'),
            ('✅', 'Run Quality Assurance',
             'Choose a module from the ribbon, review the relevant QC workflow, then process data using '
             'the project\'s local workspace and reporting tools.',
             '#6B4FA1'),
        ]

        total = len(pages_data)
        for i, (icon, title, body, accent) in enumerate(pages_data):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setStyleSheet("QScrollArea { background: transparent; }")

            page = QWidget()
            page.setObjectName('tutorialPage')
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(50, 30, 50, 20)
            page_layout.setSpacing(6)

            icon_label = QLabel(icon)
            icon_label.setStyleSheet(f"""
                font-size: 40px;
                background-color: rgba({self._hex_to_rgb(accent)}, 0.1);
                border-radius: 28px;
                padding: 12px;
            """)
            icon_label.setFixedSize(64, 64)
            icon_label.setAlignment(Qt.AlignCenter)
            self._icon_labels.append(icon_label)

            badge = QLabel(f'STEP {i + 1} OF {total}')
            badge.setStyleSheet(f"""
                color: {accent};
                font-weight: 700;
                font-size: 11px;
                letter-spacing: 2px;
                background-color: rgba({self._hex_to_rgb(accent)}, 0.1);
                padding: 4px 12px;
                border-radius: 12px;
            """)

            heading = QLabel(title)
            heading.setWordWrap(True)
            heading.setAlignment(Qt.AlignCenter)
            heading.setStyleSheet("""
                font-size: 21px;
                font-weight: 700;
                color: #102A43;
                margin-top: 8px;
            """)
            self._heading_labels.append(heading)

            text = QLabel(body)
            text.setWordWrap(True)
            text.setAlignment(Qt.AlignCenter)
            text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            text.setStyleSheet("""
                font-size: 13px;
                color: #415466;
                margin-top: 6px;
            """)

            page_layout.addWidget(icon_label, 0, Qt.AlignCenter)
            page_layout.addWidget(badge, 0, Qt.AlignCenter)
            page_layout.addWidget(heading, 0, Qt.AlignCenter)
            page_layout.addWidget(text)
            page_layout.addStretch()

            scroll.setWidget(page)
            self._pages.addWidget(scroll)

        layout.addWidget(self._pages, 1)

        # -- footer --
        bottom = QWidget()
        bottom.setStyleSheet("""
            QWidget {
                background-color: rgba(255, 255, 255, 0.5);
                border-bottom-left-radius: 20px;
                border-bottom-right-radius: 20px;
            }
        """)
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(36, 10, 36, 18)
        bottom_layout.setSpacing(10)

        # Step dots
        self.dots_row = QHBoxLayout()
        self.dots_row.setSpacing(6)
        self.dots_row.addStretch()
        self._dots: list[QLabel] = []
        for _ in range(total):
            dot = QLabel()
            dot.setFixedSize(7, 7)
            self._dots.append(dot)
            self.dots_row.addWidget(dot)
        self.dots_row.addStretch()
        bottom_layout.addLayout(self.dots_row)

        footer_controls = QHBoxLayout()
        footer_controls.setSpacing(10)

        self.show_again = QCheckBox('✨ Show this guide when TGPAssure starts')
        self.show_again.setChecked(True)
        self.show_again.setStyleSheet("""
            QCheckBox {
                color: #415466;
                font-size: 12px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 17px;
                height: 17px;
                border-radius: 4px;
                border: 2px solid #CBD5E1;
                background-color: white;
            }
            QCheckBox::indicator:checked {
                background-color: #0B6FA4;
                border-color: #0B6FA4;
            }
        """)

        controls = QHBoxLayout()
        controls.setSpacing(10)

        self.back = QPushButton('← Back')
        self.next = QPushButton('Next →')
        self.finish = QPushButton('🚀 Start Working')

        for b in (self.back, self.next, self.finish):
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(38)

        button_style = """
            QPushButton {
                padding: 9px 22px;
                border-radius: 10px;
                font-weight: 600;
                font-size: 13px;
                border: none;
            }
        """

        self.back.setStyleSheet(button_style + """
            QPushButton { background-color: transparent; color: #415466; }
            QPushButton:hover { background-color: #F1F5F9; }
        """)
        self.next.setStyleSheet(button_style + """
            QPushButton { background-color: #F1F5F9; color: #102A43; }
            QPushButton:hover { background-color: #E2E8F0; }
        """)
        self.finish.setStyleSheet(button_style + """
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #0B6FA4, stop: 1 #145E8C);
                color: white;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #0B8BC4, stop: 1 #1A7FB5);
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #0A5F8A, stop: 1 #0B6FA4);
            }
        """)

        self.back.clicked.connect(self._back)
        self.next.clicked.connect(self._next)
        self.finish.clicked.connect(self.accept)

        controls.addWidget(self.back)
        controls.addStretch()
        controls.addWidget(self.next)
        controls.addWidget(self.finish)

        bottom_layout.addWidget(self.show_again)
        bottom_layout.addLayout(footer_controls)
        bottom_layout.addLayout(controls)

        layout.addWidget(bottom)
        self._update_controls()

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> str:
        hex_color = hex_color.lstrip('#')
        return ', '.join(str(int(hex_color[i:i + 2], 16)) for i in (0, 2, 4))

    def _back(self) -> None:
        self._pages.setCurrentIndex(max(0, self._pages.currentIndex() - 1))
        self._update_controls()

    def _next(self) -> None:
        self._pages.setCurrentIndex(min(self._pages.count() - 1, self._pages.currentIndex() + 1))
        self._update_controls()

    def _update_controls(self) -> None:
        index = self._pages.currentIndex()
        self.back.setVisible(index > 0)
        self.next.setVisible(index < self._pages.count() - 1)
        self.finish.setVisible(index == self._pages.count() - 1)

        for i, dot in enumerate(self._dots):
            active = i == index
            dot.setStyleSheet(f"""
                border-radius: 3px;
                background-color: {'#0B6FA4' if active else '#CBD5E1'};
            """)

        if index < self._pages.count() - 1:
            self.next.setFocus()
        else:
            self.finish.setFocus()

    def center_on_screen(self) -> None:
        screen = QGuiApplication.screenAt(self.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + (geo.height() - self.height()) // 2
        self.move(x, y)

    def showEvent(self, event) -> None:  # noqa: D401
        super().showEvent(event)
        self.center_on_screen()

    # -- responsive scaling ------------------------------------------------

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        w = event.size().width()

        title_size = max(18, min(26, int(w * 0.026)))
        self.main_title.setStyleSheet(f"""
            color: white; font-size: {title_size}px; font-weight: 800; letter-spacing: 1px;
        """)

        heading_size = max(16, min(22, int(w * 0.022)))
        for heading in self._heading_labels:
            heading.setStyleSheet(f"""
                font-size: {heading_size}px; font-weight: 700; color: #102A43; margin-top: 8px;
            """)

    # -- window dragging (header) -------------------------------------------

    def _header_mouse_press(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _header_mouse_move(self, event: QMouseEvent) -> None:
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def _header_mouse_release(self, event: QMouseEvent) -> None:
        self._drag_pos = None

    # -- window resizing (edges of the whole dialog) ------------------------

    def _edge_at(self, pos: QPoint) -> str | None:
        rect = self.rect()
        left = pos.x() <= RESIZE_MARGIN
        right = pos.x() >= rect.width() - RESIZE_MARGIN
        top = pos.y() <= RESIZE_MARGIN
        bottom = pos.y() >= rect.height() - RESIZE_MARGIN

        if top and left:
            return 'top_left'
        if top and right:
            return 'top_right'
        if bottom and left:
            return 'bottom_left'
        if bottom and right:
            return 'bottom_right'
        if left:
            return 'left'
        if right:
            return 'right'
        if top:
            return 'top'
        if bottom:
            return 'bottom'
        return None

    _CURSORS = {
        'left': Qt.SizeHorCursor, 'right': Qt.SizeHorCursor,
        'top': Qt.SizeVerCursor, 'bottom': Qt.SizeVerCursor,
        'top_left': Qt.SizeFDiagCursor, 'bottom_right': Qt.SizeFDiagCursor,
        'top_right': Qt.SizeBDiagCursor, 'bottom_left': Qt.SizeBDiagCursor,
    }

    def mousePressEvent(self, event: QMouseEvent) -> None:
        edge = self._edge_at(event.position().toPoint())
        if edge and event.button() == Qt.LeftButton:
            self._resize_edge = edge
            self._resizing = True
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position().toPoint()
        if self._resizing and self._resize_edge and event.buttons() & Qt.LeftButton:
            self._perform_resize(event.globalPosition().toPoint())
            event.accept()
            return

        edge = self._edge_at(pos)
        if edge:
            self.setCursor(self._CURSORS[edge])
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._resizing = False
        self._resize_edge = None
        self.unsetCursor()
        super().mouseReleaseEvent(event)

    def _perform_resize(self, global_pos: QPoint) -> None:
        geo = self.geometry()
        min_w, min_h = self.minimumWidth(), self.minimumHeight()
        edge = self._resize_edge

        new_geo = QRect(geo)
        if 'left' in edge:
            new_width = geo.right() - global_pos.x()
            if new_width >= min_w:
                new_geo.setLeft(global_pos.x())
        if 'right' in edge:
            new_width = global_pos.x() - geo.left()
            new_geo.setWidth(max(min_w, new_width))
        if 'top' in edge:
            new_height = geo.bottom() - global_pos.y()
            if new_height >= min_h:
                new_geo.setTop(global_pos.y())
        if 'bottom' in edge:
            new_height = global_pos.y() - geo.top()
            new_geo.setHeight(max(min_h, new_height))

        self.setGeometry(new_geo)

if __name__ == '__main__':
    import sys
    import time
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    splash = StartupSplash()
    splash.show()

    for i in range(5):
        app.processEvents()
        time.sleep(0.3)
        splash.set_stage(f'Loading module {i + 1}/5...')

    splash.close()
    tutorial = TutorialDialog()
    if tutorial.exec() == QDialog.Accepted:
        pass

    sys.exit(app.exec())