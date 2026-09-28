"""Shared model utilities for the pitch attitude hold design.

Everything here mirrors the README's "How the grader simulates" section as closely as possible:
- exact e^{-s tau} delay in frequency response, on the grader's exact frequency grid;
- exact zero-order-hold discretization of the plant at dt = 1 ms;
- actuator integrated with forward Euler, with rate and position saturation;
- controller integrator with forward Euler;
- delay implemented as an exact 40-sample shift register.
"""
import json
import pathlib

import numpy as np
import control as ct
from scipy.signal import cont2discrete

HERE = pathlib.Path(__file__).parent
ENV = HERE.parent / "environment"

plant = json.loads((ENV / "plant.json").read_text())
A = np.array(plant["A"], dtype=float)
B = np.array(plant["B"], dtype=float)
C = np.array(plant["C"], dtype=float)
D = np.array(plant["D"], dtype=float)
TRIM_DELTA_E_RAD = plant["trim"]["delta_e_rad"]
TRIM_DELTA_E_DEG = np.degrees(TRIM_DELTA_E_RAD)

# ---- actuator & sensor constants -------------------------------------------------
TAU_ACT = 0.05          # s, first order lag time constant
RATE_LIMIT_DEG = 60.0   # deg/s
RATE_LIMIT = np.radians(RATE_LIMIT_DEG)  # rad/s
POS_LIMIT_ABS_DEG = 25.0  # deg, absolute deflection limit (trim + perturbation)
# perturbation limits (rad), from the absolute +-25 deg limit minus trim
DELTA_MIN = np.radians(-POS_LIMIT_ABS_DEG) - TRIM_DELTA_E_RAD
DELTA_MAX = np.radians(POS_LIMIT_ABS_DEG) - TRIM_DELTA_E_RAD
DELAY_S = 0.040  # s

DT = 0.001  # s, grader's fixed time step
DELAY_STEPS = round(DELAY_S / DT)
assert DELAY_STEPS == 40

THETA_IDX = 3
Q_IDX = 2

# exact ZOH discretization of the plant at dt = 1 ms (state -> state, ignoring C/D since
# theta and q are just states 3 and 2 directly)
_Ad, _Bd, _Cd, _Dd, _ = cont2discrete((A, B, C, D), DT, method="zoh")
AD = _Ad
BD = _Bd.reshape(-1)


_sys_theta = ct.ss(A, B, C[0:1, :], D[0:1, :])
_tf_theta = ct.tf(_sys_theta)
_GTH_NUM = np.array(_tf_theta.num[0][0], dtype=float)
_GTH_DEN = np.array(_tf_theta.den[0][0], dtype=float)
# sanity: q = d(theta)/dt exactly, so Gq(s) = s * Gtheta(s) (same denominator, numerator shifted)
_GQ_NUM = np.concatenate([_GTH_NUM, [0.0]])


def gtheta_gq(s):
    """Exact frequency response of theta/delta_e and q/delta_e at complex frequencies s (array).

    Evaluated as rational polynomials (from the state-space model, verified to agree with a direct
    (sI-A)^-1 B evaluation to ~1e-14) so this is fast enough to use on the full 200001-point grid.
    """
    den = np.polyval(_GTH_DEN, s)
    theta = np.polyval(_GTH_NUM, s) / den
    q = np.polyval(_GQ_NUM, s) / den
    return theta, q


def loop_gain(Kp, Ki, Kq, w):
    """Exact loop transfer function L(jw), broken between controller and actuator.

    L(s) = Gact(s) * e^{-s*tau} * [ (Kp + Ki/s) * Gtheta(s) + Kq * Gq(s) ]
    """
    s = 1j * w
    gth, gq = gtheta_gq(s)
    gact = 1.0 / (TAU_ACT * s + 1.0)
    delay = np.exp(-s * DELAY_S)
    ctrl_fb = (Kp + Ki / s) * gth + Kq * gq
    return gact * delay * ctrl_fb


def grader_freq_grid():
    return np.logspace(np.log10(0.001), np.log10(1000.0), 200001)


def margins(Kp, Ki, Kq, w=None, return_all=False):
    """Compute phase margin (deg) and gain margins (dB) exactly as R2 describes.

    Returns dict with:
      pm_deg: worst-case (minimum) phase margin over all gain crossovers (|L|=1)
      gm_increase_db: worst-case margin against a gain increase (min over phase
                      crossovers where |L|<1), 999 if none exist
      gm_decrease_db: worst-case margin against a gain decrease (min over phase
                      crossovers where |L|>=1), 999 if none exist
      n_gain_cross, n_phase_cross: counts, for sanity checking
    """
    if w is None:
        w = grader_freq_grid()
    L = loop_gain(Kp, Ki, Kq, w)
    mag = np.abs(L)
    mag_db = 20 * np.log10(mag)
    phase = np.unwrap(np.angle(L))
    phase_deg = np.degrees(phase)
    logw = np.log(w)

    # --- gain crossovers: mag_db crosses 0 (vectorized sign-change detection) -------
    sgn = np.sign(mag_db)
    idx = np.where(np.diff(sgn) != 0)[0]
    t = mag_db[idx] / (mag_db[idx] - mag_db[idx + 1])
    gain_cross_w = np.exp(logw[idx] + t * (logw[idx + 1] - logw[idx]))
    ph = phase_deg[idx] + t * (phase_deg[idx + 1] - phase_deg[idx])
    pm_list = (ph - (-180.0 + 360.0 * np.round((ph + 180.0) / 360.0))).tolist()
    gain_cross_w = gain_cross_w.tolist()

    # --- phase crossovers: phase crosses an odd multiple of 180 deg (vectorized) ----
    m = np.floor((phase_deg + 180.0) / 360.0)
    idx2 = np.where(np.diff(m) != 0)[0]
    target = -180.0 + 360.0 * np.maximum(m[idx2], m[idx2 + 1])
    a = phase_deg[idx2] - target
    bb = phase_deg[idx2 + 1] - target
    t2 = a / (a - bb)
    phase_cross_w = np.exp(logw[idx2] + t2 * (logw[idx2 + 1] - logw[idx2]))
    gdb = mag_db[idx2] + t2 * (mag_db[idx2 + 1] - mag_db[idx2])
    inc_mask = gdb < 0
    gm_inc_list = (-gdb[inc_mask]).tolist()
    gm_dec_list = (gdb[~inc_mask]).tolist()
    phase_cross_w = phase_cross_w.tolist()

    pm_deg = min(pm_list) if pm_list else 999.0
    gm_increase_db = min(gm_inc_list) if gm_inc_list else 999.0
    gm_decrease_db = min(gm_dec_list) if gm_dec_list else 999.0

    result = dict(pm_deg=pm_deg, gm_increase_db=gm_increase_db, gm_decrease_db=gm_decrease_db,
                  n_gain_cross=len(pm_list), n_phase_cross=len(gm_inc_list) + len(gm_dec_list))
    if return_all:
        result["pm_list"] = pm_list
        result["gain_cross_w"] = gain_cross_w
        result["gm_inc_list"] = gm_inc_list
        result["gm_dec_list"] = gm_dec_list
        result["phase_cross_w"] = phase_cross_w
    return result


def simulate(Kp, Ki, Kq, b, theta_cmd_deg=5.0, T=20.0, dt=DT):
    """Replicates the grader's exact time-domain recipe.

    Returns a dict of time histories (all in degrees where relevant) and t.
    """
    n_steps = round(T / dt)
    theta_cmd = np.radians(theta_cmd_deg)

    x = np.zeros((n_steps + 1, A.shape[0]))
    delta = np.zeros(n_steps + 1)          # actuator state (perturbation, rad)
    delta_cmd = np.zeros(n_steps + 1)      # controller output before actuator (rad)
    integ = np.zeros(n_steps + 1)          # controller integral state

    for k in range(n_steps):
        k_delay = k - DELAY_STEPS
        if k_delay >= 0:
            theta_m = x[k_delay, THETA_IDX]
            q_m = x[k_delay, Q_IDX]
        else:
            theta_m = 0.0
            q_m = 0.0

        error = theta_cmd - theta_m
        delta_cmd[k] = Kp * (b * theta_cmd - theta_m) + Ki * integ[k] - Kq * q_m

        # actuator: dδ/dt = sat_rate((sat_position(δcmd) - δ)/tau), forward Euler
        d_cmd_sat = min(max(delta_cmd[k], DELTA_MIN), DELTA_MAX)
        rate = (d_cmd_sat - delta[k]) / TAU_ACT
        rate = min(max(rate, -RATE_LIMIT), RATE_LIMIT)
        delta[k + 1] = delta[k] + dt * rate
        delta[k + 1] = min(max(delta[k + 1], DELTA_MIN), DELTA_MAX)

        # plant: exact ZOH step using the current (held) surface deflection
        x[k + 1] = AD @ x[k] + BD * delta[k]

        # controller integrator, forward Euler
        integ[k + 1] = integ[k] + dt * error

    # fill last delta_cmd sample (k = n_steps) for completeness / max tracking
    k = n_steps
    k_delay = k - DELAY_STEPS
    theta_m = x[k_delay, THETA_IDX] if k_delay >= 0 else 0.0
    q_m = x[k_delay, Q_IDX] if k_delay >= 0 else 0.0
    delta_cmd[k] = Kp * (b * theta_cmd - theta_m) + Ki * integ[k] - Kq * q_m

    t = np.arange(n_steps + 1) * dt
    theta_deg = np.degrees(x[:, THETA_IDX])
    q_deg = np.degrees(x[:, Q_IDX])
    delta_deg = np.degrees(delta)
    delta_cmd_deg = np.degrees(delta_cmd)
    elevator_abs_deg = TRIM_DELTA_E_DEG + delta_cmd_deg  # R4: trim + controller output
    elevator_abs_actual_deg = TRIM_DELTA_E_DEG + delta_deg

    return dict(t=t, theta_deg=theta_deg, q_deg=q_deg, delta_deg=delta_deg,
                delta_cmd_deg=delta_cmd_deg, elevator_abs_deg=elevator_abs_deg,
                elevator_abs_actual_deg=elevator_abs_actual_deg, theta_cmd_deg=theta_cmd_deg)


def metrics(sim, theta_cmd_deg=5.0, band=0.1):
    theta = sim["theta_deg"]
    t = sim["t"]
    peak = np.max(theta)
    overshoot_pct = (peak - theta_cmd_deg) / theta_cmd_deg * 100.0

    outside = np.abs(theta - theta_cmd_deg) > band
    if np.any(outside):
        settling_time = t[np.max(np.where(outside)[0])]
    else:
        settling_time = 0.0

    max_elevator_deg = np.max(np.abs(sim["elevator_abs_deg"]))
    max_elevator_actual_deg = np.max(np.abs(sim["elevator_abs_actual_deg"]))

    return dict(overshoot_pct=overshoot_pct, settling_time_s=settling_time,
                max_elevator_deg=max_elevator_deg, max_elevator_actual_deg=max_elevator_actual_deg,
                peak_theta_deg=peak)


def P_response(w):
    """Gact(jw)*delay(jw)*Ghat(jw) where Ghat = -Gtheta (positive DC gain convention)."""
    s = 1j * np.asarray(w)
    gth, _ = gtheta_gq(s)
    Ghat = -gth
    gact = 1.0 / (TAU_ACT * s + 1.0)
    delay = np.exp(-s * DELAY_S)
    return gact * delay * Ghat


def design_from_wc(wc, pm_target_deg, Ti):
    """Solve for (Kp, Ki, Kq) placing a gain crossover at wc with the given phase margin,
    using an integral time constant Ti (Ki' = Kp'/Ti in the positive-gain convention).
    Returns the actual (signed) Kp, Ki, Kq for the README's control law.
    """
    Pw = P_response(np.array([wc]))[0]
    theta_target = np.radians(-180.0 + pm_target_deg)
    T = np.exp(1j * theta_target)
    Z = T / Pw
    Kp_pos = Z.real
    X = Z.imag
    Ki_pos = Kp_pos / Ti
    Kq_pos = (X + Ki_pos / wc) / wc
    return -Kp_pos, -Ki_pos, -Kq_pos


def closed_loop_max_real_part(Kp, Ki, Kq, pade_n=14):
    """Max real part of the closed-loop poles (R1 stability check), via a clean polynomial
    construction of the loop transfer function and its 1+L(s)=0 characteristic polynomial.

    Built as ctrl_fb(s) = Gtheta(s) * (Kq s^2 + Kp s + Ki)/s -- one polynomial ratio, using the
    exact identity Gq(s) = s*Gtheta(s) -- rather than forming (Kp+Ki/s)*Gtheta + Kq*Gq via
    TransferFunction addition. That addition route was tried first and rejected: python-control's
    "+" does not reduce by the gcd, so since Gtheta and Gq share a denominator, it reintroduces
    the open-loop plant's own characteristic polynomial as a spurious *exact* common factor of
    the resulting L's numerator and denominator. Root-finding on that (via ct.pole() or minreal())
    is then corrupted: minreal's tolerance-based cancellation caught it for some Pade orders and
    not others (same gains, only pade_n changed, flipped the max real part between -0.145 and
    -0.344). The frequency-response margins() function is NOT affected by this (N(jw)/D(jw)
    evaluated at a point is correct regardless of an uncancelled common factor) -- only this
    root-finding step needs the clean construction. Cross-checked against an independent
    hand-built closed-loop state-space (plant + actuator + two Pade delay realizations for theta
    and q + integrator, no control-library tf algebra at all): both agree to 6 decimals across
    pade_n = 6..20, and the resulting pole matches the decay rate seen in the nonlinear
    time-domain simulation's tail.
    """
    num_d, den_d = ct.pade(DELAY_S, pade_n)
    num_act, den_act = [1.0], [TAU_ACT, 1.0]
    num_pid = [Kq, Kp, Ki]
    den_pid = [1.0, 0.0]
    num_ctrl = np.polymul(_GTH_NUM, num_pid)
    den_ctrl = np.polymul(_GTH_DEN, den_pid)
    num_L = np.polymul(np.polymul(num_act, num_d), num_ctrl)
    den_L = np.polymul(np.polymul(den_act, den_d), den_ctrl)
    n = max(len(num_L), len(den_L))
    char = np.pad(den_L, (n - len(den_L), 0)) + np.pad(num_L, (n - len(num_L), 0))
    return max(e.real for e in np.roots(char))
