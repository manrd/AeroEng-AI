"""Fast scalar re-implementation of environment/aircraft_model.py's derivatives(), for cheap RK4 time
simulation in Python loops. Cross-checked against the original numpy implementation in
cross_check.py -- must match to numerical noise.
"""
import json
import math
import pathlib

HERE = pathlib.Path(__file__).parent
ENV = HERE.parent / "environment"


class Params:
    __slots__ = ("mass", "Jy", "S_wing", "b_wing", "c", "rho", "e", "AR", "gravity",
                 "C_L_0", "C_L_alpha", "C_L_q", "C_L_delta_e",
                 "C_D_p", "C_D_q", "C_D_delta_e",
                 "C_m_0", "C_m_alpha", "C_m_q", "C_m_delta_e",
                 "M", "alpha0", "D_prop", "KV", "KQ", "R_motor", "i0", "V_max",
                 "C_Q0", "C_Q1", "C_Q2", "C_T0", "C_T1", "C_T2",
                 "thrust_a")

    def __init__(self, d):
        self.mass = d["mass"]; self.Jy = d["Jy"]; self.S_wing = d["S_wing"]
        self.b_wing = d["b"]; self.c = d["c"]; self.rho = d["rho"]; self.e = d["e"]
        self.AR = d["b"] ** 2 / d["S_wing"]
        self.gravity = d["gravity"]
        self.C_L_0 = d["C_L_0"]; self.C_L_alpha = d["C_L_alpha"]
        self.C_L_q = d["C_L_q"]; self.C_L_delta_e = d["C_L_delta_e"]
        self.C_D_p = d["C_D_p"]; self.C_D_q = d["C_D_q"]; self.C_D_delta_e = d["C_D_delta_e"]
        self.C_m_0 = d["C_m_0"]; self.C_m_alpha = d["C_m_alpha"]
        self.C_m_q = d["C_m_q"]; self.C_m_delta_e = d["C_m_delta_e"]
        self.M = d["M"]; self.alpha0 = d["alpha0"]
        self.D_prop = d["D_prop"]
        kv = (1.0 / d["KV_rpm_per_volt"]) * 60.0 / (2.0 * math.pi)
        self.KV = kv; self.KQ = kv
        self.R_motor = d["R_motor"]; self.i0 = d["i0"]
        self.V_max = 3.7 * d["ncells"]
        self.C_Q0 = d["C_Q0"]; self.C_Q1 = d["C_Q1"]; self.C_Q2 = d["C_Q2"]
        self.C_T0 = d["C_T0"]; self.C_T1 = d["C_T1"]; self.C_T2 = d["C_T2"]
        self.thrust_a = self.C_Q0 * self.rho * self.D_prop ** 5 / (2.0 * math.pi) ** 2


def load_params(path=ENV / "aircraft_aerosonde.json"):
    return Params(json.loads(pathlib.Path(path).read_text(encoding="utf-8")))


def thrust(p: Params, Va, delta_t):
    v_in = p.V_max * delta_t
    a = p.thrust_a
    b = p.C_Q1 * p.rho * p.D_prop ** 4 / (2.0 * math.pi) * Va + p.KQ * p.KV / p.R_motor
    c = p.C_Q2 * p.rho * p.D_prop ** 3 * Va ** 2 - p.KQ / p.R_motor * v_in + p.KQ * p.i0
    omega = (-b + math.sqrt(b * b - 4.0 * a * c)) / (2.0 * a)
    J = 2.0 * math.pi * Va / (omega * p.D_prop)
    C_T = p.C_T2 * J * J + p.C_T1 * J + p.C_T0
    return p.rho * (omega / (2.0 * math.pi)) ** 2 * p.D_prop ** 4 * C_T


def lift_drag(p: Params, alpha):
    M, a0 = p.M, p.alpha0
    e_neg = math.exp(-M * (alpha - a0))
    e_pos = math.exp(M * (alpha + a0))
    sigma = (1.0 + e_neg + e_pos) / ((1.0 + e_neg) * (1.0 + e_pos))
    linear = p.C_L_0 + p.C_L_alpha * alpha
    sin_a = math.sin(alpha)
    sign_a = 1.0 if alpha > 0.0 else (-1.0 if alpha < 0.0 else 0.0)
    C_L = (1.0 - sigma) * linear + sigma * 2.0 * sign_a * sin_a * sin_a * math.cos(alpha)
    C_D = p.C_D_p + linear * linear / (math.pi * p.e * p.AR)
    return C_L, C_D


def derivatives(p: Params, u, w, q, theta, delta_e, delta_t):
    m, g = p.mass, p.gravity
    Va = math.hypot(u, w)
    alpha = math.atan2(w, u)
    qbar_S = 0.5 * p.rho * Va * Va * p.S_wing
    qhat = p.c * q / (2.0 * Va)
    C_L, C_D = lift_drag(p, alpha)
    lift = qbar_S * (C_L + p.C_L_q * qhat + p.C_L_delta_e * delta_e)
    drag = qbar_S * (C_D + p.C_D_q * qhat + p.C_D_delta_e * delta_e)
    sin_a, cos_a = math.sin(alpha), math.cos(alpha)
    T = thrust(p, Va, delta_t)
    sin_t, cos_t = math.sin(theta), math.cos(theta)
    fx = -drag * cos_a + lift * sin_a + T - m * g * sin_t
    fz = -drag * sin_a - lift * cos_a + m * g * cos_t
    my = qbar_S * p.c * (p.C_m_0 + p.C_m_alpha * alpha + p.C_m_q * qhat + p.C_m_delta_e * delta_e)
    du = -q * w + fx / m
    dw = q * u + fz / m
    dq = my / p.Jy
    dtheta = q
    return du, dw, dq, dtheta


def rk4_step(p: Params, state, delta_e, delta_t, dt):
    u, w, q, th = state
    k1 = derivatives(p, u, w, q, th, delta_e, delta_t)
    k2 = derivatives(p, u + 0.5 * dt * k1[0], w + 0.5 * dt * k1[1], q + 0.5 * dt * k1[2], th + 0.5 * dt * k1[3],
                      delta_e, delta_t)
    k3 = derivatives(p, u + 0.5 * dt * k2[0], w + 0.5 * dt * k2[1], q + 0.5 * dt * k2[2], th + 0.5 * dt * k2[3],
                      delta_e, delta_t)
    k4 = derivatives(p, u + dt * k3[0], w + dt * k3[1], q + dt * k3[2], th + dt * k3[3],
                      delta_e, delta_t)
    nu = u + dt / 6.0 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0])
    nw = w + dt / 6.0 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1])
    nq = q + dt / 6.0 * (k1[2] + 2 * k2[2] + 2 * k3[2] + k4[2])
    nth = th + dt / 6.0 * (k1[3] + 2 * k2[3] + 2 * k3[3] + k4[3])
    return (nu, nw, nq, nth)
