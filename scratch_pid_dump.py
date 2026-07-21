"""
Dump every OBD-II PID the ECU actually supports, plus a live value where one
is available. Purely diagnostic - scratch file, safe to delete.

Notes:
- python-obd groups commands into modes (mode 01 = live data, mode 09 = vehicle
  info like VIN, etc.). ``connection.supported_commands`` is the union across
  all modes for this ECU.
- Each query is one round-trip to the ELM327 and then to the ECU over K-line
  (ISO 9141-2), so a full sweep of 60-ish PIDs on this car takes ~15-20s.
"""
from __future__ import annotations

import time

import obd

PORT = "/dev/cu.usbserial-D3BMENLN"
BAUD = 115200

print(f"Opening {PORT} @ {BAUD} ...")
connection = obd.OBD(portstr=PORT, baudrate=BAUD, fast=False, timeout=3)

if not connection.is_connected():
    print("Not connected. Status:", connection.status())
    raise SystemExit(1)

print(f"Protocol : {connection.protocol_name()}")
print(f"Supported: {len(connection.supported_commands)} commands\n")

# Sort by mode + PID for readable output.
def sort_key(cmd):
    return (cmd.command or b"").decode(errors="ignore")

def fmt_value(response) -> str:
    if response is None or response.is_null() or response.value is None:
        return "-"
    v = response.value
    # Pint quantities pretty-print with units; plain values just str().
    return str(v)

start = time.monotonic()
rows = []
for cmd in sorted(connection.supported_commands, key=sort_key):
    pid = (cmd.command or b"").decode(errors="ignore")
    try:
        r = connection.query(cmd, force=True)
        val = fmt_value(r)
    except Exception as e:
        val = f"error: {e!r}"
    rows.append((pid, cmd.name, cmd.desc, val))

elapsed = time.monotonic() - start
connection.close()

# Print aligned.
name_w = max(len(r[1]) for r in rows)
pid_w  = max(len(r[0]) for r in rows)
print(f"{'PID':<{pid_w}}  {'NAME':<{name_w}}  VALUE  |  description")
print("-" * (pid_w + name_w + 60))
for pid, name, desc, val in rows:
    print(f"{pid:<{pid_w}}  {name:<{name_w}}  {val}  |  {desc}")

print(f"\nSwept {len(rows)} PIDs in {elapsed:.1f}s")
