"""Fast pure-python nonlinear simulation of the aircraft + actuator + delay + PID(b) controller,
replicating the grader's algorithm (README "How the grader evaluates"):
  - RK4, fixed 1 ms step, elevator held constant over the step
  - actuator: dδ/dt = sat_rate((sat_position(δ_cmd) - δ)/0.05), forward Euler, position-limited
  - sensor delay: exactly 40 steps (40 ms), zero before t=0
  - controller integrator: forward Euler
Also provides a matching LINEAR simulator (same discretization, A x instead of the nonlinear
derivatives) used only as a fast proxy during design/search -- final grading-relevant numbers
always come from the nonlinear simulator below.
"""
import json
import math
import pathlib

HERE = pathlib.Path(__file__).parent
ENV = HERE.parent / "environment"

DEG = math.pi / 180.0
DT = 0.001
DELAY_STEPS = 40
ACT_TAU = 0.05
RATE_LIM = 60.0 * DEG      # rad/s
POS_LIM = 25.0 * DEG       # rad
T_END = 20.0
N_STEPS = round(T_END / DT)  # 20000


def load_params(path=ENV / "aircraft_aerosonde.json"):
    p = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    p["AR"] = p["b"] ** 2 / p["S_wing"]
    kv = (1.0 / p["KV_rpm_per_volt"]) * 60.0 / (2.0 * math.pi)
    p["KV"] = kv
    p["KQ"] = kv
    p["V_max"] = 3.7 * p["ncells"]
    return p


def load_plant(spd):
    d = json.loads((ENV / f"plant_{spd:g}.json").read_text(encoding="utf-8"))
    return d


def thrust_scalar(p, Va, delta_t):
    rho, D = p["rho"], p["D_prop"]
    v_in = p["V_max"] * delta_t
    a = p["C_Q0"] * rho * D ** 5 / (2.0 * math.pi) ** 2
    b = p["C_Q1"] * rho * D ** 4 / (2.0 * math.pi) * Va + p["KQ"] * p["KV"] / p["R_motor"]
    c = p["C_Q2"] * rho * D ** 3 * Va ** 2 - p["KQ"] / p["R_motor"] * v_in + p["KQ"] * p["i0"]
    omega = (-b + math.sqrt(b * b - 4.0 * a * c)) / (2.0 * a)
    J = 2.0 * math.pi * Va / (omega * D)
    C_T = p["C_T2"] * J * J + p["C_T1"] * J + p["C_T0"]
    return rho * (omega / (2.0 * math.pi)) ** 2 * D ** 4 * C_T


def lift_drag_scalar(p, alpha):
    M, a0 = p["M"], p["alpha0"]
    e1 = math.exp(-M * (alpha - a0))
    e2 = math.exp(M * (alpha + a0))
    sigma = (1.0 + e1 + e2) / ((1.0 + e1) * (1.0 + e2))
    linear = p["C_L_0"] + p["C_L_alpha"] * alpha
    sgn = math.copysign(1.0, alpha)
    C_L = (1.0 - sigma) * linear + sigma * 2.0 * sgn * math.sin(alpha) ** 2 * math.cos(alpha)
    C_D = p["C_D_p"] + linear ** 2 / (math.pi * p["e"] * p["AR"])
    return C_L, C_D


def derivatives_scalar(p, x, inp):
    u, w, q, theta = x
    delta_e, delta_t = inp
    m, g = p["mass"], p["gravity"]
    Va = math.hypot(u, w)
    alpha = math.atan2(w, u)
    qbar_S = 0.5 * p["rho"] * Va * Va * p["S_wing"]
    qhat = p["c"] * q / (2.0 * Va)
    C_L, C_D = lift_drag_scalar(p, alpha)
    lift = qbar_S * (C_L + p["C_L_q"] * qhat + p["C_L_delta_e"] * delta_e)
    drag = qbar_S * (C_D + p["C_D_q"] * qhat + p["C_D_delta_e"] * delta_e)
    fx = -drag * math.cos(alpha) + lift * math.sin(alpha) + thrust_scalar(p, Va, delta_t) - m * g * math.sin(theta)
    fz = -drag * math.sin(alpha) - lift * math.cos(alpha) + m * g * math.cos(theta)
    my = qbar_S * p["c"] * (p["C_m_0"] + p["C_m_alpha"] * alpha + p["C_m_q"] * qhat + p["C_m_delta_e"] * delta_e)
    return (-q * w + fx / m, q * u + fz / m, my / p["Jy"], q)


def rk4_step(p, x, inp, dt):
    def add(a, b, h):
        return (a[0] + h * b[0], a[1] + h * b[1], a[2] + h * b[2], a[3] + h * b[3])

    k1 = derivatives_scalar(p, x, inp)
    k2 = derivatives_scalar(p, add(x, k1, dt / 2), inp)
    k3 = derivatives_scalar(p, add(x, k2, dt / 2), inp)
    k4 = derivatives_scalar(p, add(x, k3, dt), inp)
    return (
        x[0] + dt / 6.0 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0]),
        x[1] + dt / 6.0 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1]),
        x[2] + dt / 6.0 * (k1[2] + 2 * k2[2] + 2 * k3[2] + k4[2]),
        x[3] + dt / 6.0 * (k1[3] + 2 * k2[3] + 2 * k3[3] + k4[3]),
    )


def clip(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def run_nonlinear(plant, gains, theta_cmd_deg=5.0, t_end=T_END, dt=DT, delay_steps=DELAY_STEPS,
                   params=None):
    """Simulate the nonlinear closed loop for one plant/airspeed.

    gains: dict with Kp, Ki, Kq, b
    Returns dict with time series (t, theta_pert_deg, q_pert_deg, elevator_cmd_deg, elevator_act_deg)
    and summary values (overshoot_pct, settling_time_s, max_elevator_deg, diverged).
    """
    p = params if params is not None else load_params()
    trim = plant["trim"]
    theta_trim = trim["theta_rad"]
    delta_e_trim = trim["delta_e_rad"]
    delta_t_trim = trim["delta_t"]
    x0 = tuple(trim["state"])

    Kp, Ki, Kq, b = gains["K_p"], gains["K_i"], gains["K_q"], gains["b"]
    theta_cmd = math.radians(theta_cmd_deg)

    N = round(t_end / dt)
    hist_theta = [0.0] * (N + 1)
    hist_q = [0.0] * (N + 1)
    elev_cmd = [0.0] * (N + 1)

    x = x0
    delta_act = delta_e_trim
    I = 0.0
    diverged = False
    airspeed_ok = True

    for k in range(N + 1):
        hist_theta[k] = x[3] - theta_trim
        hist_q[k] = x[2]

        if k < delay_steps:
            theta_m = 0.0
            q_m = 0.0
        else:
            theta_m = hist_theta[k - delay_steps]
            q_m = hist_q[k - delay_steps]

        delta_cmd_pert = Kp * (b * theta_cmd - theta_m) + Ki * I - Kq * q_m
        delta_cmd_abs = delta_e_trim + delta_cmd_pert
        elev_cmd[k] = delta_cmd_abs

        target = clip(delta_cmd_abs, -POS_LIM, POS_LIM)
        rate = clip((target - delta_act) / ACT_TAU, -RATE_LIM, RATE_LIM)
        delta_act_next = clip(delta_act + dt * rate, -POS_LIM, POS_LIM)

        I_next = I + dt * (theta_cmd - theta_m)

        # divergence check
        Va = math.hypot(x[0], x[1])
        if abs(x[3] - theta_trim) > 1.5 or not (5.0 <= Va <= 60.0):
            diverged = True
            # truncate histories to what we have and stop
            hist_theta = hist_theta[:k + 1]
            hist_q = hist_q[:k + 1]
            elev_cmd = elev_cmd[:k + 1]
            break

        if k < N:
            x = rk4_step(p, x, (delta_act, delta_t_trim), dt)
        delta_act = delta_act_next
        I = I_next

    n_have = len(hist_theta)
    t = [i * dt for i in range(n_have)]
    theta_pert_deg = [v / DEG for v in hist_theta]
    elev_cmd_deg = [v / DEG for v in elev_cmd]

    peak_theta = max(theta_pert_deg) if theta_pert_deg else 0.0
    overshoot_pct = (peak_theta - theta_cmd_deg) / theta_cmd_deg * 100.0

    band = 0.1  # deg, 2% of 5 deg step
    settling_time = 0.0
    for i in range(n_have - 1, -1, -1):
        if abs(theta_pert_deg[i] - theta_cmd_deg) > band:
            settling_time = t[i]
            break

    max_elev_deg = max(abs(v) for v in elev_cmd_deg) if elev_cmd_deg else 0.0

    return {
        "t": t,
        "theta_pert_deg": theta_pert_deg,
        "elev_cmd_deg": elev_cmd_deg,
        "diverged": diverged,
        "overshoot_pct": overshoot_pct,
        "settling_time_s": settling_time,
        "max_elevator_deg": max_elev_deg,
        "n_steps_run": n_have - 1,
    }


def run_linear(plant, gains, theta_cmd_deg=5.0, t_end=T_END, dt=DT, delay_steps=DELAY_STEPS):
    """Same discretization as run_nonlinear, but with the LINEAR plant dx/dt = A x (perturbation
    states) instead of the nonlinear derivatives, and no actuator position/rate saturation. Used
    only as an independent time-domain stability check of the linear model (R1), not for grading
    numbers.
    """
    import numpy as np
    A = np.array(plant["A"])
    B = np.array(plant["B"]).ravel()
    Kp, Ki, Kq, b = gains["K_p"], gains["K_i"], gains["K_q"], gains["b"]
    theta_cmd = math.radians(theta_cmd_deg)

    N = round(t_end / dt)
    x = np.zeros(4)
    delta_pert = 0.0
    I = 0.0
    hist_theta = [0.0] * (N + 1)
    hist_q = [0.0] * (N + 1)

    def deriv(xx, d):
        return A @ xx + B * d

    for k in range(N + 1):
        hist_theta[k] = x[3]
        hist_q[k] = x[2]
        if k < delay_steps:
            theta_m = 0.0
            q_m = 0.0
        else:
            theta_m = hist_theta[k - delay_steps]
            q_m = hist_q[k - delay_steps]
        delta_cmd_pert = Kp * (b * theta_cmd - theta_m) + Ki * I - Kq * q_m
        # linear actuator, no saturation (design/stability check only)
        rate = (delta_cmd_pert - delta_pert) / ACT_TAU
        delta_pert_next = delta_pert + dt * rate
        I_next = I + dt * (theta_cmd - theta_m)
        if k < N:
            k1 = deriv(x, delta_pert)
            k2 = deriv(x + dt / 2 * k1, delta_pert)
            k3 = deriv(x + dt / 2 * k2, delta_pert)
            k4 = deriv(x + dt * k3, delta_pert)
            x = x + dt / 6.0 * (k1 + 2 * k2 + 2 * k3 + k4)
        delta_pert = delta_pert_next
        I = I_next

    theta_deg = [v / DEG for v in hist_theta]
    return {"t": [i * dt for i in range(N + 1)], "theta_pert_deg": theta_deg,
            "final_theta_deg": theta_deg[-1], "max_abs_theta_deg": max(abs(v) for v in theta_deg)}


if __name__ == "__main__":
    import time
    p = load_params()
    plant = load_plant(25)
    gains = {"K_p": -3.0, "K_i": -1.0, "K_q": 1.0, "b": 0.5}
    t0 = time.perf_counter()
    res = run_nonlinear(plant, gains, params=p)
    t1 = time.perf_counter()
    print("elapsed", t1 - t0, "s; diverged=", res["diverged"])
    print("overshoot_pct", res["overshoot_pct"], "settling_time_s", res["settling_time_s"],
          "max_elevator_deg", res["max_elevator_deg"])
