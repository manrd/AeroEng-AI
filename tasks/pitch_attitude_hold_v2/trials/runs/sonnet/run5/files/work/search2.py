import sys
sys.path.insert(0, "<run>/work")
import numpy as np
from lib import PLANTS, SPEEDS, loop_response
from margins_fast import analyze_margins

w = np.logspace(-3, 3, 6001)


def freq_margins(Kp, Ki, Kq):
    worst_pm, worst_gm, dec_ok = 999, 999, True
    for spd in SPEEDS:
        pl = PLANTS[spd]
        L = loop_response(pl, w, Kp, Ki, Kq)
        m = analyze_margins(w, L)
        worst_pm = min(worst_pm, m["worst_pm_deg"])
        worst_gm = min(worst_gm, m["gm_against_increase_db"])
        dec_ok = dec_ok and m["gm_against_decrease_ok"]
    return worst_pm, worst_gm, dec_ok


def max_Ki_for(Kp, Kq, pm_floor=46.0, gm_floor=6.3, Ki_lo=-0.5, Ki_hi=-12.0, iters=25):
    """Bisect on |Ki| (Ki negative) to find the most-negative Ki (fastest) that still
    clears pm_floor/gm_floor with a small buffer. Assumes margins degrade monotonically
    as |Ki| grows (checked empirically)."""
    lo, hi = Ki_lo, Ki_hi  # lo passes (small |Ki|), hi may fail
    wp, wg, dec = freq_margins(Kp, hi, Kq)
    if wp >= pm_floor and wg >= gm_floor and dec:
        return hi  # even the extreme passes
    for _ in range(iters):
        mid = (lo + hi) / 2
        wp, wg, dec = freq_margins(Kp, mid, Kq)
        if wp >= pm_floor and wg >= gm_floor and dec:
            lo = mid
        else:
            hi = mid
    return lo


for Kp in [-1.8, -2.0, -2.2, -2.4]:
    for Kq in [-0.05, -0.1, -0.15, -0.2]:
        Ki_max = max_Ki_for(Kp, Kq)
        wp, wg, dec = freq_margins(Kp, Ki_max, Kq)
        print(f"Kp={Kp:5.2f} Kq={Kq:5.2f}  max|Ki| -> Ki={Ki_max:7.3f}  PM={wp:6.1f} GMinc={wg:5.2f} dec_ok={dec}")
