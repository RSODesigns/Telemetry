"""Quick check that MockEngine's new fields populate. Scratch, safe to delete."""
from dashboard.mock import MockEngine

m = MockEngine()
for i in range(5):
    t = m.update(0.05)
print("last snapshot:", t)
print(f"  rpm         = {t.rpm}")
print(f"  coolant_c   = {t.coolant_c}")
print(f"  speed_kmh   = {t.speed_kmh}")
print(f"  throttle_pct= {t.throttle_pct}")
print(f"  battery_v   = {t.battery_v}")
