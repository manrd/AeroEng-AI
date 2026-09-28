"""Builds the deliberately broken solutions in tests/broken/, each one a realistic mistake.

Every case gets controller.json, report.json (what the mistaken agent would claim) and WHY.md. The claims are
computed the way the mistaken agent would compute them, not invented.

    python make_broken.py
"""
import json
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
TASK = HERE.parents[1]
sys.path.insert(0, str(TASK / "grader"))
import truth_model as tm  # noqa: E402

PLANT = tm.load_plant()
REF = json.loads((TASK / "reference" / "controller.json").read_text(encoding="utf-8"))
REF_REPORT = json.loads((TASK / "reference" / "report.json").read_text(encoding="utf-8"))


def settling_to_final_value(sim, band=0.02):
    """Settling time measured against the final value of the response, not the command. This is the
    convention of MATLAB's stepinfo and python-control's step_info, and it hides a steady state error."""
    th, t = sim["theta"], sim["t"]
    outside = np.nonzero(np.abs(th - th[-1]) > band * abs(th[-1]))[0]
    return float(t[outside[-1] + 1]) if len(outside) else 0.0


def honest_report(ctrl, delay=True, perturbation_elevator=False, final_value_settling=False):
    """The report an agent would write from its own run, with the given modelling choices."""
    m = tm.margins(PLANT, ctrl, delay=delay)
    sim = tm.simulate(PLANT, ctrl)
    met = tm.step_metrics(sim)
    elev = np.degrees(np.max(np.abs(sim["de_cmd"]))) if perturbation_elevator else met["max_elevator_deg"]
    ts = settling_to_final_value(sim) if final_value_settling else met["settling_time_s"]

    def finite(v):  # the README asks for 999 when a margin is infinite
        return round(float(v), 2) if np.isfinite(v) else 999.0

    return {"phase_margin_deg": finite(m["pm_deg"]), "gain_margin_db": finite(m["gm_db"]),
            "overshoot_pct": round(met["overshoot_pct"], 2), "settling_time_s": round(ts, 3),
            "max_elevator_deg": round(float(elev), 2)}


def cases():
    flipped = {k: (abs(v) if k != "b" else v) for k, v in REF.items()}
    hot = {k: (round(v * 1.5, 4) if k != "b" else v) for k, v in REF.items()}
    no_i = REF | {"K_i": 0.0, "b": 1.0}
    b1 = REF | {"b": 1.0}
    q_deg = REF | {"K_q": round(REF["K_q"] / np.degrees(1.0), 5)}
    slow = {"K_p": -1.0, "K_i": -1.0, "K_q": -0.1, "b": 0.3}
    aggressive = {"K_p": -2.7184, "K_i": -14.7038, "K_q": -0.2467, "b": 1.0}
    return {
        "sign_flipped": (flipped, REF_REPORT,
                         "Gains entered with the usual positive signs. Here positive elevator pitches the nose "
                         "down, so every gain must be negative; positive gains give positive feedback and the "
                         "loop diverges. The report repeats numbers from a design the agent never simulated."),
        "ignores_delay": (hot, honest_report(hot, delay=False),
                          "Gains raised by 50% after computing margins without the 40 ms sensor delay. Without "
                          "the delay the margins look fine, which is what the report claims; with it both fail: "
                          "the gain margin drops to about 3 dB and the phase margin to about 17 deg."),
        "no_integrator": (no_i, honest_report(no_i, final_value_settling=True),
                          "Proportional and rate feedback only, as in a textbook pitch damper. Holding a new "
                          "pitch attitude needs a steady elevator offset, so the response settles about 18% "
                          "short of the command. The agent measured settling against the final value, as "
                          "stepinfo and step_info do, so the report shows a fast settling time and hides the "
                          "error."),
        "full_setpoint_weight": (b1, REF_REPORT,
                                 "The reference gains with b = 1: the proportional term acts on the full "
                                 "command step, which kicks the elevator into the rate limit and overshoots by "
                                 "about 33%. The report was copied from the b = 0.15 design without rerunning."),
        "q_in_degrees": (q_deg, honest_report(REF),
                         "K_q tuned as if pitch rate were measured in deg/s, so it is 57.3 times too small "
                         "for the rad/s signal the plant provides. The report comes from the intended design."),
        "slow_but_safe": (slow, honest_report(slow),
                          "A cautious design with honest numbers: stable, good margins, no overshoot, but it "
                          "settles far slower than the 4.0 s target."),
        "unsupported_claims": (REF, REF_REPORT | {"phase_margin_deg": 70.0, "settling_time_s": 1.5},
                               "The reference gains with inflated claims: a 70 deg phase margin and 1.5 s "
                               "settling, which the design does not achieve."),
        "perturbation_limit": (aggressive, honest_report(aggressive, perturbation_elevator=True),
                               "An aggressive design with acceptable margins whose elevator command peaks at "
                               "about 21 deg from trim, reported as within the 25 deg limit. The limit applies "
                               "to the absolute deflection, and trim is already -7.1 deg, so the command goes "
                               "about 3 deg past the stop. The full setpoint weight also overshoots badly."),
    }


def main():
    out = HERE / "broken"
    for name, (ctrl, report, why) in cases().items():
        d = out / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "controller.json").write_text(json.dumps(ctrl, indent=2) + "\n", encoding="utf-8")
        (d / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (d / "WHY.md").write_text(f"# {name}\n\n{why}\n", encoding="utf-8")
        print(f"{name}: {ctrl} | {report}")
    d = out / "malformed"
    d.mkdir(parents=True, exist_ok=True)
    (d / "controller.json").write_text(json.dumps({"K_p": REF["K_p"], "K_i": REF["K_i"], "K_q": "fast",
                                                   "b": 1.5}, indent=2) + "\n", encoding="utf-8")
    (d / "report.json").write_text(json.dumps(REF_REPORT, indent=2) + "\n", encoding="utf-8")
    (d / "WHY.md").write_text("# malformed\n\nA controller file with a text value for K_q and b outside 0 to 1. "
                              "The grader must reject it with a clear message instead of crashing.\n",
                              encoding="utf-8")
    print("malformed: written")


if __name__ == "__main__":
    main()
