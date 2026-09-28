"""Second round: focused DE in a tight box around the round-1 optimum (Kp=-1.81,Ki=-3.20,Kq=-0.13,
b~0), with smaller buffers now that a good region is known (validate_margins.py already showed the
fast linear-margin method agrees with control.stability_margins to ~0.01 deg/dB, and nlsim.py is not an
approximation of the grader's time-domain recipe but the same recipe, so less safety margin is needed
there than in round 1's first blind global search) -- looking for whether R5 (<=6.0s) is reachable at
20 m/s (worst case, 6.74 s after round 1) without breaking R3 (25 m/s already at 8.0%, i.e. right at
round 1's overshoot buffer) or R4.
"""
import time
import numpy as np
from scipy.optimize import differential_evolution
import joint_search as js

R3_MAX, R4_MAX, R5_MAX = 10.0, 25.0, 6.0
BUF_R3, BUF_R4, BUF_R5 = 1.0, 1.0, 0.15
PM_MIN, GM_MIN_DB = 45.0, 6.0
BUF_PM, BUF_GM = 2.0, 0.75


def linear_ok2(Kp, Ki, Kq):
    return js.linear_ok(Kp, Ki, Kq, buf_pm=BUF_PM, buf_gm=BUF_GM)


def cost2(params):
    Kp, Ki, Kq, b = params
    if not (0.0 <= b <= 1.0):
        return 1e6
    ok, wpm, wgm, min_gc = linear_ok2(Kp, Ki, Kq)
    if not ok:
        return 5000.0 + abs(Kp) + abs(Ki) + abs(Kq)
    r = js.nonlinear_eval(Kp, Ki, Kq, b)
    if r["diverged"]:
        return 3000.0
    penalty = 0.0
    penalty += max(0.0, r["worst_over"] - (R3_MAX - BUF_R3)) * 8.0
    penalty += max(0.0, r["worst_elev"] - (R4_MAX - BUF_R4)) * 8.0
    penalty += max(0.0, r["worst_settle"] - (R5_MAX - BUF_R5)) * 8.0
    if penalty > 1e-9:
        return 100.0 + penalty
    return r["worst_settle"]


if __name__ == "__main__":
    from scipy.optimize import minimize

    t0 = time.time()
    bounds = [(-3.5, -0.3), (-5.5, -1.0), (-1.2, 1.2), (0.0, 0.35)]
    result = differential_evolution(cost2, bounds, seed=5, maxiter=25, popsize=8, tol=1e-10,
                                     mutation=(0.3, 1.4), recombination=0.85, polish=False, workers=1,
                                     init="sobol")
    print("DE elapsed", time.time() - t0)
    print(result)
    Kp, Ki, Kq, b = result.x
    print("best2:", Kp, Ki, Kq, b)
    js.report(Kp, Ki, Kq, b)

    t1 = time.time()
    res2 = minimize(cost2, [Kp, Ki, Kq, b], method="Nelder-Mead", bounds=bounds,
                     options=dict(xatol=1e-5, fatol=1e-7, maxiter=600, maxfev=600, adaptive=True))
    print("polish elapsed", time.time() - t1)
    print(res2)
    Kp2, Ki2, Kq2, b2 = res2.x
    print("polished2:", Kp2, Ki2, Kq2, b2)
    js.report(Kp2, Ki2, Kq2, b2)
