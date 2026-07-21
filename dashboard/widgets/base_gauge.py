"""
base_gauge.py
=============

Common machinery shared by every gauge widget.

It gives each gauge:

* **A ``set_value()`` slot** that accepts a number or ``None`` (no data).
* **60 FPS easing** - incoming values are treated as *targets*; the displayed
  value glides toward them a fraction each frame, so a jumpy 20 Hz OBD feed
  becomes a silky needle/arc sweep. The easing is time-agnostic (fixed per
  frame) which is exactly what we want tied to the 60 Hz repaint clock.
* **Flash timing** - a shared blink phase for "critical" states (overheating
  coolant, redline RPM), driven by a slower timer.
* **Repaint economy** - the widget only calls ``update()`` when the displayed
  value actually moved or the blink phase flipped, so a steady reading costs
  the Raspberry Pi GPU nothing.

Subclasses implement :meth:`paintEvent` (the vector drawing) and, optionally,
:meth:`is_flashing` to opt into the blink behaviour.
"""

from __future__ import annotations

from PyQt5.QtCore import QRectF, Qt, QTimer, pyqtSlot
from PyQt5.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt5.QtWidgets import QWidget, QSizePolicy

from .. import config

# Fraction of the remaining distance to close each frame (~60 Hz). 0.28 gives
# a responsive-yet-smooth glide that settles in ~120-150 ms.
_SMOOTHING = 0.28


class BaseGauge(QWidget):
    """Base class for the animated, self-drawing gauges."""

    def __init__(self, minimum: float, maximum: float, parent=None) -> None:
        super().__init__(parent)
        self._min = float(minimum)
        self._max = float(maximum)
        # Displayed (eased) value and the target we are gliding toward.
        self._value = float(minimum)
        self._target = float(minimum)
        # True once at least one real reading has arrived; drives the dim
        # "-- / no data" appearance before the ECU answers.
        self._has_data = False
        # Blink phase shared by all "critical" visuals (True = lit).
        self._flash_on = True

        # Expand to fill whatever slot the layout gives us.
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(120, 160)
        # Transparent backing so the window's vignette shows through the
        # rounded corners of each gauge's "card" (drawn in draw_card()).
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # 60 FPS animation clock: advances the eased value.
        self._anim_timer = QTimer(self)
        self._anim_timer.setTimerType(0)  # Qt.PreciseTimer
        self._anim_timer.timeout.connect(self._on_frame)
        self._anim_timer.start(config.FRAME_INTERVAL_MS)

        # Slower clock: toggles the blink phase for critical states.
        self._flash_timer = QTimer(self)
        self._flash_timer.timeout.connect(self._on_flash)
        self._flash_timer.start(config.FLASH_INTERVAL_MS)

    # ------------------------------------------------------------------ #
    # Public slot
    # ------------------------------------------------------------------ #
    @pyqtSlot(object)
    def set_value(self, value) -> None:
        """Set the gauge target. ``None`` marks the reading as unavailable."""
        if value is None:
            self._has_data = False
            return
        self._has_data = True
        # Clamp into the gauge's declared scale so geometry stays in-bounds.
        self._target = max(self._min, min(self._max, float(value)))

    # ------------------------------------------------------------------ #
    # Values exposed to subclasses' paintEvent
    # ------------------------------------------------------------------ #
    @property
    def value(self) -> float:
        """The current *eased* value being displayed."""
        return self._value

    @property
    def fraction(self) -> float:
        """Displayed value as a 0..1 fraction of the gauge's scale."""
        span = self._max - self._min
        if span <= 0:
            return 0.0
        return (self._value - self._min) / span

    @property
    def has_data(self) -> bool:
        return self._has_data

    def is_flashing(self) -> bool:
        """Override: return True when the gauge should blink (critical)."""
        return False

    # ------------------------------------------------------------------ #
    # Animation / repaint economy
    # ------------------------------------------------------------------ #
    def _on_frame(self) -> None:
        """Glide the displayed value toward the target; repaint if it moved."""
        diff = self._target - self._value
        # Settle threshold scaled to the gauge range (avoids endless twitching).
        epsilon = (self._max - self._min) * 0.0005
        if abs(diff) <= epsilon:
            if self._value != self._target:
                self._value = self._target
                self.update()
            return
        self._value += diff * _SMOOTHING
        self.update()

    def _on_flash(self) -> None:
        """Advance the blink phase; repaint when it changes something visible."""
        if self.is_flashing():
            self._flash_on = not self._flash_on
            self.update()
        elif not self._flash_on:
            # Leaving a critical state: make sure we end up fully lit again.
            self._flash_on = True
            self.update()

    # ------------------------------------------------------------------ #
    # Small drawing helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def color(hex_str: str, alpha: int = 255) -> QColor:
        """Build a QColor from a ``#rrggbb`` string with optional alpha."""
        c = QColor(hex_str)
        c.setAlpha(alpha)
        return c

    @staticmethod
    def scaled_font(px: float, bold: bool = True,
                    family: str = "DejaVu Sans", spacing: float = 0.0) -> QFont:
        """A pixel-sized font that scales with the widget for crisp vectors.

        ``spacing`` adds letter-spacing as *extra* percent (e.g. 25 = 125%),
        which gives labels a cleaner, more technical / instrument look.
        """
        font = QFont(family)
        font.setPixelSize(max(6, int(px)))
        font.setBold(bold)
        if spacing:
            font.setLetterSpacing(QFont.PercentageSpacing, 100.0 + spacing)
        return font

    # ------------------------------------------------------------------ #
    # Shared "professional" drawing helpers
    # ------------------------------------------------------------------ #
    def draw_card(self, painter: QPainter,
                  margin: float | None = None,
                  radius: float | None = None) -> QRectF:
        """Draw the elevated rounded panel every gauge sits on.

        A soft vertical gradient fill, a hairline border, and a faint inner
        top-highlight give a sense of depth. Returns the card's rectangle so
        callers can lay content out inside it if they wish.
        """
        margin = config.CARD_MARGIN if margin is None else margin
        radius = config.CARD_RADIUS if radius is None else radius
        r = QRectF(self.rect()).adjusted(margin, margin, -margin, -margin)

        grad = QLinearGradient(r.left(), r.top(), r.left(), r.bottom())
        grad.setColorAt(0.0, self.color(config.COLOR_CARD_TOP))
        grad.setColorAt(1.0, self.color(config.COLOR_CARD_BOTTOM))
        path = QPainterPath()
        path.addRoundedRect(r, radius, radius)
        painter.fillPath(path, grad)

        # Faint highlight just inside the top edge (subtle bevel).
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(self.color(config.COLOR_CARD_HILITE, alpha=90), 1.0))
        painter.drawLine(int(r.left() + radius), int(r.top() + 2),
                         int(r.right() - radius), int(r.top() + 2))

        # Hairline border.
        painter.setPen(QPen(self.color(config.COLOR_CARD_BORDER), 1.4))
        painter.drawRoundedRect(r, radius, radius)
        return r

    def glow_arc(self, painter: QPainter, rect: QRectF,
                 start_deg: float, span_deg: float,
                 col: QColor, width: float, layers: int | None = None) -> None:
        """Draw an arc with a soft neon halo.

        The halo is faked cheaply by stroking the same arc a few times with
        increasing width and decreasing opacity, then the crisp arc on top -
        no blur/QGraphicsEffect, so it stays fast on the Pi's GPU.
        """
        layers = config.GLOW_LAYERS if layers is None else layers
        painter.setBrush(Qt.NoBrush)
        for i in range(layers, 0, -1):
            halo = QColor(col)
            halo.setAlpha(max(8, int(config.GLOW_ALPHA / i)))
            painter.setPen(QPen(halo, width * (1.0 + 0.55 * i),
                                Qt.SolidLine, Qt.RoundCap))
            painter.drawArc(rect, int(start_deg * 16), int(span_deg * 16))
        painter.setPen(QPen(col, width, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(rect, int(start_deg * 16), int(span_deg * 16))

    def draw_glow_text(self, painter: QPainter, rect: QRectF, flags: int,
                       text: str, col: QColor, glow: bool = False) -> None:
        """Draw text, optionally with a faint halo for emphasis (redline)."""
        if glow:
            halo = QColor(col)
            halo.setAlpha(60)
            painter.setPen(halo)
            for dx, dy in ((-1.5, 0), (1.5, 0), (0, -1.5), (0, 1.5)):
                painter.drawText(rect.translated(dx, dy), flags, text)
        painter.setPen(col)
        painter.drawText(rect, flags, text)
