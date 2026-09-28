"""How sensitive are the pass/fail margins to small perturbations of the chosen gains?
This is a due-diligence check, not a search: it perturbs each gain by +/-1% and +/-3% one
at a time and reports the worst R2/R3/R5 numbers, to see how "sharp" the feasible region is
around the chosen operating point.
"""
import sys
sys.path.insert(0, "<run>/work")
import numpy as np
from lib import PLANTS, SPEEDS, loop_response, simulate, metrics_from_sim
from margins_fast import analyze_margins

w = np.logspace(-3, 3, 6001)
base = {"Kp": -2.0, "Ki": -4.15, "Kq": -0.1, "b": 0.1}


def worst_metrics(Kp, Ki, Kq, b):
    worst_pm, worst_gm = 999, 999
    dec_ok_all = True
    worst_over, worst_settle, worst_elev = -1, -1, -1
    for spd in SPEEDS:
        pl = PLANTS[spd]
        m = analyze_margins(w, loop_response(pl, w, Kp, Ki, Kq))
        worst_pm = min(worst_pm, m["worst_pm_deg"])
        worst_gm = min(worst_gm, m["gm_against_increase_db"])
        dec_ok_all = dec_ok_all and m["gm_against_decrease_ok"]
        met = metrics_from_sim(simulate(spd, Kp, Ki, Kq, b))
        worst_over = max(worst_over, met["overshoot_pct"])
        worst_settle = max(worst_settle, met["settling_time_s"])
        worst_elev = max(worst_elev, met["max_elevator_deg"])
    return worst_pm, worst_gm, dec_ok_all, worst_over, worst_settle, worst_elev


print("baseline:", worst_metrics(**base))
for key in ["Kp", "Ki", "Kq", "b"]:
    for pct in [-0.03, -0.01, 0.01, 0.03]:
        p = dict(base)
        p[key] = base[key] * (1 + pct)
        wpm, wgm, dec, wov, wst, wel = worst_metrics(**p)
        ok = wpm >= 45 and wgm >= 6 and dec and wov <= 10 and wel <= 25 and wst <= 6
        print(f"{key} {pct:+.0%}: PM={wpm:6.2f} GM={wgm:5.2f}dB dec_ok={dec} over={wov:5.2f}% "
              f"settle={wst:5.3f}s elev={wel:5.2f}deg  {'OK' if ok else 'FAIL'}")
