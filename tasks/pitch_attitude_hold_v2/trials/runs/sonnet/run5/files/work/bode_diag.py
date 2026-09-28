import sys
sys.path.insert(0, "<run>/work")
import numpy as np
from lib import PLANTS, SPEEDS, TAU_ACT, DELAY_S

ws = np.array([0.3, 0.5, 0.7, 1, 1.5, 2, 3, 4, 5, 7, 10, 15, 20, 30])
for spd in SPEEDS:
    pl = PLANTS[spd]
    s = 1j * ws
    Act = 1.0 / (1.0 + TAU_ACT * s)
    Delay = np.exp(-DELAY_S * s)
    Pth = pl.P_theta(s)
    G = Act * Delay * Pth
    print(f"--- {spd} m/s: G(s)=Act*Delay*Ptheta (pure gain Kp=1) ---")
    for wi, gi in zip(ws, G):
        print(f"  w={wi:6.2f}  |G|={np.abs(gi):9.4f}  ({20*np.log10(np.abs(gi)):7.2f} dB)  "
              f"phase={np.degrees(np.angle(gi)):8.2f} deg")
    print()
