"""Nonlinear time-domain simulation of the pitch attitude hold loop, matching the grader's recipe:
RK4 fixed 1 ms step for the plant, forward-Euler actuator with rate+position saturation, an exact
40-step measurement delay, and a forward-Euler controller integrator. No anti-windup.
"""
import math
import json
import pathlib
from collections import deque

import model_fast as mf

HERE = pathlib.Path(__file__).parent
ENV = HERE.parent / "environment"

DT = 0.001
DELAY_STEPS = 40
TAU_ACT = 0.05
RATE_LIM = math.radians(60.0)
POS_LIM = math.radians(25.0)
T_END = 20.0
N_STEPS = round(T_END / DT)  # 20000


def load_trim(speed):
    d = json.loads((ENV / f"plant_{speed}.json").read_text(encoding="utf-8"))
    tr = d["trim"]
    return dict(state=tuple(tr["state"]), delta_e=tr["delta_e_rad"], delta_t=tr["delta_t"],
                theta=tr["theta_rad"])


def clip(x, lo, hi):
    return lo if x < lo else (hi if x > hi else x)


def simulate(speed, Kp, Ki, Kq, b, theta_cmd_deg=5.0, params=None, n_steps=N_STEPS, record=True):
    """Run the full nonlinear closed-loop simulation at the given trim airspeed.

    Returns a dict of time histories (lists) and summary stats.
    """
    p = params if params is not None else mf.load_params()
    trim = load_trim(speed)
    u, w, q, theta = trim["state"]
    theta_trim = trim["theta"]
    delta_e_trim = trim["delta_e"]
    delta_t_trim = trim["delta_t"]
    theta_cmd = math.radians(theta_cmd_deg)

    delta_act = delta_e_trim  # actuator starts settled at trim
    integ = 0.0
    hist_theta = deque([0.0] * DELAY_STEPS, maxlen=DELAY_STEPS)
    hist_q = deque([0.0] * DELAY_STEPS, maxlen=DELAY_STEPS)

    t_arr = [0.0] * (n_steps + 1) if record else None
    theta_arr = [0.0] * (n_steps + 1) if record else None
    elev_cmd_arr = [0.0] * (n_steps + 1) if record else None  # raw (pre-saturation) absolute command, deg
    elev_act_arr = [0.0] * (n_steps + 1) if record else None
    Va_arr = [0.0] * (n_steps + 1) if record else None

    max_abs_cmd_deg = 0.0
    max_theta = -1e9
    diverged = False
    diverge_reason = None

    for k in range(n_steps + 1):
        theta_pert_true = theta - theta_trim
        Va = math.hypot(u, w)

        if record:
            t_arr[k] = k * DT
            theta_arr[k] = theta_pert_true
            Va_arr[k] = Va

        max_theta = max(max_theta, theta_pert_true)

        if abs(theta_pert_true) > 1.5 or not (5.0 <= Va <= 60.0):
            diverged = True
            diverge_reason = f"theta_pert={theta_pert_true:.3f} rad, Va={Va:.2f} m/s at t={k*DT:.3f}s"
            break  # design already fails R1; stop early to save time (esp. during search)

        if k == n_steps:
            if record:
                elev_cmd_arr[k] = elev_cmd_arr[k - 1] if k > 0 else math.degrees(delta_act)
                elev_act_arr[k] = math.degrees(delta_act)
            break  # no further actuation/integration needed past the last sample

        # measurements (delayed by exactly 40 steps; pre-t0 samples are zero)
        theta_m = hist_theta[0]
        q_m = hist_q[0]
        hist_theta.append(theta_pert_true)
        hist_q.append(q)

        # controller (pre-update integrator value used at this step)
        raw_pert = Kp * (b * theta_cmd - theta_m) + Ki * integ - Kq * q_m
        delta_cmd_abs = delta_e_trim + raw_pert
        max_abs_cmd_deg = max(max_abs_cmd_deg, abs(math.degrees(delta_cmd_abs)))
        if record:
            elev_cmd_arr[k] = math.degrees(delta_cmd_abs)
            elev_act_arr[k] = math.degrees(delta_act)

        # forward-Euler integrator update (for use at step k+1)
        integ += DT * (theta_cmd - theta_m)

        # actuator: rate+position limited first order lag, forward Euler
        target = clip(delta_cmd_abs, -POS_LIM, POS_LIM)
        rate = clip((target - delta_act) / TAU_ACT, -RATE_LIM, RATE_LIM)
        delta_act = delta_act + DT * rate
        delta_act = clip(delta_act, -POS_LIM, POS_LIM)

        # plant: RK4 with the surface deflection (and throttle) held constant over the step
        u, w, q, theta = mf.rk4_step(p, (u, w, q, theta), delta_act, delta_t_trim, DT)

    overshoot_pct = max(0.0, (max_theta - theta_cmd)) / theta_cmd * 100.0

    # settling time: last time |theta_pert - theta_cmd| > 0.02*step  (2% band)
    band = 0.02 * theta_cmd
    settling_time = 0.0
    if record:
        for k in range(n_steps, -1, -1):
            if abs(theta_arr[k] - theta_cmd) > band:
                settling_time = k * DT
                break
        else:
            settling_time = 0.0
    else:
        settling_time = None

    return dict(
        diverged=diverged, diverge_reason=diverge_reason,
        overshoot_pct=overshoot_pct, max_elevator_deg=max_abs_cmd_deg,
        settling_time_s=settling_time,
        t=t_arr, theta=theta_arr, elev_cmd=elev_cmd_arr, elev_act=elev_act_arr, Va=Va_arr,
        max_theta_deg=math.degrees(max_theta), theta_cmd_deg=theta_cmd_deg,
    )


if __name__ == "__main__":
    import time
    t0 = time.time()
    res = simulate(20, Kp=1.0, Ki=0.3, Kq=0.3, b=0.6)
    print("elapsed", time.time() - t0)
    print({k: v for k, v in res.items() if k not in ("t", "theta", "elev_cmd", "elev_act", "Va")})
