"""Fast, self-contained margin analysis from a complex frequency response array.

Method: gain crossovers where |L|=1 (interpolate in log|L|); phase/gain-margin
crossovers where the Nyquist locus crosses the negative real axis (Im(L)=0, Re(L)<0),
found via sign changes of Im(L) filtered to Re(L)<0 -- equivalent to, but far simpler
and faster than, unwrapping phase, and matches control.stability_margins' own 'poly'
method logic (which looks for Im(H(iw))==0). Validated against control.stability_margins
on reference cases in validate_margins.py / validate_fast.py.
"""
import numpy as np


def _interp_crossing(w, y, i, target=0.0):
    """Linear interpolation of the crossing of y(w)=target between i and i+1;
    w is interpolated in log-space (natural for a log-spaced grid)."""
    y0, y1 = y[i], y[i + 1]
    frac = (target - y0) / (y1 - y0)
    lw = np.log(w[i]) + frac * (np.log(w[i + 1]) - np.log(w[i]))
    return np.exp(lw), frac


def analyze_margins(w, L):
    mag = np.abs(L)
    logmag = np.log10(mag)
    real = L.real
    imag = L.imag

    # --- gain crossovers: |L| = 1 ---
    gc_w, gc_phase_deg = [], []
    sgn = np.sign(logmag)
    for i in np.where(np.diff(sgn) != 0)[0]:
        if logmag[i] == logmag[i + 1]:
            continue
        wc, frac = _interp_crossing(w, logmag, i, 0.0)
        re = real[i] + frac * (real[i + 1] - real[i])
        im = imag[i] + frac * (imag[i + 1] - imag[i])
        gc_w.append(wc)
        gc_phase_deg.append(np.degrees(np.arctan2(im, re)))
    gc_w = np.array(gc_w)
    gc_phase_deg = np.array(gc_phase_deg)
    # phase margin: standard PM = 180 + phase, using the WRAPPED angle at the crossover.
    # This matches control.stability_margins' definition (remainder(angle,360)-180) and is
    # unambiguous here because at a genuine gain crossover the relevant "phase" is just the
    # instantaneous angle of L at that point (no multi-wrap ambiguity: the margin is how far
    # that specific point on the unit circle is from -1).
    pm_deg = 180.0 + gc_phase_deg
    # normalize into (-180,180]
    pm_deg = (pm_deg + 180) % 360 - 180

    # --- phase/gain-margin crossovers: Im(L)=0 crossing with Re(L)<0 ---
    pc_w, pc_gain_db = [], []
    sgn_im = np.sign(imag)
    for i in np.where(np.diff(sgn_im) != 0)[0]:
        if imag[i] == imag[i + 1]:
            continue
        wc, frac = _interp_crossing(w, imag, i, 0.0)
        re = real[i] + frac * (real[i + 1] - real[i])
        if re >= 0:
            continue
        lm = logmag[i] + frac * (logmag[i + 1] - logmag[i])
        pc_w.append(wc)
        pc_gain_db.append(20.0 * lm)
    pc_w = np.array(pc_w)
    pc_gain_db = np.array(pc_gain_db)

    gm_increase_candidates = -pc_gain_db[pc_gain_db < 0]   # margin (dB) against a gain increase
    gm_decrease_candidates = pc_gain_db[pc_gain_db >= 0]   # margin (dB) against a gain decrease

    worst_pm = float(np.min(np.abs(pm_deg))) if len(pm_deg) else 999.0
    worst_pm_signed = pm_deg[np.argmin(np.abs(pm_deg))] if len(pm_deg) else 999.0
    gm_against_increase_db = float(np.min(gm_increase_candidates)) if len(gm_increase_candidates) else 999.0
    gm_against_decrease_worst_db = float(np.min(gm_decrease_candidates)) if len(gm_decrease_candidates) else 999.0
    gm_against_decrease_ok = bool(gm_against_decrease_worst_db >= 6.0 - 1e-9)

    return {
        "gc_w": gc_w, "gc_phase_deg": gc_phase_deg, "pm_deg": pm_deg,
        "pc_w": pc_w, "pc_gain_db": pc_gain_db,
        "worst_pm_deg": worst_pm_signed,
        "worst_pm_abs_deg": worst_pm,
        "gm_against_increase_db": gm_against_increase_db,
        "gm_against_decrease_worst_db": gm_against_decrease_worst_db,
        "gm_against_decrease_ok": gm_against_decrease_ok,
    }


if __name__ == "__main__":
    import control as ct

    w = np.logspace(-3, 3, 20001)
    G = ct.tf([10], np.poly([-1, -2, -3]))
    resp = G(1j * w)
    m = analyze_margins(w, resp)
    print("Case1 fast:", m["worst_pm_deg"], m["gm_against_increase_db"], m["gc_w"], m["pc_w"], m["pc_gain_db"])
    gm_poly, pm_poly, wpc_poly, wgc_poly = ct.margin(G)
    print("Case1 poly:", pm_poly, 20*np.log10(gm_poly), wgc_poly, wpc_poly)

    num = [5]
    den = np.polymul(np.poly([0, -2]), [0.05, 1])
    Gnd = ct.tf(num, den)
    resp2 = Gnd(1j * w) * np.exp(-0.04j * w)
    m2 = analyze_margins(w, resp2)
    print("Case2 fast: PM=", m2["worst_pm_deg"], "GMinc_db=", m2["gm_against_increase_db"])
    print("  all pc (w, gain_db):", list(zip(m2["pc_w"], m2["pc_gain_db"])))
    print("  all gc (w, pm_deg):", list(zip(m2["gc_w"], m2["pm_deg"])))
    Gpade = ct.tf(*ct.pade(0.04, 10))
    gm3, pm3, wpc3, wgc3 = ct.margin(Gnd * Gpade)
    print("Case2 pade10 poly: PM=", pm3, "GM_db=", 20*np.log10(gm3), "wgc=", wgc3, "wpc=", wpc3)
