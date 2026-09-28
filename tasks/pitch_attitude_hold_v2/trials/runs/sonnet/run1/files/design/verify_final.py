"""One-shot full verification of a candidate (Kp, Ki, Kq, b): exact-delay margins on the full
200001-point grid, full 20 s nonlinear run, and the Pade closed-loop-eigenvalue cross-check. Prints a
clear per-requirement pass/fail table for all three airspeeds.
"""
import sys
import numpy as np
from loop import load_plant, loop_gain, find_margins, OMEGA_GRID
from nlsim import simulate, metrics
from padecheck import closed_loop_eigs
import aircraft_model as am


def verify(Kp, Ki, Kq, b):
    p = am.load_params()
    all_ok = True
    print(f"=== Kp={Kp} Ki={Ki} Kq={Kq} b={b} ===")
    worst_settle = -1.0
    for va in (20, 25, 32):
        A, B, C, trim = load_plant(va)
        L = loop_gain(Kp, Ki, Kq, A, B, C, OMEGA_GRID)
        GM_db, PM_deg, wpc, wgc = find_margins(L, OMEGA_GRID)
        worst_gm = np.min(np.abs(GM_db)) if len(GM_db) else np.inf
        worst_pm = np.min(PM_deg) if len(PM_deg) else np.inf
        pos = GM_db[GM_db > 0]
        gm_report = np.min(pos) if len(pos) else 999.0

        eigs = closed_loop_eigs(Kp, Ki, Kq, A, B, C, n_pade=12)
        max_eig_re = np.max(eigs.real)

        out = simulate(Kp, Ki, Kq, b, va, p=p)
        m = metrics(out)
        worst_settle = max(worst_settle, m["settling_time_s"])

        r2_ok = worst_gm >= 6.0 and worst_pm >= 45.0
        r1_ok = (not m["diverged"]) and max_eig_re < 0
        r3_ok = m["overshoot_pct"] <= 10.0
        r4_ok = m["max_elevator_deg"] <= 25.0
        r5_ok = m["settling_time_s"] <= 6.0
        ok = r1_ok and r2_ok and r3_ok and r4_ok and r5_ok
        all_ok = all_ok and ok

        print(f"--- va={va} ---")
        print(f"  R1 stable: nonlinear diverged={m['diverged']}  Pade max Re(eig)={max_eig_re:.4f}  -> {r1_ok}")
        print(f"  R2 margins: worst GM={worst_gm:.2f} dB (>=6)  worst PM={worst_pm:.2f} deg (>=45) -> {r2_ok}")
        print(f"      report gain_margin_db (vs increase)={gm_report:.3f}  phase_margin_deg={worst_pm:.3f}")
        print(f"      n_phase_crossings={len(wpc)} n_gain_crossings={len(wgc)}")
        print(f"  R3 overshoot: {m['overshoot_pct']:.3f}% (<=10) -> {r3_ok}")
        print(f"  R4 max elevator: {m['max_elevator_deg']:.3f} deg (<=25) -> {r4_ok}")
        print(f"  R5 settling time: {m['settling_time_s']:.3f} s (<=6.0) -> {r5_ok}")
        print(f"  ALL OK for va={va}: {ok}")
    print(f"=== worst-of-3 settling time: {worst_settle:.3f} s   ALL REQUIREMENTS OK: {all_ok} ===")
    return all_ok, worst_settle


if __name__ == "__main__":
    Kp, Ki, Kq, b = (float(x) for x in sys.argv[1:5]) if len(sys.argv) >= 5 else (-2.0, -4.0, -0.10, 0.25)
    verify(Kp, Ki, Kq, b)
