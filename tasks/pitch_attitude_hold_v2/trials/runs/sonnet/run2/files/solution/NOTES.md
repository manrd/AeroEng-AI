# Method

## Controller structure and sign convention

The loop is `delta_e_cmd = Kp(b*theta_cmd - theta_m) + Ki*Integral(theta_cmd - theta_m) - Kq*q_m`.
Since positive `delta_e` is trailing-edge-down/nose-down (given), and the plant's B matrix confirms
`dq/dt` from `delta_e` is negative at all three speeds, a positive command step (+5 deg) needs a
*negative* elevator to pitch up. Working through the sign of each term shows `K_p`, `K_i`, `K_q` must
all be negative for correct-sense negative feedback; this was confirmed numerically (positive gains
diverge immediately, wrong direction).

## Loop gain for R2

Breaking the loop at `delta_e_cmd` and setting `theta_cmd = 0` (irrelevant to the feedback path):

    L(s) = e^{-0.04 s} * Gact(s) * [ (Kp + Ki/s) * Ptheta(s) + Kq * Pq(s) ]
    Gact(s) = 1/(0.05 s + 1)
    Ptheta(s) = C_theta (sI-A)^-1 B,  Pq(s) = C_q (sI-A)^-1 B   (from each plant_*.json)

`b` does not appear in `L(s)` -- it only weights the reference path, so it has zero effect on R1/R2 and
was tuned purely against the nonlinear R3/R5 metrics. Also, since `theta_dot = q` exactly in this model,
`Ptheta(s) = Pq(s)/s` exactly, so `L(s) = e^{-0.04s} Gact(s) Pq(s) [Kq + Kp/s + Ki/s^2]`: the loop is
literally a PID acting on the rate channel, with `Ki` entering through a *double* integrator. This is
why pushing `Ki` up (needed for a fast gain-crossover under the margin constraints alone) costs
closed-loop damping/overshoot well before it costs the classical Bode margins -- which is the main
reason R3/R5 had to be optimized directly rather than inferred from R2.

`(sI-A)^-1 B` was evaluated at the required 200001 log-spaced frequencies (0.001 to 1000 rad/s) via the
eigendecomposition of each plant's 4x4 `A` (cached per plant), checked against a direct
`np.linalg.solve` per frequency to ~1e-13, about 2000x faster -- needed to make the search practical.

## Margin scan (R2)

Gain crossovers (`|L|=1`) and phase crossovers (`L` real and negative, i.e. phase = -180 mod 360) were
found by scanning the precomputed `(mag, phase, omega)` arrays for sign changes with linear-interpolation
refinement between the (very closely spaced) grid points, exactly reproducing what
`control.stability_margins(..., returnall=True)` gives when fed the same three arrays (verified point
for point on the real designs below, and on a hand-built synthetic conditionally-stable loop shape to
exercise the "gain margin against a decrease" branch, which none of the real candidate designs actually
triggered -- their loop gain rolls off past the primary crossover and never comes back above 1 before
the next -180 crossing, so that second clause of R2 turned out not to be the binding constraint here).
`control`'s own function was too slow to call directly on the full 2e5-point grid (~100 s/plant, because
of its smoothed-FRD evaluation) so the search used the equivalent, ~1000x faster, direct scan.

Reported `phase_margin_deg` is the minimum phase margin over every gain crossover found;
`gain_margin_db` is the minimum margin-against-increase over every phase crossing where `|L|<1`
(999 if none). All three speeds showed exactly one gain crossover and seven phase crossovers in the
final design (the extra six are all far out past 100 rad/s, at tiny loop gain, from the delay wrapping
phase repeatedly -- harmless).

## R1 (linear stability), independently of the margin scan

As a check that does not share code with the margin scanner: the 40 ms delay was replaced with a
Pade approximant (orders 8/12/16/24) and the closed-loop poles were found as the roots of the
numerator of `1 + L_pade(s)` (a rational transfer function built from state-space `Ptheta`/`Pq` blocks
via `python-control`). Results converge by order 12 and agree at 16/24. For every design tried, the
least-stable closed-loop pole sits almost exactly on the *open-loop phugoid pole* (e.g. -0.1136 rad/s at
20 m/s) -- the theta/q feedback barely touches the (already stable) phugoid, so it is never what limits
stability; the short-period/actuator/delay loop is always the actual constraint, i.e. exactly what R2
is shaping.

## Nonlinear time domain (R1, R3-R5)

Implemented the grader's algorithm literally: RK4 with a fixed 1 ms step and `delta_e` held constant
over the step; the actuator `dδ/dt = sat_rate((sat_position(δ_cmd)-δ)/0.05)` integrated with forward
Euler and the resulting position also clipped; a 40-sample ring buffer for the delay with zero history
before t=0; the controller integrator with forward Euler using the same delayed measurement used that
step; divergence if `|theta-theta_trim|>1.5 rad` or airspeed leaves [5,60] m/s.

For search speed only, a scalar-math (no per-call numpy overhead) reimplementation of
`aircraft_model.derivatives` was used (validated against the real one to ~1e-13 over 20000 random
states; ~7x faster per run). Every number that ends up in `report.json` was recomputed with the real
`aircraft_model.derivatives` through the official (slow) simulator, not the fast one.

`overshoot_pct` = `max(0, peak_theta_pert_deg - 5) / 5 * 100`. `settling_time_s` = the last time the
pitch attitude is more than 0.1 deg (2% of the 5 deg step) from the command, linearly interpolated
between the last "outside the band" sample and the next one. `max_elevator_deg` is the peak of the
absolute *commanded* elevator (trim + controller output), before actuator saturation -- R4 is a
statement about the controller not demanding more than the actuator can give, so the design was kept
comfortably inside 25 deg on the command itself, not just on the actual (saturating) surface position.

## Search strategy and why the margin-only optimum doesn't work

`b` has no effect on margins, so (Kp, Ki, Kq) were first optimized purely against R2: maximize the
worst-case (min over the 3 speeds) gain-crossover frequency subject to phase margin >= 45+buffer deg
and gain margin >= 6+buffer dB at all three speeds (a `differential_evolution` global search and a
local Nelder-Mead polish from an independent grid search converged to the same point, Kp~-1.96,
Ki~-10.2, Kq~-0.13, bandwidth ~5-5.5 rad/s). That point turned out to fail R3/R4 badly (overshoot
24-29%, and the elevator command already at the 25 deg limit at 20 m/s -- even at b=0, i.e. with zero
proportional kick from the reference step). This is the direct consequence of the `Kq + Kp/s + Ki/s^2`
structure above: a high Ki/Kq ratio buys gain-crossover frequency (hence R2 margin) cheaply, but costs
closed-loop damping (hence R3) expensively.

So (Kp, Ki, Kq, b) were then optimized jointly and directly against the true nonlinear objective
(worst-case settling time), penalizing any margin, overshoot, elevator, or divergence violation, using
the fast simulator, seeded from a manual grid mapping of the overshoot/settling-time trade-off at
b=0. The *unconstrained-buffer* optimum sits with two requirements simultaneously active (gain margin
essentially at exactly 6.0 dB and overshoot at exactly 10.0%) at a worst-case settling time around
5.0-5.15 s -- mathematically optimal but with essentially zero robustness margin against any rounding
difference between this recompute and the grader's, so it was not used. Backing off from it along the
same trade-off (a joint re-optimization with an explicit safety buffer, plus a systematic grid over
Kp in [-1.9,-2.3] x Ki in [-4.0,-5.0] x Kq in [-0.12,-0.20], filtered to gain margin >= 6.4 dB and
overshoot <= 9.5%, then a b sweep on the best grid point) gave the reported design, which keeps gain
margin and overshoot comfortably (0.4 dB and 0.37-0.6 percentage points respectively) clear of their
pass/fail floors at every speed while still settling in 5.39 s worst case, 0.6 s inside the 6.0 s
requirement.

# Final gains and where each requirement binds

`K_p = -2.10`, `K_i = -4.60`, `K_q = -0.13`, `b = 0.15` (`solution/controller.json`).

| Airspeed | phase margin (deg) | gain margin (dB) | overshoot (%) | settling time (s) | max elevator cmd (deg) |
|---|---|---|---|---|---|
| 20 m/s | 73.05 | 9.55 | 8.96 | 5.389 | 21.65 |
| 25 m/s | 75.92 | 8.13 | 9.63 | 4.259 | 11.34 |
| 32 m/s | 78.81 | 6.41 | 8.64 | 3.057 | 5.15  |

Worst-case (optimization target) settling time: 5.389 s at 20 m/s, against the 6.0 s pass threshold.
Decrease-margin (against a gain decrease at a `|L|>1` phase crossing) is 999 (no such crossing) at
every speed. Every speed shows exactly 1 gain crossover and 7 phase crossovers (the extra 6 are all
past 100 rad/s at negligible loop gain, from the delay winding phase around repeatedly -- harmless).

20 m/s is the tightest speed throughout: it has the least control effectiveness (B_q=-23 vs -59 at
32 m/s) so it needs the largest elevator swing and settles slowest; 32 m/s has the least gain-margin
headroom (largest loop gain for the same controller gains). Phase margin and the elevator-command limit
were never close to binding for the final design (comfortable at 74+ deg and well under 25 deg at every
speed); the two requirements that actually shaped the final choice were the 32 m/s gain margin and the
25 m/s overshoot.

# How this was checked

- The fast frequency-response evaluation was cross-checked against a direct `np.linalg.solve`-based
  implementation (agreement ~1e-13) and against `control.stability_margins(..., returnall=True)` fed
  the identical `(mag, phase, omega)` data (agreement to the digits printed) on real designs, plus a
  hand-built synthetic conditionally-stable loop shape to exercise the branch none of the real designs
  hit.
- `s * Ptheta(s) = Pq(s)` was checked to hold numerically (it must, since `theta_dot = q` exactly in
  this model) as an independent sanity check of the frequency-response code.
- R1 (linear) was checked two independent ways: via the margin scan's crossing pattern (no crossing
  ever showed the loop needing a "decrease" margin, i.e. no encirclement-flip risk) and via the
  Pade-approximant closed-loop pole computation described above, both agreeing the design is stable
  with the phugoid, not the shaped loop, as the least-stable mode. Re-run on the final gains: max real
  part of any closed-loop pole is -0.1136 (20 m/s) / -0.1426 (25 m/s) / -0.1819 (32 m/s), all the
  open-loop phugoid pole, converged from Pade order 12 through 24.
- The fast scalar-math nonlinear simulator was checked against the official `aircraft_model.derivatives`
  -based simulator on the chosen design (and others along the way); they agree to within floating-point
  noise. `report.json`'s numbers were produced by the official (slow) path only.
- The final `controller.json` was re-run end to end (frequency response + nonlinear simulation) after
  being written, reproducing exactly the numbers in `report.json`, and all of R1-R5 pass at all three
  airspeeds.

# Assumptions

- `K_p`, `K_i`, `K_q` are all negative given the stated sign convention (positive elevator = nose down);
  this was derived analytically and confirmed numerically, and the whole search was restricted to that
  sign region.
- `max_elevator_deg` (R4 / report.json) is the peak of the *commanded* elevator angle (trim plus
  controller output, before actuator rate/position saturation), matching "the absolute elevator command
  ... stays within +-25 deg" in R4's wording, not the post-saturation actuator position (which is
  trivially within the limits by construction).
- `theta_m` and `q_m` are both delayed by the same 40 samples, with zero history before t=0, as stated;
  `q`'s trim value is 0 at every speed (confirmed from each `plant_*.json`), so no trim subtraction was
  needed for `q_m`.
- No margin/report value came out infinite in the final design, so the "write 999" convention was
  exercised only in the search tooling's synthetic test, not in the delivered `report.json`.
