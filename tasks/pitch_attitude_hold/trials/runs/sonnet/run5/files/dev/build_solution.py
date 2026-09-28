"""Builds solution/controller.json and solution/report.json from the final chosen gains.

NOTES.md is written separately (by hand, describing the method); this script only handles the
two JSON deliverables, computed with the same exact-replica model used throughout the design.
"""
import json
import sys

sys.path.insert(0, "dev")
import model as m

SOLUTION_DIR = m.HERE.parent / "solution"

# ---- FINAL CHOSEN GAINS -----------------------------------------------------------
# Frequency-domain design: gain crossover wc = 11.6 rad/s, integrator corner at wc/5,
# phase margin target 46.6 deg (see dev/search3.py); b bisected so overshoot = 9.30 %.
Kp = -2.6388160739006086
Ki = -6.1220532914494115
Kq = -0.23576487235862442
b = 0.22559658903020807


def main():
    res = m.margins(Kp, Ki, Kq, return_all=True)
    sim = m.simulate(Kp, Ki, Kq, b)
    met = m.metrics(sim)

    controller = {"K_p": Kp, "K_i": Ki, "K_q": Kq, "b": b}

    report = {
        "phase_margin_deg": round(res["pm_deg"], 4),
        "gain_margin_db": round(res["gm_increase_db"], 4),
        "overshoot_pct": round(met["overshoot_pct"], 4),
        "settling_time_s": round(float(met["settling_time_s"]), 4),
        "max_elevator_deg": round(met["max_elevator_deg"], 4),
    }

    print("controller:", json.dumps(controller, indent=2))
    print("report:", json.dumps(report, indent=2))
    print()
    print("gm_decrease_db (not reported, must be >=6):", res["gm_decrease_db"])
    print("n_gain_cross:", res["n_gain_cross"], "n_phase_cross:", res["n_phase_cross"])
    print("max_elevator_actual_deg (post-actuator, sanity):", met["max_elevator_actual_deg"])
    print("peak_theta_deg:", met["peak_theta_deg"])

    (SOLUTION_DIR / "controller.json").write_text(json.dumps(controller, indent=2) + "\n", encoding="utf-8")
    (SOLUTION_DIR / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("\nwrote solution/controller.json and solution/report.json")


if __name__ == "__main__":
    main()
