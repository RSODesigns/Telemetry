"""
config.py
=========

Single source of truth for every tunable value in the dashboard: screen
geometry, the deep-charcoal colour palette, gauge scales, the colour-zone
thresholds described in the UX spec, and the serial-port parameters used to
reach the ELM327 USB adapter.

Keeping these here means the visual behaviour of the car's dashboard can be
re-tuned (e.g. a different redline for a supercharged Elise, or a Fahrenheit
build) without touching any of the rendering or threading logic.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Display / geometry
# ---------------------------------------------------------------------------
# The Waveshare / generic 5" HDMI panels used with the Pi are natively
# 800 x 480. We render at exactly that so there is a 1:1 pixel mapping and no
# GPU scaling blur.
SCREEN_WIDTH: int = 800
SCREEN_HEIGHT: int = 480

# Target frame rate for the smooth needle/arc easing animation. 60 FPS matches
# the panel refresh and the VideoCore VII can composite these vector gauges
# comfortably at that rate. Derived interval is used by the widgets' QTimers.
TARGET_FPS: int = 60
FRAME_INTERVAL_MS: int = max(1, round(1000 / TARGET_FPS))  # ~16 ms

# Rate at which the "flashing" (critical) elements toggle on/off, in ms.
# 200 ms -> 2.5 Hz blink, aggressive enough to grab attention on track.
FLASH_INTERVAL_MS: int = 200

# Rate at which the Controller (on the GUI thread) samples the latest snapshot
# published by the data thread and emits its signals. Decoupling this from the
# raw OBD poll rate means the worker never emits signals across the thread
# boundary - it just parks the newest reading behind a lock and the GUI thread
# pulls it. 30 Hz is ample: the gauges ease between targets at 60 FPS anyway.
UI_POLL_HZ: float = 30.0
UI_POLL_INTERVAL_MS: int = max(1, round(1000 / UI_POLL_HZ))  # ~33 ms

# ---------------------------------------------------------------------------
# Colour palette - "Racing Red / Black / White" instrument theme
# ---------------------------------------------------------------------------
# Deep neutral-black canvas (no colour cast) so the whole panel reads as a
# cockpit instrument, not a consumer infotainment screen.
COLOR_BG_TOP = "#141414"       # vignette centre (neutral black)
COLOR_BG_EDGE = "#080808"      # vignette edges (near pure black)
COLOR_BACKGROUND = "#0b0b0b"   # base flat fill / fallback

# Each gauge sits on an elevated rounded "card" with a hairline border.
# (Used by the General layout; Track layout uses card-free SidePanels.)
COLOR_CARD_TOP = "#191919"     # card fill, top of its gradient
COLOR_CARD_BOTTOM = "#121212"  # card fill, bottom of its gradient
COLOR_CARD_BORDER = "#2c2c2c"  # hairline border around the card
COLOR_CARD_HILITE = "#373737"  # faint top inner highlight line

COLOR_PANEL = "#151515"        # neutral fill (e.g. an unlit shift LED)
COLOR_TRACK = "#222222"        # unfilled portion of an arc/bar

COLOR_TEXT = "#f5f0f0"         # primary readouts (warm white)
COLOR_TEXT_DIM = "#8a7e80"     # labels, units, secondary info
COLOR_TEXT_FAINT = "#5a4e50"   # minor ticks, disabled text

# Semantic / zone colours (racing red dominant, functional differentiation).
COLOR_ACCENT = "#e81820"       # racing red - primary accent / highlight
COLOR_COLD = "#6690b0"         # steel blue - coolant below optimal
COLOR_OPTIMAL = "#ffffff"      # white      - healthy operating band
COLOR_AMBER = "#ff8c00"        # dark orange - caution / upper rev band
COLOR_CRITICAL = "#ff2020"     # bright red  - overheating / redline
COLOR_SHIFT = "#ff0040"        # hot crimson - final shift-light flash

COLOR_OK = "#ffffff"           # connection status: live data (white)
COLOR_WARN = "#ff8c00"         # connection status: reconnecting
COLOR_MOCK = "#e81820"         # connection status: simulated data (red)

# ---------------------------------------------------------------------------
# Glow / depth tuning (soft "bloom" simulated with layered translucent passes)
# ---------------------------------------------------------------------------
GLOW_ALPHA: int = 66           # base alpha (0-255) of the brightest glow pass
GLOW_LAYERS: int = 3           # number of widening translucent passes
CARD_MARGIN: float = 6.0       # inset of the card from the widget edge (px)
CARD_RADIUS: float = 18.0      # corner radius of the gauge cards (px)

# ---------------------------------------------------------------------------
# Coolant temperature gauge (left)
# ---------------------------------------------------------------------------
# Displayed scale of the vertical bar (degrees Celsius). The Elise K-series /
# Toyota 2ZZ runs ~ 80-95C normally; we show a band that makes cold-start and
# overheat both visible.
COOLANT_MIN_C: float = 40.0
COOLANT_MAX_C: float = 120.0

# Colour-zone thresholds (degrees Celsius) straight from the UX spec:
#   below COLD          -> blue   (engine not warmed up)
#   OPTIMAL_LOW..HIGH   -> green  (happy operating temperature)
#   at / above CRITICAL -> flashing red + textual overheat warning
COOLANT_COLD_MAX_C: float = 70.0        # < 70C  => blue
COOLANT_OPTIMAL_MIN_C: float = 70.0     # 70-95C => green
COOLANT_OPTIMAL_MAX_C: float = 95.0
COOLANT_CRITICAL_C: float = 98.0        # > 98C  => flashing red + warning

OVERHEAT_WARNING_TEXT: str = "WARNING: ENGINE OVERHEATING"

# ---------------------------------------------------------------------------
# Track-layout coolant thresholds (--layout track)
# ---------------------------------------------------------------------------
# Track driving keeps the engine hotter than road use; these are the empirical
# operating bands for this specific 2ZZ. The general dashboard's thresholds
# above are unchanged so `--layout general` looks and behaves exactly as it
# does today.
#
#   below COLD                 -> blue    (still warming up, don't push it)
#   COLD..OPTIMAL_MAX          -> green   (normal operating range)
#   OPTIMAL_MAX..CRITICAL      -> amber   ("getting too hot")
#   at / above CRITICAL        -> flashing red + overheat overlay
TRACK_COOLANT_COLD_MAX_C: float = 84.0    # < 84C   => blue
TRACK_COOLANT_OPTIMAL_MAX_C: float = 99.0 # 84-99C  => green
TRACK_COOLANT_CRITICAL_C: float = 105.0   # >=105C  => flashing red

# ---------------------------------------------------------------------------
# Battery / control-module voltage zones (track layout)
# ---------------------------------------------------------------------------
# Alternator charging on a healthy Elise sits around 13.8-14.4V; below ~12.5V
# with the engine running usually means the alternator isn't charging or the
# battery is dying. A gauge reading well above 15V hints at a regulator fault.
BATTERY_LOW_V: float = 12.5              # < 12.5V => red (concerning)
BATTERY_OPTIMAL_MIN_V: float = 13.5      # 13.5..14.5 => green (charging)
BATTERY_OPTIMAL_MAX_V: float = 14.5
BATTERY_HIGH_V: float = 15.5             # > 15.5V => red (overcharging)

# ---------------------------------------------------------------------------
# Intake air temperature thresholds (°C)
# ---------------------------------------------------------------------------
# High intake temperatures reduce air density and cause ignition timing pull /
# loss of power on the 2ZZ.
INTAKE_MIN_C: float = -10.0
INTAKE_MAX_C: float = 90.0
INTAKE_OPTIMAL_MAX_C: float = 45.0       # < 45C => green (good density)
INTAKE_CRITICAL_C: float = 60.0          # 45-60C => amber, >=60C => red (heat soak)

# ---------------------------------------------------------------------------
# Fuel level thresholds (%)
# ---------------------------------------------------------------------------
FUEL_LEVEL_LOW_PCT: float = 15.0         # < 15% => red flashing (low fuel)
FUEL_LEVEL_CAUTION_PCT: float = 30.0     # 15-30% => amber


# ---------------------------------------------------------------------------
# Throttle position (track layout)
# ---------------------------------------------------------------------------
# THROTTLE_POS is reported as a percentage 0-100. On a 2ZZ the idle stop
# reads roughly 12-14%, so we normalise against the actual travel range
# rather than raw sensor reading; ``RELATIVE_THROTTLE_POS`` (0145) would give
# the same information natively but not all ECUs expose it.
THROTTLE_MIN_PCT: float = 0.0
THROTTLE_MAX_PCT: float = 100.0
# Below this the driver hasn't really pressed anything (idle stop). We shift
# the visible bar so it starts filling once the pedal is meaningfully pressed.
THROTTLE_IDLE_STOP_PCT: float = 14.0

# ---------------------------------------------------------------------------
# RPM tachometer (centre, dominant)
# ---------------------------------------------------------------------------
RPM_MIN: float = 0.0
RPM_MAX: float = 8500.0                  # 2ZZ-GE VVTL-i redline territory

# Progressive shift-light / arc colour zones (spec):
#   0    .. 6000  -> solid green
#   6000 .. 7800  -> amber
#   7800 .. 8500  -> flashing red / magenta (shift NOW!)
RPM_GREEN_MAX: float = 6000.0
RPM_AMBER_MAX: float = 7800.0

# 2ZZ VVTL-i cam profile switchover RPM. Below this the ECU is on the mild
# "under-cam" lobe; above it the high-lift lobe engages and the engine makes
# most of its power. Used only by the Track layout, which colours the tacho
# blue below the switch (out of the power band) and green above it (on cam).
TRACK_RPM_CAM_SWITCH: float = 6200.0

# Number of discrete LEDs in the motorsport shift-light strip drawn across the
# top of the tachometer.
SHIFT_LIGHT_COUNT: int = 12

# ---------------------------------------------------------------------------
# Speedometer (right)
# ---------------------------------------------------------------------------
# OBD-II reports vehicle speed in km/h. Convert to MPH for the readout.
#   Speed_mph = Speed_kmh * KMH_TO_MPH
KMH_TO_MPH: float = 0.621371
SPEED_MAX_MPH: float = 160.0             # only used for the decorative arc

# ---------------------------------------------------------------------------
# Serial / OBD-II connection
# ---------------------------------------------------------------------------
# Preferred device node for the wired USB ELM327 adapter on Linux/Raspberry Pi.
# If auto-detection finds nothing we fall back to this explicitly.
#
# On other hosts (macOS dev laptops, Windows) the OS enumerates the same FTDI
# adapter under a different name, e.g. ``/dev/cu.usbserial-XXXXXXXX`` or
# ``COM3``. Rather than baking a host-specific path into this file, allow the
# operator to override the port at launch time:
#
#     PITELEMETRY_PORT=/dev/cu.usbserial-D3BMENLN python3 main.py --windowed
#
# On the Pi the env var is left unset and the historic default is used, so
# production deployment is unchanged.
DEFAULT_PORT: str = os.environ.get("PITELEMETRY_PORT", "/dev/ttyUSB0")

# ELM327 clones commonly enumerate at one of these two baud rates. The model
# thread tries them in order. Override with a comma-separated list, highest-
# priority first, e.g. ``PITELEMETRY_BAUDS=115200,38400``.
_bauds_env = os.environ.get("PITELEMETRY_BAUDS")
BAUD_RATES: tuple[int, ...] = (
    tuple(int(b) for b in _bauds_env.split(",") if b.strip())
    if _bauds_env
    else (38400, 115200)
)

# How hard the data thread polls the ECU. 20 Hz is plenty faster than the ECU
# can refresh RPM and keeps the adapter's command buffer from backing up.
OBD_POLL_HZ: float = 20.0
OBD_POLL_INTERVAL_S: float = 1.0 / OBD_POLL_HZ

# Timeouts / dropout handling.
OBD_CONNECT_TIMEOUT_S: float = 5.0       # per connection attempt
OBD_RECONNECT_DELAY_S: float = 2.0       # wait between reconnect attempts
OBD_MAX_CONSECUTIVE_ERRORS: int = 5      # errors before we flag a dropout

# ---------------------------------------------------------------------------
# Mock / simulation mode
# ---------------------------------------------------------------------------
# When True the model NEVER touches real hardware and always simulates a car.
# Handy for developing the UI on a laptop. Normally left False; the model will
# still auto-fall-back to simulation if no adapter is found.
FORCE_MOCK_MODE: bool = False

# Ambient / starting coolant temperature for the "engine warming up" sim.
MOCK_AMBIENT_TEMP_C: float = 20.0
