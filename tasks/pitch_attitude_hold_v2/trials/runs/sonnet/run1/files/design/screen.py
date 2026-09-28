"""Fast screening: nonlinear sim truncated to a shorter horizon (settling well under 6s is the goal,
so 9s is ample) to search (kp, ki, kq, b) quickly. Promising candidates get re-checked at the full 20s
horizon before being trusted."""
import sys
import numpy as np
from nlsim import simulate, metrics
import aircraft_model as am

p = am.load_params()


def run_screen(Kp, Ki, Kq, b, n_steps=9000):
    worst_settle = -1.0
    worst_over = -1e9
    worst_elev = -1.0
    any_div = False
    for va in (20, 25, 32):
        out = simulate(Kp, Ki, Kq, b, va, p=p, n_steps=n_steps)
        m = metrics(out)
        worst_settle = max(worst_settle, m["settling_time_s"])
        worst_over = max(worst_over, m["overshoot_pct"])
        worst_elev = max(worst_elev, m["max_elevator_deg"])
        any_div = any_div or m["diverged"]
    return worst_settle, worst_over, worst_elev, any_div


if __name__ == "__main__":
    results = []
    for kp in (1.7, 1.8, 1.9, 2.0, 2.1, 2.2):
        for ki in (3.0, 3.5, 4.0, 4.5, 5.0):
            for b in (0.15, 0.2, 0.25, 0.3, 0.35):
                Kp, Ki, Kq = -kp, -ki, -0.10
                ws, wo, we, div = run_screen(Kp, Ki, Kq, b)
                ok = (not div) and wo <= 10.0 and we <= 25.0 and ws <= 6.0
                results.append((kp, ki, b, ws, wo, we, ok))
                print(f"kp={kp:.2f} ki={ki:.2f} kq=0.10 b={b:.2f}: settle={ws:.3f} over={wo:.2f}% "
                      f"elev={we:.2f} ok={ok}", flush=True)
