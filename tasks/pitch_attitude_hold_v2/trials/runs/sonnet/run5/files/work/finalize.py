"""Given final gains, run the full-rigor check (200001-pt grid + nonlinear sim) and write
solution/controller.json and solution/report.json. Prints a pass/fail summary against every
requirement with the safety buffers used during design, for a final human sanity check.
"""
import sys
sys.path.insert(0, "<run>/work")
import json
import numpy as np
from lib import PLANTS, SPEEDS, loop_response, simulate, metrics_from_sim, freq_grid
from margins_fast import analyze_margins

SOL = "<run>/solution"


def finalize(Kp, Ki, Kq, b, write=True):
    w = freq_grid(200001, 0.001, 1000.0)
    report = {}
    all_ok = True
    worst_settle = -1.0
    print(f"Kp={Kp} Ki={Ki} Kq={Kq} b={b}")
    for spd in SPEEDS:
        pl = PLANTS[spd]
        L = loop_response(pl, w, Kp, Ki, Kq)
        m = analyze_margins(w, L)
        sim = simulate(spd, Kp, Ki, Kq, b)
        met = metrics_from_sim(sim)
        pm, gm = m["worst_pm_deg"], m["gm_against_increase_db"]
        dec_ok = m["gm_against_decrease_ok"]
        r1 = (not met["diverged"])
        r2 = (pm >= 45.0 and gm >= 6.0 and dec_ok)
        r3 = met["overshoot_pct"] <= 10.0
        r4 = met["max_elevator_deg"] <= 25.0
        r5 = met["settling_time_s"] <= 6.0
        ok = r1 and r2 and r3 and r4 and r5
        all_ok = all_ok and ok
        worst_settle = max(worst_settle, met["settling_time_s"])
        print(f"  {spd} m/s: PM={pm:7.3f}(buf {pm-45:+6.2f}) GM={gm:6.3f}dB(buf {gm-6:+5.2f}) "
              f"dec_ok={dec_ok}  overshoot={met['overshoot_pct']:6.3f}%(buf {10-met['overshoot_pct']:+5.2f}) "
              f"settle={met['settling_time_s']:6.3f}s(buf {6-met['settling_time_s']:+5.3f}) "
              f"max_elev={met['max_elevator_deg']:7.3f}deg(buf {25-met['max_elevator_deg']:+5.2f})  "
              f"R1={r1} R2={r2} R3={r3} R4={r4} R5={r5}  {'PASS' if ok else 'FAIL'}")
        report[str(spd)] = {
            "phase_margin_deg": round(float(pm), 4),
            "gain_margin_db": round(float(gm), 4),
            "overshoot_pct": round(float(met["overshoot_pct"]), 4),
            "settling_time_s": round(float(met["settling_time_s"]), 4),
            "max_elevator_deg": round(float(met["max_elevator_deg"]), 4),
        }
    print(f"ALL_OK={all_ok}  worst_settle={worst_settle:.3f}s")
    if write and all_ok:
        with open(f"{SOL}/controller.json", "w") as f:
            json.dump({"K_p": Kp, "K_i": Ki, "K_q": Kq, "b": b}, f, indent=2)
            f.write("\n")
        with open(f"{SOL}/report.json", "w") as f:
            json.dump(report, f, indent=2)
            f.write("\n")
        print("WROTE solution/controller.json and solution/report.json")
    elif write:
        print("NOT WRITTEN: a requirement failed.")
    return all_ok, worst_settle, report


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("Kp", type=float)
    ap.add_argument("Ki", type=float)
    ap.add_argument("Kq", type=float)
    ap.add_argument("b", type=float)
    ap.add_argument("--nowrite", action="store_true")
    args = ap.parse_args()
    finalize(args.Kp, args.Ki, args.Kq, args.b, write=not args.nowrite)
