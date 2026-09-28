"""Reference design for version 2: one set of gains for 20, 25 and 32 m/s, on the grader's truth model.

Minimizes the worst 2% settling time over the three airspeeds (nonlinear aircraft), with differential evolution
(fixed seed). The search keeps a small reserve beyond each limit: 2 deg of phase margin, 0.5 dB of gain margin, one
point of overshoot and 1 deg of elevator. Writes controller.json and report.json in this folder.

    python design_reference.py        about ten minutes on 10 cores
"""
import json
import pathlib
import sys

import numpy as np
from scipy.optimize import differential_evolution
from scipy.stats import qmc

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "grader"))
import truth_model as tm  # noqa: E402

SPEEDS = tm.SPEC["speeds_m_s"]
PLANTS = {V: tm.load_plant(V) for V in SPEEDS}
W_COARSE = np.logspace(-3, 3, 20001)
BOUNDS = [(-8.0, 0.0), (-20.0, 0.0), (-0.8, 0.0), (0.0, 1.0)]  # K_p, K_i, K_q, b; negative gains, see the README
START = [-2.0538, -4.3754, -0.1008, 0.1906]  # best design on the linear models, used as one starting member


def cost(z):
    c = dict(K_p=z[0], K_i=z[1], K_q=z[2], b=z[3])
    penalty = 0.0
    for V in SPEEDS:
        m = tm.margins(PLANTS[V], c, w=W_COARSE)
        penalty += (10 * max(0.0, 47.0 - m["pm_deg"]) + 30 * max(0.0, 6.5 - m["gm_db"])
                    + 30 * max(0.0, 6.5 - m["gm_low_db"]))
    if penalty > 50:
        return 100 + penalty
    worst = 0.0
    for V in SPEEDS:
        met = tm.step_metrics(tm.simulate(V, c))
        if met["diverged"] or not np.isfinite(met["settling_time_s"]):
            return 100 + penalty
        penalty += 5 * max(0.0, met["overshoot_pct"] - 9.0) + 5 * max(0.0, met["max_elevator_deg"] - 24.0)
        worst = max(worst, met["settling_time_s"])
    return worst + penalty


def main():
    lo, hi = np.array([b[0] for b in BOUNDS]), np.array([b[1] for b in BOUNDS])
    init = qmc.scale(qmc.LatinHypercube(d=4, seed=1).random(47), lo, hi)
    init = np.vstack([init, START])
    r = differential_evolution(cost, BOUNDS, seed=1, init=init, maxiter=30, tol=1e-6, polish=False, workers=10,
                               updating="deferred")
    ctrl = {k: round(float(v), 4) for k, v in zip(("K_p", "K_i", "K_q", "b"), r.x)}
    report = {}
    for V in SPEEDS:
        m = tm.margins(PLANTS[V], ctrl)
        met = tm.step_metrics(tm.simulate(V, ctrl))
        report[f"{V:g}"] = {"phase_margin_deg": round(m["pm_deg"], 2), "gain_margin_db": round(m["gm_db"], 2),
                            "overshoot_pct": round(met["overshoot_pct"], 2),
                            "settling_time_s": round(met["settling_time_s"], 3),
                            "max_elevator_deg": round(met["max_elevator_deg"], 2)}
    (HERE / "controller.json").write_text(json.dumps(ctrl, indent=2) + "\n", encoding="utf-8")
    (HERE / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("controller:", ctrl)
    for V, rep in report.items():
        print(f"  {V} m/s:", rep)
    print(f"worst settling time: {max(r['settling_time_s'] for r in report.values()):.3f} s (cost {r.fun:.3f})")


if __name__ == "__main__":
    main()
