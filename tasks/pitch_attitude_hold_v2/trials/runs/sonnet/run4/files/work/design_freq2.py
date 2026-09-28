"""Frequency-domain search v2: precompute each plant's Gtheta(jw), Gq(jw), delay, actuator response
ONCE on the full grader grid (200001 pts), so each (Kp,Ki,Kq) trial is just elementwise numpy algebra
(no eigendecomposition per trial) -- cheap enough to always evaluate on the exact grader resolution,
avoiding the coarse-grid blind spot that let a spurious low-frequency crossing pair (near the lightly
damped phugoid) slip through in design_freq.py.

Design philosophy: penalize any topology other than a clean single gain crossover (and require >=6dB
away from 0dB at every phase crossover, whichever side of 0dB it's on) -- i.e. push the optimizer away
from fragile conditionally-stable notches near the phugoid, toward one clean crossover per speed.
"""
import numpy as np
from scipy.optimize import differential_evolution
import loopgain as lg

SPEEDS = (20, 25, 32)
OMEGA = lg.GRADER_OMEGA
S = 1j * OMEGA
TAU_ACT, TAU_DELAY = lg.TAU_ACT, lg.TAU_DELAY
AACT = 1.0 / (TAU_ACT * S + 1.0)
DELAY = np.exp(-TAU_DELAY * S)

PRECOMP = {}
for spd in SPEEDS:
    plant = lg.load_plant(spd)
    Gtheta, Gq = lg.plant_freq_response(plant, OMEGA)
    PRECOMP[spd] = dict(Gtheta=Gtheta, Gq=Gq, plant=plant)


def loop_L_fast(spd, Kp, Ki, Kq):
    d = PRECOMP[spd]
    ctrl = (Kp + Ki / S) * d["Gtheta"] + Kq * d["Gq"]
    return DELAY * AACT * ctrl


PM_MIN, GM_MIN_DB = 45.0, 6.0
BUFFER_PM, BUFFER_GM = 8.0, 2.5


def analyze(Kp, Ki, Kq, verbose=False):
    out = {}
    for spd in SPEEDS:
        L = loop_L_fast(spd, Kp, Ki, Kq)
        gcs, pcs = lg.find_all_margins(OMEGA, L)
        out[spd] = dict(gcs=gcs, pcs=pcs)
        if verbose:
            print(spd, "gain crossings", gcs)
            print(spd, "phase crossings", pcs)
    return out


def cost(params):
    Kp, Ki, Kq = params
    penalty = 0.0
    min_gc = 1e9
    for spd in SPEEDS:
        L = loop_L_fast(spd, Kp, Ki, Kq)
        gcs, pcs = lg.find_all_margins(OMEGA, L)
        if len(gcs) != 1:
            penalty += 200.0 * abs(len(gcs) - 1) + 50.0
        if not gcs:
            continue
        wc, pm = gcs[0]
        min_gc = min(min_gc, wc)
        penalty += max(0.0, (PM_MIN + BUFFER_PM) - pm) * 2.0
        for wpc, gdb in pcs:
            if abs(gdb) < GM_MIN_DB + BUFFER_GM:
                penalty += (GM_MIN_DB + BUFFER_GM - abs(gdb)) * 3.0
    if penalty > 1e-6:
        return penalty + 100.0
    return -min_gc


if __name__ == "__main__":
    bounds = [(-4.0, 4.0), (-4.0, 4.0), (-4.0, 4.0)]
    result = differential_evolution(cost, bounds, seed=1, maxiter=400, popsize=30, tol=1e-12,
                                     mutation=(0.4, 1.5), recombination=0.85, polish=True, workers=-1)
    print(result)
    Kp, Ki, Kq = result.x
    print("Best Kp,Ki,Kq:", Kp, Ki, Kq)
    analyze(Kp, Ki, Kq, verbose=True)
