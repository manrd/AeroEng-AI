"""Fast pure-Python (scalar-math) reimplementation of aircraft_model.derivatives and
the closed-loop nonlinear simulation, used ONLY to speed up the gain search.

This trades numpy call overhead for plain-float math, precomputing the parameter
scalars once per plant. It is validated against aircraft_model.derivatives (see
dev/check_fastsim.py) to agree to floating point rounding. All FINAL reported
numbers must come from core.simulate (which calls the real aircraft_model.derivatives)
-- this module is a search accelerant, not the source of truth.
"""
import math

import core

D2R = core.D2R
R2D = core.R2D
ACTUATOR_TAU = core.ACTUATOR_TAU
RATE_LIMIT = core.RATE_LIMIT
POS_LIMIT = core.POS_LIMIT
DELAY_STEPS = core.DELAY_STEPS
DT = core.DT
SIM_T = core.SIM_T
STEP_RAD = core.STEP_RAD


def make_fast_derivatives(p):
    mass = p["mass"]; g = p["gravity"]; S = p["S_wing"]; c = p["c"]; rho = p["rho"]
    e = p["e"]; AR = p["AR"]; Jy = p["Jy"]
    CL0 = p["C_L_0"]; CLa = p["C_L_alpha"]; CLq = p["C_L_q"]; CLde = p["C_L_delta_e"]
    CDp = p["C_D_p"]; CDq = p["C_D_q"]; CDde = p["C_D_delta_e"]
    Cm0 = p["C_m_0"]; Cma = p["C_m_alpha"]; Cmq = p["C_m_q"]; Cmde = p["C_m_delta_e"]
    M = p["M"]; a0 = p["alpha0"]
    Dprop = p["D_prop"]; KV = p["KV"]; KQ = p["KQ"]; Rm = p["R_motor"]; i0 = p["i0"]; Vmax = p["V_max"]
    CQ0 = p["C_Q0"]; CQ1 = p["C_Q1"]; CQ2 = p["C_Q2"]; CT0 = p["C_T0"]; CT1 = p["C_T1"]; CT2 = p["C_T2"]
    pi = math.pi
    twopi = 2.0 * pi

    def thrust(Va, delta_t):
        v_in = Vmax * delta_t
        a = CQ0 * rho * Dprop ** 5 / twopi ** 2
        b = CQ1 * rho * Dprop ** 4 / twopi * Va + KQ * KV / Rm
        cc = CQ2 * rho * Dprop ** 3 * Va * Va - KQ / Rm * v_in + KQ * i0
        omega = (-b + math.sqrt(b * b - 4.0 * a * cc)) / (2.0 * a)
        J = twopi * Va / (omega * Dprop)
        CT = CT2 * J * J + CT1 * J + CT0
        return rho * (omega / twopi) ** 2 * Dprop ** 4 * CT

    def deriv(x0, x1, x2, x3, delta_e, delta_t):
        u, w, q, theta = x0, x1, x2, x3
        Va = math.hypot(u, w)
        alpha = math.atan2(w, u)
        qbar_S = 0.5 * rho * Va * Va * S
        qhat = c * q / (2.0 * Va)
        em = math.exp(-M * (alpha - a0))
        ep = math.exp(M * (alpha + a0))
        sigma = (1.0 + em + ep) / ((1.0 + em) * (1.0 + ep))
        linear = CL0 + CLa * alpha
        sgn = 1.0 if alpha > 0.0 else (-1.0 if alpha < 0.0 else 0.0)
        sina = math.sin(alpha)
        cosa = math.cos(alpha)
        CL = (1.0 - sigma) * linear + sigma * 2.0 * sgn * sina * sina * cosa
        CD = CDp + linear * linear / (pi * e * AR)
        lift = qbar_S * (CL + CLq * qhat + CLde * delta_e)
        drag = qbar_S * (CD + CDq * qhat + CDde * delta_e)
        fx = -drag * cosa + lift * sina + thrust(Va, delta_t) - mass * g * math.sin(theta)
        fz = -drag * sina - lift * cosa + mass * g * math.cos(theta)
        my = qbar_S * c * (Cm0 + Cma * alpha + Cmq * qhat + Cmde * delta_e)
        return (-q * w + fx / mass, q * u + fz / mass, my / Jy, q)

    return deriv


def clip(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def simulate_fast(plant, Kp, Ki, Kq, b, deriv, T=SIM_T, dt=DT, theta_cmd=STEP_RAD):
    n = int(round(T / dt))
    theta_trim = plant["_theta_trim"]
    delta_trim = plant["_delta_e_trim"]
    throttle = plant["_delta_t_trim"]
    x0 = plant["_x0"]

    x0_, x1_, x2_, x3_ = float(x0[0]), float(x0[1]), float(x0[2]), float(x0[3])
    delta = delta_trim
    integ = 0.0

    theta_hist = [0.0] * (n + 1)
    q_hist = [0.0] * (n + 1)

    max_abs_cmd = 0.0
    peak_theta_pert_deg = -1e18
    diverged = False
    div_step = n

    dt_over_tau = dt / ACTUATOR_TAU

    for k in range(n + 1):
        theta_pert_k = x3_ - theta_trim
        q_k = x2_
        theta_hist[k] = theta_pert_k
        q_hist[k] = q_k

        j = k - DELAY_STEPS
        theta_m = theta_hist[j] if j >= 0 else 0.0
        q_m = q_hist[j] if j >= 0 else 0.0

        delta_e_cmd_pert = Kp * (b * theta_cmd - theta_m) + Ki * integ - Kq * q_m
        delta_cmd_abs = delta_trim + delta_e_cmd_pert
        acmd = delta_cmd_abs if delta_cmd_abs >= 0 else -delta_cmd_abs
        if acmd > max_abs_cmd:
            max_abs_cmd = acmd

        tpd = theta_pert_k * R2D
        if tpd > peak_theta_pert_deg:
            peak_theta_pert_deg = tpd

        Va_k = math.hypot(x0_, x1_)
        if theta_pert_k > 1.5 or theta_pert_k < -1.5 or Va_k < 5.0 or Va_k > 60.0:
            diverged = True
            div_step = k
            break

        if k == n:
            break

        delta_cmd_sat = clip(delta_cmd_abs, -POS_LIMIT, POS_LIMIT)
        rate_raw = (delta_cmd_sat - delta) / ACTUATOR_TAU
        rate_sat = clip(rate_raw, -RATE_LIMIT, RATE_LIMIT)
        delta_next = clip(delta + dt * rate_sat, -POS_LIMIT, POS_LIMIT)

        d0, d1, d2, d3 = deriv(x0_, x1_, x2_, x3_, delta, throttle)
        xa0, xa1, xa2, xa3 = x0_ + 0.5 * dt * d0, x1_ + 0.5 * dt * d1, x2_ + 0.5 * dt * d2, x3_ + 0.5 * dt * d3
        e0, e1, e2, e3 = deriv(xa0, xa1, xa2, xa3, delta, throttle)
        xb0, xb1, xb2, xb3 = x0_ + 0.5 * dt * e0, x1_ + 0.5 * dt * e1, x2_ + 0.5 * dt * e2, x3_ + 0.5 * dt * e3
        f0, f1, f2, f3 = deriv(xb0, xb1, xb2, xb3, delta, throttle)
        xc0, xc1, xc2, xc3 = x0_ + dt * f0, x1_ + dt * f1, x2_ + dt * f2, x3_ + dt * f3
        g0, g1, g2, g3 = deriv(xc0, xc1, xc2, xc3, delta, throttle)

        x0_ = x0_ + (dt / 6.0) * (d0 + 2 * e0 + 2 * f0 + g0)
        x1_ = x1_ + (dt / 6.0) * (d1 + 2 * e1 + 2 * f1 + g1)
        x2_ = x2_ + (dt / 6.0) * (d2 + 2 * e2 + 2 * f2 + g2)
        x3_ = x3_ + (dt / 6.0) * (d3 + 2 * e3 + 2 * f3 + g3)

        integ = integ + dt * (theta_cmd - theta_m)
        delta = delta_next

    step_deg = theta_cmd * R2D
    overshoot_pct = max(0.0, (peak_theta_pert_deg - step_deg) / step_deg * 100.0)
    band = 0.02 * step_deg
    last_idx = -1
    for k in range(div_step, -1, -1):
        tpd = theta_hist[k] * R2D
        if abs(tpd - step_deg) > band:
            last_idx = k
            break
    settling_time_s = 0.0 if last_idx < 0 else last_idx * dt
    max_elevator_deg = max_abs_cmd * R2D

    return {
        "diverged": diverged,
        "overshoot_pct": overshoot_pct,
        "settling_time_s": settling_time_s,
        "max_elevator_deg": max_elevator_deg,
        "peak_theta_deg": peak_theta_pert_deg,
        "div_step": div_step,
    }
