# Difficulty notes

Version 2 of the pitch attitude hold task. Version 1 (`../pitch_attitude_hold/`) was solved by all five runs of
Claude Sonnet 5; its `DIFFICULTY.md` explains why and proposes this version. Every number here comes from the scripts
in this folder.

## What makes the task hard

- **One set of gains across a 1.6 to 1 speed range.** The elevator is 2.6 times more effective at 32 m/s than at
  20 m/s (about 8 dB of loop gain). The 32 m/s gain margin is the limit the reference presses against (6.5 dB), while
  the 20 m/s settling time sets the target. The version 1 gains fail both margins at 32 m/s.
- **The truth model is the nonlinear aircraft.** At 20 m/s the airspeed sags from 20 to 17.7 m/s during the step, the
  elevator loses effectiveness, and the reference settles in 5.60 s where its linear model predicts 5.08 s. A design
  checked only on the linear models misreports its own numbers (`grader/tests/broken/linear_only`).
- **Little elevator left at low speed.** Trim at 20 m/s already uses 15.4 deg of up elevator, and holding +5 deg
  needs about 21 deg. A large setpoint kick drives the command past the stop, and the absolute limit must be computed
  with each airspeed's own trim (`broken/wrong_trim`).
- **The cost of each evaluation.** Every candidate needs three nonlinear simulations of 20 000 steps; an optimizer
  that treats them carelessly runs for hours.
- The version 1 traps still apply: the sign convention, the exact delay, the slow mode next to the zero, the setpoint
  weight, and the settling time convention.

## Calibration before the trials

- **Threshold:** 6.0 s, 7% above the reference's worst settling time (5.595 s at 20 m/s). A cautious design is not
  punished: scaling the reference gains down for 1 dB more gain margin costs only 2% (5.725 s).
- **Reference reserve:** the search kept 2 deg of phase margin, 0.5 dB of gain margin, one point of overshoot and
  1 deg of elevator beyond the limits.
- **The low end of the range is physical.** At 18 m/s the +5 deg hold would need 27.8 deg of up elevator, past the
  stop, whatever the gains (`reference/VALIDATION.md`, section 6). The task stops at 20 m/s, where it needs about
  21 deg.
- **Ambiguities removed:** the truth model for each check (linear models for the margins, the nonlinear aircraft for
  the step), the integration scheme, the trim each run starts from, the divergence rule, and the report format, one
  entry per airspeed.

## Calibration from the trials (2026-09-27)

Five runs with Claude Sonnet 5, one at a time (`trials/RESULTS.md`):
- **All five passed:** pass@1 is 1.00. Worst settling times were 5.389 to 5.794 s, against 5.595 s for the
  reference; every worst case was at 20 m/s, and every report matched the grader within the stated tolerances.
- **The designs converged.** All six gain sets, the reference's included, lie within 5% of each other on K_p (-2.00
  to -2.10) and within 10% on K_i (-4.15 to -4.60). They differ mainly in the setpoint weight (0 to 0.20). Each kept
  0.4 to 0.8 dB beyond the 6 dB gain margin at 32 m/s.
- **No trap reached a deliverable.** Every run took its numbers from the nonlinear aircraft, computed the elevator
  limit with each airspeed's own trim, and found the binding airspeeds.
- **The difficulty moved into the process.** The runs took 127 to 283 tool calls and 58 to 179 minutes, against 68
  to 183 tool calls and 57 to 106 minutes in version 1. Run 4's first search, on the linear models under margin
  constraints only, reached gains with 90 to 152 deg of phase margin and an unstable closed loop. With full setpoint
  weight they overshot about 470% to 730% on the nonlinear aircraft; the run blamed windup, and recovered by
  searching on the nonlinear model. Runs 2 and 4
  reported the open loop phugoid as their slowest closed loop pole, an artifact of python-control's transfer function
  arithmetic, and run 2 explained it as physics.
- **The grader held.** Run 4's unstable design is now the broken solution `grader/tests/broken/unstable_good_margins`;
  the grader rejects it on stability alone, without any change.

Version 2 is therefore still not model breaking for this model at the level of pass or fail. The grader checks the
design, and every design was right; the errors were in the analysis around it, which the report does not ask for.

## Proposed for version 3 (not built)

1. **Grade the analysis as well as the design:** ask for the slowest closed loop pole at each airspeed in
   `report.json`, checked against the grader's state space computation. That pole, at about -0.33, -0.34 and -0.39 1/s at
   20, 25 and 32 m/s, sits just to the right of the zero of the pitch attitude response to the elevator (-0.37,
   -0.36 and -0.40 1/s), and barely moves with the gains: all six designs agree within 0.004 1/s at each airspeed.
   The check therefore tests the stability analysis, not the design. Runs 2 and 4 would have failed it.
2. **Sensor noise with an actuator budget,** proposed for version 2 and not built: noise on the rate gyro and attitude
   measurements, and a limit on the RMS elevator rate. The rate gain, which the runs set freely, would then trade
   against actuator wear.
3. **Gust rejection,** also proposed for version 2 and not built: a vertical gust requirement that competes with the
   step response for the same gains.

Calibrate as before: a reference, broken solutions for the grader, then five trials one at a time.
