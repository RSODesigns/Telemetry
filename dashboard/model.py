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


# ---------------------------------------------------------------------------
# Field classification for the per-frame query budget (see OBDModel's
# ``_needed_fields`` / slow-field decimation notes below).
#
# "Fast" fields reflect driver input / motion in real time (RPM, speed,
# throttle) and are re-queried every loop iteration. Every other field
# changes only over seconds-to-minutes (temperatures, battery, fuel) - on a
# K-line (ISO 9141-2) link, where the ELM327 can't pipeline requests and
# every PID is a blocking round-trip, re-fetching those just as often steals
# round-trip budget from the fields that actually need to be fresh.
# ---------------------------------------------------------------------------
FAST_TELEMETRY_FIELDS = frozenset({
    "rpm", "speed_kmh", "throttle_pct", "relative_throttle_pct",
})
ALL_QUERY_FIELDS = (
    "rpm", "coolant_c", "speed_kmh", "throttle_pct", "battery_v",
    "intake_temp_c", "relative_throttle_pct", "fuel_status", "fuel_level_pct",
)


class OBDModel(QThread):
    """Background worker that continuously produces telemetry.

    The worker never touches Qt signals; instead it exposes two thread-safe
    read points that the controller polls from the GUI thread:

    * :meth:`snapshot` - the latest :class:`Telemetry` plus the current
      :class:`ConnectionState`.
    * :meth:`drain_messages` - and clears any queued diagnostic strings.
    """

    def __init__(self, force_mock: bool | None = None,
                needed_fields: frozenset[str] | None = None, parent=None) -> None:
        super().__init__(parent)
        # Whether to skip real hardware entirely. Defaults to the config flag.
        self._force_mock = config.FORCE_MOCK_MODE if force_mock is None else force_mock
        self._running = True                 # cleared by stop() to end the loop
        self._connection = None              # the live obd.OBD instance, if any

        # Which Telemetry fields the active layout actually renders (by
        # dataclass attribute name, e.g. "rpm", "coolant_c"). ``None`` means
        # "no restriction, query everything" (the historic default, used by
        # anything that constructs OBDModel directly, e.g. scratch scripts).
        #
        # Why this matters: on a K-line (ISO 9141-2) link every PID is a
        # blocking round-trip over a slow, single-wire, half-duplex bus - the
        # ELM327 cannot pipeline requests, so each extra query in the loop is
        # pure added latency. Restricting the query set to only what's on
        # screen is the only lever available to cut per-frame lag; it can't
        # be parallelised away.
        self._needed_fields = needed_fields

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
        """Continuously query the ECU, with dropout detection + reconnect.

        Query budget per iteration
        ---------------------------
        Restrict the query set to what the active layout actually renders
        (see the ``_needed_fields`` docstring in __init__), then split that
        set into "fast" fields (RPM, speed, throttle - re-queried every
        iteration, since they can change from one frame to the next) and
        "slow" fields (temperatures, battery, fuel - re-queried in rotation,
        one per iteration, since they physically cannot change meaningfully
        within a single ~50ms poll period). This keeps the *fast* fields'
        round-trip latency low and constant regardless of how many slow
        gauges a layout has, which is the only lever available on a K-line
        (ISO 9141-2) link where the ELM327 can't pipeline requests.
        """
        consecutive_errors = 0

        # Restrict the per-frame query set to what the active layout actually
        # renders. ``None`` (no restriction passed in) queries every PID, in
        # rotation for the slow ones, matching pre-existing behaviour's data
        # (just not necessarily every single field on every single frame).
        want = self._needed_fields
        def needed(field: str) -> bool:
            return want is None or field in want

        # PID/query dispatch for every field, used for both fast (every
        # iteration) and slow (one per iteration, round-robin) fields.
        query_fn = {
            "rpm": lambda: self._query_value(obd.commands.RPM),
            "speed_kmh": lambda: self._query_value(obd.commands.SPEED),
            "throttle_pct": lambda: self._query_value(obd.commands.THROTTLE_POS),
            "relative_throttle_pct": lambda: self._query_value(obd.commands.RELATIVE_THROTTLE_POS),
            "coolant_c": lambda: self._query_value(obd.commands.COOLANT_TEMP),
            # ELM_VOLTAGE is an AT command answered by the adapter itself,
            # not the ECU, so it stays live even during ignition-off / ECU
            # -sleep windows and doubles as a link health signal.
            "battery_v": lambda: self._query_value(obd.commands.ELM_VOLTAGE),
            "intake_temp_c": lambda: self._query_value(obd.commands.INTAKE_TEMP),
            "fuel_status": self._query_fuel_status,
            "fuel_level_pct": lambda: self._query_value(obd.commands.FUEL_LEVEL),
        }

        slow_fields = [f for f in ALL_QUERY_FIELDS
                       if f not in FAST_TELEMETRY_FIELDS and needed(f)]
        slow_cursor = 0
        # Last known-good value for each slow field, carried forward between
        # the iterations where it isn't that field's turn to be queried.
        # Only overwritten on a *successful* (non-None) query, so a single
        # flaky round-trip doesn't blank an otherwise healthy gauge. Starts
        # as None ("no data yet"), same as every other field.
        slow_cache: dict[str, object] = {f: None for f in slow_fields}

        while self._running:
            loop_start = time.monotonic()
            try:
                # If the transport reports it is down, jump straight to recovery.
                if self._connection is None or not self._connection.is_connected():
                    raise ConnectionError("OBD link reported not connected")

                # Fields attempted with a real round-trip *this iteration*,
                # mapped to what came back. Used only for dropout detection
                # below - a field absent from this dict was never attempted
                # (excluded by ``_needed_fields``) and must not be treated
                # as a failure. Slow fields not up in this iteration's
                # rotation are likewise absent here, even though the
                # snapshot below still reports their cached value.
                fresh: dict[str, object] = {}
                for fld in FAST_TELEMETRY_FIELDS:
                    if needed(fld):
                        fresh[fld] = query_fn[fld]()

                # --- Slow fields: query exactly one per iteration, in
                # round-robin, and reuse the cached value for the rest. ---
                if slow_fields:
                    slow_field = slow_fields[slow_cursor]
                    slow_cursor = (slow_cursor + 1) % len(slow_fields)
                    result = query_fn[slow_field]()
                    fresh[slow_field] = result
                    if result is not None:
                        slow_cache[slow_field] = result

                snapshot = Telemetry(
                    rpm=fresh.get("rpm"),
                    coolant_c=slow_cache.get("coolant_c"),
                    speed_kmh=fresh.get("speed_kmh"),
                    throttle_pct=fresh.get("throttle_pct"),
                    battery_v=slow_cache.get("battery_v"),
                    intake_temp_c=slow_cache.get("intake_temp_c"),
                    relative_throttle_pct=fresh.get("relative_throttle_pct"),
                    fuel_status=slow_cache.get("fuel_status"),
                    fuel_level_pct=slow_cache.get("fuel_level_pct"),
                )

                # Dropout detection is based only on *this iteration's fresh*
                # query attempts (``fresh``), not the displayed snapshot:
                # cached slow fields hold their last good value indefinitely
                # by design, so they'd never look "all null" again after the
                # first success and would mask a real disconnect. Fields
                # never attempted this iteration simply aren't in ``fresh``,
                # so a restricted field set (or a slow field waiting its
                # turn) is never mistaken for a failure. Battery voltage is
                # excluded on purpose because it comes from the adapter, not
                # the ECU.
                queried_fields = [f for f in fresh if f != "battery_v"]
                ecu_all_null = (
                    bool(queried_fields)
                    and all(fresh[f] is None for f in queried_fields)
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

        Why auto-baud (``baudrate=None``) on that port comes first: some
        ELM327 clones (e.g. the Vgate vLinker FS) don't lock on cleanly when
        pyserial's baud is forced directly - they need the handshake/reset
        sequence python-obd runs when it negotiates the baud itself. Forcing
        a specific rate straight away can produce "Failed to read port" on
        hardware that connects fine when the baud is left to auto-detect.

        Returns ``True`` on success and stashes the live connection on
        ``self._connection``.
        """
        attempts: list[tuple[str | None, int | None]] = []

        # 1. Explicit port first, if it plausibly exists. Auto-baud on that
        #    same port before any forced rate - see the auto-baud note above.
        default_port_exists = os.path.exists(config.DEFAULT_PORT)
        if default_port_exists:
            attempts.append((config.DEFAULT_PORT, None))
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

    def _query_fuel_status(self) -> tuple[str, str] | None:
        """Query FUEL_STATUS PID and return tuple of status strings, or None."""
        try:
            response = self._connection.query(obd.commands.FUEL_STATUS, force=True)
            if response is None or response.is_null() or response.value is None:
                return None
            val = response.value
            if isinstance(val, tuple):
                return (str(val[0]) if len(val) > 0 else "", str(val[1]) if len(val) > 1 else "")
            return (str(val), "")
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
