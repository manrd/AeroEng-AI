"""Builds the deliberately broken solutions in tests/broken/, each one a realistic mistake for this task.

Every case gets controller.json, report.json (what the mistaken agent would claim) and WHY.md. The claims are
computed the way the mistaken agent would compute them, not invented.

    python make_broken.py
"""
import json
import pathlib
import sys

import numpy as np
from scipy.linalg import expm

HERE = pathlib.Path(__file__).resolve().parent
TASK = HERE.parents[1]
sys.path.insert(0, str(TASK / "grader"))
import truth_model as tm  # noqa: E402

SPEEDS = tm.SPEC["speeds_m_s"]
REF = json.loads((TASK / "reference" / "controller.json").read_text(encoding="utf-8"))
REF_REPORT = json.loads((TASK / "reference" / "report.json").read_text(encoding="utf-8"))
V1_GAINS = {"K_p": -2.5925, "K_i": -6.129, "K_q": -0.1815, "b": 0.1486}   # version 1 reference, tuned at 25 m/s only
LINEAR_BEST = {"K_p": -2.0538, "K_i": -4.3754, "K_q": -0.1008, "b": 0.1906}  # best design on the linear models
RUN4_FIRST = {"K_p": -3.999, "K_i": -3.997, "K_q": 2.4118, "b": 1.0}  # trial run 4's margins only optimum (steps 116, 117)


def finite(v):
    return round(float(v), 3) if np.isfinite(v) else 999.0


def linear_sim(plant, ctrl, trim_de=None):
    """The version 1 style simulation on a linear model (what an agent that skips the nonlinear model runs)."""
    spec = tm.SPEC
    dt, n = spec["dt_s"], int(round(spec["horizon_s"] / spec["dt_s"])) + 1
    nd = int(round(spec["delay_s"] / dt))
    A, B = plant["A"], plant["B"]
    M = expm(np.block([[A, B], [np.zeros((1, A.shape[0] + 1))]]) * dt)
    Phi, Gam = M[:4, :4], M[:4, 4:]
    de0 = plant["trim"]["delta_e_rad"] if trim_de is None else trim_de
    lim = np.radians(spec["position_limit_deg"])
    lo, hi = -lim - de0, lim - de0
    rate, tau, ref = np.radians(spec["rate_limit_deg_s"]), spec["tau_actuator_s"], np.radians(spec["step_deg"])
    x, integ, d = np.zeros(4), 0.0, 0.0
    theta, q, cmds = np.zeros(n), np.zeros(n), np.zeros(n)
    for k in range(n):
        theta[k], q[k] = x[3], x[2]
        j = k - nd
        th_m, q_m = (theta[j], q[j]) if j >= 0 else (0.0, 0.0)
        cmd = ctrl["K_p"] * (ctrl["b"] * ref - th_m) + ctrl["K_i"] * integ - ctrl["K_q"] * q_m
        integ += (ref - th_m) * dt
        cmds[k] = cmd
        rdot = min(max((min(max(cmd, lo), hi) - d) / tau, -rate), rate)
        x = Phi @ x + Gam[:, 0] * d
        d = min(max(d + rdot * dt, lo), hi)
    t = np.arange(n) * dt
    out = np.nonzero(np.abs(theta - ref) > spec["band"] * ref)[0]
    ts = float("inf") if len(out) and out[-1] == n - 1 else (float(t[out[-1] + 1]) if len(out) else 0.0)
    return {"overshoot_pct": max(0.0, (theta.max() - ref) / ref * 100), "settling_time_s": ts,
            "max_elevator_deg": float(np.degrees(np.max(np.abs(cmds + de0))))}


def report_linear(ctrl, copy_from=None, trim_from=None):
    """Claims from linear simulations; copy_from copies one airspeed's entry to all three; trim_from uses another
    airspeed's trim deflection for the absolute elevator (the wrong one)."""
    rep = {}
    for V in SPEEDS:
        src = copy_from or V
        plant = tm.load_plant(src)
        trim_de = tm.load_plant(trim_from)["trim"]["delta_e_rad"] if trim_from else None
        met = linear_sim(plant, ctrl, trim_de)
        m = tm.margins(plant, ctrl)
        rep[f"{V:g}"] = {"phase_margin_deg": finite(m["pm_deg"]), "gain_margin_db": finite(m["gm_db"]),
                         "overshoot_pct": round(met["overshoot_pct"], 2), "settling_time_s": finite(met["settling_time_s"]),
                         "max_elevator_deg": round(met["max_elevator_deg"], 2)}
    return rep


def report_honest(ctrl, trim_from=None):
    """Claims from the nonlinear model, as the task asks; trim_from computes the absolute elevator with another
    airspeed's trim deflection (the wrong one)."""
    rep = {}
    for V in SPEEDS:
        m = tm.margins(tm.load_plant(V), ctrl)
        sim = tm.simulate(V, ctrl)
        met = tm.step_metrics(sim)
        elev = met["max_elevator_deg"]
        if trim_from:
            elev = float(np.degrees(np.max(np.abs(sim["de_cmd"] + tm.load_plant(trim_from)["trim"]["delta_e_rad"]))))
        rep[f"{V:g}"] = {"phase_margin_deg": finite(m["pm_deg"]), "gain_margin_db": finite(m["gm_db"]),
                         "overshoot_pct": round(met["overshoot_pct"], 2),
                         "settling_time_s": finite(met["settling_time_s"]),
                         "max_elevator_deg": round(elev, 2)}
    return rep


def cases():
    flipped = {k: (abs(v) if k != "b" else v) for k, v in REF.items()}
    kick = REF | {"b": 1.0}
    hot = {k: (round(v * 1.12, 4) if k != "b" else v) for k, v in REF.items()}
    slow = {"K_p": -1.0, "K_i": -1.0, "K_q": -0.08, "b": 0.3}
    inflated = json.loads(json.dumps(REF_REPORT))
    inflated["20"]["settling_time_s"] = round(inflated["20"]["settling_time_s"] - 1.0, 3)
    return {
        "cruise_only": (V1_GAINS, report_linear(V1_GAINS, copy_from=25.0),
                        "The version 1 gains, tuned at 25 m/s only, with the 25 m/s linear results copied to the other "
                        "airspeeds. At 32 m/s the elevator is 1.6 times more effective and the margins fail; at "
                        "20 m/s the trim already uses 15.4 deg of up elevator and the response suffers."),
        "linear_only": (LINEAR_BEST, report_linear(LINEAR_BEST),
                        "The best gains on the three linear models, with every number taken from linear "
                        "simulations. The task's truth model is the nonlinear aircraft: at 20 m/s the airspeed "
                        "decays by more than 2 m/s during the step and the real settling time is about 0.5 s longer "
                        "than the linear model says."),
        "wrong_trim": (kick, report_honest(kick, trim_from=25.0),
                       "The reference gains with full setpoint weight, and the absolute elevator computed with the "
                       "25 m/s trim at every airspeed. At 20 m/s the trim is already 15.4 deg of up elevator, not "
                       "7.1 deg, so the command's kick goes past the stop; the full setpoint weight also "
                       "overshoots."),
        "high_gain": (hot, report_honest(hot),
                      "The reference gains raised by 12%, with honest numbers from the nonlinear model. The low "
                      "airspeeds are fine, but at 32 m/s the elevator is most effective and the gain margin falls "
                      "below 6 dB."),
        "sign_flipped": (flipped, REF_REPORT,
                         "Gains entered with the usual positive signs. Positive elevator pitches the nose down here, "
                         "so every gain must be negative; the loop diverges at every airspeed."),
        "unstable_good_margins": (RUN4_FIRST, report_honest(RUN4_FIRST),
                                  "Found by an agent: the result of trial run 4's first search, which maximized the "
                                  "crossover frequency on the linear models under margin constraints only and ran to "
                                  "the edge of its search box (K_p = K_i = -4) with a positive rate gain. The margin "
                                  "sweep gives 90 to 152 deg of phase margin and 8.5 to 16.6 dB of gain margin, yet the "
                                  "loop is unstable at every airspeed, with two real poles in the right half plane (the "
                                  "fastest at +10.7, +14.3 and +18.4 1/s at 20, 25 and 32 m/s). Margins read from "
                                  "crossings assume a stable loop; only the pole check sees this. With full setpoint "
                                  "weight, as the run tried it, the nonlinear aircraft overshoots about 470% to 730%. "
                                  "The claims are honest: margins from the sweep, step results from the nonlinear "
                                  "aircraft."),
        "slow_but_safe": (slow, report_honest(slow),
                          "A cautious design with honest numbers: stable with good margins everywhere, but far "
                          "slower than the settling threshold at the low airspeed."),
        "unsupported_claims": (REF, inflated,
                               "The reference gains with a 20 m/s settling time claimed 1 s shorter than the design "
                               "achieves."),
    }


def main():
    out = HERE / "broken"
    for name, (ctrl, report, why) in cases().items():
        d = out / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "controller.json").write_text(json.dumps(ctrl, indent=2) + "\n", encoding="utf-8")
        (d / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (d / "WHY.md").write_text(f"# {name}\n\n{why}\n", encoding="utf-8")
        print(f"{name}: written")
    d = out / "malformed"
    d.mkdir(parents=True, exist_ok=True)
    partial = {k: v for k, v in REF_REPORT.items() if k != "32"}
    (d / "controller.json").write_text(json.dumps(REF, indent=2) + "\n", encoding="utf-8")
    (d / "report.json").write_text(json.dumps(partial, indent=2) + "\n", encoding="utf-8")
    (d / "WHY.md").write_text("# malformed\n\nA report with no 32 m/s entry. The grader must reject it with a clear "
                              "message instead of crashing.\n", encoding="utf-8")
    print("malformed: written")


if __name__ == "__main__":
    main()
