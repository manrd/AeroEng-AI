"""Check sensitivity of the nonlinear-sim metrics to a plausible alternate implementation
ordering: use the actuator position AFTER this step's update (delta_next) as the constant
elevator value fed through the plant's RK4 stages, instead of the position BEFORE update
(delta) as lib.simulate() does. This brackets the "reasonable variations" the task says
should agree within tolerance, and lets us see how much our margins would need to absorb.
"""
import sys
sys.path.insert(0, "<run>/work")
import numpy as np
from lib import PLANTS, SPEEDS, TAU_ACT, RATE_LIMIT, POS_LIMIT, DELAY_STEPS, DT, _PARAMS
import aircraft_model as am
from lib import rk4_step


def simulate_alt(speed, Kp, Ki, Kq, b, T=20.0, theta_cmd_deg=5.0, dt=DT):
    plant = PLANTS[speed]
    p = _PARAMS
    n = round(T / dt)
    x = plant.x0.copy()
    delta = plant.delta_e0
    theta_cmd = np.radians(theta_cmd_deg)
    integ = 0.0
    theta_pert_buf = np.zeros(n + 1)
    q_buf = np.zeros(n + 1)
    theta_pert_buf[0] = 0.0
    q_buf[0] = x[2]
    t_hist = np.arange(n + 1) * dt
    theta_hist = np.zeros(n + 1)
    theta_hist[0] = x[3]
    max_abs_delta_cmd = abs(delta)
    diverged = False

    def f(xx, dd):
        return am.derivatives(p, xx, [dd, plant.delta_t0])

    for k in range(n):
        idx_delay = k - DELAY_STEPS
        theta_m = theta_pert_buf[idx_delay] if idx_delay >= 0 else 0.0
        q_m = q_buf[idx_delay] if idx_delay >= 0 else 0.0
        error_p = theta_cmd - theta_m
        de_cmd_pert = Kp * (b * theta_cmd - theta_m) + Ki * integ - Kq * q_m
        delta_cmd_abs = plant.delta_e0 + de_cmd_pert
        max_abs_delta_cmd = max(max_abs_delta_cmd, abs(delta_cmd_abs))

        delta_cmd_sat = np.clip(delta_cmd_abs, -POS_LIMIT, POS_LIMIT)
        rate = np.clip((delta_cmd_sat - delta) / TAU_ACT, -RATE_LIMIT, RATE_LIMIT)
        delta_next = np.clip(delta + dt * rate, -POS_LIMIT, POS_LIMIT)

        # ALT: use delta_next (post-update) for this step's plant RK4, instead of delta
        x_next = rk4_step(f, x, delta_next, dt)
        integ = integ + dt * error_p
        x = x_next
        delta = delta_next

        theta_hist[k + 1] = x[3]
        theta_pert_buf[k + 1] = x[3] - plant.theta0
        q_buf[k + 1] = x[2]
        if abs(x[3] - plant.theta0) > 1.5:
            diverged = True

    theta_pert_deg = np.degrees(theta_hist - plant.theta0)
    cmd = theta_cmd_deg
    overshoot_pct = max(0.0, (np.max(theta_pert_deg) - cmd) / cmd * 100.0)
    band = 0.02 * cmd
    err = np.abs(theta_pert_deg - cmd)
    outside = np.where(err > band)[0]
    settling_time_s = t_hist[outside[-1]] if len(outside) else 0.0
    return {
        "overshoot_pct": overshoot_pct,
        "settling_time_s": settling_time_s,
        "max_elevator_deg": np.degrees(max_abs_delta_cmd),
        "diverged": diverged,
    }


from lib import simulate, metrics_from_sim

Kp, Ki, Kq, b = -2.0, -4.15, -0.1, 0.1
print(f"Ordering sensitivity check for Kp={Kp} Ki={Ki} Kq={Kq} b={b}")
for spd in SPEEDS:
    base = metrics_from_sim(simulate(spd, Kp, Ki, Kq, b))
    alt = simulate_alt(spd, Kp, Ki, Kq, b)
    print(f"{spd} m/s:")
    print(f"  base (delta at step start): overshoot={base['overshoot_pct']:.3f}% settle={base['settling_time_s']:.3f}s max_elev={base['max_elevator_deg']:.3f}deg")
    print(f"  alt  (delta at step end):   overshoot={alt['overshoot_pct']:.3f}% settle={alt['settling_time_s']:.3f}s max_elev={alt['max_elevator_deg']:.3f}deg")
    print(f"  deltas: overshoot={alt['overshoot_pct']-base['overshoot_pct']:+.4f}pt  settle={alt['settling_time_s']-base['settling_time_s']:+.4f}s  max_elev={alt['max_elevator_deg']-base['max_elevator_deg']:+.4f}deg")
