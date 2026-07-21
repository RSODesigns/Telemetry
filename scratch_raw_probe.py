"""
Raw serial poke at the vLinker FS.

Bypasses python-obd entirely. Sends ATZ (reset) and ATI (identify) at each
candidate baud rate and prints any bytes that come back. If the ELM327 is
alive at that baud, we'll see the version banner (something like
'ELM327 v2.2' or 'STN2120' for the vLinker firmware).
"""
import time
import serial

PORT = "/dev/cu.usbserial-D3BMENLN"

def poke(baud: int) -> None:
    print(f"\n--- {baud} baud ---")
    try:
        s = serial.Serial(PORT, baudrate=baud, timeout=1)
    except Exception as e:
        print(f"  open failed: {e!r}")
        return
    try:
        # Drain any junk in the OS buffer, then reset the ELM327.
        s.reset_input_buffer()
        s.reset_output_buffer()
        s.write(b"ATZ\r")
        time.sleep(1.2)                      # ATZ needs ~1s to reboot the chip
        data = s.read(256)
        print(f"  after ATZ ({len(data)}B): {data!r}")

        s.reset_input_buffer()
        s.write(b"ATI\r")
        time.sleep(0.3)
        data = s.read(128)
        print(f"  after ATI ({len(data)}B): {data!r}")
    finally:
        s.close()

for baud in (38400, 115200, 9600, 57600):
    poke(baud)
