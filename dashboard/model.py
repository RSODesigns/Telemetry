"""
model.py
========

The **Model** layer of the MVC design: a dedicated :class:`QThread` that owns
the serial link to the car's ECU and polls it as fast as is sensible, entirely
off the GUI thread.

Why a thread?
-------------
``python-obd`` talks to an ELM327 over a serial port. Every ``query()`` blocks
until the adapter answers (tens of milliseconds, sometimes more, and *seconds*
if the adapter is mid-dropout). Doing that on Qt's main thread would freeze the
render loop and make the gauges stutter. By isolating all I/O in this worker
thread the View is never blocked.

How the data crosses the thread boundary
----------------------------------------
Rather than emitting a Qt signal for every sample straight from the worker
thread, the model simply *parks the newest reading* in a small, mutex-protected
snapshot (:meth:`snapshot`) and appends diagnostics to a lock-guarded queue
(:meth:`drain_messages`). The :class:`~dashboard.controller.DashboardController`
pulls from these on the GUI thread via a timer and does all the ``pyqtSignal``
emission there.

This "publish latest / poll on the UI thread" pattern is a well-worn approach
for high-rate telemetry. It:

* keeps every signal emission on the GUI thread (inherently thread-safe),
* decouples the acquisition rate from the UI rate (the UI just reads the most
  recent value and naturally coalesces bursts), and
* avoids marshalling a Python object across the thread boundary on every
  single sample.

How python-obd is used here
---------------------------
* ``obd.OBD(portstr, baudrate=...)`` opens/negotiates the connection. Passing
  ``portstr=None`` lets the library auto-scan serial ports and baud rates.
* ``connection.query(obd.commands.RPM)`` sends the PID request and returns an
  ``OBDResponse``. ``response.is_null()`` means "no data this time"; otherwise
  ``response.value`` is a Pint quantity whose ``.magnitude`` is the number in
  the command's native unit (RPM, degC, km/h).
* ``connection.is_connected()`` is polled to detect a dropped link so we can
  transition into a reconnect cycle instead of spraying exceptions.

Dropout safeguards
------------------
Every poll is wrapped in ``try/except``. Consecutive failures are counted; once
the link is judged dead the model flips its published state to ``RECONNECTING``
and enters a back-off reconnect loop rather than crashing. If *no* adapter can
be opened at start-up we transparently switch to the
:class:`~dashboard.mock.MockEngine` so the UI is always alive.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque

from PyQt5.QtCore import QThread

from . import config
from .mock import MockEngine
from .telemetry import ConnectionState, Telemetry

# ---------------------------------------------------------------------------
# Import python-obd defensively. On a dev laptop the library (or a serial
# backend) may be missing entirely; that must NOT stop the dashboard - it just
# means we run in simulation mode.
# ---------------------------------------------------------------------------
try:
    import obd  # type: ignore

    OBD_AVAILABLE = True
except Exception:  # pragma: no cover - depends on host environment
    obd = None  # type: ignore
    OBD_AVAILABLE = False


class OBDModel(QThread):
    """Background worker that continuously produces telemetry.

    The worker never touches Qt signals; instead it exposes two thread-safe
    read points that the controller polls from the GUI thread:

    * :meth:`snapshot` - the latest :class:`Telemetry` plus the current
      :class:`ConnectionState`.
    * :meth:`drain_messages` - and clears any queued diagnostic strings.
    """

    def __init__(self, force_mock: bool | None = None, parent=None) -> None:
        super().__init__(parent)
        # Whether to skip real hardware entirely. Defaults to the config flag.
        self._force_mock = config.FORCE_MOCK_MODE if force_mock is None else force_mock
        self._running = True                 # cleared by stop() to end the loop
        self._connection = None              # the live obd.OBD instance, if any

        # ---- Thread-safe published state (read by the GUI thread) --------
        self._lock = threading.Lock()
        self._latest = Telemetry()                       # newest reading
        self._pub_state = ConnectionState.CONNECTING     # newest link state
        self._messages: deque[str] = deque(maxlen=100)   # diagnostics queue

        # Worker-local mirror of the state, for change detection in run().
        self._state = ConnectionState.CONNECTING

    # ------------------------------------------------------------------ #
    # Thread-safe read API (called from the GUI thread)
    # ------------------------------------------------------------------ #
    def snapshot(self) -> tuple[Telemetry, ConnectionState]:
        """Return the most recent telemetry and connection state."""
        with self._lock:
            return self._latest, self._pub_state

    def drain_messages(self) -> list[str]:
        """Return and clear any queued diagnostic messages."""
        with self._lock:
            msgs = list(self._messages)
            self._messages.clear()
            return msgs

    # ------------------------------------------------------------------ #
    # Internal publish helpers (called from the worker thread)
    # ------------------------------------------------------------------ #
    def _publish(self, telemetry: Telemetry) -> None:
        with self._lock:
            self._latest = telemetry

    def _log(self, message: str) -> None:
        with self._lock:
            self._messages.append(message)

    def _set_state(self, state: ConnectionState) -> None:
        """Publish a connection-state change (only when it actually changes)."""
        if state is self._state:
            return
        self._state = state
        with self._lock:
            self._pub_state = state

    # ------------------------------------------------------------------ #
    # Thread entry point
    # ------------------------------------------------------------------ #
    def run(self) -> None:  # noqa: D401 - Qt override
        """Main worker loop; runs on the worker thread until :meth:`stop`."""
        if self._force_mock or not OBD_AVAILABLE:
            reason = "forced by config" if self._force_mock else "python-obd not installed"
            self._log(f"Starting in MOCK mode ({reason}).")
            self._run_mock_loop()
            return

        # Try to reach a real adapter. If we can't, degrade gracefully to mock.
        self._set_state(ConnectionState.CONNECTING)
        if not self._open_connection():
            self._log("No OBD-II adapter found - falling back to MOCK mode.")
            self._run_mock_loop()
            return

        self._set_state(ConnectionState.CONNECTED)
        self._run_obd_loop()

    # ------------------------------------------------------------------ #
    # Real-hardware polling loop
    # ------------------------------------------------------------------ #
    def _run_obd_loop(self) -> None:
        """Continuously query the ECU, with dropout detection + reconnect."""
        consecutive_errors = 0

        while self._running:
            loop_start = time.monotonic()
            try:
                # If the transport reports it is down, jump straight to recovery.
                if self._connection is None or not self._connection.is_connected():
                    raise ConnectionError("OBD link reported not connected")

                snapshot = Telemetry(
                    rpm=self._query_value(obd.commands.RPM),
                    coolant_c=self._query_value(obd.commands.COOLANT_TEMP),
                    speed_kmh=self._query_value(obd.commands.SPEED),
                    throttle_pct=self._query_value(obd.commands.THROTTLE_POS),
                    # ELM_VOLTAGE is an AT command answered by the adapter
                    # itself, not the ECU, so it stays live even during
                    # ignition-off / ECU-sleep windows and doubles as a link
                    # health signal.
                    battery_v=self._query_value(obd.commands.ELM_VOLTAGE),
                )

                # A frame where every ECU-sourced PID failed is treated as
                # an error; a healthy link should answer at least one of
                # them. Battery voltage is excluded on purpose because it
                # comes from the adapter, not the ECU.
                ecu_all_null = (
                    snapshot.rpm is None
                    and snapshot.coolant_c is None
                    and snapshot.speed_kmh is None
                    and snapshot.throttle_pct is None
                )
                if ecu_all_null:
                    consecutive_errors += 1
                else:
                    consecutive_errors = 0
                    self._set_state(ConnectionState.CONNECTED)
                    self._publish(snapshot)

            except Exception as exc:  # broad on purpose: never kill the thread
                consecutive_errors += 1
                self._log(f"OBD poll error: {exc}")

            # Too many failures in a row -> the link is really gone. Try to
            # re-establish it instead of spinning on a dead port.
            if consecutive_errors >= config.OBD_MAX_CONSECUTIVE_ERRORS:
                if not self._recover_connection():
                    break  # stop() was called while we were reconnecting
                consecutive_errors = 0

            self._sleep_remaining(loop_start, config.OBD_POLL_INTERVAL_S)

        self._close_connection()

    def _recover_connection(self) -> bool:
        """Back-off reconnect cycle after a dropout.

        Returns ``True`` once the link is restored, or ``False`` if the thread
        was asked to stop while trying.
        """
        self._set_state(ConnectionState.RECONNECTING)
        self._close_connection()

        while self._running:
            self._log("Attempting to reconnect to OBD-II adapter...")
            if self._open_connection():
                self._set_state(ConnectionState.CONNECTED)
                self._log("OBD-II link re-established.")
                return True
            # Wait before retrying, but stay responsive to stop().
            self._interruptible_sleep(config.OBD_RECONNECT_DELAY_S)

        return False

    # ------------------------------------------------------------------ #
    # Mock polling loop
    # ------------------------------------------------------------------ #
    def _run_mock_loop(self) -> None:
        """Drive the UI from :class:`MockEngine` at the normal poll rate."""
        self._set_state(ConnectionState.MOCK)
        engine = MockEngine()
        last = time.monotonic()

        while self._running:
            loop_start = time.monotonic()
            dt = loop_start - last
            last = loop_start
            self._publish(engine.update(dt))
            self._sleep_remaining(loop_start, config.OBD_POLL_INTERVAL_S)

    # ------------------------------------------------------------------ #
    # Connection helpers
    # ------------------------------------------------------------------ #
    def _open_connection(self) -> bool:
        """Try hard to open a working OBD connection.

        Strategy: if ``config.DEFAULT_PORT`` actually exists on disk, try it
        first at each configured baud rate; otherwise (or if it doesn't
        answer) fall back to python-obd's full auto-scan, and finally any
        other ports the library can see.

        Why explicit-port-first-when-present: python-obd's auto-scan is
        aggressive - it sends ``ATBRD`` to try switching the adapter's baud
        rate on the fly, and on a K-line (ISO 9141-2 / KWP2000) ECU that
        stray traffic can leave the adapter or the ECU's diagnostic session
        in a state that makes the *next* connection attempt fail with
        "no response to 0100". Trying the known-good port first sidesteps
        this whenever the operator has told us where the adapter lives
        (Pi default ``/dev/ttyUSB0``, or an override via
        ``PITELEMETRY_PORT``).

        Returns ``True`` on success and stashes the live connection on
        ``self._connection``.
        """
        attempts: list[tuple[str | None, int | None]] = []

        # 1. Explicit port first, if it plausibly exists.
        default_port_exists = os.path.exists(config.DEFAULT_PORT)
        if default_port_exists:
            for baud in config.BAUD_RATES:
                attempts.append((config.DEFAULT_PORT, baud))

        # 2. python-obd's full auto-scan is the fallback.
        attempts.append((None, None))

        # 3. If auto-scan didn't find it either, try to enumerate ports and
        #    hit whatever else the OS sees. If DEFAULT_PORT existed we already
        #    tried it above, so exclude it here to avoid a redundant retry.
        if not default_port_exists:
            for baud in config.BAUD_RATES:
                attempts.append((config.DEFAULT_PORT, baud))

        # Add any other serial ports the OS exposes (covers /dev/ttyACM0 etc.).
        try:
            for port in obd.scan_serial():
                if port != config.DEFAULT_PORT:
                    for baud in config.BAUD_RATES:
                        attempts.append((port, baud))
        except Exception:
            pass  # scan_serial is best-effort only

        for portstr, baud in attempts:
            if not self._running:
                return False
            where = portstr or "auto-detect"
            try:
                self._log(f"Opening OBD-II on {where} @ {baud or 'auto'} baud...")
                connection = obd.OBD(
                    portstr=portstr,
                    baudrate=baud,
                    fast=False,                       # no command batching; robust
                    timeout=config.OBD_CONNECT_TIMEOUT_S,
                    check_voltage=True,               # verify the adapter sees 12V
                )
                if connection.is_connected():
                    self._connection = connection
                    self._log(f"Connected on {connection.port_name()}.")
                    return True
                connection.close()
            except Exception as exc:
                self._log(f"Connection attempt failed ({where}): {exc}")

        return False

    def _query_value(self, command) -> float | None:
        """Query one PID and return its magnitude as a float, or ``None``.

        Wrapped so a single flaky PID (or a Pint/units hiccup) can never take
        down the whole poll - it just yields ``None`` for that field, which the
        View renders as a dim "no data" state.
        """
        try:
            response = self._connection.query(command, force=True)
            if response is None or response.is_null() or response.value is None:
                return None
            # response.value is a Pint quantity; .magnitude is the raw number
            # in the command's native unit (RPM, degC for coolant, km/h speed).
            return float(response.value.magnitude)
        except Exception:
            return None

    def _close_connection(self) -> None:
        """Close the serial link if open, swallowing any shutdown errors."""
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None

    # ------------------------------------------------------------------ #
    # Timing utilities
    # ------------------------------------------------------------------ #
    def _sleep_remaining(self, loop_start: float, interval_s: float) -> None:
        """Sleep so the loop period matches ``interval_s`` (drift-corrected)."""
        elapsed = time.monotonic() - loop_start
        remaining = interval_s - elapsed
        if remaining > 0:
            self._interruptible_sleep(remaining)

    def _interruptible_sleep(self, seconds: float) -> None:
        """Sleep in small slices so :meth:`stop` takes effect promptly."""
        deadline = time.monotonic() + seconds
        while self._running and time.monotonic() < deadline:
            self.msleep(10)

    # ------------------------------------------------------------------ #
    # Public control
    # ------------------------------------------------------------------ #
    def stop(self) -> None:
        """Ask the worker loop to finish and wait for the thread to exit.

        Safe to call from the GUI thread during application shutdown.
        """
        self._running = False
        self.wait(3000)  # give run() up to 3s to unwind and close the port
