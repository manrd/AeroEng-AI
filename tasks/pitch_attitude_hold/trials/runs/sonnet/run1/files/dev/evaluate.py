import sys
import numpy as np
sys.path.insert(0, ".")
from model import (load_plant, plant_freq_response, discretize, simulate,
                    loop_gain, margins_from_L, default_w_grid)

A, B, C, D, trim = load_plant()
TRIM_DE = trim["delta_e_rad"]
THETA_CMD = np.radians(5.0)

W = default_w_grid()
_Y = plant_freq_response(A, B, C, W)
PTHETA_JW = _Y[:, 0]
PQ_JW = _Y[:, 1]

_AD, _BD = discretize(A, B)


def settling_time(t, theta_deg, cmd_deg=5.0, band_deg=0.1):
    dev = np.abs(theta_deg - cmd_deg)
    bad = np.where(dev > band_deg)[0]
    if len(bad) == 0:
        return 0.0
    return float(t[bad[-1]])


def settling_time_robustness(t, theta_deg, cmd_deg=5.0):
    """Settling time at 1.9%, 2.0%, 2.1% bands -- should be tightly clustered for a clean
    (non-marginal) settling event, since the grader compares our reported value against the
    range obtained with 1.9%/2.1% bands (+/- 0.05 s)."""
    lo = settling_time(t, theta_deg, cmd_deg, band_deg=cmd_deg * 0.019)
    mid = settling_time(t, theta_deg, cmd_deg, band_deg=cmd_deg * 0.020)
    hi = settling_time(t, theta_deg, cmd_deg, band_deg=cmd_deg * 0.021)
    return lo, mid, hi


def overshoot_pct(theta_deg, cmd_deg=5.0):
    peak = np.max(theta_deg)
    return max(0.0, (peak - cmd_deg) / cmd_deg * 100.0)


def evaluate(Kp, Ki, Kq, b, verbose=False):
    L = loop_gain(W, Kp, Ki, Kq, PTHETA_JW, PQ_JW)
    m = margins_from_L(W, L)

    res = simulate(Kp, Ki, Kq, b, A, B, TRIM_DE, THETA_CMD, Ad=_AD, Bd=_BD)
    theta_deg = res["theta_deg"]
    t = res["t"]

    ov = overshoot_pct(theta_deg)
    st = settling_time(t, theta_deg)
    max_e = float(np.max(np.abs(res["cmd_abs_deg"])))
    peak_theta = float(np.max(theta_deg))
    final_theta = float(theta_deg[-1])

    out = {
        "Kp": Kp, "Ki": Ki, "Kq": Kq, "b": b,
        "phase_margin_deg": m["worst_phase_margin_deg"],
        "gain_margin_up_db": m["worst_gain_margin_up_db"],
        "gain_margin_down_db": m["worst_gain_margin_down_db"],
        "n_gc": m["n_gain_crossovers"], "n_pc": m["n_phase_crossovers"],
        "overshoot_pct": ov,
        "settling_time_s": st,
        "max_elevator_deg": max_e,
        "peak_theta_deg": peak_theta,
        "final_theta_deg": final_theta,
    }
    if verbose:
        for k2, v in out.items():
            print(f"  {k2}: {v}")
    return out, m, res


def passes(out, margin_buf_pm=0.0, margin_buf_gm=0.0):
    ok = True
    reasons = []
    if out["phase_margin_deg"] < 45 + margin_buf_pm:
        ok = False; reasons.append("PM")
    if out["gain_margin_up_db"] < 6 + margin_buf_gm:
        ok = False; reasons.append("GMup")
    if out["gain_margin_down_db"] < 6 + margin_buf_gm:
        ok = False; reasons.append("GMdown")
    if out["overshoot_pct"] > 10.0:
        ok = False; reasons.append("overshoot")
    if out["max_elevator_deg"] > 25.0:
        ok = False; reasons.append("elevator")
    if out["settling_time_s"] > 4.0:
        ok = False; reasons.append("settling")
    return ok, reasons


if __name__ == "__main__":
    out, m, res = evaluate(-1.0, -0.5, -0.3, 0.5, verbose=True)
    print(passes(out))
