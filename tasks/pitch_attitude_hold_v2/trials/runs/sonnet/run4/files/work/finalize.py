"""Given final (Kp, Ki, Kq, b), compute every report.json field with independent, from-scratch
recomputation (exact frequency response for R2, full nonlinear RK4 sim for R1/R3/R4/R5), print a
pass/fail summary against every requirement, and write solution/controller.json + report.json.
NOTES.md is written separately (by hand) once the numbers are final.
"""
import json
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).parent
SOLUTION = HERE.parent / "solution"

import loopgain as lg
import nlsim


def evaluate(Kp, Ki, Kq, b, verbose=True):
    report = {}
    all_ok = True
    for spd in (20, 25, 32):
        plant = lg.load_plant(spd)
        L = lg.loop_L(lg.GRADER_OMEGA, Kp, Ki, Kq, plant)
        mrep = lg.margins_report_fast(lg.GRADER_OMEGA, L)
        pm = mrep["phase_margin_deg"]
        gm = mrep["gain_margin_db"]
        ok_pm = mrep["ok_pm45"]
        ok_gm_inc = mrep["ok_gm6_increase"]
        ok_gm_dec = mrep["ok_gm6_decrease"]
        n_gc = len(mrep["gain_crossings"])

        sim = nlsim.simulate(spd, Kp, Ki, Kq, b)
        r1 = (not sim["diverged"])
        r3 = sim["overshoot_pct"] <= 10.0 + 1e-9
        r4 = sim["max_elevator_deg"] <= 25.0 + 1e-9
        r5 = sim["settling_time_s"] <= 6.0 + 1e-9
        r2 = ok_pm and ok_gm_inc and ok_gm_dec

        pm_report = 999.0 if pm >= 999.0 else pm
        gm_report = 999.0 if gm >= 999.0 else gm

        report[str(spd)] = dict(
            phase_margin_deg=round(float(pm_report), 4),
            gain_margin_db=round(float(gm_report), 4),
            overshoot_pct=round(float(sim["overshoot_pct"]), 4),
            settling_time_s=round(float(sim["settling_time_s"]), 4),
            max_elevator_deg=round(float(sim["max_elevator_deg"]), 4),
        )

        speed_ok = r1 and r2 and r3 and r4 and r5
        all_ok = all_ok and speed_ok
        if verbose:
            print(f"--- {spd} m/s ---")
            print(f"  PM={pm:.2f} deg (ok45={ok_pm}, n_gain_crossings={n_gc})  "
                  f"GM={gm:.2f} dB (ok_inc={ok_gm_inc}, ok_dec={ok_gm_dec})")
            print(f"  diverged={sim['diverged']} ({sim['diverge_reason']})")
            print(f"  overshoot={sim['overshoot_pct']:.3f}% (R3 max theta {sim['max_theta_deg']:.4f} deg)")
            print(f"  max |elevator cmd|={sim['max_elevator_deg']:.3f} deg (R4)")
            print(f"  settling_time={sim['settling_time_s']:.4f} s (R5)")
            print(f"  R1={r1} R2={r2} R3={r3} R4={r4} R5={r5}  -> speed_ok={speed_ok}")
    if verbose:
        print("ALL OK:", all_ok)
        worst_settle = max(report[k]["settling_time_s"] for k in report)
        print("worst settling time:", worst_settle)
    return report, all_ok


def write_solution(Kp, Ki, Kq, b):
    report, all_ok = evaluate(Kp, Ki, Kq, b)
    SOLUTION.mkdir(exist_ok=True)
    (SOLUTION / "controller.json").write_text(
        json.dumps({"K_p": Kp, "K_i": Ki, "K_q": Kq, "b": b}, indent=2), encoding="utf-8")
    (SOLUTION / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("wrote controller.json and report.json; all_ok =", all_ok)
    return report, all_ok


if __name__ == "__main__":
    Kp, Ki, Kq, b = 0.3, 0.9, 2.5, 0.6
    if len(sys.argv) >= 5:
        Kp, Ki, Kq, b = (float(x) for x in sys.argv[1:5])
    write_solution(Kp, Ki, Kq, b)
