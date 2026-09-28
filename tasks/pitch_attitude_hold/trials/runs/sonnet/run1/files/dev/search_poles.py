import sys
import time
import numpy as np
from scipy.optimize import differential_evolution
sys.path.insert(0, ".")
from poles import eigs
from model import (load_plant, plant_freq_response, default_w_grid, loop_gain, margins_from_L)

A, B, C, D, trim = load_plant()
W = default_w_grid()
_Y = plant_freq_response(A, B, C, W)
PTHETA_JW = _Y[:, 0]
PQ_JW = _Y[:, 1]


def max_re_pole(Kp, Ki, Kq):
    ev = eigs(Kp, Ki, Kq)
    return float(np.max(ev.real))


def margins(Kp, Ki, Kq):
    L = loop_gain(W, Kp, Ki, Kq, PTHETA_JW, PQ_JW)
    return margins_from_L(W, L)


def penalty(Kp, Ki, Kq, pm_req=45.0, gm_req=6.0):
    maxre = max_re_pole(Kp, Ki, Kq)
    if maxre >= 0:
        # unstable: heavy penalty proportional to how unstable, skip margins (meaningless)
        return 1000.0 + 1000.0 * maxre, maxre, None
    m = margins(Kp, Ki, Kq)
    pm = m["worst_phase_margin_deg"]
    gmu = m["worst_gain_margin_up_db"]
    gmd = m["worst_gain_margin_down_db"]
    pen = 0.0
    if pm < pm_req:
        pen += (pm_req - pm) ** 2
    if gmu < gm_req:
        pen += (gm_req - gmu) ** 2
    if gmd < gm_req:
        pen += (gm_req - gmd) ** 2
    obj = maxre + 50.0 * pen  # want maxre very negative; penalty pushes away from infeasible
    return obj, maxre, m


def objective(x):
    Kp, Ki, Kq = x
    obj, maxre, m = penalty(Kp, Ki, Kq)
    return obj


if __name__ == "__main__":
    bounds = [(-60, -0.01), (-60, -0.01), (-30, 30)]
    t0 = time.time()
    result = differential_evolution(objective, bounds, maxiter=200, popsize=25, tol=1e-10,
                                     mutation=(0.3, 1.7), recombination=0.8, seed=42, polish=True,
                                     workers=-1)
    print("time:", time.time() - t0)
    print(result)
    Kp, Ki, Kq = result.x
    obj, maxre, m = penalty(Kp, Ki, Kq)
    print("Kp,Ki,Kq=", Kp, Ki, Kq)
    print("max_re_pole=", maxre)
    if m:
        print("PM=", m["worst_phase_margin_deg"], "GMup=", m["worst_gain_margin_up_db"],
              "GMdown=", m["worst_gain_margin_down_db"], "n_gc=", m["n_gain_crossovers"],
              "n_pc=", m["n_phase_crossovers"])
