"""
fuel_status_widget.py
=====================

Diagnostic-style fuel system status readout (Closed Loop vs Open Loop modes).
Displays a compact pill with motorsport status codes:
- CL         (Green) - Closed loop, normal feedback
- OL-COLD    (Blue)  - Open loop, warming up
- OL-DRIVE   (Amber) - Open loop, high load / deceleration fuel cut
- OL-FAULT   (Red, flashing) - Open loop system failure
"""

from __future__ import annotations

from PyQt5.QtCore import QRectF, Qt, pyqtSlot
from PyQt5.QtGui import QPainter

from .. import config
from .base_gauge import BaseGauge


class FuelStatusWidget(BaseGauge):
    """Compact card widget for displaying OBD-II Fuel System Status."""

    def __init__(self, parent=None) -> None:
        super().__init__(0.0, 1.0, parent)
        self._status_text: str = "--"
        self._status_color: str = config.COLOR_TEXT_DIM
        self._critical: bool = False
        self.setMinimumSize(120, 76)

    @pyqtSlot(object)
    def set_fuel_status(self, status: tuple[str, str] | None) -> None:
        """Process raw OBD FUEL_STATUS tuple into a short motorsport label and color."""
        if not status or not status[0]:
            self._has_data = False
            self._status_text = "--"
            self._status_color = config.COLOR_TEXT_DIM
            self._critical = False
            self.update()
            return

        self._has_data = True
        s1 = str(status[0]).lower()

        if "closed loop" in s1:
            if "fault" in s1:
                self._status_text = "CL-FAULT"
                self._status_color = config.COLOR_AMBER
                self._critical = False
            else:
                self._status_text = "CL"
                self._status_color = config.COLOR_OPTIMAL
                self._critical = False
        elif "open loop" in s1:
            if "temp" in s1 or "warm" in s1:
                self._status_text = "OL-COLD"
                self._status_color = config.COLOR_COLD
                self._critical = False
            elif "load" in s1 or "decel" in s1 or "fuel cut" in s1:
                self._status_text = "OL-DRIVE"
                self._status_color = config.COLOR_AMBER
                self._critical = False
            elif "fail" in s1:
                self._status_text = "OL-FAULT"
                self._status_color = config.COLOR_CRITICAL
                self._critical = True
            else:
                self._status_text = "OPEN"
                self._status_color = config.COLOR_AMBER
                self._critical = False
        else:
            self._status_text = "OK"
            self._status_color = config.COLOR_OPTIMAL
            self._critical = False

        self.update()

    def is_flashing(self) -> bool:
        return self._has_data and self._critical

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        w, h = float(self.width()), float(self.height())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        self.draw_card(painter, margin=4.0, radius=12.0)

        # Title / Label
        label_h = h * 0.32
        painter.setPen(self.color(config.COLOR_TEXT_DIM))
        painter.setFont(self.scaled_font(max(10, h * 0.19), spacing=28))
        painter.drawText(
            QRectF(0, label_h * 0.10, w, label_h),
            Qt.AlignHCenter | Qt.AlignTop,
            "FUEL SYS",
        )

        # Status text
        value_rect = QRectF(0, label_h, w, h - label_h - 4)

        if not self._has_data:
            painter.setPen(self.color(config.COLOR_TEXT_DIM))
            painter.setFont(self.scaled_font(h * 0.38))
            painter.drawText(value_rect, Qt.AlignCenter, "--")
        else:
            color = self.color(self._status_color)
            if self._critical and not self._flash_on:
                color = self.color(self._status_color, alpha=90)
            painter.setFont(self.scaled_font(h * 0.36, bold=True))
            self.draw_glow_text(
                painter,
                value_rect,
                Qt.AlignCenter,
                self._status_text,
                color,
                glow=self._critical and self._flash_on,
            )
        painter.end()
