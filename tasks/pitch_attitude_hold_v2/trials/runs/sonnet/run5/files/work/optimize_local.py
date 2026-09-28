import sys
sys.path.insert(0, "<run>/work")
import time
import numpy as np
from scipy.optimize import minimize
from lib import PLANTS, SPEEDS, loop_response, simulate, metrics_from_sim
from margins_fast import analyze_margins

w = np.logspace(-3, 3, 4001)  # fast grid for search; final answer re-verified on full grid separately

PM_FLOOR = 45.0
GM_FLOOR = 6.0
OVER_CAP = 10.0
ELEV_CAP = 25.0
SETTLE_CAP = 6.0

n_eval = 0


def objective(x):
    global n_eval
    n_eval += 1
    Kp, Ki, Kq, b = x
    if b < 0 or b > 1:
        return 200.0 + 10 * (abs(min(b, 0)) + abs(max(b - 1, 0)))
    viol = 0.0
    worst_settle = -1.0
    for spd in SPEEDS:
        pl = PLANTS[spd]
        L = loop_response(pl, w, Kp, Ki, Kq)
        m = analyze_margins(w, L)
        viol += max(0.0, PM_FLOOR - m["worst_pm_deg"])
        viol += max(0.0, GM_FLOOR - m["gm_against_increase_db"]) * 2.0
        if not m["gm_against_decrease_ok"]:
            viol += max(0.0, GM_FLOOR - m["gm_against_decrease_worst_db"]) * 2.0
        sim = simulate(spd, Kp, Ki, Kq, b)
        met = metrics_from_sim(sim)
        if met["diverged"]:
            viol += 50.0
        viol += max(0.0, met["overshoot_pct"] - OVER_CAP) * 3.0
        viol += max(0.0, met["max_elevator_deg"] - ELEV_CAP) * 3.0
        viol += max(0.0, met["settling_time_s"] - SETTLE_CAP) * 3.0
        worst_settle = max(worst_settle, met["settling_time_s"])
    if viol > 1e-9:
        return 100.0 + viol
    return worst_settle


x0 = np.array([-2.0, -4.15, -0.1, 0.1])
t0 = time.time()
res = minimize(objective, x0, method="Nelder-Mead",
               options={"xatol": 2e-3, "fatol": 2e-4, "maxiter": 80, "maxfev": 80,
                        "adaptive": True})
print("time:", time.time() - t0, "n_eval:", n_eval)
print(res)
print("best x:", res.x, "obj:", res.fun)
