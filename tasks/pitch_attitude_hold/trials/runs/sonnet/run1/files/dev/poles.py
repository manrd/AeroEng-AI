"""Closed-loop pole analysis using an 8th order Pade approximation of the 40 ms delay, to
understand which mode dominates settling time and to guide the search (much cheaper per
evaluation than full time-domain simulation)."""
import sys
import numpy as np
import control as ct
sys.path.insert(0, ".")
from model import load_plant, ACT_TAU, DELAY_S

A, B, C, D, trim = load_plant()
TRIM_DE = trim["delta_e_rad"]

PADE_N = 8
num_d, den_d = ct.pade(DELAY_S, PADE_N)
_delay_ss = ct.tf2ss(ct.tf(num_d, den_d))
Ad_delay = np.array(_delay_ss.A)
Bd_delay = np.array(_delay_ss.B).reshape(-1)
Cd_delay = np.array(_delay_ss.C).reshape(-1)
Dd_delay = float(np.array(_delay_ss.D).reshape(-1)[0])
ND = Ad_delay.shape[0]


def closed_loop_A(Kp, Ki, Kq):
    """State vector: [u,w,q,theta, delta(actuator), I(integrator), xdT(delay of theta, ND), xdQ(delay of q, ND)]."""
    n_plant = 4
    n_tot = n_plant + 1 + 1 + ND + ND
    Aextra = np.zeros((n_tot, n_tot))
    # indices
    i_plant = slice(0, 4)
    i_act = 4
    i_int = 5
    i_dT = slice(6, 6 + ND)
    i_dQ = slice(6 + ND, 6 + 2 * ND)

    # plant: dx/dt = A x + B*delta   (delta = actuator output, perturbation)
    Aextra[i_plant, i_plant] = A
    Aextra[i_plant, i_act] = B[:, 0]

    # delay blocks: dxd/dt = Ad_delay xd + Bd_delay * input ; output = Cd_delay xd + Dd_delay*input
    # theta_m = Cd_delay @ xdT + Dd_delay*theta   (theta = x[3])
    Aextra[i_dT, i_dT] = Ad_delay
    Aextra[i_dT, 3] = Bd_delay  # input to theta-delay block is theta (state 3)
    Aextra[i_dQ, i_dQ] = Ad_delay
    Aextra[i_dQ, 2] = Bd_delay  # input to q-delay block is q (state 2)

    # theta_m, q_m as linear combinations (feedthrough Dd_delay* direct state included)
    def theta_m_row():
        row = np.zeros(n_tot)
        row[i_dT] = Cd_delay
        row[3] += Dd_delay
        return row

    def q_m_row():
        row = np.zeros(n_tot)
        row[i_dQ] = Cd_delay
        row[2] += Dd_delay
        return row

    theta_m_r = theta_m_row()
    q_m_r = q_m_row()

    # controller (homogeneous part, theta_cmd term omitted -- doesn't affect pole locations):
    # delta_cmd = -Kp*theta_m + Ki*I - Kq*q_m
    delta_cmd_row = -Kp * theta_m_r + Ki * unit(n_tot, i_int) - Kq * q_m_r

    # actuator: d(delta)/dt = (delta_cmd - delta)/tau   (linear part, ignoring rate/position sat)
    Aextra[i_act, :] += delta_cmd_row / ACT_TAU
    Aextra[i_act, i_act] += -1.0 / ACT_TAU

    # integrator: dI/dt = -theta_m   (homogeneous part)
    Aextra[i_int, :] += -theta_m_r

    return Aextra


def unit(n, i):
    v = np.zeros(n)
    v[i] = 1.0
    return v


def eigs(Kp, Ki, Kq):
    Acl = closed_loop_A(Kp, Ki, Kq)
    return np.linalg.eigvals(Acl)


def slowest_mode(Kp, Ki, Kq):
    ev = eigs(Kp, Ki, Kq)
    # discard the Pade's own fast/nonphysical or far-negative junk if any; keep all, find max real part
    idx = np.argmax(ev.real)
    return ev[idx], ev


if __name__ == "__main__":
    Kp, Ki, Kq = -2.589706292780335, -1.2948531463901676, -0.22282189526786447
    lam_slow, ev = slowest_mode(Kp, Ki, Kq)
    print("slowest (max real part) closed loop pole:", lam_slow, " |", abs(lam_slow), "tau=", -1/lam_slow.real)
    print("\nall poles sorted by real part (least negative first):")
    for lam in sorted(ev, key=lambda z: -z.real)[:12]:
        wn = abs(lam)
        zeta = -lam.real/wn if wn > 1e-9 else float('nan')
        print(f"  {lam:22.6f}   wn={wn:8.4f}  zeta={zeta:7.4f}")
