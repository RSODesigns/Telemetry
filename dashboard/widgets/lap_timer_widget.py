"""
lap_timer_widget.py
===================

Motorsport Lap Timer widget for the Track dashboard.

Features:
* Live 60 FPS lap timing display (MM:SS.ff).
* Touch & Mouse interactive START / STOP and RESET buttons.
* Tracks current lap number, last lap time, and session best lap time.
* Automatic simulated lap completion in mock mode so the driver sees live
  lap progression, lap splits, and best-lap updates on track.
"""

from __future__ import annotations

import time

from PyQt5.QtCore import QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QPushButton

from .. import config
from .base_gauge import BaseGauge


class LapTimerWidget(BaseGauge):
    """Compact motorsport Lap Timer card with interactive Start/Stop and Reset buttons."""

    def __init__(self, target_lap_time_s: float = 85.0, parent=None) -> None:
        super().__init__(0.0, 1.0, parent)
        self._target_sim_lap_s = target_lap_time_s
        self._lap_number: int = 1
        self._lap_start: float = time.monotonic()
        self._elapsed_paused: float = 0.0
        self._last_lap_s: float | None = None
        self._best_lap_s: float | None = None
        self._running: bool = False  # Start stopped until driver taps START

        self.setMinimumSize(220, 76)

        # Interactive touch/mouse buttons
        self._btn_reset = QPushButton("RESET", self)
        self._btn_reset.setCursor(Qt.PointingHandCursor)
        self._btn_reset.clicked.connect(self.reset_timer)

        self._btn_start_stop = QPushButton("START", self)
        self._btn_start_stop.setCursor(Qt.PointingHandCursor)
        self._btn_start_stop.clicked.connect(self._toggle_start_stop)

        self._update_button_styles()

        # 60 FPS timer for smooth hundredths-of-a-second readout updates
        self._timer = QTimer(self)
        self._timer.setInterval(config.FRAME_INTERVAL_MS)
        self._timer.timeout.connect(self.update)
        self._timer.start()

    # ------------------------------------------------------------------ #
    # Public & Internal Controls
    # ------------------------------------------------------------------ #
    def start_timer(self) -> None:
        if not self._running:
            self._lap_start = time.monotonic()
            self._running = True
            self._update_button_styles()
            self.update()

    def stop_timer(self) -> None:
        if self._running:
            self._elapsed_paused += time.monotonic() - self._lap_start
            self._running = False
            self._update_button_styles()
            self.update()

    def _toggle_start_stop(self) -> None:
        if self._running:
            self.stop_timer()
        else:
            self.start_timer()

    def reset_timer(self) -> None:
        self._lap_number = 1
        self._running = False
        self._lap_start = time.monotonic()
        self._elapsed_paused = 0.0
        self._last_lap_s = None
        self._best_lap_s = None
        self._update_button_styles()
        self.update()

    def complete_lap(self) -> None:
        """Trigger lap completion: record last/best times and start new lap."""
        now = time.monotonic()
        elapsed = (now - self._lap_start + self._elapsed_paused) if self._running else self._elapsed_paused
        self._last_lap_s = elapsed
        if self._best_lap_s is None or elapsed < self._best_lap_s:
            self._best_lap_s = elapsed
        self._lap_number += 1
        self._lap_start = now
        self._elapsed_paused = 0.0
        self.update()

    def _update_button_styles(self) -> None:
        if self._running:
            self._btn_start_stop.setText("STOP")
            self._btn_start_stop.setStyleSheet(
                "QPushButton {"
                "  background-color: rgba(255, 56, 56, 35);"
                "  color: #ff3838;"
                "  border: 1px solid rgba(255, 56, 56, 160);"
                "  border-radius: 5px;"
                "  font-weight: bold;"
                "  font-size: 10px;"
                "}"
                "QPushButton:hover { background-color: rgba(255, 56, 56, 75); }"
            )
        else:
            self._btn_start_stop.setText("START")
            self._btn_start_stop.setStyleSheet(
                "QPushButton {"
                "  background-color: rgba(32, 224, 123, 35);"
                "  color: #20e07b;"
                "  border: 1px solid rgba(32, 224, 123, 160);"
                "  border-radius: 5px;"
                "  font-weight: bold;"
                "  font-size: 10px;"
                "}"
                "QPushButton:hover { background-color: rgba(32, 224, 123, 75); }"
            )

        self._btn_reset.setStyleSheet(
            "QPushButton {"
            "  background-color: rgba(130, 138, 152, 25);"
            "  color: #828a98;"
            "  border: 1px solid rgba(130, 138, 152, 100);"
            "  border-radius: 5px;"
            "  font-weight: bold;"
            "  font-size: 10px;"
            "}"
            "QPushButton:hover { background-color: rgba(130, 138, 152, 50); color: #f3f6fc; }"
        )

    # ------------------------------------------------------------------ #
    # Geometry layout for buttons
    # ------------------------------------------------------------------ #
    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        w, h = float(self.width()), float(self.height())
        btn_w, btn_h = 54, 22
        margin_right = 10
        margin_top = 7

        self._btn_start_stop.setGeometry(int(w - margin_right - btn_w), int(margin_top), btn_w, btn_h)
        self._btn_reset.setGeometry(int(w - margin_right - 2 * btn_w - 6), int(margin_top), btn_w, btn_h)

    # ------------------------------------------------------------------ #
    # Helper formatters
    # ------------------------------------------------------------------ #
    @staticmethod
    def _format_time(seconds: float | None, show_hundredths: bool = True) -> str:
        if seconds is None:
            return "--:--.--" if show_hundredths else "--:--"
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        if show_hundredths:
            hundredths = int((seconds - int(seconds)) * 100)
            return f"{mins:02d}:{secs:02d}.{hundredths:02d}"
        return f"{mins:02d}:{secs:02d}"

    # ------------------------------------------------------------------ #
    # Rendering
    # ------------------------------------------------------------------ #
    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        w, h = float(self.width()), float(self.height())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        self.draw_card(painter, margin=4.0, radius=12.0)

        # Elapsed time calculation & simulated lap trigger
        now = time.monotonic()
        elapsed = (now - self._lap_start + self._elapsed_paused) if self._running else self._elapsed_paused

        # Auto-complete simulated lap when running target duration
        if self._running and self._target_sim_lap_s > 0 and elapsed >= self._target_sim_lap_s:
            self.complete_lap()
            now = time.monotonic()
            elapsed = (now - self._lap_start + self._elapsed_paused) if self._running else self._elapsed_paused

        # --- Top Header: LAP # (Left) | BEST (Center) ---------------------
        header_h = h * 0.28
        header_y = header_h * 0.12
        margin_left = 12.0
        btn_zone_w = 124.0  # reserved width for top-right buttons

        # Left: LAP X
        painter.setPen(self.color(config.COLOR_TEXT_DIM))
        painter.setFont(self.scaled_font(max(10, h * 0.18), spacing=24))
        painter.drawText(
            QRectF(margin_left, header_y, 70.0, header_h),
            Qt.AlignLeft | Qt.AlignTop,
            f"LAP {self._lap_number}",
        )

        # Center/Right: BEST time summary
        if self._best_lap_s is not None:
            best_str = f"BEST {self._format_time(self._best_lap_s)}"
            painter.setPen(self.color(config.COLOR_OPTIMAL))
            painter.drawText(
                QRectF(85.0, header_y, w - 85.0 - btn_zone_w - 6.0, header_h),
                Qt.AlignLeft | Qt.AlignTop,
                best_str,
            )

        # --- Main Live Timer Readout (Center) -----------------------------
        time_rect = QRectF(0, header_h * 0.85, w, h - header_h - 4)
        time_str = self._format_time(elapsed, show_hundredths=True)

        color = self.color(config.COLOR_ACCENT) if self._running else self.color(config.COLOR_TEXT_DIM)
        painter.setFont(self.scaled_font(h * 0.44, bold=True))
        self.draw_glow_text(
            painter,
            time_rect,
            Qt.AlignCenter,
            time_str,
            color,
            glow=False,
        )

        painter.end()
