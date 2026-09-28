"""Frequency-domain search v3: serial (no multiprocessing -- avoids oversubscribing this 12-core box),
using the fast + corrected (wrapped-phase, validated against control.stability_margins in
validate_margins.py) crossing finder on the full 200001-point grader grid. Penalizes any topology
other than a clean single gain crossover per speed (avoids fragile phugoid-notch double crossings),
and maximizes the worst-case (min over 3 speeds) gain crossover frequency as a bandwidth proxy, subject
to buffered PM/GM constraints holding at every crossing found.
"""
import time
import numpy as np
from scipy.optimize import differential_evolution, minimize
import loopgain as lg

SPEEDS = (20, 25, 32)
OMEGA = lg.GRADER_OMEGA
PLANTS = {s: lg.load_plant(s) for s in SPEEDS}

PM_MIN, GM_MIN_DB = 45.0, 6.0
BUFFER_PM, BUFFER_GM = 8.0, 2.5


def cost(params, buf_pm=BUFFER_PM, buf_gm=BUFFER_GM):
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


if __name__ == "__main__":
    t0 = time.time()
    bounds = [(-4.0, 4.0), (-4.0, 4.0), (-4.0, 4.0)]
    result = differential_evolution(cost, bounds, seed=2, maxiter=50, popsize=12, tol=1e-9,
                                     mutation=(0.4, 1.5), recombination=0.85, polish=False, workers=1)
    print("DE done in", time.time() - t0, "s")
    print(result)
    Kp, Ki, Kq = result.x
    print("DE best Kp,Ki,Kq:", Kp, Ki, Kq)
    report(Kp, Ki, Kq)

    t1 = time.time()
    res2 = minimize(cost, [Kp, Ki, Kq], method="Nelder-Mead",
                     options=dict(xatol=1e-5, fatol=1e-8, maxiter=3000, maxfev=3000, adaptive=True))
    print("polish done in", time.time() - t1, "s")
    print(res2)
    Kp2, Ki2, Kq2 = res2.x
    print("polished Kp,Ki,Kq:", Kp2, Ki2, Kq2)
    report(Kp2, Ki2, Kq2)
