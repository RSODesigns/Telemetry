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

    python3 main.py                        # shows welcome screen
    python3 main.py --layout general       # skip welcome, go straight to Road
    python3 main.py --layout track         # skip welcome, go straight to Track

For development on a laptop with no adapter, force the simulator and run in a
normal window::

    python3 main.py --mock --windowed

Command-line options
--------------------
    --mock              Skip real hardware and always use the mock engine.
    --windowed          Run in a normal window instead of fullscreen.
    --layout {general,track}
                        Which dashboard layout to show.  When omitted a
                        welcome screen with Road / Track buttons is shown.
                        ``general`` - vertical coolant bar, big tacho, digital
                        MPH: the original road-friendly view.
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
from dashboard.welcome import WelcomeScreen

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
        "--layout", choices=("general", "track"), default=None,
        help=(
            "which dashboard layout to show.  When omitted a welcome screen "
            "with Road / Track buttons is displayed.  'general' is the "
            "original road-friendly three-gauge view; 'track' emphasises the "
            "tacho and shift-lights with compact readouts and a throttle bar."
        ),
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
#  Dashboard builder: creates the window + controller, wires them, starts data
# ---------------------------------------------------------------------------
def _launch_dashboard(layout: str, args: argparse.Namespace,
                      app: QApplication) -> None:
    """Build the chosen dashboard window, wire it to a fresh controller, and
    show it.  This is called either immediately (when ``--layout`` is given) or
    after the user picks Road / Track on the welcome screen.
    """
    # --- View --------------------------------------------------------------
    if layout == "track":
        window = TrackDashboardWindow(windowed=args.windowed)
    else:
        window = DashboardWindow(windowed=args.windowed)

    # --- Controller (owns the Model thread) --------------------------------
    force_mock = True if args.mock else None  # None => auto-detect, fall back
    controller = DashboardController(force_mock=force_mock)

    # --- Wire Controller signals -> View -----------------------------------
    controller.rpm_changed.connect(window.rpm_gauge.set_value)
    controller.connection_changed.connect(window.set_connection_state)
    controller.message.connect(window.set_message)
    controller.message.connect(log.info)

    if layout == "track":
        controller.coolant_changed.connect(window.on_coolant_changed)
        controller.speed_changed.connect(window._set_speed)
        controller.relative_throttle_changed.connect(window._set_throttle)
        controller.battery_changed.connect(window._set_battery)
        controller.intake_temp_changed.connect(window._set_intake)
        controller.fuel_level_changed.connect(window._set_fuel)
    else:
        controller.coolant_changed.connect(window.coolant_gauge.set_value)
        controller.speed_changed.connect(window.speedometer.set_value)
        controller.overheat_changed.connect(window.set_overheating)

    # --- Clean shutdown ----------------------------------------------------
    app.aboutToQuit.connect(controller.stop)

    # --- Show ---------------------------------------------------------------
    if args.windowed:
        window.show()
    else:
        window.showFullScreen()

    controller.start()
    log.info(
        "Dashboard started (%s mode, %s layout). Press Esc or Q to quit.",
        "mock" if args.mock else "auto",
        layout,
    )

    # Keep references alive for the lifetime of the app so they aren't GC'd.
    app._dashboard_window = window
    app._dashboard_controller = controller


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    app = QApplication(sys.argv)
    app.setApplicationName("Lotus Elise Dashboard")
    if not args.windowed:
        app.setOverrideCursor(Qt.BlankCursor)

    if args.layout is not None:
        # Direct launch: skip the welcome screen (backwards compatible).
        _launch_dashboard(args.layout, args, app)
    else:
        # Show the welcome / mode-selection screen.
        welcome = WelcomeScreen(windowed=args.windowed)

        def _on_layout_chosen(layout: str) -> None:
            welcome.close()
            _launch_dashboard(layout, args, app)

        welcome.layout_chosen.connect(_on_layout_chosen)

        if args.windowed:
            welcome.show()
        else:
            welcome.showFullScreen()

        # Keep a reference so the welcome screen isn't garbage-collected.
        app._welcome_screen = welcome

    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
