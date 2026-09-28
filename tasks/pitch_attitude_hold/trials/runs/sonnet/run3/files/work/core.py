"""Core model, margin, and time-domain simulation functions for the pitch attitude hold design.

All angles handled in radians internally; conversions to/from degrees happen at the edges.
"""
import json
import pathlib

import numpy as np
import control as ct

HERE = pathlib.Path(__file__).parent
ENV = HERE.parent / "environment"

DEG = np.pi / 180.0

# ---------------------------------------------------------------------------
# Plant
# ---------------------------------------------------------------------------

def load_plant():
    p = json.loads((ENV / "plant.json").read_text(encoding="utf-8"))
    A = np.array(p["A"], dtype=float)
    B = np.array(p["B"], dtype=float)
    C = np.array(p["C"], dtype=float)
    D = np.array(p["D"], dtype=float)
    trim = p["trim"]
    return A, B, C, D, trim


def theta_tf():
    """Return (num, den) polynomial coefficients (highest power first) of Gtheta(s) = theta(s)/delta_e(s)."""
    A, B, C, D, trim = load_plant()
    Ctheta = C[0:1, :]  # row for theta output
    sys_theta = ct.ss(A, B, Ctheta, np.zeros((1, 1)))
    tf_theta = ct.ss2tf(sys_theta)
    num = np.array(tf_theta.num[0][0])
    den = np.array(tf_theta.den[0][0])
    return num, den


# Actuator: first order lag, tau = 0.05 s -> Act(s) = 1/(0.05 s + 1)
TAU_ACT = 0.05
DELAY = 0.04  # s
RATE_LIMIT = 60.0 * DEG  # rad/s
POS_LIMIT_ABS = 25.0 * DEG  # rad, absolute deflection limit


def limits_from_trim(trim):
    delta_e_trim = trim["delta_e_rad"]
    pert_min = -POS_LIMIT_ABS - delta_e_trim
    pert_max = POS_LIMIT_ABS - delta_e_trim
    return pert_min, pert_max


# ---------------------------------------------------------------------------
# Frequency response of the loop transfer function
# L(s) = Act(s) * e^{-s*DELAY} * Gtheta(s) * (Kp + Kq*s + Ki/s)
# broken at the elevator command, per the README.
# ---------------------------------------------------------------------------

def loop_response(Kp, Ki, Kq, w, num_theta, den_theta):
    """Complex frequency response L(jw) for an array of w (rad/s), w must be > 0."""
    s = 1j * w
    Gtheta = np.polyval(num_theta, s) / np.polyval(den_theta, s)
    Act = 1.0 / (TAU_ACT * s + 1.0)
    delay = np.exp(-s * DELAY)
    C = Kp + Kq * s + Ki / s
    return Act * delay * Gtheta * C


def _crossings(w, f_vals, target=0.0):
    """Vectorized detection of linearly-interpolated crossings of f_vals(w) == target.

    Returns (wc, frac) arrays: wc = crossing frequency, frac = interpolation fraction in [0,1]
    used to interpolate any other array sampled on the same w grid at the same crossings.
    """
    d = f_vals - target
    prod = d[:-1] * d[1:]
    idx = np.where(prod < 0)[0]
    exact = np.where(d == 0.0)[0]
    if idx.size == 0 and exact.size == 0:
        return np.array([]), np.array([], dtype=int), np.array([])
    frac = d[idx] / (d[idx] - d[idx + 1])
    wc = w[idx] + frac * (w[idx + 1] - w[idx])
    # exact hits (rare, ignore fractional interp, frac=0)
    if exact.size:
        wc = np.concatenate([wc, w[exact]])
        idx = np.concatenate([idx, exact])
        frac = np.concatenate([frac, np.zeros(exact.size)])
    order = np.argsort(wc)
    return wc[order], idx[order], frac[order]


def compute_margins(Kp, Ki, Kq, num_theta, den_theta, n=200001, wmin=1e-3, wmax=1e3):
    """Replicates the grader's exact frequency-response margin computation.

    Returns dict with:
      phase_margin_deg : minimum phase margin (deg) over all gain crossovers (|L|=1); +999 if none
      gain_margin_incr_db : minimum margin (dB) against a gain INCREASE, over all -180 deg phase
                             crossings where |L| < 1; +999 if none such crossing exists
      gain_margin_decr_db : minimum margin (dB) against a gain DECREASE, over all -180 deg phase
                             crossings where |L| > 1; +999 if none such crossing exists (this is the
                             "binding" direction only when a design has a high-gain -180 crossing)
      details: crossover frequencies, for diagnostics
    """
    w = np.logspace(np.log10(wmin), np.log10(wmax), n)
    L = loop_response(Kp, Ki, Kq, w, num_theta, den_theta)
    mag_db = 20 * np.log10(np.abs(L))
    phase_deg = np.unwrap(np.angle(L)) * 180.0 / np.pi

    # --- Gain crossovers (|L| = 1, mag_db = 0) -> phase margins ---
    wc, idx, frac = _crossings(w, mag_db, 0.0)
    ph = phase_deg[idx] + frac * (phase_deg[idx + 1] - phase_deg[idx])
    pm_raw = 180.0 + ph
    pm_folded = ((pm_raw + 180.0) % 360.0) - 180.0
    pm_list = pm_folded.tolist()
    pm_freqs = wc.tolist()

    # --- Phase crossovers (phase = -180 mod 360) -> gain margins ---
    lo = phase_deg.min()
    target_lines = np.arange(-180.0, lo - 360.0, -360.0)
    gm_incr_list, gm_incr_freqs = [], []
    gm_decr_list, gm_decr_freqs = [], []
    for line in target_lines:
        wcp, idxp, fracp = _crossings(w, phase_deg, line)
        if wcp.size == 0:
            continue
        mdb = mag_db[idxp] + fracp * (mag_db[idxp + 1] - mag_db[idxp])
        incr_mask = mdb < 0
        decr_mask = mdb > 0
        gm_incr_list.extend((-mdb[incr_mask]).tolist())
        gm_incr_freqs.extend(wcp[incr_mask].tolist())
        gm_decr_list.extend(mdb[decr_mask].tolist())
        gm_decr_freqs.extend(wcp[decr_mask].tolist())
        zero_mask = mdb == 0
        if np.any(zero_mask):
            gm_incr_list.extend([0.0] * int(zero_mask.sum()))
            gm_incr_freqs.extend(wcp[zero_mask].tolist())

    phase_margin_deg = min(pm_list) if pm_list else 999.0
    gain_margin_incr_db = min(gm_incr_list) if gm_incr_list else 999.0
    gain_margin_decr_db = min(gm_decr_list) if gm_decr_list else 999.0

    return {
        "phase_margin_deg": phase_margin_deg,
        "gain_margin_incr_db": gain_margin_incr_db,
        "gain_margin_decr_db": gain_margin_decr_db,
        "pm_all": pm_list,
        "pm_freqs": pm_freqs,
        "gm_incr_freqs": gm_incr_freqs,
        "gm_decr_freqs": gm_decr_freqs,
        "w": w,
        "mag_db": mag_db,
        "phase_deg": phase_deg,
    }


# ---------------------------------------------------------------------------
# Exact nonlinear time-domain simulation, matching the grader's algorithm
# ---------------------------------------------------------------------------

def simulate(Kp, Ki, Kq, b, T=20.0, dt=1e-3, theta_cmd_deg=5.0):
    A, B, C, D, trim = load_plant()
    pert_min, pert_max = limits_from_trim(trim)
    delta_e_trim = trim["delta_e_rad"]

    n = int(round(T / dt))
    delay_steps = int(round(DELAY / dt))
    assert abs(delay_steps * dt - DELAY) < 1e-12

    # exact ZOH discretization of the plant for step dt
    sysd = ct.c2d(ct.ss(A, B, np.eye(4), np.zeros((4, 1))), dt, method="zoh")
    Ad = np.array(sysd.A)
    Bd = np.array(sysd.B).reshape(4)

    theta_cmd = theta_cmd_deg * DEG

    x = np.zeros(4)  # u, w, q, theta perturbation states
    delta = 0.0       # actuator (elevator) perturbation state
    integ = 0.0       # controller integral state

    theta_hist = np.zeros(n + 1)
    q_hist = np.zeros(n + 1)
    delta_cmd_hist = np.zeros(n + 1)
    delta_hist = np.zeros(n + 1)
    t_hist = np.arange(n + 1) * dt

    theta_hist[0] = x[3]
    q_hist[0] = x[2]
    delta_hist[0] = delta

    for k in range(n):
        # delayed measurements (zero before t=0)
        idx = k - delay_steps
        theta_m = theta_hist[idx] if idx >= 0 else 0.0
        q_m = q_hist[idx] if idx >= 0 else 0.0

        delta_cmd = Kp * (b * theta_cmd - theta_m) + Ki * integ - Kq * q_m
        delta_cmd_hist[k] = delta_cmd

        # actuator: position-saturate the command, then rate-saturate the resulting rate, forward Euler
        delta_cmd_sat = min(max(delta_cmd, pert_min), pert_max)
        rate = (delta_cmd_sat - delta) / TAU_ACT
        rate = min(max(rate, -RATE_LIMIT), RATE_LIMIT)
        delta_next = delta + dt * rate
        delta_next = min(max(delta_next, pert_min), pert_max)

        # plant propagation, ZOH with current delta held over the step
        x_next = Ad @ x + Bd * delta

        # controller integrator, forward Euler
        integ_next = integ + dt * (theta_cmd - theta_m)

        x, delta, integ = x_next, delta_next, integ_next
        theta_hist[k + 1] = x[3]
        q_hist[k + 1] = x[2]
        delta_hist[k + 1] = delta

    # last delta_cmd (k = n) uses measurements at n for completeness (not used further, but fill for plotting)
    idx = n - delay_steps
    theta_m = theta_hist[idx] if idx >= 0 else 0.0
    q_m = q_hist[idx] if idx >= 0 else 0.0
    delta_cmd_hist[n] = Kp * (b * theta_cmd - theta_m) + Ki * integ - Kq * q_m

    return {
        "t": t_hist,
        "theta": theta_hist,
        "q": q_hist,
        "delta_cmd": delta_cmd_hist,
        "delta": delta_hist,
        "theta_cmd": theta_cmd,
        "delta_e_trim": delta_e_trim,
        "pert_min": pert_min,
        "pert_max": pert_max,
    }


def metrics_from_sim(sim):
    theta_deg = sim["theta"] / DEG
    theta_cmd_deg = sim["theta_cmd"] / DEG
    t = sim["t"]

    overshoot_pct = max(0.0, (theta_deg.max() - theta_cmd_deg)) / theta_cmd_deg * 100.0

    band = 0.1  # deg, 2% of 5 deg command
    outside = np.abs(theta_deg - theta_cmd_deg) > band
    if outside.any():
        last_outside_idx = np.where(outside)[0].max()
        settling_time_s = t[last_outside_idx] if last_outside_idx < len(t) - 1 else t[-1]
        # if the last outside sample is the final sample, settling didn't happen within T
        if last_outside_idx == len(t) - 1:
            settling_time_s = t[-1]
    else:
        settling_time_s = 0.0

    abs_elevator_deg = np.abs((sim["delta_cmd"] + sim["delta_e_trim"]) / DEG)
    max_elevator_deg = abs_elevator_deg.max()

    return {
        "overshoot_pct": overshoot_pct,
        "settling_time_s": settling_time_s,
        "max_elevator_deg": max_elevator_deg,
        "theta_max_deg": theta_deg.max(),
    }
