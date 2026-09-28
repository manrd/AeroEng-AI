"""Supplementary cross-check for R1 ('closed loop is stable on the linear model'): build the exact
augmented closed-loop state-space (plant + actuator + controller integrator + TWO delay blocks, one
each for the theta and q measurement channels) with the delay represented by a high-order Pade
approximant, and check that every eigenvalue has negative real part.

This is a supplementary sanity check, not the primary margin computation (which uses the exact
e^{-s tau} frequency response with no approximation, see loop.py). A 12th-order Pade is accurate to
better than 0.1 deg of phase error out to several hundred rad/s for tau=0.04s, i.e. far beyond this
loop's ~3-6 rad/s crossover and the actuator's 20 rad/s pole, so it is more than sufficient to confirm
there is no hidden instability that better margins alone wouldn't reveal.
"""
import numpy as np
import control
from loop import load_plant, TAU_DELAY, TAU_ACT


def delay_ss(tau, n=12):
    num, den = control.pade(tau, n)
    sys = control.tf2ss(control.tf(num, den))
    return np.asarray(sys.A), np.asarray(sys.B), np.asarray(sys.C), np.asarray(sys.D)


def closed_loop_eigs(Kp, Ki, Kq, A, B, C, n_pade=12):
    Ad, Bd, Cd, Dd = delay_ss(TAU_DELAY, n_pade)
    n = Ad.shape[0]
    C_th = C[0:1, :]   # 1x4
    C_q = C[1:2, :]    # 1x4

    n_p = A.shape[0]     # 4
    n_tot = n_p + 1 + n + n + 1   # plant + actuator + delay_theta + delay_q + integrator
    Acl = np.zeros((n_tot, n_tot))

    # index ranges
    i_p = slice(0, n_p)
    i_e = n_p
    i_dth = slice(n_p + 1, n_p + 1 + n)
    i_dq = slice(n_p + 1 + n, n_p + 1 + 2 * n)
    i_z = n_p + 1 + 2 * n

    # plant: xp_dot = A xp + B*e
    Acl[i_p, i_p] = A
    Acl[i_p, i_e] = B[:, 0]

    # delay theta block: input = theta = C_th @ xp ; xdth_dot = Ad xdth + Bd*theta
    Acl[i_dth, i_dth] = Ad
    Acl[i_dth, i_p] = np.outer(Bd[:, 0], C_th[0, :])
    theta_m_row = lambda: None  # placeholder

    # delay q block: input = q = C_q @ xp
    Acl[i_dq, i_dq] = Ad
    Acl[i_dq, i_p] = np.outer(Bd[:, 0], C_q[0, :])

    # theta_m = Cd @ xdth + Dd * theta ;  q_m = Cd @ xdq + Dd * q
    # u_ctrl (theta_cmd = 0 for the homogeneous/stability system) = -Kp*theta_m + Ki*z - Kq*q_m
    theta_m_from_xdth = Cd[0, :]                     # coefficients on x_dth
    theta_m_from_xp = Dd[0, 0] * C_th[0, :]           # coefficients on xp (direct feedthrough path)
    q_m_from_xdq = Cd[0, :]
    q_m_from_xp = Dd[0, 0] * C_q[0, :]

    u_ctrl_from_xp = -Kp * theta_m_from_xp - Kq * q_m_from_xp
    u_ctrl_from_xdth = -Kp * theta_m_from_xdth
    u_ctrl_from_xdq = -Kq * q_m_from_xdq
    u_ctrl_from_z = Ki

    # actuator: e_dot = (u_ctrl - e)/tau_act
    Acl[i_e, i_p] += u_ctrl_from_xp / TAU_ACT
    Acl[i_e, i_dth] += u_ctrl_from_xdth / TAU_ACT
    Acl[i_e, i_dq] += u_ctrl_from_xdq / TAU_ACT
    Acl[i_e, i_z] += u_ctrl_from_z / TAU_ACT
    Acl[i_e, i_e] += -1.0 / TAU_ACT

    # integrator: z_dot = theta_cmd - theta_m = -theta_m   (theta_cmd = 0 here)
    Acl[i_z, i_p] += -theta_m_from_xp
    Acl[i_z, i_dth] += -theta_m_from_xdth

    eigs = np.linalg.eigvals(Acl)
    return eigs


if __name__ == "__main__":
    for Kp, Ki, Kq in [(-2.0, -4.0, -0.10)]:
        for va in (20, 25, 32):
            A, B, C, trim = load_plant(va)
            eigs = closed_loop_eigs(Kp, Ki, Kq, A, B, C, n_pade=12)
            worst = np.max(eigs.real)
            print(f"Kp={Kp} Ki={Ki} Kq={Kq} va={va}: max real part of closed-loop eig = {worst:.5f}  "
                  f"({'STABLE' if worst < 0 else 'UNSTABLE'})")
