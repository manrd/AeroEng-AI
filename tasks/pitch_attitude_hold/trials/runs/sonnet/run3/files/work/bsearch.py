import sys
sys.path.insert(0, "work")
import numpy as np
import core


def best_b(Kp, Ki, Kq, b_grid=None, overshoot_limit=10.0, elevator_limit=25.0):
    """Scan b in [0,1] and return the feasible b with the smallest settling time.

    If none is feasible, return the b with the smallest overshoot (closest to feasible),
    flagged via feasible=False.
    """
    if b_grid is None:
        b_grid = np.linspace(0.0, 1.0, 51)
    rows = []
    for b in b_grid:
        sim = core.simulate(Kp, Ki, Kq, b)
        m = core.metrics_from_sim(sim)
        feas = (m["overshoot_pct"] <= overshoot_limit) and (m["max_elevator_deg"] <= elevator_limit) and (m["settling_time_s"] < 20.0)
        rows.append((b, m["settling_time_s"], m["overshoot_pct"], m["max_elevator_deg"], feas))
    rows_arr = rows
    feas_rows = [r for r in rows_arr if r[4]]
    if feas_rows:
        best = min(feas_rows, key=lambda r: r[1])
        return {"b": best[0], "settling_time_s": best[1], "overshoot_pct": best[2],
                "max_elevator_deg": best[3], "feasible": True, "rows": rows_arr}
    else:
        best = min(rows_arr, key=lambda r: r[2])
        return {"b": best[0], "settling_time_s": best[1], "overshoot_pct": best[2],
                "max_elevator_deg": best[3], "feasible": False, "rows": rows_arr}


if __name__ == "__main__":
    from loopshape import design_at_crossover
    num_theta, den_theta = core.theta_tf()

    print(f"{'wc':>5} {'N':>3} {'pmT':>4} | {'PM':>6} {'GMi':>6} {'GMd':>6} | {'b*':>5} {'settle':>7} {'OS%':>6} {'maxE':>6} feas")
    for wc in [9, 10, 11, 12, 13, 14, 15, 16]:
        for N in [10, 15]:
            for pmT in [45.0, 48.0, 50.0]:
                kp, ki, kq = design_at_crossover(wc, N, pm_target_deg=pmT)
                if kp <= 0:
                    continue
                Kp, Ki, Kq = -kp, -ki, -kq
                res = core.compute_margins(Kp, Ki, Kq, num_theta, den_theta, n=20001)
                if res["phase_margin_deg"] < 44.9 or res["gain_margin_incr_db"] < 5.9:
                    tag = "  (margin fail, skip fine b-search)"
                    print(f"{wc:5.1f} {N:3d} {pmT:4.0f} | {res['phase_margin_deg']:6.2f} {res['gain_margin_incr_db']:6.2f} {res['gain_margin_decr_db']:6.1f} |" + tag)
                    continue
                r = best_b(Kp, Ki, Kq, b_grid=np.linspace(0, 1, 26))
                print(f"{wc:5.1f} {N:3d} {pmT:4.0f} | {res['phase_margin_deg']:6.2f} {res['gain_margin_incr_db']:6.2f} {res['gain_margin_decr_db']:6.1f} | "
                      f"{r['b']:5.2f} {r['settling_time_s']:7.3f} {r['overshoot_pct']:6.2f} {r['max_elevator_deg']:6.2f} {r['feasible']}")
