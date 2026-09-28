import sys
sys.path.insert(0, "<run>/work")
import numpy as np
from lib import PLANTS, SPEEDS, loop_response, simulate, metrics_from_sim
from margins_fast import analyze_margins

w = np.logspace(-3, 3, 6001)


def freq_check(Kp, Ki, Kq):
    worst_pm, worst_gm, dec_ok = 999, 999, True
    for spd in SPEEDS:
        pl = PLANTS[spd]
        L = loop_response(pl, w, Kp, Ki, Kq)
        m = analyze_margins(w, L)
        worst_pm = min(worst_pm, m["worst_pm_deg"])
        worst_gm = min(worst_gm, m["gm_against_increase_db"])
        dec_ok = dec_ok and m["gm_against_decrease_ok"]
    return worst_pm, worst_gm, dec_ok


candidates = []
for Kp in [-1.5, -1.8, -2.0, -2.2]:
    for Ki in [-1.0, -1.5, -2.0, -2.5, -3.0, -4.0]:
        for Kq in [0.0, -0.05, -0.1]:
            wp, wg, dec = freq_check(Kp, Ki, Kq)
            pass_freq = wp >= 46 and wg >= 6.3 and dec  # small buffer above the raw thresholds
            if pass_freq:
                candidates.append((Kp, Ki, Kq, wp, wg))

print(f"{len(candidates)} candidates pass frequency-domain screen (with small buffer)")
for c in candidates:
    print(f"  Kp={c[0]} Ki={c[1]} Kq={c[2]}  PM={c[3]:.1f} GMinc={c[4]:.1f}")
