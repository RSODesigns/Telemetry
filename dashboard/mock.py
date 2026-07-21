"""
mock.py
=======

Fail-safe simulation source.

When the dashboard is run away from the car (e.g. on a laptop) there is no
ELM327 adapter on ``/dev/ttyUSB0``. Rather than showing a dead UI, the Model
falls back to :class:`MockEngine`, which produces believable, continuously
changing telemetry so every visual state - cold/optimal/overheating coolant,
the full 0-8500 RPM sweep with shift-lights, and a moving speed readout - can
be exercised anywhere.

The simulation is deliberately simple and dependency-free: a tiny "driver"
state machine (idle -> accelerate -> cruise -> decelerate) drives RPM and road
speed, while coolant follows a first-order warm-up curve toward operating
temperature with an occasional scripted overheat excursion so the overheating
warning overlay can be verified without a real fault.
"""

from __future__ import annotations

import random
from enum import Enum, auto

from . import config
from .telemetry import Telemetry


class _DriveState(Enum):
    """Coarse behaviour of the simulated driver."""

    IDLE = auto()          # sat at the lights, engine idling
    ACCELERATE = auto()    # foot down, revs and speed climbing
    CRUISE = auto()        # steady-state motorway pace
    DECELERATE = auto()    # lifting off / braking back toward idle


class MockEngine:
    """Generates a realistic stream of :class:`Telemetry` snapshots.

    Call :meth:`update` on a fixed cadence (the Model calls it at
    ``config.OBD_POLL_HZ``); each call advances the internal simulation by
    ``dt`` seconds and returns the current snapshot.
    """

    # Idle band for the engine (RPM).
    _IDLE_RPM = 900.0

    def __init__(self) -> None:
        # --- Engine / drivetrain state ------------------------------------
        self._rpm: float = self._IDLE_RPM
        self._speed_kmh: float = 0.0
        self._state: _DriveState = _DriveState.IDLE
        self._state_time: float = 0.0        # seconds spent in current state
        self._state_duration: float = 2.0    # how long to stay in it
        self._shift_rpm: float = 8000.0      # rev target before an up-shift

        # --- Coolant warm-up model ----------------------------------------
        # Starts cold at ambient and approaches a target operating temp with a
        # first-order (exponential) response, mimicking a warming engine.
        self._coolant: float = config.MOCK_AMBIENT_TEMP_C
        self._coolant_target: float = 90.0   # normal operating temperature
        self._overheat_timer: float = random.uniform(45.0, 120.0)
        self._overheating: bool = False

        # --- Throttle position --------------------------------------------
        # Starts at the sensor's idle stop; the driver state machine below
        # drives it toward realistic targets per phase.
        self._throttle: float = config.THROTTLE_IDLE_STOP_PCT
        self._throttle_target: float = config.THROTTLE_IDLE_STOP_PCT

        # --- Battery / control-module voltage ----------------------------
        # Alternator charging on a healthy Elise sits around 13.8-14.4V; we
        # centre the mock there and let it drift slightly so the readout
        # visibly flickers instead of showing a flat, obviously-fake value.
        self._battery: float = 14.1

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def update(self, dt: float) -> Telemetry:
        """Advance the simulation by ``dt`` seconds and return a snapshot."""
        self._advance_driver(dt)
        self._advance_coolant(dt)
        self._advance_throttle(dt)
        self._advance_battery(dt)
        return Telemetry(
            rpm=round(self._rpm),
            coolant_c=round(self._coolant, 1),
            speed_kmh=round(self._speed_kmh, 1),
            throttle_pct=round(self._throttle, 1),
            battery_v=round(self._battery, 2),
        )

    # ------------------------------------------------------------------ #
    # Internal: engine speed + road speed
    # ------------------------------------------------------------------ #
    def _advance_driver(self, dt: float) -> None:
        """Run the little driver state machine that shapes RPM and speed."""
        self._state_time += dt
        if self._state_time >= self._state_duration:
            self._pick_next_state()

        if self._state is _DriveState.IDLE:
            # Settle toward idle with a touch of combustion "hunting" noise.
            self._rpm = self._ease(self._rpm, self._IDLE_RPM, dt, tau=0.5)
            self._rpm += random.uniform(-25.0, 25.0)
            self._speed_kmh = self._ease(self._speed_kmh, 0.0, dt, tau=1.5)

        elif self._state is _DriveState.ACCELERATE:
            # Sweep RPM up toward the shift point, then bang an up-shift by
            # dropping the revs sharply - this exercises the full tacho range
            # and the progressive shift-lights.
            self._rpm = self._ease(self._rpm, self._shift_rpm, dt, tau=0.9)
            if self._rpm >= self._shift_rpm - 60.0:
                self._rpm -= random.uniform(2200.0, 2800.0)  # up-shift
                self._shift_rpm = random.uniform(7000.0, 8300.0)
            self._speed_kmh = min(210.0, self._speed_kmh + dt * random.uniform(18.0, 30.0))

        elif self._state is _DriveState.CRUISE:
            target = random.uniform(2600.0, 3600.0)
            self._rpm = self._ease(self._rpm, target, dt, tau=1.2)
            self._rpm += random.uniform(-40.0, 40.0)
            # Hold speed roughly constant with minor throttle corrections.
            self._speed_kmh += random.uniform(-1.0, 1.0)

        else:  # DECELERATE
            self._rpm = self._ease(self._rpm, self._IDLE_RPM, dt, tau=1.1)
            self._speed_kmh = self._ease(self._speed_kmh, 0.0, dt, tau=3.0)

        # Clamp to physically sane, spec-defined bounds.
        self._rpm = max(config.RPM_MIN, min(config.RPM_MAX, self._rpm))
        self._speed_kmh = max(0.0, self._speed_kmh)

    def _pick_next_state(self) -> None:
        """Choose the next driver state and how long to hold it."""
        self._state_time = 0.0
        # Weighted transitions that read like real stop/start driving.
        transitions = {
            _DriveState.IDLE: [
                (_DriveState.ACCELERATE, 0.7), (_DriveState.IDLE, 0.3)],
            _DriveState.ACCELERATE: [
                (_DriveState.CRUISE, 0.6), (_DriveState.ACCELERATE, 0.4)],
            _DriveState.CRUISE: [
                (_DriveState.DECELERATE, 0.4), (_DriveState.ACCELERATE, 0.3),
                (_DriveState.CRUISE, 0.3)],
            _DriveState.DECELERATE: [
                (_DriveState.IDLE, 0.6), (_DriveState.ACCELERATE, 0.4)],
        }
        choices, weights = zip(*transitions[self._state])
        self._state = random.choices(choices, weights=weights, k=1)[0]
        # Accelerate bursts are short; cruises are longer.
        self._state_duration = {
            _DriveState.IDLE: random.uniform(1.5, 4.0),
            _DriveState.ACCELERATE: random.uniform(1.5, 3.5),
            _DriveState.CRUISE: random.uniform(3.0, 7.0),
            _DriveState.DECELERATE: random.uniform(1.5, 3.0),
        }[self._state]

        # New drive phase => new throttle target (bounded to sensible ranges).
        self._throttle_target = {
            _DriveState.IDLE: config.THROTTLE_IDLE_STOP_PCT,
            _DriveState.ACCELERATE: random.uniform(60.0, 95.0),
            _DriveState.CRUISE: random.uniform(22.0, 38.0),
            _DriveState.DECELERATE: random.uniform(0.0, config.THROTTLE_IDLE_STOP_PCT),
        }[self._state]

    # ------------------------------------------------------------------ #
    # Internal: coolant temperature warm-up + scripted overheat demo
    # ------------------------------------------------------------------ #
    def _advance_coolant(self, dt: float) -> None:
        """First-order warm-up toward the target temperature.

        Every so often the target is nudged above the critical threshold for a
        few seconds so the flashing red state and the overheat warning overlay
        can be demonstrated, then it recovers to normal.
        """
        self._overheat_timer -= dt
        if self._overheat_timer <= 0.0:
            self._overheating = not self._overheating
            if self._overheating:
                # Brief simulated cooling-system fault.
                self._coolant_target = random.uniform(100.0, 108.0)
                self._overheat_timer = random.uniform(6.0, 10.0)
            else:
                self._coolant_target = 90.0
                self._overheat_timer = random.uniform(60.0, 150.0)

        # Warm-up is slow (large time constant); small sensor noise on top.
        self._coolant = self._ease(self._coolant, self._coolant_target, dt, tau=25.0)
        self._coolant += random.uniform(-0.15, 0.15)
        self._coolant = max(config.MOCK_AMBIENT_TEMP_C - 5.0,
                            min(config.COOLANT_MAX_C, self._coolant))

    # ------------------------------------------------------------------ #
    # Internal: throttle position
    # ------------------------------------------------------------------ #
    def _advance_throttle(self, dt: float) -> None:
        """Ease toward the phase-appropriate throttle target with light noise."""
        # Fast attack (short tau) so a punchy accelerate visibly slams the bar
        # to the top; small random jitter mimics real pedal micro-corrections.
        self._throttle = self._ease(self._throttle, self._throttle_target,
                                    dt, tau=0.35)
        self._throttle += random.uniform(-1.0, 1.0)
        self._throttle = max(config.THROTTLE_MIN_PCT,
                             min(config.THROTTLE_MAX_PCT, self._throttle))

    # ------------------------------------------------------------------ #
    # Internal: battery / control-module voltage
    # ------------------------------------------------------------------ #
    def _advance_battery(self, dt: float) -> None:
        """Slow drift around a healthy alternator-charging voltage.

        Doesn't try to model transient loads (headlights, cooling fan) - just
        keeps the readout visibly alive so the operator can see it is a live
        value and not a hard-coded number.
        """
        # Slowly nudge toward a target inside the healthy 13.8-14.4V band.
        target = 14.1 + 0.15 * random.uniform(-1.0, 1.0)
        self._battery = self._ease(self._battery, target, dt, tau=4.0)
        # Small sensor-style noise on top.
        self._battery += random.uniform(-0.02, 0.02)
        # Hard-clamp to a plausible envelope so the widget never divides by
        # weirdness.
        self._battery = max(9.0, min(16.0, self._battery))

    # ------------------------------------------------------------------ #
    # Helper
    # ------------------------------------------------------------------ #
    @staticmethod
    def _ease(current: float, target: float, dt: float, tau: float) -> float:
        """Exponential approach of ``current`` toward ``target``.

        ``tau`` is the time constant in seconds: larger = slower/smoother.
        Frame-rate independent because it is a function of ``dt``.
        """
        if tau <= 0.0:
            return target
        alpha = 1.0 - pow(2.718281828, -dt / tau)
        return current + (target - current) * alpha
