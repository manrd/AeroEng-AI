"""Exact nonlinear time-domain simulation of the pitch attitude hold loop, per README's grader spec:
RK4 (fixed 1 ms step, elevator held constant over the step), actuator with rate+position limits
integrated by forward Euler, a 40-step measurement delay, and a forward-Euler controller integrator.
"""
import pathlib
import sys
import json
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV = ROOT / "environment"
sys.path.insert(0, str(ENV))
import aircraft_model as am  # noqa: E402

H = 0.001            # s, fixed RK4 / Euler step
N_STEPS = 20000       # 20 s / 1 ms
DELAY_STEPS = 40      # exactly 40 steps = 40 ms
TAU_ACT = 0.05
RATE_LIMIT = np.radians(60.0)
POS_LIMIT = np.radians(25.0)
THETA_CMD = np.radians(5.0)
DIVERGE_THETA = 1.5   # rad from trim
V_MIN, V_MAX = 5.0, 60.0


def rk4_step(p, x, inp, h):
    k1 = am.derivatives(p, x, inp)
    k2 = am.derivatives(p, x + 0.5 * h * k1, inp)
    k3 = am.derivatives(p, x + 0.5 * h * k2, inp)
    k4 = am.derivatives(p, x + h * k3, inp)
    return x + (h / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)


def simulate(Kp, Ki, Kq, b, va, p=None, n_steps=N_STEPS, record_full=False):
    """Simulate the step response at airspeed va (20, 25 or 32). Returns a dict of results."""
    if p is None:
        p = am.load_params()
    plant = json.load(open(ENV / f"plant_{va}.json"))
    trim = plant["trim"]
    x = np.array(trim["state"], dtype=float)          # u, w, q, theta
    theta_trim = trim["theta_rad"]
    delta_e_trim = trim["delta_e_rad"]
    delta_t = trim["delta_t"]

    delta_e = delta_e_trim   # actuator state (absolute)
    z = 0.0                   # controller integrator

    theta_hist = np.empty(n_steps + 1)
    q_hist = np.empty(n_steps + 1)
    de_cmd_hist = np.empty(n_steps)     # unsaturated absolute commanded elevator, per step
    de_act_hist = np.empty(n_steps + 1)  # actual (actuated) absolute elevator
    de_act_hist[0] = delta_e

    diverged = False
    diverge_time = None

    for k in range(n_steps):
        theta_pert = x[3] - theta_trim
        q_now = x[2]
        theta_hist[k] = theta_pert
        q_hist[k] = q_now

        if k >= DELAY_STEPS:
            theta_m = theta_hist[k - DELAY_STEPS]
            q_m = q_hist[k - DELAY_STEPS]
        else:
            theta_m = 0.0
            q_m = 0.0

        de_ctrl = Kp * (b * THETA_CMD - theta_m) + Ki * z - Kq * q_m
        de_cmd_abs = delta_e_trim + de_ctrl
        de_cmd_hist[k] = de_cmd_abs

        de_cmd_sat = np.clip(de_cmd_abs, -POS_LIMIT, POS_LIMIT)
        rate = (de_cmd_sat - delta_e) / TAU_ACT
        rate = np.clip(rate, -RATE_LIMIT, RATE_LIMIT)
        delta_e_next = delta_e + H * rate
        delta_e_next = np.clip(delta_e_next, -POS_LIMIT, POS_LIMIT)

        x_next = rk4_step(p, x, [delta_e, delta_t], H)

        z_next = z + H * (THETA_CMD - theta_m)

        x = x_next
        delta_e = delta_e_next
        z = z_next
        de_act_hist[k + 1] = delta_e

        Va = np.hypot(x[0], x[1])
        if abs(x[3] - theta_trim) > DIVERGE_THETA or not (V_MIN <= Va <= V_MAX):
            diverged = True
            diverge_time = (k + 1) * H
            n_used = k + 1
            theta_hist[k + 1] = x[3] - theta_trim
            q_hist[k + 1] = x[2]
            theta_hist = theta_hist[: n_used + 1]
            q_hist = q_hist[: n_used + 1]
            de_cmd_hist = de_cmd_hist[: n_used]
            de_act_hist = de_act_hist[: n_used + 1]
            break

    else:
        theta_hist[n_steps] = x[3] - theta_trim
        q_hist[n_steps] = x[2]

    t = np.arange(len(theta_hist)) * H

    out = dict(
        t=t, theta_pert=theta_hist, q=q_hist, de_cmd_abs=de_cmd_hist, de_act_abs=de_act_hist,
        diverged=diverged, diverge_time=diverge_time, theta_trim=theta_trim,
        delta_e_trim=delta_e_trim,
    )
    if not record_full:
        for key in ("de_cmd_abs", "de_act_abs"):
            pass  # keep everything; arrays are small (20001 floats) so no need to drop
    return out


def metrics(out):
    """Compute overshoot_pct, settling_time_s, max_elevator_deg from a simulate() result."""
    theta_deg = np.degrees(out["theta_pert"])
    step_deg = 5.0
    peak = np.max(theta_deg)
    overshoot_pct = (peak - step_deg) / step_deg * 100.0

    band = 0.1  # deg, = 2% of the 5 deg step
    err = np.abs(theta_deg - step_deg)
    t = out["t"]
    over = err > band
    if np.any(over):
        idx_last = np.where(over)[0][-1]
        settling_time = t[idx_last]
        if idx_last == len(t) - 1:
            settling_time = t[-1]  # never actually settles within the run
    else:
        settling_time = 0.0

    max_elev_deg = np.degrees(np.max(np.abs(out["de_cmd_abs"]))) if len(out["de_cmd_abs"]) else np.nan

    return dict(overshoot_pct=overshoot_pct, settling_time_s=settling_time, max_elevator_deg=max_elev_deg,
                diverged=out["diverged"])


if __name__ == "__main__":
    import time
    p = am.load_params()
    t0 = time.time()
    for va in (20, 25, 32):
        out = simulate(-2.0, -1.0, -0.5, 0.3, va, p=p)
        m = metrics(out)
        print(va, m)
    print("time for 3 sims:", time.time() - t0)
