"""Given final Kp,Ki,Kq,b: run full checks and write solution/controller.json + solution/report.json."""
import sys
import json
import pathlib
import numpy as np
sys.path.insert(0, ".")
from evaluate import evaluate, passes

SOL = pathlib.Path("..") / "solution"


def finalize(Kp, Ki, Kq, b, write=True):
    out, m, res = evaluate(Kp, Ki, Kq, b, verbose=True)
    ok, reasons = passes(out)
    print("\nPASS" if ok else f"\nFAIL: {reasons}")
    print("n_gain_crossovers:", m["n_gain_crossovers"], "n_phase_crossovers:", m["n_phase_crossovers"])
    print("phase margins @ crossovers:", m["phase_margins"])
    print("gain crossings (w, dB) near 0:",
          [(w, g) for w, g in m["gain_crossings"] if abs(g) < 20])

    controller = {"K_p": Kp, "K_i": Ki, "K_q": Kq, "b": b}
    report = {
        "phase_margin_deg": out["phase_margin_deg"],
        "gain_margin_db": out["gain_margin_up_db"],
        "overshoot_pct": out["overshoot_pct"],
        "settling_time_s": out["settling_time_s"],
        "max_elevator_deg": out["max_elevator_deg"],
    }
    if write:
        SOL.mkdir(exist_ok=True)
        (SOL / "controller.json").write_text(json.dumps(controller, indent=2), encoding="utf-8")
        (SOL / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("\nwrote", SOL / "controller.json")
        print("wrote", SOL / "report.json")
    return out, m, res, ok, reasons


if __name__ == "__main__":
    Kp, Ki, Kq, b = map(float, sys.argv[1:5])
    finalize(Kp, Ki, Kq, b)
