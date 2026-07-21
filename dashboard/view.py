"""
view.py
=======

The **View** layer.

The Pi runs one of two layouts, selected by ``main.py --layout``:

General (default, road use) - 800 x 480::

    +-----------------------------------------------------------+
    | [ WARNING: ENGINE OVERHEATING ]  (flashing overlay banner) |
    | +---------+  +---------------------+  +-----------------+  |
    | | COOLANT |  |     TACHOMETER      |  |      SPEED      |  |
    | | (bar)   |  |  (dominant, arc +   |  |   (digital MPH) |  |
    | |         |  |   shift-lights)     |  |                 |  |
    | +---------+  +---------------------+  +-----------------+  |
    | * OBD CONNECTED                         <last message>     |
    +-----------------------------------------------------------+

Track (``--layout track``, motorsport use) - 800 x 480::

    +---------------------------------------------------------------+
    | +---------+  +---------+  +---------+                          |
    | | COOLANT |  | BATTERY |  |  SPEED  |    <- compact readouts   |
    | +---------+  +---------+  +---------+                          |
    | +-----------------------------------------------------------+  |
    | |   oooooooooooo    (shift lights - built into tacho)       |  |
    | |                                                           |  |
    | |            BIG TACHO takes the bulk of the screen         |  |
    | |                                                           |  |
    | +-----------------------------------------------------------+  |
    | | THROTTLE  [============              ]   45%              |  |
    | +-----------------------------------------------------------+  |
    | * OBD CONNECTED                          <last message>       |
    +---------------------------------------------------------------+

Both windows share:

* Kiosk mode setup (frameless, hidden cursor) unless ``--windowed``.
* A tinted status pill + a right-aligned diagnostic message strip.
* The floating :class:`WarningOverlay` used when coolant is critical.
* Radial-vignette background painting.
* ``Esc`` / ``Q`` to quit.

The shared bits live on :class:`_BaseDashboardWindow`; each layout is a small
subclass that composes its own gauges and stretches. Adding a third layout
later means writing one more subclass, nothing more.
"""

from __future__ import annotations

from PyQt5.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSlot
from PyQt5.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRadialGradient,
)
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import config
from .telemetry import ConnectionState
from .widgets import (
    CoolantGauge,
    MiniReadout,
    RPMGauge,
    Speedometer,
    ThrottleBar,
)


# ===========================================================================
#  Overheating warning overlay
# ===========================================================================
class WarningOverlay(QWidget):
    """A prominent, flashing banner shown across the dashboard when the engine
    coolant exceeds the critical threshold.

    Implemented as a free (non-layout) child so it floats *above* the gauges;
    it is positioned in :meth:`_BaseDashboardWindow.resizeEvent`.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # Click-through-ish: purely decorative, never steals focus/mouse.
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._on = True
        self._active = False

        self._flash_timer = QTimer(self)
        self._flash_timer.timeout.connect(self._blink)
        self.hide()

    def set_active(self, active: bool) -> None:
        """Show/flash the banner (``True``) or hide it (``False``)."""
        if active == self._active:
            return
        self._active = active
        if active:
            self._on = True
            self.show()
            self.raise_()
            self._flash_timer.start(config.FLASH_INTERVAL_MS)
        else:
            self._flash_timer.stop()
            self.hide()

    def _blink(self) -> None:
        self._on = not self._on
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        on = self._on
        base = QColor(config.COLOR_CRITICAL) if on else QColor(config.COLOR_CRITICAL).darker(175)
        rect = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        radius = rect.height() * 0.28

        # Soft red halo so the banner reads as "glowing".
        halo = QColor(config.COLOR_CRITICAL)
        halo.setAlpha(80 if on else 30)
        painter.setPen(Qt.NoPen)
        painter.setBrush(halo)
        painter.drawRoundedRect(rect.adjusted(-3, -3, 3, 3), radius + 3, radius + 3)

        # Panel body with a vertical red gradient.
        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0.0, base.lighter(122))
        grad.setColorAt(1.0, base.darker(120))
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.fillPath(path, grad)

        # Bright rim.
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 220 if on else 110), 2))
        painter.drawRoundedRect(rect, radius, radius)

        # Warning triangle (drawn, not glyph, so it never depends on a font).
        s = rect.height() * 0.5
        tcx = rect.left() + rect.height() * 0.62
        tcy = rect.center().y()
        tri = QPolygonF([
            QPointF(tcx, tcy - s * 0.55),
            QPointF(tcx - s * 0.58, tcy + s * 0.5),
            QPointF(tcx + s * 0.58, tcy + s * 0.5),
        ])
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 235 if on else 120))
        painter.drawPolygon(tri)
        painter.setPen(QPen(base.darker(160), max(2.0, s * 0.09)))
        painter.drawLine(int(tcx), int(tcy - s * 0.18), int(tcx), int(tcy + s * 0.12))
        painter.drawPoint(int(tcx), int(tcy + s * 0.30))

        # Warning text with wide tracking, centred in the banner.
        font = self.font()
        font.setBold(True)
        font.setPixelSize(max(12, int(self.height() * 0.34)))
        font.setLetterSpacing(font.PercentageSpacing, 108.0)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff") if on else QColor(255, 255, 255, 190))
        painter.drawText(rect, Qt.AlignCenter, config.OVERHEAT_WARNING_TEXT)
        painter.end()


# ===========================================================================
#  Shared base window - plumbing common to every layout
# ===========================================================================
class _BaseDashboardWindow(QWidget):
    """Kiosk-mode window with a status pill, background vignette, warning
    overlay, and Esc/Q-to-quit. Layout subclasses build their own gauge grid
    inside :meth:`_install_body`.
    """

    def __init__(self, windowed: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Lotus Elise Dashboard")

        # Kiosk mode (the default, for the Pi): frameless with a hidden cursor;
        # main.py then calls showFullScreen(). In --windowed dev/preview mode we
        # keep the normal title bar and mouse cursor so the window is easy to
        # move and close on a desktop.
        if not windowed:
            self.setWindowFlag(Qt.FramelessWindowHint, True)
            self.setCursor(Qt.BlankCursor)
        self.resize(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
        self.setMinimumSize(640, 400)

        # --- Status-line labels -----------------------------------------
        self._status_label = QLabel("CONNECTING\u2026")
        self._status_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self._message_label = QLabel("")
        self._message_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._message_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        for lbl in (self._status_label, self._message_label):
            f = lbl.font()
            f.setPixelSize(13)
            f.setBold(True)
            lbl.setFont(f)

        # --- Overheat overlay (floats above the gauges) -----------------
        self._warning = WarningOverlay(self)

        # Prime the status line with what we know initially.
        self.set_connection_state(ConnectionState.CONNECTING)

    # ------------------------------------------------------------------ #
    # Layout helper for subclasses
    # ------------------------------------------------------------------ #
    def _build_status_row(self) -> QHBoxLayout:
        """Horizontal layout containing the status pill + message label.

        Subclasses call this at the bottom of their outer VBox so every layout
        gets the same status strip in the same place.
        """
        status = QHBoxLayout()
        status.setContentsMargins(4, 0, 4, 0)
        status.addWidget(self._status_label)
        status.addWidget(self._message_label)
        return status

    # ------------------------------------------------------------------ #
    # Slots wired to the Controller
    # ------------------------------------------------------------------ #
    def set_overheating(self, active: bool) -> None:
        """Show/hide the flashing overheating banner."""
        self._warning.set_active(active)

    def set_connection_state(self, state: ConnectionState) -> None:
        """Update the coloured connection indicator (a tinted pill)."""
        text, hex_color = {
            ConnectionState.CONNECTING: ("CONNECTING\u2026", config.COLOR_WARN),
            ConnectionState.CONNECTED: ("OBD CONNECTED", config.COLOR_OK),
            ConnectionState.RECONNECTING: ("RECONNECTING\u2026", config.COLOR_WARN),
            ConnectionState.MOCK: ("MOCK MODE \u2014 SIMULATED DATA", config.COLOR_MOCK),
        }.get(state, ("UNKNOWN", config.COLOR_TEXT_DIM))
        c = QColor(hex_color)
        rgb = f"{c.red()},{c.green()},{c.blue()}"
        # A filled dot glyph + label inside a softly-tinted rounded pill.
        self._status_label.setText(f"\u25cf  {text}")
        self._status_label.setStyleSheet(
            "QLabel {"
            f"  color: {hex_color};"
            f"  background-color: rgba({rgb},36);"
            f"  border: 1px solid rgba({rgb},110);"
            "   border-radius: 10px;"
            "   padding: 3px 12px;"
            "}"
        )

    def set_message(self, text: str) -> None:
        """Show the latest diagnostic message (dimmed, right-aligned)."""
        self._message_label.setText(text)
        self._message_label.setStyleSheet(f"color: {config.COLOR_TEXT_DIM};")

    # ------------------------------------------------------------------ #
    # Painting / geometry / input (shared)
    # ------------------------------------------------------------------ #
    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        """Radial vignette (lighter centre, darker edges) so the gauge cards
        read as elevated on the panel."""
        painter = QPainter(self)
        w, h = self.width(), self.height()
        grad = QRadialGradient(w * 0.5, h * 0.42, max(w, h) * 0.75)
        grad.setColorAt(0.0, QColor(config.COLOR_BG_TOP))
        grad.setColorAt(1.0, QColor(config.COLOR_BG_EDGE))
        painter.fillRect(self.rect(), grad)
        painter.end()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Keep the floating warning banner centred over the upper dial area."""
        super().resizeEvent(event)
        if not hasattr(self, "_warning"):
            return
        w, h = self.width(), self.height()
        banner_w = int(w * 0.66)
        banner_h = int(h * 0.16)
        x = (w - banner_w) // 2
        y = int(h * 0.28)
        self._warning.setGeometry(x, y, banner_w, banner_h)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Allow quitting a frameless / cursor-less kiosk window."""
        if event.key() in (Qt.Key_Escape, Qt.Key_Q):
            self.close()
        else:
            super().keyPressEvent(event)


# ===========================================================================
#  General layout (default, unchanged from the original single-layout build)
# ===========================================================================
class DashboardWindow(_BaseDashboardWindow):
    """The road-friendly three-gauge layout: coolant bar / big tacho / MPH.

    Behaviourally identical to the pre-Track single-window build; the shared
    plumbing has just been lifted into :class:`_BaseDashboardWindow`.
    """

    def __init__(self, windowed: bool = False, parent=None) -> None:
        super().__init__(windowed=windowed, parent=parent)

        # --- Gauges -----------------------------------------------------
        self.coolant_gauge = CoolantGauge()
        self.rpm_gauge = RPMGauge()
        self.speedometer = Speedometer()

        # --- Layout -----------------------------------------------------
        gauges = QHBoxLayout()
        gauges.setSpacing(10)
        gauges.setContentsMargins(0, 0, 0, 0)
        gauges.addWidget(self.coolant_gauge, 1)   # left  (narrow)
        gauges.addWidget(self.rpm_gauge, 2)        # centre (dominant, 2x)
        gauges.addWidget(self.speedometer, 1)      # right (narrow)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 4)
        outer.setSpacing(4)
        outer.addLayout(gauges, 1)
        outer.addLayout(self._build_status_row(), 0)


# ===========================================================================
#  Track layout - dominant tacho, peripheral compact readouts, throttle bar
# ===========================================================================
class TrackDashboardWindow(_BaseDashboardWindow):
    """Motorsport-oriented layout: tacho + shift-lights dominate; the
    peripherals shrink to compact numeric readouts.

    Notes on the overheat overlay
    -----------------------------
    The Track layout uses stricter coolant zones than the general dashboard
    (see ``config.TRACK_COOLANT_*``). Rather than have the Controller emit a
    layout-specific ``overheat_changed``, this window bypasses that signal:
    the caller wires ``controller.coolant_changed`` to
    :meth:`on_coolant_changed` here, and this class both forwards the value
    into the readout *and* transitions the overheat overlay using its own
    threshold. The general dashboard continues to use ``overheat_changed``
    unchanged.
    """

    def __init__(self, windowed: bool = False, parent=None) -> None:
        super().__init__(windowed=windowed, parent=parent)

        # --- Widgets ----------------------------------------------------
        # 2ZZ VVTL-i zones: blue below the cam switch (mild lobe, out of the
        # power band), green above it (on-cam, where the engine sings),
        # flashing red only right at the 8500 redline.
        self.rpm_gauge = RPMGauge(
            zones=[
                (config.TRACK_RPM_CAM_SWITCH, config.COLOR_COLD),
                (config.RPM_MAX,              config.COLOR_OPTIMAL),
            ],
            redline_rpm=config.RPM_MAX,
        )

        self.coolant_readout = MiniReadout(
            label="COOLANT",
            unit="\u00b0C",
            value_fmt="{:.0f}",
            zone_fn=self._coolant_zone,
            minimum=config.COOLANT_MIN_C,
            maximum=config.COOLANT_MAX_C,
        )
        self.battery_readout = MiniReadout(
            label="BATTERY",
            unit=" V",
            value_fmt="{:.1f}",
            zone_fn=self._battery_zone,
            minimum=9.0,
            maximum=16.0,
        )
        self.speed_readout = MiniReadout(
            label="SPEED",
            unit=" MPH",
            value_fmt="{:.0f}",
            zone_fn=None,               # neutral colour; no zones for speed
            minimum=0.0,
            maximum=config.SPEED_MAX_MPH,
        )
        self.throttle_bar = ThrottleBar()

        # --- Top strip: coolant | battery | speed -----------------------
        top = QHBoxLayout()
        top.setSpacing(8)
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(self.coolant_readout, 1)
        top.addWidget(self.battery_readout, 1)
        top.addWidget(self.speed_readout, 1)

        # --- Outer VBox: top strip / tacho / throttle bar / status ------
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 4)
        outer.setSpacing(6)
        outer.addLayout(top, 0)                       # natural height (~72 px)
        outer.addWidget(self.rpm_gauge, 1)            # dominant, stretches
        outer.addWidget(self.throttle_bar, 0)         # natural height (~48 px)
        outer.addLayout(self._build_status_row(), 0)

        # Track its own overheat state so we only toggle the overlay on flips.
        self._overheating: bool = False

    # ------------------------------------------------------------------ #
    # Coolant-aware slot that also drives the overheat overlay
    # ------------------------------------------------------------------ #
    @pyqtSlot(object)
    def on_coolant_changed(self, temp) -> None:
        """Forward temperature into the readout *and* update overheat state.

        ``temp`` follows the same ``float | None`` convention as every other
        Controller signal payload: ``None`` means "no data" and shouldn't
        trigger the warning.
        """
        # 1. Feed the mini readout so the number/colour updates.
        self.coolant_readout.set_value(temp)

        # 2. Drive the overheat overlay against the Track threshold.
        is_over = temp is not None and temp >= config.TRACK_COOLANT_CRITICAL_C
        if is_over != self._overheating:
            self._overheating = is_over
            self.set_overheating(is_over)

    # ------------------------------------------------------------------ #
    # Zone functions used by the MiniReadouts
    # ------------------------------------------------------------------ #
    @staticmethod
    def _coolant_zone(temp: float) -> tuple[str, bool]:
        """Track thresholds: <84 blue, 84-99 green, 100-104 amber, 105+ red."""
        if temp < config.TRACK_COOLANT_COLD_MAX_C:
            return config.COLOR_COLD, False
        if temp <= config.TRACK_COOLANT_OPTIMAL_MAX_C:
            return config.COLOR_OPTIMAL, False
        if temp < config.TRACK_COOLANT_CRITICAL_C:
            return config.COLOR_AMBER, False
        return config.COLOR_CRITICAL, True

    @staticmethod
    def _battery_zone(volts: float) -> tuple[str, bool]:
        """< 12.5 or > 15.5 = red flashing; edges of the band = amber; otherwise green."""
        if volts < config.BATTERY_LOW_V or volts > config.BATTERY_HIGH_V:
            return config.COLOR_CRITICAL, True
        if (volts < config.BATTERY_OPTIMAL_MIN_V
                or volts > config.BATTERY_OPTIMAL_MAX_V):
            return config.COLOR_AMBER, False
        return config.COLOR_OPTIMAL, False
