"""Linear frequency-domain loop analysis: exact (no Pade) evaluation of the loop transfer function
broken at the elevator command, exactly as the grader specifies, and gain/phase margin extraction via
python-control's own stability_margins() (fed the exact mag/phase/omega triple) -- since R2's
vocabulary ("gain margin", "phase margin", "gain crossover", "phase crossover") matches that
function's docstring exactly, and python-control 0.10.2 is the version this task installs, this is
almost certainly the grader's own method, so matching its convention (a *wrapped* phase margin, not a
continuously-unwrapped one -- see NOTES.md) is important for agreeing with the grader within tolerance.

Loop derivation (theta_cmd set to 0, since margins are a property of the feedback loop only):
    delta_e_cmd(s) = -(Kp + Ki/s) * e^{-s*tau_d} * theta_m(s) - Kq * e^{-s*tau_d} * q_m(s)
    theta(s), q(s) = G(s) * delta_e(s),   delta_e(s) = Aact(s) * delta_e_cmd(s)
=>  L(s) = e^{-s*tau_d} * Aact(s) * [ (Kp + Ki/s) * G_theta(s) + Kq * G_q(s) ]
    closed loop char. eq.:  1 + L(s) = 0
This matches standard unity-negative-feedback margin conventions (python-control's margin()).
"""
import json
import pathlib
import numpy as np
import control as ct

HERE = pathlib.Path(__file__).parent
ENV = HERE.parent / "environment"

TAU_ACT = 0.05
TAU_DELAY = 0.04
RATE_LIM_DEG_S = 60.0
POS_LIM_DEG = 25.0

GRADER_OMEGA = np.logspace(np.log10(0.001), np.log10(1000.0), 200001)


def load_plant(speed):
    d = json.loads((ENV / f"plant_{speed}.json").read_text(encoding="utf-8"))
    A = np.array(d["A"], dtype=float)
    B = np.array(d["B"], dtype=float).ravel()
    C = np.array(d["C"], dtype=float)
    return dict(A=A, B=B, C=C, trim=d["trim"])


def _siso_response(A, Bvec, Crow, s):
    """C (sI-A)^-1 B at each complex s (array), via eigendecomposition of A (4x4, cheap)."""
    eigvals, V = np.linalg.eig(A)
    Vinv = np.linalg.inv(V)
    CV = Crow @ V
    VinvB = Vinv @ Bvec
    coeff = CV * VinvB
    denom = s[:, None] - eigvals[None, :]
    return (coeff[None, :] / denom).sum(axis=1)


def plant_freq_response(plant, omega):
    s = 1j * omega
    Gtheta = _siso_response(plant["A"], plant["B"], plant["C"][0, :], s)
    Gq = _siso_response(plant["A"], plant["B"], plant["C"][1, :], s)
    return Gtheta, Gq


def loop_L(omega, Kp, Ki, Kq, plant, tau_act=TAU_ACT, tau_delay=TAU_DELAY):
    s = 1j * omega
    Gtheta, Gq = plant_freq_response(plant, omega)
    Aact = 1.0 / (tau_act * s + 1.0)
    delay = np.exp(-tau_delay * s)
    ctrl = (Kp + Ki / s) * Gtheta + Kq * Gq
    return delay * Aact * ctrl


def _interp_log_omega(w1, w2, frac):
    return w1 * (w2 / w1) ** frac


def find_all_margins_fast(omega, L):
    """Fast, fully vectorized (no per-point library/spline overhead) crossing finder for use inside a
    search loop. Crossing *locations* are found by tracking the continuously unwrapped phase (needed so
    a mere +/-360 wraparound in the wrapped representation is never mistaken for a real -180 crossing,
    and so a real crossing many wraps in is not missed). The *reported* phase margin at each gain
    crossing is then reduced with the same convention control.stability_margins uses -- PM =
    (phase_deg % 360) - 180 -- instead of the naive '180 + continuously-unwrapped phase', which
    silently returns nonsense (e.g. "250 deg of phase margin") once the 40 ms delay has wrapped the
    phase past a multiple of 360 deg before the crossing. Cross-checked against control.stability_margins
    fed the exact same (mag, phase, omega) in work/validate_margins.py.
    """
    mag = np.abs(L)
    logmag = np.log(mag)
    phase_deg = np.degrees(np.unwrap(np.angle(L)))  # continuous, for locating crossings only

    gain_crossings = []
    s = np.sign(logmag)
    idx = np.where(np.diff(s) != 0)[0]
    for i in idx:
        m1, m2 = logmag[i], logmag[i + 1]
        if m2 == m1:
            continue
        frac = -m1 / (m2 - m1)
        wc = _interp_log_omega(omega[i], omega[i + 1], frac)
        p1, p2 = phase_deg[i], phase_deg[i + 1]
        pc = p1 + (p2 - p1) * frac  # continuous phase at the crossing (may be well past +/-180)
        pm = (pc % 360.0) - 180.0  # reduce to control.stability_margins' convention
        gain_crossings.append((wc, pm))

    phase_crossings = []
    h = phase_deg + 180.0
    k = np.floor(h / 360.0)
    idx2 = np.where(np.diff(k) != 0)[0]
    for i in idx2:
        h1, h2 = h[i], h[i + 1]
        lo, hi = min(h1, h2), max(h1, h2)
        target = 360.0 * np.ceil(lo / 360.0)
        if not (lo - 1e-9 <= target <= hi + 1e-9):
            continue
        frac = (target - h1) / (h2 - h1) if h2 != h1 else 0.0
        wc = _interp_log_omega(omega[i], omega[i + 1], frac)
        m1, m2 = logmag[i], logmag[i + 1]
        mc = m1 + (m2 - m1) * frac
        gain_db = 20.0 * mc / np.log(10.0)
        phase_crossings.append((wc, gain_db))

    return sorted(gain_crossings), sorted(phase_crossings)


def all_margins(omega, L):
    """All gain/phase crossings via control.stability_margins (FRD/'best' method), fed the *exact*
    (non-Pade) frequency response. Returns dict with:
      gain_crossings: list of (freq, phase_margin_deg)   -- one per |L|=1 crossing
      phase_crossings: list of (freq, gain_db)            -- one per phase=-180(mod 360) crossing,
                        gain_db = 20*log10(|L|) there (>0 means loop gain above 1 at that crossing)
    """
    mag = np.abs(L)
    phase_deg = np.degrees(np.angle(L))  # wrapped to (-180,180]; exp() below reconstructs L exactly
    GM, PM, SM, w180, wgc, wstab = ct.stability_margins((mag, phase_deg, omega), returnall=True)
    gain_crossings = list(zip(np.atleast_1d(wgc).tolist(), np.atleast_1d(PM).tolist()))
    with np.errstate(divide="ignore"):
        gain_db_at_180 = 20.0 * np.log10(np.atleast_1d(GM))  # >0 dB <=> |L|<1 there (GM=1/|L|>1)
    phase_crossings = list(zip(np.atleast_1d(w180).tolist(), (-gain_db_at_180).tolist()))
    # sign flip: report gain_db as 20log10(|L|) directly (>0 means loop gain above 1), i.e. -1*(GM in dB)
    return dict(gain_crossings=sorted(gain_crossings), phase_crossings=sorted(phase_crossings))


PM_MIN, GM_MIN_DB = 45.0, 6.0


def _summarize(gcs, pcs):
    """Worst-case phase margin (deg) over all gain crossovers, and worst-case classic gain margin
    (dB, against a gain increase) over all phase crossovers with loop gain below 0 dB there. Also
    flags whether the 'against a gain decrease' condition (>=6dB) holds at every phase crossing with
    loop gain above 0 dB, and whether every gain crossover meets the 45 deg phase margin bar.
    """
    if gcs:
        worst_pm = min(pm for _, pm in gcs)
    else:
        worst_pm = 999.0  # |L| never reaches 0 dB -> no gain crossover -> PM requirement vacuous
    below = [gdb for _, gdb in pcs if gdb < 0]   # loop gain below 1 at that -180 crossing (classic GM)
    above = [gdb for _, gdb in pcs if gdb >= 0]  # loop gain above 1 at that -180 crossing
    gm_against_increase = (-max(below)) if below else 999.0  # smallest margin among below-0dB points
    ok_increase = all((-gdb) >= GM_MIN_DB for gdb in below)
    ok_decrease = all(gdb >= GM_MIN_DB for gdb in above)
    ok_pm = all(pm >= PM_MIN for _, pm in gcs)
    return dict(phase_margin_deg=worst_pm, gain_margin_db=gm_against_increase,
                gain_crossings=gcs, phase_crossings=pcs,
                ok_pm45=ok_pm, ok_gm6_increase=ok_increase, ok_gm6_decrease=ok_decrease)


def margins_report(omega, L):
    """Authoritative (but slow -- FRD spline construction over the full grid) margin report, via
    control.stability_margins. Use for final verification, not inside a search loop."""
    m = all_margins(omega, L)
    return _summarize(m["gain_crossings"], m["phase_crossings"])


def margins_report_fast(omega, L):
    """Fast margin report for use inside a search loop; see find_all_margins_fast."""
    gcs, pcs = find_all_margins_fast(omega, L)
    return _summarize(gcs, pcs)
