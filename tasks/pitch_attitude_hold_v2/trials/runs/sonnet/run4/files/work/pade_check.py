"""Independent cross-check of R1 (closed-loop stability on the linear model): build a finite-dimensional
approximation of the closed loop (plant + actuator lag + Pade-approximated delay + PI/rate controller)
and check that every pole has negative real part. This is independent of the Bode crossing-detection
code in loopgain.py (different method, same question), used only as a sanity cross-check.
"""
import numpy as np
import control as ct
import loopgain as lg


def closed_loop_poles(Kp, Ki, Kq, plant, pade_order=10):
    A, B, C = plant["A"], plant["B"].reshape(-1, 1), plant["C"]
    n = A.shape[0]
    D = np.zeros((2, 1))
    ss_plant = ct.ss(A, B, C, D)

    act = ct.tf([1.0], [lg.TAU_ACT, 1.0])
    num_pade, den_pade = ct.pade(lg.TAU_DELAY, pade_order)
    delay = ct.tf(num_pade, den_pade)

    theta_ch = ss_plant[0, 0]  # theta channel
    q_ch = ss_plant[1, 0]      # q channel

    # forward path delta_e_cmd -> [theta_m, q_m] through actuator, plant, delay
    fwd_theta = ct.series(act, theta_ch, delay)
    fwd_q = ct.series(act, q_ch, delay)

    s = ct.tf('s')
    pi = Kp + Ki / s
    loop = ct.parallel(ct.series(pi, fwd_theta), ct.series(Kq, fwd_q))
    # characteristic equation 1 + loop = 0  <=> feedback(1, loop) poles, but simplest: poles of
    # closed loop with unity feedback around 'loop' (theta_cmd path doesn't matter for stability)
    cl = ct.feedback(loop, 1)
    poles = ct.poles(cl)
    return poles


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 4:
        Kp, Ki, Kq = (float(x) for x in sys.argv[1:4])
    else:
        Kp, Ki, Kq = 0.3, 0.9, 2.5
    print("Kp,Ki,Kq =", Kp, Ki, Kq)
    for order in (4, 6, 8, 10):
        print(f"--- Pade order {order} ---")
        for spd in (20, 25, 32):
            plant = lg.load_plant(spd)
            try:
                poles = closed_loop_poles(Kp, Ki, Kq, plant, pade_order=order)
                worst = max(p.real for p in poles)
                print(f"  {spd} m/s: max real part = {worst:.4f}  "
                      f"{'STABLE' if worst < 0 else 'UNSTABLE'}  (n_poles={len(poles)})")
            except Exception as e:
                print(spd, "ERROR", e)
