"""
throttle_card.py
================

Compact sidebar card for relative throttle position (0-100%).
Shows a numeric percentage readout and an embedded horizontal progress bar.
"""

from __future__ import annotations

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen

from .. import config
from .base_gauge import BaseGauge


class ThrottleCard(BaseGauge):
    """Compact card widget for Relative Throttle Position."""

    def __init__(self, parent=None) -> None:
        super().__init__(0.0, 100.0, parent)
        self.setMinimumSize(120, 76)

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        w, h = float(self.width()), float(self.height())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        self.draw_card(painter, margin=4.0, radius=12.0)

        # Title / Label
        label_h = h * 0.28
        painter.setPen(self.color(config.COLOR_TEXT_DIM))
        painter.setFont(self.scaled_font(max(10, h * 0.18), spacing=28))
        painter.drawText(
            QRectF(0, label_h * 0.10, w, label_h),
            Qt.AlignHCenter | Qt.AlignTop,
            "THROTTLE",
        )

        # Numeric readout
        num_h = h * 0.38
        num_rect = QRectF(0, label_h, w, num_h)
        if not self._has_data:
            painter.setPen(self.color(config.COLOR_TEXT_DIM))
            painter.setFont(self.scaled_font(h * 0.35))
            painter.drawText(num_rect, Qt.AlignCenter, "--%")
        else:
            pct = self.value
            painter.setFont(self.scaled_font(h * 0.36, bold=True))
            painter.setPen(self.color(config.COLOR_ACCENT))
            painter.drawText(num_rect, Qt.AlignCenter, f"{int(round(pct))}%")

        # Mini horizontal bar at the bottom of the card
        bar_margin = 12.0
        bar_w = max(1.0, w - 2 * bar_margin)
        bar_h = max(4.0, h * 0.12)
        bar_top = h - bar_h - 10.0
        bar_rect = QRectF(bar_margin, bar_top, bar_w, bar_h)
        radius = bar_h * 0.5

        # Unfilled track
        track_path = QPainterPath()
        track_path.addRoundedRect(bar_rect, radius, radius)
        painter.fillPath(track_path, self.color(config.COLOR_TRACK))
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(self.color(config.COLOR_CARD_BORDER), 1.0))
        painter.drawRoundedRect(bar_rect, radius, radius)

        # Fill
        if self._has_data and self.value > 0.0:
            fill_w = bar_w * (self.fraction)
            fill_rect = QRectF(bar_margin, bar_top, fill_w, bar_h)
            painter.save()
            painter.setClipPath(track_path)
            grad = QLinearGradient(bar_margin, 0, bar_margin + fill_w, 0)
            base = QColor(config.COLOR_ACCENT)
            grad.setColorAt(0.0, base.darker(120))
            grad.setColorAt(1.0, base.lighter(130))
            painter.fillRect(fill_rect, grad)
            painter.restore()

        painter.end()
