import sys
sys.path.insert(0, "<run>/work")
import numpy as np
import control as ct
from lib import PLANTS, SPEEDS, loop_response, TAU_ACT, DELAY_S
from margins_fast import analyze_margins

Kp, Ki, Kq = -2.0, -4.15, -0.1

# 1) cross-check margins via control.stability_margins on a reduced (but still fine) grid
w_small = np.logspace(-3, 3, 20001)
for spd in SPEEDS:
    pl = PLANTS[spd]
    L = loop_response(pl, w_small, Kp, Ki, Kq)
    mine = analyze_margins(w_small, L)
    mag, phase = np.abs(L), np.degrees(np.angle(L))
    gm, pm, sm, wpc, wgc, wms = ct.stability_margins((mag, phase, w_small), returnall=True)
    gm_db = 20 * np.log10(gm)
    print(f"{spd} m/s: mine PM={mine['worst_pm_deg']:.3f} GMinc={mine['gm_against_increase_db']:.3f}dB")
    print(f"           ctrl PM(all)={pm} GM_db(all)={gm_db}")

print()
# 2) independent closed-loop stability check via Pade approximation of the delay (order 12),
#    building the full closed-loop state matrix (plant 4 + actuator 1 + integrator 1 + Pade states)
#    and checking eigenvalues.
for spd in SPEEDS:
    pl = PLANTS[spd]
    A, B = pl.A, pl.B.reshape(-1, 1)
    Ctheta = np.array([[0, 0, 0, 1.0]])
    Cq = np.array([[0, 0, 1.0, 0]])
    plant_ss = ct.ss(A, B, np.vstack([Ctheta, Cq]), 0)
    act = ct.tf([1], [TAU_ACT, 1])
    pade_num, pade_den = ct.pade(DELAY_S, 12)
    delay = ct.tf(pade_num, pade_den)
    # controller: outputs de_cmd_fb from [theta_m, q_m] (feedback part only, th_cmd=0)
    # de_cmd_fb = -(Kp+Ki/s)*theta_m - Kq*q_m
    s = ct.tf('s')
    C_theta_path = -(Kp + Ki / s)
    C_q_path = -Kq
    # Build as an interconnection: plant_ss (2 outputs: theta,q) -> delay (applied to both) -> controller -> actuator -> plant
    delay_mimo = ct.append(delay, delay)
    ctrl_tf = ct.tf([1], [1]) * 0  # placeholder
    # Simplify: since loop_response already gives L(s) with Pade delay swapped in, build L via Pade and find closed loop poles of 1+L=0
    Pth = ct.tf(ct.ss(A, B, Ctheta, 0))
    Pq = ct.tf(ct.ss(A, B, Cq, 0))
    comp = (Kp + Ki / s) * Pth + Kq * Pq
    L_pade = ct.minreal(act * delay * comp, verbose=False)
    cl_charpoly_poles = ct.poles(ct.feedback(L_pade, 1))
    worst_real = np.max(np.real(cl_charpoly_poles))
    print(f"{spd} m/s: closed-loop poles (Pade-12 delay) worst real part = {worst_real:.5f}  "
          f"(stable if <0); n_poles={len(cl_charpoly_poles)}")
    unstable = cl_charpoly_poles[np.real(cl_charpoly_poles) > 0]
    if len(unstable):
        print("   UNSTABLE POLES:", unstable)
