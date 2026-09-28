# Pitch attitude hold for a small UAV

This file is the task exactly as the agent receives it. It is complete on its own: nothing outside this file and
the `environment/` folder is needed to solve it.

## Context

A small fixed wing UAV (the Aerosonde model: 11 kg, 2.9 m wing span) flies wings level at constant altitude and
25 m/s, with the throttle fixed at its trim setting. Design the pitch attitude hold loop of its autopilot: the loop
that makes the pitch attitude follow a commanded value.

## What you are given

`environment/`:
- `plant.json`: the longitudinal dynamics linearized about this flight condition, as perturbations from trim:
  `dx/dt = A x + B δe`, `y = C x`.
  - States: `u`, `w` (body axis velocities, m/s), `q` (pitch rate, rad/s), `θ` (pitch attitude, rad).
  - Input: `δe`, the elevator deflection (rad).
  - Outputs: `θ` and `q`.
  - The trim values: angle of attack 2.85 deg, elevator 7.10 deg trailing edge up (`δe = -0.1239` rad), throttle
    0.774.
- `aircraft_model.py` and `aircraft_aerosonde.json`: the nonlinear model and parameters that `plant.json` was
  derived from. They are for reference only; the grader uses `plant.json`.

Python 3.12 with numpy 2.5.2, scipy 1.18.0, python-control 0.10.2 and matplotlib 3.11.1 is installed. No internet
access is needed.

## The loop

**Sign convention.** Positive elevator is trailing edge down, and it pitches the nose down.

**Elevator actuator.**
- First order lag with a time constant of 0.05 s.
- Rate limit: the surface moves at most 60 deg/s.
- Position limit: the absolute deflection (trim plus perturbation) stays within ±25 deg. Because trim is 7.10 deg
  trailing edge up, the perturbation can range from 17.9 deg trailing edge up to 32.1 deg trailing edge down.

**Sensors.** Pitch attitude and pitch rate, without noise, both delayed by 40 ms (sensing, filtering and
computation).

**Controller.** The structure is fixed; you choose the four parameters:

```
δe_cmd(t) = K_p (b θ_cmd - θ_m(t)) + K_i ∫[0,t] (θ_cmd - θ_m) dt - K_q q_m(t)
```

- All signals are perturbations from trim, in rad, rad/s and s. `θ_m` and `q_m` are the delayed measurements.
- `K_p`, `K_i` and `K_q` may be any real numbers; `b` (the setpoint weight) must be between 0 and 1.
- The integrator starts at zero. There is no anti windup logic.

## Scenario

At t = 0 the aircraft is at trim and the command `θ_cmd` steps from 0 to +5 deg (a perturbation from trim).
Simulate 20 s.

## Requirements

| # | Requirement |
|---|---|
| R1 | The closed loop is stable. |
| R2 | Break the loop at the elevator command (between the controller and the actuator), with the actuator lag and the exact 40 ms delay included. Gain margin at least 6 dB against a gain increase, and also against a gain decrease wherever the phase crosses `-180` deg with a loop gain above 1. Phase margin at least 45 deg at every gain crossover. |
| R3 | Overshoot at most 10% of the step: the pitch attitude never exceeds 5.5 deg. |
| R4 | The absolute elevator command (trim plus controller output) stays within ±25 deg for the whole 20 s. |
| R5 | 2% settling time at most 4.0 s: the last time within the 20 s at which the pitch attitude is more than 0.1 deg away from the 5 deg command. |

**Optimization target:** make the 2% settling time as short as you can. R5 is the pass threshold; the grader also
reports the value.

## How the grader simulates

The grader recomputes everything from your gains with its own truth model:
- a fixed time step of 1 ms; the plant is discretized exactly, with a zero order hold on the surface deflection;
- the actuator: `dδ/dt = sat_rate((sat_position(δ_cmd) - δ) / 0.05)`, integrated with forward Euler; the surface
  deflection is also held within the position limits;
- the delay: exactly 40 time steps; measurements before t = 0 are zero;
- the controller integrator: forward Euler;
- margins: the exact frequency response, with `e^(-sτ)` for the delay, on 200001 frequencies spaced
  logarithmically from 0.001 to 1000 rad/s.

Reasonable variations, such as an eighth order Padé approximation of the delay or a variable step integrator, agree
with these numbers within the claim tolerances below. Where they differ, the grader's numbers count.

## Deliverables

Put these in `solution/`:
1. `controller.json`: `{"K_p": ..., "K_i": ..., "K_q": ..., "b": ...}`
2. `report.json`: the values you computed yourself:
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
- R1 to R5;
- every value in `report.json` agrees with the grader's recomputed value within these tolerances:
  - phase margin: 1.5 deg;
  - gain margin: 0.5 dB;
  - overshoot: 1.0 percentage point;
  - peak elevator command: 0.5 deg;
  - settling time: within 0.05 s of the range the grader gets with settling bands of 1.9% and 2.1%.
