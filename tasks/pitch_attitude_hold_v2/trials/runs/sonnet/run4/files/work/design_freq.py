"""Frequency-domain search for (Kp, Ki, Kq): maximize the worst-case (min over 3 speeds) gain
crossover frequency subject to PM >= 45+buffer deg and GM >= 6+buffer dB (against increase) at all
three speeds, and the extra 'against a decrease' check at any above-0dB phase crossing. b does not
affect the linear loop (theta_cmd multiplies only b, and margins are computed with theta_cmd = 0), so
it is tuned separately against the nonlinear overshoot requirement.
"""
import numpy as np
from scipy.optimize import differential_evolution
import loopgain as lg

SPEEDS = (20, 25, 32)
PLANTS = {s: lg.load_plant(s) for s in SPEEDS}
OMEGA = np.logspace(np.log10(0.001), np.log10(1000.0), 20001)  # coarser grid for fast search; refine later

PM_MIN = 45.0
GM_MIN_DB = 6.0
BUFFER_PM = 6.0   # design buffer above the bare minimum, to survive nonlinearity + grader recompute tolerance
BUFFER_GM = 2.0


def evaluate(Kp, Ki, Kq, omega=OMEGA, verbose=False):
    out = {}
    for s in SPEEDS:
        L = lg.loop_L(omega, Kp, Ki, Kq, PLANTS[s])
        rep = lg.margins_report(omega, L)
        out[s] = rep
        if verbose:
            print(s, "PM", rep["phase_margin_deg"], "GM_db", rep["gain_margin_db"],
                  "ok_dec", rep["ok_gm6_decrease"], "gc", rep["gain_crossings"])
    return out


def cost(params):
    Kp, Ki, Kq = params
    penalty = 0.0
    min_gc = 1e9
    for s in SPEEDS:
        L = lg.loop_L(OMEGA, Kp, Ki, Kq, PLANTS[s])
        rep = lg.margins_report(OMEGA, L)
        pm = rep["phase_margin_deg"]
        gm = rep["gain_margin_db"]
        if not rep["gain_crossings"]:
            penalty += 1000.0
            continue
        gcs = [w for w, _ in rep["gain_crossings"]]
        min_gc = min(min_gc, min(gcs))
        # penalize shortfall vs buffered targets
        penalty += max(0.0, (PM_MIN + BUFFER_PM) - pm) * 2.0
        penalty += max(0.0, (GM_MIN_DB + BUFFER_GM) - gm) * 3.0
        for _, gdb in rep["phase_crossings"]:
            if gdb >= 0 and gdb < GM_MIN_DB + BUFFER_GM:
                penalty += (GM_MIN_DB + BUFFER_GM - gdb) * 3.0
        for _, pmc in rep["gain_crossings"]:
            if pmc < PM_MIN + BUFFER_PM:
                penalty += (PM_MIN + BUFFER_PM - pmc) * 1.0
    if penalty > 1e-6:
        return penalty + 100.0  # keep infeasible region worse than any feasible bandwidth value
    return -min_gc  # maximize worst-case bandwidth => minimize its negative


if __name__ == "__main__":
    bounds = [(-4.0, 4.0), (-4.0, 4.0), (-4.0, 4.0)]
    result = differential_evolution(cost, bounds, seed=0, maxiter=300, popsize=25, tol=1e-10,
                                     mutation=(0.4, 1.5), recombination=0.8, polish=True, workers=-1)
    print(result)
    Kp, Ki, Kq = result.x
    print("Best Kp,Ki,Kq:", Kp, Ki, Kq)
    evaluate(Kp, Ki, Kq, omega=lg.GRADER_OMEGA, verbose=True)
