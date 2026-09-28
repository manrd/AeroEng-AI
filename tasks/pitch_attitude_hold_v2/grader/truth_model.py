"""The grader's truth model for version 2, as the task README defines it.

Frequency domain, per airspeed: the linear model in environment/plant_<V>.json, the loop broken at the elevator
command, with the actuator lag and the exact delay e^(-s tau).
Time domain, per airspeed: the nonlinear longitudinal aircraft (the equations of environment/aircraft_model.py,
reimplemented here with scalar math for speed and checked against it in the tests), started at trim, with the
throttle fixed at trim. Fourth order Runge-Kutta with a 1 ms step and the surface deflection held over each step;
the actuator is a first order lag with rate and position limits (forward Euler); both measurements are delayed by a
whole number of steps; the controller integrator is forward Euler.
"""
import json
import math
import pathlib

import numpy as np

TASK = pathlib.Path(__file__).resolve().parents[1]
SPEC = {
    "speeds_m_s": (20.0, 25.0, 32.0),
    "tau_actuator_s": 0.05,        # elevator servo time constant
    "rate_limit_deg_s": 60.0,      # elevator slew limit
    "position_limit_deg": 25.0,    # absolute elevator deflection limit, both directions
    "delay_s": 0.040,              # sensor and computation delay on theta and q
    "step_deg": 5.0,               # pitch attitude command step, from trim
    "horizon_s": 20.0,             # simulation length
    "dt_s": 0.001,
    "band": 0.02,                  # settling band, fraction of the step
}


def load_plant(V):
    p = json.loads((TASK / "environment" / f"plant_{V:g}.json").read_text(encoding="utf-8"))
    return {k: np.array(p[k], dtype=float) for k in ("A", "B", "C", "D")} | {"trim": p["trim"]}


# ---------------------------------------------------------------- nonlinear aircraft, scalar version

class Aircraft:
    """The longitudinal equations of environment/aircraft_model.py, with scalar math for speed."""

    def __init__(self, path=TASK / "environment" / "aircraft_aerosonde.json"):
        p = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        self.p = p
        self.AR = p["b"] ** 2 / p["S_wing"]
        kv = (1.0 / p["KV_rpm_per_volt"]) * 60.0 / (2.0 * math.pi)
        self.KV = self.KQ = kv
        self.V_max = 3.7 * p["ncells"]

    def thrust(self, Va, delta_t):
        p, rho, D = self.p, self.p["rho"], self.p["D_prop"]
        v_in = self.V_max * delta_t
        a = p["C_Q0"] * rho * D ** 5 / (2.0 * math.pi) ** 2
        b = p["C_Q1"] * rho * D ** 4 / (2.0 * math.pi) * Va + self.KQ * self.KV / p["R_motor"]
        c = p["C_Q2"] * rho * D ** 3 * Va ** 2 - self.KQ / p["R_motor"] * v_in + self.KQ * p["i0"]
        omega = (-b + math.sqrt(b * b - 4.0 * a * c)) / (2.0 * a)
        J = 2.0 * math.pi * Va / (omega * D)
        C_T = p["C_T2"] * J * J + p["C_T1"] * J + p["C_T0"]
        return rho * (omega / (2.0 * math.pi)) ** 2 * D ** 4 * C_T

    def derivatives(self, u, w, q, theta, delta_e, delta_t):
        p = self.p
        m, g = p["mass"], p["gravity"]
        Va = math.hypot(u, w)
        alpha = math.atan2(w, u)
        qbar_S = 0.5 * p["rho"] * Va * Va * p["S_wing"]
        qhat = p["c"] * q / (2.0 * Va)
        M, a0 = p["M"], p["alpha0"]
        e1, e2 = math.exp(-M * (alpha - a0)), math.exp(M * (alpha + a0))
        sigma = (1.0 + e1 + e2) / ((1.0 + e1) * (1.0 + e2))
        linear = p["C_L_0"] + p["C_L_alpha"] * alpha
        sgn = (alpha > 0) - (alpha < 0)
        C_L = (1.0 - sigma) * linear + sigma * 2.0 * sgn * math.sin(alpha) ** 2 * math.cos(alpha)
        C_D = p["C_D_p"] + linear * linear / (math.pi * p["e"] * self.AR)
        lift = qbar_S * (C_L + p["C_L_q"] * qhat + p["C_L_delta_e"] * delta_e)
        drag = qbar_S * (C_D + p["C_D_q"] * qhat + p["C_D_delta_e"] * delta_e)
        ca, sa = math.cos(alpha), math.sin(alpha)
        fx = -drag * ca + lift * sa + self.thrust(Va, delta_t) - m * g * math.sin(theta)
        fz = -drag * sa - lift * ca + m * g * math.cos(theta)
        my = qbar_S * p["c"] * (p["C_m_0"] + p["C_m_alpha"] * alpha + p["C_m_q"] * qhat
                                + p["C_m_delta_e"] * delta_e)
        return (-q * w + fx / m, q * u + fz / m, my / p["Jy"], q)


AIRCRAFT = Aircraft()


def simulate(V, ctrl, spec=SPEC, step_deg=None, horizon_s=None, aircraft=AIRCRAFT):
    """Step response of the closed loop on the nonlinear aircraft at airspeed V. ctrl: K_p, K_i, K_q, b.

    Returns time histories as perturbations from trim (rad, rad/s, s), plus the absolute elevator command.
    """
    trim = load_plant(V)["trim"]
    u, w, q, th = trim["state"]
    th0, de0, dt_throttle = trim["theta_rad"], trim["delta_e_rad"], trim["delta_t"]
    dt = spec["dt_s"]
    n = int(round((horizon_s or spec["horizon_s"]) / dt)) + 1
    nd = int(round(spec["delay_s"] / dt))
    lim = math.radians(spec["position_limit_deg"])
    lo, hi = -lim - de0, lim - de0
    rate = math.radians(spec["rate_limit_deg_s"])
    tau = spec["tau_actuator_s"]
    ref = math.radians(step_deg if step_deg is not None else spec["step_deg"])
    K_p, K_i, K_q, b = ctrl["K_p"], ctrl["K_i"], ctrl["K_q"], ctrl["b"]
    f = aircraft.derivatives

    theta, qs, cmds, surf, speed = (np.zeros(n) for _ in range(5))
    sat_pos, sat_rate = np.zeros(n, bool), np.zeros(n, bool)
    integ, d = 0.0, 0.0
    diverged = False
    for k in range(n):
        theta[k], qs[k], speed[k] = th - th0, q, math.hypot(u, w)
        j = k - nd
        th_m, q_m = (theta[j], qs[j]) if j >= 0 else (0.0, 0.0)
        cmd = K_p * (b * ref - th_m) + K_i * integ - K_q * q_m
        integ += (ref - th_m) * dt
        cmds[k] = cmd
        target = min(max(cmd, lo), hi)
        sat_pos[k] = target != cmd
        rdot = (target - d) / tau
        sat_rate[k] = abs(rdot) > rate
        rdot = min(max(rdot, -rate), rate)
        surf[k] = d
        de = de0 + d
        k1 = f(u, w, q, th, de, dt_throttle)
        k2 = f(u + dt / 2 * k1[0], w + dt / 2 * k1[1], q + dt / 2 * k1[2], th + dt / 2 * k1[3], de, dt_throttle)
        k3 = f(u + dt / 2 * k2[0], w + dt / 2 * k2[1], q + dt / 2 * k2[2], th + dt / 2 * k2[3], de, dt_throttle)
        k4 = f(u + dt * k3[0], w + dt * k3[1], q + dt * k3[2], th + dt * k3[3], de, dt_throttle)
        u += dt / 6 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0])
        w += dt / 6 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1])
        q += dt / 6 * (k1[2] + 2 * k2[2] + 2 * k3[2] + k4[2])
        th += dt / 6 * (k1[3] + 2 * k2[3] + 2 * k3[3] + k4[3])
        d = min(max(d + rdot * dt, lo), hi)
        if not (math.isfinite(th) and abs(th - th0) < 1.5 and 5.0 < math.hypot(u, w) < 60.0):
            diverged = True             # left the region where the model means anything
            theta[k + 1:], cmds[k + 1:] = np.nan, np.nan
            break
    return {"t": np.arange(n) * dt, "theta": theta, "q": qs, "de": surf, "de_cmd": cmds, "airspeed": speed,
            "sat_pos": sat_pos, "sat_rate": sat_rate, "ref": ref, "trim_de": de0, "diverged": diverged}


def step_metrics(sim, spec=SPEC):
    """Overshoot (% of the step), 2% settling time (s), and elevator use, from a step response."""
    th, t, ref = sim["theta"], sim["t"], sim["ref"]
    if sim["diverged"] or not np.all(np.isfinite(th)):
        return {"diverged": True}
    err = np.abs(th - ref)
    outside = np.nonzero(err > spec["band"] * abs(ref))[0]
    if len(outside) == 0:
        settling = 0.0
    elif outside[-1] == len(t) - 1:
        settling = float("inf")
    else:
        settling = float(t[outside[-1] + 1])
    cmd_abs = sim["de_cmd"] + sim["trim_de"]
    return {
        "diverged": bool(np.max(np.abs(th)) > 10 * abs(ref)),
        "overshoot_pct": float(max(0.0, (np.max(th) - ref) / ref * 100.0)),
        "settling_time_s": settling,
        "final_error_pct": float((th[-1] - ref) / ref * 100.0),
        "max_elevator_deg": float(np.degrees(np.max(np.abs(cmd_abs)))),
        "position_limited_s": float(np.sum(sim["sat_pos"]) * spec["dt_s"]),
        "rate_limited_s": float(np.sum(sim["sat_rate"]) * spec["dt_s"]),
        "min_airspeed_m_s": float(np.min(sim["airspeed"])),
    }


# ---------------------------------------------------------------- linear models: margins and poles

def plant_frequency_response(plant, w):
    """G_theta(jw) and G_q(jw), responses of theta and q to the elevator deflection."""
    A, B, C = plant["A"], plant["B"], plant["C"]
    n = A.shape[0]
    M = 1j * np.asarray(w)[:, None, None] * np.eye(n) - A
    X = np.linalg.solve(M, np.broadcast_to(B, (len(w), n, 1)))
    G = (C @ X)[:, :, 0]
    return G[:, 0], G[:, 1]


def loop_response(plant, ctrl, w, spec=SPEC, delay=True):
    """L(jw), broken at the elevator command: L = (K_q G_q + (K_p + K_i/s) G_theta) Act e^(-s tau)."""
    s = 1j * w
    G_th, G_q = plant_frequency_response(plant, w)
    act = 1.0 / (spec["tau_actuator_s"] * s + 1.0)
    L = (ctrl["K_q"] * G_q + (ctrl["K_p"] + ctrl["K_i"] / s) * G_th) * act
    if delay:
        L = L * np.exp(-s * spec["delay_s"])
    return L


def margins(plant, ctrl, spec=SPEC, w=None, delay=True):
    """Gain and phase margins from a dense frequency sweep with the exact delay.

    gm_db: smallest margin against a gain increase (from -180 deg crossings with |L| < 1).
    gm_low_db: smallest margin against a gain decrease (from -180 deg crossings with |L| > 1); inf if none.
    pm_deg: smallest phase margin over all gain crossovers.
    """
    w = np.logspace(-3, 3, 200001) if w is None else w
    L = loop_response(plant, ctrl, w, spec, delay)
    mag = np.abs(L)
    ph = np.unwrap(np.angle(L))
    idx = np.nonzero(np.diff(np.sign(mag - 1.0)))[0]
    pms, wcs = [], []
    for i in idx:
        f = (1.0 - mag[i]) / (mag[i + 1] - mag[i])
        phc = ph[i] + f * (ph[i + 1] - ph[i])
        pm = (np.degrees(phc) + 180.0) % 360.0
        pms.append(pm if pm <= 180.0 else pm - 360.0)
        wcs.append(w[i] + f * (w[i + 1] - w[i]))
    shifted = (ph + np.pi) / (2 * np.pi)
    jdx = np.nonzero(np.diff(np.floor(shifted)))[0]
    gm_up, gm_down = [np.inf], [np.inf]
    for j in jdx:
        k = np.floor(shifted[j + 1]) if shifted[j + 1] > shifted[j] else np.floor(shifted[j])
        target = 2 * np.pi * k - np.pi
        f = (target - ph[j]) / (ph[j + 1] - ph[j])
        m = mag[j] + f * (mag[j + 1] - mag[j])
        if m < 1.0:
            gm_up.append(-20 * np.log10(m))
        else:
            gm_down.append(20 * np.log10(m))
    return {"pm_deg": float(min(pms)) if pms else float("inf"), "gm_db": float(min(gm_up)),
            "gm_low_db": float(min(gm_down)), "crossover_rad_s": [float(x) for x in wcs]}


def closed_loop_poles(plant, ctrl, spec=SPEC, pade_order=8):
    """Closed loop poles of the linear loop (no limits), built in state space with a Pade delay on each
    measurement. With K_i = 0 the disconnected integrator's pole at the origin is dropped."""
    import control as ct
    A, B, C = plant["A"], plant["B"], plant["C"]
    Ad, Bd, Cd, Dd = (np.atleast_2d(np.asarray(m, dtype=float))
                      for m in ct.ssdata(ct.tf2ss(*ct.pade(spec["delay_s"], pade_order))))
    n, nd, tau = A.shape[0], Ad.shape[0], spec["tau_actuator_s"]
    N = n + 2 + 2 * nd
    ix, idl, ii = slice(0, n), n, n + 1
    izt, izq = slice(n + 2, n + 2 + nd), slice(n + 2 + nd, N)
    th_m = np.zeros(N)
    th_m[ix] = Dd[0, 0] * C[0]
    th_m[izt] = Cd[0]
    q_m = np.zeros(N)
    q_m[ix] = Dd[0, 0] * C[1]
    q_m[izq] = Cd[0]
    u_c = -ctrl["K_p"] * th_m - ctrl["K_q"] * q_m
    u_c[ii] += ctrl["K_i"]
    Acl = np.zeros((N, N))
    Acl[ix, ix] = A
    Acl[ix, idl] = B[:, 0]
    Acl[idl] = u_c / tau
    Acl[idl, idl] -= 1.0 / tau
    Acl[ii] = -th_m
    Acl[izt, izt] = Ad
    Acl[izt, ix] = np.outer(Bd[:, 0], C[0])
    Acl[izq, izq] = Ad
    Acl[izq, ix] = np.outer(Bd[:, 0], C[1])
    poles = np.linalg.eigvals(Acl)
    if ctrl["K_i"] == 0:
        poles = np.delete(poles, np.argmin(np.abs(poles)))
    return poles
