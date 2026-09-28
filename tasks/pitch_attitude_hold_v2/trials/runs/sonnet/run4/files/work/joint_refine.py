"""Bounded local polish of the joint_search.py result: DE (3416 nonlinear evals, ~60 min) converged to
Kp=-1.694, Ki=-2.495, Kq=-0.156, b=0.454 with worst-of-3 settling 7.9 s at 20 m/s -- overshoot and
elevator margins are fine (6-8%, well under 25 deg) but R5 (<=6.0 s) fails at 20 m/s specifically (the
slowest short period, least control effectiveness, tightest elevator headroom of the three speeds).
Refine locally with bounded Nelder-Mead from that point to see how much further worst-case settling
time can be pushed down while keeping every requirement satisfied with a safety buffer.
"""
import sys
import time
import numpy as np
from scipy.optimize import minimize
import joint_search as js


def report(Kp, Ki, Kq, b):
    js.report(Kp, Ki, Kq, b)


if __name__ == "__main__":
    x0 = [-1.6941580203935067, -2.4950344792152137, -0.15648029859333085, 0.4541193954286484]
    if len(sys.argv) >= 5:
        x0 = [float(v) for v in sys.argv[1:5]]
    print("start:", x0)
    report(*x0)

    bounds = [(-4.0, 0.0), (-4.0, 0.0), (-2.0, 2.0), (0.0, 1.0)]
    t0 = time.time()
    res = minimize(js.full_cost, x0, method="Nelder-Mead", bounds=bounds,
                    options=dict(xatol=1e-5, fatol=1e-6, maxiter=1500, maxfev=1500, adaptive=True))
    print("elapsed", time.time() - t0)
    print(res)
    Kp, Ki, Kq, b = res.x
    print("refined:", Kp, Ki, Kq, b)
    report(Kp, Ki, Kq, b)
