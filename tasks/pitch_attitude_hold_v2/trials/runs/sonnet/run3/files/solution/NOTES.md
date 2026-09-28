# Method

## 1. The loop collapses to a single ideal PID on theta

The plant state equation for `theta` is exactly `d(theta)/dt = q` (row 4 of every `A` matrix is
`[0, 0, 1, 0]`, and `B[3] = 0`). A pure time delay commutes with differentiation, so the delayed
rate measurement is exactly the derivative of the delayed attitude measurement:
`q_m(t) = d(theta_m)/dt`. That means the two feedback terms of the controller,

    delta_e_cmd = Kp*(b*theta_cmd - theta_m) + Ki*Integral(theta_cmd - theta_m) - Kq*q_m

are really an ideal PID acting on `theta_m` (P = Kp, I = Ki, D = Kq) plus setpoint weight `b` on
the P branch only. Breaking the loop at the elevator command (as R2 specifies) and writing
`G_theta(s) = theta(s)/delta_e(s)` (from the state space model) gives a loop transfer function

    L(s) = (Kp + Ki/s + Kq*s) * G_theta(s) * G_act(s) * exp(-s*0.04),   G_act(s) = 1/(0.05 s + 1)

with closed-loop characteristic equation `1 + L(s) = 0`. Note `b` never appears in `L(s)`: it only
reshapes the feed-forward path from `theta_cmd`, so it changes the step transient (mostly
overshoot) without touching stability or margins. This was verified directly in code (`b` is
accepted but unused in `loop_gain`).

`G_theta(s)` was extracted from each `plant_*.json` with `scipy.signal.ss2tf` and cross-checked
point-by-point against `control.ss(...).__call__(jw)` (exact agreement to float precision).

## 2. Sign convention

Positive elevator pitches the nose down, and the DC gain `theta(0)/delta_e` computed from
`-C(A^-1)B` is negative at all three trim points (-0.92, -1.78, -4.15 rad/rad for 20/25/32 m/s).
A stabilizing type-1 loop needs `Ki * G_theta(0) > 0`, so `Ki < 0`; the same sign was found to be
required for `Kp` and `Kq` (confirmed both analytically and by scanning: positive `Kq` is
catastrophically unstable, e.g. overshoot > 100% and growing).

## 3. Margins (R1/R2): frequency response, no approximation

`work/freq.py` evaluates `L(jw)` analytically (exact `exp(-jw*0.04)`, no Pade) on the grader's own
grid (200001 points, log-spaced 0.001 to 1000 rad/s). Gain crossovers (`|L|=1`) and negative-real-axis
crossings (`Im(L)=0 and Re(L)<0`, which finds every `phase = -180 mod 360` point without any
`unwrap` ambiguity) are found by vectorized sign-change detection with log-frequency linear
interpolation. Reported `phase_margin_deg` is the worst (minimum) margin over all gain crossovers;
`gain_margin_db` is the worst margin against a gain *increase* over all negative-real-axis crossings
with loop gain below 1 (matching the standard "report the worst case" convention, e.g. MATLAB's
`margin`). The extra R2 clause (margin against a gain *decrease* wherever loop gain is above 1 at
such a crossing) is checked separately (`decrease_margin_ok`); for the final design there are no
crossings with loop gain above 1 at all, so it is trivially satisfied.

This whole margin computation was cross-checked against `control.stability_margins((mag, phase_deg,
w))` fed with the identical `L(jw)` array (units matter: that function wants phase in *degrees*) --
it reproduced my gain and phase margins to 4 decimal places at all three speeds, which is strong
independent confirmation the margin code is correct.

Stability (R1) on the linear model was cross-checked a second way: `work/nlsim.run_linear` simulates
the *exact* delayed linear closed loop (same 1 ms step, same 40-step delay buffer, same forward-Euler
actuator/integrator as the nonlinear grader, just with `A x` instead of the nonlinear derivatives,
and no actuator saturation) for 60 s. At all three speeds it settles to exactly the commanded 5 deg
with a bounded transient, confirming stability independent of the frequency-domain argument.

## 4. Time domain (R1, R3-R5): pure-Python replica of the grader's algorithm

`work/nlsim.py` reimplements `aircraft_model.derivatives` with scalar `math` calls (not numpy) for
speed, and reproduces the grader's stated discretization exactly:
RK4 at a fixed 1 ms step with elevator held constant over the step; actuator
`ddelta/dt = sat_rate((sat_position(delta_cmd) - delta)/0.05)` integrated by forward Euler with the
position limit re-applied after integration; the delay as an exact 40-sample lookback buffer
(zero before t=0); the controller integrator by forward Euler. Per step: the true (theta, q)
perturbation is recorded into the delay buffer, the 40-step-old values are read back as `theta_m`,
`q_m`, the controller and actuator command are computed from those, and *then* the aircraft state is
advanced using the elevator position that was current at the start of the step (zero-order hold,
one step of computational delay beyond the sensor delay itself -- a reasonable reading of "the
surface deflection held constant over each step"). `max_elevator_deg` is the peak of the
*unsaturated* commanded value `trim + controller output`, per the literal wording of R4/report.json.
This simulator was built to be fast in pure Python (~0.02-0.03 s per 20 s run) so that hundreds of
designs could be evaluated during the search.

## 5. Design search

A first pass used only the fast frequency-domain check: for a family of phase-margin targets
(maximize the worst-case gain-crossover frequency subject to `PM >= target`, `GM >= target'`), the
gains needed to reach 45-55 deg of margin gave 20-35% nonlinear overshoot -- far over the 10%
budget. This showed that, because of the actuator lag, the 40 ms delay, and the lightly damped
phugoid/short-period pair, the classical "PM~45 deg gives ~zeta 0.4" rule of thumb badly
*under*-estimates the margin actually needed for low overshoot here: matching the 10% overshoot
spec needed roughly 70-80 deg of true phase margin, not 45.

From there the design was refined directly against the nonlinear simulator (grid search, then a
bounded local search) because the overshoot/settling-time landscape is not well summarized by a
single margin number. Two effects dominated the final trade-off:

- **20 m/s has almost no "up-elevator" authority.** Trim there is already -15.41 deg out of a
  +-25 deg limit, leaving only 9.6 deg of headroom for the (up-elevator, i.e. negative) command
  needed to pitch up -- against a steady-state need of about -5.4 deg, that is only about 4 deg of
  headroom for transient overshoot in the elevator command itself. This, not the phase/gain margin,
  is what makes 20 m/s the slowest of the three and keeps `max_elevator_deg` close to the limit
  there (21.6 deg) while 25/32 m/s have 11-14 and 20+ deg of spare room respectively.
- **32 m/s has the least frequency-domain margin.** For a fixed gain set, higher airspeed means
  higher control effectiveness (`B` grows about 2.6x from 20 to 32 m/s), which pushes the gain
  crossover to a higher frequency where the fixed 40 ms delay has eaten more phase -- so uniformly
  scaling the gains up trades 20/25 m/s settling speed for 32 m/s margin, and does so very
  non-linearly: doubling the gains from a good point (all margins 75-82 deg / 6.3-10 dB) is enough
  to push 32 m/s's phase margin *negative* (the crossover sweeps into the short-period resonance).
  `Kq` (the rate/derivative gain) has its own local optimum for 32 m/s's gain margin, found by a
  1-D scan (about Kq = -0.12 for the chosen Kp, Ki); moving away from it costs margin in *both*
  directions.

The final gains sit at the point, found by grid search, then a bounded Nelder-Mead polish, then a
final 1-D scan of `Ki` (holding `Kp`, `Kq` fixed, since the grid/polish runs showed `Ki` trades
overshoot for settling time almost independently of the 32 m/s gain margin -- `Ki/s` is negligible
at the crossover frequency near 18 rad/s where that margin is set, so it is essentially a free knob
once `Kq` is chosen), that minimizes the worst-of-three settling time subject to keeping roughly
0.6 dB of gain-margin buffer at 32 m/s (its floor is essentially fixed by `Kq`, see below) and at
least 0.5 percentage points of overshoot buffer at 20/25 m/s. Pushing `Ki` any further (e.g. to
-4.60) crosses the 10% overshoot line entirely (measured 10.0%, checked explicitly). Setpoint
weight `b` was swept from 0 to 1 at several candidate gains and consistently *increased* overshoot
for negligible settling-time benefit (the proportional kick from a fresh step is exactly what a
low-overshoot spec cannot afford), so `b = 0` was used: the reference reaches the loop only through
the integral path.

# Final gains (`controller.json`)

    K_p = -2.05, K_i = -4.45, K_q = -0.12, b = 0.0

# Verification (`work/verify.py`)

Computed with the exact 200001-point frequency grid and the full 20 s nonlinear simulation
(`work/verify.py -2.05 -4.45 -0.12 0.0`):

| Va (m/s) | PM (deg) | GM (dB) | Overshoot (%) | Settling (s) | Max |delta_e_cmd| (deg) |
|---|---|---|---|---|---|
| 20 | 71.92 | 9.50 | 8.81 | 5.548 | 21.65 |
| 25 | 74.61 | 8.21 | 9.42 | 4.393 | 11.23 |
| 32 | 77.31 | 6.63 | 8.45 | 3.223 | 4.99  |

All of R1-R5 hold at all three speeds, with margin to spare relative to the grading tolerances:
worst-case settling time is 5.548 s (20 m/s) against the 6.0 s pass/fail threshold and the
optimization target; worst-case overshoot is 9.42% (25 m/s) against the 10% threshold; worst-case
gain margin is 6.63 dB (32 m/s) against the 6.0 dB floor. `decrease_margin_ok` is `True` at all
three speeds (there is no negative-real crossing with loop gain above 1, so the extra "margin
against a gain decrease" clause of R2 is moot here -- confirmed explicitly, not just assumed).

# Assumptions (nothing outside README.md/environment/ was used; these fill genuinely
unspecified details of the discretization)

1. **Per-step ordering.** Each 1 ms step: (a) read the true (theta, q) perturbation at the start of
   the step into the delay buffer; (b) form `theta_m`, `q_m` from the buffer 40 steps back
   (zero for the first 40 steps); (c) compute the controller output and the actuator's rate- and
   position-limited target from it; (d) advance the aircraft state one RK4 step using the elevator
   position that was current *before* this step's actuator update (i.e. the actuator's motion during
   step k first affects the plant at step k+1); (e) update the actuator position and the controller
   integrator by forward Euler. This is the natural reading of "RK4 ... the surface deflection held
   constant over each step" combined with "the actuator ... integrated with forward Euler" as two
   separate update rules evaluated once per 1 ms tick.
2. **R4 / `max_elevator_deg`** is measured on the commanded value `trim + controller output` *before*
   the actuator's rate/position saturation, per the literal parenthetical in R4 and in the
   report.json spec. (The actuator's own position is additionally kept within +-25 deg regardless,
   as stated, so the aircraft itself is never actually given an out-of-range surface command; R4 is
   the stricter, no-saturation-needed condition and is the one checked here.)
3. **Reporting a single PM/GM per speed when several crossings exist.** `phase_margin_deg` is the
   minimum phase margin over all gain crossovers; `gain_margin_db` is the minimum gain margin
   against an increase over all phase (negative-real-axis) crossings with loop gain below 1. This
   is the standard convention (matches `control.stability_margins`/MATLAB `margin`) and is also the
   natural reading of R2 ("at least 6 dB ... Phase margin at least 45 deg at every gain crossover").
4. **`b = 0`** is within the stated `0 <= b <= 1` range and was the best point found; it means the
   reference step reaches the plant only through the integral branch, not that setpoint weighting is
   "off" in a structural sense.

# Files

- `work/nlsim.py` -- pure-Python nonlinear simulator (grader-equivalent discretization) + a linear
  variant used only for the independent R1 time-domain check.
- `work/freq.py` -- exact-delay frequency response and margins on the grader's own frequency grid.
- `work/search.py`, `work/codesign.py`, `work/polish.py` -- the search scripts used to find the gains.
- `work/verify.py` -- the final check that produced the numbers in this file and in `report.json`.
