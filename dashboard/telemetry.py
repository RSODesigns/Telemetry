"""
telemetry.py
============

The immutable data object that travels from the Model (data thread) through
the Controller (signal router) to the View.

Using a single small ``@dataclass`` snapshot rather than a bag of loose numbers
has two benefits for a threaded Qt app:

* **Atomicity** - one ``pyqtSignal(object)`` emission carries a fully
  consistent frame of telemetry, so the View never renders a mix of an old
  RPM with a new speed.
* **Clarity** - ``None`` is used explicitly to mean "this PID was not
  available on this poll" (e.g. the ECU didn't answer, or the sensor is
  unsupported), which the gauges can render as a dim / "--" state instead of
  drawing a misleading zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ConnectionState(Enum):
    """Lifecycle of the link to the ECU, surfaced to the status indicator."""

    CONNECTING = "connecting"      # attempting to open the serial port
    CONNECTED = "connected"        # live data flowing from a real adapter
    RECONNECTING = "reconnecting"  # lost the link, retrying
    MOCK = "mock"                  # simulated data (no adapter present)


@dataclass(frozen=True)
class Telemetry:
    """A single consistent snapshot of the values shown on the dashboard.

    Attributes
    ----------
    rpm:
        Engine speed in revolutions per minute, or ``None`` if unavailable.
    coolant_c:
        Coolant temperature in degrees Celsius, or ``None`` if unavailable.
    speed_kmh:
        Road speed in km/h exactly as the ECU reports it (OBD-II native unit),
        or ``None`` if unavailable. Conversion to MPH happens in the View so
        the raw value stays authoritative here.
    throttle_pct:
        Absolute throttle position in the 0-100 % scale that OBD-II reports.
        Idle stop on a 2ZZ reads ~12-14 %; the View shifts the visible fill
        so the bar starts moving once the pedal is meaningfully pressed.
        ``None`` if unavailable.
    battery_v:
        Voltage measured at the OBD-II port (adapter's ATRV reading, so it
        answers even at ignition off). ``None`` if unavailable.
    """

    rpm: float | None = None
    coolant_c: float | None = None
    speed_kmh: float | None = None
    throttle_pct: float | None = None
    battery_v: float | None = None
    intake_temp_c: float | None = None
    relative_throttle_pct: float | None = None
    fuel_status: tuple[str, str] | None = None
    fuel_level_pct: float | None = None
