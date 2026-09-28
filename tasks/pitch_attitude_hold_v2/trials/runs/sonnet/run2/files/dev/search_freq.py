"""Stage 1: frequency-domain-only search for (Kp, Ki, Kq).

b does not appear in the loop gain L(s) at all (it only weights the reference
path), so margins depend only on (Kp, Ki, Kq). This stage finds gains that
satisfy the R2 margins at all three airspeeds with some safety buffer, while
maximizing the worst-case (minimum across speeds) gain-crossover frequency as
a fast proxy for closed-loop speed. b is tuned afterwards against the real
nonlinear metric (see dev/search_b.py / dev/refine.py).
"""
import sys
import time

import numpy as np
from scipy.optimize import differential_evolution

import core
import margins as margins_mod

PLANTS = {spd: core.load_plant(spd) for spd in core.SPEEDS}
OMEGA = core.grader_omega_grid()

PM_TARGET = 45.0
GM_TARGET = 6.0
DM_TARGET = 6.0
# safety buffer above the pass threshold, so the final design isn't marginal
# once we round / once b is added / once the nonlinear run is checked.
PM_BUFFER = 3.0
GM_BUFFER = 1.0
DM_BUFFER = 1.0


def evaluate(gains):
    Kp, Ki, Kq = gains
    worst_pm = np.inf
    worst_gm = np.inf
    worst_dm = np.inf
    wgcs = []
    per_speed = {}
    for spd, plant in PLANTS.items():
        r = margins_mod.analyze(plant, Kp, Ki, Kq, omega=OMEGA)
        per_speed[spd] = r
        worst_pm = min(worst_pm, r["phase_margin_deg"])
        worst_gm = min(worst_gm, r["gain_margin_db"])
        worst_dm = min(worst_dm, r["decrease_margin_db"])
        wgcs.append(np.min(r["wgc"]) if r["wgc"].size else 0.0)
    min_wgc = min(wgcs) if wgcs else 0.0
    return worst_pm, worst_gm, worst_dm, min_wgc, per_speed


def cost(gains):
    Kp, Ki, Kq = gains
    if Kp >= 0 or Ki >= 0 or Kq >= 0:
        return 1e6
    worst_pm, worst_gm, worst_dm, min_wgc, _ = evaluate(gains)
    viol = (max(0.0, (PM_TARGET + PM_BUFFER) - worst_pm)
            + max(0.0, (GM_TARGET + GM_BUFFER) - worst_gm) * 2.0
            + max(0.0, (DM_TARGET + DM_BUFFER) - worst_dm) * 2.0)
    if viol > 0:
        return 1000.0 + viol * 50.0
    return -min_wgc


def main():
    bounds = [(-30.0, -0.001), (-15.0, -0.001), (-8.0, -0.001)]
    t0 = time.time()
    result = differential_evolution(
        cost, bounds, maxiter=int(sys.argv[1]) if len(sys.argv) > 1 else 80,
        popsize=20, tol=1e-8, seed=42, polish=True, workers=1, disp=True,
        mutation=(0.4, 1.5), recombination=0.7,
    )
    t1 = time.time()
    print("elapsed", t1 - t0, "s")
    print("best gains:", result.x, "cost:", result.fun)
    worst_pm, worst_gm, worst_dm, min_wgc, per_speed = evaluate(result.x)
    print(f"worst_pm={worst_pm:.2f} worst_gm={worst_gm:.2f} worst_dm={worst_dm:.2f} min_wgc={min_wgc:.4f}")
    for spd, r in per_speed.items():
        print(spd, "pm=%.2f gm=%.2f dm=%.2f wgc=%s n_pc=%d" % (
            r["phase_margin_deg"], r["gain_margin_db"], r["decrease_margin_db"],
            np.round(r["wgc"], 4), r["n_phase_crossovers"]))
    np.save("best_gains_stage1.npy", result.x)


if __name__ == "__main__":
    main()
