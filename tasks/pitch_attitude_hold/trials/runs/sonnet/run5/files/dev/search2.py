import sys
sys.path.insert(0, "dev")
import model as m
import numpy as np

GM_BUF = 6.5
OS_BUF = 9.0
EL_BUF = 23.0


def eval_design(wc, N, pm_target):
    Ti = N / wc
    Kp, Ki, Kq = m.design_from_wc(wc, pm_target, Ti)
    res = m.margins(Kp, Ki, Kq)
    return Kp, Ki, Kq, res


def best_b(Kp, Ki, Kq, os_limit=OS_BUF, el_limit=EL_BUF, iters=24):
    sim0 = m.simulate(Kp, Ki, Kq, b=0.0)
    met0 = m.metrics(sim0)
    if met0["overshoot_pct"] > os_limit or met0["max_elevator_deg"] > el_limit:
        return None
    lo, hi = 0.0, 1.0
    best = (0.0, met0)
    for _ in range(iters):
        bmid = 0.5 * (lo + hi)
        sim = m.simulate(Kp, Ki, Kq, b=bmid)
        met = m.metrics(sim)
        if met["overshoot_pct"] <= os_limit and met["max_elevator_deg"] <= el_limit:
            best = (bmid, met)
            lo = bmid
        else:
            hi = bmid
    return best


def main():
    results = []
    for pm_target in [45.5, 46.0, 46.5]:
        for N in [3, 4, 5, 6, 7, 9]:
            for wc in np.arange(10.6, 12.41, 0.1):
                Kp, Ki, Kq, res = eval_design(wc, N, pm_target)
                if res["pm_deg"] < pm_target - 0.05 or res["n_gain_cross"] != 1:
                    continue
                if res["gm_increase_db"] < GM_BUF or res["gm_decrease_db"] < GM_BUF:
                    continue
                r = best_b(Kp, Ki, Kq)
                if r is None:
                    continue
                b, met = r
                results.append((met["settling_time_s"], pm_target, wc, N, Kp, Ki, Kq, b, met, res))

    results.sort(key=lambda r: r[0])
    print("best 20 by settling time:")
    for ts, pm_target, wc, N, Kp, Ki, Kq, b, met, res in results[:20]:
        print(f"ts={ts:6.3f} pmT={pm_target:5.2f} wc={wc:5.2f} N={N:3d} Kp={Kp:8.4f} Ki={Ki:8.4f} Kq={Kq:8.4f} b={b:6.4f} "
              f"OS%={met['overshoot_pct']:6.2f} maxel={met['max_elevator_deg']:6.2f} "
              f"pm={res['pm_deg']:6.2f} gm_inc={res['gm_increase_db']:6.2f} gm_dec={res['gm_decrease_db']:6.2f}")


if __name__ == "__main__":
    main()
