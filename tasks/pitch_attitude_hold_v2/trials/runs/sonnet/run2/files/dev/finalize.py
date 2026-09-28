"""Final assembly: given Kp, Ki, Kq, b, run the OFFICIAL (slow, exact
aircraft_model.derivatives) nonlinear simulation and the exact margin scan at
all three airspeeds, print everything, and write solution/controller.json and
solution/report.json.
"""
import json
import sys

import numpy as np

import core
import margins as margins_mod
import stability_check

SOLUTION = core.RUN_ROOT / "solution"


def run(Kp, Ki, Kq, b, write=True):
    params = core.load_params()
    omega = core.grader_omega_grid()

    report = {}
    all_ok = True
    print(f"Kp={Kp!r} Ki={Ki!r} Kq={Kq!r} b={b!r}\n")
    for spd in core.SPEEDS:
        plant = core.load_plant(spd)
        m = margins_mod.analyze(plant, Kp, Ki, Kq, omega=omega)
        sim = core.simulate(plant, Kp, Ki, Kq, b, params=params)
        t = core.compute_metrics(sim)

        pm = m["phase_margin_deg"]
        gm = m["gain_margin_db"]
        dm = m["decrease_margin_db"]
        os_ = t["overshoot_pct"]
        ts = t["settling_time_s"]
        me = t["max_elevator_deg"]
        div = t["diverged"]

        pade_res = stability_check.check(plant, Kp, Ki, Kq, orders=(12, 24))
        pade_stable = all(worst_real < 0 for worst_real, _ in pade_res.values())
        r1 = (not div) and pade_stable  # stability: no divergence, and Pade-based closed-loop poles all LHP
        r2 = (pm >= 45.0) and (gm >= 6.0) and (dm >= 6.0)
        r3 = os_ <= 10.0 + 1e-9
        r4 = me <= 25.0 + 1e-9
        r5 = ts <= 6.0 + 1e-9
        ok = r1 and r2 and r3 and r4 and r5
        all_ok = all_ok and ok

        print(f"--- {spd:g} m/s ---")
        print(f"  phase_margin_deg   = {pm:.3f}   (R2 pm>=45: {'OK' if pm>=45 else 'FAIL'})")
        print(f"  gain_margin_db     = {gm:.3f}   (R2 gm>=6 : {'OK' if gm>=6 else 'FAIL'})")
        print(f"  decrease_margin_db = {dm:.3f}   (R2 dm>=6 : {'OK' if dm>=6 else 'FAIL'})")
        print(f"  n_gain_crossovers={m['n_gain_crossovers']} n_phase_crossovers={m['n_phase_crossovers']}")
        print(f"  overshoot_pct      = {os_:.4f}  (R3<=10  : {'OK' if r3 else 'FAIL'})")
        print(f"  settling_time_s    = {ts:.4f}  (R5<=6.0 : {'OK' if r5 else 'FAIL'})")
        print(f"  max_elevator_deg   = {me:.4f}  (R4<=25  : {'OK' if r4 else 'FAIL'})")
        print(f"  diverged           = {div}      (R1 nonlinear: {'OK' if not div else 'FAIL'})")
        print(f"  Pade closed-loop poles (orders 12,24) max Re = "
              f"{[round(v[0], 5) for v in pade_res.values()]}  (R1 linear: {'OK' if pade_stable else 'FAIL'})")
        print()

        report[str(int(spd))] = {
            "phase_margin_deg": pm,
            "gain_margin_db": gm if gm < 999 else 999,
            "overshoot_pct": os_,
            "settling_time_s": ts,
            "max_elevator_deg": me,
        }

    worst_ts = max(v["settling_time_s"] for v in report.values())
    print(f"ALL OK: {all_ok}   worst settling_time_s = {worst_ts:.4f}")

    if write:
        SOLUTION.mkdir(exist_ok=True)
        controller = {"K_p": Kp, "K_i": Ki, "K_q": Kq, "b": b}
        (SOLUTION / "controller.json").write_text(json.dumps(controller, indent=2), encoding="utf-8")
        (SOLUTION / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("\nwrote", SOLUTION / "controller.json")
        print("wrote", SOLUTION / "report.json")

    return all_ok, report, worst_ts


if __name__ == "__main__":
    Kp, Ki, Kq, b = [float(v) for v in sys.argv[1:5]]
    write = (len(sys.argv) <= 5) or (sys.argv[5] != "nowrite")
    run(Kp, Ki, Kq, b, write=write)
