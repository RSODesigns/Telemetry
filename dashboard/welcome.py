"""
welcome.py
==========

Welcome / mode-selection screen shown at startup when no ``--layout`` flag is
provided.  Displays the RSO Designs logo centred on the same dark-cockpit
canvas as the dashboards, with two pill-shaped buttons underneath:

* **Road** → opens the General dashboard
* **Track** → opens the Track dashboard

The widget emits :pyqtSignal:`layout_chosen(str)` with ``"general"`` or
``"track"`` so the caller can wire up the appropriate dashboard window.
"""

from __future__ import annotations

import os
from pathlib import Path

from PyQt5.QtCore import QPropertyAnimation, QSize, Qt, QEasingCurve, pyqtSignal
from PyQt5.QtGui import (
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PyQt5.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import config


# ---------------------------------------------------------------------------
#  Resolve logo path once at import time
# ---------------------------------------------------------------------------
_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
_LOGO_PATH = _ASSETS_DIR / "RSOLogo.png"


def _invert_logo(path: Path) -> QPixmap:
    """Load a logo PNG and invert its RGB channels (black → white) while
    keeping the original alpha transparency intact.  Returns a null QPixmap
    if the file doesn't exist.
    """
    if not path.exists():
        return QPixmap()
    img = QImage(str(path))
    if img.isNull():
        return QPixmap()
    img = img.convertToFormat(QImage.Format_ARGB32)
    img.invertPixels(QImage.InvertRgb)  # inverts R/G/B only, alpha untouched
    return QPixmap.fromImage(img)


class _PillButton(QPushButton):
    """A wide, rounded pill button with a subtle glow border that matches the
    dashboard colour palette.  Hover and press states are animated via
    stylesheet transitions.
    """

    def __init__(self, text: str, accent: str, parent=None) -> None:
        super().__init__(text, parent)
        self._accent = accent
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(52)
        self.setMinimumWidth(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._apply_style()

    def _apply_style(self) -> None:
        c = QColor(self._accent)
        r, g, b = c.red(), c.green(), c.blue()
        self.setStyleSheet(f"""
            QPushButton {{
                color: {config.COLOR_TEXT};
                background-color: rgba({r},{g},{b},30);
                border: 2px solid rgba({r},{g},{b},140);
                border-radius: 26px;
                font-size: 18px;
                font-weight: bold;
                letter-spacing: 3px;
                padding: 0 36px;
            }}
            QPushButton:hover {{
                background-color: rgba({r},{g},{b},70);
                border: 2px solid rgba({r},{g},{b},220);
            }}
            QPushButton:pressed {{
                background-color: rgba({r},{g},{b},110);
                border: 2px solid rgba({r},{g},{b},255);
            }}
        """)


class WelcomeScreen(QWidget):
    """Full-screen welcome page with logo + Road / Track pill buttons.

    Signals
    -------
    layout_chosen(str)
        Emitted with ``"general"`` when Road is clicked, ``"track"`` when
        Track is clicked.
    """

    layout_chosen = pyqtSignal(str)

    def __init__(self, windowed: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("RSO Designs – Select Mode")
        if not windowed:
            self.setWindowFlag(Qt.FramelessWindowHint, True)
            self.setCursor(Qt.BlankCursor)
        self.resize(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
        self.setMinimumSize(640, 400)

        # --- Load logo pixmap (inverted so it reads white on dark bg) ----
        self._logo_pixmap = _invert_logo(_LOGO_PATH)

        # --- Pill buttons -----------------------------------------------
        btn_road = _PillButton("R O A D", config.COLOR_OPTIMAL)
        btn_track = _PillButton("T R A C K", config.COLOR_ACCENT)

        btn_road.clicked.connect(lambda: self.layout_chosen.emit("general"))
        btn_track.clicked.connect(lambda: self.layout_chosen.emit("track"))

        btn_row = QHBoxLayout()
        btn_row.setSpacing(28)
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_road)
        btn_row.addWidget(btn_track)
        btn_row.addStretch(1)

        # --- Outer layout (logo is painted, buttons are laid out) --------
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        # Push buttons to ~70% down the screen so they sit beneath the logo.
        outer.addStretch(5)
        outer.addLayout(btn_row)
        outer.addStretch(2)

        # --- Fade-in animation ------------------------------------------
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)
        self._fade_in = QPropertyAnimation(self._opacity, b"opacity")
        self._fade_in.setDuration(600)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.OutCubic)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._fade_in.start()

    # ------------------------------------------------------------------ #
    # Painting
    # ------------------------------------------------------------------ #
    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        w, h = self.width(), self.height()

        # 1. Radial vignette background (same as dashboard)
        grad = QRadialGradient(w * 0.5, h * 0.42, max(w, h) * 0.75)
        grad.setColorAt(0.0, QColor(config.COLOR_BG_TOP))
        grad.setColorAt(1.0, QColor(config.COLOR_BG_EDGE))
        painter.fillRect(self.rect(), grad)

        # 2. Subtle accent glow behind where the logo sits
        glow = QRadialGradient(w * 0.5, h * 0.36, min(w, h) * 0.45)
        glow.setColorAt(0.0, QColor(232, 24, 32, 18))   # faint racing red
        glow.setColorAt(0.5, QColor(232, 24, 32, 6))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(self.rect(), glow)

        # 3. Draw the logo centred in the upper portion
        if not self._logo_pixmap.isNull():
            # Target: logo occupies ~40% of the smaller dimension, centred
            # vertically in the upper 60% of the window.
            max_logo_h = int(h * 0.40)
            max_logo_w = int(w * 0.40)
            scaled = self._logo_pixmap.scaled(
                max_logo_w, max_logo_h,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            lx = (w - scaled.width()) // 2
            ly = int(h * 0.08) + (max_logo_h - scaled.height()) // 2
            painter.drawPixmap(lx, ly, scaled)

        # 4. Thin horizontal separator above the buttons
        sep_y = int(h * 0.60)
        sep_margin = int(w * 0.25)
        sep_grad = QLinearGradient(sep_margin, sep_y, w - sep_margin, sep_y)
        sep_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
        sep_grad.setColorAt(0.3, QColor(config.COLOR_ACCENT))
        sep_grad.setColorAt(0.7, QColor(config.COLOR_ACCENT))
        sep_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(QPen(sep_grad, 1.0))
        painter.drawLine(sep_margin, sep_y, w - sep_margin, sep_y)

        painter.end()

    # ------------------------------------------------------------------ #
    # Keyboard
    # ------------------------------------------------------------------ #
    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key_Escape, Qt.Key_Q):
            self.close()
        else:
            super().keyPressEvent(event)
