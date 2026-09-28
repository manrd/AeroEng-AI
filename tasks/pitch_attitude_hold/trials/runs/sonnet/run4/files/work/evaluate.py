import numpy as np
from common import (simulate, requirements_from_sim, closed_loop_eigs, TRIM_DELTA_E_DEG)
from search import freq_eval

def full_eval(Kp, Ki, Kq, b, t_end=20.0, pade_order=8, verbose=True):
    fr = freq_eval(Kp, Ki, Kq)
    sim = simulate(Kp, Ki, Kq, b, t_end=t_end)
    req = requirements_from_sim(sim)
    eigs = closed_loop_eigs(Kp, Ki, Kq, pade_order=pade_order)
    max_real = max(e.real for e in eigs)
    out = {
        "Kp": Kp, "Ki": Ki, "Kq": Kq, "b": b,
        "worst_pm": fr["worst_pm"], "worst_gm_inc": fr["worst_gm_inc"], "worst_gm_dec": fr["worst_gm_dec"],
        "n_gc": fr["n_gain_cross"], "n_pc": fr["n_phase_cross"],
        "wgc_list": fr["wgc_list"],
        "overshoot_pct": req["overshoot_pct"], "settling_time_s": req["settling_time_s"],
        "max_elevator_deg": req["max_elevator_deg"], "theta_peak_deg": req["theta_peak_deg"],
        "max_real_eig_pade": max_real,
        "stable_pade": max_real < 0,
    }
    if verbose:
        print(f"Kp={Kp:.4f} Ki={Ki:.4f} Kq={Kq:.4f} b={b:.4f}")
        print(f"  PM={out['worst_pm']:.2f}deg  GMinc={out['worst_gm_inc']}  GMdec={out['worst_gm_dec']}  "
              f"n_gc={out['n_gc']} n_pc={out['n_pc']} wgc={out['wgc_list']}")
        print(f"  overshoot={out['overshoot_pct']:.3f}%  settling={out['settling_time_s']:.3f}s  "
              f"max_elev={out['max_elevator_deg']:.3f}deg  theta_peak={out['theta_peak_deg']:.3f}deg")
        print(f"  Pade closed-loop max real eig={out['max_real_eig_pade']:.4f}  stable={out['stable_pade']}")
    return out


if __name__ == "__main__":
    import sys
    full_eval(-2.0, -1.0, -0.2, 1.0)
