import sys
sys.path.insert(0, "<run>/work")
import numpy as np
from lib import PLANTS, SPEEDS, loop_response, simulate, metrics_from_sim
from margins_fast import analyze_margins

W_SMALL = np.logspace(-3, 3, 4001)


def evaluate(Kp, Ki, Kq, b, verbose=True, w=W_SMALL, do_sim=True):
    results = {}
    worst_settle = -1
    ok = True
    for spd in SPEEDS:
        pl = PLANTS[spd]
        L = loop_response(pl, w, Kp, Ki, Kq)
        m = analyze_margins(w, L)
        row = {
            "pm": m["worst_pm_deg"],
            "gm_inc": m["gm_against_increase_db"],
            "gm_dec_ok": m["gm_against_decrease_ok"],
            "gm_dec_worst": m["gm_against_decrease_worst_db"],
        }
        if do_sim:
            sim = simulate(spd, Kp, Ki, Kq, b)
            met = metrics_from_sim(sim)
            row.update(met)
            worst_settle = max(worst_settle, met["settling_time_s"])
            if met["diverged"] or met["overshoot_pct"] > 10.0 or met["max_elevator_deg"] > 25.0 or met["settling_time_s"] > 6.0:
                ok = False
        if row["pm"] < 45.0 or row["gm_inc"] < 6.0 or not row["gm_dec_ok"]:
            ok = False
        results[spd] = row
        if verbose:
            extra = ""
            if do_sim:
                extra = (f" | overshoot={row['overshoot_pct']:.2f}% settle={row['settling_time_s']:.3f}s "
                         f"max_elev={row['max_elevator_deg']:.3f}deg diverged={row['diverged']}")
            print(f"  {spd} m/s: PM={row['pm']:.2f}deg GMinc={row['gm_inc']:.2f}dB "
                  f"GMdec_ok={row['gm_dec_ok']}(worst={row['gm_dec_worst']:.2f}dB){extra}")
    if verbose:
        print(f"  worst settle={worst_settle:.3f}s  ALL_OK={ok}")
    return results, ok, worst_settle


if __name__ == "__main__":
    Kp, Ki, Kq, b = -3.0, -1.0, -1.0, 0.5
    print(f"Kp={Kp} Ki={Ki} Kq={Kq} b={b}")
    evaluate(Kp, Ki, Kq, b)
