"""Frequency domain analysis: loop gain L(s) for the pitch attitude hold loop, and margins.

Loop structure (derived in NOTES.md): breaking at the elevator command (controller output,
before the actuator), with theta_cmd = 0 (pure feedback loop):

    L(s) = (Kp + Ki/s + Kq*s) * G_theta(s) * G_act(s) * exp(-s*tau_delay)

using q = d(theta)/dt exactly (4th state row of A is [0,0,1,0], B_theta=0), so G_q(s) = s*G_theta(s)
and the two feedback terms combine into one PID(s) acting on theta through a common delay.

Closed loop char. eq: 1 + L(s) = 0.
"""
import json
import pathlib

import numpy as np
from scipy.signal import ss2tf

HERE = pathlib.Path(__file__).parent
ENV = HERE.parent / "environment"

ACT_TAU = 0.05
DELAY = 0.04

# Exact grader frequency grid
W_GRID = np.logspace(np.log10(0.001), np.log10(1000.0), 200001)
# Coarser grid for fast iteration during search; final numbers are always re-checked on W_GRID.
W_GRID_FAST = np.logspace(np.log10(0.001), np.log10(1000.0), 4001)


def load_plant(spd):
    return json.loads((ENV / f"plant_{spd:g}.json").read_text(encoding="utf-8"))


def theta_tf(plant):
    """Numerator/denominator (descending powers) of G_theta(s) = theta(s)/delta_e(s)."""
    A = np.array(plant["A"])
    B = np.array(plant["B"])  # (4,1)
    Cth = np.array([[0.0, 0.0, 0.0, 1.0]])
    D = np.array([[0.0]])
    num, den = ss2tf(A, B, Cth, D)
    return np.asarray(num).ravel(), np.asarray(den).ravel()


def loop_gain(w, Kp, Ki, Kq, b, num, den):
    """Evaluate L(jw) (array) for the given controller gains. `b` does not affect L (verified: b
    only scales the reference feed-forward path, not the feedback loop)."""
    s = 1j * w
    Gtheta = np.polyval(num, s) / np.polyval(den, s)
    Gact = 1.0 / (ACT_TAU * s + 1.0)
    delay = np.exp(-s * DELAY)
    pid = Kp + Ki / s + Kq * s
    return pid * Gtheta * Gact * delay


def _crossings(w, y):
    """Vectorized: indices i where y[i],y[i+1] bracket a zero crossing (strict sign change), plus
    the linear-interpolation fraction in [0,1] from i to i+1."""
    s0 = y[:-1]
    s1 = y[1:]
    mask = (s0 < 0) != (s1 < 0)
    idx = np.nonzero(mask)[0]
    frac = -s0[idx] / (s1[idx] - s0[idx])
    return idx, frac


def margins(w, L):
    """Return dict with all gain crossovers (freq, phase_margin_deg) and all negative-real-axis
    ("phase = -180 mod 360") crossovers (freq, gain_margin_db_against_increase, loop_gain_mag).

    Robust, fully vectorized method: gain crossovers are where |L|=1 (sign change of log|L|).
    Negative-real-axis crossovers are where Im(L)=0 AND Re(L)<0 (captures phase=-180,-540,...
    without unwrap ambiguity). Phase margin at a gain crossover uses the continuously unwrapped
    phase.
    """
    mag = np.abs(L)
    logmag = np.log(mag)
    phase = np.unwrap(np.angle(L))  # radians, continuous
    logw = np.log(w)

    idx, frac = _crossings(w, logmag)
    wc = np.exp(logw[idx] + frac * (logw[idx + 1] - logw[idx]))
    ph = phase[idx] + frac * (phase[idx + 1] - phase[idx])
    pm = 180.0 + np.degrees(ph)
    gain_cross = list(zip(wc.tolist(), pm.tolist()))

    idx2, frac2 = _crossings(w, L.imag)
    wc2 = np.exp(logw[idx2] + frac2 * (logw[idx2 + 1] - logw[idx2]))
    re2 = L.real[idx2] + frac2 * (L.real[idx2 + 1] - L.real[idx2])
    keep = re2 < 0
    magc = np.abs(re2[keep])
    gm_increase_db = -20.0 * np.log10(magc)
    phase_cross = list(zip(wc2[keep].tolist(), magc.tolist(), gm_increase_db.tolist()))

    return gain_cross, phase_cross


def evaluate(plant, Kp, Ki, Kq, b, num=None, den=None, w=W_GRID):
    if num is None or den is None:
        num, den = theta_tf(plant)
    L = loop_gain(w, Kp, Ki, Kq, b, num, den)
    gc, pc = margins(w, L)
    worst_pm = min((pm for _, pm in gc), default=999.0)
    # gain margin against increase: worst (min) over phase crossovers with mag<1
    increase_candidates = [gm for (_, magc, gm) in pc if magc < 1.0]
    gm_increase = min(increase_candidates) if increase_candidates else 999.0
    # gain margin against decrease requirement: at crossovers with mag>1, need 20log10(mag)>=6dB
    decrease_ok = all((20.0 * np.log10(magc)) >= 6.0 - 1e-9 for (_, magc, gm) in pc if magc >= 1.0)
    decrease_margins = [20.0 * np.log10(magc) for (_, magc, gm) in pc if magc >= 1.0]
    return {
        "gain_crossovers": gc,
        "phase_crossovers": pc,
        "phase_margin_deg": worst_pm,
        "gain_margin_db": gm_increase,
        "decrease_margin_ok": decrease_ok,
        "decrease_margins_db": decrease_margins,
        "n_gain_cross": len(gc),
        "n_phase_cross": len(pc),
    }


if __name__ == "__main__":
    for spd in (20, 25, 32):
        plant = load_plant(spd)
        num, den = theta_tf(plant)
        print(spd, "num", num, "den", den)
        res = evaluate(plant, Kp=-3.0, Ki=-1.0, Kq=-1.0, b=0.5, num=num, den=den)
        print("  PM", res["phase_margin_deg"], "GM_inc_dB", res["gain_margin_db"],
              "decrease_ok", res["decrease_margin_ok"], "n_gc", res["n_gain_cross"],
              "n_pc", res["n_phase_cross"])
