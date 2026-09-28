import sys, time
import numpy as np
sys.path.insert(0, ".")
from model import (load_plant, plant_freq_response, discretize, simulate,
                    loop_gain, margins_from_L, default_w_grid)

A, B, C, D, trim = load_plant()
print("trim:", trim)
trim_de = trim["delta_e_rad"]

# sanity: DC gain check at very low freq
w_small = np.array([1e-6])
Y = plant_freq_response(A, B, C, w_small)
print("low-freq theta/de, q/de:", Y[0])
print("expected theta DC gain ~ -1.776, q DC gain ~ 0")

t0 = time.time()
w = default_w_grid()
Y = plant_freq_response(A, B, C, w)
Ptheta_jw = Y[:, 0]
Pq_jw = Y[:, 1]
print("freq resp time for", len(w), "points:", time.time() - t0, "s")

Ad, Bd = discretize(A, B)
print("Ad eig:", np.abs(np.linalg.eigvals(Ad)))

# quick simulate with arbitrary small gains just to test plumbing / timing
t0 = time.time()
res = simulate(Kp=-1.0, Ki=-0.5, Kq=-0.3, b=0.5, A=A, B=B,
               trim_delta_e_rad=trim_de, theta_cmd_rad=np.radians(5.0))
print("sim time:", time.time() - t0, "s")
print("theta_deg[-1]:", res["theta_deg"][-1], "final q:", res["q_radps"][-1])
print("max |cmd_abs_deg|:", np.max(np.abs(res["cmd_abs_deg"])))

L = loop_gain(w, -1.0, -0.5, -0.3, Ptheta_jw, Pq_jw)
t0 = time.time()
m = margins_from_L(w, L)
print("margins calc time:", time.time() - t0, "s")
print("worst PM:", m["worst_phase_margin_deg"], "n_gc:", m["n_gain_crossovers"])
print("worst GM up:", m["worst_gain_margin_up_db"], "worst GM down:", m["worst_gain_margin_down_db"], "n_pc:", m["n_phase_crossovers"])
