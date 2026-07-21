# 2ZZ Elise — Supported OBD-II PIDs

Snapshot of the 62 OBD-II commands the ECU responded to when the PiTelemetry app
was first hooked up to the car on 2026-07-21.

- Adapter: Vgate vLinker FS (FTDI FT230X, VID:PID `0403:6015`)
- Protocol: ISO 9141-2 (K-line)
- Baud: 115200
- Engine state during capture: warm idle, ~945 rpm, 25 s run time, no DTCs set

Regenerate this list any time with `python3 scratch_pid_dump.py` from the
project root (engine must be running for the ECU to answer PID probes).

## Mode 01 — live data (28 PIDs)

| PID  | Name                    | Description                        | Example at capture               |
|------|-------------------------|------------------------------------|----------------------------------|
| 0100 | PIDS_A                  | Supported PIDs [01-20] bitmask     | `11111110000111111011100000010011` |
| 0101 | STATUS                  | Status since DTCs cleared          | (composite object)               |
| 0102 | FREEZE_DTC              | DTC that triggered the freeze frame| `P0000` (none set)               |
| 0103 | FUEL_STATUS             | Fuel system status                 | Closed loop, O2 feedback         |
| 0104 | ENGINE_LOAD             | Calculated engine load             | 20 %                             |
| 0105 | COOLANT_TEMP            | Engine coolant temperature         | 75 °C                            |
| 0106 | SHORT_FUEL_TRIM_1       | Short-term fuel trim, bank 1       | +15.6 %                          |
| 0107 | LONG_FUEL_TRIM_1        | Long-term fuel trim, bank 1        | 0 %                              |
| 010C | RPM                     | Engine RPM                         | 943.5 rpm                        |
| 010D | SPEED                   | Vehicle speed                      | 0 km/h                           |
| 010E | TIMING_ADVANCE          | Ignition timing advance            | 2°                               |
| 010F | INTAKE_TEMP             | Intake air temperature             | 38 °C                            |
| 0110 | MAF                     | Mass air flow rate                 | 2.75 g/s                         |
| 0111 | THROTTLE_POS            | Throttle position (absolute)       | 12.2 %                           |
| 0113 | O2_SENSORS              | O2 sensors present bitmask         | B1: S1 + S2 present              |
| 0114 | O2_B1S1                 | O2 bank 1 sensor 1 voltage         | 0.72 V                           |
| 0115 | O2_B1S2                 | O2 bank 1 sensor 2 voltage         | 0.635 V                          |
| 011C | OBD_COMPLIANCE          | OBD standards compliance           | EOBD (Europe)                    |
| 011F | RUN_TIME                | Engine run time since start        | 25 s                             |
| 0120 | PIDS_B                  | Supported PIDs [21-40] bitmask     | `10000000000001100010000000000001` |
| 0121 | DISTANCE_W_MIL          | Distance travelled with MIL on     | 0 km                             |
| 012E | EVAPORATIVE_PURGE       | Commanded evaporative purge        | 0 %                              |
| 012F | FUEL_LEVEL              | Fuel level input                   | 23.1 %                           |
| 0133 | BAROMETRIC_PRESSURE     | Barometric pressure                | 101 kPa                          |
| 0140 | PIDS_C                  | Supported PIDs [41-60] bitmask     | `01101000000000000000000000000000` |
| 0142 | CONTROL_MODULE_VOLTAGE  | Control module voltage             | 14.27 V                          |
| 0143 | ABSOLUTE_LOAD           | Absolute load value                | 12.5 %                           |
| 0145 | RELATIVE_THROTTLE_POS   | Relative throttle position         | 0 %                              |

## Mode 02 — freeze frame (27 PIDs, all mirrors of the above)

Each mode-01 PID has a matching mode-02 form (`DTC_STATUS`, `DTC_FUEL_STATUS`,
`DTC_ENGINE_LOAD` and so on) that returns the value captured at the moment a
Diagnostic Trouble Code was set. All returned `null` at capture because no DTCs
are currently stored on this car.

## Mode 03 / 04 / 07 — DTC operations (3 commands)

| Cmd | Name             | Purpose                                                        |
|-----|------------------|----------------------------------------------------------------|
| 03  | GET_DTC          | Read stored DTCs. Returned `[]` — no faults.                   |
| 04  | CLEAR_DTC        | Clear DTCs and freeze-frame data. Destructive; not used yet.   |
| 07  | GET_CURRENT_DTC  | DTCs from the current/last drive cycle. Returned `[]`.         |

## Mode 06 — on-board monitoring test results (1 PID)

| PID  | Name    | Notes                                                        |
|------|---------|--------------------------------------------------------------|
| 0600 | MIDS_A  | Supported monitor IDs [01-20]. Empty — no mode-06 monitors.  |

## Mode 09 — vehicle information (1 PID)

| PID  | Name     | Bitmask                                                     |
|------|----------|-------------------------------------------------------------|
| 0900 | PIDS_9A  | Supported mode-09 PIDs [01-20]: `0000000100110000000000000000000000000000` |

The bitmask says at least one mode-09 PID is exposed. VIN (`0902`) and calibration
identifiers may respond if queried explicitly.

## Adapter-level AT commands (2)

| Cmd  | Name         | Value at capture                                |
|------|--------------|-------------------------------------------------|
| ATI  | ELM_VERSION  | ELM327 v2.3                                     |
| ATRV | ELM_VOLTAGE  | 13.9 V (measured at the OBD port)               |

## Not currently used by the dashboard

The dashboard plots 3 of the 28 mode-01 PIDs (`RPM`, `COOLANT_TEMP`, `SPEED`).
Good candidates to add next, in order of driver usefulness:

1. `THROTTLE_POS` — driver feedback, pairs naturally with the tacho.
2. `CONTROL_MODULE_VOLTAGE` / `ELM_VOLTAGE` — battery / charging health.
3. `INTAKE_TEMP` — matters for making power on the 2ZZ.
4. `ENGINE_LOAD` — one-glance "how hard is it working".
5. `FUEL_LEVEL` — coarse (1 byte, 0–100 %) but practical.

## Gotchas learned during the first live run

- The 2ZZ ECU sleeps within a couple of minutes of ignition-on if the engine
  never fires. Once asleep, python-obd reports **"Adapter connected, but the
  ignition is off"** even with the key still turned. Cranking the engine wakes
  it back up.
- python-obd's auto-scan (`obd.OBD()` with no port) can leave the adapter or
  the K-line session in a state that breaks the *next* connection attempt.
  The model now tries `config.DEFAULT_PORT` first when it exists on disk,
  falling back to auto-scan only if that fails.
- On macOS the FTDI enumerates as `/dev/cu.usbserial-<serial>`, which is why
  `config.DEFAULT_PORT` can be overridden per-host via the `PITELEMETRY_PORT`
  environment variable.
