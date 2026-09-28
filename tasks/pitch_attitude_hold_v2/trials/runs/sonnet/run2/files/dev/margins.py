"""Gain/phase margin computation, replicating the grader's frequency-domain method:
exact frequency response (with e^{-s*tau} for the delay) on 200001 log-spaced
points from 0.001 to 1000 rad/s, loop broken at the elevator command, ALL
gain-crossover and ALL phase-crossover (-180 deg) points considered (not just
the single "worst" pair), so that conditionally-stable configurations are
caught correctly.

Implemented as a direct vectorized scan of the precomputed (mag, phase, omega)
arrays with linear-interpolation refinement of each crossing. This gives the
same result as control.stability_margins(..., returnall=True) fed the same
(mag, phase, omega) tuple (verified in dev/check_margins_impl.py against that
reference on a coarser grid -- the library call is far too slow, ~100 s per
plant, to evaluate its smoothed FRD on the full 2e5-point grid, which rules it
out for use inside a search loop or even for repeated final checks).
"""
import numpy as np

from core import loop_gain, grader_omega_grid


def _interp_root(w0, w1, f0, f1):
    """Linear-interpolation root of f between w0 and w1 (f0, f1 the values there)."""
    if f1 == f0:
        return 0.5 * (w0 + w1)
    frac = f0 / (f0 - f1)
    return w0 + frac * (w1 - w0)


def find_crossings(L, omega):
    """Scan the frequency response L(jw) (arrays, same length as omega) for:
      - gain crossovers: |L| = 1               -> (wgc, phase_deg_at_wgc)
      - phase crossovers: L crosses the negative real axis (phase = -180 mod 360)
                                                -> (w180, |L|_at_w180)
    Returns (wgc, pm_deg, w180, mag_at_180).
    """
    omega = np.asarray(omega, dtype=float)
    re = L.real
    im = L.imag
    mag = np.abs(L)

    # --- gain crossovers: |L(w)| - 1 changes sign ---
    g = mag - 1.0
    sg = np.sign(g)
    idx_gc = np.where(np.diff(sg) != 0)[0]
    wgc = np.empty(idx_gc.size)
    pm_deg = np.empty(idx_gc.size)
    for k, i in enumerate(idx_gc):
        w0, w1, f0, f1 = omega[i], omega[i + 1], g[i], g[i + 1]
        w_root = _interp_root(w0, w1, f0, f1)
        # interpolate the complex response linearly and take its angle
        t = 0.0 if f1 == f0 else (w_root - w0) / (w1 - w0)
        Lr = (1 - t) * re[i] + t * re[i + 1]
        Li = (1 - t) * im[i] + t * im[i + 1]
        phase = np.degrees(np.arctan2(Li, Lr))
        pm_deg[k] = (phase % 360.0) - 180.0
        wgc[k] = w_root

    # --- phase crossovers: Im(L) changes sign, keep only where Re(L) < 0 ---
    si = np.sign(im)
    idx_pc_raw = np.where(np.diff(si) != 0)[0]
    # keep only genuine -180 crossings (L real negative), not the +/-180 branch wrap
    # (L real positive) -- check Re at both bracketing samples
    keep = (re[idx_pc_raw] <= 0) | (re[idx_pc_raw + 1] <= 0)
    idx_pc = idx_pc_raw[keep]
    w180 = np.empty(idx_pc.size)
    mag180 = np.empty(idx_pc.size)
    for k, i in enumerate(idx_pc):
        w0, w1, f0, f1 = omega[i], omega[i + 1], im[i], im[i + 1]
        w_root = _interp_root(w0, w1, f0, f1)
        t = 0.0 if f1 == f0 else (w_root - w0) / (w1 - w0)
        Lr = (1 - t) * re[i] + t * re[i + 1]
        Li = (1 - t) * im[i] + t * im[i + 1]
        w180[k] = w_root
        mag180[k] = np.hypot(Lr, Li)

    return wgc, pm_deg, w180, mag180


def analyze(plant, Kp, Ki, Kq, omega=None):
    """Full margin analysis for one plant/gain set.

    Returns a dict with:
      phase_margin_deg  : worst-case (minimum) phase margin over all gain crossovers
      gain_margin_db    : worst-case (minimum) margin against a gain INCREASE,
                           over all -180 crossings where |L| < 1  (999 if none / infinite)
      decrease_margin_db: worst-case (minimum) margin against a gain DECREASE,
                           over all -180 crossings where |L| > 1  (999 if none / infinite)
      n_gain_crossovers, n_phase_crossovers, ok  (bool, both margin requirements met)
    """
    if omega is None:
        omega = grader_omega_grid()
    L = loop_gain(plant, omega, Kp, Ki, Kq)
    wgc, pm_deg, w180, mag180 = find_crossings(L, omega)

    if pm_deg.size == 0:
        phase_margin_deg = 999.0
    else:
        phase_margin_deg = float(np.min(pm_deg))

    if mag180.size == 0:
        gain_margin_db = 999.0
        decrease_margin_db = 999.0
    else:
        inc_mask = mag180 < 1.0
        dec_mask = mag180 > 1.0
        if np.any(inc_mask):
            gain_margin_db = float(np.min(-20.0 * np.log10(mag180[inc_mask])))
        else:
            gain_margin_db = 999.0
        if np.any(dec_mask):
            decrease_margin_db = float(np.min(20.0 * np.log10(mag180[dec_mask])))
        else:
            decrease_margin_db = 999.0

    ok = (phase_margin_deg >= 45.0) and (gain_margin_db >= 6.0) and (decrease_margin_db >= 6.0)

    return {
        "phase_margin_deg": phase_margin_deg,
        "gain_margin_db": gain_margin_db,
        "decrease_margin_db": decrease_margin_db,
        "n_gain_crossovers": int(wgc.size),
        "n_phase_crossovers": int(w180.size),
        "wgc": wgc,
        "w180": w180,
        "pm_deg": pm_deg,
        "mag180": mag180,
        "ok": bool(ok),
    }
