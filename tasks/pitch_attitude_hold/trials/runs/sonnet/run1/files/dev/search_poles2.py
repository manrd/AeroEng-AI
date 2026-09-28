"""Cheap (eigenvalue-based) search: fast slow-pole, but also penalize underdamped fast poles
(zeta too low causes overshoot/ringing that b can't fix). Margins as constraints."""
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


def analyze(Kp, Ki, Kq):
    ev = eigs(Kp, Ki, Kq)
    maxre = np.max(ev.real)
    # min zeta among poles with wn > 1.0 (ignore the very slow / near-origin pole itself, and
    # ignore very high frequency Pade artifacts above 100 rad/s)
    zetas = []
    for lam in ev:
        wn = abs(lam)
        if 1.0 < wn < 100.0:
            zeta = -lam.real / wn
            zetas.append(zeta)
    min_zeta = min(zetas) if zetas else 1.0
    return maxre, min_zeta, ev


def margins(Kp, Ki, Kq):
    L = loop_gain(W, Kp, Ki, Kq, PTHETA_JW, PQ_JW)
    return margins_from_L(W, L)


def objective(x, zeta_target=0.6, pm_req=45.0, gm_req=6.0):
    Kp, Ki, Kq = x
    maxre, min_zeta, ev = analyze(Kp, Ki, Kq)
    if maxre >= -1e-4:
        return 1000.0 + 1000.0 * max(maxre, 0.0)
    m = margins(Kp, Ki, Kq)
    pm = m["worst_phase_margin_deg"]
    gmu = m["worst_gain_margin_up_db"]
    gmd = m["worst_gain_margin_down_db"]
    pen = 0.0
    if pm < pm_req:
        pen += (pm_req - pm) ** 2
    if gmu < gm_req:
        pen += (gm_req - gmu) ** 2
    if np.isfinite(gmd) and gmd < gm_req:
        pen += (gm_req - gmd) ** 2
    if min_zeta < zeta_target:
        pen += (zeta_target - min_zeta) ** 2 * 5.0
    # objective: minimize (maxre) i.e. push most-negative; primary term maxre, penalty added
    return maxre + 30.0 * pen


if __name__ == "__main__":
    bounds = [(-15, -0.05), (-15, -0.05), (-6, 6)]
    t0 = time.time()
    result = differential_evolution(objective, bounds, maxiter=120, popsize=20, tol=1e-10,
                                     mutation=(0.3, 1.7), recombination=0.8, seed=7, polish=True)
    print("time:", time.time() - t0)
    Kp, Ki, Kq = result.x
    maxre, min_zeta, ev = analyze(Kp, Ki, Kq)
    m = margins(Kp, Ki, Kq)
    print("Kp,Ki,Kq=", Kp, Ki, Kq)
    print("maxre=", maxre, "min_zeta(wn in (1,100))=", min_zeta)
    print("PM=", m["worst_phase_margin_deg"], "GMup=", m["worst_gain_margin_up_db"],
          "GMdown=", m["worst_gain_margin_down_db"])
    print("poles:")
    for lam in sorted(ev, key=lambda z: -z.real)[:8]:
        wn = abs(lam)
        zeta = -lam.real / wn if wn > 1e-9 else float("nan")
        print(f"  {lam:22.6f}  wn={wn:8.4f} zeta={zeta:7.4f}")
