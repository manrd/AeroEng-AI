import json
import sys
import numpy as np
from common import ROOT
from evaluate import full_eval

SOLUTION = ROOT / "solution"


def write_solution(Kp, Ki, Kq, b):
    out = full_eval(Kp, Ki, Kq, b, verbose=True)

    gm_inc = out["worst_gm_inc"]
    gm_report = 999 if gm_inc is None else gm_inc
    pm_report = 999 if out["worst_pm"] is None else out["worst_pm"]

    controller = {"K_p": Kp, "K_i": Ki, "K_q": Kq, "b": b}
    report = {
        "phase_margin_deg": pm_report,
        "gain_margin_db": gm_report,
        "overshoot_pct": out["overshoot_pct"],
        "settling_time_s": out["settling_time_s"],
        "max_elevator_deg": out["max_elevator_deg"],
    }

    SOLUTION.mkdir(exist_ok=True)
    (SOLUTION / "controller.json").write_text(json.dumps(controller, indent=2), encoding="utf-8")
    (SOLUTION / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("wrote", SOLUTION / "controller.json")
    print("wrote", SOLUTION / "report.json")
    print(json.dumps(controller, indent=2))
    print(json.dumps(report, indent=2))
    return out


if __name__ == "__main__":
    Kp, Ki, Kq, b = [float(v) for v in sys.argv[1:5]]
    write_solution(Kp, Ki, Kq, b)
