"""Reference design: the gains that minimize settling time with a margin kept on every requirement.

Searches K_p, K_i, K_q and b with differential evolution (fixed seed) on the grader's truth model. The search keeps
2 deg of phase margin, 0.5 dB of gain margin and 1 point of overshoot in hand, so the reference passes with room
to spare. Writes controller.json and report.json in this folder, with the grader's recomputed numbers.

    python design_reference.py        takes about one minute on 10 cores
"""
import json
import pathlib
import sys

import numpy as np
from scipy.optimize import differential_evolution

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "grader"))
import truth_model as tm  # noqa: E402

PLANT = tm.load_plant()
W_COARSE = np.logspace(-3, 3, 20001)
BOUNDS = [(-8.0, 0.0), (-20.0, 0.0), (-0.8, 0.0), (0.0, 1.0)]  # K_p, K_i, K_q, b; negative gains, see the README


def cost(z):
    c = dict(K_p=z[0], K_i=z[1], K_q=z[2], b=z[3])
    m = tm.margins(PLANT, c, w=W_COARSE)
    penalty = (10 * max(0.0, 47.0 - m["pm_deg"]) + 30 * max(0.0, 6.5 - m["gm_db"])
               + 30 * max(0.0, 6.5 - m["gm_low_db"]))
    if penalty > 50:
        return 100 + penalty
    met = tm.step_metrics(tm.simulate(PLANT, c))
    if met["diverged"] or not np.isfinite(met["settling_time_s"]):
        return 100 + penalty
    penalty += 5 * max(0.0, met["overshoot_pct"] - 9.0) + 50 * met["position_limited_s"]
    return met["settling_time_s"] + penalty


def main():
    r = differential_evolution(cost, BOUNDS, seed=1, popsize=12, maxiter=40, tol=1e-6, polish=False,
                               workers=10, updating="deferred")
    ctrl = {k: round(float(v), 4) for k, v in zip(("K_p", "K_i", "K_q", "b"), r.x)}
    m = tm.margins(PLANT, ctrl)
    met = tm.step_metrics(tm.simulate(PLANT, ctrl))
    report = {"phase_margin_deg": round(m["pm_deg"], 2), "gain_margin_db": round(m["gm_db"], 2),
              "overshoot_pct": round(met["overshoot_pct"], 2), "settling_time_s": round(met["settling_time_s"], 3),
              "max_elevator_deg": round(met["max_elevator_deg"], 2)}
    (HERE / "controller.json").write_text(json.dumps(ctrl, indent=2) + "\n", encoding="utf-8")
    (HERE / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("controller:", ctrl)
    print("report:", report)
    print(f"crossover {m['crossover_rad_s']} rad/s; rate limited {met['rate_limited_s']:.3f} s; "
          f"airspeed change {met['max_u_change_m_s']:.2f} m/s")


if __name__ == "__main__":
    main()
