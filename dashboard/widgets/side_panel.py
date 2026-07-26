"""
side_panel.py
=============

Unified custom-painted side panel for the Track dashboard.

Instead of separate card-backed MiniReadout widgets, this paints all readouts
on a single transparent canvas — floating text with subtle groove dividers,
matching the MotecTachometer's instrument aesthetic.

Each panel holds 3 readout slots (top, middle, bottom). The bottom slot on the
right panel can optionally include an inline throttle progress bar.
"""

from __future__ import annotations

from typing import Callable

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

# Zone callback: (value) -> (hex_colour, is_critical)
ZoneFn = Callable[[float], "tuple[str, bool]"]

# Fraction of the remaining distance to close each frame (~60 Hz).
_SMOOTHING = 0.28


def _make_font(size: int, bold: bool = True, spacing: float = 0.0) -> QFont:
    f = QFont("DejaVu Sans", size, QFont.Bold if bold else QFont.Normal)
    f.setPixelSize(max(6, int(size)))
    if spacing > 0:
        f.setLetterSpacing(QFont.PercentageSpacing, 100.0 + spacing)
    return f


class _ReadoutSlot:
    """Internal state for a single readout row."""

    def __init__(
        self,
        label: str,
        unit: str,
        value_fmt: str,
        zone_fn: ZoneFn | None,
        minimum: float,
        maximum: float,
        show_bar: bool = False,
    ) -> None:
        self.label = label
        self.unit = unit
        self.fmt = value_fmt
        self.zone_fn = zone_fn
        self.minimum = minimum
        self.maximum = maximum
        self.show_bar = show_bar

        self.value: float = minimum
        self.target: float = minimum
        self.has_data: bool = False
        self.critical: bool = False
        self.hex_color: str = config.COLOR_ACCENT

    def set_target(self, value: float | None) -> None:
        if value is None:
            self.has_data = False
            return
        self.has_data = True
        self.target = max(self.minimum, min(self.maximum, float(value)))

    def ease(self) -> bool:
        """Advance value toward target. Return True if it moved."""
        diff = self.target - self.value
        epsilon = (self.maximum - self.minimum) * 0.0005
        if abs(diff) <= epsilon:
            if self.value != self.target:
                self.value = self.target
                return True
            return False
        self.value += diff * _SMOOTHING
        return True

    @property
    def fraction(self) -> float:
        span = self.maximum - self.minimum
        if span <= 0:
            return 0.0
        return (self.value - self.minimum) / span


class SidePanel(QWidget):
    """Unified, card-free side panel for the Track dashboard.

    Paints 3 readout slots as floating text on a transparent background,
    separated by subtle groove dividers matching the MotecTachometer pod.

    Parameters
    ----------
    slots:
        List of dicts defining each readout. Each dict has keys:
        label, unit, value_fmt, zone_fn, minimum, maximum, show_bar (optional)
    """

    def __init__(
        self,
        slots: list[dict],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(140, 200)

        self._slots: list[_ReadoutSlot] = []
        for s in slots:
            self._slots.append(
                _ReadoutSlot(
                    label=s["label"],
                    unit=s.get("unit", ""),
                    value_fmt=s.get("value_fmt", "{:.0f}"),
                    zone_fn=s.get("zone_fn"),
                    minimum=s.get("minimum", 0.0),
                    maximum=s.get("maximum", 100.0),
                    show_bar=s.get("show_bar", False),
                )
            )

        # Flash phase for critical blink
        self._flash_on: bool = True

        # 60 FPS animation timer
        self._anim_timer = QTimer(self)
        self._anim_timer.setTimerType(0)  # Qt.PreciseTimer
        self._anim_timer.timeout.connect(self._on_frame)
        self._anim_timer.start(config.FRAME_INTERVAL_MS)

        # Slower flash timer
        self._flash_timer = QTimer(self)
        self._flash_timer.timeout.connect(self._on_flash)
        self._flash_timer.start(config.FLASH_INTERVAL_MS)

    # ------------------------------------------------------------------ #
    # Public API — slot setters for signal wiring
    # ------------------------------------------------------------------ #
    def slot_setter(self, index: int):
        """Return a callable suitable for pyqtSignal.connect() that sets
        the target value on the given slot index."""

        @pyqtSlot(object)
        def _setter(value) -> None:
            if 0 <= index < len(self._slots):
                self._slots[index].set_target(value)

        return _setter

    # ------------------------------------------------------------------ #
    # Animation
    # ------------------------------------------------------------------ #
    def _on_frame(self) -> None:
        moved = False
        for s in self._slots:
            if s.ease():
                moved = True
        if moved:
            self.update()

    def _on_flash(self) -> None:
        any_critical = any(s.has_data and s.critical for s in self._slots)
        if any_critical:
            self._flash_on = not self._flash_on
            self.update()
        elif not self._flash_on:
            self._flash_on = True
            self.update()

    # ------------------------------------------------------------------ #
    # Rendering
    # ------------------------------------------------------------------ #
    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        w, h = float(self.width()), float(self.height())
        n = len(self._slots)
        if n == 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        slot_h = h / n
        margin_x = 8.0

        for i, slot in enumerate(self._slots):
            y_top = i * slot_h
            slot_rect = QRectF(margin_x, y_top, w - 2 * margin_x, slot_h)

            self._draw_slot(painter, slot, slot_rect)

            # Groove divider between slots (not after last)
            if i < n - 1:
                div_y = y_top + slot_h
                # Dark groove line (shadow)
                painter.setPen(QPen(QColor("#080606"), 1.5))
                painter.drawLine(
                    int(margin_x + 6), int(div_y),
                    int(w - margin_x - 6), int(div_y),
                )
                # Light highlight line (bevel)
                painter.setPen(QPen(QColor("#2a1a1e"), 1.0))
                painter.drawLine(
                    int(margin_x + 6), int(div_y + 1),
                    int(w - margin_x - 6), int(div_y + 1),
                )

        painter.end()

    def _draw_slot(
        self, painter: QPainter, slot: _ReadoutSlot, rect: QRectF
    ) -> None:
        """Draw a single readout slot: dim label + large colour-coded value."""
        cx = rect.center().x()

        # --- Label ---
        label_h = rect.height() * 0.30
        label_rect = QRectF(rect.left(), rect.top() + 4, rect.width(), label_h)
        painter.setFont(_make_font(11, bold=True, spacing=30))
        painter.setPen(QColor(config.COLOR_TEXT_DIM))
        painter.drawText(label_rect, Qt.AlignHCenter | Qt.AlignBottom, slot.label)

        # --- Value ---
        if not slot.has_data:
            val_rect = QRectF(
                rect.left(), rect.top() + label_h,
                rect.width(), rect.height() - label_h - 4,
            )
            painter.setFont(_make_font(max(22, int(rect.height() * 0.38)), bold=True))
            painter.setPen(QColor(config.COLOR_TEXT_DIM))
            painter.drawText(val_rect, Qt.AlignHCenter | Qt.AlignTop, "--")
            return

        # Get zone colour
        if slot.zone_fn is not None:
            slot.hex_color, slot.critical = slot.zone_fn(slot.value)
        else:
            slot.hex_color, slot.critical = config.COLOR_TEXT, False

        color = QColor(slot.hex_color)
        if slot.critical and not self._flash_on:
            color.setAlpha(90)

        text = slot.fmt.format(slot.value) + slot.unit
        font_size = max(22, int(rect.height() * 0.38))

        # Value area
        val_top = rect.top() + label_h - 2
        bar_reserve = 20.0 if slot.show_bar else 4.0
        val_rect = QRectF(
            rect.left(), val_top,
            rect.width(), rect.height() - label_h - bar_reserve,
        )

        # Drop shadow
        painter.setFont(_make_font(font_size, bold=True))
        shadow_color = QColor(0, 0, 0, 200)
        painter.setPen(shadow_color)
        painter.drawText(val_rect.translated(1.5, 1.5), Qt.AlignHCenter | Qt.AlignTop, text)

        # Glow for critical flashing state
        if slot.critical and self._flash_on:
            glow = QColor(slot.hex_color)
            glow.setAlpha(50)
            for dx, dy in ((-1.5, 0), (1.5, 0), (0, -1.5), (0, 1.5)):
                painter.setPen(glow)
                painter.drawText(
                    val_rect.translated(dx, dy),
                    Qt.AlignHCenter | Qt.AlignTop, text,
                )

        # Main text
        painter.setPen(color)
        painter.drawText(val_rect, Qt.AlignHCenter | Qt.AlignTop, text)

        # --- Throttle bar (optional) ---
        if slot.show_bar and slot.has_data:
            self._draw_throttle_bar(painter, rect, slot)

    def _draw_throttle_bar(
        self, painter: QPainter, rect: QRectF, slot: _ReadoutSlot
    ) -> None:
        """Draw a minimal horizontal progress bar at the bottom of a slot."""
        bar_margin = 10.0
        bar_h = 6.0
        bar_w = rect.width() - 2 * bar_margin
        bar_top = rect.bottom() - bar_h - 6.0
        bar_rect = QRectF(rect.left() + bar_margin, bar_top, bar_w, bar_h)
        radius = bar_h * 0.5

        # Unfilled track
        track_path = QPainterPath()
        track_path.addRoundedRect(bar_rect, radius, radius)
        painter.fillPath(track_path, QColor(config.COLOR_TRACK))
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#1a1214"), 1.0))
        painter.drawRoundedRect(bar_rect, radius, radius)

        # Fill
        if slot.value > 0.0:
            fill_w = bar_w * slot.fraction
            fill_rect = QRectF(rect.left() + bar_margin, bar_top, fill_w, bar_h)
            painter.save()
            painter.setClipPath(track_path)
            grad = QLinearGradient(
                rect.left() + bar_margin, 0,
                rect.left() + bar_margin + fill_w, 0,
            )
            base = QColor(config.COLOR_ACCENT)
            grad.setColorAt(0.0, base.darker(120))
            grad.setColorAt(1.0, base.lighter(130))
            painter.fillRect(fill_rect, grad)
            painter.restore()
