"""Independent cross-check of R1 (linear closed-loop stability) using a
high-order Pade approximation of the 40 ms delay, so the check does not share
any code path with margins.py's crossing scan. Builds L_pade(s) as a rational
transfer function and finds the roots of (1 + L_pade(s))'s numerator -- the
closed-loop poles -- checking that all have negative real part, at increasing
Pade order to confirm convergence.
"""
import numpy as np
import control as ct

import core


def loop_gain_tf(plant, Kp, Ki, Kq, pade_order=12, tau_delay=core.DELAY_S, tau_act=core.ACTUATOR_TAU):
    A, B, C = plant["_A"], plant["_B"], plant["_C"]
    Ptheta = ct.ss(A, B, C[0:1, :], [[0.0]])
    Pq = ct.ss(A, B, C[1:2, :], [[0.0]])
    Ptheta_tf = ct.tf(Ptheta)
    Pq_tf = ct.tf(Pq)

    Gact = ct.tf([1.0], [tau_act, 1.0])
    num_d, den_d = ct.pade(tau_delay, pade_order)
    Delay = ct.tf(num_d, den_d)

    s = ct.tf('s')
    ctrl_theta = Kp + Ki / s

    L = Delay * Gact * (ctrl_theta * Ptheta_tf + Kq * Pq_tf)
    return L


def closed_loop_poles(plant, Kp, Ki, Kq, pade_order=12):
    L = loop_gain_tf(plant, Kp, Ki, Kq, pade_order=pade_order)
    one_plus_L = 1 + L
    num = np.squeeze(one_plus_L.num[0][0]) if hasattr(one_plus_L, "num") else None
    # control >=0.10 stores num/den as nested lists [[array]]
    num_poly = one_plus_L.num[0][0]
    roots = np.roots(num_poly)
    return roots


def check(plant, Kp, Ki, Kq, orders=(8, 12, 16, 24)):
    results = {}
    for n in orders:
        roots = closed_loop_poles(plant, Kp, Ki, Kq, pade_order=n)
        worst_real = float(np.max(roots.real))
        results[n] = (worst_real, roots)
    return results


if __name__ == "__main__":
    import sys
    Kp, Ki, Kq = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
    for spd in core.SPEEDS:
        plant = core.load_plant(spd)
        res = check(plant, Kp, Ki, Kq)
        print(f"--- {spd} m/s ---")
        for n, (worst_real, roots) in res.items():
            print(f"  Pade order {n}: max Re(closed-loop pole) = {worst_real:.5f}  "
                  f"({'STABLE' if worst_real < 0 else 'UNSTABLE'})")
