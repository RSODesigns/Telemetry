#!/usr/bin/env python3
"""
main.py - Lotus Elise Digital Dashboard entry point
====================================================

Composition root that assembles the Model-View-Controller stack and starts the
Qt event loop.

    Model       dashboard.model.OBDModel          (QThread, serial I/O)
    Controller  dashboard.controller.DashboardController (signal router)
    View        dashboard.view.DashboardWindow    (QPainter gauges)

Dependencies
------------
    PyQt5        - GUI toolkit / QThread / QPainter   (pip install PyQt5)
    python-obd   - ELM327 / OBD-II communication      (pip install obd)
    pyserial     - serial transport (pulled in by obd)
See requirements.txt.

Running it
----------
On the Raspberry Pi (fullscreen kiosk, cursor hidden)::

    python3 main.py

For development on a laptop with no adapter, force the simulator and run in a
normal window::

    python3 main.py --mock --windowed

Command-line options
--------------------
    --mock              Skip real hardware and always use the mock engine.
    --windowed          Run in a normal 800x480 window instead of fullscreen.
    --layout {general,track}
                        Which dashboard layout to show.
                        ``general`` (default) - vertical coolant bar, big
                        tacho, digital MPH: the original road-friendly view.
                        ``track`` - dominant tacho with a compact top strip of
                        coolant / battery / speed readouts and a horizontal
                        throttle bar underneath; uses stricter coolant zones
                        (84-99 green, 100-104 amber, 105+ flashing red).

Tip for the Pi: to render straight on the GPU without a desktop, launch with
``QT_QPA_PLATFORM=eglfs python3 main.py``.

Runtime: press Esc or Q to quit.
"""

from __future__ import annotations

import argparse
import logging
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from dashboard import config
from dashboard.controller import DashboardController
from dashboard.view import DashboardWindow, TrackDashboardWindow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("dashboard")


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse the small set of runtime flags."""
    parser = argparse.ArgumentParser(description="Lotus Elise digital dashboard")
    parser.add_argument(
        "--mock", action="store_true",
        help="force the simulated engine instead of talking to real hardware",
    )
    parser.add_argument(
        "--windowed", action="store_true",
        help="run in a normal window instead of fullscreen (for development)",
    )
    parser.add_argument(
        "--layout", choices=("general", "track"), default="general",
        help=(
            "which dashboard layout to show. 'general' (default) is the "
            "original road-friendly three-gauge view; 'track' emphasises the "
            "tacho and shift-lights with compact readouts and a throttle bar."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    app = QApplication(sys.argv)
    app.setApplicationName("Lotus Elise Dashboard")
    # Hide the mouse pointer everywhere for the embedded touchscreen build.
    if not args.windowed:
        app.setOverrideCursor(Qt.BlankCursor)

    # --- View --------------------------------------------------------------
    # Two layouts share the same signal surface; the wiring below dispatches
    # per-layout because the target widget names and slot semantics differ.
    if args.layout == "track":
        window = TrackDashboardWindow(windowed=args.windowed)
    else:
        window = DashboardWindow(windowed=args.windowed)

    # --- Controller (owns the Model thread) --------------------------------
    force_mock = True if args.mock else None  # None => auto-detect, fall back
    controller = DashboardController(force_mock=force_mock)

    # --- Wire Controller signals -> View -----------------------------------
    # These are all direct (same-thread) connections: the Controller already
    # marshalled the worker-thread data onto the GUI thread for us.
    # Signals common to both layouts.
    controller.rpm_changed.connect(window.rpm_gauge.set_value)
    controller.connection_changed.connect(window.set_connection_state)
    controller.message.connect(window.set_message)
    controller.message.connect(log.info)  # mirror diagnostics to the console

    if args.layout == "track":
        # Track: readouts are fed through the unified SidePanel slot setters.
        # The window handles its own overheat detection against the Track
        # threshold via ``on_coolant_changed``, so ``overheat_changed`` is
        # intentionally NOT connected here.
        controller.coolant_changed.connect(window.on_coolant_changed)
        controller.speed_changed.connect(window._set_speed)
        controller.relative_throttle_changed.connect(window._set_throttle)
        controller.battery_changed.connect(window._set_battery)
        controller.intake_temp_changed.connect(window._set_intake)
        controller.fuel_level_changed.connect(window._set_fuel)
    else:
        # General: coolant bar / big tacho / MPH speedometer plus the classic
        # controller-driven overheat overlay (threshold: COOLANT_CRITICAL_C).
        controller.coolant_changed.connect(window.coolant_gauge.set_value)
        controller.speed_changed.connect(window.speedometer.set_value)
        controller.overheat_changed.connect(window.set_overheating)

    # --- Clean shutdown: stop the data thread before the app exits ---------
    app.aboutToQuit.connect(controller.stop)

    # --- Show ---------------------------------------------------------------
    if args.windowed:
        window.show()
    else:
        window.showFullScreen()

    # --- Start polling and enter the event loop ----------------------------
    controller.start()
    log.info(
        "Dashboard started (%s mode, %s layout). Press Esc or Q to quit.",
        "mock" if args.mock else "auto",
        args.layout,
    )
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
