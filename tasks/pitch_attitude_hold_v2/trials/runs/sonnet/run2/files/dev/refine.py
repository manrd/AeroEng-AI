"""Stage 2/3: tune b against the real nonlinear metric, then jointly polish
(Kp, Ki, Kq, b) with a local derivative-free search, using the fast simulator
and fast margin scan. Finishes by re-checking the chosen design with the
official (slow, exact aircraft_model.derivatives-based) simulator and the
exact margin scan, which is what actually matters.
"""
import sys
import time

import numpy as np
from scipy.optimize import minimize

import core
import fastsim
import margins as margins_mod

PARAMS = core.load_params()
PLANTS = {spd: core.load_plant(spd) for spd in core.SPEEDS}
DERIVS = {spd: fastsim.make_fast_derivatives(PARAMS) for spd in core.SPEEDS}
OMEGA = core.grader_omega_grid()

PM_MIN = 45.0
GM_MIN = 6.0
DM_MIN = 6.0
OS_MAX = 10.0
ELEV_MAX = 25.0
TS_MAX = 6.0


def margin_report(Kp, Ki, Kq):
    out = {}
    for spd, plant in PLANTS.items():
        out[spd] = margins_mod.analyze(plant, Kp, Ki, Kq, omega=OMEGA)
    return out


def time_report_fast(Kp, Ki, Kq, b):
    out = {}
    for spd in core.SPEEDS:
        out[spd] = fastsim.simulate_fast(PLANTS[spd], Kp, Ki, Kq, b, DERIVS[spd])
    return out


def time_report_slow(Kp, Ki, Kq, b):
    out = {}
    for spd in core.SPEEDS:
        sim = core.simulate(PLANTS[spd], Kp, Ki, Kq, b, params=PARAMS)
        out[spd] = core.compute_metrics(sim)
    return out


def penalty_and_cost(Kp, Ki, Kq, b, mreps, treps):
    """Shared scoring used by both the b-sweep and the joint polish."""
    worst_pm = min(r["phase_margin_deg"] for r in mreps.values())
    worst_gm = min(r["gain_margin_db"] for r in mreps.values())
    worst_dm = min(r["decrease_margin_db"] for r in mreps.values())
    worst_os = max(r["overshoot_pct"] for r in treps.values())
    worst_elev = max(r["max_elevator_deg"] for r in treps.values())
    worst_ts = max(r["settling_time_s"] for r in treps.values())
    any_div = any(r["diverged"] for r in treps.values())

    viol = 0.0
    viol += max(0.0, PM_MIN - worst_pm)
    viol += max(0.0, GM_MIN - worst_gm) * 2.0
    viol += max(0.0, DM_MIN - worst_dm) * 2.0
    viol += max(0.0, worst_os - OS_MAX) * 3.0
    viol += max(0.0, worst_elev - ELEV_MAX) * 3.0
    if any_div:
        viol += 500.0

    if viol > 1e-9:
        cost = 1000.0 + viol * 20.0
    else:
        cost = worst_ts
    return cost, dict(worst_pm=worst_pm, worst_gm=worst_gm, worst_dm=worst_dm,
                       worst_os=worst_os, worst_elev=worst_elev, worst_ts=worst_ts,
                       any_div=any_div, viol=viol)


def full_cost_fast(x):
    Kp, Ki, Kq, b = x
    if Kp >= 0 or Ki >= 0 or Kq >= 0 or b < 0.0 or b > 1.0:
        return 1e6
    mreps = margin_report(Kp, Ki, Kq)
    treps = time_report_fast(Kp, Ki, Kq, b)
    cost, _ = penalty_and_cost(Kp, Ki, Kq, b, mreps, treps)
    return cost


def sweep_b(Kp, Ki, Kq, n=41):
    mreps = margin_report(Kp, Ki, Kq)
    best = None
    rows = []
    for b in np.linspace(0.0, 1.0, n):
        treps = time_report_fast(Kp, Ki, Kq, b)
        cost, info = penalty_and_cost(Kp, Ki, Kq, b, mreps, treps)
        rows.append((b, cost, info))
        if best is None or cost < best[1]:
            best = (b, cost, info)
    return best, rows


def main():
    gains_path = sys.argv[1] if len(sys.argv) > 1 else "best_gains_stage1.npy"
    Kp, Ki, Kq = np.load(gains_path)
    print("stage-1 gains:", Kp, Ki, Kq)

    mreps = margin_report(Kp, Ki, Kq)
    for spd, r in mreps.items():
        print(spd, "pm=%.2f gm=%.2f dm=%.2f" % (r["phase_margin_deg"], r["gain_margin_db"], r["decrease_margin_db"]))

    best, rows = sweep_b(Kp, Ki, Kq)
    print("best b from sweep:", best[0], "cost", best[1], best[2])

    x0 = np.array([Kp, Ki, Kq, best[0]])
    t0 = time.time()
    res = minimize(full_cost_fast, x0, method="Nelder-Mead",
                    options=dict(maxiter=800, maxfev=800, xatol=1e-5, fatol=1e-6, adaptive=True))
    t1 = time.time()
    print("polish elapsed", t1 - t0, "s, cost", res.fun, "x", res.x)

    Kp2, Ki2, Kq2, b2 = res.x
    mreps2 = margin_report(Kp2, Ki2, Kq2)
    treps2_fast = time_report_fast(Kp2, Ki2, Kq2, b2)
    for spd in core.SPEEDS:
        r = mreps2[spd]; t = treps2_fast[spd]
        print(spd, "pm=%.2f gm=%.2f dm=%.2f | os=%.2f ts=%.3f maxE=%.2f div=%s" % (
            r["phase_margin_deg"], r["gain_margin_db"], r["decrease_margin_db"],
            t["overshoot_pct"], t["settling_time_s"], t["max_elevator_deg"], t["diverged"]))

    np.save("best_gains_stage2.npy", res.x)

    print("\n--- official (slow) verification ---")
    treps2_slow = time_report_slow(Kp2, Ki2, Kq2, b2)
    for spd in core.SPEEDS:
        t = treps2_slow[spd]
        print(spd, "os=%.3f ts=%.3f maxE=%.3f div=%s" % (
            t["overshoot_pct"], t["settling_time_s"], t["max_elevator_deg"], t["diverged"]))


if __name__ == "__main__":
    main()
