"""
mini_readout.py
===============

Compact numeric readout for the Track dashboard.

Where the general dashboard uses full-height gauges to communicate a value's
range and zone visually (a filled column, a swept arc), the track dashboard
needs its non-tacho readouts to sit in a thin peripheral strip so the tacho
can dominate. This widget provides that: a small elevated card with a dim
label, a big value (colour-coded via a supplied zone function), and an
optional unit suffix.

Colour is not baked in - callers pass a ``zone_fn`` callback that returns
the colour for a given value and whether that value is "critical" (which
drives the shared blink phase from :class:`BaseGauge`). This keeps the widget
domain-agnostic and reusable for coolant, battery voltage, speed, or anything
else added later.
"""

from __future__ import annotations

from typing import Callable

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QPainter

from .. import config
from .base_gauge import BaseGauge


# Return type of the zone callback: (hex colour string, is_critical flag).
ZoneFn = Callable[[float], "tuple[str, bool]"]


class MiniReadout(BaseGauge):
    """Compact label + numeric readout on an elevated card.

    Parameters
    ----------
    label:
        Small caption drawn above the number (e.g. ``"COOLANT"``).
    unit:
        Suffix appended to the number (e.g. ``"\u00b0C"``, ``"V"``, ``"MPH"``).
        Pass an empty string for a bare number.
    value_fmt:
        ``str.format``-style format for the number itself. Defaults to
        ``"{:.0f}"`` (integer look). Use ``"{:.1f}"`` for one decimal.
    zone_fn:
        Callback ``(value: float) -> (hex_color: str, is_critical: bool)``.
        Called every frame to decide the number's colour and whether the
        widget should flash. If ``None`` the number stays in the neutral
        accent colour and never flashes.
    minimum, maximum:
        Range used by :class:`BaseGauge` for easing / clamping. These bounds
        are not drawn; they only prevent absurd values from breaking the
        smoothing.
    """

    def __init__(
        self,
        label: str,
        unit: str = "",
        value_fmt: str = "{:.0f}",
        zone_fn: ZoneFn | None = None,
        minimum: float = -1e6,
        maximum: float = 1e6,
        parent=None,
    ) -> None:
        super().__init__(minimum, maximum, parent)
        self._label = label
        self._unit = unit
        self._fmt = value_fmt
        self._zone_fn = zone_fn
        # Cached flag so is_flashing() can be answered without re-invoking the
        # zone function (it may allocate a QColor each call).
        self._critical: bool = False
        # Compact card: shrink the minimum so the layout can pack multiple in
        # a row on an 800x480 panel.
        self.setMinimumSize(120, 76)

    # ------------------------------------------------------------------ #
    # BaseGauge hook - drives the shared blink phase
    # ------------------------------------------------------------------ #
    def is_flashing(self) -> bool:
        return self._has_data and self._critical

    # ------------------------------------------------------------------ #
    # Rendering
    # ------------------------------------------------------------------ #
    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        w, h = float(self.width()), float(self.height())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        # Elevated card with the same visual language as the main gauges,
        # but slightly reduced radius for a snugger look in the peripheral
        # strip.
        self.draw_card(painter, margin=4.0, radius=12.0)

        # --- Label (dim caption at the top) ------------------------------
        label_h = h * 0.32
        painter.setPen(self.color(config.COLOR_TEXT_DIM))
        painter.setFont(self.scaled_font(max(10, h * 0.19), spacing=28))
        painter.drawText(
            QRectF(0, label_h * 0.10, w, label_h),
            Qt.AlignHCenter | Qt.AlignTop,
            self._label,
        )

        # --- Value + unit ------------------------------------------------
        value_rect = QRectF(0, label_h, w, h - label_h - 4)

        if not self._has_data:
            painter.setPen(self.color(config.COLOR_TEXT_DIM))
            painter.setFont(self.scaled_font(h * 0.42))
            painter.drawText(value_rect, Qt.AlignCenter, "--")
            painter.end()
            return

        # Ask the zone function what colour + critical state we're in.
        if self._zone_fn is not None:
            hex_color, self._critical = self._zone_fn(self.value)
        else:
            hex_color, self._critical = config.COLOR_ACCENT, False

        color = self.color(hex_color)
        # Dim the value on the "off" half of the blink phase when critical.
        if self._critical and not self._flash_on:
            color = self.color(hex_color, alpha=90)

        text = self._fmt.format(self.value) + self._unit
        painter.setFont(self.scaled_font(h * 0.42))
        self.draw_glow_text(
            painter,
            value_rect,
            Qt.AlignCenter,
            text,
            color,
            glow=self._critical and self._flash_on,
        )
        painter.end()
