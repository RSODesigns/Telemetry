"""
scratch_test_motec_dash.py
==========================
Renders a MoTeC C125 / AiM MXG Motorsport Dash UI prototype with subtle 3D depth effects.
"""

from __future__ import annotations

import math
import sys

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PyQt5.QtWidgets import QApplication, QWidget

from dashboard import config

app = QApplication.instance() or QApplication(sys.argv)


def make_font(size: int, bold: bool = False, spacing: float = 0.0) -> QFont:
    f = QFont("DejaVu Sans", size, QFont.Bold if bold else QFont.Normal)
    if spacing > 0:
        f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    return f


class MotecTrackWindow(QWidget):
    """MoTeC C125 / AiM MXG style motorsport cluster window with subtle 3D depth."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.resize(800, 480)
        self.setStyleSheet("background-color: #06070a;")

        # Telemetry State
        self.rpm = 6937.0
        self.speed = 45.0
        self.coolant = 87.0
        self.intake = 48.0
        self.fuel = 64.0
        self.battery = 14.1
        self.throttle = 64.0
        self.lap_num = 2
        self.lap_time_str = "01:24.38"
        self.best_time_str = "01:21.40"
        self.running = True

    def paintEvent(self, _event) -> None:
        w, h = float(self.width()), float(self.height())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        # 1. 3D Recessed Cockpit Background with subtle radial depth gradient
        bg_grad = QRadialGradient(w * 0.5, h * 0.45, w * 0.6)
        bg_grad.setColorAt(0.0, QColor("#111622"))
        bg_grad.setColorAt(0.6, QColor("#090c12"))
        bg_grad.setColorAt(1.0, QColor("#040508"))
        painter.fillRect(self.rect(), bg_grad)

        # Subtle background grid lines for technical cockpit depth
        painter.setPen(QPen(QColor(255, 255, 255, 6), 1.0, Qt.DotLine))
        for x in range(50, int(w), 50):
            painter.drawLine(x, 0, x, int(h))
        for y in range(40, int(h), 40):
            painter.drawLine(0, y, int(w), y)

        # 2. 3D Shift Light Strip (Curved LED sockets across top)
        self._draw_3d_shift_lights(painter, w, h)

        # 3. Dominant Central 3D MoTeC Gauge Pod (Center: 400, 235)
        cx, cy = 400.0, 235.0
        R = 155.0
        self._draw_3d_central_tachometer(painter, cx, cy, R)

        # 4. Left Telemetry Readouts (Coolant, Intake, Fuel)
        self._draw_left_telemetry(painter, 35.0, h)

        # 5. Right Telemetry Readouts (Speed, Battery, Throttle)
        self._draw_right_telemetry(painter, w - 185.0, h)

        # 6. Bottom Status Row
        self._draw_status_bar(painter, w, h)

        painter.end()

    # ------------------------------------------------------------------ #
    # 3D Shift Light Strip
    # ------------------------------------------------------------------ #
    def _draw_3d_shift_lights(self, painter: QPainter, w: float, h: float) -> None:
        count = 10
        strip_w = 340.0
        x0 = (w - strip_w) * 0.5
        led_w = 26.0
        led_h = 12.0
        y0 = 16.0

        for i in range(count):
            x = x0 + i * (strip_w / count)
            offset_y = -math.sin(i / (count - 1) * math.pi) * 6.0
            rect = QRectF(x, y0 + offset_y, led_w, led_h)

            # 3D Outer socket bevel
            painter.setBrush(QColor("#0d1017"))
            painter.setPen(QPen(QColor("#242c3d"), 1.0))
            painter.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), 5, 5)

            lit = (self.rpm / 8500.0) >= ((i + 1) / count)
            if i < 4:
                col_hex = "#20e07b"  # Green
            elif i < 7:
                col_hex = "#ffb020"  # Yellow
            else:
                col_hex = "#ff3838"  # Red

            if lit:
                # 3D LED lens linear gradient (bright top highlight)
                led_grad = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.bottom())
                led_grad.setColorAt(0.0, QColor("#ffffff"))
                led_grad.setColorAt(0.35, QColor(col_hex))
                led_grad.setColorAt(1.0, QColor(col_hex).darker(140))

                # Glow halo
                halo = QColor(col_hex)
                halo.setAlpha(110)
                painter.setPen(QPen(halo, 4.0))
                painter.setBrush(led_grad)
                painter.drawRoundedRect(rect, 3, 3)

                # Specular top highlight line
                painter.setPen(QPen(QColor(255, 255, 255, 200), 1.0))
                painter.drawLine(QPointF(rect.left() + 3, rect.top() + 2), QPointF(rect.right() - 3, rect.top() + 2))
            else:
                unlit_grad = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.bottom())
                unlit_grad.setColorAt(0.0, QColor("#1c2230"))
                unlit_grad.setColorAt(1.0, QColor("#0f131a"))
                painter.setBrush(unlit_grad)
                painter.setPen(QPen(QColor("#2c3444"), 1.0))
                painter.drawRoundedRect(rect, 3, 3)

    # ------------------------------------------------------------------ #
    # Dominant Central 3D Tachometer Gauge Pod
    # ------------------------------------------------------------------ #
    def _draw_3d_central_tachometer(self, painter: QPainter, cx: float, cy: float, R: float) -> None:
        arc_rect = QRectF(cx - R, cy - R, 2 * R, 2 * R)
        start_angle = 225.0
        sweep_angle = 270.0

        # --- 3D Outer Metallic Bezel Ring ---
        outer_bezel_r = R + 14.0
        bezel_grad = QRadialGradient(cx, cy - 30, outer_bezel_r)
        bezel_grad.setColorAt(0.0, QColor("#2a3447"))
        bezel_grad.setColorAt(0.85, QColor("#121722"))
        bezel_grad.setColorAt(1.0, QColor("#080a0e"))
        painter.setBrush(bezel_grad)
        painter.setPen(QPen(QColor("#38465e"), 1.5))
        painter.drawEllipse(QPointF(cx, cy), outer_bezel_r, outer_bezel_r)

        # Bezel Outer Shadow
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(0, 0, 0, 160), 3.0))
        painter.drawEllipse(QPointF(cx, cy), outer_bezel_r + 1, outer_bezel_r + 1)

        # --- 3D Recessed Track Groove ---
        painter.setPen(QPen(QColor("#0a0c12"), 26.0, Qt.SolidLine, Qt.FlatCap))
        painter.drawArc(arc_rect, int(start_angle * 16), int(-sweep_angle * 16))

        # Colored sectors: Blue (0-6.2k), Green (6.2k-7.8k), Red (7.8k-8.5k)
        blue_sweep = sweep_angle * (6200.0 / 8500.0)
        painter.setPen(QPen(QColor("#1e60d0"), 22.0, Qt.SolidLine, Qt.FlatCap))
        painter.drawArc(arc_rect, int(start_angle * 16), int(-blue_sweep * 16))

        cam_start_ang = start_angle - blue_sweep
        cam_sweep = sweep_angle * ((7800.0 - 6200.0) / 8500.0)
        painter.setPen(QPen(QColor("#20e07b"), 22.0, Qt.SolidLine, Qt.FlatCap))
        painter.drawArc(arc_rect, int(cam_start_ang * 16), int(-cam_sweep * 16))

        red_start_ang = cam_start_ang - cam_sweep
        red_sweep = sweep_angle * ((8500.0 - 7800.0) / 8500.0)
        painter.setPen(QPen(QColor("#ff3838"), 22.0, Qt.SolidLine, Qt.FlatCap))
        painter.drawArc(arc_rect, int(red_start_ang * 16), int(-red_sweep * 16))

        # 3D Inner Bevel Shadow on Arc Track
        painter.setPen(QPen(QColor(0, 0, 0, 90), 4.0, Qt.SolidLine, Qt.FlatCap))
        painter.drawArc(QRectF(cx - R + 9, cy - R + 9, 2 * (R - 9), 2 * (R - 9)), int(start_angle * 16), int(-sweep_angle * 16))

        # Active RPM Fill Needle / Cursor
        frac = min(1.0, max(0.0, self.rpm / 8500.0))
        val_sweep = frac * sweep_angle

        # 3D Bright Value Overlay Line with Glow
        painter.setPen(QPen(QColor(255, 255, 255, 70), 8.0, Qt.SolidLine, Qt.FlatCap))
        painter.drawArc(arc_rect, int(start_angle * 16), int(-val_sweep * 16))
        painter.setPen(QPen(QColor("#ffffff"), 4.0, Qt.SolidLine, Qt.FlatCap))
        painter.drawArc(arc_rect, int(start_angle * 16), int(-val_sweep * 16))

        # 3D Hairline Cursor with Shadow
        cur_ang = math.radians(start_angle - val_sweep)
        p_inner = QPointF(cx + (R - 15) * math.cos(cur_ang), cy - (R - 15) * math.sin(cur_ang))
        p_outer = QPointF(cx + (R + 15) * math.cos(cur_ang), cy - (R + 15) * math.sin(cur_ang))
        
        # Cursor Shadow
        painter.setPen(QPen(QColor(0, 0, 0, 180), 4.0))
        painter.drawLine(QPointF(p_inner.x() + 2, p_inner.y() + 2), QPointF(p_outer.x() + 2, p_outer.y() + 2))
        
        # White Hairline
        painter.setPen(QPen(QColor("#ffffff"), 3.5))
        painter.drawLine(p_inner, p_outer)

        # Scale tick numbers (0..8) with subtle 3D drop shadow
        painter.setFont(make_font(12, bold=True))
        for r in range(0, 9):
            rf = r / 8.5
            ang = math.radians(start_angle - rf * sweep_angle)
            px = cx + (R - 32) * math.cos(ang)
            py = cy - (R - 32) * math.sin(ang)

            # Drop shadow
            painter.setPen(QColor(0, 0, 0, 200))
            painter.drawText(QRectF(px - 11, py - 11, 24, 24), Qt.AlignCenter, str(r))

            # Foreground text
            painter.setPen(QColor("#ffffff" if r >= 6 else "#a0acbf"))
            painter.drawText(QRectF(px - 12, py - 12, 24, 24), Qt.AlignCenter, str(r))

        # --- 3D RECESSED INNER GAUGE POD CUP -----------------------------
        inner_r = R - 42.0
        
        # Radial Gradient Cup (Dark Rim fading to lighter center)
        pod_grad = QRadialGradient(cx, cy, inner_r)
        pod_grad.setColorAt(0.0, QColor("#141a26"))
        pod_grad.setColorAt(0.7, QColor("#0c0f17"))
        pod_grad.setColorAt(1.0, QColor("#06080d"))

        painter.setBrush(pod_grad)
        painter.setPen(QPen(QColor("#242e40"), 2.0))
        painter.drawEllipse(QPointF(cx, cy), inner_r, inner_r)

        # Inner Sunken Shadow Ring
        shadow_grad = QRadialGradient(cx, cy, inner_r)
        shadow_grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        shadow_grad.setColorAt(0.85, QColor(0, 0, 0, 80))
        shadow_grad.setColorAt(1.0, QColor(0, 0, 0, 180))
        painter.setBrush(shadow_grad)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx, cy), inner_r, inner_r)

        # 1. Digital RPM with Drop Shadow (Top of pod)
        rpm_rect = QRectF(cx - 70, cy - 85, 140, 36)
        
        # Shadow
        painter.setFont(make_font(26, bold=True))
        painter.setPen(QColor(0, 0, 0, 220))
        painter.drawText(rpm_rect.translated(2, 2), Qt.AlignCenter, f"{int(self.rpm)}")
        
        # Text
        painter.setPen(QColor("#ffffff"))
        painter.drawText(rpm_rect, Qt.AlignCenter, f"{int(self.rpm)}")

        painter.setFont(make_font(9, bold=True, spacing=1.5))
        painter.setPen(QColor("#6b7a90"))
        painter.drawText(QRectF(cx - 50, cy - 52, 100, 16), Qt.AlignCenter, "RPM")

        # 3D Groove Divider line
        painter.setPen(QPen(QColor("#080a0e"), 2.0))
        painter.drawLine(QPointF(cx - 65, cy - 33), QPointF(cx + 65, cy - 33))
        painter.setPen(QPen(QColor("#2a3547"), 1.0))
        painter.drawLine(QPointF(cx - 65, cy - 34), QPointF(cx + 65, cy - 34))

        # 2. Lap Number & Lap Timer Display with 3D Drop Shadow
        painter.setFont(make_font(10, bold=True))
        painter.setPen(QColor("#34c8ff"))
        painter.drawText(QRectF(cx - 60, cy - 28, 120, 18), Qt.AlignCenter, f"LAP {self.lap_num}")

        time_rect = QRectF(cx - 85, cy - 8, 170, 38)
        painter.setFont(make_font(28, bold=True))
        painter.setPen(QColor(0, 0, 0, 220))
        painter.drawText(time_rect.translated(2, 2), Qt.AlignCenter, self.lap_time_str)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(time_rect, Qt.AlignCenter, self.lap_time_str)

        # 3. Best Lap Split
        painter.setFont(make_font(10, bold=True))
        painter.setPen(QColor("#20e07b"))
        painter.drawText(QRectF(cx - 70, cy + 34, 140, 20), Qt.AlignCenter, f"BEST  {self.best_time_str}")

        # 3D Touch Pill Buttons (START/STOP & RESET)
        btn_w, btn_h = 52, 20
        
        # START/STOP (Right)
        b_right = QRectF(cx + 10, cy + 57, btn_w, btn_h)
        btn_grad1 = QLinearGradient(b_right.left(), b_right.top(), b_right.left(), b_right.bottom())
        btn_grad1.setColorAt(0.0, QColor("rgba(32, 224, 123, 60)"))
        btn_grad1.setColorAt(1.0, QColor("rgba(32, 224, 123, 20)"))
        painter.setBrush(btn_grad1)
        painter.setPen(QPen(QColor("#20e07b"), 1.2))
        painter.drawRoundedRect(b_right, 5, 5)
        painter.setFont(make_font(8, bold=True))
        painter.setPen(QColor("#20e07b"))
        painter.drawText(b_right, Qt.AlignCenter, "START")

        # RESET (Left)
        b_left = QRectF(cx - 62, cy + 57, btn_w, btn_h)
        btn_grad2 = QLinearGradient(b_left.left(), b_left.top(), b_left.left(), b_left.bottom())
        btn_grad2.setColorAt(0.0, QColor("rgba(130, 138, 152, 45)"))
        btn_grad2.setColorAt(1.0, QColor("rgba(130, 138, 152, 15)"))
        painter.setBrush(btn_grad2)
        painter.setPen(QPen(QColor("#6b7a90"), 1.2))
        painter.drawRoundedRect(b_left, 5, 5)
        painter.setPen(QColor("#c0c9d8"))
        painter.drawText(b_left, Qt.AlignCenter, "RESET")

    # ------------------------------------------------------------------ #
    # Left Telemetry Panel
    # ------------------------------------------------------------------ #
    def _draw_left_telemetry(self, painter: QPainter, x: float, h: float) -> None:
        # COOLANT
        painter.setFont(make_font(9, bold=True, spacing=1.2))
        painter.setPen(QColor("#6b7a90"))
        painter.drawText(QRectF(x, 100, 140, 16), Qt.AlignLeft, "COOLANT")

        painter.setFont(make_font(32, bold=True))
        painter.setPen(QColor(0, 0, 0, 200))
        painter.drawText(QRectF(x + 2, 120, 140, 42), Qt.AlignLeft, f"{int(self.coolant)}\u00b0C")
        painter.setPen(QColor("#20e07b"))
        painter.drawText(QRectF(x, 118, 140, 42), Qt.AlignLeft, f"{int(self.coolant)}\u00b0C")

        # INTAKE
        painter.setFont(make_font(9, bold=True, spacing=1.2))
        painter.setPen(QColor("#6b7a90"))
        painter.drawText(QRectF(x, 205, 140, 16), Qt.AlignLeft, "INTAKE")

        painter.setFont(make_font(32, bold=True))
        painter.setPen(QColor(0, 0, 0, 200))
        painter.drawText(QRectF(x + 2, 225, 140, 42), Qt.AlignLeft, f"{int(self.intake)}\u00b0C")
        painter.setPen(QColor("#ffb020"))
        painter.drawText(QRectF(x, 223, 140, 42), Qt.AlignLeft, f"{int(self.intake)}\u00b0C")

        # FUEL LEVEL
        painter.setFont(make_font(9, bold=True, spacing=1.2))
        painter.setPen(QColor("#6b7a90"))
        painter.drawText(QRectF(x, 310, 140, 16), Qt.AlignLeft, "FUEL LEVEL")

        painter.setFont(make_font(32, bold=True))
        painter.setPen(QColor(0, 0, 0, 200))
        painter.drawText(QRectF(x + 2, 330, 140, 42), Qt.AlignLeft, f"{int(self.fuel)}%")
        painter.setPen(QColor("#20e07b"))
        painter.drawText(QRectF(x, 328, 140, 42), Qt.AlignLeft, f"{int(self.fuel)}%")

        # 3D Vertical accent divider (Embossed double line)
        painter.setPen(QPen(QColor("#07090d"), 1.5))
        painter.drawLine(QPointF(x + 156, 90), QPointF(x + 156, 390))
        painter.setPen(QPen(QColor("#222b3b"), 1.5))
        painter.drawLine(QPointF(x + 154, 90), QPointF(x + 154, 390))

    # ------------------------------------------------------------------ #
    # Right Telemetry Panel
    # ------------------------------------------------------------------ #
    def _draw_right_telemetry(self, painter: QPainter, x: float, h: float) -> None:
        # 3D Vertical accent divider
        painter.setPen(QPen(QColor("#07090d"), 1.5))
        painter.drawLine(QPointF(x - 14, 90), QPointF(x - 14, 390))
        painter.setPen(QPen(QColor("#222b3b"), 1.5))
        painter.drawLine(QPointF(x - 16, 90), QPointF(x - 16, 390))

        # SPEED
        painter.setFont(make_font(9, bold=True, spacing=1.2))
        painter.setPen(QColor("#6b7a90"))
        painter.drawText(QRectF(x, 100, 150, 16), Qt.AlignRight, "SPEED")

        painter.setFont(make_font(36, bold=True))
        painter.setPen(QColor(0, 0, 0, 200))
        painter.drawText(QRectF(x + 2, 120, 150, 44), Qt.AlignRight, f"{int(self.speed)} MPH")
        painter.setPen(QColor("#ffffff"))
        painter.drawText(QRectF(x, 118, 150, 44), Qt.AlignRight, f"{int(self.speed)} MPH")

        # BATTERY
        painter.setFont(make_font(9, bold=True, spacing=1.2))
        painter.setPen(QColor("#6b7a90"))
        painter.drawText(QRectF(x, 205, 150, 16), Qt.AlignRight, "BATTERY")

        painter.setFont(make_font(32, bold=True))
        painter.setPen(QColor(0, 0, 0, 200))
        painter.drawText(QRectF(x + 2, 225, 150, 42), Qt.AlignRight, f"{self.battery:.1f} V")
        painter.setPen(QColor("#34c8ff"))
        painter.drawText(QRectF(x, 223, 150, 42), Qt.AlignRight, f"{self.battery:.1f} V")

        # THROTTLE
        painter.setFont(make_font(9, bold=True, spacing=1.2))
        painter.setPen(QColor("#6b7a90"))
        painter.drawText(QRectF(x, 310, 150, 16), Qt.AlignRight, "THROTTLE")

        painter.setFont(make_font(32, bold=True))
        painter.setPen(QColor(0, 0, 0, 200))
        painter.drawText(QRectF(x + 2, 330, 150, 42), Qt.AlignRight, f"{int(self.throttle)}%")
        painter.setPen(QColor("#34c8ff"))
        painter.drawText(QRectF(x, 328, 150, 42), Qt.AlignRight, f"{int(self.throttle)}%")

    # ------------------------------------------------------------------ #
    # Bottom Status Bar
    # ------------------------------------------------------------------ #
    def _draw_status_bar(self, painter: QPainter, w: float, h: float) -> None:
        painter.setPen(QPen(QColor("#080a0e"), 1.0))
        painter.drawLine(QPointF(20, h - 31), QPointF(w - 20, h - 31))
        painter.setPen(QPen(QColor("#1a2230"), 1.0))
        painter.drawLine(QPointF(20, h - 32), QPointF(w - 20, h - 32))

        painter.setFont(make_font(9, bold=True))
        painter.setPen(QColor("#20e07b"))
        painter.drawText(QRectF(25, h - 26, 200, 20), Qt.AlignLeft | Qt.AlignVCenter, "\u25cf  OBD CONNECTED")

        painter.setPen(QColor("#6b7a90"))
        painter.drawText(QRectF(w - 225, h - 26, 200, 20), Qt.AlignRight | Qt.AlignVCenter, "TRACK MODE \u2014 LOTUS 2ZZ")


if __name__ == "__main__":
    win = MotecTrackWindow()
    img = win.grab()
    paths = [
        "C:/Users/Ger-QA/.gemini/antigravity-ide/brain/f570a03a-776c-4ef1-8a25-839e22589a26/motec_track_render.png",
        "d:/RSODesigns/Projects/Pi/Telemetry/motec_track_render.png",
        "d:/RSODesigns/motec_track_render.png",
    ]
    for p in paths:
        img.save(p)
        print("Saved 3D MoTeC render to:", p)
