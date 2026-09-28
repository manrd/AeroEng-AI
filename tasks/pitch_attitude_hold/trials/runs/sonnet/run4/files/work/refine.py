import numpy as np
from scipy.optimize import minimize
from common import simulate, requirements_from_sim
from search import freq_eval


def penalty(val, min_ok, weight=1.0):
    return weight * max(0.0, (min_ok - val)) ** 2


def penalty_max(val, max_ok, weight=1.0):
    return weight * max(0.0, (val - max_ok)) ** 2


def objective(x, pm_floor=45.5, gm_floor=6.2, overshoot_ceiling=9.7, elevator_ceiling=24.7,
              verbose=False):
    Kp, Ki, Kq, b = x
    if not (0.0 <= b <= 1.0):
        return 1e6 + 1e4 * (abs(b - np.clip(b, 0, 1)))
    fr = freq_eval(Kp, Ki, Kq)
    if fr["worst_pm"] is None:
        return 1e6
    pen = 0.0
    pen += penalty(fr["worst_pm"], pm_floor, weight=2.0)
    if fr["worst_gm_inc"] is not None:
        pen += penalty(fr["worst_gm_inc"], gm_floor, weight=5.0)
    if fr["worst_gm_dec"] is not None:
        pen += penalty(fr["worst_gm_dec"], gm_floor, weight=5.0)

    sim = simulate(Kp, Ki, Kq, b, t_end=20.0)
    req = requirements_from_sim(sim)
    pen += penalty_max(req["overshoot_pct"], overshoot_ceiling, weight=3.0)
    pen += penalty_max(req["max_elevator_deg"], elevator_ceiling, weight=3.0)

    obj = req["settling_time_s"] + 50.0 * pen
    if verbose:
        print(f"x={x}  settle={req['settling_time_s']:.3f} pen={pen:.4f} "
              f"PM={fr['worst_pm']:.2f} GMinc={fr['worst_gm_inc']} GMdec={fr['worst_gm_dec']} "
              f"OS={req['overshoot_pct']:.3f} maxE={req['max_elevator_deg']:.3f} obj={obj:.4f}")
    return obj


def run_refine(x0, maxiter=400, **kwargs):
    res = minimize(lambda x: objective(x, **kwargs), x0, method="Nelder-Mead",
                    options={"maxiter": maxiter, "xatol": 1e-5, "fatol": 1e-6, "adaptive": True})
    return res


if __name__ == "__main__":
    import sys
    x0 = [float(v) for v in sys.argv[1:5]] if len(sys.argv) >= 5 else [-1.2, -0.37, -0.4, 1.0]
    print("start:", x0)
    objective(x0, verbose=True)
    res = run_refine(x0)
    print("result:", res.x, res.fun)
    objective(res.x, verbose=True)
