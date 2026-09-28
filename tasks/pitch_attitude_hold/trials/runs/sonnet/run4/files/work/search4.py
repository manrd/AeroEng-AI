import numpy as np
from common import simulate, requirements_from_sim
from search3 import feasible_margins

results = []


def quick_best_b(Kp, Ki, Kq, b_list=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0)):
    best = None
    for b in b_list:
        sim = simulate(Kp, Ki, Kq, b, t_end=20.0)
        req = requirements_from_sim(sim)
        ok = (req["overshoot_pct"] <= 10.0) and (req["max_elevator_deg"] <= 25.0)
        if ok and (best is None or req["settling_time_s"] < best[0]):
            best = (req["settling_time_s"], b, req["overshoot_pct"], req["max_elevator_deg"])
    return best


if __name__ == "__main__":
    import itertools
    combos = []
    for kq in [0.15, 0.2, 0.25, 0.3, 0.35, 0.4]:
        Kq = -kq
        for kp in [0.5, 1.0, 1.5, 2.0, 3.0, 4.0]:
            Kp = -kp
            for ki in [0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 14.0]:
                Ki = -ki
                ok, pm, gmi, gmd = feasible_margins(Kp, Ki, Kq, pm_min=45.0, gm_min=6.0)
                if not ok:
                    continue
                combos.append((Kp, Ki, Kq, pm, gmi, gmd))
    print(f"feasible combos: {len(combos)}", flush=True)

    best_overall = None
    for Kp, Ki, Kq, pm, gmi, gmd in combos:
        res = quick_best_b(Kp, Ki, Kq)
        if res is None:
            continue
        settle, b, os_pct, maxE = res
        print(f"Kp={Kp:.3f} Ki={Ki:.3f} Kq={Kq:.3f} b={b:.2f}  settle={settle:.3f} "
              f"OS={os_pct:.2f} maxE={maxE:.2f}  PM={pm:.2f} GMinc={gmi}", flush=True)
        if best_overall is None or settle < best_overall[0]:
            best_overall = (settle, Kp, Ki, Kq, b, os_pct, maxE, pm, gmi, gmd)

    print("\n=== BEST ===", flush=True)
    print(best_overall, flush=True)
