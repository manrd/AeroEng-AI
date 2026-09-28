import sys
sys.path.insert(0, "work")
import numpy as np
import core
from loopshape import P2, design_at_crossover

num_theta, den_theta = core.theta_tf()

for wc in np.arange(9, 20.1, 1.0):
    for N in [8, 12, 20]:
        for pm_t in [45.0, 50.0]:
            kp,ki,kq = design_at_crossover(wc, N, pm_target_deg=pm_t)
            Kp,Ki,Kq = -kp,-ki,-kq
            res = core.compute_margins(Kp,Ki,Kq, num_theta, den_theta, n=20001)
            print(f"wc={wc:5.1f} N={N:2d} pmT={pm_t:4.0f}: kp={kp:6.3f} ki={ki:6.3f} kq={kq:7.4f}  "
                  f"PM={res['phase_margin_deg']:6.2f} GMi={res['gain_margin_incr_db']:6.2f} GMd={res['gain_margin_decr_db']:6.1f}")
