"""Final verification of a candidate gain set against all requirements (R1-R5), using the exact
grader methods described in README.md:
  - frequency domain: exact e^{-s tau} delay, 200001-point log grid 0.001..1000 rad/s (R1, R2)
  - time domain: nonlinear model, RK4 fixed 1 ms step, exact actuator/delay/integrator discretization,
    full 20 s (R1, R3, R4, R5)
Also runs an independent long-horizon linear time-domain check as a second confirmation of R1.
"""
import json
import sys

import freq as fq
import nlsim

SPEEDS = (20, 25, 32)


def verify(Kp, Ki, Kq, b, verbose=True):
    params = nlsim.load_params()
    report = {}
    all_ok = True
    reasons = []

    for s in SPEEDS:
        plant_fq = fq.load_plant(s)
        num, den = fq.theta_tf(plant_fq)
        fres = fq.evaluate(plant_fq, Kp, Ki, Kq, b, num=num, den=den, w=fq.W_GRID)

        plant_nl = nlsim.load_plant(s)
        gains = {"K_p": Kp, "K_i": Ki, "K_q": Kq, "b": b}
        tres = nlsim.run_nonlinear(plant_nl, gains, t_end=20.0, params=params)

        lres = nlsim.run_linear(plant_nl, gains, t_end=60.0)

        pm = fres["phase_margin_deg"]
        gm = fres["gain_margin_db"]
        dec_ok = fres["decrease_margin_ok"]
        os_pct = tres["overshoot_pct"]
        settle = tres["settling_time_s"]
        maxelev = tres["max_elevator_deg"]
        diverged = tres["diverged"]
        lin_bounded = lres["max_abs_theta_deg"] < 100.0  # generous; real check is decay/boundedness

        r1 = (not diverged) and (pm > 0) and (gm > 0) and lin_bounded
        r2 = (pm >= 45.0) and (gm >= 6.0) and dec_ok
        r3 = os_pct <= 10.0
        r4 = maxelev <= 25.0
        r5 = settle <= 6.0

        ok = r1 and r2 and r3 and r4 and r5
        all_ok = all_ok and ok
        if not ok:
            reasons.append(f"{s} m/s: R1={r1} R2={r2}(PM={pm:.2f},GM={gm:.2f},dec_ok={dec_ok}) "
                            f"R3={r3}(OS={os_pct:.2f}) R4={r4}(elev={maxelev:.2f}) R5={r5}(settle={settle:.3f})")

        report[str(s)] = {
            "phase_margin_deg": round(pm, 4),
            "gain_margin_db": round(gm, 4),
            "overshoot_pct": round(os_pct, 4),
            "settling_time_s": round(settle, 4),
            "max_elevator_deg": round(maxelev, 4),
        }
        if verbose:
            print(f"{s} m/s: PM={pm:7.3f} deg  GM={gm:7.3f} dB  dec_ok={dec_ok}  "
                  f"OS={os_pct:7.3f}%  settle={settle:7.4f} s  maxelev={maxelev:7.3f} deg  "
                  f"diverged={diverged}  lin_max|theta|={lres['max_abs_theta_deg']:.3f}deg  "
                  f"lin_final_theta={lres['final_theta_deg']:.4f}deg  R1-R5 OK={ok}")

    if verbose:
        print()
        print("ALL REQUIREMENTS OK:" , all_ok)
        if reasons:
            for r in reasons:
                print("  FAIL:", r)
        worst_settle = max(v["settling_time_s"] for v in report.values())
        print("worst settling_time_s:", worst_settle)

    return all_ok, report, reasons


if __name__ == "__main__":
    if len(sys.argv) >= 5:
        Kp, Ki, Kq, b = (float(x) for x in sys.argv[1:5])
    else:
        Kp, Ki, Kq, b = -2.05, -4.40, -0.12, 0.0
    ok, report, reasons = verify(Kp, Ki, Kq, b)
    print(json.dumps(report, indent=2))
