"""Local polish of (Kp, Ki, Kq) around a candidate, using the *corrected* (wrapped-phase,
control.stability_margins-based) margin code in loopgain.py. Serial (no multiprocessing -- cheap
enough per call once not competing with other CPU-bound work), single-gain-crossover-per-speed
enforced via penalty, maximizing the worst-case (min over 3 speeds) gain-crossover frequency subject
to buffered PM/GM constraints holding at every crossing found.
"""
import numpy as np
from scipy.optimize import minimize
import loopgain as lg

SPEEDS = (20, 25, 32)
OMEGA = lg.GRADER_OMEGA
PLANTS = {s: lg.load_plant(s) for s in SPEEDS}

PM_MIN, GM_MIN_DB = 45.0, 6.0


def cost(params, buf_pm=8.0, buf_gm=2.5, verbose=False):
    Kp, Ki, Kq = params
    penalty = 0.0
    min_gc = 1e9
    for spd in SPEEDS:
        L = lg.loop_L(OMEGA, Kp, Ki, Kq, PLANTS[spd])
        gcs, pcs = lg.find_all_margins_fast(OMEGA, L)
        if len(gcs) != 1:
            penalty += 300.0 * abs(len(gcs) - 1) + 80.0
        if not gcs:
            continue
        wc, pm = gcs[0]
        min_gc = min(min_gc, wc)
        penalty += max(0.0, (PM_MIN + buf_pm) - pm) * 2.0
        for _, gdb in pcs:
            if abs(gdb) < GM_MIN_DB + buf_gm:
                penalty += (GM_MIN_DB + buf_gm - abs(gdb)) * 3.0
        if verbose:
            print(f"  {spd}: wc={wc:.3f} pm={pm:.2f}  pcs={pcs}")
    if penalty > 1e-6:
        return penalty + 100.0
    return -min_gc


def report(Kp, Ki, Kq):
    for spd in SPEEDS:
        L = lg.loop_L(OMEGA, Kp, Ki, Kq, PLANTS[spd])
        rep = lg.margins_report_fast(OMEGA, L)
        print(f"{spd} m/s: PM={rep['phase_margin_deg']:.2f} deg  GM={rep['gain_margin_db']:.2f} dB  "
              f"ok_pm45={rep['ok_pm45']} ok_inc={rep['ok_gm6_increase']} ok_dec={rep['ok_gm6_decrease']}  "
              f"n_gc={len(rep['gain_crossings'])} n_pc={len(rep['phase_crossings'])}")
        print("   gain_crossings:", rep["gain_crossings"])
        print("   phase_crossings:", rep["phase_crossings"])


if __name__ == "__main__":
    import sys
    x0 = [float(v) for v in sys.argv[1:4]] if len(sys.argv) >= 4 else [-1.0, -0.5, -0.5]
    print("start:", x0)
    report(*x0)
    res = minimize(cost, x0, method="Nelder-Mead",
                    options=dict(xatol=1e-4, fatol=1e-6, maxiter=2000, maxfev=2000, adaptive=True))
    print(res)
    print("refined:", res.x)
    report(*res.x)
