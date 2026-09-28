import sys
sys.path.insert(0, "<run>/work")
import numpy as np
from lib import PLANTS, SPEEDS, loop_response
from margins_fast import analyze_margins

w = np.logspace(-3, 3, 8001)


def summarize(Kp, Ki, Kq):
    worst_pm, worst_gm, dec_ok = 999, 999, True
    gcs = {}
    pcs = {}
    for spd in SPEEDS:
        pl = PLANTS[spd]
        L = loop_response(pl, w, Kp, Ki, Kq)
        m = analyze_margins(w, L)
        worst_pm = min(worst_pm, m["worst_pm_deg"])
        worst_gm = min(worst_gm, m["gm_against_increase_db"])
        dec_ok = dec_ok and m["gm_against_decrease_ok"]
        gcs[spd] = m["gc_w"]
        pcs[spd] = list(zip(m["pc_w"], m["pc_gain_db"]))
    return worst_pm, worst_gm, dec_ok, gcs, pcs


Kp, Ki = -1.5, -0.625
print(f"Baseline Kp={Kp} Ki={Ki}, scanning Kq:")
for Kq in [0, -0.02, -0.05, -0.1, -0.2, -0.3, -0.5, -0.8, -1.2]:
    wp, wg, dec, gcs, pcs = summarize(Kp, Ki, Kq)
    print(f" Kq={Kq:6.2f}  worst_PM={wp:6.1f}  worst_GMinc={wg:6.1f}dB dec_ok={dec}  gc20={gcs[20]}")

print()
print("Now scan Kp with Kq=-0.15 fixed, Ki = -|Kp|*0.4 (rough corner keep):")
for Kp in [-1.5, -1.8, -2.0, -2.3, -2.6, -3.0]:
    Ki = Kp * 0.4
    for Kq in [-0.1, -0.2, -0.3, -0.5]:
        wp, wg, dec, gcs, pcs = summarize(Kp, Ki, Kq)
        flag = "OK" if wp >= 45 and wg >= 6 and dec else "--"
        print(f" Kp={Kp:5.2f} Ki={Ki:6.3f} Kq={Kq:5.2f}  worst_PM={wp:6.1f} worst_GMinc={wg:6.1f}dB dec_ok={dec}  {flag}")
    print()
