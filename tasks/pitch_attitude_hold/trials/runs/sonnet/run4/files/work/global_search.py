import numpy as np
from scipy.optimize import differential_evolution
from common import loop_frd, margins_from_L
from poly_model import closed_loop_poles_poly, worst_pole_metric

w = np.load("w_coarse.npy")
Gtm = np.load("Gtm_coarse.npy")
Gqm = np.load("Gqm_coarse.npy")

PM_MIN = 45.0
GM_MIN = 6.0
PM_TARGET = 46.5   # small buffer above the hard floor for the optimizer to aim past
GM_TARGET = 6.3


def margins(Kp, Ki, Kq):
    L = loop_frd(w, Kp, Ki, Kq, Gtm, Gqm)
    m = margins_from_L(w, L)
    gcs = m["gain_crossings"]
    pcs = m["phase_crossings"]
    if len(gcs) == 0:
        return None, None, None
    worst_pm = min(g[1] for g in gcs)
    worst_gm_inc = None
    worst_gm_dec = None
    for wpc, kind, gm in pcs:
        if kind == "increase":
            worst_gm_inc = gm if worst_gm_inc is None else min(worst_gm_inc, gm)
        else:
            worst_gm_dec = gm if worst_gm_dec is None else min(worst_gm_dec, gm)
    return worst_pm, worst_gm_inc, worst_gm_dec


def objective(x):
    Kp, Ki, Kq = x
    pm, gmi, gmd = margins(Kp, Ki, Kq)
    pen = 0.0
    if pm is None:
        pen += 1e3
        pm_val = 0.0
    else:
        pen += 30.0 * max(0.0, PM_TARGET - pm) ** 2
        pm_val = pm
    if gmi is None:
        pen += 50.0  # no increase-side crossing at all is suspicious; discourage
    else:
        pen += 30.0 * max(0.0, GM_TARGET - gmi) ** 2
    if gmd is not None:
        pen += 30.0 * max(0.0, GM_TARGET - gmd) ** 2

    poles = closed_loop_poles_poly(Kp, Ki, Kq)
    speed, pole, stable = worst_pole_metric(poles)
    if not stable:
        pen += 1e3 + 10.0 * (-speed)
        return pen
    # maximize speed => minimize -speed, combined with penalty
    return -speed + pen


if __name__ == "__main__":
    bounds = [(-15.0, -0.05), (-80.0, -0.05), (-1.2, -0.02)]
    res = differential_evolution(objective, bounds, maxiter=300, popsize=25, tol=1e-10,
                                  mutation=(0.4, 1.5), recombination=0.8, seed=42,
                                  polish=True, workers=1)
    Kp, Ki, Kq = res.x
    pm, gmi, gmd = margins(Kp, Ki, Kq)
    poles = closed_loop_poles_poly(Kp, Ki, Kq)
    speed, pole, stable = worst_pole_metric(poles)
    print("result x:", res.x, "fun:", res.fun)
    print(f"Kp={Kp:.5f} Ki={Ki:.5f} Kq={Kq:.5f}")
    print(f"PM={pm} GMinc={gmi} GMdec={gmd}")
    print(f"dominant pole speed |Re|={speed:.4f} pole={pole} stable={stable}")
    print(f"approx settle proxy: {4.0/speed:.3f} s")
