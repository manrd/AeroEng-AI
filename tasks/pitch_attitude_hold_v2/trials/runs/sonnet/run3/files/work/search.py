"""Search for Kp, Ki, Kq (b fixed at 0.5 for now) that satisfy margins at all three speeds,
maximizing the worst-case (lowest) gain-crossover frequency as a fast proxy for closed-loop speed.
"""
import numpy as np
from scipy.optimize import differential_evolution

import freq as fq

SPEEDS = (20, 25, 32)
PLANTS = {s: fq.load_plant(s) for s in SPEEDS}
TFS = {s: fq.theta_tf(PLANTS[s]) for s in SPEEDS}

PM_TARGET = 45.5
GM_TARGET = 6.3


def eval_all(Kp, Ki, Kq, b=0.5, w=fq.W_GRID_FAST):
    out = {}
    for s in SPEEDS:
        num, den = TFS[s]
        out[s] = fq.evaluate(PLANTS[s], Kp, Ki, Kq, b, num=num, den=den, w=w)
    return out


def cost(x):
    Kp, Ki, Kq = x
    res = eval_all(Kp, Ki, Kq)
    penalty = 0.0
    worst_wc = np.inf
    for s in SPEEDS:
        r = res[s]
        pm = r["phase_margin_deg"]
        gm = r["gain_margin_db"]
        gc = r["gain_crossovers"]
        penalty += max(0.0, PM_TARGET - pm) * 10.0
        penalty += max(0.0, GM_TARGET - gm) * 5.0
        if not r["decrease_margin_ok"]:
            penalty += 1000.0 + max(r["decrease_margins_db"], default=0) ** 2 if r["decrease_margins_db"] else 1000.0
        if not gc:
            penalty += 1000.0
            continue
        wc_main = min(gc, key=lambda t: t[1])[0]
        worst_wc = min(worst_wc, wc_main)
    if not np.isfinite(worst_wc):
        worst_wc = 0.0
    return -worst_wc + penalty * 100.0


if __name__ == "__main__":
    bounds = [(-60, -0.01), (-60, -0.01), (-60, -0.01)]
    result = differential_evolution(cost, bounds, seed=0, maxiter=300, popsize=25, tol=1e-10,
                                     mutation=(0.3, 1.5), recombination=0.7, polish=True, workers=-1)
    print(result)
    Kp, Ki, Kq = result.x
    print("Kp,Ki,Kq =", Kp, Ki, Kq)
    res = eval_all(Kp, Ki, Kq, w=fq.W_GRID)
    for s in SPEEDS:
        r = res[s]
        print(s, "PM", r["phase_margin_deg"], "GM", r["gain_margin_db"], "dec_ok",
              r["decrease_margin_ok"], "n_gc", r["n_gain_cross"], "gc", r["gain_crossovers"])
