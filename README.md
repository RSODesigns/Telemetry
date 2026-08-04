# Lotus Elise Digital Dashboard (PiTelemetry)

A PyQt5 + python-obd digital instrument cluster for a Lotus Elise (Toyota 2ZZ-GE / K-series), designed to run fullscreen on a Raspberry Pi 5 with an 800x480 touchscreen display.

---

## Quick Start

### Installation

```bash
# Install dependencies
python3 -m pip install -r requirements.txt
```

> **Note:** use `python3`, not `python`. macOS (and most modern Linux distros)
> ship no bare `python` alias, so `python main.py` fails with
> `zsh: command not found: python`.

On Raspberry Pi OS:
```bash
sudo apt install python3-pyqt5 python3-pyqt5.qtsvg
python3 -m pip install obd pyserial
```

### Running the Dashboard

#### 🏠 Welcome Screen (default)
*Displays the RSO Designs logo with Road and Track pill buttons to choose your layout.*

```bash
# Laptop / Simulated mode (no car needed)
python3 main.py --mock --windowed

# Raspberry Pi (Fullscreen kiosk mode)
python3 main.py
```

#### 🏎️ Race-Inspired Track Layout (`--layout track`)
*Skips the welcome screen. Dominant central 270° tachometer + progressive shift lights flanked by symmetric engine/drivetrain peripheral cards.*

```bash
# Laptop / Simulated mode (no car needed)
python3 main.py --mock --windowed --layout track

# Plugged into car (Windowed dev mode)
python3 main.py --windowed --layout track

# Raspberry Pi (Fullscreen kiosk mode)
python3 main.py --layout track
```

#### 🚗 General Road Layout (`--layout general`)
*Skips the welcome screen. Classic three-gauge view: vertical coolant bar, dominant central tachometer, and digital speedometer.*

```bash
# Laptop / Simulated mode
python3 main.py --mock --windowed --layout general

# Raspberry Pi (Fullscreen kiosk mode)
python3 main.py --layout general
```

---

## Connecting to the Real Car

### Serial port

The default port is `/dev/ttyUSB0`, which is correct on the Raspberry Pi. **On
macOS and Windows the same adapter enumerates under a different name**, so you
must tell the app where it lives via `PITELEMETRY_PORT`.

Find your port:

```bash
# macOS - the FTDI adapter shows up as /dev/cu.usbserial-XXXXXXXX
ls /dev/cu.*

# Linux
ls /dev/ttyUSB* /dev/ttyACM*
```

Then launch with it set:

```bash
PITELEMETRY_PORT=/dev/cu.usbserial-D3BMENLN python3 main.py --windowed
```

The variable only applies to the command it prefixes. To avoid re-typing it on
every relaunch, export it once per terminal session:

```bash
export PITELEMETRY_PORT=/dev/cu.usbserial-D3BMENLN
python3 main.py --windowed          # picks it up automatically
```

Baud rates can be overridden the same way (rarely needed - the app negotiates
automatically first):

```bash
PITELEMETRY_BAUDS=115200,38400 python3 main.py --windowed
```

### Pre-drive checklist

* **Engine running.** Ignition-only leaves the ECU asleep and most PIDs
  unanswered - python-obd reports `Adapter connected, but the ignition is off`.
* Adapter seated in the OBD-II port, USB connected.
* Watch the status pill (bottom-left): amber `CONNECTING…` → green
  `OBD CONNECTED`. Cyan `MOCK MODE` means no adapter was found.
* A gauge showing a dim `--` means that PID isn't answering - not a real zero.

### Quick connection sanity check

Faster to debug in isolation than through the full GUI:

```bash
python3 -c "import obd; c=obd.OBD('/dev/cu.usbserial-D3BMENLN'); print(c.status()); print(c.query(obd.commands.RPM))"
```

Expect `Car Connected` and a live RPM value.

---

## Troubleshooting

| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| `zsh: command not found: python` | No bare `python` alias on this OS | Use `python3` |
| `could not open port /dev/ttyUSB0: No such file or directory` | Linux-only device name; you're on macOS/Windows | Set `PITELEMETRY_PORT` (see above) |
| Hangs ~30s on `/dev/tty.debug-console`, repeating `Failed to read port` | `PITELEMETRY_PORT` unset, so python-obd's auto-scan fell through to Apple's internal debug console | Set `PITELEMETRY_PORT` |
| Worked once, then failed on the next command | `VAR=x cmd` only scopes to that one command | `export PITELEMETRY_PORT=…` for the session |
| `Adapter connected, but the ignition is off` | ECU asleep | Start the engine, then relaunch |
| `Failed to read port` at a forced baud rate | Some ELM327 clones (e.g. Vgate vLinker FS) need python-obd's own baud negotiation | Already handled - the app tries auto-baud on the known port first, then forced rates |

### Latency notes

This car negotiates **ISO 9141-2 (K-line)** - a slow, single-wire, half-duplex
bus. The ELM327 cannot pipeline requests, so **every PID is a blocking
round-trip** and the only lever on responsiveness is asking for less.

The model therefore:

* queries **only the PIDs the active layout actually renders**, and
* splits those into *fast* fields (RPM, speed, throttle - re-read every poll)
  and *slow* fields (temperatures, battery, fuel - re-read one per poll in
  rotation, since they can't meaningfully change between frames).

Net effect: General drops from 9 to 3 round-trips per poll, Track from 7 to 4,
and needle response no longer waits on slow gauges. If you add a gauge to a
layout, add its `Telemetry` field name to that layout's `needed_fields` set in
`main.py` or it will never populate.

---

## Layout Options & Telemetry PIDs

| Layout | Focus | Monitored Parameters |
| :--- | :--- | :--- |
| **Track** (`--layout track`) | Motorsport / Track Day | **Center**: 0-8500 RPM Tacho + 12-LED Shift Lights<br>**Left Panel**: Coolant Temp (°C), Intake Air Temp (°C), Fuel Level (%)<br>**Right Panel**: Battery Voltage (V), Digital Speed (MPH), Relative Throttle Effort (%) |
| **General** (`--layout general`) | Daily Road Use | **Left**: Coolant Temp Bar<br>**Center**: 0-8500 RPM Tacho + Shift Lights<br>**Right**: Digital Speedometer (MPH) |

---

## Controls & Keyboard Shortcuts

* **Quit Application**: Press `Esc` or `Q`.
* **Kiosk Mode**: Mouse cursor is automatically hidden in non-windowed mode.
