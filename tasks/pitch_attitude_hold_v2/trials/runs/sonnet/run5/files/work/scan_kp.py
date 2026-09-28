import sys
sys.path.insert(0, "<run>/work")
import numpy as np
from lib import PLANTS, SPEEDS, loop_response
from margins_fast import analyze_margins

w = np.logspace(-3, 3, 8001)

for Kp in [-0.5, -1, -1.5, -2, -3, -4, -6, -8]:
    print(f"Kp={Kp} Ki=0 Kq=0")
    for spd in SPEEDS:
        pl = PLANTS[spd]
        L = loop_response(pl, w, Kp, 0.0, 0.0)
        m = analyze_margins(w, L)
        gc = m["gc_w"]
        print(f"  {spd}m/s: gain_crossovers(w)={np.array2string(gc, precision=3)}  "
              f"PM={m['worst_pm_deg']:.1f}deg  GMinc={m['gm_against_increase_db']:.1f}dB "
              f"GMdec_ok={m['gm_against_decrease_ok']}")
