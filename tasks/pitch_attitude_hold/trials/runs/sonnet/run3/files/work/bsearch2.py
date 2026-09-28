import sys
sys.path.insert(0, "work")
import numpy as np
import core
from loopshape import design_at_crossover
from bsearch import best_b

num_theta, den_theta = core.theta_tf()

print(f"{'wc':>5} {'N':>3} {'pmT':>4} | {'PM':>6} {'GMi':>6} {'GMd':>6} | {'b*':>5} {'settle':>7} {'OS%':>6} {'maxE':>6} feas")
results = []
for wc in [11, 12, 13, 14, 15]:
    for N in [3, 4, 5, 6, 8]:
        for pmT in [45.0, 48.0]:
            kp, ki, kq = design_at_crossover(wc, N, pm_target_deg=pmT)
            if kp <= 0:
                continue
            Kp, Ki, Kq = -kp, -ki, -kq
            res = core.compute_margins(Kp, Ki, Kq, num_theta, den_theta, n=20001)
            if res["phase_margin_deg"] < 44.9 or res["gain_margin_incr_db"] < 5.9:
                print(f"{wc:5.1f} {N:3d} {pmT:4.0f} | {res['phase_margin_deg']:6.2f} {res['gain_margin_incr_db']:6.2f} {res['gain_margin_decr_db']:6.1f} |  (margin fail)")
                continue
            r = best_b(Kp, Ki, Kq, b_grid=np.linspace(0, 1, 26))
            print(f"{wc:5.1f} {N:3d} {pmT:4.0f} | {res['phase_margin_deg']:6.2f} {res['gain_margin_incr_db']:6.2f} {res['gain_margin_decr_db']:6.1f} | "
                  f"{r['b']:5.2f} {r['settling_time_s']:7.3f} {r['overshoot_pct']:6.2f} {r['max_elevator_deg']:6.2f} {r['feasible']}")
            results.append((wc, N, pmT, Kp, Ki, Kq, r))

results.sort(key=lambda t: t[6]["settling_time_s"] if t[6]["feasible"] else 1e9)
print()
print("Top 5 by settling time (feasible only):")
for t in results[:5]:
    wc, N, pmT, Kp, Ki, Kq, r = t
    print(f"  wc={wc} N={N} pmT={pmT}: Kp={Kp:.4f} Ki={Ki:.4f} Kq={Kq:.4f} b={r['b']:.3f} settle={r['settling_time_s']:.3f} OS={r['overshoot_pct']:.2f} maxE={r['max_elevator_deg']:.2f} feas={r['feasible']}")
