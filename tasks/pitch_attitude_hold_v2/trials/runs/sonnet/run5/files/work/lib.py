"""Core toolkit: plant loading, exact frequency response of the broken loop, margins,
and a faithful replica of the grader's nonlinear time-domain simulation.
"""
import json
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parent
ENV = ROOT / "environment"

sys.path.insert(0, str(ENV))
sys.path.insert(0, str(HERE))
import aircraft_model as am  # noqa: E402
from margins_fast import analyze_margins  # noqa: E402

DEG = np.pi / 180.0
TAU_ACT = 0.05       # actuator time constant, s
RATE_LIMIT = 60 * DEG  # rad/s
POS_LIMIT = 25 * DEG   # rad
DELAY_S = 0.040
DT = 0.001
DELAY_STEPS = round(DELAY_S / DT)
assert DELAY_STEPS == 40

SPEEDS = (20, 25, 32)

_PARAMS = am.load_params()


class Plant:
    def __init__(self, speed):
        d = json.loads((ENV / f"plant_{speed}.json").read_text(encoding="utf-8"))
        self.speed = speed
        self.A = np.array(d["A"], dtype=float)
        self.B = np.array(d["B"], dtype=float)[:, 0]
        self.trim = d["trim"]
        self.x0 = np.array(self.trim["state"], dtype=float)
        self.delta_e0 = self.trim["delta_e_rad"]
        self.delta_t0 = self.trim["delta_t"]
        self.theta0 = self.trim["theta_rad"]
        # eigen-decomposition for fast frequency response: P(s) = sum_i r_i/(s-lam_i)
        lam, V = np.linalg.eig(self.A)
        Vinv = np.linalg.inv(V)
        Ctheta = np.array([0, 0, 0, 1.0])
        Cq = np.array([0, 0, 1.0, 0])
        self.lam = lam
        self.r_theta = (Ctheta @ V) * (Vinv @ self.B)
        self.r_q = (Cq @ V) * (Vinv @ self.B)
        # sanity: residues should combine to real transfer function (imaginary parts cancel in conjugate pairs)

    def P_theta(self, s):
        return np.sum(self.r_theta[None, :] / (s[:, None] - self.lam[None, :]), axis=1)

    def P_q(self, s):
        return np.sum(self.r_q[None, :] / (s[:, None] - self.lam[None, :]), axis=1)


PLANTS = {spd: Plant(spd) for spd in SPEEDS}


def loop_response(plant, w, Kp, Ki, Kq):
    """L(jw) for the loop broken at the elevator command, actuator+delay included.

    Derivation (see NOTES.md): with controller
        de_cmd = Kp(b th_cmd - th_m) + Ki INT(th_cmd-th_m) - Kq q_m
    and th_m, q_m the delayed measurements, breaking the loop at de_cmd and closing
    through actuator -> plant -> delay -> controller feedback terms gives a
    characteristic equation 1 + L(s) = 0 with
        L(s) = Act(s) * exp(-s*tau) * [ (Kp + Ki/s) P_theta(s) + Kq P_q(s) ]
    independent of b (b only shapes the command feedforward, not the loop).
    """
    s = 1j * w
    Act = 1.0 / (1.0 + TAU_ACT * s)
    Delay = np.exp(-DELAY_S * s)
    Pth = plant.P_theta(s)
    Pq = plant.P_q(s)
    comp = (Kp + Ki / s) * Pth + Kq * Pq
    return Act * Delay * comp


def freq_grid(n=200001, wmin=0.001, wmax=1000.0):
    return np.logspace(np.log10(wmin), np.log10(wmax), n)


# analyze_margins is imported from margins_fast (validated separately against
# control.stability_margins on reference cases -- see validate_margins.py output in NOTES).


# ---------------- nonlinear time-domain simulation (replicates the grader's algorithm) --------------

def rk4_step(f, x, u, dt):
    k1 = f(x, u)
    k2 = f(x + 0.5 * dt * k1, u)
    k3 = f(x + 0.5 * dt * k2, u)
    k4 = f(x + dt * k3, u)
    return x + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)


def simulate(speed, Kp, Ki, Kq, b, T=20.0, theta_cmd_deg=5.0, dt=DT):
    plant = PLANTS[speed]
    p = _PARAMS
    n = round(T / dt)
    x = plant.x0.copy()
    delta = plant.delta_e0  # actuator state (absolute elevator, rad), starts at trim
    theta_cmd = np.radians(theta_cmd_deg)
    integ = 0.0

    theta_hist = np.zeros(n + 1)
    q_hist = np.zeros(n + 1)
    delta_hist = np.zeros(n + 1)
    delta_cmd_hist = np.zeros(n + 1)
    t_hist = np.arange(n + 1) * dt
    Va_hist = np.zeros(n + 1)

    # perturbation history buffers for the delay (theta_pert, q) ; index k -> value at time k*dt
    theta_pert_buf = np.zeros(n + 1)
    q_buf = np.zeros(n + 1)
    theta_pert_buf[0] = x[3] - plant.theta0
    q_buf[0] = x[2]

    theta_hist[0] = x[3]
    q_hist[0] = x[2]
    delta_hist[0] = delta
    delta_cmd_hist[0] = delta
    Va_hist[0] = np.hypot(x[0], x[1])

    diverged = False
    max_abs_delta_cmd = abs(delta)

    def f(xx, dd):
        return am.derivatives(p, xx, [dd, plant.delta_t0])

    for k in range(n):
        # delayed measurements available at step k (using history up to k)
        idx_delay = k - DELAY_STEPS
        if idx_delay < 0:
            theta_m = 0.0
            q_m = 0.0
        else:
            theta_m = theta_pert_buf[idx_delay]
            q_m = q_buf[idx_delay]

        error_p = theta_cmd - theta_m
        de_cmd_pert = Kp * (b * theta_cmd - theta_m) + Ki * integ - Kq * q_m
        delta_cmd_abs = plant.delta_e0 + de_cmd_pert
        delta_cmd_hist[k] = delta_cmd_abs
        if abs(delta_cmd_abs) > max_abs_delta_cmd:
            max_abs_delta_cmd = abs(delta_cmd_abs)

        # actuator: forward Euler on dδ/dt = sat_rate((sat_position(δcmd)-δ)/tau)
        delta_cmd_sat = np.clip(delta_cmd_abs, -POS_LIMIT, POS_LIMIT)
        rate = (delta_cmd_sat - delta) / TAU_ACT
        rate = np.clip(rate, -RATE_LIMIT, RATE_LIMIT)
        delta_next = delta + dt * rate
        delta_next = np.clip(delta_next, -POS_LIMIT, POS_LIMIT)

        # plant RK4 step with delta held constant at 'delta' (this step's actuator position)
        x_next = rk4_step(f, x, delta, dt)

        # controller integrator forward Euler
        integ = integ + dt * error_p

        # commit
        x = x_next
        delta = delta_next

        theta_hist[k + 1] = x[3]
        q_hist[k + 1] = x[2]
        delta_hist[k + 1] = delta
        Va_hist[k + 1] = np.hypot(x[0], x[1])
        theta_pert_buf[k + 1] = x[3] - plant.theta0
        q_buf[k + 1] = x[2]

        if abs(x[3] - plant.theta0) > 1.5 or not (5.0 <= Va_hist[k + 1] <= 60.0):
            diverged = True
            # continue simulating regardless is fine, but flag it
        if not np.all(np.isfinite(x)):
            diverged = True
            break

    delta_cmd_hist[n] = delta_cmd_hist[n - 1]

    return {
        "t": t_hist,
        "theta": theta_hist,
        "q": q_hist,
        "delta": delta_hist,
        "delta_cmd": delta_cmd_hist,
        "Va": Va_hist,
        "diverged": diverged,
        "max_abs_delta_cmd_rad": max_abs_delta_cmd,
        "theta0": plant.theta0,
    }


def metrics_from_sim(sim, theta_cmd_deg=5.0):
    theta_pert_deg = np.degrees(sim["theta"] - sim["theta0"])
    cmd = theta_cmd_deg
    overshoot_pct = max(0.0, (np.max(theta_pert_deg) - cmd) / cmd * 100.0)
    band = 0.02 * cmd  # 0.1 deg
    err = np.abs(theta_pert_deg - cmd)
    outside = np.where(err > band)[0]
    if len(outside) == 0:
        settling_time_s = 0.0
    else:
        last_bad = outside[-1]
        settling_time_s = sim["t"][last_bad]
        if last_bad == len(sim["t"]) - 1:
            settling_time_s = sim["t"][-1]  # never settles within window
    max_elevator_deg = np.degrees(sim["max_abs_delta_cmd_rad"])
    return {
        "overshoot_pct": overshoot_pct,
        "settling_time_s": settling_time_s,
        "max_elevator_deg": max_elevator_deg,
        "diverged": sim["diverged"],
        "theta_pert_deg": theta_pert_deg,
    }
