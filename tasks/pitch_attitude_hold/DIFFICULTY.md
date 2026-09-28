# Difficulty notes

Version 1. Every number here comes from the scripts in this folder or from the agent trials in `trials/`.

## What makes the task hard

- **A slow mode that hides.** Holding pitch attitude at fixed throttle leaves a slow closed loop pole near
  `-0.34` 1/s (a time constant of about 3 s). It moves little with the gains, because it sits next to the zero of
  the pitch response to the elevator at `-0.36` 1/s, where the airspeed adjusts to the new attitude. Its small
  residue shows up as a dip after the first rise: in the reference, the 2% settling time (3.485 s) is set by a
  2.6% dip near 2.9 s, not by the rise. A design checked for only 2 or 3 s, or designed on a short period model,
  looks settled too early.
- **Signs.** Positive elevator pitches the nose down, so every gain must be negative. The README states the
  convention once, in plain words.
- **The delay costs gain margin.** The 40 ms delay and the actuator lag put the phase crossover near 17 rad/s. The
  gain margin is the limit the reference presses against (6.5 dB); the phase margin is not (54.9 deg).
- **Setpoint weight.** With `b = 1` the proportional term kicks the elevator into the rate limit and the step
  overshoots by 33%. The reference uses `b = 0.15`. The structure allows it; the README does not say it is needed.
- **Absolute versus perturbation limits.** The ±25 deg limit applies to trim plus perturbation, and trim is
  already 7.10 deg trailing edge up.
- **Settling time convention.** It is measured against the command. MATLAB's `stepinfo` and python-control's
  `step_info` measure it against the final value, which hides a steady state error.
- **Claims are checked.** The grader recomputes every number in the report.

## Calibration before the trials

- The pass threshold (4.0 s) sits 15% above the reference's settling time (3.485 s). The cautious but otherwise
  valid design in `grader/tests/broken/slow_but_safe` settles in 8.41 s and fails only on this threshold.
- The reference search required a small reserve beyond each limit (2 deg of phase margin, 0.5 dB of gain margin,
  one point of overshoot), so a careful agent can do slightly better than the reference.

## Calibration from the trials (2026-09-26)

Five runs with Claude Sonnet 5 (`trials/RESULTS.md`):
- **All five passed:** pass@1 is 1.00. Settling times were 3.447 to 3.722 s, against 3.485 s for the reference, and
  every report matched the grader within the stated tolerances.
- **No failure came from ambiguity.** All five read every requirement the way the grader does, including the ones
  written to be traps: the sign convention, the exact delay, the absolute elevator limit and the settling time
  convention.
- **Every trap was recognized,** including the slow mode next to the zero. All five chose a small setpoint weight
  (0.05 to 0.23; the reference uses 0.15), and run 1 explained why: the weight places a zero near the slow pole.
- **The threshold is loose.** The runs also found designs at about 3.1 to 3.4 s and set them aside to keep margins in
  hand.

Version 1 is therefore not model breaking for this model. Tightening the threshold alone would only reward riding the
requirement limits, which the runs rightly avoided. A harder version should add real engineering conflict instead.

## Ambiguities removed before any trial

- where the loop is broken for the margins, and that the delay is exact, not approximated;
- the definition of settling time, against the command, over the full 20 s;
- that the elevator limit is on the absolute command;
- how to report an infinite margin (999);
- the grader's integration scheme, stated in full, with claim tolerances wide enough for reasonable alternatives.

## Proposed for version 2 (not built)

Each keeps the README complete and adds a conflict a control engineer would recognize:
1. **One set of gains across the speed range:** the same controller must meet the requirements at 18, 25 and
   32 m/s, each with its own trim and linear model. The slow mode and the elevator effectiveness move with speed.
2. **Sensor noise with an actuator budget:** noise on the pitch rate and attitude measurements, and a limit on the
   RMS elevator rate. Damping from the rate gyro then competes with actuator wear.
3. **The nonlinear model as the truth model:** a larger step, so the airspeed decay and the lift curve matter and a
   design tuned only on the linear model can fail.
4. **Gust rejection:** a vertical gust requirement that competes with the step response for the same gains.

Calibrate each candidate the same way: a reference, broken solutions for the grader, then five trials. If pass@1 is
zero because the README is ambiguous, fix the README, not the grader. Run the trials one at a time or in separate
containers, since runs sharing a machine could see, and in one case stop, each other's processes.
