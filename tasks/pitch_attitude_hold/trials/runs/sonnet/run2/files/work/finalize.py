"""Given final (Kp, Ki, Kq, b), compute the full report on the grader's exact grid/method
and write solution/controller.json and solution/report.json.
"""
import json
import sys
import pathlib

import numpy as np

import lib

SOLUTION = pathlib.Path(__file__).parent.parent / "solution"


def finalize(Kp, Ki, Kq, b):
    r = lib.evaluate(Kp, Ki, Kq, b)
    ok_discrete, max_eig = lib.is_discrete_stable(Kp, Ki, Kq)

    print("=== final gains ===")
    print(f"Kp={Kp!r} Ki={Ki!r} Kq={Kq!r} b={b!r}")
    print("=== requirement check ===")
    for k in ["R1_ok", "R2_ok", "R3_ok", "R4_ok", "R5_ok", "all_ok"]:
        print(k, r[k])
    print("exact discrete linear closed loop stable:", ok_discrete, "max|eig|=", max_eig)
    print("=== report values ===")
    for k in ["phase_margin_deg", "gain_margin_db", "gain_margin_decrease_db",
              "overshoot_pct", "settling_time_s", "max_elevator_deg", "max_elevator_actual_deg"]:
        print(k, r[k])
    print("n_gain_crossings", r["margins_detail"]["n_gain_crossings"],
          "n_phase_crossings", r["margins_detail"]["n_phase_crossings"])

    if not r["all_ok"]:
        print("\n!!! NOT ALL REQUIREMENTS SATISFIED -- refusing to write solution files !!!")
        sys.exit(1)

    controller = {"K_p": Kp, "K_i": Ki, "K_q": Kq, "b": b}
    report = {
        "phase_margin_deg": round(float(r["phase_margin_deg"]), 4),
        "gain_margin_db": round(float(r["gain_margin_db"]), 4),
        "overshoot_pct": round(float(r["overshoot_pct"]), 4),
        "settling_time_s": round(float(r["settling_time_s"]), 4),
        "max_elevator_deg": round(float(r["max_elevator_deg"]), 4),
    }

    SOLUTION.mkdir(exist_ok=True)
    (SOLUTION / "controller.json").write_text(json.dumps(controller, indent=2) + "\n", encoding="utf-8")
    (SOLUTION / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("\nwrote", SOLUTION / "controller.json")
    print("wrote", SOLUTION / "report.json")
    return r


if __name__ == "__main__":
    # placeholder; real invocation happens from an explicit call with chosen gains
    pass
