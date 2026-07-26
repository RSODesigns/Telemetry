# Lotus Elise Digital Dashboard (PiTelemetry)

A PyQt5 + python-obd digital instrument cluster for a Lotus Elise (Toyota 2ZZ-GE / K-series), designed to run fullscreen on a Raspberry Pi 5 with an 800x480 touchscreen display.

---

## Quick Start

### Installation

```bash
# Install dependencies
python -m pip install -r requirements.txt
```

On Raspberry Pi OS:
```bash
sudo apt install python3-pyqt5 python3-pyqt5.qtsvg
python3 -m pip install obd pyserial
```

### Running the Dashboard

#### 🏎️ Race-Inspired Track Layout (`--layout track`)
*Dominant central 270° tachometer + progressive shift lights flanked by symmetric engine/drivetrain peripheral cards.*

```bash
# Laptop / Simulated mode (no car needed)
python main.py --mock --windowed --layout track

# Plugged into car (Windowed dev mode)
python main.py --windowed --layout track

# Raspberry Pi (Fullscreen kiosk mode)
python main.py --layout track
```

#### 🚗 General Road Layout (`--layout general`)
*Classic three-gauge view: vertical coolant bar, dominant central tachometer, and digital speedometer.*

```bash
# Laptop / Simulated mode
python main.py --mock --windowed --layout general

# Raspberry Pi (Fullscreen kiosk mode)
python main.py --layout general
```

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
