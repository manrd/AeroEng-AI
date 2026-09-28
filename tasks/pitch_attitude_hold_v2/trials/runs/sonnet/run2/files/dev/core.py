"""Core model, frequency-response, and nonlinear time-domain simulation for the
pitch attitude hold design task.

Everything here works in absolute SI units (rad, rad/s, s) internally; degrees are
only used at the report-formatting boundary.
"""
import json
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).parent
RUN_ROOT = HERE.parent
ENV = RUN_ROOT / "environment"

sys.path.insert(0, str(ENV))
import aircraft_model as am  # noqa: E402

D2R = np.pi / 180.0
R2D = 180.0 / np.pi

ACTUATOR_TAU = 0.05          # s
RATE_LIMIT = 60.0 * D2R      # rad/s
POS_LIMIT = 25.0 * D2R       # rad
DELAY_S = 0.040              # s
DT = 0.001                   # s, grader's fixed RK4 / Euler step
DELAY_STEPS = 40
SIM_T = 20.0                 # s
STEP_DEG = 5.0
STEP_RAD = STEP_DEG * D2R

SPEEDS = (20.0, 25.0, 32.0)


def load_plant(speed):
    name = f"plant_{speed:g}.json"
    d = json.loads((ENV / name).read_text(encoding="utf-8"))
    A = np.array(d["A"], dtype=float)
    B = np.array(d["B"], dtype=float).reshape(-1, 1)
    C = np.array(d["C"], dtype=float)
    trim = d["trim"]
    d["_A"] = A
    d["_B"] = B
    d["_C"] = C
    d["_theta_trim"] = float(trim["theta_rad"])
    d["_delta_e_trim"] = float(trim["delta_e_rad"])
    d["_delta_t_trim"] = float(trim["delta_t"])
    d["_x0"] = np.array(trim["state"], dtype=float)
    d["_speed"] = speed
    return d


def load_params():
    return am.load_params(ENV / "aircraft_aerosonde.json")


# ---------------------------------------------------------------------------
# Frequency response
# ---------------------------------------------------------------------------

def _eig_cache(plant):
    cache = plant.get("_eig")
    if cache is None:
        A, B, C = plant["_A"], plant["_B"], plant["_C"]
        lam, V = np.linalg.eig(A)
        Vinv = np.linalg.inv(V)
        z = Vinv @ B[:, 0]                     # V^-1 B, shape (n,)
        c_theta_modal = C[0, :] @ V             # shape (n,)
        c_q_modal = C[1, :] @ V
        cache = (lam, c_theta_modal * z, c_q_modal * z)
        plant["_eig"] = cache
    return cache


def plant_frf(plant, omega):
    """Return (Ptheta(jw), Pq(jw)) arrays: transfer functions from delta_e to
    theta and to q, evaluated at the given real angular-frequency array (rad/s).
    Ptheta = C_theta (jwI - A)^-1 B ,  Pq = C_q (jwI - A)^-1 B

    Uses the eigendecomposition of A (cached on the plant dict) so this is a
    cheap, fully vectorized evaluation even for ~2e5 frequency points:
        (sI-A)^-1 B = sum_i  V[:,i] * (V^-1 B)[i] / (s - lambda_i)
    """
    lam, w_theta, w_q = _eig_cache(plant)
    s = 1j * np.asarray(omega, dtype=float)
    # shape (n, len(omega)) via broadcasting
    denom = s[None, :] - lam[:, None]
    Ptheta = (w_theta[:, None] / denom).sum(axis=0)
    Pq = (w_q[:, None] / denom).sum(axis=0)
    return Ptheta, Pq


def plant_frf_direct(plant, omega):
    """Reference (slow, direct-solve) implementation of plant_frf, for cross-checking."""
    A, B, C = plant["_A"], plant["_B"], plant["_C"]
    n = A.shape[0]
    I = np.eye(n)
    jw = 1j * np.asarray(omega, dtype=float)
    Ptheta = np.empty(jw.shape, dtype=complex)
    Pq = np.empty(jw.shape, dtype=complex)
    c_theta = C[0, :]
    c_q = C[1, :]
    for i, s in enumerate(jw):
        x = np.linalg.solve(s * I - A, B[:, 0])
        Ptheta[i] = c_theta @ x
        Pq[i] = c_q @ x
    return Ptheta, Pq


def actuator_frf(omega):
    jw = 1j * np.asarray(omega, dtype=float)
    return 1.0 / (ACTUATOR_TAU * jw + 1.0)


def delay_frf(omega):
    return np.exp(-1j * np.asarray(omega, dtype=float) * DELAY_S)


def loop_gain(plant, omega, Kp, Ki, Kq):
    """L(jw) broken at the elevator command, per the README:
    L = e^{-jw*0.04} * Gact(jw) * [ (Kp + Ki/(jw)) * Ptheta(jw) + Kq * Pq(jw) ]
    """
    omega = np.asarray(omega, dtype=float)
    Ptheta, Pq = plant_frf(plant, omega)
    Gact = actuator_frf(omega)
    Gdelay = delay_frf(omega)
    jw = 1j * omega
    with np.errstate(divide="ignore", invalid="ignore"):
        ctrl_theta = Kp + Ki / jw
    # w=0 would be a problem (division by zero); the grid starts at 0.001 so it's fine,
    # but guard anyway.
    bad = ~np.isfinite(ctrl_theta)
    if np.any(bad):
        ctrl_theta[bad] = Kp + Ki / (1j * 1e-12)
    L = Gdelay * Gact * (ctrl_theta * Ptheta + Kq * Pq)
    return L


def grader_omega_grid():
    return np.logspace(np.log10(0.001), np.log10(1000.0), 200001)


# ---------------------------------------------------------------------------
# Nonlinear time-domain simulation (mirrors the grader's algorithm exactly)
# ---------------------------------------------------------------------------

def rk4_step(f, x, dt):
    k1 = f(x)
    k2 = f(x + 0.5 * dt * k1)
    k3 = f(x + 0.5 * dt * k2)
    k4 = f(x + dt * k3)
    return x + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)


def simulate(plant, Kp, Ki, Kq, b, params=None, T=SIM_T, dt=DT, theta_cmd=STEP_RAD):
    """Run the exact nonlinear closed-loop simulation described in the README.

    Returns a dict of time histories and summary metrics.
    """
    if params is None:
        params = load_params()

    n = int(round(T / dt))
    theta_trim = plant["_theta_trim"]
    delta_trim = plant["_delta_e_trim"]
    throttle = plant["_delta_t_trim"]
    x0 = plant["_x0"].copy()

    x = np.empty((n + 1, 4), dtype=float)
    delta = np.empty(n + 1, dtype=float)
    theta_hist = np.empty(n + 1, dtype=float)     # perturbation theta, for the delay buffer
    q_hist = np.empty(n + 1, dtype=float)
    delta_cmd_abs_hist = np.empty(n + 1, dtype=float)
    integ = np.empty(n + 1, dtype=float)

    x[0] = x0
    delta[0] = delta_trim
    integ[0] = 0.0

    diverged = False

    for k in range(n + 1):
        theta_pert_k = x[k, 3] - theta_trim
        q_k = x[k, 2]
        theta_hist[k] = theta_pert_k
        q_hist[k] = q_k

        j = k - DELAY_STEPS
        theta_m = theta_hist[j] if j >= 0 else 0.0
        q_m = q_hist[j] if j >= 0 else 0.0

        delta_e_cmd_pert = Kp * (b * theta_cmd - theta_m) + Ki * integ[k] - Kq * q_m
        delta_cmd_abs = delta_trim + delta_e_cmd_pert
        delta_cmd_abs_hist[k] = delta_cmd_abs

        # divergence check
        Va_k = float(np.hypot(x[k, 0], x[k, 1]))
        if abs(theta_pert_k) > 1.5 or not (5.0 <= Va_k <= 60.0):
            diverged = True
            # truncate arrays to what has been filled and stop
            x = x[: k + 1]
            delta = delta[: k + 1]
            theta_hist = theta_hist[: k + 1]
            q_hist = q_hist[: k + 1]
            delta_cmd_abs_hist = delta_cmd_abs_hist[: k + 1]
            integ = integ[: k + 1]
            break

        if k == n:
            break  # no further state update needed past the last sample

        delta_cmd_sat = np.clip(delta_cmd_abs, -POS_LIMIT, POS_LIMIT)
        rate_raw = (delta_cmd_sat - delta[k]) / ACTUATOR_TAU
        rate_sat = np.clip(rate_raw, -RATE_LIMIT, RATE_LIMIT)
        delta_next = np.clip(delta[k] + dt * rate_sat, -POS_LIMIT, POS_LIMIT)

        f = lambda xx, dk=delta[k]: am.derivatives(params, xx, [dk, throttle])
        x_next = rk4_step(f, x[k], dt)

        integ_next = integ[k] + dt * (theta_cmd - theta_m)

        delta[k + 1] = delta_next
        x[k + 1] = x_next
        integ[k + 1] = integ_next

    t = np.arange(x.shape[0]) * dt

    return {
        "t": t,
        "x": x,
        "delta": delta,
        "delta_cmd_abs": delta_cmd_abs_hist,
        "theta_pert": theta_hist,
        "q": q_hist,
        "integ": integ,
        "diverged": diverged,
        "theta_trim": theta_trim,
        "delta_trim": delta_trim,
    }


def compute_metrics(sim, theta_cmd=STEP_RAD):
    t = sim["t"]
    theta_pert_deg = sim["theta_pert"] * R2D
    step_deg = theta_cmd * R2D

    diverged = sim["diverged"]

    peak = float(np.max(theta_pert_deg)) if theta_pert_deg.size else 0.0
    overshoot_pct = max(0.0, (peak - step_deg) / step_deg * 100.0)

    err = np.abs(theta_pert_deg - step_deg)
    band = 0.02 * step_deg  # 2% of the step, in degrees (=0.1 deg)
    outside = np.where(err > band)[0]
    if outside.size == 0:
        settling_time_s = 0.0
    else:
        last_idx = outside[-1]
        settling_time_s = float(t[last_idx])
        # linear interpolation to the actual crossing between last_idx and last_idx+1,
        # if that next sample exists and is within the sim horizon
        if last_idx + 1 < t.size:
            e0, e1 = err[last_idx], err[last_idx + 1]
            if e1 < e0 and e0 != e1:
                frac = (e0 - band) / (e0 - e1)
                frac = min(max(frac, 0.0), 1.0)
                settling_time_s = float(t[last_idx] + frac * (t[last_idx + 1] - t[last_idx]))

    max_elevator_deg = float(np.max(np.abs(sim["delta_cmd_abs"]))) * R2D

    return {
        "diverged": diverged,
        "overshoot_pct": overshoot_pct,
        "settling_time_s": settling_time_s,
        "max_elevator_deg": max_elevator_deg,
        "peak_theta_deg": peak,
        "final_t": float(t[-1]) if t.size else 0.0,
    }
