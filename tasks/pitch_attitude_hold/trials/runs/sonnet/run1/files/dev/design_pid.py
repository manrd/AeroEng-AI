"""Closed-form PID design for a target crossover frequency & phase margin, then full-grid margin
verification (all crossings), sweeping wc to find the fastest feasible design."""
import sys
import numpy as np
sys.path.insert(0, ".")
from model import (load_plant, plant_freq_response, ACT_TAU, DELAY_S, default_w_grid,
                    loop_gain, margins_from_L)

A, B, C, D, trim = load_plant()
TRIM_DE = trim["delta_e_rad"]

W = default_w_grid()
_Y = plant_freq_response(A, B, C, W)
PTHETA_JW = _Y[:, 0]
PQ_JW = _Y[:, 1]


def G_at(w):
    """G(jw) = Aact*Delay*Ptheta at scalar or array w, using direct formula (not the big grid)."""
    Y = plant_freq_response(A, B, C, np.atleast_1d(w))
    Ptheta = Y[:, 0]
    jw = 1j * np.atleast_1d(w)
    Aact = 1.0 / (1.0 + ACT_TAU * jw)
    Delay = np.exp(-jw * DELAY_S)
    return Aact * Delay * Ptheta


def design_pid(wc, pm_target_deg, N):
    """Return Kp,Ki,Kq such that L=C*G has |L(jwc)|=1 and phase(L(jwc))=-180+pm_target_deg,
    with the PI corner (zero) placed at wc/N. Kp forced negative (matches plant DC-gain sign)."""
    Gc = G_at(wc)[0]
    magG = abs(Gc)
    phG = np.degrees(np.angle(np.exp(1j * np.angle(Gc))))  # principal value ok; we only need it
    # use unwrapped-consistent phase via a short local sweep from low freq to avoid branch issues
    wtrace = np.geomspace(0.01, wc, 4000)
    Gt = G_at(wtrace)
    ph_trace = np.degrees(np.unwrap(np.angle(Gt)))
    phG_unwrapped = ph_trace[-1]

    Ti = wc / N
    phase_needed_from_C = (-180.0 + pm_target_deg) - phG_unwrapped
    # C = Kp*(1 + 1/(j wc Ti) + j wc Td), Kp<0 contributes 180 deg
    target_inner_phase_deg = phase_needed_from_C - 180.0
    # wrap to (-90,90) branch (principal solution); if outside, infeasible with this simple recipe
    target_inner_phase_deg_wrapped = ((target_inner_phase_deg + 180.0) % 360.0) - 180.0
    tip = np.radians(target_inner_phase_deg_wrapped)
    feasible = abs(target_inner_phase_deg_wrapped) < 89.9
    Td = (np.tan(tip) + 1.0 / (wc * Ti)) / wc
    Kp_mag = np.cos(tip) / magG
    Kp = -Kp_mag
    Ki = Kp / Ti
    Kq = Kp * Td
    return Kp, Ki, Kq, feasible, target_inner_phase_deg_wrapped


def full_margins(Kp, Ki, Kq):
    L = loop_gain(W, Kp, Ki, Kq, PTHETA_JW, PQ_JW)
    return margins_from_L(W, L)


if __name__ == "__main__":
    print("wc sweep, N=6, pm_target=46 deg")
    for wc in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 25]:
        Kp, Ki, Kq, feas, tip = design_pid(wc, 46.0, 6.0)
        m = full_margins(Kp, Ki, Kq)
        print(f"wc={wc:5.1f}  Kp={Kp:9.4f} Ki={Ki:9.4f} Kq={Kq:9.4f}  feas={feas} tip={tip:7.2f} | "
              f"worstPM={m['worst_phase_margin_deg']:8.2f} GMup={m['worst_gain_margin_up_db']:7.2f} "
              f"GMdn={m['worst_gain_margin_down_db']:7.2f} n_gc={m['n_gain_crossovers']} n_pc={m['n_phase_crossovers']}")
