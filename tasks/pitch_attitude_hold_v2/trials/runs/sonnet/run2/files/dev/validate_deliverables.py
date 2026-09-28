"""Sanity-check the deliverables in solution/ before calling the task done:
valid JSON, all-finite numbers, required keys present, values in sane ranges.
Does not re-derive pass/fail against R1-R5 (finalize.py already prints that);
this is just a schema/sanity gate matching the "Grading" section's basic checks.
"""
import json
import math
import sys

import core

SOLUTION = core.RUN_ROOT / "solution"


def check_finite(x, path):
    if not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(x):
        raise ValueError(f"{path}: not a finite number: {x!r}")


def main():
    errs = []

    ctrl_path = SOLUTION / "controller.json"
    rep_path = SOLUTION / "report.json"
    notes_path = SOLUTION / "NOTES.md"

    if not ctrl_path.exists():
        errs.append("controller.json missing")
    if not rep_path.exists():
        errs.append("report.json missing")
    if not notes_path.exists():
        errs.append("NOTES.md missing")
    if errs:
        print("FAIL:", errs)
        sys.exit(1)

    ctrl = json.loads(ctrl_path.read_text(encoding="utf-8"))
    for k in ("K_p", "K_i", "K_q", "b"):
        if k not in ctrl:
            errs.append(f"controller.json missing key {k}")
        else:
            check_finite(ctrl[k], f"controller.{k}")
    if ctrl.get("K_p", 0) >= 0 or ctrl.get("K_i", 0) >= 0 or ctrl.get("K_q", 0) >= 0:
        errs.append("K_p, K_i, K_q expected strictly negative given the sign convention "
                     f"(got K_p={ctrl.get('K_p')}, K_i={ctrl.get('K_i')}, K_q={ctrl.get('K_q')})")
    b = ctrl.get("b")
    if b is None or not (0.0 <= b <= 1.0):
        errs.append(f"b={b} not in [0,1]")

    rep = json.loads(rep_path.read_text(encoding="utf-8"))
    for spd in ("20", "25", "32"):
        if spd not in rep:
            errs.append(f"report.json missing airspeed key {spd!r}")
            continue
        entry = rep[spd]
        for k in ("phase_margin_deg", "gain_margin_db", "overshoot_pct",
                   "settling_time_s", "max_elevator_deg"):
            if k not in entry:
                errs.append(f"report.json[{spd}] missing key {k}")
            else:
                check_finite(entry[k], f"report.{spd}.{k}")
        if entry.get("phase_margin_deg", 0) < 45.0:
            errs.append(f"report.json[{spd}].phase_margin_deg={entry.get('phase_margin_deg')} < 45 (R2)")
        if entry.get("gain_margin_db", 0) < 6.0:
            errs.append(f"report.json[{spd}].gain_margin_db={entry.get('gain_margin_db')} < 6 (R2)")
        if entry.get("overshoot_pct", 999) > 10.0:
            errs.append(f"report.json[{spd}].overshoot_pct={entry.get('overshoot_pct')} > 10 (R3)")
        if entry.get("max_elevator_deg", 999) > 25.0:
            errs.append(f"report.json[{spd}].max_elevator_deg={entry.get('max_elevator_deg')} > 25 (R4)")
        if entry.get("settling_time_s", 999) > 6.0:
            errs.append(f"report.json[{spd}].settling_time_s={entry.get('settling_time_s')} > 6.0 (R5)")

    if errs:
        print("FAIL:")
        for e in errs:
            print(" -", e)
        sys.exit(1)
    else:
        print("OK: controller.json and report.json look valid and within all thresholds.")
        print(json.dumps(ctrl, indent=2))
        print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
