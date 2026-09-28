import numpy as np
from common import loop_frd, margins_from_L
from poly_model import closed_loop_poles_poly, worst_pole_metric

w = np.load("w_coarse.npy")
Gtm = np.load("Gtm_coarse.npy")
Gqm = np.load("Gqm_coarse.npy")


def feasible_margins(Kp, Ki, Kq, pm_min=45.0, gm_min=6.0):
    L = loop_frd(w, Kp, Ki, Kq, Gtm, Gqm)
    m = margins_from_L(w, L)
    gcs = m["gain_crossings"]
    pcs = m["phase_crossings"]
    if len(gcs) == 0:
        return False, None, None, None
    worst_pm = min(g[1] for g in gcs)
    if worst_pm < pm_min:
        return False, worst_pm, None, None
    worst_gm_inc = None
    worst_gm_dec = None
    for wpc, kind, gm in pcs:
        if kind == "increase":
            worst_gm_inc = gm if worst_gm_inc is None else min(worst_gm_inc, gm)
        else:
            worst_gm_dec = gm if worst_gm_dec is None else min(worst_gm_dec, gm)
    if worst_gm_inc is not None and worst_gm_inc < gm_min:
        return False, worst_pm, worst_gm_inc, worst_gm_dec
    if worst_gm_dec is not None and worst_gm_dec < gm_min:
        return False, worst_pm, worst_gm_inc, worst_gm_dec
    return True, worst_pm, worst_gm_inc, worst_gm_dec


def scan(kq_list, kp_list, ki_list, pm_min=45.0, gm_min=6.0):
    best = None
    for kq in kq_list:
        Kq = -kq
        for kp in kp_list:
            Kp = -kp
            for ki in ki_list:
                Ki = -ki
                ok, pm, gmi, gmd = feasible_margins(Kp, Ki, Kq, pm_min, gm_min)
                if not ok:
                    continue
                poles = closed_loop_poles_poly(Kp, Ki, Kq)
                speed, pole, stable = worst_pole_metric(poles)
                if not stable:
                    continue
                if best is None or speed > best[0]:
                    best = (speed, Kp, Ki, Kq, pm, gmi, gmd, pole)
    return best


if __name__ == "__main__":
    kq_list = np.linspace(0.02, 0.50, 49)
    kp_list = np.linspace(0.1, 8, 50)
    ki_list = np.linspace(0.05, 8, 50)
    best = scan(kq_list, kp_list, ki_list)
    if best:
        speed, Kp, Ki, Kq, pm, gmi, gmd, pole = best
        print(f"BEST: speed(min|Re|)={speed:.4f}  Kp={Kp:.5f} Ki={Ki:.5f} Kq={Kq:.5f}")
        print(f"  PM={pm:.3f} GMinc={gmi} GMdec={gmd}  dominant pole={pole:.4f}")
        print(f"  approx 2% settle ~ {4.0/speed:.3f} s (rough single-pole proxy)")
    else:
        print("no feasible point found")
