"""Given fixed (Kp, Ki, Kq) that already satisfy R2 with margin, scan the setpoint weight b in [0,1]
(which does not affect the linear loop / R1 / R2 at all -- it only reweights the reference into the
proportional term) to find the b that minimises the worst-of-3-speeds settling time while keeping R3
(overshoot) and R4 (elevator command) satisfied. Pure nonlinear-sim search, since R3/R4/R5 are only
defined on the nonlinear run.
"""
import numpy as np
import nlsim
import model_fast as mf

SPEEDS = (20, 25, 32)
_PARAMS = mf.load_params()


def eval_b(Kp, Ki, Kq, b, verbose=False):
    worst_settle = 0.0
    worst_over = 0.0
    worst_elev = 0.0
    any_diverged = False
    per_speed = {}
    for spd in SPEEDS:
        sim = nlsim.simulate(spd, Kp, Ki, Kq, b, params=_PARAMS)
        per_speed[spd] = sim
        worst_settle = max(worst_settle, sim["settling_time_s"])
        worst_over = max(worst_over, sim["overshoot_pct"])
        worst_elev = max(worst_elev, sim["max_elevator_deg"])
        any_diverged = any_diverged or sim["diverged"]
        if verbose:
            print(f"  b={b:.3f} spd={spd}: settle={sim['settling_time_s']:.3f}s "
                  f"over={sim['overshoot_pct']:.2f}% elev={sim['max_elevator_deg']:.2f}deg "
                  f"diverged={sim['diverged']}")
    ok = (not any_diverged) and worst_over <= 10.0 and worst_elev <= 25.0 and worst_settle <= 6.0
    return dict(worst_settle=worst_settle, worst_over=worst_over, worst_elev=worst_elev,
                ok=ok, per_speed=per_speed)


def scan(Kp, Ki, Kq, b_values=None, verbose=True):
    if b_values is None:
        b_values = np.round(np.arange(0.0, 1.001, 0.05), 3)
    results = []
    for b in b_values:
        r = eval_b(Kp, Ki, Kq, float(b))
        results.append((float(b), r))
        if verbose:
            print(f"b={b:.3f}  ok={r['ok']}  worst_settle={r['worst_settle']:.3f}s "
                  f"worst_over={r['worst_over']:.2f}%  worst_elev={r['worst_elev']:.2f}deg")
    feasible = [(b, r) for b, r in results if r["ok"]]
    if feasible:
        best = min(feasible, key=lambda br: br[1]["worst_settle"])
        print("BEST feasible b:", best[0], "worst_settle", best[1]["worst_settle"])
    else:
        print("NO feasible b found in scan range")
    return results


if __name__ == "__main__":
    import sys
    Kp, Ki, Kq = (float(x) for x in sys.argv[1:4]) if len(sys.argv) >= 4 else (-1.0, -0.5, -0.5)
    scan(Kp, Ki, Kq)
