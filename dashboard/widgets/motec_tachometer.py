"""
motec_tachometer.py
===================

3D MoTeC C125 / AiM MXG Motorsport Tachometer Gauge & Inner Pod.

Features:
* 3D Recessed instrument pod with metallic bezel and radial cup shading.
* Curved top 10-LED shift light strip (Green -> Yellow -> Red).
* Radial 0-8500 RPM arc scale tuned for Lotus 2ZZ-GE engine zones.
* Integrated inner pod displaying Digital RPM, Lap Number, Live Lap Timer,
  and Best Lap splits with touch-interactive START/STOP and RESET buttons.
"""

from __future__ import annotations

import math
import time

from PyQt5.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QRadialGradient
from PyQt5.QtWidgets import QPushButton

from .. import config
from .base_gauge import BaseGauge


def _make_font(size: int, bold: bool = False, spacing: float = 0.0) -> QFont:
    f = QFont("DejaVu Sans", size, QFont.Bold if bold else QFont.Normal)
    if spacing > 0:
        f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    return f


class MotecTachometer(BaseGauge):
    """3D MoTeC style Motorsport Tachometer & Central Display Pod."""

    def __init__(self, parent=None) -> None:
        super().__init__(config.RPM_MIN, config.RPM_MAX, parent)

        # Lap Timer State
        self._lap_number: int = 1
        self._lap_start: float = time.monotonic()
        self._elapsed_paused: float = 0.0
        self._last_lap_s: float | None = None
        self._best_lap_s: float | None = None
        self._running: bool = False  # Start stopped until driver taps START
        self._target_sim_lap_s: float = 85.0

        self.setMinimumSize(360, 360)

        # Interactive Touch Buttons inside/under pod
        self._btn_reset = QPushButton("RESET", self)
        self._btn_reset.setCursor(Qt.PointingHandCursor)
        self._btn_reset.clicked.connect(self.reset_timer)

        self._btn_start_stop = QPushButton("START", self)
        self._btn_start_stop.setCursor(Qt.PointingHandCursor)
        self._btn_start_stop.clicked.connect(self._toggle_start_stop)

        self._update_button_styles()

        # 60 FPS animation timer
        self._timer = QTimer(self)
        self._timer.setInterval(config.FRAME_INTERVAL_MS)
        self._timer.timeout.connect(self.update)
        self._timer.start()

    # ------------------------------------------------------------------ #
    # Lap Timer Controls
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
                "  background-color: rgba(255, 255, 255, 25);"
                "  color: #ffffff;"
                "  border: 1px solid rgba(255, 255, 255, 140);"
                "  border-radius: 5px;"
                "  font-weight: bold;"
                "  font-size: 9px;"
                "}"
                "QPushButton:hover { background-color: rgba(255, 255, 255, 55); }"
            )
        else:
            self._btn_start_stop.setText("START")
            self._btn_start_stop.setStyleSheet(
                "QPushButton {"
                "  background-color: rgba(232, 24, 32, 35);"
                "  color: #e81820;"
                "  border: 1px solid rgba(232, 24, 32, 160);"
                "  border-radius: 5px;"
                "  font-weight: bold;"
                "  font-size: 9px;"
                "}"
                "QPushButton:hover { background-color: rgba(232, 24, 32, 75); }"
            )

        self._btn_reset.setStyleSheet(
            "QPushButton {"
            "  background-color: rgba(138, 126, 128, 25);"
            "  color: #8a7e80;"
            "  border: 1px solid rgba(138, 126, 128, 100);"
            "  border-radius: 5px;"
            "  font-weight: bold;"
            "  font-size: 9px;"
            "}"
            "QPushButton:hover { background-color: rgba(138, 126, 128, 50); color: #f5f0f0; }"
        )

    # ------------------------------------------------------------------ #
    # Button Geometry
    # ------------------------------------------------------------------ #
    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        w, h = float(self.width()), float(self.height())
        cx, cy = w * 0.5, h * 0.52
        btn_w, btn_h = 54, 20

        self._btn_start_stop.setGeometry(int(cx + 8), int(cy + 60), btn_w, btn_h)
        self._btn_reset.setGeometry(int(cx - 62), int(cy + 60), btn_w, btn_h)

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


        # 2. Central Tachometer Pod
        cx, cy = w * 0.5, h * 0.52
        R = min(w, h) * 0.5 * 0.78
        self._draw_3d_central_tachometer(painter, cx, cy, R)

        painter.end()

    def _draw_3d_shift_lights(self, painter: QPainter, w: float, h: float) -> None:
        count = 10
        strip_w = min(w * 0.85, 340.0)
        x0 = (w - strip_w) * 0.5
        led_w = strip_w / count * 0.76
        led_h = 12.0
        y0 = 10.0

        for i in range(count):
            x = x0 + i * (strip_w / count)
            offset_y = -math.sin(i / (count - 1) * math.pi) * 6.0
            rect = QRectF(x, y0 + offset_y, led_w, led_h)

            # Outer socket bevel
            painter.setBrush(QColor("#0b0b0b"))
            painter.setPen(QPen(QColor("#252525"), 1.0))
            painter.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), 5, 5)

            rpm_val = self.value if self._has_data else 0.0
            lit = (rpm_val / config.RPM_MAX) >= ((i + 1) / count)
            if i < 4:
                col_hex = config.COLOR_OPTIMAL  # Green
            elif i < 7:
                col_hex = config.COLOR_AMBER    # Yellow
            else:
                col_hex = config.COLOR_CRITICAL # Red

            if lit:
                led_grad = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.bottom())
                led_grad.setColorAt(0.0, QColor("#ffffff"))
                led_grad.setColorAt(0.35, QColor(col_hex))
                led_grad.setColorAt(1.0, QColor(col_hex).darker(140))

                halo = QColor(col_hex)
                halo.setAlpha(110)
                painter.setPen(QPen(halo, 4.0))
                painter.setBrush(led_grad)
                painter.drawRoundedRect(rect, 3, 3)

                painter.setPen(QPen(QColor(255, 255, 255, 200), 1.0))
                painter.drawLine(QPointF(rect.left() + 3, rect.top() + 2), QPointF(rect.right() - 3, rect.top() + 2))
            else:
                unlit_grad = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.bottom())
                unlit_grad.setColorAt(0.0, QColor("#181818"))
                unlit_grad.setColorAt(1.0, QColor("#0d0d0d"))
                painter.setBrush(unlit_grad)
                painter.setPen(QPen(QColor("#282828"), 1.0))
                painter.drawRoundedRect(rect, 3, 3)

    def _draw_3d_central_tachometer(self, painter: QPainter, cx: float, cy: float, R: float) -> None:
        arc_rect = QRectF(cx - R, cy - R, 2 * R, 2 * R)
        start_angle = 225.0
        sweep_angle = 270.0

        # --- 3D Outer Metallic Bezel Ring ---
        outer_bezel_r = R + 14.0
        bezel_grad = QRadialGradient(cx, cy - 30, outer_bezel_r)
        bezel_grad.setColorAt(0.0, QColor("#212121"))
        bezel_grad.setColorAt(0.85, QColor("#0f0f0f"))
        bezel_grad.setColorAt(1.0, QColor("#070707"))
        painter.setBrush(bezel_grad)
        painter.setPen(QPen(QColor("#2b2b2b"), 1.5))
        painter.drawEllipse(QPointF(cx, cy), outer_bezel_r, outer_bezel_r)

        # Bezel Outer Shadow
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(0, 0, 0, 160), 3.0))
        painter.drawEllipse(QPointF(cx, cy), outer_bezel_r + 1, outer_bezel_r + 1)

        # --- 3D Recessed Track Groove ---
        painter.setPen(QPen(QColor("#080808"), 26.0, Qt.SolidLine, Qt.FlatCap))
        painter.drawArc(arc_rect, int(start_angle * 16), int(-sweep_angle * 16))

        # Sector 1: Off-cam Silver (0 to 6.2k)
        blue_sweep = sweep_angle * (config.TRACK_RPM_CAM_SWITCH / config.RPM_MAX)
        painter.setPen(QPen(QColor("#b0b0b0"), 22.0, Qt.SolidLine, Qt.FlatCap))
        painter.drawArc(arc_rect, int(start_angle * 16), int(-blue_sweep * 16))

        # Sector 2: On-cam White (6.2k to 8.4k)
        cam_start_ang = start_angle - blue_sweep
        cam_sweep = sweep_angle * ((8400.0 - config.TRACK_RPM_CAM_SWITCH) / config.RPM_MAX)
        painter.setPen(QPen(QColor("#ffffff"), 22.0, Qt.SolidLine, Qt.FlatCap))
        painter.drawArc(arc_rect, int(cam_start_ang * 16), int(-cam_sweep * 16))

        # Sector 3: Redline Red (8.4k to 8.5k)
        red_start_ang = cam_start_ang - cam_sweep
        red_sweep = sweep_angle * ((config.RPM_MAX - 8400.0) / config.RPM_MAX)
        painter.setPen(QPen(QColor(config.COLOR_CRITICAL), 22.0, Qt.SolidLine, Qt.FlatCap))
        painter.drawArc(arc_rect, int(red_start_ang * 16), int(-red_sweep * 16))

        # 3D Inner Bevel Shadow on Arc Track
        painter.setPen(QPen(QColor(0, 0, 0, 90), 4.0, Qt.SolidLine, Qt.FlatCap))
        painter.drawArc(QRectF(cx - R + 9, cy - R + 9, 2 * (R - 9), 2 * (R - 9)), int(start_angle * 16), int(-sweep_angle * 16))

        # Active RPM Value Overlay
        rpm_val = self.value if self._has_data else 0.0
        frac = min(1.0, max(0.0, rpm_val / config.RPM_MAX))
        val_sweep = frac * sweep_angle

        painter.setPen(QPen(QColor(255, 255, 255, 70), 8.0, Qt.SolidLine, Qt.FlatCap))
        painter.drawArc(arc_rect, int(start_angle * 16), int(-val_sweep * 16))
        painter.setPen(QPen(QColor("#ffffff"), 4.0, Qt.SolidLine, Qt.FlatCap))
        painter.drawArc(arc_rect, int(start_angle * 16), int(-val_sweep * 16))

        # Hairline Cursor
        cur_ang = math.radians(start_angle - val_sweep)
        p_inner = QPointF(cx + (R - 15) * math.cos(cur_ang), cy - (R - 15) * math.sin(cur_ang))
        p_outer = QPointF(cx + (R + 15) * math.cos(cur_ang), cy - (R + 15) * math.sin(cur_ang))

        painter.setPen(QPen(QColor(0, 0, 0, 180), 4.0))
        painter.drawLine(QPointF(p_inner.x() + 2, p_inner.y() + 2), QPointF(p_outer.x() + 2, p_outer.y() + 2))
        painter.setPen(QPen(QColor("#ffffff"), 3.5))
        painter.drawLine(p_inner, p_outer)

        # Scale Ticks (0..8)
        painter.setFont(_make_font(12, bold=True))
        for r in range(0, 9):
            rf = r / 8.5
            ang = math.radians(start_angle - rf * sweep_angle)
            px = cx + (R - 32) * math.cos(ang)
            py = cy - (R - 32) * math.sin(ang)

            painter.setPen(QColor(0, 0, 0, 200))
            painter.drawText(QRectF(px - 11, py - 11, 24, 24), Qt.AlignCenter, str(r))

            painter.setPen(QColor("#ffffff" if r >= 6 else "#a09898"))
            painter.drawText(QRectF(px - 12, py - 12, 24, 24), Qt.AlignCenter, str(r))

        # --- 3D RECESSED INNER GAUGE POD CUP -----------------------------
        inner_r = R - 42.0
        pod_grad = QRadialGradient(cx, cy, inner_r)
        pod_grad.setColorAt(0.0, QColor("#121212"))
        pod_grad.setColorAt(0.7, QColor("#0a0a0a"))
        pod_grad.setColorAt(1.0, QColor("#050505"))

        painter.setBrush(pod_grad)
        painter.setPen(QPen(QColor("#252525"), 2.0))
        painter.drawEllipse(QPointF(cx, cy), inner_r, inner_r)

        # Inner Sunken Shadow Ring
        shadow_grad = QRadialGradient(cx, cy, inner_r)
        shadow_grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        shadow_grad.setColorAt(0.85, QColor(0, 0, 0, 80))
        shadow_grad.setColorAt(1.0, QColor(0, 0, 0, 180))
        painter.setBrush(shadow_grad)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx, cy), inner_r, inner_r)

        # 1. Digital RPM with Drop Shadow
        rpm_rect = QRectF(cx - 70, cy - 85, 140, 36)
        painter.setFont(_make_font(26, bold=True))
        painter.setPen(QColor(0, 0, 0, 220))
        painter.drawText(rpm_rect.translated(2, 2), Qt.AlignCenter, f"{int(rpm_val)}")
        painter.setPen(QColor("#ffffff"))
        painter.drawText(rpm_rect, Qt.AlignCenter, f"{int(rpm_val)}")

        painter.setFont(_make_font(9, bold=True, spacing=1.5))
        painter.setPen(QColor("#7a7a7a"))
        painter.drawText(QRectF(cx - 50, cy - 52, 100, 16), Qt.AlignCenter, "RPM")

        # 3D Groove Divider line
        painter.setPen(QPen(QColor("#060606"), 2.0))
        painter.drawLine(QPointF(cx - 65, cy - 33), QPointF(cx + 65, cy - 33))
        painter.setPen(QPen(QColor("#252525"), 1.0))
        painter.drawLine(QPointF(cx - 65, cy - 34), QPointF(cx + 65, cy - 34))

        # 2. Lap Timer State & Elapsed Time calculation
        now = time.monotonic()
        elapsed = (now - self._lap_start + self._elapsed_paused) if self._running else self._elapsed_paused
        if self._running and self._target_sim_lap_s > 0 and elapsed >= self._target_sim_lap_s:
            self.complete_lap()
            now = time.monotonic()
            elapsed = (now - self._lap_start + self._elapsed_paused) if self._running else self._elapsed_paused

        painter.setFont(_make_font(10, bold=True))
        painter.setPen(QColor(config.COLOR_ACCENT))
        painter.drawText(QRectF(cx - 60, cy - 28, 120, 18), Qt.AlignCenter, f"LAP {self._lap_number}")

        time_rect = QRectF(cx - 85, cy - 8, 170, 38)
        time_str = self._format_time(elapsed, show_hundredths=True)
        painter.setFont(_make_font(28, bold=True))
        painter.setPen(QColor(0, 0, 0, 220))
        painter.drawText(time_rect.translated(2, 2), Qt.AlignCenter, time_str)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(time_rect, Qt.AlignCenter, time_str)

        # 3. Best Lap Split
        painter.setFont(_make_font(10, bold=True))
        painter.setPen(QColor(config.COLOR_OPTIMAL))
        best_str = f"BEST  {self._format_time(self._best_lap_s)}"
        painter.drawText(QRectF(cx - 70, cy + 34, 140, 20), Qt.AlignCenter, best_str)
