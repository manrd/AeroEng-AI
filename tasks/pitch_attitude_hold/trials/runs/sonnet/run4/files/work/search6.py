import numpy as np
from search4 import quick_best_b
from search3 import feasible_margins

if __name__ == "__main__":
    best = None
    for kp in [2.2, 2.3, 2.4, 2.5, 2.6]:
        Kp = -kp
        for ki in [3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5]:
            Ki = -ki
            for kq in [0.05, 0.10, 0.15, 0.20, 0.25]:
                Kq = -kq
                ok, pm, gmi, gmd = feasible_margins(Kp, Ki, Kq, pm_min=46.0, gm_min=6.3)
                if not ok:
                    continue
                res = quick_best_b(Kp, Ki, Kq,
                                    b_list=tuple(np.arange(0.0, 0.81, 0.05)))
                if res is None:
                    continue
                settle, b, os_pct, maxE = res
                if os_pct > 9.0:  # want buffer below the 10% hard cap
                    continue
                print(f"Kp={Kp:.2f} Ki={Ki:.2f} Kq={Kq:.2f} b={b:.2f}  settle={settle:.3f} "
                      f"OS={os_pct:.2f} maxE={maxE:.2f}  PM={pm:.2f} GMinc={gmi:.2f}", flush=True)
                if best is None or settle < best[0]:
                    best = (settle, Kp, Ki, Kq, b, os_pct, maxE, pm, gmi)

    print("\n=== BEST (OS<=9%) ===", flush=True)
    print(best, flush=True)
