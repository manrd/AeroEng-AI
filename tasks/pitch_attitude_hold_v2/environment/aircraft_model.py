"""Longitudinal flight dynamics of the Aerosonde UAV: trim and linearization.

Equations follow Beard and McLain, Small Unmanned Aircraft (2012), chapter 4, restricted to the longitudinal
plane (no sideslip, no roll or yaw rate) with a flat earth and no wind. Parameter values are in
aircraft_aerosonde.json, with their source.

State x = [u, w, q, theta]: body axis velocities (m/s), pitch rate (rad/s), pitch attitude (rad).
Input  = [delta_e, delta_t]: elevator (rad, positive trailing edge down, which pitches the nose down) and
throttle (0 to 1).

    python aircraft_model.py            writes plant_20.json, plant_25.json and plant_32.json (trim in level flight at
                                        each airspeed) and prints a summary
"""
import json
import pathlib

import numpy as np
from scipy.optimize import fsolve

HERE = pathlib.Path(__file__).parent


def load_params(path=HERE / "aircraft_aerosonde.json"):
    p = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    p["AR"] = p["b"] ** 2 / p["S_wing"]
    kv = (1.0 / p["KV_rpm_per_volt"]) * 60.0 / (2.0 * np.pi)  # back EMF constant, V s/rad
    p["KV"] = kv
    p["KQ"] = kv  # torque constant, N m/A
    p["V_max"] = 3.7 * p["ncells"]
    return p


def thrust(p, Va, delta_t):
    """Propeller thrust (N) from the motor and propeller model: torque balance for the shaft speed, then C_T(J)."""
    rho, D = p["rho"], p["D_prop"]
    v_in = p["V_max"] * delta_t
    a = p["C_Q0"] * rho * D**5 / (2.0 * np.pi) ** 2
    b = p["C_Q1"] * rho * D**4 / (2.0 * np.pi) * Va + p["KQ"] * p["KV"] / p["R_motor"]
    c = p["C_Q2"] * rho * D**3 * Va**2 - p["KQ"] / p["R_motor"] * v_in + p["KQ"] * p["i0"]
    omega = (-b + np.sqrt(b**2 - 4.0 * a * c)) / (2.0 * a)
    J = 2.0 * np.pi * Va / (omega * D)
    C_T = p["C_T2"] * J**2 + p["C_T1"] * J + p["C_T0"]
    return rho * (omega / (2.0 * np.pi)) ** 2 * D**4 * C_T


def lift_drag_coefficients(p, alpha):
    """C_L with the blended flat plate stall model, and C_D with the induced drag polar (Beard and McLain, ch. 4)."""
    M, a0 = p["M"], p["alpha0"]
    sigma = (1 + np.exp(-M * (alpha - a0)) + np.exp(M * (alpha + a0))) / (
        (1 + np.exp(-M * (alpha - a0))) * (1 + np.exp(M * (alpha + a0))))
    linear = p["C_L_0"] + p["C_L_alpha"] * alpha
    C_L = (1 - sigma) * linear + sigma * 2.0 * np.sign(alpha) * np.sin(alpha) ** 2 * np.cos(alpha)
    C_D = p["C_D_p"] + linear**2 / (np.pi * p["e"] * p["AR"])
    return C_L, C_D


def derivatives(p, x, inp):
    """dx/dt for x = [u, w, q, theta] and inp = [delta_e, delta_t]."""
    u, w, q, theta = x
    delta_e, delta_t = inp
    m, g = p["mass"], p["gravity"]
    Va = np.hypot(u, w)
    alpha = np.arctan2(w, u)
    qbar_S = 0.5 * p["rho"] * Va**2 * p["S_wing"]
    qhat = p["c"] * q / (2.0 * Va)
    C_L, C_D = lift_drag_coefficients(p, alpha)
    lift = qbar_S * (C_L + p["C_L_q"] * qhat + p["C_L_delta_e"] * delta_e)
    drag = qbar_S * (C_D + p["C_D_q"] * qhat + p["C_D_delta_e"] * delta_e)
    fx = -drag * np.cos(alpha) + lift * np.sin(alpha) + thrust(p, Va, delta_t) - m * g * np.sin(theta)
    fz = -drag * np.sin(alpha) - lift * np.cos(alpha) + m * g * np.cos(theta)
    my = qbar_S * p["c"] * (p["C_m_0"] + p["C_m_alpha"] * alpha + p["C_m_q"] * qhat + p["C_m_delta_e"] * delta_e)
    return np.array([-q * w + fx / m, q * u + fz / m, my / p["Jy"], q])


def trim_level(p, Va):
    """Wings level, constant altitude flight at airspeed Va: solve for alpha, delta_e, delta_t."""
    def residual(z):
        alpha, delta_e, delta_t = z
        x = [Va * np.cos(alpha), Va * np.sin(alpha), 0.0, alpha]  # theta = alpha, since the flight path is level
        return derivatives(p, x, [delta_e, delta_t])[:3]

    z, info, ok, msg = fsolve(residual, [0.05, -0.1, 0.5], full_output=True, xtol=1e-12)
    if ok != 1:
        raise RuntimeError(f"trim did not converge: {msg}")
    alpha, delta_e, delta_t = z
    x0 = np.array([Va * np.cos(alpha), Va * np.sin(alpha), 0.0, alpha])
    return x0, np.array([delta_e, delta_t]), float(np.max(np.abs(residual(z))))


def linearize(p, x0, u0, rel_step=1e-6):
    """Central difference Jacobians A = df/dx and B = df/du at the trim point."""
    n, m = len(x0), len(u0)
    A, B = np.zeros((n, n)), np.zeros((n, m))
    for i in range(n):
        h = rel_step * max(1.0, abs(x0[i]))
        dx = np.zeros(n)
        dx[i] = h
        A[:, i] = (derivatives(p, x0 + dx, u0) - derivatives(p, x0 - dx, u0)) / (2 * h)
    for j in range(m):
        h = rel_step * max(1.0, abs(u0[j]))
        du = np.zeros(m)
        du[j] = h
        B[:, j] = (derivatives(p, x0, u0 + du) - derivatives(p, x0, u0 - du)) / (2 * h)
    return A, B


def short_period_estimate(p, Va, alpha):
    """Hand calculation: the classical two state short period approximation from the dimensional derivatives.

    Z_alpha/Va comes from the lift curve slope plus drag, M_alpha and M_q from C_m_alpha and C_m_q. Independent of
    the numerical Jacobian, so it checks the linearization.
    """
    qbar = 0.5 * p["rho"] * Va**2
    S, c, m, Jy = p["S_wing"], p["c"], p["mass"], p["Jy"]
    _, C_D = lift_drag_coefficients(p, alpha)
    Z_alpha_over_V = -qbar * S * (p["C_L_alpha"] + C_D) / (m * Va)   # 1/s
    M_alpha = qbar * S * c * p["C_m_alpha"] / Jy                      # 1/s^2
    M_q = qbar * S * c * p["C_m_q"] * c / (2 * Va) / Jy               # 1/s
    wn = np.sqrt(Z_alpha_over_V * M_q - M_alpha)
    zeta = -(Z_alpha_over_V + M_q) / (2 * wn)
    return wn, zeta


def modes(A):
    """Natural frequency (rad/s) and damping ratio of each complex pair, fastest first."""
    out = []
    for lam in np.linalg.eigvals(A):
        if lam.imag > 1e-9:
            wn = abs(lam)
            out.append((wn, -lam.real / wn))
    return sorted(out, reverse=True)


SPEEDS = (20.0, 25.0, 32.0)


def write_plant(Va):
    """Trim at airspeed Va, linearize, and write plant_<Va>.json with the trim state for the nonlinear model."""
    p = load_params()
    x0, u0, res = trim_level(p, Va)
    A, B = linearize(p, x0, u0)
    alpha = float(np.arctan2(x0[1], x0[0]))
    (wn_sp, z_sp), (wn_ph, z_ph) = modes(A)
    wn_est, z_est = short_period_estimate(p, Va, alpha)
    plant = {
        "description": f"Aerosonde UAV, longitudinal dynamics linearized about wings level, constant altitude flight "
                       f"at {Va:g} m/s. Perturbation model: dx/dt = A x + B delta_e, y = C x.",
        "source": "Generated by environment/aircraft_model.py from aircraft_aerosonde.json (parameters from Beard "
                  "and McLain, 2012). Throttle is held at its trim value.",
        "states": ["u (m/s)", "w (m/s)", "q (rad/s)", "theta (rad)"],
        "input": "delta_e (rad), positive trailing edge down, which pitches the nose down",
        "outputs": ["theta (rad)", "q (rad/s)"],
        "A": A.round(10).tolist(),
        "B": B[:, [0]].round(10).tolist(),
        "C": [[0.0, 0.0, 0.0, 1.0], [0.0, 0.0, 1.0, 0.0]],
        "D": [[0.0], [0.0]],
        "trim": {"airspeed_m_s": Va, "alpha_rad": alpha, "theta_rad": float(x0[3]),
                 "delta_e_rad": float(u0[0]), "delta_t": float(u0[1]),
                 "state": [float(v) for v in x0]},
    }
    name = f"plant_{Va:g}.json"
    (HERE / name).write_text(json.dumps(plant, indent=2), encoding="utf-8")
    print(f"{Va:g} m/s: alpha {np.degrees(alpha):.3f} deg, delta_e {np.degrees(u0[0]):.3f} deg, "
          f"delta_t {u0[1]:.4f}, residual {res:.1e}; short period {wn_sp:.3f} rad/s, zeta {z_sp:.3f} "
          f"(hand estimate {wn_est:.3f}, {z_est:.3f}); phugoid {wn_ph:.4f} rad/s, zeta {z_ph:.4f}; wrote {name}")


def main():
    for Va in SPEEDS:
        write_plant(Va)


if __name__ == "__main__":
    main()
