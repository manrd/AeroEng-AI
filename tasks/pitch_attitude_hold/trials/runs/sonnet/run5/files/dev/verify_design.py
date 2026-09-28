"""Full compliance check (R1-R5) for a chosen (Kp, Ki, Kq, b), replicating the grader's methods."""
import sys
sys.path.insert(0, "dev")
import model as m
import numpy as np


def report(Kp, Ki, Kq, b, label=""):
    print(f"=== {label} Kp={Kp:.6f} Ki={Ki:.6f} Kq={Kq:.6f} b={b:.6f} ===")
    res = m.margins(Kp, Ki, Kq, return_all=True)
    sim = m.simulate(Kp, Ki, Kq, b)
    met = m.metrics(sim)
    maxreal = m.closed_loop_max_real_part(Kp, Ki, Kq)

    r1 = maxreal < 0
    r2 = (res["pm_deg"] >= 45.0 and res["gm_increase_db"] >= 6.0 and res["gm_decrease_db"] >= 6.0)
    r3 = met["overshoot_pct"] <= 10.0
    r4 = met["max_elevator_deg"] <= 25.0
    r5 = met["settling_time_s"] <= 4.0

    print(f"R1 stable: max closed-loop pole real part = {maxreal:.6f}  -> {'PASS' if r1 else 'FAIL'}")
    print(f"R2 margins: PM={res['pm_deg']:.3f} deg (n_gain_cross={res['n_gain_cross']}), "
          f"GM_inc={res['gm_increase_db']:.3f} dB, GM_dec={res['gm_decrease_db']:.3f} dB "
          f"(n_phase_cross={res['n_phase_cross']}) -> {'PASS' if r2 else 'FAIL'}")
    print(f"R3 overshoot: {met['overshoot_pct']:.3f} % (peak theta = {met['peak_theta_deg']:.4f} deg) "
          f"-> {'PASS' if r3 else 'FAIL'}")
    print(f"R4 max |elevator cmd|: {met['max_elevator_deg']:.3f} deg "
          f"(actual surface peak {met['max_elevator_actual_deg']:.3f} deg) -> {'PASS' if r4 else 'FAIL'}")
    print(f"R5 settling time (2%): {met['settling_time_s']:.4f} s -> {'PASS' if r5 else 'FAIL'}")
    for band in (0.019 * 5.0, 0.02 * 5.0, 0.021 * 5.0):
        mb = m.metrics(sim, band=band)
        print(f"    settling time at band={band:.4f} deg: {mb['settling_time_s']:.4f} s")
    print()
    return dict(res=res, met=met, maxreal=maxreal, all_pass=(r1 and r2 and r3 and r4 and r5))


if __name__ == "__main__":
    import ast
    args = sys.argv[1:]
    if args:
        Kp, Ki, Kq, b = map(float, args[:4])
        report(Kp, Ki, Kq, b, label="cli")
