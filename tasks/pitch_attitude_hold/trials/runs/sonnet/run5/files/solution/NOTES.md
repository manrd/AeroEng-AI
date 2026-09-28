# Pitch attitude hold — method and verification

## 1. Key structural simplification

`theta` is a state and `q = d(theta)/dt` exactly (row 4 of `A` is `[0, 0, 1, 0]`), so in the
Laplace domain `Q(s) = s * Theta(s)` **exactly**, with no approximation. Since the 40 ms delay is
a common, linear, time-invariant block applied to both measurements, delay and differentiation
commute: `q_m(s) = s * theta_m(s)`. Substituting into the given control law,

```
delta_e_cmd(s) = (Kp*b + Ki/s) * theta_cmd(s)  -  (Kp + Ki/s + Kq*s) * theta_m(s)
```

i.e. the fixed structure is **exactly a standard PID controller on theta_m** (P = Kp, I = Ki,
D = Kq) with setpoint weighting b on the proportional term only (the "I-PD"/"PI-D with b"
structure used in autopilot design). This has two useful consequences used throughout:

- The loop broken at the elevator command (R2) is a plain **SISO** transfer function
  `L(s) = Gact(s) * e^(-s*tau) * Gtheta(s) * (Kq*s + Kp + Ki/s)`, with
  `Gtheta(s) = theta(s)/delta_e(s)` read off `plant.json`. No MIMO bookkeeping is needed.
- `b` multiplies only the reference path, never the measurement, so **it does not appear in
  L(s) at all**. Stability and margins (R1, R2) depend only on `(Kp, Ki, Kq)`; `b` is free to
  tune purely for the step-response shape (R3/R5), independently of R1/R2.

## 2. Design method

1. **Loop shaping in the frequency domain.** For a chosen gain-crossover frequency `wc` and
   target phase margin, and a chosen integrator corner `wc/N` (standard practice, N ~ 5).
   `L(jwc) = 1*exp(j*(PM-180))` is one complex equation; with the integrator corner fixing
   `Ki = Kp/(N/wc)`, the remaining complex equation is linear in `(Kp, Kq)` and solved in closed
   form (`dev/model.py:design_from_wc`).
2. **Swept `(wc, N, phase-margin target)`** (`dev/search.py`, `search2.py`, `search3.py`),
   keeping only points with a single gain crossover, phase margin and both gain margins above a
   safety-buffered threshold (comfortably inside R2's 45 deg / 6 dB).
3. **For each surviving `(Kp,Ki,Kq)`, bisected `b` in [0,1]** for the largest value with
   overshoot under a buffered threshold (b=0 gives the least overshoot; overshoot increases
   monotonically with b for this plant, verified numerically), since a larger b speeds up the
   response.
4. Picked the fastest settling candidate with comfortable margins on every requirement
   simultaneously (not just the one with the single lowest settling time — see buffer discussion
   below).

## 3. How every quantity was computed (mirrors "How the grader simulates" exactly)

- **Margins**: `L(jw)` evaluated with the *exact* `e^(-jw*tau)` delay term (no Pade), on the
  grader's exact grid (200001 points, log-spaced, 0.001 to 1000 rad/s). Gain/phase crossovers
  found by vectorized sign-change detection with log-linear interpolation. Phase margin = min
  over *every* gain (0 dB) crossover; gain margin against increase = min over phase (-180 deg mod
  360) crossovers with gain below 0 dB; gain margin against decrease = min over phase crossovers
  with gain above 0 dB (R2's second clause) — none exist for the final design (reported as 999
  internally, not requested in report.json).
- **Time domain**: implemented the discretization verbatim — plant advanced with the *exact*
  zero-order-hold discretization at dt = 1 ms (`scipy.signal.cont2discrete`, `method="zoh"`);
  actuator `dδ/dt = sat_rate((sat_position(δcmd) - δ)/0.05)` integrated with forward Euler using
  the state at the start of the step; controller integral state updated with forward Euler using
  the error at the start of the step; the 40 ms delay as an exact 40-sample shift register (zero
  before t=0). Overshoot = `(peak(theta_deg) - 5)/5*100`. Settling time = last time the trajectory
  is more than 0.1 deg from 5 deg. Elevator command peak = `max|trim_deg + delta_e_cmd_deg|`
  (the controller's raw, pre-actuator output, per R4's literal wording), tracked separately from
  the actual (saturated) surface position.

All of this lives in `dev/model.py` (`margins`, `simulate`, `metrics`).

## 4. Independent cross-checks performed

- **Margins vs. python-control**: built `L(s)` with a 12th-order Pade delay approximation and
  ran `control.stability_margins`. It returned PM = 45.996 deg, GM = 6.324 dB, wp = 11.501 rad/s,
  wg = 17.827 rad/s for a nearby design — matching this project's exact-delay computation to
  ~4 decimal places. This validates the crossover/margin-finding logic independently of this
  project's own implementation.
- **Plant discretization vs. transfer function**: holding a constant 2 deg elevator perturbation
  through the ZOH-discretized state update for 200 s gives a steady-state theta matching
  `Gtheta(0)*delta_e` from the transfer function to 9 significant figures.
- **Closed-loop stability (R1)**: found and fixed a real pitfall here. Building
  `ctrl_fb = (Kp+Ki/s)*Gtheta + Kq*Gq` via python-control's `TransferFunction` addition and then
  taking `feedback()`/`poles()`/`minreal()` gave **inconsistent** answers for the *same* gains
  depending only on the Pade order used for the delay (max closed-loop pole real part flipping
  between about -0.14 and -0.34). Root cause: `Gtheta` and `Gq` share a denominator (since
  `Gq = s*Gtheta` exactly), and python-control's `TransferFunction.__add__` does not reduce by
  the gcd, so it silently reintroduces the open-loop plant's own characteristic polynomial as an
  exact spurious common factor of L's numerator and denominator; `minreal()`'s tolerance-based
  cancellation then catches it on some Pade realizations and not others. This does **not**
  affect the margins computation (evaluating `N(jw)/D(jw)` at a specific point is correct
  regardless of an uncancelled common factor — only root-finding on the raw polynomial is
  corrupted). Fix: build `ctrl_fb(s) = Gtheta(s) * (Kq*s^2 + Kp*s + Ki)/s` as a single polynomial
  ratio (no fraction addition at all), confirmed identical (to 6 decimals) across Pade orders
  6–20, and cross-checked again against a hand-built closed-loop state-space (plant + actuator +
  two independent Pade delay realizations, one per measurement, + integrator state, assembled as
  one numpy matrix with no control-library transfer-function algebra whatsoever). Both give a
  dominant closed-loop pole at **-0.344** (real, critically damped), which also matches the decay
  rate actually observed in the nonlinear time-domain simulation's tail (residual error decays
  by a factor of ~8.9 from t=4s to t=10s, i.e. a rate of ~0.36/s). This is implemented as
  `dev/model.py:closed_loop_max_real_part` and used by `dev/verify_design.py`.
- **Tail behaviour / phugoid**: checked theta out to t=20s for the chosen design; the largest
  deviation from the 5 deg command after t=4s is 0.062 deg, falling to 0.007 deg by t=10s —
  monotonic decay, no late re-excursion through the settling band from the lightly-damped
  open-loop phugoid mode (which the loop in fact pulls to the real -0.344 pole above, not left
  untouched).
- **Settling-time robustness**: recomputed settling time at 1.9%/2.1% bands (0.095/0.105 deg):
  3.592 s / 3.481 s, bracketing the reported 3.536 s — a single, non-tangential crossing, not a
  knife-edge case sensitive to small implementation differences.
- **Sensitivity**: perturbing Kp and Kq by +/-0.01 to 0.02 around the final point moves PM by
  roughly 0.7-0.9 deg and GM by roughly 0.03-0.07 dB — a smooth, well-behaved local landscape,
  not a sharp-edged optimum.

## 5. Final design

```
K_p = -2.6388160739006086
K_i = -6.1220532914494115
K_q = -0.23576487235862442
b   =  0.22559658903020807
```

(Signs: positive elevator is trailing-edge-down/nose-down and `M_delta_e < 0` in `plant.json`, so
a positive pitch-up command needs a *negative* commanded elevator; all three gains work out
negative for this sign convention.)

Computed values (this project's exact replica of the grader's methods; see `report.json`):

| Quantity | Value | Requirement | Margin |
|---|---|---|---|
| Phase margin | 46.60 deg | >= 45 deg, every gain crossover (1 exists) | 1.60 deg |
| Gain margin (against increase) | 6.412 dB | >= 6 dB | 0.412 dB |
| Gain margin (against decrease) | none exists (999) | >= 6 dB where applicable | n/a |
| Overshoot | 9.30 % | <= 10 % (5.5 deg) | 0.70 pp |
| Settling time (2%) | 3.536 s | <= 4.0 s (optimization target: minimize) | 0.464 s |
| Peak |elevator command| | 12.32 deg | <= 25 deg | 12.68 deg |
| Max closed-loop pole real part | -0.344 | < 0 (R1) | stable |

The elevator command never comes close to its limit (12.3 of 25 deg), so the actuator's position
and rate saturation are never active for this step, and the lack of anti-windup logic mentioned
in the README never becomes relevant for this scenario.

## 6. Why not push settling time even lower

A broader search (`dev/search.py`) found designs down to ~3.4-3.5 s settling time, but only by
sitting within a few hundredths of a dB/degree of the R2 thresholds. The chosen design gives up
about 0.05-0.1 s of settling time (an ~2% difference, still far under the 4.0 s requirement)
in exchange for phase margin, gain margin and overshoot buffers close to half of the *grading
tolerances themselves* (1.5 deg / 0.5 dB / 1.0 pp), on top of the fact that this project's
methods already replicate the grader's exact formulas (verified independently, see above). Going
further outside this family (e.g. crossovers above ~13 rad/s, near the short-period/actuator
resonance) produces multiple gain crossovers and a materially harder margin case for no further
speed benefit (verified in `dev/search.py`'s wc=13-16 rows).

## 7. Assumptions (README does not spell these out explicitly)

- **Forward Euler update order**: at each 1 ms step k, the controller/actuator/integrator use
  the values already known at the *start* of the step (delayed measurements from step k-40,
  actuator position delta[k], integral state I[k]) to compute delta_cmd[k]; the plant is then
  advanced with delta[k] held constant over the step (exact ZOH, matching "zero order hold on the
  surface deflection"); the actuator and integrator states are advanced to k+1 using values from
  step k (explicit/forward Euler by definition). This is the only reading consistent with "the
  plant is discretized exactly, with a zero order hold on the surface deflection" alongside
  "forward Euler" for the two nonlinear/integrator states.
- **R4's "elevator command"** is read literally as the controller's raw output before the
  actuator (trim + delta_e_cmd), which is also what `max_elevator_deg` in `report.json` reports;
  the actual (post-actuator) surface position is tracked too (`max_elevator_actual_deg` in the
  dev tooling) and is even smaller (11.90 deg), so this reading is not load-bearing for pass/fail
  here either way.
- **Overshoot sign convention**: `overshoot_pct = (peak(theta) - 5)/5*100`, which would be
  negative if the response never reached the command; not the case for this design.
- Both JSON deliverables use full double-precision values for the gains (controller.json) and
  4-decimal rounding for the reported metrics (report.json), well inside every stated tolerance.

## 8. Tools

All development/exploration scripts are in `dev/` (not part of the deliverable): `model.py`
(shared plant/loop/simulation/margin code, reused by everything else), `search.py`/`search2.py`/
`search3.py` (the gain search at progressively refined buffer levels), `verify_design.py`
(prints a full R1-R5 compliance report for any given gains, used to check the final design), and
`build_solution.py` (writes `solution/controller.json` and `solution/report.json` from the chosen
gains).
