import sys
sys.path.insert(0, "dev")
import model as m
import numpy as np

PM_BUF = 46.0      # target phase margin (deg), a bit above the 45 deg minimum for safety
GM_BUF = 6.3        # target min gain margin (dB), a bit above the 6 dB minimum
OS_BUF = 9.3         # target max overshoot (%), a bit below the 10% requirement
EL_BUF = 24.3        # target max elevator (deg), a bit below the 25 deg requirement


def eval_design(wc, N, pm_target=PM_BUF):
    Ti = N / wc
    Kp, Ki, Kq = m.design_from_wc(wc, pm_target, Ti)
    res = m.margins(Kp, Ki, Kq)
    return Kp, Ki, Kq, res


def best_b(Kp, Ki, Kq, os_limit=OS_BUF, el_limit=EL_BUF):
    """Find the largest b in [0,1] with overshoot <= os_limit (assumes OS increasing in b,
    as observed); returns (b, metrics) or None if even b=0 violates constraints."""
    sim0 = m.simulate(Kp, Ki, Kq, b=0.0)
    met0 = m.metrics(sim0)
    if met0["overshoot_pct"] > os_limit or met0["max_elevator_deg"] > el_limit:
        return None
    lo, hi = 0.0, 1.0
    best = (0.0, met0)
    for _ in range(40):
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
    for N in [3, 5, 8, 12]:
        for wc in np.arange(6.0, 13.01, 0.25):
            Kp, Ki, Kq, res = eval_design(wc, N)
            if res["pm_deg"] < PM_BUF - 0.05 or res["n_gain_cross"] != 1:
                continue
            if res["gm_increase_db"] < GM_BUF or res["gm_decrease_db"] < GM_BUF:
                continue
            r = best_b(Kp, Ki, Kq)
            if r is None:
                continue
            b, met = r
            results.append((met["settling_time_s"], wc, N, Kp, Ki, Kq, b, met, res))

    results.sort(key=lambda r: r[0])
    print("best 15 by settling time:")
    for ts, wc, N, Kp, Ki, Kq, b, met, res in results[:15]:
        print(f"ts={ts:6.3f} wc={wc:5.2f} N={N:3d} Kp={Kp:8.4f} Ki={Ki:8.4f} Kq={Kq:8.4f} b={b:5.3f} "
              f"OS%={met['overshoot_pct']:6.2f} maxel={met['max_elevator_deg']:6.2f} "
              f"pm={res['pm_deg']:6.2f} gm_inc={res['gm_increase_db']:6.2f} gm_dec={res['gm_decrease_db']:6.2f}")


if __name__ == "__main__":
    main()
