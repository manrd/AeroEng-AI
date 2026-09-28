# Pitch attitude hold across the speed range

This file is the task exactly as the agent receives it. It is complete on its own: nothing outside this file and
the `environment/` folder is needed to solve it.

## Context

A small fixed wing UAV (the Aerosonde model: 11 kg, 2.9 m wing span) flies wings level at constant altitude, anywhere
from 20 to 32 m/s, with the throttle fixed at the trim setting for its speed. Design the pitch attitude hold loop of
its autopilot: the loop that makes the pitch attitude follow a commanded value. **The autopilot uses one set of gains
at every speed**: there is no gain scheduling.

## What you are given

`environment/`:
- `aircraft_model.py` and `aircraft_aerosonde.json`: the nonlinear longitudinal model of the aircraft (equations of
  motion, trim and linearization) and its parameters. **The grader's time domain truth model is this nonlinear
  model.**
- `plant_20.json`, `plant_25.json` and `plant_32.json`: the model trimmed in wings level, constant altitude flight at
  20, 25 and 32 m/s, and linearized there:
  - `A`, `B`, `C`, `D`: `dx/dt = A x + B δe`, `y = C x`, as perturbations from trim. States: `u`, `w` (body axis
    velocities, m/s), `q` (pitch rate, rad/s), `θ` (pitch attitude, rad). Input: `δe`, the elevator deflection (rad).
    Outputs: `θ` and `q`.
  - `trim`: the trim values, including the full trim state `[u, w, q, θ]` and the throttle.

  | Airspeed | Angle of attack | Trim elevator | Throttle |
  |---|---|---|---|
  | 20 m/s | 5.85 deg | 15.41 deg trailing edge up (`δe = -0.2690` rad) | 0.629 |
  | 25 m/s | 2.85 deg | 7.10 deg trailing edge up (`δe = -0.1239` rad) | 0.774 |
  | 32 m/s | 0.76 deg | 1.33 deg trailing edge up (`δe = -0.0232` rad) | 0.986 |

Python 3.12 with numpy 2.5.2, scipy 1.18.0, python-control 0.10.2 and matplotlib 3.11.1 is installed. No internet
access is needed.

## The loop

**Sign convention.** Positive elevator is trailing edge down, and it pitches the nose down.

**Elevator actuator.**
- First order lag with a time constant of 0.05 s.
- Rate limit: the surface moves at most 60 deg/s.
- Position limit: the absolute deflection (trim plus perturbation) stays within ±25 deg. The trim deflection depends
  on the airspeed, so the room left for the controller does too.

**Sensors.** Pitch attitude and pitch rate, without noise, both delayed by 40 ms (sensing, filtering and
computation).

**Controller.** The structure is fixed; you choose four parameters, the same at every airspeed:

```
δe_cmd(t) = K_p (b θ_cmd - θ_m(t)) + K_i ∫[0,t] (θ_cmd - θ_m) dt - K_q q_m(t)
```

- All signals are perturbations from the trim of the airspeed being flown, in rad, rad/s and s. `θ_m` and `q_m` are
  the delayed measurements.
- `K_p`, `K_i` and `K_q` may be any real numbers; `b` (the setpoint weight) must be between 0 and 1.
- The integrator starts at zero. There is no anti windup logic.

## Scenario

At each of the three airspeeds separately: the aircraft starts at trim (the trim state and throttle in that
airspeed's `plant_*.json`), and at t = 0 the command `θ_cmd` steps from 0 to +5 deg (a perturbation from trim).
Simulate 20 s.

## Requirements

Every requirement must hold at all three airspeeds.

| # | Requirement |
|---|---|
| R1 | The closed loop is stable: on the linear model of each airspeed, and the nonlinear run does not diverge. |
| R2 | On the linear model of each airspeed, break the loop at the elevator command (between the controller and the actuator), with the actuator lag and the exact 40 ms delay included. Gain margin at least 6 dB against a gain increase, and also against a gain decrease wherever the phase crosses `-180` deg with a loop gain above 1. Phase margin at least 45 deg at every gain crossover. |
| R3 | Overshoot at most 10% of the step on the nonlinear run: the pitch attitude never exceeds trim plus 5.5 deg. |
| R4 | On the nonlinear run, the absolute elevator command (that airspeed's trim plus the controller output) stays within ±25 deg for the whole 20 s. |
| R5 | 2% settling time at most 6.0 s on the nonlinear run: the last time within the 20 s at which the pitch attitude is more than 0.1 deg away from the command. |

**Optimization target:** make the worst of the three settling times as short as you can. R5 is the pass threshold;
the grader also reports the worst value.

## How the grader evaluates

The grader recomputes everything from your gains.

**Frequency domain (R1 and R2),** on each `plant_*.json`: the exact frequency response, with `e^(-sτ)` for the delay,
on 200001 frequencies spaced logarithmically from 0.001 to 1000 rad/s. Closed loop stability is checked on the same
linear models.

**Time domain (R1, R3 to R5),** on the nonlinear model, at each airspeed:
- the equations of `aircraft_model.derivatives`, with the throttle fixed at trim (the grader uses an equivalent
  implementation that agrees with it to rounding error);
- fourth order Runge-Kutta with a fixed 1 ms step, the surface deflection held constant over each step;
- the actuator: `dδ/dt = sat_rate((sat_position(δ_cmd) - δ) / 0.05)`, integrated with forward Euler; the surface
  deflection is also held within the position limits;
- the delay: exactly 40 time steps; measurements before t = 0 are zero; `θ_m` is the pitch attitude minus its trim
  value;
- the controller integrator: forward Euler;
- a run counts as diverged if the pitch attitude moves more than 1.5 rad from trim or the airspeed leaves the range
  5 to 60 m/s.

Reasonable variations, such as a variable step integrator, agree with these numbers within the claim tolerances
below. Where they differ, the grader's numbers count.

## Deliverables

Put these in `solution/`:
1. `controller.json`: `{"K_p": ..., "K_i": ..., "K_q": ..., "b": ...}`
2. `report.json`: the values you computed yourself, one entry per airspeed, keyed `"20"`, `"25"` and `"32"`. Each
   entry holds:
   - `phase_margin_deg`
   - `gain_margin_db`: the margin against a gain increase
   - `overshoot_pct`: percent of the step
   - `settling_time_s`
   - `max_elevator_deg`: the peak absolute elevator command, in degrees

   Write 999 for an infinite margin.
3. `NOTES.md`: a short account of your method and of how you checked the result.

## Grading

The solution passes only if all of these hold:
- both JSON files are valid, with finite numbers;
- R1 to R5 at all three airspeeds;
- every value in `report.json` agrees with the grader's recomputed value within these tolerances:
  - phase margin: 1.5 deg;
  - gain margin: 0.5 dB;
  - overshoot: 1.0 percentage point;
  - peak elevator command: 0.5 deg;
  - settling time: within 0.05 s of the range the grader gets with settling bands of 1.9% and 2.1%.
