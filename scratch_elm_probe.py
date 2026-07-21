"""
Lightweight ELM327 handshake probe (scratch file, safe to delete).

Opens the vLinker FS directly at 38400 baud with fast=False so python-obd
runs the full initialisation sequence, and prints the resulting OBDStatus.

With ignition OFF we expect at best ELM_CONNECTED (the adapter talks to us
over serial, but the ECU is asleep so no CAR_CONNECTED). If we see
OBD_CONNECTED or CAR_CONNECTED, even better.
"""
import logging
import obd

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
                    datefmt="%H:%M:%S")

PORT = "/dev/cu.usbserial-D3BMENLN"
BAUD = 115200  # confirmed by raw probe: vLinker FS on this cable is 115200

print(f"Opening {PORT} @ {BAUD} ...")
connection = obd.OBD(portstr=PORT, baudrate=BAUD, fast=False, timeout=3)

print(f"status()          = {connection.status()}")
print(f"is_connected()    = {connection.is_connected()}")
print(f"port_name()       = {connection.port_name()}")
print(f"protocol_name()   = {connection.protocol_name()}")
print(f"supported cmds N  = {len(connection.supported_commands)}")

try:
    r = connection.query(obd.commands.ELM_VERSION)
    print(f"ELM_VERSION       = {r.value if r else 'None'}")
except Exception as e:
    print(f"ELM_VERSION query raised: {e!r}")

try:
    r = connection.query(obd.commands.RPM)
    if r and not r.is_null():
        print(f"RPM               = {r.value}")
    else:
        print("RPM               = None (expected with ignition off)")
except Exception as e:
    print(f"RPM query raised: {e!r}")

connection.close()
print("closed")
