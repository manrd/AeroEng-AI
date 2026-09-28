# Method

## 1. Reformulating the loop

In the linear model, `theta` is a state and its own row of `A` is exactly `[0, 0, 1, 0]`: `dtheta/dt = q`
identically, with no other term. So `q` is exactly the derivative of `theta`, and since the sensor
delay is a pure time shift, `q_m(t) = d(theta_m)/dt` exactly as well. That means the **loop gain**
(controller output over controller output, reference set to zero, used for R2) collapses to a plain
series compensator:

```
L(s) = e^(-s*0.04) * Act(s) * [ K_p + K_i/s + K_q*s ] * G_theta(s)
Act(s) = 1/(1 + 0.05 s)                          (elevator actuator lag)
G_theta(s) = theta(s)/delta_e(s)                  (from each plant_*.json's A, B, C)
```

`b` does **not** appear in `L(s)` — it only weights the reference path — so R2 (margins) can be
designed from `K_p, K_i, K_q` alone, and `b` tuned afterwards purely for the time-domain shape
(overshoot vs. settling, and critically, staying inside the elevator budget below).

**Sign convention.** Positive elevator pitches nose down, and `theta(s)/delta_e(s)` has a negative DC
gain at every airspeed (confirmed numerically). To pitch nose-up (the commanded +5 deg step) the
controller has to drive the elevator negative, so a correctly stabilizing controller needs `K_p, K_i,
K_q` all **negative** (verified numerically, not just assumed — a positive-gain search was tried first
and gives nonsense margins).

## 2. The elevator budget is the real constraint, not just R2

Solving the linear equilibrium (`q=0`, `theta = trim+5 deg`, throttle fixed at trim) for the elevator
perturbation the aircraft needs in the *new* steady state gives, before any controller dynamics are even
involved:

| Airspeed | Steady-state elevator perturbation needed | Room to the +-25 deg absolute stop |
|---|---|---|
| 20 m/s | -5.43 deg | 9.59 deg (trim already at -15.41 deg) |
| 25 m/s | -2.82 deg | 17.90 deg |
| 32 m/s | -1.21 deg | 23.67 deg |

At 20 m/s the steady requirement alone eats 57% of the only 9.59 deg of headroom left before the
position limit — and 20 m/s also has the smallest elevator effectiveness (`B` row for `q` is -23 at 20
m/s vs -59 at 32 m/s). 20 m/s is therefore the binding case for R4 and for settling time throughout the
search (it is also, empirically, the binding case for R3 in the final design).

## 3. Design process

1. **Linear loop-shaping.** Computed the exact frequency response of each plant by eigendecomposing
   `A` once and evaluating `C(jwI-A)^-1 B` over the whole array (vectorized; cross-checked against
   `python-control`'s own `frequency_response` to ~1e-14 absolute error, and about 100x faster than
   calling the library directly at 200001 points). Swept `(K_p, K_i, K_q)` on a grid, keeping only
   points with >=6 dB gain margin and >=45 deg phase margin at **every** crossing (not just the
   nearest one) simultaneously at all three airspeeds. The feasible region tops out around
   `|K_p| ~ 2.0-2.2` for this airframe/actuator/delay combination; within it, larger `|K_i|` buys a
   higher gain-crossover frequency (potentially faster response).
2. **Nonlinear check drove the final choice.** Margins alone don't set `K_i`: pushing `|K_i|` past
   about 5 (even where margins still allow it) blows the R3 overshoot budget on the nonlinear model
   well before it helps R5, and at `K_i=10` the *unsaturated* elevator command was already exceeding
   25 deg at 20 m/s. So `K_i` was chosen empirically against the exact nonlinear simulation (RK4 1 ms,
   actuator rate/position limits, 40-step delay, forward-Euler integrator — implemented exactly as the
   grader's spec describes), not from margins alone. `K_p` and `K_i` trade off together: for fixed
   `K_i`, a larger `K_p` *reduces* overshoot but *slows* settling, so the search moved both together,
   then `K_q` and `b` were swept finely to squeeze out the last bit of settling time while keeping
   comfortable buffers on R2, R3 and R4 at all three airspeeds.
3. **Final gains:** `K_p = -2.10`, `K_i = -4.50`, `K_q = -0.12`, `b = 0.20`.

## 4. Verification

- **R2 (margins):** exact frequency response (no Pade/delay approximation — `e^{-s*0.04}` multiplied in
  directly at each frequency) on the same grid the grader specifies: 200001 points, log-spaced, 0.001 to
  1000 rad/s. `python-control`'s own `stability_margins(..., returnall=True)` is correct but far too slow
  at this resolution (its generic "distance to -1" local-minima search calls
  `scipy.optimize.minimize_scalar` for every float-level wiggle in a 200001-point array — tens of minutes,
  observed directly). Re-implemented just the two crossing types R2 actually asks about (phase crossings
  at -180 deg for gain margin, magnitude-1 crossings for phase margin) with linear interpolation between
  adjacent grid points instead of a smoothing spline; cross-checked against `control.stability_margins`
  on coarser grids where the library is fast enough to run, agreement is within about 0.01 dB / 0.01 deg
  (see `design/verify_margins.py`). Every phase crossing and every gain crossing in the whole band was
  checked (R2's wording explicitly allows for more than one of each), not just the nearest one.
- **R1 (linear stability):** the open-loop plant+actuator has no unstable poles at any airspeed (checked
  directly), and the delay is a stable (all-pass) element, so healthy margins at every crossing across the
  whole tested band imply a stable closed loop by the standard Nyquist argument. As an independent,
  more literal cross-check, I also built the full closed-loop state space with the 40 ms delay
  represented by a 12th-order Pade approximant (accurate to a fraction of a degree of phase out to several
  hundred rad/s, far past this loop's ~4-5 rad/s crossover) and confirmed every closed-loop eigenvalue has
  negative real part at all three airspeeds (`design/padecheck.py`).
- **R1 (nonlinear), R3, R4, R5:** simulated exactly as specified — `aircraft_model.derivatives` with RK4
  and a fixed 1 ms step (elevator held constant over each step), the actuator integrated with forward
  Euler and both position and rate limits, the 40-step measurement delay, and the controller integrator
  with forward Euler. Overshoot is `(peak_theta_deg - 5)/5*100`; settling time is the last time inside the
  20 s run at which `|theta - 5 deg| > 0.1 deg` (checked that the response settles cleanly and
  monotonically through the band — the 1.9%/2.0%/2.1% band settling times are 5.65 s / 5.48 s / 5.35 s at
  20 m/s, a smooth spread, not a value hovering on the boundary).

**One assumption**, stated because the spec doesn't pin it down and I had no one to ask: within each 1 ms
step, the elevator actuator's rate-limited forward-Euler update and the RK4 propagation of the rigid-body
state both use the actuator position from the *start* of the step (a zero-order hold over the step), then
the actuator state is advanced for use in the *next* step. This is the standard causal ordering for this
kind of loop, and at a 1 ms step against a 50 ms actuator lag and a 40 ms delay the choice changes almost
nothing: re-running all three airspeeds with the opposite ordering (the *new*, post-update actuator
position used in that same step's RK4 call) moves settling time by at most 0.003 s, overshoot by at most
0.04 percentage points, and peak elevator by at most 0.03 deg — all far inside the grader's own matching
tolerances.

## 5. Final numbers (from `report.json`)

| Airspeed | Phase margin | Gain margin | Overshoot | Settling time | Peak elevator |
|---|---|---|---|---|---|
| 20 m/s | 72.9 deg | 9.18 dB | 8.49 % | **5.48 s** | 21.65 deg |
| 25 m/s | 75.6 deg | 7.95 dB | 9.25 % | 4.29 s | 11.47 deg |
| 32 m/s | 78.2 deg | 6.41 dB | 8.16 % | 2.13 s | 5.21 deg |

Worst of the three settling times (the optimization target): **5.48 s** at 20 m/s, against the 6.0 s pass
threshold. The binding requirements in the final design are R5 at 20 m/s (0.52 s of buffer), R2's gain
margin at 32 m/s (0.41 dB of buffer above the 6 dB floor — the short-period mode moves to higher
frequency as airspeed increases, which is what makes 32 m/s, not 20 m/s, the tight case for margins even
though 20 m/s is tight for everything else), and R3 at 25 m/s (0.75 percentage points of buffer). No
requirement is closer to its limit than that at any airspeed.

## Files

- `design/aircraft_model.py` is not copied here; the scripts under `design/` import it directly from
  `environment/`.
- `design/loop.py` — fast exact-delay frequency response and margins.
- `design/nlsim.py` — the nonlinear time-domain simulator (RK4/actuator/delay/integrator, per spec).
- `design/padecheck.py` — Pade-delay closed-loop eigenvalue cross-check for R1.
- `design/finalize.py` — builds `controller.json` and `report.json` from a chosen `(K_p,K_i,K_q,b)` and
  checks all five requirements before writing them.
- `design/verify_final.py` — the one-shot full verification run shown above.
- `design/scan.py`, `design/screen.py`, `design/trial.py`, `design/scan2.txt`..`scan4.txt` — the gain
  search (linear margin grid search, then nonlinear screening/confirmation) that led to the final gains.
