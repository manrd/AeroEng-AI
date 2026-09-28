"""Given a chosen (Kp, Ki, Kq, b), compute the final full-resolution margins and time-domain
metrics, check every requirement R1-R5, and write solution/controller.json and
solution/report.json.
"""
import sys
import json
import pathlib

sys.path.insert(0, "work")
import numpy as np
import core

SOLUTION = pathlib.Path(__file__).parent.parent / "solution"


def evaluate_full(Kp, Ki, Kq, b, n_margin=200001, verbose=True):
    num_theta, den_theta = core.theta_tf()
    margins = core.compute_margins(Kp, Ki, Kq, num_theta, den_theta, n=n_margin)
    sim = core.simulate(Kp, Ki, Kq, b)
    metrics = core.metrics_from_sim(sim)

    checks = {
        "R1_stable": metrics["settling_time_s"] < 20.0 and np.all(np.isfinite(sim["theta"])) and abs(sim["theta"][-1] - sim["theta_cmd"]) < 1e-3,
        "R2_phase_margin": margins["phase_margin_deg"] >= 45.0,
        "R2_gain_margin_incr": margins["gain_margin_incr_db"] >= 6.0,
        "R2_gain_margin_decr": margins["gain_margin_decr_db"] >= 6.0,
        "R3_overshoot": metrics["theta_max_deg"] <= 5.5 + 1e-9,
        "R4_elevator": metrics["max_elevator_deg"] <= 25.0 + 1e-9,
        "R5_settling": metrics["settling_time_s"] <= 4.0 + 1e-9,
    }
    if verbose:
        print(f"Kp={Kp:.6f} Ki={Ki:.6f} Kq={Kq:.6f} b={b:.6f}")
        print(f"  phase_margin_deg   = {margins['phase_margin_deg']:.4f}   (>=45 required)")
        print(f"  gain_margin_incr_dB= {margins['gain_margin_incr_db']:.4f}   (>=6 required)")
        print(f"  gain_margin_decr_dB= {margins['gain_margin_decr_db']:.4f}   (>=6 required if applicable)")
        print(f"  overshoot_pct      = {metrics['overshoot_pct']:.4f}   theta_max_deg={metrics['theta_max_deg']:.4f} (<=5.5 required)")
        print(f"  settling_time_s    = {metrics['settling_time_s']:.4f}   (<=4.0 required)")
        print(f"  max_elevator_deg   = {metrics['max_elevator_deg']:.4f}   (<=25 required)")
        print(f"  checks: {checks}")
        print(f"  all pass: {all(checks.values())}")
    return margins, metrics, checks


def write_solution(Kp, Ki, Kq, b, margins, metrics):
    SOLUTION.mkdir(exist_ok=True)
    controller = {"K_p": Kp, "K_i": Ki, "K_q": Kq, "b": b}
    (SOLUTION / "controller.json").write_text(json.dumps(controller, indent=2), encoding="utf-8")

    def fin(x, cap=999.0):
        if not np.isfinite(x):
            return cap
        return float(x)

    report = {
        "phase_margin_deg": fin(margins["phase_margin_deg"]),
        "gain_margin_db": fin(margins["gain_margin_incr_db"]),
        "overshoot_pct": float(metrics["overshoot_pct"]),
        "settling_time_s": float(metrics["settling_time_s"]),
        "max_elevator_deg": float(metrics["max_elevator_deg"]),
    }
    (SOLUTION / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return controller, report


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("Kp", type=float)
    ap.add_argument("Ki", type=float)
    ap.add_argument("Kq", type=float)
    ap.add_argument("b", type=float)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    margins, metrics, checks = evaluate_full(args.Kp, args.Ki, args.Kq, args.b)
    if args.write:
        write_solution(args.Kp, args.Ki, args.Kq, args.b, margins, metrics)
        print("wrote solution/controller.json and solution/report.json")
