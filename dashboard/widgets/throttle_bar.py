"""
throttle_bar.py
===============

Horizontal throttle-position bar for the Track dashboard.

OBD-II PID 0111 (``THROTTLE_POS``) reports the *absolute* throttle-body
position; on a 2ZZ that sensor's idle stop reads roughly 12-14 %, so a raw
reading of 14 % actually means "pedal fully released". Showing that verbatim
would confuse the driver, so the widget normalises against
``config.THROTTLE_IDLE_STOP_PCT`` and displays the more intuitive
*pedal effort* as a 0-100 % fill: 0 at idle, 100 at floored.

The bar itself is a soft-cornered rectangle with a cyan-accent fill and a
subtle glow along the leading edge; the label sits to the left and the
numeric readout to the right, so the whole widget lives comfortably in a
50-60 px tall strip along the bottom of the dashboard.
"""

from __future__ import annotations

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen

from .. import config
from .base_gauge import BaseGauge


class ThrottleBar(BaseGauge):
    """Horizontal pedal-effort bar (0-100 %)."""

    def __init__(self, parent=None) -> None:
        # Store raw OBD throttle percentage; normalisation for the display
        # fill happens in paintEvent so no data is lost.
        super().__init__(config.THROTTLE_MIN_PCT, config.THROTTLE_MAX_PCT, parent)
        self.setMinimumSize(280, 42)

    # ------------------------------------------------------------------ #
    # Derived value: 0 at idle stop, 100 at full-press
    # ------------------------------------------------------------------ #
    def _pedal_effort_pct(self) -> float:
        idle = config.THROTTLE_IDLE_STOP_PCT
        raw = self.value
        # Everything at or below the idle stop reads as 0 %.
        if raw <= idle:
            return 0.0
        span = config.THROTTLE_MAX_PCT - idle
        if span <= 0.0:
            return 0.0
        return max(0.0, min(100.0, (raw - idle) / span * 100.0))

    # ------------------------------------------------------------------ #
    # Rendering
    # ------------------------------------------------------------------ #
    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        w, h = float(self.width()), float(self.height())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        # Elevated card behind everything (thinner than the main gauges).
        self.draw_card(painter, margin=3.0, radius=10.0)

        # --- Vertical centre and horizontal bands ----------------------
        label_w = min(w * 0.16, 96.0)
        value_w = min(w * 0.14, 84.0)
        gap = 8.0

        bar_left = label_w + gap
        bar_right = w - value_w - gap
        bar_w = max(1.0, bar_right - bar_left)
        bar_h = min(h * 0.42, 20.0)
        bar_top = (h - bar_h) * 0.5
        bar_rect = QRectF(bar_left, bar_top, bar_w, bar_h)
        radius = bar_h * 0.5

        # --- Label on the left ---------------------------------------
        painter.setPen(self.color(config.COLOR_TEXT_DIM))
        painter.setFont(self.scaled_font(h * 0.36, bold=True, spacing=28))
        painter.drawText(
            QRectF(gap, 0, label_w, h),
            Qt.AlignVCenter | Qt.AlignLeft,
            "THROTTLE",
        )

        # --- Bar track (unfilled) ------------------------------------
        track_path = QPainterPath()
        track_path.addRoundedRect(bar_rect, radius, radius)
        painter.fillPath(track_path, self.color(config.COLOR_TRACK))
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(self.color(config.COLOR_CARD_BORDER), 1.0))
        painter.drawRoundedRect(bar_rect, radius, radius)

        # --- Bar fill (pedal effort) ---------------------------------
        pct = self._pedal_effort_pct() if self._has_data else 0.0
        if self._has_data and pct > 0.0:
            fill_w = bar_w * (pct / 100.0)
            fill_rect = QRectF(bar_left, bar_top, fill_w, bar_h)
            painter.save()
            painter.setClipPath(track_path)

            # Horizontal cyan gradient; leading edge slightly brighter so the
            # tip of the bar reads as the "active" edge.
            grad = QLinearGradient(bar_left, 0, bar_left + fill_w, 0)
            base = QColor(config.COLOR_ACCENT)
            grad.setColorAt(0.0, base.darker(120))
            grad.setColorAt(1.0, base.lighter(140))
            painter.fillRect(fill_rect, grad)

            # Soft glow just beyond the leading edge for a bit of neon.
            if fill_w > 4.0:
                glow_col = QColor(config.COLOR_ACCENT)
                glow_col.setAlpha(90)
                glow_rect = QRectF(
                    bar_left + fill_w - bar_h * 0.6,
                    bar_top - 2,
                    bar_h * 1.2,
                    bar_h + 4,
                )
                painter.setPen(Qt.NoPen)
                painter.setBrush(glow_col)
                painter.drawRoundedRect(glow_rect, radius, radius)
            painter.restore()

        # --- Numeric percentage on the right -------------------------
        value_rect = QRectF(bar_right + gap, 0, value_w, h)
        painter.setFont(self.scaled_font(h * 0.5, bold=True))
        if self._has_data:
            painter.setPen(self.color(config.COLOR_TEXT))
            painter.drawText(
                value_rect,
                Qt.AlignVCenter | Qt.AlignRight,
                f"{int(round(pct))}%",
            )
        else:
            painter.setPen(self.color(config.COLOR_TEXT_DIM))
            painter.drawText(value_rect, Qt.AlignVCenter | Qt.AlignRight, "--")

        painter.end()
