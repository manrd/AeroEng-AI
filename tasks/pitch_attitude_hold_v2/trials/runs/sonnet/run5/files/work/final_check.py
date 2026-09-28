import sys
sys.path.insert(0, "<run>/work")
import json
import numpy as np
from lib import PLANTS, SPEEDS, loop_response, simulate, metrics_from_sim, freq_grid
from margins_fast import analyze_margins

Kp, Ki, Kq, b = -2.0, -4.15, -0.1, 0.1

w = freq_grid(200001, 0.001, 1000.0)  # exact grader spec

print(f"FINAL CANDIDATE: Kp={Kp} Ki={Ki} Kq={Kq} b={b}")
print(f"frequency grid: {len(w)} points, {w[0]} to {w[-1]} rad/s")
print()

report = {}
for spd in SPEEDS:
    pl = PLANTS[spd]
    L = loop_response(pl, w, Kp, Ki, Kq)
    m = analyze_margins(w, L)
    print(f"--- {spd} m/s : frequency domain ---")
    print(f"  gain crossovers (rad/s): {m['gc_w']}")
    print(f"  PM at each: {m['pm_deg']}")
    print(f"  phase/gain-margin crossovers (rad/s): {m['pc_w']}")
    print(f"  gain (dB) at each: {m['pc_gain_db']}")
    print(f"  -> worst PM = {m['worst_pm_deg']:.3f} deg")
    print(f"  -> GM against increase = {m['gm_against_increase_db']:.3f} dB")
    print(f"  -> GM against decrease OK = {m['gm_against_decrease_ok']}  (worst if any: {m['gm_against_decrease_worst_db']:.3f} dB)")

    sim = simulate(spd, Kp, Ki, Kq, b)
    met = metrics_from_sim(sim)
    print(f"--- {spd} m/s : nonlinear time domain ---")
    print(f"  overshoot = {met['overshoot_pct']:.4f} %")
    print(f"  settling time = {met['settling_time_s']:.4f} s")
    print(f"  max |elevator cmd| = {met['max_elevator_deg']:.4f} deg")
    print(f"  diverged = {met['diverged']}")
    print()

    report[str(spd)] = {
        "phase_margin_deg": round(float(m["worst_pm_deg"]), 4),
        "gain_margin_db": round(float(m["gm_against_increase_db"]), 4),
        "overshoot_pct": round(float(met["overshoot_pct"]), 4),
        "settling_time_s": round(float(met["settling_time_s"]), 4),
        "max_elevator_deg": round(float(met["max_elevator_deg"]), 4),
    }

print(json.dumps(report, indent=2))

with open("<run>/work/final_report_draft.json", "w") as f:
    json.dump(report, f, indent=2)
