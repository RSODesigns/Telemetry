"""
rpm_gauge.py
============

Centre (dominant) element: a large sweeping circular-arc tachometer with a
motorsport-style progressive shift-light strip across the top, all drawn with
:class:`QPainter` vector primitives so it stays razor sharp and cheap to
composite on the Pi's VideoCore VII GPU.

Zone / colour logic
-------------------
The tacho is coloured by *zones* - configurable ``(max_rpm, colour)`` bands
walked in order from 0 up to the top of the scale. The gauge also has a
single ``redline_rpm`` threshold at (or above) which the value arc, the
central number and the whole shift-light strip blink between the primary
"red" and a secondary "magenta" (a shift-NOW pulse).

Two callers currently instantiate this widget with different tunings:

* **General layout (default)** - the classic road-friendly scheme::

      0    .. 6000  -> solid green
      6000 .. 7800  -> amber
      7800 .. 8500  -> flashing red / magenta

* **Track layout** - blue below the 2ZZ VVTL-i cam switchover (6200 rpm),
  green above it (the on-cam power band), and flashing red only right at the
  8500 redline. See :class:`~dashboard.view.TrackDashboardWindow`.

Geometry / coordinate mapping
-----------------------------
The dial is a 270-degree arc that opens at the bottom. A value is turned into
an angle by normalising it against the 0-8500 scale::

    frac  = rpm / RPM_MAX
    angle = START_ANGLE_DEG - frac * SWEEP_DEG      # degrees, math convention

Qt's ``drawArc`` wants sixteenths of a degree and treats clockwise spans as
negative, hence the ``* 16`` and the negative sweep below.
"""

from __future__ import annotations

import math

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPen

from .. import config
from .base_gauge import BaseGauge

# Dial spans 270 degrees, starting at the lower-left (225 deg) and sweeping
# clockwise over the top to the lower-right (-45 deg).
START_ANGLE_DEG = 225.0
SWEEP_DEG = 270.0

# The shift-light bar starts illuminating from this RPM (below it the strip is
# dark); LEDs then fill progressively up to the redline.
SHIFT_START_RPM = 3500.0

# Default zones = the original general-layout scheme. Given as a list of
# ``(max_rpm, colour)`` pairs, sorted ascending. An RPM value falls into the
# first zone whose ``max_rpm`` it is at or below. The last zone's max should
# be at least ``config.RPM_MAX``.
_DEFAULT_ZONES: "list[tuple[float, str]]" = [
    (config.RPM_GREEN_MAX, config.COLOR_OPTIMAL),
    (config.RPM_AMBER_MAX, config.COLOR_AMBER),
    (config.RPM_MAX,       config.COLOR_CRITICAL),
]


class RPMGauge(BaseGauge):
    """Circular tachometer + progressive shift-lights (0-RPM_MAX)."""

    def __init__(
        self,
        zones: "list[tuple[float, str]] | None" = None,
        redline_rpm: float | None = None,
        parent=None,
    ) -> None:
        """Build a tacho with optional per-layout zone tuning.

        Parameters
        ----------
        zones:
            Ordered list of ``(max_rpm, hex_colour)`` pairs describing the
            coloured bands from 0 up to the top of the scale. If ``None``
            the general-layout scheme is used (green / amber / red-flashing).
        redline_rpm:
            Threshold at or above which the arc, centre number and shift-
            lights all blink between the primary ``COLOR_CRITICAL`` red and
            the secondary ``COLOR_SHIFT`` magenta. If ``None`` the general-
            layout redline (``config.RPM_AMBER_MAX``) is used.
        """
        super().__init__(config.RPM_MIN, config.RPM_MAX, parent)
        self._zones: list[tuple[float, str]] = (
            list(zones) if zones is not None else list(_DEFAULT_ZONES)
        )
        self._redline_rpm: float = (
            float(redline_rpm) if redline_rpm is not None
            else config.RPM_AMBER_MAX
        )
        self.setMinimumSize(300, 320)

    # ------------------------------------------------------------------ #
    # Critical-state hook: the redline band blinks
    # ------------------------------------------------------------------ #
    def is_flashing(self) -> bool:
        return self._has_data and self.value >= self._redline_rpm

    # ------------------------------------------------------------------ #
    # Colour selection
    # ------------------------------------------------------------------ #
    def _color_for(self, rpm: float) -> QColor:
        """Return the colour for a given RPM.

        Used for the value arc, the centre readout, *and* each shift-light
        LED (each LED asks for its own threshold's colour). Values at or
        above ``redline_rpm`` return the alternating red/magenta flash colour
        regardless of the zones list.
        """
        if rpm >= self._redline_rpm:
            return self.color(config.COLOR_CRITICAL if self._flash_on
                              else config.COLOR_SHIFT)
        for max_rpm, hex_color in self._zones:
            if rpm <= max_rpm:
                return self.color(hex_color)
        # Above the last zone but below redline (shouldn't happen with a
        # well-formed zones list): fall back to the top zone's colour.
        return self.color(self._zones[-1][1])

    # ------------------------------------------------------------------ #
    # Angle / point helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _angle_for(frac: float) -> float:
        """Map a 0..1 fraction to a dial angle in degrees (math convention)."""
        return START_ANGLE_DEG - frac * SWEEP_DEG

    def _point(self, cx: float, cy: float, radius: float, frac: float) -> QPointF:
        a = math.radians(self._angle_for(frac))
        return QPointF(cx + radius * math.cos(a), cy - radius * math.sin(a))

    # ------------------------------------------------------------------ #
    # Rendering
    # ------------------------------------------------------------------ #
    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        w, h = float(self.width()), float(self.height())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        self.draw_card(painter)

        # --- Top strip: progressive shift lights -------------------------
        strip_h = h * 0.14
        self._draw_shift_lights(painter, w, strip_h)

        # --- Dial geometry ----------------------------------------------
        dial_top = strip_h
        dial_h = h - dial_top
        R = min(w, dial_h) * 0.5 * 0.92
        cx = w * 0.5
        cy = dial_top + dial_h * 0.5

        main_w = R * 0.15          # thickness of the main value/track arc
        zone_w = R * 0.045         # thin outer zone-band ring
        gap = R * 0.05

        r_zone = R - zone_w * 0.5
        r_main = r_zone - zone_w * 0.5 - gap - main_w * 0.5

        zone_rect = QRectF(cx - r_zone, cy - r_zone, 2 * r_zone, 2 * r_zone)
        main_rect = QRectF(cx - r_main, cy - r_main, 2 * r_main, 2 * r_main)

        # --- Outer zone bands (always visible reference) -----------------
        self._draw_zone_bands(painter, zone_rect, zone_w)

        # --- Main track arc (dim) ---------------------------------------
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(self.color(config.COLOR_TRACK), main_w,
                            Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(main_rect, int(START_ANGLE_DEG * 16), int(-SWEEP_DEG * 16))

        # --- Value arc (coloured by zone, with neon glow) ----------------
        if self._has_data:
            self.glow_arc(painter, main_rect, START_ANGLE_DEG,
                          -self.fraction * SWEEP_DEG,
                          self._color_for(self.value), main_w)

        # --- Tick marks + thousands labels ------------------------------
        self._draw_ticks(painter, cx, cy, r_main, main_w, R)

        # --- Bright cursor at the current value --------------------------
        if self._has_data:
            self._draw_cursor(painter, cx, cy, r_main, main_w)

        # --- Central digital readout ------------------------------------
        self._draw_center_readout(painter, cx, cy, R)

        painter.end()

    # ------------------------------------------------------------------ #
    # Sub-drawing routines
    # ------------------------------------------------------------------ #
    def _draw_zone_bands(self, painter: QPainter, rect: QRectF, width: float) -> None:
        """Thin reference ring outside the main arc, one segment per zone.

        Painted at the zones' full colour but reduced alpha so the main
        value arc reads as the primary visual.
        """
        painter.setBrush(Qt.NoBrush)
        prev = 0.0
        for max_rpm, hex_color in self._zones:
            pen = QPen(self.color(hex_color, alpha=130), width,
                       Qt.SolidLine, Qt.FlatCap)
            painter.setPen(pen)
            start = self._angle_for(prev / self._max) * 16
            span = -(max_rpm - prev) / self._max * SWEEP_DEG * 16
            painter.drawArc(rect, int(start), int(span))
            prev = max_rpm

    def _draw_ticks(self, painter: QPainter, cx: float, cy: float,
                    r_main: float, main_w: float, R: float) -> None:
        """Radial ticks every 500 RPM, labelled (in thousands) every 1000."""
        tick_outer = r_main - main_w * 0.5 - R * 0.02
        painter.setFont(self.scaled_font(R * 0.10, bold=True))

        rpm = 0
        while rpm <= int(config.RPM_MAX):
            frac = rpm / self._max
            major = (rpm % 1000 == 0)
            length = R * 0.065 if major else R * 0.035
            p_out = self._point(cx, cy, tick_outer, frac)
            p_in = self._point(cx, cy, tick_outer - length, frac)

            painter.setPen(QPen(self.color(config.COLOR_TEXT_DIM if major else config.COLOR_TEXT_FAINT),
                                2.4 if major else 1.2))
            painter.drawLine(p_out, p_in)

            if major:
                p_lbl = self._point(cx, cy, tick_outer - length - R * 0.11, frac)
                painter.setPen(self.color(config.COLOR_TEXT))
                painter.drawText(QRectF(p_lbl.x() - R * 0.11, p_lbl.y() - R * 0.09,
                                        R * 0.22, R * 0.18),
                                 Qt.AlignCenter, str(rpm // 1000))
            rpm += 500

    def _draw_cursor(self, painter: QPainter, cx: float, cy: float,
                     r_main: float, main_w: float) -> None:
        """A short bright radial marker highlighting the current value."""
        frac = self.fraction
        outer = self._point(cx, cy, r_main + main_w * 0.6, frac)
        inner = self._point(cx, cy, r_main - main_w * 0.6, frac)
        painter.setPen(QPen(self.color(config.COLOR_TEXT), max(2.0, main_w * 0.16),
                            Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(inner, outer)

    def _draw_center_readout(self, painter: QPainter, cx: float, cy: float,
                             R: float) -> None:
        """Big central RPM number + label, coloured by the current zone."""
        if self._has_data:
            number = f"{int(round(self.value)):d}"
            color = self._color_for(self.value)
            redline = self.value >= self._redline_rpm
        else:
            number = "----"
            color = self.color(config.COLOR_TEXT_DIM)
            redline = False

        # Big number, glowing when in the redline band.
        painter.setFont(self.scaled_font(R * 0.44))
        self.draw_glow_text(painter, QRectF(cx - R, cy - R * 0.52, 2 * R, R * 0.66),
                            Qt.AlignCenter, number, color,
                            glow=redline and self._flash_on)

        # "RPM" caption beneath the number, wide tracking.
        painter.setPen(self.color(config.COLOR_TEXT_DIM))
        painter.setFont(self.scaled_font(R * 0.12, bold=True, spacing=40))
        painter.drawText(QRectF(cx - R, cy + R * 0.20, 2 * R, R * 0.2),
                         Qt.AlignCenter, "RPM")

    def _draw_shift_lights(self, painter: QPainter, w: float, strip_h: float) -> None:
        """Motorsport-style LED strip that fills progressively with RPM.

        Each LED has an RPM threshold spread from ``SHIFT_START_RPM`` up to the
        redline. An LED lights once the current RPM passes its threshold and
        is coloured by :meth:`_color_for` at *its own* threshold, so the strip
        naturally follows the same zone scheme as the arc. In the redline
        band the entire lit portion of the bar blinks via the shared flash
        phase for an unmistakable "SHIFT NOW" cue.
        """
        count = config.SHIFT_LIGHT_COUNT
        total_w = w * 0.74
        x0 = (w - total_w) * 0.5
        cell = total_w / count
        led_w = cell * 0.74
        led_h = min(strip_h * 0.46, led_w * 0.85)
        y = strip_h * 0.34
        rad = led_h * 0.30

        rpm = self.value if self._has_data else 0.0
        redline = self._has_data and rpm >= self._redline_rpm
        span = config.RPM_MAX - SHIFT_START_RPM

        for i in range(count):
            threshold = SHIFT_START_RPM + span * (i + 1) / count
            lit = self._has_data and rpm >= threshold
            on_color = self._color_for(threshold)

            show = lit and (not redline or self._flash_on)
            x = x0 + i * cell + (cell - led_w) * 0.5
            rect = QRectF(x, y, led_w, led_h)

            if show:
                # Glow halo behind the lit LED.
                halo = QColor(on_color)
                halo.setAlpha(90)
                painter.setPen(Qt.NoPen)
                painter.setBrush(halo)
                painter.drawRoundedRect(rect.adjusted(-3, -3, 3, 3), rad + 2, rad + 2)
                painter.setBrush(on_color)
                painter.drawRoundedRect(rect, rad, rad)
            else:
                # Dark "off" LED with a faint outline so the bar is still read.
                painter.setPen(QPen(self.color(config.COLOR_CARD_BORDER), 1.0))
                painter.setBrush(self.color(config.COLOR_PANEL))
                painter.drawRoundedRect(rect, rad, rad)
