import sys
sys.path.insert(0, "<run>/work")
import numpy as np
from lib import PLANTS, SPEEDS, loop_response
from margins_fast import analyze_margins

w = np.logspace(-3, 3, 8001)


def margins_all(Kp, Ki, Kq):
    out = {}
    for spd in SPEEDS:
        pl = PLANTS[spd]
        L = loop_response(pl, w, Kp, Ki, Kq)
        m = analyze_margins(w, L)
        out[spd] = m
    return out


for Kp in [-1.5, -1.8, -2.0, -2.2, -2.5, -2.8]:
    for wi_ratio in [4, 6, 8, 12]:  # integrator corner = |Kp/Ki| roughly at w_c/wi_ratio using a rough w_c guess
        w_c_guess = 2.5  # ballpark from the P-only scan
        Ki = Kp / wi_ratio * w_c_guess / 1.0 * -1  # placeholder, fix sign below
        Ki = -abs(Kp) * (w_c_guess / wi_ratio)  # Ki negative like Kp, magnitude such that |Ki/Kp| = w_c/wi_ratio
        out = margins_all(Kp, Ki, 0.0)
        worst_pm = min(out[s]["worst_pm_deg"] for s in SPEEDS)
        worst_gm = min(out[s]["gm_against_increase_db"] for s in SPEEDS)
        all_dec_ok = all(out[s]["gm_against_decrease_ok"] for s in SPEEDS)
        gcs = {s: out[s]["gc_w"].tolist() for s in SPEEDS}
        flag = "OK" if (worst_pm >= 45 and worst_gm >= 6 and all_dec_ok) else "--"
        print(f"Kp={Kp:6.2f} Ki={Ki:7.3f} (wi~{abs(Ki/Kp):.3f})  worst_PM={worst_pm:6.1f}deg "
              f"worst_GMinc={worst_gm:6.1f}dB dec_ok={all_dec_ok}  {flag}  gc={gcs}")
    print()
