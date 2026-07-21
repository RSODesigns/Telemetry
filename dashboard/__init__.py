"""
Lotus Elise Digital Dashboard
=============================

A production-grade, asynchronous PyQt5 automotive dashboard designed to run
fullscreen on a Raspberry Pi 5 driving a 5-inch 800x480 touchscreen.

The package is organised as a strict Model-View-Controller (MVC) system so the
serial I/O never blocks the render loop:

    model.OBDModel          -> the "Model": a QThread that polls the ECU
    controller.DashboardController
                            -> the "Controller": routes thread-safe signals
    view.DashboardWindow    -> the "View": QPainter vector-graphics gauges
    widgets/                -> individual self-contained gauge widgets
    config                  -> tunable constants (colours, thresholds, serial)

See ``main.py`` in the project root for the composition entry point.
"""

__all__ = ["config", "model", "controller", "view", "widgets"]
__version__ = "1.0.0"
