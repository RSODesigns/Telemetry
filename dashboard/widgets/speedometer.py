"""
speedometer.py
==============

Right-hand element: a large, clean digital speed read-out in MPH on an elevated
card, with a thin glowing accent arc for visual cohesion with the tachometer.

Unit conversion
---------------
OBD-II reports vehicle speed in km/h. The controller has already applied the
spec's conversion before the value reaches this widget::

    Speed_mph = Speed_kmh * 0.621371

so the gauge simply displays the MPH figure it is given. The accent arc uses
``SPEED_MAX_MPH`` purely as a visual full-scale reference.
"""

from __future__ import annotations

import math

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QPainter, QPen

from .. import config
from .base_gauge import BaseGauge

# Same 270-degree, bottom-opening arc convention as the tachometer.
START_ANGLE_DEG = 225.0
SWEEP_DEG = 270.0


class Speedometer(BaseGauge):
    """Big digital MPH read-out with a thin glowing accent arc."""

    def __init__(self, parent=None) -> None:
        super().__init__(0.0, config.SPEED_MAX_MPH, parent)

    def _point(self, cx: float, cy: float, radius: float, frac: float) -> QPointF:
        a = math.radians(START_ANGLE_DEG - frac * SWEEP_DEG)
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

        # --- Title -------------------------------------------------------
        title_h = h * 0.11
        painter.setPen(self.color(config.COLOR_TEXT_DIM))
        painter.setFont(self.scaled_font(h * 0.05, spacing=32))
        painter.drawText(QRectF(0, title_h * 0.2, w, title_h),
                         Qt.AlignHCenter | Qt.AlignTop, "SPEED")

        # --- Accent arc geometry ----------------------------------------
        dial_top = title_h
        dial_h = h - dial_top
        R = min(w, dial_h) * 0.5 * 0.88
        cx = w * 0.5
        cy = dial_top + dial_h * 0.5
        arc_w = R * 0.085
        r_arc = R - arc_w * 0.5
        arc_rect = QRectF(cx - r_arc, cy - r_arc, 2 * r_arc, 2 * r_arc)

        # Track arc (dim) then the value arc (glowing cyan accent).
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(self.color(config.COLOR_TRACK), arc_w, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(arc_rect, int(START_ANGLE_DEG * 16), int(-SWEEP_DEG * 16))

        if self._has_data:
            self.glow_arc(painter, arc_rect, START_ANGLE_DEG,
                          -self.fraction * SWEEP_DEG, self.color(config.COLOR_TEXT), arc_w)

        # --- Big digital number -----------------------------------------
        num_rect = QRectF(cx - R, cy - R * 0.56, 2 * R, R * 0.86)
        if self._has_data:
            number = f"{int(round(self.value)):d}"
            painter.setFont(self.scaled_font(R * 0.74, family="DejaVu Sans Mono"))
            self.draw_glow_text(painter, num_rect, Qt.AlignCenter, number,
                                self.color(config.COLOR_TEXT), glow=True)
        else:
            painter.setPen(self.color(config.COLOR_TEXT_DIM))
            painter.setFont(self.scaled_font(R * 0.74, family="DejaVu Sans Mono"))
            painter.drawText(num_rect, Qt.AlignCenter, "--")

        # --- "MPH" unit caption -----------------------------------------
        painter.setPen(self.color(config.COLOR_TEXT))
        painter.setFont(self.scaled_font(R * 0.19, bold=True, spacing=30))
        painter.drawText(QRectF(cx - R, cy + R * 0.34, 2 * R, R * 0.3),
                         Qt.AlignCenter, "MPH")

        painter.end()
