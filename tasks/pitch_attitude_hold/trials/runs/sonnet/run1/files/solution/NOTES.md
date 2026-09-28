# Method

## Model setup

Loaded `A,B,C,D` and the exact trim (`delta_e_rad = -0.12391805205152141`) from
`environment/plant.json` (never the rounded figures quoted in the README text). All work is done
in SI units (rad, rad/s, s) and converted to degrees only for the limits/reporting.

A useful structural fact falls out of the state ordering `x=[u,w,q,theta]`: row 4 of `A` is
`[0,0,1,0]` with `B[3]=0`, i.e. `theta_dot = q` exactly, as a kinematic identity, for *any* input.
Hence in the Laplace domain `Q(s) = s*Theta(s)` identically, so

    P_q(s) := q(s)/delta_e(s) = s * P_theta(s)   exactly (verified numerically, residual ~1e-16)

and because the 40 ms delay is a pure delay, it commutes with differentiation, so `q_m(t)` is
exactly the derivative of `theta_m(t)` even after delay. This means the given controller

    delta_e_cmd = Kp*(b*theta_cmd - theta_m) + Ki*Int(theta_cmd-theta_m) - Kq*q_m

is, from the plant's point of view, an ordinary **PID acting on the single measurement
theta_m** (with the derivative term implemented through the direct rate-gyro measurement instead
of a numerical derivative), plus independent setpoint weighting `b` on the P-term only. The
setpoint weight cannot affect the loop's poles (see below) — only the numerator zero of the
theta_cmd -> theta transfer function — because it is not part of the theta_m/q_m feedback path.

## Loop transfer function (R2)

Breaking the loop at the elevator command, with `theta_cmd=0` (so `b` drops out, confirming it
cannot affect margins):

    L(s) = Aact(s) * e^(-s*0.040) * P_theta(s) * (Kp + Ki/s + Kq*s)
    Aact(s) = 1/(1+0.05 s)

`1+L(s)=0` is the closed-loop characteristic equation in the standard unity-feedback convention.

I implemented the grader's exact margin recipe: `w = logspace(log10(0.001), log10(1000), 200001)`,
exact delay `e^{-jw*0.040}`, magnitude/phase of `L(jw)` from the exact state-space frequency
response (batched `C(jwI-A)^-1 B`, not a fitted transfer function, to avoid any polynomial
round-off). Gain margins are taken at *every* frequency where the (continuously unwrapped) phase
crosses an odd multiple of 180 deg: `-20log10|L|` where `|L|<1` ("against an increase"), and
`+20log10|L|` where `|L|>1` ("against a decrease"); phase margins are `180+phase(L)` at *every*
0 dB crossing. The reported/checked values are the worst case over all crossings. I verified this
custom routine two ways: (1) against `control.margin()` on a known textbook `L(s)=10/(s(s+1)(s+5))`
(exact match to 6 decimals), and (2) against `control.frequency_response()` evaluated directly at
the final design's crossing frequencies (exact match, see below) — a completely independent code
path from the batched linear solve used for the 200001-point sweep.

## Time-domain model (R3-R5)

Implemented the grader's simulation exactly as specified: fixed `dt=1 ms`; the plant discretized
**exactly** by the augmented-matrix-exponential ZOH trick (`expm([[A,B],[0,0]]*dt)`), not an
approximation; the actuator `ddelta/dt = sat_rate((sat_position(delta_cmd)-delta)/0.05)` integrated
with forward Euler and the result re-clipped to the position limit; the 40 ms delay as exactly 40
samples with zero history before t=0; the controller integrator by forward Euler. All elevator
limits are computed from the *exact* trim angle (`+-25 deg absolute` -> perturbation range
`[-0.312414261, 0.560250365]` rad, i.e. -17.900019/+32.099981 deg, matching but slightly more
precise than the README's rounded -17.9/+32.1 deg). R4 and `max_elevator_deg` are checked on the
**raw controller output**
(`trim + Kp(...)+Ki(...)-Kq(...)`, before the actuator's own position saturation) since that is
what R4 explicitly names ("elevator command", the same signal `sat_position` is applied *to*
inside the actuator ODE) — checking the already-clipped actuator position would make R4 vacuous.
Re-running the same design at `dt=0.2 ms` changed overshoot/settling/peak-elevator by <0.05% ,
confirming the `dt=1 ms` result is not a step-size artifact.

# Design process

A first pass using classical PID loop-shaping (place the crossover frequency, size Ki/Kp from a
PI-corner rule, size Kq from the required phase lead at crossover) easily meets R1/R2/R4 but
settles in 7-14 s: `P_theta(s)` has a lightly-damped phugoid pair (wn=0.499 rad/s, zeta=0.286) and
a real zero at s=-0.359. Closed-loop pole analysis (8th-order Pade model of the delay, cross-checked
against the exact-frequency-response margins) shows that with this Kp+Ki/s+Kq*s structure the
phugoid pair splits into a fast pair and a slow real pole that is dragged toward that -0.359 zero
as loop gain grows, but **cannot be pushed faster than about -0.36 rad/s while holding PM>=45 deg
and GM>=6 dB** — confirmed by a dedicated global search that maximized the slowest pole's decay
rate subject to the margins and found -0.356 as the practical ceiling. A pole that slow would need
about 11 s to settle to 2% on its own, far outside R5's 4 s, no matter how the other three gains
are tuned — so speed cannot come from moving that pole.

The way out is the setpoint weight `b`: the theta_cmd -> theta numerator carries a zero at
`s = -Ki/(Kp*b)`, which is the *only* free handle that does not move the poles. Choosing `b` to
place that zero close to the slow pole cancels most of its residue in the step response, so the
observed settling time can be much faster than "4/|slow pole|" suggests even though the pole
itself stays put. Also matters: `Kq` away from a narrow near-zero range destabilizes quickly at
the Kp/Ki magnitudes needed here, and pushing `Kp,b` too far for speed re-introduces overshoot
from the short-period-derived complex pair, so `Kp,Ki,Kq,b` were tuned jointly, not one at a time.

Final tuning used `scipy.optimize.differential_evolution` followed by `Nelder-Mead`, directly on
the exact nonlinear time-domain simulator (objective = settling time; margins, overshoot and the
elevator limit enforced as penalties with a safety buffer beyond the bare pass thresholds, since
the optimizer otherwise rides the bare constraint to the millidegree). The fastest point found
(Kp=-2.573, Ki=-6.361, Kq=-0.172, b=0.122) settles in 3.41 s but leaves only 0.49 dB of gain-margin
buffer; I walked 50% of the way toward a second, more conservative local optimum (more buffer on
every requirement, settles in 3.84 s) along the line joining them — settling time, overshoot,
phase and gain margin all move smoothly and monotonically along that line, so this interpolation
is a legitimate point, not a random guess — landing on the reported design. It is not the
fastest design found, but the fastest one I was comfortable certifying against a linear/nonlinear
margin computation that is, in the end, a numerical estimate:

| | Kp | Ki | Kq | b | PM | GM(up) | overshoot | settling | peak elevator |
|---|---|---|---|---|---|---|---|---|---|
|fastest found| -2.573|-6.361|-0.172|0.122|57.9 deg|6.49 dB|9.50%|3.41 s|12.1 deg|
|**reported**| **-2.444**|**-5.752**|**-0.167**|**0.145**|**80.8 deg**|**6.98 dB**|**9.35%**|**3.61 s**|**11.8 deg**|
|more conservative|-2.316|-5.142|-0.162|0.167|81.3 deg|7.49 dB|9.00%|3.84 s|11.5 deg|

# Verification performed

- Margins cross-checked against `control.margin()` (toy system) and `control.frequency_response()`
  (this design, at its exact crossing frequencies 5.947 and 16.480 rad/s) — matched to 5 decimals.
- Closed-loop poles (Pade-delay model): slowest is -0.343 rad/s (real), all others have zeta>=0.18
  and the dominant overshoot-causing pair has zeta=0.60; max real part -0.343 < 0, confirming R1.
- Settling time computed at 1.9%/2.0%/2.1% bands: 3.554 / 3.608 / 3.663 s — a tight, monotonic
  cluster, i.e. the crossing is clean and not a marginal graze of the band that would make the
  reported number sensitive to exactly how the grader breaks ties.
- `max_elevator_deg` is a peak over the *entire* 20 s record of the pre-saturation command, not
  just its value at the overshoot peak.
- Re-read `solution/controller.json` from disk and re-ran the whole pipeline on the parsed JSON;
  reproduced every `report.json` number to at least 1e-9.

# Assumptions

- "The pitch attitude" in R3/R5 is the actual aircraft attitude `theta` (the true state), not the
  delayed measurement `theta_m` — the physically meaningful autopilot performance quantity. The
  controller itself, per the given control law, only ever sees the delayed `theta_m`/`q_m`.
- `gain_margin_db` in `report.json` is the margin against a gain *increase* (as the README asks
  for), i.e. the worst case over crossings where `|L|<1` at a -180 deg crossing. The complementary
  "against a decrease" margin (only relevant where `|L|>1` at a -180 deg crossing) was checked
  internally to confirm R2 but has no dedicated report field; for this design it is infinite (no
  such crossing exists — the design has a single, clean gain crossover and a single relevant
  phase crossover).
- Reported `phase_margin_deg`/`gain_margin_db` are the worst case across *all* crossings found on
  the specified grid, matching R2's "at every gain crossover" / "wherever the phase crosses -180".

# Files

- `controller.json`, `report.json` — deliverables.
- (development scripts used to reach this design are in `../dev/`, not required for grading:
  `model.py` the plant/actuator/delay/margin/simulation core, `evaluate.py` the metrics used
  above, `poles.py` the Pade closed-loop pole check, `search_full.py`/`refine1.py` the optimizers,
  `finalize.py` the script that wrote the two JSON files.)
