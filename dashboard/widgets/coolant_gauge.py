"""
coolant_gauge.py
================

Left-hand element: a vertical progress-bar style coolant-temperature gauge
drawn entirely with :class:`QPainter` vector primitives, styled as an elevated
"card" with a neon liquid column.

Colour logic (from the UX spec)
-------------------------------
* **Blue**  - below 70 C (engine still cold / warming up)
* **Green** - 70-90 C (healthy operating band)
* **Red**   - 90 C and above (overheating danger zone)

Coordinate mapping
------------------
The bar occupies a fixed rectangle. A temperature ``t`` maps to a fill height
by normalising it against the gauge scale::

    frac  = (t - COOLANT_MIN_C) / (COOLANT_MAX_C - COOLANT_MIN_C)
    fill  = bar_height * frac            # measured up from the bar's bottom

The same normalisation places the tick labels and the fixed 98 C red-line
marker, so everything stays aligned at any widget size.
"""

from __future__ import annotations

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen

from .. import config
from .base_gauge import BaseGauge

# General-dashboard coolant zone colours (distinct from the track theme).
_COOLANT_GREEN = "#30b860"         # healthy operating band (70-90 C)
_COOLANT_ZONE_HOT_C = 90.0        # >= 90 C => red


class CoolantGauge(BaseGauge):
    """Vertical bar gauge for engine coolant temperature (deg C)."""

    def __init__(self, parent=None) -> None:
        super().__init__(config.COOLANT_MIN_C, config.COOLANT_MAX_C, parent)

    # ------------------------------------------------------------------ #
    # Critical-state hook (drives the shared blink phase)
    # ------------------------------------------------------------------ #
    def is_flashing(self) -> bool:
        return self._has_data and self.value > config.COOLANT_CRITICAL_C

    # ------------------------------------------------------------------ #
    # Colour zone selection
    # ------------------------------------------------------------------ #
    def _zone_color(self, temp: float) -> QColor:
        if temp < config.COOLANT_COLD_MAX_C:
            return self.color(config.COLOR_COLD)          # blue  (< 70 C)
        if temp < _COOLANT_ZONE_HOT_C:
            return self.color(_COOLANT_GREEN)              # green (70-90 C)
        return self.color(config.COLOR_CRITICAL)           # red   (>= 90 C)

    # ------------------------------------------------------------------ #
    # Rendering
    # ------------------------------------------------------------------ #
    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        w, h = float(self.width()), float(self.height())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        # Elevated card behind everything.
        self.draw_card(painter)

        # --- Vertical layout bands ---------------------------------------
        title_h = h * 0.11
        readout_h = h * 0.19
        bar_top = title_h + h * 0.02
        bar_bottom = h - readout_h
        bar_h = max(1.0, bar_bottom - bar_top)
        bar_w = min(w * 0.26, 52.0)
        bar_x = w * 0.20
        bar_rect = QRectF(bar_x, bar_top, bar_w, bar_h)
        radius = bar_w * 0.5

        # --- Title -------------------------------------------------------
        painter.setPen(self.color(config.COLOR_TEXT_DIM))
        painter.setFont(self.scaled_font(h * 0.05, spacing=32))
        painter.drawText(QRectF(0, title_h * 0.2, w, title_h), Qt.AlignHCenter | Qt.AlignTop, "COOLANT")

        # --- Track (unfilled channel) ------------------------------------
        track_path = QPainterPath()
        track_path.addRoundedRect(bar_rect, radius, radius)
        painter.fillPath(track_path, self.color(config.COLOR_TRACK))
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(self.color(config.COLOR_CARD_BORDER), 1.0))
        painter.drawRoundedRect(bar_rect, radius, radius)

        # --- Fill (neon liquid column) -----------------------------------
        if self._has_data:
            temp = self.value
            zone = self._zone_color(temp)
            dim = self.is_flashing() and not self._flash_on
            if dim:
                zone = self.color(config.COLOR_CRITICAL, alpha=70)

            fill_h = bar_h * self.fraction
            fill_top = bar_bottom - fill_h
            fill_rect = QRectF(bar_x, fill_top, bar_w, fill_h)

            painter.save()
            painter.setClipPath(track_path)

            # Soft glow above the liquid surface.
            if not dim:
                glow = QLinearGradient(0, fill_top - bar_w, 0, fill_top + bar_w)
                gcol = QColor(zone)
                gcol.setAlpha(120)
                glow.setColorAt(0.0, self.color(config.COLOR_TRACK, alpha=0))
                glow.setColorAt(1.0, gcol)
                painter.fillRect(QRectF(bar_x, fill_top - bar_w, bar_w, bar_w * 2), glow)

            # Column body gradient.
            body = QLinearGradient(0, fill_rect.top(), 0, fill_rect.bottom())
            body.setColorAt(0.0, zone.lighter(150))
            body.setColorAt(1.0, zone)
            painter.fillRect(fill_rect, body)

            # Bright surface cap line.
            if not dim:
                painter.setPen(QPen(zone.lighter(170), 2.2))
                painter.drawLine(int(bar_x + 2), int(fill_top),
                                 int(bar_x + bar_w - 2), int(fill_top))
            painter.restore()

        # --- Red-line marker at the 98 C overheat threshold --------------
        crit_frac = (config.COOLANT_CRITICAL_C - self._min) / (self._max - self._min)
        crit_y = bar_bottom - bar_h * crit_frac
        painter.setPen(QPen(self.color(config.COLOR_CRITICAL, alpha=200), 2, Qt.DotLine))
        painter.drawLine(int(bar_x - 5), int(crit_y), int(bar_x + bar_w + 5), int(crit_y))

        # --- Tick marks + labels (every 20 C) ----------------------------
        painter.setFont(self.scaled_font(h * 0.036, bold=False))
        label_x = bar_x + bar_w + w * 0.08
        tick = int(config.COOLANT_MIN_C)
        while tick <= int(config.COOLANT_MAX_C):
            frac = (tick - self._min) / (self._max - self._min)
            y = bar_bottom - bar_h * frac
            painter.setPen(self.color(config.COLOR_TEXT_FAINT))
            painter.drawLine(int(bar_x + bar_w + 3), int(y), int(bar_x + bar_w + 9), int(y))
            painter.setPen(self.color(config.COLOR_TEXT_DIM))
            painter.drawText(QRectF(label_x, y - 10, w - label_x, 20),
                             Qt.AlignVCenter | Qt.AlignLeft, str(tick))
            tick += 20

        # --- Numeric readout ---------------------------------------------
        readout_rect = QRectF(0, bar_bottom + h * 0.005, w, readout_h)
        if self._has_data:
            temp = self.value
            text_color = self._zone_color(temp)
            hot = self.is_flashing()
            if hot and not self._flash_on:
                text_color = self.color(config.COLOR_CRITICAL, alpha=70)
            painter.setFont(self.scaled_font(h * 0.15))
            self.draw_glow_text(painter, readout_rect, Qt.AlignCenter,
                                f"{temp:.0f}\u00b0", text_color, glow=hot and self._flash_on)
            # small "C" unit
            painter.setPen(self.color(config.COLOR_TEXT_DIM))
            painter.setFont(self.scaled_font(h * 0.06, spacing=10))
            painter.drawText(readout_rect, Qt.AlignHCenter | Qt.AlignBottom, "\u00b0CELSIUS")
        else:
            painter.setPen(self.color(config.COLOR_TEXT_DIM))
            painter.setFont(self.scaled_font(h * 0.15))
            painter.drawText(readout_rect, Qt.AlignCenter, "--\u00b0")

        painter.end()
