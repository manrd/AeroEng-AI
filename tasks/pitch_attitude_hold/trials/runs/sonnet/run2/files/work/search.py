"""Numerical search for (Kp, Ki, Kq, b) that satisfies R1-R5 with margin, minimizing
settling time. Uses a penalty-based objective with scipy's differential_evolution
(global, gradient-free -- appropriate given saturation nonlinearity and multiple
frequency-response crossings make the feasible region non-smooth).
"""
import sys
import time

import numpy as np
from scipy.optimize import differential_evolution, minimize

import lib

PM_MIN = 46.0
GM_MIN = 6.3
OS_MAX = 9.5
ELEV_MAX = 24.5
TS_MAX = 3.8


def penalty(params):
    Kp, Ki, Kq, b = params
    try:
        r = lib.evaluate(Kp, Ki, Kq, b)
    except Exception:
        return 1e8

    pen = 0.0
    pm = r["phase_margin_deg"]
    pen += max(0.0, PM_MIN - pm) * 10.0
    gminc = r["gain_margin_db"]
    pen += max(0.0, GM_MIN - gminc) * 10.0
    gmdec = r["gain_margin_decrease_db"]
    if gmdec is not None:
        pen += max(0.0, GM_MIN - gmdec) * 10.0
    os_ = r["overshoot_pct"]
    pen += max(0.0, os_ - OS_MAX) * 5.0
    maxe = r["max_elevator_deg"]
    pen += max(0.0, maxe - ELEV_MAX) * 5.0
    ts = r["settling_time_s"]
    pen += max(0.0, ts - TS_MAX) * 20.0

    return pen * 100.0 + ts


def main():
    bounds = [(-10.0, 0.0), (-10.0, 0.0), (-10.0, 0.0), (0.0, 1.0)]
    t0 = time.time()
    res = differential_evolution(
        penalty, bounds, maxiter=80, popsize=15, tol=1e-8, seed=12345,
        workers=-1, updating="deferred", polish=True, disp=True,
    )
    print("DE time:", time.time() - t0)
    print("DE result:", res.x, res.fun)

    # local polish
    res2 = minimize(penalty, res.x, method="Nelder-Mead",
                     options=dict(xatol=1e-6, fatol=1e-8, maxiter=4000, adaptive=True))
    print("polish result:", res2.x, res2.fun)

    Kp, Ki, Kq, b = res2.x
    r = lib.evaluate(Kp, Ki, Kq, b)
    print("Kp,Ki,Kq,b =", Kp, Ki, Kq, b)
    for k in ["phase_margin_deg", "gain_margin_db", "gain_margin_decrease_db",
              "overshoot_pct", "settling_time_s", "max_elevator_deg",
              "max_elevator_actual_deg", "R1_ok", "R2_ok", "R3_ok", "R4_ok", "R5_ok", "all_ok"]:
        print(k, r[k])


if __name__ == "__main__":
    main()
