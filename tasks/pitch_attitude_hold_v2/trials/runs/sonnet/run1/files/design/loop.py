"""Linear loop-shaping helpers: fast frequency response, loop gain with actuator+delay, margins."""
import json
import pathlib
import numpy as np
import control

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV = ROOT / "environment"

TAU_DELAY = 0.040   # s, sensor delay
TAU_ACT = 0.05      # s, actuator lag
RATE_LIMIT = np.radians(60.0)   # rad/s
POS_LIMIT = np.radians(25.0)    # rad

OMEGA_GRID = np.logspace(np.log10(0.001), np.log10(1000.0), 200001)


def load_plant(va):
    d = json.load(open(ENV / f"plant_{va}.json"))
    A = np.array(d["A"], dtype=float)
    B = np.array(d["B"], dtype=float)   # (4,1)
    C = np.array(d["C"], dtype=float)   # rows: theta, q
    trim = d["trim"]
    return A, B, C, trim


def freqresp_eig(A, B, C, omega):
    """G(jw) = C (jwI-A)^-1 B, vectorized. Returns (n_outputs, len(omega)) complex."""
    eigvals, V = np.linalg.eig(A)
    Vinv = np.linalg.inv(V)
    CV = C @ V
    VinvB = Vinv @ B
    coeff = CV * VinvB[:, 0]
    denom = 1j * omega[None, :] - eigvals[:, None]
    return coeff @ (1.0 / denom)


def loop_gain(Kp, Ki, Kq, A, B, C, omega, tau_delay=TAU_DELAY, tau_act=TAU_ACT):
    """L(jw) = e^-jw*tau * Act(jw) * [ (Kp+Ki/jw)*Theta(jw) + Kq*Q(jw) ]"""
    G = freqresp_eig(A, B, C, omega)   # row0 theta, row1 q
    Theta, Q = G[0], G[1]
    jw = 1j * omega
    Act = 1.0 / (1.0 + jw * tau_act)
    delay = np.exp(-jw * tau_delay)
    ctrl = (Kp + Ki / jw) * Theta + Kq * Q
    return delay * Act * ctrl


def _crossings(f_vals, omega):
    """Zero crossings of a smooth real function f sampled at omega (dense grid), via linear
    interpolation between adjacent samples (grid is fine enough that this is essentially exact).
    Returns (indices_below, frac) so callers can interpolate any array at the same crossings.
    """
    s = np.sign(f_vals)
    idx = np.where(np.diff(s) != 0)[0]
    idx = idx[(f_vals[idx] != 0)]  # drop degenerate exact-zero grid hits (handled by neighbour)
    f0, f1 = f_vals[idx], f_vals[idx + 1]
    frac = -f0 / (f1 - f0)
    return idx, frac


def _interp_complex(L, idx, frac):
    return L[idx] + frac * (L[idx + 1] - L[idx])


def _interp_real(omega, idx, frac):
    return omega[idx] + frac * (omega[idx + 1] - omega[idx])


def find_margins(L, omega):
    """Fast replacement for control.stability_margins(..., returnall=True), specialised to a dense
    FRD-style (mag, phase, omega) triple. Avoids control's smoothing-spline / local-minima search
    (control.stability_margins is unusably slow on a 200001-point grid with a delay term, because the
    'wstab' local-minima search calls scipy.optimize.minimize_scalar for every tiny numerical wiggle in
    |L+1| -- something we don't need, since R2 only asks for GM at phase crossings and PM at gain
    crossings). Cross-checked against control.stability_margins on a coarser grid, see design/verify_margins.py.

    Returns: GM_db (array, one per -180 deg phase crossing; 20*log10(1/|L|), can be negative when
    |L|>1 at that crossing -- that IS the margin against a gain decrease), PM_deg (array, one per
    |L|=1 crossing), wpc (phase-crossover frequencies), wgc (gain-crossover frequencies).
    """
    arg = np.angle(-L)   # robust: crosses 0 exactly where angle(L) crosses +-180, no branch-cut artifact
    idx, frac = _crossings(arg, omega)
    # keep only genuine phase crossings (control filters the same way): real(L) <= 0 nearby
    keep = (np.real(L[idx]) <= 0) | (np.real(L[idx + 1]) <= 0)
    idx, frac = idx[keep], frac[keep]
    L_pc = _interp_complex(L, idx, frac)
    wpc = _interp_real(omega, idx, frac)
    with np.errstate(divide="ignore"):
        GM_db = -20.0 * np.log10(np.abs(L_pc))

    mag_minus_1 = np.abs(L) - 1.0
    idx2, frac2 = _crossings(mag_minus_1, omega)
    L_gc = _interp_complex(L, idx2, frac2)
    wgc = _interp_real(omega, idx2, frac2)
    PM_deg = np.remainder(np.degrees(np.angle(L_gc)), 360.0) - 180.0

    order = np.argsort(wpc)
    wpc, GM_db = wpc[order], GM_db[order]
    order2 = np.argsort(wgc)
    wgc, PM_deg = wgc[order2], PM_deg[order2]
    return GM_db, PM_deg, wpc, wgc


def margins_report(L, omega, verbose=False):
    """Worst-case GM (dB) and PM (deg) across ALL crossings, per R2's wording (gain margin against
    increase AND against decrease at every -180 crossing; phase margin at every gain crossover)."""
    GM_db, PM_deg, wpc, wgc = find_margins(L, omega)
    if verbose:
        print("phase crossings (rad/s):", wpc)
        print("  GM (dB) at each:", GM_db)
        print("gain crossings (rad/s):", wgc)
        print("  PM (deg) at each:", PM_deg)
    worst_gm_db = np.min(np.abs(GM_db)) if len(GM_db) else np.inf
    worst_pm = np.min(PM_deg) if len(PM_deg) else np.inf
    return worst_gm_db, worst_pm, dict(GM_db=GM_db, PM=PM_deg, wpc=wpc, wgc=wgc)


def report_margins_grader_style(Kp, Ki, Kq, A, B, C, omega=None):
    """phase_margin_deg (min PM over gain crossovers) and gain_margin_db against an INCREASE
    (i.e. among crossings where |L|<1, the smallest GM_db; matches the report.json field
    'gain_margin_db: the margin against a gain increase')."""
    if omega is None:
        omega = OMEGA_GRID
    L = loop_gain(Kp, Ki, Kq, A, B, C, omega)
    GM_db, PM_deg, wpc, wgc = find_margins(L, omega)
    return GM_db, PM_deg, wpc, wgc


if __name__ == "__main__":
    for va in (20, 25, 32):
        A, B, C, trim = load_plant(va)
        G = freqresp_eig(A, B, C, OMEGA_GRID)
        # quick bode-ish printout of theta/delta_e at a few frequencies
        for w in (0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50):
            idx = np.argmin(np.abs(OMEGA_GRID - w))
            th = G[0, idx]
            print(f"va={va} w={w:6.3f} |Theta/de|={np.abs(th):9.4f} phase={np.degrees(np.angle(th)):8.2f} deg")
        print()
