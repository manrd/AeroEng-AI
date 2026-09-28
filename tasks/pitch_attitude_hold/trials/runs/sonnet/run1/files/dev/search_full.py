"""Full nonlinear optimization: minimize settling time subject to margins (linear), overshoot,
and elevator-limit constraints (nonlinear time-domain sim), over Kp,Ki,Kq,b."""
import sys
import time
import numpy as np
from scipy.optimize import differential_evolution
sys.path.insert(0, ".")
from evaluate import evaluate

PM_REQ = 45.0
GM_REQ = 6.0
OV_REQ = 10.0
EL_REQ = 25.0
TS_REQ = 4.0

PM_BUF = 1.0
GM_BUF = 0.5
OV_BUF = 0.5
EL_BUF = 0.5


def objective(x):
    Kp, Ki, Kq, b = x
    try:
        out, m, res = evaluate(Kp, Ki, Kq, b)
    except Exception:
        return 1e6
    if not np.all(np.isfinite(res["theta_deg"])) or np.max(np.abs(res["theta_deg"])) > 1e4:
        return 1e6

    pm = out["phase_margin_deg"]
    gmu = out["gain_margin_up_db"]
    gmd = out["gain_margin_down_db"]
    ov = out["overshoot_pct"]
    el = out["max_elevator_deg"]
    ts = out["settling_time_s"]

    pen = 0.0
    if pm < PM_REQ + PM_BUF:
        pen += (PM_REQ + PM_BUF - pm) ** 2
    if gmu < GM_REQ + GM_BUF:
        pen += (GM_REQ + GM_BUF - gmu) ** 2
    if np.isfinite(gmd) and gmd < GM_REQ + GM_BUF:
        pen += (GM_REQ + GM_BUF - gmd) ** 2
    if ov > OV_REQ - OV_BUF:
        pen += (ov - (OV_REQ - OV_BUF)) ** 2
    if el > EL_REQ - EL_BUF:
        pen += (el - (EL_REQ - EL_BUF)) ** 2 * 4.0  # weight elevator violation heavily (hard req)

    obj = ts + 20.0 * pen
    return obj


if __name__ == "__main__":
    bounds = [(-20, -0.01), (-20, -0.01), (-8, 8), (0.0, 1.0)]
    t0 = time.time()
    result = differential_evolution(objective, bounds, maxiter=60, popsize=15, tol=1e-9,
                                     mutation=(0.3, 1.7), recombination=0.8, seed=1, polish=True)
    print("time:", time.time() - t0)
    print(result)
    Kp, Ki, Kq, b = result.x
    out, m, res = evaluate(Kp, Ki, Kq, b, verbose=True)
    print("Kp,Ki,Kq,b=", Kp, Ki, Kq, b)
