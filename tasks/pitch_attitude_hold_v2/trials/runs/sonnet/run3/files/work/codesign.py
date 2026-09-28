"""Time-domain refinement: directly minimize worst-case settling time (nonlinear sim) subject to
margin / overshoot / elevator constraints, starting from a frequency-domain candidate.
"""
import numpy as np
from scipy.optimize import minimize

import freq as fq
import nlsim

SPEEDS = (20, 25, 32)
PLANTS_FQ = {s: fq.load_plant(s) for s in SPEEDS}
TFS = {s: fq.theta_tf(PLANTS_FQ[s]) for s in SPEEDS}
PLANTS_NL = {s: nlsim.load_plant(s) for s in SPEEDS}
PARAMS = nlsim.load_params()

PM_MIN = 45.0
GM_MIN = 6.0
OS_MAX = 10.0
ELEV_MAX = 25.0
# small safety buffers applied during search (not for final reporting)
PM_BUF = 1.0
GM_BUF = 0.4
OS_BUF = 0.5
ELEV_BUF = 0.5

T_SEARCH = 8.0  # truncated horizon for speed during search; final check uses full 20 s


def evaluate_point(Kp, Ki, Kq, b, t_end=T_SEARCH, w=fq.W_GRID_FAST):
    freq_res = {}
    for s in SPEEDS:
        num, den = TFS[s]
        freq_res[s] = fq.evaluate(PLANTS_FQ[s], Kp, Ki, Kq, b, num=num, den=den, w=w)
    time_res = {}
    gains = {"K_p": Kp, "K_i": Ki, "K_q": Kq, "b": b}
    for s in SPEEDS:
        time_res[s] = nlsim.run_nonlinear(PLANTS_NL[s], gains, t_end=t_end, params=PARAMS)
    return freq_res, time_res


def cost(x, t_end=T_SEARCH, verbose=False):
    Kp, Ki, Kq, b = x
    if not (0.0 <= b <= 1.0):
        return 1e6 + 1e4 * (abs(b - 0.5))
    freq_res, time_res = evaluate_point(Kp, Ki, Kq, b, t_end=t_end)
    penalty = 0.0
    worst_settle = 0.0
    details = []
    for s in SPEEDS:
        fr = freq_res[s]
        tr = time_res[s]
        pm = fr["phase_margin_deg"]
        gm = fr["gain_margin_db"]
        penalty += max(0.0, (PM_MIN + PM_BUF) - pm) ** 2 * 5.0
        penalty += max(0.0, (GM_MIN + GM_BUF) - gm) ** 2 * 5.0
        if not fr["decrease_margin_ok"]:
            penalty += 1e4
        if tr["diverged"]:
            penalty += 1e5
        os_pct = tr["overshoot_pct"]
        penalty += max(0.0, os_pct - (OS_MAX - OS_BUF)) ** 2 * 3.0
        elev = tr["max_elevator_deg"]
        penalty += max(0.0, elev - (ELEV_MAX - ELEV_BUF)) ** 2 * 3.0
        st = tr["settling_time_s"]
        worst_settle = max(worst_settle, st)
        details.append((s, pm, gm, os_pct, elev, st))
    if verbose:
        for d in details:
            print(f"    Va={d[0]:>3} PM={d[1]:7.2f} GM={d[2]:6.2f} OS%={d[3]:7.2f} "
                  f"elev={d[4]:6.2f} settle={d[5]:5.2f}")
    return worst_settle + penalty


if __name__ == "__main__":
    import sys
    import json

    # Starting guess: read from a file if given, else a reasonable default.
    if len(sys.argv) > 1:
        x0 = json.loads(sys.argv[1])
    else:
        x0 = [-1.0, -1.5, -1.0, 0.3]

    print("initial point:", x0)
    cost(x0, t_end=T_SEARCH, verbose=True)

    res = minimize(cost, x0, method="Nelder-Mead",
                    options={"maxiter": 4000, "maxfev": 4000, "xatol": 1e-4, "fatol": 1e-5, "adaptive": True})
    print(res)
    print("Final gains: Kp={:.5f} Ki={:.5f} Kq={:.5f} b={:.5f}".format(*res.x))
    cost(res.x, t_end=20.0, verbose=True)
