"""Autograder for version 2: pitch attitude hold across the speed range.

    python grade.py SOLUTION_DIR [--json]

Reads SOLUTION_DIR/controller.json and SOLUTION_DIR/report.json, recomputes every metric at 20, 25 and 32 m/s with
its own truth model (truth_model.py: linear models for the margins, the nonlinear aircraft for the step response),
and prints PASS or FAIL with one line per check. Checks carry the airspeed they refer to, as in GAIN_MARGIN@32.
Exit code 0 on PASS, 1 on FAIL.
"""
import json
import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import truth_model as tm  # noqa: E402

REQ = {"pm_deg": 45.0, "gm_db": 6.0, "overshoot_pct": 10.0, "settling_s": 6.0}
TOL = {"phase_margin_deg": 1.5, "gain_margin_db": 0.5, "overshoot_pct": 1.0, "max_elevator_deg": 0.5,
       "settling_time_s": 0.05}
INFINITE = 999.0  # how report.json writes an infinite margin
CTRL_KEYS = ("K_p", "K_i", "K_q", "b")
REPORT_KEYS = ("phase_margin_deg", "gain_margin_db", "overshoot_pct", "settling_time_s", "max_elevator_deg")
SPEEDS = tm.SPEC["speeds_m_s"]


def _read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, f"{path.name} is missing"
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, f"{path.name} is not valid JSON ({exc})"


def _finite_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def check_schema(ctrl, report):
    problems = []
    for k in CTRL_KEYS:
        if not _finite_number(ctrl.get(k)):
            problems.append(f"controller.json: {k} missing or not a finite number")
    if _finite_number(ctrl.get("b")) and not 0.0 <= ctrl["b"] <= 1.0:
        problems.append("controller.json: b must be between 0 and 1")
    if not isinstance(report, dict):
        return problems + ["report.json: must be an object keyed by airspeed"]
    for V in SPEEDS:
        entry = report.get(f"{V:g}")
        if not isinstance(entry, dict):
            problems.append(f'report.json: entry "{V:g}" missing')
            continue
        for k in REPORT_KEYS:
            if not _finite_number(entry.get(k)):
                problems.append(f'report.json: "{V:g}".{k} missing or not a finite number')
    return problems


def grade_speed(V, c, claims, checks, results):
    tag = f"@{V:g}"
    plant = tm.load_plant(V)
    poles = tm.closed_loop_poles(plant, c)
    sim = tm.simulate(V, c)
    met = tm.step_metrics(sim)
    stable = bool(np.max(poles.real) < 0) and not met["diverged"]
    checks.append(("STABILITY" + tag, stable,
                   f"slowest linear closed loop pole real part {np.max(poles.real):.4f} 1/s"
                   + ("" if not met["diverged"] else "; the nonlinear run diverges")))
    if not stable:
        results[f"{V:g}"] = {"max_pole_real": float(np.max(poles.real)), "diverged": met["diverged"]}
        return
    mg = tm.margins(plant, c)
    checks.append(("PHASE_MARGIN" + tag, mg["pm_deg"] >= REQ["pm_deg"],
                   f"{mg['pm_deg']:.2f} deg (needs at least {REQ['pm_deg']:.0f})"))
    gm_ok = mg["gm_db"] >= REQ["gm_db"] and mg["gm_low_db"] >= REQ["gm_db"]
    low = "" if math.isinf(mg["gm_low_db"]) else f"; against a gain decrease {mg['gm_low_db']:.2f} dB"
    checks.append(("GAIN_MARGIN" + tag, gm_ok, f"{mg['gm_db']:.2f} dB{low} (needs at least {REQ['gm_db']:.0f})"))
    checks.append(("OVERSHOOT" + tag, met["overshoot_pct"] <= REQ["overshoot_pct"],
                   f"{met['overshoot_pct']:.2f}% (at most {REQ['overshoot_pct']:.0f}%)"))
    checks.append(("POSITION_LIMIT" + tag, met["max_elevator_deg"] <= tm.SPEC["position_limit_deg"],
                   f"peak absolute elevator command {met['max_elevator_deg']:.2f} deg "
                   f"(at most {tm.SPEC['position_limit_deg']:.0f}); beyond the stop for "
                   f"{met['position_limited_s']:.3f} s"))
    ts = met["settling_time_s"]
    checks.append(("SETTLING" + tag, ts <= REQ["settling_s"],
                   f"{ts:.3f} s (at most {REQ['settling_s']:.1f} s)"
                   + ("" if math.isfinite(ts) else f"; final error {met['final_error_pct']:.2f}% of the step")))

    lo_band = tm.step_metrics(sim, tm.SPEC | {"band": 0.021})["settling_time_s"]
    hi_band = tm.step_metrics(sim, tm.SPEC | {"band": 0.019})["settling_time_s"]
    actual = {"phase_margin_deg": mg["pm_deg"], "gain_margin_db": mg["gm_db"],
              "overshoot_pct": met["overshoot_pct"], "max_elevator_deg": met["max_elevator_deg"]}

    def matches(k, v):
        if math.isinf(v):
            return claims[k] >= INFINITE
        return abs(claims[k] - v) <= TOL[k]

    bad = [f"{k} claimed {claims[k]:.3f}, recomputed {v:.3f}" for k, v in actual.items() if not matches(k, v)]
    t_claim = claims["settling_time_s"]
    if not math.isfinite(ts):
        if t_claim < INFINITE:
            bad.append(f"settling_time_s claimed {t_claim:.3f}, but the response never settles within the horizon")
    elif not (lo_band - TOL["settling_time_s"] <= t_claim <= hi_band + TOL["settling_time_s"]):
        bad.append(f"settling_time_s claimed {t_claim:.3f}, recomputed {ts:.3f} "
                   f"(accepted {lo_band:.3f} to {hi_band:.3f} with a 1.9% to 2.1% band)")
    checks.append(("CLAIMS" + tag, not bad, "; ".join(bad) or "every claim matches the recomputed value"))
    results[f"{V:g}"] = {"phase_margin_deg": mg["pm_deg"], "gain_margin_db": mg["gm_db"],
                         "gain_margin_decrease_db": mg["gm_low_db"], "crossover_rad_s": mg["crossover_rad_s"],
                         "overshoot_pct": met["overshoot_pct"], "settling_time_s": ts,
                         "max_elevator_deg": met["max_elevator_deg"], "rate_limited_s": met["rate_limited_s"],
                         "min_airspeed_m_s": met["min_airspeed_m_s"]}


def grade(solution_dir):
    sol = pathlib.Path(solution_dir)
    checks, results = [], {}
    ctrl, err_c = _read(sol / "controller.json")
    report, err_r = _read(sol / "report.json")
    if err_c or err_r:
        checks.append(("SCHEMA", False, "; ".join(e for e in (err_c, err_r) if e)))
        return _verdict(checks, results)
    problems = check_schema(ctrl, report)
    checks.append(("SCHEMA", not problems, "; ".join(problems) or "all fields present and finite"))
    if problems:
        return _verdict(checks, results)
    c = {k: float(ctrl[k]) for k in CTRL_KEYS}
    for V in SPEEDS:
        grade_speed(V, c, report[f"{V:g}"], checks, results)
    settle = [r["settling_time_s"] for r in results.values() if "settling_time_s" in r]
    if settle and len(settle) == len(SPEEDS):
        results["worst_settling_time_s"] = max(settle)
    return _verdict(checks, results)


def _verdict(checks, results):
    passed = all(ok for _, ok, _ in checks)
    return {"verdict": "PASS" if passed else "FAIL",
            "failed": [code for code, ok, _ in checks if not ok],
            "checks": [{"check": code, "passed": ok, "detail": d} for code, ok, d in checks],
            "recomputed": results}


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    out = grade(argv[1])
    if "--json" in argv:
        print(json.dumps(out, indent=2, default=float))
    else:
        print(f"{out['verdict']}: {argv[1]}")
        for ch in out["checks"]:
            print(f"  [{'ok' if ch['passed'] else 'FAIL'}] {ch['check']}: {ch['detail']}")
        worst = out["recomputed"].get("worst_settling_time_s")
        if worst is not None:
            print(f"  worst settling time over the airspeeds: {worst:.3f} s (lower is better)")
    return 0 if out["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
