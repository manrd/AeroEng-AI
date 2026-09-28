import sys
import time
import numpy as np
from scipy.optimize import minimize
sys.path.insert(0, ".")
from evaluate import evaluate, passes

PM_REQ, GM_REQ, OV_REQ, EL_REQ = 45.0, 6.0, 10.0, 25.0
PM_BUF, GM_BUF, OV_BUF, EL_BUF = 2.0, 1.5, 1.0, 1.0


def objective(x):
    Kp, Ki, Kq, b = x
    try:
        out, m, res = evaluate(Kp, Ki, Kq, b)
    except Exception:
        return 1e6
    if not np.all(np.isfinite(res["theta_deg"])) or np.max(np.abs(res["theta_deg"])) > 1e4:
        return 1e6
    pm = out["phase_margin_deg"]; gmu = out["gain_margin_up_db"]; gmd = out["gain_margin_down_db"]
    ov = out["overshoot_pct"]; el = out["max_elevator_deg"]; ts = out["settling_time_s"]
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
        pen += (el - (EL_REQ - EL_BUF)) ** 2 * 4.0
    return ts + 20.0 * pen


if __name__ == "__main__":
    x0 = [-2.572556544123545, -6.361332643262375, -0.1724451428589344, 0.12220729650563046]
    t0 = time.time()
    res = minimize(objective, x0, method="Nelder-Mead",
                    options={"maxiter": 600, "xatol": 1e-6, "fatol": 1e-8, "adaptive": True})
    print("time:", time.time() - t0)
    print(res.x, res.fun, res.success, res.message)
    Kp, Ki, Kq, b = res.x
    out, m, r = evaluate(Kp, Ki, Kq, b, verbose=True)
    ok, reasons = passes(out)
    print("ok", ok, reasons)
