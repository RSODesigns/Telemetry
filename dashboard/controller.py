"""
controller.py
=============

The **Controller** layer: the signal router that sits between the Model (the
OBD worker thread) and the View (the gauges).

Responsibilities
----------------
* Own the :class:`~dashboard.model.OBDModel` thread lifecycle (start/stop).
* On a GUI-thread timer, pull the newest :class:`~dashboard.telemetry.Telemetry`
  snapshot the worker has published and fan it out into small, purpose-built
  ``pyqtSignal`` s the View can wire straight onto individual gauges.
* Perform the unit conversion the spec calls for - OBD reports road speed in
  km/h, the speedometer shows MPH - so the View stays purely presentational.
* Derive higher-level UI facts (e.g. "the engine is overheating") once, here,
  rather than duplicating the threshold logic in the window.

Why a timer instead of reacting to worker signals?
--------------------------------------------------
Every signal this class emits is emitted from the GUI thread (the timer fires
there), which is inherently thread-safe - there is no cross-thread signal
marshalling at all. The worker just parks its latest reading behind a lock and
we sample it here at the UI rate. This is the classic, crash-proof pattern for
high-frequency telemetry and keeps the render path completely decoupled from
serial I/O jitter.
"""

from __future__ import annotations

from PyQt5.QtCore import QObject, QTimer, Qt, pyqtSignal

from . import config
from .model import OBDModel
from .telemetry import ConnectionState


class DashboardController(QObject):
    """Routes telemetry from the data thread to the view widgets.

    All value signals carry ``object`` (float or ``None``) so that a missing
    PID propagates as ``None`` and the gauges can show a "no data" state rather
    than a misleading zero.
    """

    rpm_changed = pyqtSignal(object)          # float | None  (RPM)
    coolant_changed = pyqtSignal(object)      # float | None  (deg C)
    speed_changed = pyqtSignal(object)        # float | None  (MPH, converted)
    throttle_changed = pyqtSignal(object)     # float | None  (%, 0-100)
    battery_changed = pyqtSignal(object)      # float | None  (volts)
    intake_temp_changed = pyqtSignal(object)  # float | None  (deg C)
    relative_throttle_changed = pyqtSignal(object) # float | None  (%, 0-100)
    fuel_status_changed = pyqtSignal(object)  # tuple[str, str] | None
    fuel_level_changed = pyqtSignal(object)   # float | None (%, 0-100)
    overheat_changed = pyqtSignal(bool)       # True while coolant is critical
    connection_changed = pyqtSignal(object)   # ConnectionState
    message = pyqtSignal(str)                 # diagnostics passthrough

    def __init__(self, force_mock: bool | None = None, parent=None) -> None:
        super().__init__(parent)
        self._model = OBDModel(force_mock=force_mock)
        self._overheating = False               # cached: only emit on change
        self._last_state: ConnectionState | None = None

        # GUI-thread sampling timer. Everything it does runs on the GUI thread.
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self._poll)

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def start(self) -> None:
        """Start the background data thread and begin sampling it."""
        self._model.start()
        self._timer.start(config.UI_POLL_INTERVAL_MS)

    def stop(self) -> None:
        """Stop sampling and join the background data thread (app shutdown)."""
        self._timer.stop()
        self._model.stop()

    @property
    def connection_state(self) -> ConnectionState:
        """Most recent connection state (read from the worker's snapshot)."""
        return self._model.snapshot()[1]

    # ------------------------------------------------------------------ #
    # GUI-thread sampling: Model -> View routing
    # ------------------------------------------------------------------ #
    def _poll(self) -> None:
        """Sample the worker's latest snapshot and emit per-gauge signals."""
        # 1) Forward any diagnostics the worker queued.
        for msg in self._model.drain_messages():
            self.message.emit(msg)

        telemetry, state = self._model.snapshot()

        # 2) Connection state - emit only when it changes.
        if state is not self._last_state:
            self._last_state = state
            self.connection_changed.emit(state)

        # 3) Raw pass-through values.
        self.rpm_changed.emit(telemetry.rpm)
        self.coolant_changed.emit(telemetry.coolant_c)
        self.throttle_changed.emit(telemetry.throttle_pct)
        self.battery_changed.emit(telemetry.battery_v)
        self.intake_temp_changed.emit(telemetry.intake_temp_c)
        self.relative_throttle_changed.emit(telemetry.relative_throttle_pct)
        self.fuel_status_changed.emit(telemetry.fuel_status)
        self.fuel_level_changed.emit(telemetry.fuel_level_pct)

        # 4) Speed: OBD-II gives km/h; convert to MPH for the readout.
        #    Speed_mph = Speed_kmh * 0.621371
        if telemetry.speed_kmh is None:
            self.speed_changed.emit(None)
        else:
            self.speed_changed.emit(telemetry.speed_kmh * config.KMH_TO_MPH)

        # 5) Derived overheating flag - emit only when it flips.
        self._update_overheat(telemetry.coolant_c)

    def _update_overheat(self, coolant_c: float | None) -> None:
        """Compute + emit the overheat flag when it changes."""
        is_over = coolant_c is not None and coolant_c > config.COOLANT_CRITICAL_C
        if is_over != self._overheating:
            self._overheating = is_over
            self.overheat_changed.emit(is_over)
