# Onboarding — Lotus Elise Digital Dashboard

This file gets you (or a fresh Kiro session on another machine) up to speed fast,
and walks through connecting the app to the **real car** with a live OBD-II feed.

---

## 1. Paste-this prompt for a fresh Kiro session

> I'm continuing work on an existing project: a PyQt5 + python-obd digital
> dashboard for a Lotus Elise, designed to run fullscreen on a Raspberry Pi 5
> with an 800x480 touchscreen. It uses a strict asynchronous MVC layout:
>
> - **Model** (`dashboard/model.py`): a `QThread` that polls the ECU over an
>   ELM327 USB adapter and *publishes* the latest reading behind a lock (it does
>   NOT emit Qt signals across threads).
> - **Controller** (`dashboard/controller.py`): a `QObject` with a GUI-thread
>   `QTimer` that samples the model snapshot ~30 Hz and emits `pyqtSignal`s.
> - **View** (`dashboard/view.py` + `dashboard/widgets/`): pure `QPainter`
>   vector gauges (coolant bar, RPM tacho + shift-lights, digital MPH).
>
> It runs today in mock mode (`python main.py --mock --windowed`) and all render
> paths are verified. I now have the physical adapter (a Vgate **vLinker FS**,
> genuine FTDI chip) and I want to run it against the real car and get live data.
> Read `Onboarding.md` and `dashboard/config.py` first, then help me connect,
> verify the serial link, and debug live telemetry.
>
> IMPORTANT context so you don't repeat past dead-ends:
> - Do NOT re-architect to emit signals from the worker thread. The publish/poll
>   pattern is deliberate (it avoids a cross-thread refcount crash we already hit).
> - GUI can't be smoke-tested under Qt's `offscreen` platform on a headless box
>   (its raster engine crashes on text/gradients with no font DB). Verify paint
>   code with `QWidget.grab()` into a QImage, not a live event loop.

---

## 2. What this app is

A track-legible instrument cluster:

- **Coolant gauge (left):** vertical "liquid column" bar. Blue < 70 °C,
  green 70–95 °C, amber 95–98 °C, flashing red > 98 °C with a full-screen
  "WARNING: ENGINE OVERHEATING" banner.
- **Tachometer (centre, dominant):** 270° arc, 0–8500 RPM. Green 0–6000,
  amber 6000–7800, flashing red/magenta 7800–8500, plus a 12-LED progressive
  shift-light strip.
- **Speedometer (right):** big digital MPH readout. OBD reports km/h; the
  controller converts with `Speed_mph = Speed_kmh * 0.621371`.

Fullscreen, frameless, cursor hidden in kiosk mode. Falls back to a simulated
engine if no adapter is found, so the UI is never dead.

---

## 3. Tech stack

| Component  | Version (verified) | Notes |
|-----------|--------------------|-------|
| Python     | 3.13 (works 3.9+)  | Pi OS ships 3.11 |
| PyQt5      | 5.15.11            | GUI, QThread, QPainter |
| python-obd | 0.7.3              | ELM327 / OBD-II |
| pyserial   | 3.5                | serial transport (obd dep) |
| pint       | 0.24.4             | units (obd dep) |

See `requirements.txt`.

---

## 4. Repo layout

```
main.py                       # entry point: wires MVC, --mock / --windowed flags
requirements.txt
Onboarding.md                 # this file
dashboard/
├── config.py                 # ALL tunables: colours, thresholds, scales, serial ports
├── telemetry.py              # Telemetry dataclass + ConnectionState enum
├── mock.py                   # simulated engine (fail-safe / dev mode)
├── model.py                  # OBDModel(QThread): serial I/O + dropout recovery
├── controller.py             # DashboardController: GUI-thread poll + signals
├── view.py                   # DashboardWindow + warning overlay + status pill
└── widgets/
    ├── base_gauge.py         # 60 FPS easing, flash timing, card/glow helpers
    ├── coolant_gauge.py
    ├── rpm_gauge.py
    └── speedometer.py
```

---

## 5. Setup on the new laptop

```bash
# from the project root
python -m pip install -r requirements.txt
```

On a Raspberry Pi, prefer the distro PyQt5 and only pip-install obd:
```bash
sudo apt install python3-pyqt5 python3-pyqt5.qtsvg
python3 -m pip install obd pyserial
```

Quick sanity check (no car needed):
```bash
python main.py --mock --windowed      # Windows: python ; Linux/Pi: python3
```
You should see the three gauges animating and a cyan "MOCK MODE" status pill.
`Esc` or `Q` quits.

---

## 6. Connect the real adapter (Vgate vLinker FS)

The vLinker FS uses a **genuine FTDI** chip, so drivers are easy.

### Linux laptop / Raspberry Pi
Plug-and-play — the `ftdi_sio` kernel driver is built in. Verify:
```bash
lsusb                     # look for "Future Technology Devices International"
dmesg | grep -i ftdi      # "...converter now attached to ttyUSB0"
ls -l /dev/ttyUSB*        # expect /dev/ttyUSB0
```
Permissions gotcha: your user must be in the `dialout` group or you'll get
"permission denied":
```bash
sudo usermod -aG dialout $USER   # then log out/in (or reboot)
```

### Windows laptop
It appears as a COM port (e.g. `COM3`). Win 10/11 usually auto-installs the FTDI
VCP driver; if Device Manager shows a warning, install the FTDI VCP driver from
ftdichip.com. Find the port under Device Manager → "Ports (COM & LPT)".

### Verify the link independently (recommended before the GUI)
With the adapter plugged into the car and **ignition on / engine running**:
```bash
python -c "import obd; c=obd.OBD(); print(c.status()); print(c.query(obd.commands.RPM))"
```
A healthy result prints `OBDStatus.CAR_CONNECTED` and a non-null RPM value.

---

## 7. Run with real data

Just omit `--mock`:
```bash
python main.py                 # fullscreen kiosk (Esc/Q to quit)
python main.py --windowed      # normal window, easier on a laptop
```

The model tries to connect in this order: **full auto-scan** (`obd.OBD()` scans
all serial ports + bauds), then the explicit `config.DEFAULT_PORT`
(`/dev/ttyUSB0`) at 38400 then 115200 baud, then any other scanned ports.

Watch the terminal — connection diagnostics are logged there:
```
Opening OBD-II on auto-detect @ auto baud...
Connected on /dev/ttyUSB0.
```
And watch the **status pill** (bottom-left of the window):

| Pill | Meaning |
|------|---------|
| CONNECTING… (amber) | opening the port |
| OBD CONNECTED (green) | live data flowing |
| RECONNECTING… (amber) | link dropped, retrying with back-off |
| MOCK MODE (cyan) | no adapter found → simulated data |

If you see **MOCK MODE**, it did not find/open the adapter — see troubleshooting.

---

## 8. First real-drive checklist

1. Engine running (the ECU won't answer many PIDs with ignition off).
2. Adapter firmly seated in the OBD-II port; USB in the laptop.
3. `python main.py --windowed`, confirm the status pill goes **green**.
4. Idle: RPM ≈ 800–1100, coolant climbs from ambient (blue) toward green.
5. Blip the throttle: tacho arc sweeps, shift-lights fill, colour zones change.
6. Roll forward: speedometer shows MPH (converted from km/h).
7. Missing PID shows as a dim `--` on that gauge rather than a fake zero.

---

## 9. Troubleshooting

**Stuck on MOCK MODE / can't connect**
- Confirm the OS sees the adapter (Linux `ls /dev/ttyUSB*`; Windows Device Manager).
- Linux: are you in `dialout`? (`groups | grep dialout`).
- Windows: auto-scan usually finds the COM port; if not, set the port explicitly
  in `dashboard/config.py` → `DEFAULT_PORT = "COM3"` (use your actual port). The
  auto-scan runs first regardless, so this is only a fallback.
- Engine must be on; some cheap ports are flaky at one baud — the app already
  tries both 38400 and 115200.

**Connects but all gauges show `--`**
- The ECU may not expose those PIDs at idle/ignition-only. Confirm with the
  one-liner in §6. The Elise 2ZZ supports RPM/COOLANT_TEMP/SPEED when running.

**Values look wrong (e.g. RPM maxes out too early)**
- Check the vehicle-specific scales in §10 — the defaults assume a 2ZZ (8500 rpm).

**GUI stutters** — unlikely on a laptop; the render path is decoupled from serial
I/O. If it happens, lower `UI_POLL_HZ` in `config.py`.

---

## 10. Vehicle-specific config (`dashboard/config.py`)

Defaults are tuned for a **Toyota 2ZZ-GE** Elise/Exige (S2). If yours is a
**K-series** (S1 / early S2 111), lower the redline:

```python
RPM_MAX        = 8500.0     # 2ZZ. K-series: ~7200
RPM_GREEN_MAX  = 6000.0     # green→amber
RPM_AMBER_MAX  = 7800.0     # amber→flashing red  (scale down for K-series)

COOLANT_COLD_MAX_C   = 70.0   # < this = blue
COOLANT_OPTIMAL_MAX_C = 95.0  # up to here = green
COOLANT_CRITICAL_C   = 98.0   # above = flashing red + overheat banner

DEFAULT_PORT = "/dev/ttyUSB0" # set to "COM3" etc. on Windows if auto-scan fails
BAUD_RATES   = (38400, 115200)
OBD_POLL_HZ  = 20.0           # ECU query rate
UI_POLL_HZ   = 30.0           # signal-emit / repaint sampling rate
```

Colours and glow intensity are all near the top of `config.py` too.

---

## 11. Architecture notes & gotchas (read before refactoring)

- **Publish/poll, not worker signals.** The model parks its latest `Telemetry`
  snapshot under a `threading.Lock` (`model.snapshot()`), and the controller's
  GUI-thread timer reads it and emits the signals. This keeps *all* signal
  emission on the GUI thread. Emitting `pyqtSignal(object)` rapidly from the
  worker thread caused a non-deterministic native crash on one PyQt5/Python
  combo — don't reintroduce it.
- **Dropout handling** lives in `model._run_obd_loop()`: consecutive failures
  trigger a `RECONNECTING` state and a back-off reconnect loop; a query is
  wrapped so a single flaky PID yields `None` (dim `--`) instead of killing the
  loop.
- **Testing paint code headlessly:** use `widget.grab()` into a QImage/QPixmap
  (register a real font via `QFontDatabase.addApplicationFont` first). Do NOT
  rely on a live event loop under `QT_QPA_PLATFORM=offscreen` — that stub's
  raster engine crashes on text/gradients when no font DB is present. This is a
  test-sandbox artifact, not an app bug; the real display (eglfs/X11) is fine.
- **Pi GPU rendering:** launch with `QT_QPA_PLATFORM=eglfs python3 main.py` to
  render straight on the VideoCore VII without a desktop.

---

## 12. Verification commands

```bash
# syntax check everything
python -m py_compile main.py dashboard/*.py dashboard/widgets/*.py

# run the simulated pipeline (no hardware)
python main.py --mock --windowed
```
