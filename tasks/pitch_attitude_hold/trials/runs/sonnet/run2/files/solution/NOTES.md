# Method

## Structure of the problem

`plant.json` gives a 4th-order longitudinal model (states `u, w, q, theta`) that is stable
in open loop: short period at wn=11.02 rad/s, zeta=0.443; phugoid at wn=0.499 rad/s,
zeta=0.286 (eigenvalues -4.895+-9.870j and -0.1426+-0.478j). Because the fourth state
equation is exactly `theta_dot = q`, the plant's `q` output is *exactly* `s` times its
`theta` output, at every frequency, for the linear model. That means the given control
law

    delta_e_cmd = Kp(b*theta_cmd - theta_m) + Ki*Integral(theta_cmd - theta_m) - Kq*q_m

is algebraically a PID controller on theta (P=Kp, I=Ki, D=Kq) with setpoint weighting
applied only to the P term -- a standard "PI-D" structure, except the derivative is
formed from the directly measured (and independently delayed) pitch rate rather than by
differentiating a delayed position signal. Since delay and differentiation commute for
linear systems, and there is no sensor noise here, these are the same signal. This let me
reason about the design with ordinary PID/loop-shaping intuition while still simulating
the literal, given block diagram.

## Frequency-domain model (for R2)

Breaking the loop at `delta_e_cmd` as R2 specifies gives

    L(s) = Act(s) * e^(-s*tau) * P_theta(s) * (Kp + Ki/s + Kq*s)

with `Act(s) = 1/(1+0.05s)`, `tau = 0.04 s`, and `P_theta(s) = C_theta (sI-A)^-1 B` evaluated
directly from the state-space matrices (an eigendecomposition of `A` turns this into a
partial-fraction sum, which is exact and fast to evaluate on the grader's full grid of
200001 points from 0.001 to 1000 rad/s). Gain/phase margins were computed by finding all
gain crossovers (|L|=1) and all crossings of the negative real axis (Im(L)=0, Re(L)<0),
exactly as `python-control`'s `stability_margins` defines them, but with a direct
vectorized crossing search instead of `control`'s FRD/spline path (which was too slow --
about 100 s per call -- to use inside an optimizer). I validated the fast method against
`control.stability_margins(..., returnall=True)` directly and the two agree to about 1e-4
dB / 1e-4 deg. For the final design there is exactly one gain crossover (phase margin) and
one relevant phase crossover with loop gain below 1 (gain margin); the other six phase
crossovers found by the search are all above 150 rad/s, artifacts of the delay's phase
wrapping, with 45+ dB of margin -- not binding. Because no phase crossing has loop gain
above 1, this design is not conditionally stable, so R2's extra "margin against a gain
decrease" clause does not apply (there is nothing to protect against).

## Time-domain model (for R1, R3-R5)

I wrote a nonlinear simulator that follows "How the grader simulates" literally: the
plant is advanced with the exact zero-order-hold discretization of `(A,B)` at dt=1 ms
(checked against a direct `scipy.integrate.solve_ivp` run on the continuous ODE -- they
agree to 1e-14); the actuator integrates `ddelta/dt = sat_rate((sat_position(delta_cmd) -
delta)/0.05)` with forward Euler, including the position clamp on the resulting position
too; the 40 ms delay is an exact 40-sample FIFO (40 steps at dt=1 ms, no approximation
needed); the controller integrator uses forward Euler; measurements before t=0 are zero.
One implementation choice the README leaves open is exactly which within-step values feed
which update (e.g. does the plant's zero-order hold use the actuator position from the
start or the end of the step). I checked this by re-running the final design with three
different, equally defensible orderings: the differences were under 0.06 percentage
points of overshoot, 0.004 s of settling time, and 0.03 deg of elevator -- all far inside
the grading tolerances, so this ambiguity is not a practical risk.

## Search

`Kp, Ki, Kq` set the closed-loop poles (via `1+L(s)=0`); `b` only moves a zero in the
command-to-theta path and so trades overshoot against speed without touching stability.
I first scanned by hand to understand scale (pure-P is gain-margin-limited to about
`Kp=-1.85` by a crossing near the short-period frequency, ~16 rad/s, giving huge spare
phase margin, ~94 deg, so there was clearly room to add speed via I and D without an
obvious stability problem), then used `scipy.optimize.differential_evolution` (global,
since the feasible region is shaped by saturation and by which of several
frequency-response crossings binds, not smooth) followed by a `Nelder-Mead` polish, on a
penalty function that heavily penalizes violating buffered versions of R1-R5 and
otherwise minimizes settling time. All four gains came out negative -- consistent with the
plant's DC gain from elevator to theta being negative (about -1.78 rad/rad): a positive
pitch-up command must be met with a negative (trailing-edge-up) elevator perturbation, so
positive error must produce negative `delta_e_cmd`.

I deliberately did not push the buffers all the way to the bare R1-R5 thresholds: the
optimizer happily finds points sitting exactly on whatever buffer is asked for, and the
settling time bought by shaving the buffer further is small (roughly 3.84 s at a 1.5 dB /
1.0-point buffer, 3.72 s at 1.0 dB / 1.5 points, 3.60 s at 1.0 dB / 0.5 points) -- so I kept
comfortable margin rather than chase the last tenth of a second.

# Result

    K_p = -2.41928257
    K_i = -5.42894891
    K_q = -0.15787529
    b   =  0.14503308

| quantity | value | requirement | buffer |
|---|---|---|---|
| phase margin | 80.99 deg | >= 45 deg | 36.0 deg |
| gain margin (vs. increase) | 7.00 dB | >= 6 dB | 1.00 dB |
| gain margin (vs. decrease) | n/a (no crossing with loop gain > 1) | -- | -- |
| overshoot | 8.50 % (peak theta = 5.425 deg at t=1.39 s) | <= 10 % (5.5 deg) | 1.5 points |
| max elevator command | 11.63 deg | <= 25 deg | 13.4 deg |
| 2% settling time | 3.721 s | <= 4.0 s | 0.28 s |

These are exactly the numbers written to `report.json` (rounded to 4 decimals there).

# Verification

Stability (R1) was checked three independent ways, all agreeing:
1. The frequency-domain margins above are both positive (finite, positive dB and degrees).
2. I built the *exact* dt=1 ms discrete update matrix for the full linear closed loop
   (plant + actuator + integrator + a 40-sample FIFO per delayed signal, 86 states) with
   saturation removed -- the same linearization already implicit in the margin
   computation -- and confirmed every eigenvalue is inside the unit circle
   (max |eig| = 0.99966; not a sign of marginal stability, just the expected result of
   sampling a slow, well-damped closed-loop mode at a very fine 1 ms step -- a continuous
   pole at -0.34 /s maps to `exp(-0.34*0.001) = 0.99966` exactly).
3. The full nonlinear 20 s simulation (with actuator rate/position saturation active)
   converges smoothly with no divergence or limit-cycling; I inspected the time trace
   (theta rises to a single overshoot peak at t=1.39 s, dips slightly below 5 deg near
   t=3 s, and converges monotonically after that; the elevator command stays in a narrow
   band around -8 to -11.6 deg, nowhere near its +-25 deg limit).

R3-R5 come directly from that same nonlinear simulator, run at the grader's exact
dt=1 ms for the full 20 s. R2 was cross-checked against `python-control`'s own
`stability_margins` (see above). `report.json`'s numbers are the same simulator/margin
outputs used for the pass/fail checks, so they should reproduce the grader's recomputed
values well inside the stated tolerances.

# Assumptions (nothing in the README was contradictory, but a few points needed a
concrete choice)

- **"controller output" in R4 / `max_elevator_deg`** means the controller's raw
  `delta_e_cmd(t)` (trim plus the *unsaturated* command), not the post-actuator surface
  position. I track both; the actual (post-saturation) peak is smaller (11.46 deg vs.
  11.63 deg here) and is never the binding one for this design.
- **Within-step update order** for the discrete simulation (e.g. whether the plant's
  zero-order hold uses the actuator position from the start or end of the 1 ms step) is
  not fully pinned down by the prose; I used the most natural reading (plant and actuator
  both advance from step k to k+1 consuming the values available at the start of step k)
  and confirmed by direct experiment (see "Time-domain model" above) that alternative,
  equally reasonable choices change nothing by more than a few hundredths of a unit --
  well under the grading tolerances.
- **R2's gain-margin-against-decrease clause** is checked but turns out vacuous for this
  design: every phase crossing (Im(L)=0, Re(L)<0) found on the full 200001-point grid has
  loop gain below 1, i.e. this is not a conditionally stable loop, so there is no crossing
  that needs protecting against a gain decrease.

# Files

- `work/lib.py` -- plant loading, frequency response, margins, exact discrete stability
  check, and the nonlinear time-domain simulator (all the analysis machinery described
  above).
- `work/search.py`, and the ad hoc scripts used interactively -- the optimization driver.
- `work/finalize.py` -- recomputes the report from the final gains and writes
  `controller.json` / `report.json`.
