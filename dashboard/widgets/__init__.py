"""
Reusable QPainter gauge widgets for the dashboard View.

Each widget is fully self-contained: it exposes a simple ``set_value()`` slot,
performs its own 60 FPS easing animation, and renders itself with pure vector
graphics (no external image assets) so it stays crisp at any scale and is cheap
for the Raspberry Pi 5 VideoCore VII GPU to composite.
"""

from .coolant_gauge import CoolantGauge
from .mini_readout import MiniReadout
from .rpm_gauge import RPMGauge
from .speedometer import Speedometer
from .throttle_bar import ThrottleBar

__all__ = [
    "CoolantGauge",
    "MiniReadout",
    "RPMGauge",
    "Speedometer",
    "ThrottleBar",
]
