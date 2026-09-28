"""Direct joint search over (Kp, Ki, Kq, b) using the *nonlinear* simulation as the primary objective
and constraint source. The purely-linear (bandwidth-maximizing) search in design_freq3.py turned out to
be a bad proxy: it happily ran gains out to Kp=-129, Ki=-4, Kq=2.7, which pass the R2 Bode margins with
huge PM (the linear model has no actuator rate/position limit!) but produce 300-700% nonlinear
overshoot and 250-370 deg 'elevator commands' -- the 60 deg/s actuator rate limit binds hard for a
5 deg attitude step at these gains, something the small-signal frequency response cannot see at all.
So: gate on the fast linear margins (cheap, catches genuinely unstable/marginal points early), but
score and rank candidates by the real nonlinear closed-loop performance.
"""
import time
import numpy as np
import loopgain as lg
import nlsim
import model_fast as mf

SPEEDS = (20, 25, 32)
OMEGA = lg.GRADER_OMEGA
PLANTS = {s: lg.load_plant(s) for s in SPEEDS}
PARAMS = mf.load_params()

PM_MIN, GM_MIN_DB = 45.0, 6.0
BUF_PM, BUF_GM = 5.0, 1.5  # smaller buffer now that nonlinear reality is the real judge


def linear_ok(Kp, Ki, Kq, buf_pm=BUF_PM, buf_gm=BUF_GM):
    """Cheap gate: every speed must have exactly one gain crossover with buffered PM/GM. Returns
    (ok, worst_pm, worst_gm, min_gc)."""
    worst_pm = 1e9
    worst_gm = 1e9
    min_gc = 1e9
    for spd in SPEEDS:
        L = lg.loop_L(OMEGA, Kp, Ki, Kq, PLANTS[spd])
        gcs, pcs = lg.find_all_margins_fast(OMEGA, L)
        if len(gcs) != 1:
            return False, -1, -1, -1
        wc, pm = gcs[0]
        if pm < PM_MIN + buf_pm:
            return False, pm, -1, -1
        for _, gdb in pcs:
            if abs(gdb) < GM_MIN_DB + buf_gm:
                return False, pm, gdb, -1
        worst_pm = min(worst_pm, pm)
        min_gc = min(min_gc, wc)
        worst_gm = min(worst_gm, min(abs(gdb) for _, gdb in pcs))
    return True, worst_pm, worst_gm, min_gc


def nonlinear_eval(Kp, Ki, Kq, b):
    worst_settle, worst_over, worst_elev = 0.0, 0.0, 0.0
    diverged = False
    for spd in SPEEDS:
        sim = nlsim.simulate(spd, Kp, Ki, Kq, b, params=PARAMS)
        worst_settle = max(worst_settle, sim["settling_time_s"])
        worst_over = max(worst_over, sim["overshoot_pct"])
        worst_elev = max(worst_elev, sim["max_elevator_deg"])
        diverged = diverged or sim["diverged"]
    return dict(worst_settle=worst_settle, worst_over=worst_over, worst_elev=worst_elev,
                diverged=diverged)


R3_MAX, R4_MAX, R5_MAX = 10.0, 25.0, 6.0
BUF_R3, BUF_R4, BUF_R5 = 2.0, 1.5, 0.5  # safety buffer under each threshold


def full_cost(params):
    Kp, Ki, Kq, b = params
    if not (0.0 <= b <= 1.0):
        return 1e6 + 1000.0 * (abs(b - 0.5))
    ok, wpm, wgm, min_gc = linear_ok(Kp, Ki, Kq)
    if not ok:
        # still give gradient: how far from a valid single-crossing/margin design
        return 5000.0 + abs(Kp) + abs(Ki) + abs(Kq)
    r = nonlinear_eval(Kp, Ki, Kq, b)
    if r["diverged"]:
        return 3000.0
    penalty = 0.0
    penalty += max(0.0, r["worst_over"] - (R3_MAX - BUF_R3)) * 5.0
    penalty += max(0.0, r["worst_elev"] - (R4_MAX - BUF_R4)) * 5.0
    penalty += max(0.0, r["worst_settle"] - (R5_MAX - BUF_R5)) * 5.0
    if penalty > 1e-9:
        return 100.0 + penalty
    return r["worst_settle"]  # minimize worst-of-3 settling time directly


def report(Kp, Ki, Kq, b):
    ok, wpm, wgm, min_gc = linear_ok(Kp, Ki, Kq, buf_pm=0, buf_gm=0)
    print(f"linear: single-crossing-ok={ok} worst_pm={wpm:.2f} worst_gm={wgm:.2f} min_gc={min_gc:.3f}")
    for spd in SPEEDS:
        sim = nlsim.simulate(spd, Kp, Ki, Kq, b, params=PARAMS)
        print(f"  {spd} m/s: settle={sim['settling_time_s']:.3f}s over={sim['overshoot_pct']:.2f}% "
              f"elev={sim['max_elevator_deg']:.2f}deg diverged={sim['diverged']}")


if __name__ == "__main__":
    import sys
    from scipy.optimize import differential_evolution

    t0 = time.time()
    bounds = [(-2.5, 2.5), (-2.5, 2.5), (-2.5, 2.5), (0.0, 1.0)]
    result = differential_evolution(full_cost, bounds, seed=3, maxiter=60, popsize=14, tol=1e-9,
                                     mutation=(0.4, 1.5), recombination=0.85, polish=False, workers=1)
    print("elapsed", time.time() - t0)
    print(result)
    Kp, Ki, Kq, b = result.x
    print("best:", Kp, Ki, Kq, b)
    report(Kp, Ki, Kq, b)
