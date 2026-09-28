import numpy as np
from common import *

w = np.load("w.npy")
Gtm = np.load("Gtm.npy")
Gqm = np.load("Gqm.npy")


def freq_eval(Kp, Ki, Kq):
    L = loop_frd(w, Kp, Ki, Kq, Gtm, Gqm)
    m = margins_from_L(w, L)
    gcs = m["gain_crossings"]
    pcs = m["phase_crossings"]
    if len(gcs) == 0:
        worst_pm = None
        wgc_list = []
    else:
        wgc_list = [g[0] for g in gcs]
        worst_pm = min(g[1] for g in gcs)
    worst_gm_inc = None
    worst_gm_dec = None
    for wpc, kind, gm in pcs:
        if kind == "increase":
            worst_gm_inc = gm if worst_gm_inc is None else min(worst_gm_inc, gm)
        else:
            worst_gm_dec = gm if worst_gm_dec is None else min(worst_gm_dec, gm)
    return {
        "wgc_list": wgc_list,
        "worst_pm": worst_pm,
        "worst_gm_inc": worst_gm_inc,
        "worst_gm_dec": worst_gm_dec,
        "n_gain_cross": len(gcs),
        "n_phase_cross": len(pcs),
        "gcs": gcs,
        "pcs": pcs,
    }


def feasible(res, pm_min=45.0, gm_min=6.0):
    if res["worst_pm"] is None or res["worst_pm"] < pm_min:
        return False
    if res["worst_gm_inc"] is not None and res["worst_gm_inc"] < gm_min:
        return False
    if res["worst_gm_dec"] is not None and res["worst_gm_dec"] < gm_min:
        return False
    return True


if __name__ == "__main__":
    import sys

    # broad scan: kp,ki>0 with Kp=-kp,Ki=-ki, for a few Kq
    for kq in [0.0, -0.05, -0.1, -0.15, -0.2, -0.3, -0.4]:
        best = None
        for kp in np.linspace(0.2, 6, 30):
            for ki in np.linspace(0.1, 6, 30):
                Kp, Ki, Kq = -kp, -ki, kq
                res = freq_eval(Kp, Ki, Kq)
                if feasible(res):
                    wmax = max(res["wgc_list"]) if res["wgc_list"] else 0
                    if best is None or wmax > best[0]:
                        best = (wmax, kp, ki, res)
        if best:
            wmax, kp, ki, res = best
            print(f"Kq={kq:6.2f}  best wgc={wmax:.3f}  Kp={-kp:.3f} Ki={-ki:.3f}  "
                  f"PM={res['worst_pm']:.2f} GMinc={res['worst_gm_inc']} GMdec={res['worst_gm_dec']} "
                  f"n_gc={res['n_gain_cross']} n_pc={res['n_phase_cross']}")
        else:
            print(f"Kq={kq:6.2f}  no feasible point found in grid")
