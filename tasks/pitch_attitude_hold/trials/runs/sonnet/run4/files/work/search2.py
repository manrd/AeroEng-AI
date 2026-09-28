import numpy as np
from search import freq_eval, feasible

results = []
for kq in [0.4, 0.5, 0.6, 0.7, 0.8, 1.0, 1.2, 1.5, 1.8, 2.2, 2.6, 3.0]:
    Kq = -kq
    best = None
    for kp in np.linspace(0.3, 8, 35):
        for ki in np.linspace(0.02, 4, 35):
            Kp, Ki = -kp, -ki
            res = freq_eval(Kp, Ki, Kq)
            if feasible(res, pm_min=45.0, gm_min=6.0):
                wmax = max(res["wgc_list"]) if res["wgc_list"] else 0
                if best is None or wmax > best[0]:
                    best = (wmax, kp, ki, res)
    if best:
        wmax, kp, ki, res = best
        print(f"Kq={Kq:6.2f}  best wgc={wmax:.3f}  Kp={-kp:.3f} Ki={-ki:.3f}  "
              f"PM={res['worst_pm']:.2f} GMinc={res['worst_gm_inc']} GMdec={res['worst_gm_dec']} "
              f"n_gc={res['n_gain_cross']} n_pc={res['n_phase_cross']}", flush=True)
        results.append((Kq, wmax, -kp, -ki))
    else:
        print(f"Kq={Kq:6.2f}  no feasible point found in grid", flush=True)

np.save("results2.npy", np.array(results))
