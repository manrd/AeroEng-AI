import numpy as np
from scipy.optimize import minimize
import freq as fq
import nlsim

SPEEDS = (20, 25, 32)
PLANTS_FQ = {s: fq.load_plant(s) for s in SPEEDS}
TFS = {s: fq.theta_tf(PLANTS_FQ[s]) for s in SPEEDS}
PLANTS_NL = {s: nlsim.load_plant(s) for s in SPEEDS}
PARAMS = nlsim.load_params()

# safety-buffered targets (hard requirement in parens)
PM_TARGET = 50.0   # (45)
GM_TARGET = 6.6     # (6.0)
OS_TARGET = 9.5     # (10.0)
ELEV_TARGET = 24.0  # (25.0)
SETTLE_TARGET = 6.0 # (6.0) no buffer needed here, it's the objective itself


def cost(x, t_end=10.0):
    Kp, Ki, Kq = x
    b = 0.0
    penalty = 0.0
    worst_settle = 0.0
    for s in SPEEDS:
        num, den = TFS[s]
        fr = fq.evaluate(PLANTS_FQ[s], Kp, Ki, Kq, b, num=num, den=den, w=fq.W_GRID_FAST)
        pm, gm = fr["phase_margin_deg"], fr["gain_margin_db"]
        penalty += max(0.0, PM_TARGET - pm) ** 2 * 2.0
        penalty += max(0.0, GM_TARGET - gm) ** 2 * 10.0
        if not fr["decrease_margin_ok"]:
            penalty += 1e4
        gains = {"K_p": Kp, "K_i": Ki, "K_q": Kq, "b": b}
        tr = nlsim.run_nonlinear(PLANTS_NL[s], gains, t_end=t_end, params=PARAMS)
        if tr["diverged"]:
            penalty += 1e5
        penalty += max(0.0, tr["overshoot_pct"] - OS_TARGET) ** 2 * 3.0
        penalty += max(0.0, tr["max_elevator_deg"] - ELEV_TARGET) ** 2 * 2.0
        worst_settle = max(worst_settle, tr["settling_time_s"])
    return worst_settle + penalty


if __name__ == "__main__":
    x0 = [-2.05, -4.40, -0.12]
    print("x0 cost:", cost(x0))
    res = minimize(cost, x0, method="Nelder-Mead",
                    options={"maxiter": 300, "maxfev": 300, "xatol": 1e-4, "fatol": 1e-6,
                             "adaptive": True, "initial_simplex": np.array([
                                 x0,
                                 [x0[0]*1.05, x0[1], x0[2]],
                                 [x0[0], x0[1]*1.05, x0[2]],
                                 [x0[0], x0[1], x0[2]*1.2],
                             ])})
    print(res)
    print("final:", res.x, "cost:", res.fun)
