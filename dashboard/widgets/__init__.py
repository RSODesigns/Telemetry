"""
Reusable QPainter gauge widgets for the dashboard View.

Each widget is fully self-contained: it exposes a simple ``set_value()`` slot,
performs its own 60 FPS easing animation, and renders itself with pure vector
graphics (no external image assets) so it stays crisp at any scale and is cheap
for the Raspberry Pi 5 VideoCore VII GPU to composite.
"""

from .coolant_gauge import CoolantGauge
from .fuel_status_widget import FuelStatusWidget
from .lap_timer_widget import LapTimerWidget
from .mini_readout import MiniReadout
from .motec_tachometer import MotecTachometer
from .rpm_gauge import RPMGauge
from .side_panel import SidePanel
from .speedometer import Speedometer
from .throttle_bar import ThrottleBar
from .throttle_card import ThrottleCard

__all__ = [
    "CoolantGauge",
    "FuelStatusWidget",
    "LapTimerWidget",
    "MiniReadout",
    "MotecTachometer",
    "RPMGauge",
    "SidePanel",
    "Speedometer",
    "ThrottleBar",
    "ThrottleCard",
]
