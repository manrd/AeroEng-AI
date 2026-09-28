import sys
import numpy as np
from nlsim import simulate, metrics
import aircraft_model as am

p = am.load_params()


def run(Kp, Ki, Kq, b, verbose=True):
    rows = {}
    worst_settle = -1
    ok = True
    for va in (20, 25, 32):
        out = simulate(Kp, Ki, Kq, b, va, p=p)
        m = metrics(out)
        rows[va] = m
        if verbose:
            print(f"  va={va}: overshoot={m['overshoot_pct']:+.2f}%  settle={m['settling_time_s']:.3f}s  "
                  f"max_elev={m['max_elevator_deg']:.2f}deg  diverged={m['diverged']}")
        worst_settle = max(worst_settle, m["settling_time_s"])
        if m["diverged"] or m["overshoot_pct"] > 10.0 or m["max_elevator_deg"] > 25.0 or m["settling_time_s"] > 6.0:
            ok = False
    if verbose:
        print(f"  worst settle={worst_settle:.3f}s   ALL R1,R3,R4,R5 OK={ok}")
    return rows, worst_settle, ok


if __name__ == "__main__":
    cases = [
        (-2.0, -1.0, -0.1, 1.0),
        (-2.0, -1.0, -0.1, 0.5),
        (-2.0, -1.0, -0.1, 0.3),
        (-2.0, -4.0, -0.15, 0.3),
        (-1.9, -4.0, -0.08, 0.3),
    ]
    for Kp, Ki, Kq, b in cases:
        print(f"Kp={Kp} Ki={Ki} Kq={Kq} b={b}")
        run(Kp, Ki, Kq, b)
        print()
