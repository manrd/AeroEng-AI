"""Build solution/controller.json and solution/report.json from a chosen (Kp, Ki, Kq, b), using:
  - the exact 200001-point log-spaced frequency grid (0.001 to 1000 rad/s) for phase/gain margins
    (matches the grader's frequency-domain method exactly: e^{-s tau} for the delay, no Pade approx);
  - the exact nonlinear RK4/actuator/delay discretisation (nlsim.py) for overshoot, settling time and
    peak elevator command.
"""
import json
import pathlib
import numpy as np

from loop import load_plant, loop_gain, find_margins, OMEGA_GRID
from nlsim import simulate, metrics
import aircraft_model as am

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOLDIR = ROOT / "solution"


def build_report(Kp, Ki, Kq, b, verbose=True):
    p = am.load_params()
    report = {}
    lin = {}
    for va in (20, 25, 32):
        A, B, C, trim = load_plant(va)
        L = loop_gain(Kp, Ki, Kq, A, B, C, OMEGA_GRID)
        GM_db, PM_deg, wpc, wgc = find_margins(L, OMEGA_GRID)
        # gain margin against an increase: among phase crossings where |L|<1 (GM_db>0), the smallest;
        # if none exist (no crossing with |L|<1) report 999 (infinite).
        pos = GM_db[GM_db > 0]
        gm_incr = float(np.min(pos)) if len(pos) else 999.0
        pm = float(np.min(PM_deg)) if len(PM_deg) else 999.0

        out = simulate(Kp, Ki, Kq, b, va, p=p)
        m = metrics(out)

        report[str(va)] = {
            "phase_margin_deg": round(pm, 4),
            "gain_margin_db": round(gm_incr, 4),
            "overshoot_pct": round(float(m["overshoot_pct"]), 4),
            "settling_time_s": round(float(m["settling_time_s"]), 4),
            "max_elevator_deg": round(float(m["max_elevator_deg"]), 4),
        }
        lin[va] = dict(GM_db=GM_db, PM_deg=PM_deg, wpc=wpc, wgc=wgc, diverged=m["diverged"])
        if verbose:
            print(f"va={va}: {report[str(va)]}")
            print(f"   all phase-crossing GM_db: {np.round(GM_db,3)}")
            print(f"   all gain-crossing PM_deg: {np.round(PM_deg,3)}")
            print(f"   diverged={m['diverged']}")
    return report, lin


def check_requirements(report, lin):
    ok = True
    msgs = []
    for va in (20, 25, 32):
        r = report[str(va)]
        d = lin[va]
        if d["diverged"]:
            ok = False
            msgs.append(f"va={va}: R1 FAIL nonlinear diverged")
        if len(d["GM_db"]) and np.min(np.abs(d["GM_db"])) < 6.0 - 1e-9:
            ok = False
            msgs.append(f"va={va}: R2 FAIL gain margin {np.min(np.abs(d['GM_db'])):.3f} dB < 6 dB")
        if len(d["PM_deg"]) and np.min(d["PM_deg"]) < 45.0 - 1e-9:
            ok = False
            msgs.append(f"va={va}: R2 FAIL phase margin {np.min(d['PM_deg']):.3f} deg < 45 deg")
        if r["overshoot_pct"] > 10.0:
            ok = False
            msgs.append(f"va={va}: R3 FAIL overshoot {r['overshoot_pct']:.3f}% > 10%")
        if r["max_elevator_deg"] > 25.0:
            ok = False
            msgs.append(f"va={va}: R4 FAIL max elevator {r['max_elevator_deg']:.3f} deg > 25 deg")
        if r["settling_time_s"] > 6.0:
            ok = False
            msgs.append(f"va={va}: R5 FAIL settling time {r['settling_time_s']:.3f} s > 6.0 s")
    return ok, msgs


def write_solution(Kp, Ki, Kq, b):
    report, lin = build_report(Kp, Ki, Kq, b)
    ok, msgs = check_requirements(report, lin)
    print("REQUIREMENTS OK:", ok)
    for m in msgs:
        print("  ", m)

    SOLDIR.mkdir(exist_ok=True)
    controller = {"K_p": Kp, "K_i": Ki, "K_q": Kq, "b": b}
    (SOLDIR / "controller.json").write_text(json.dumps(controller, indent=2) + "\n", encoding="utf-8")
    (SOLDIR / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("wrote", SOLDIR / "controller.json")
    print("wrote", SOLDIR / "report.json")
    return report, lin, ok


if __name__ == "__main__":
    import sys
    Kp, Ki, Kq, b = -2.0, -4.0, -0.15, 0.30
    write_solution(Kp, Ki, Kq, b)
