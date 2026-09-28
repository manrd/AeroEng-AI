# Agent trials: results

## Setup

- **Model:** Claude Sonnet 5 (`claude-sonnet-5`), run as Claude Code subagents on 2026-09-27.
- **Runs:** five, one at a time. Each run had its own folder holding only the task `README.md` (SHA256
  `4c9dbaa9...1b86a`) and `environment/`: no reference, no grader, no hints.
- **Prompt:** the version 1 prompt, plus one rule learned there: "Never stop or kill a process you did not start
  yourself; other work may be running on this computer."
- **Grading:** `grader/grade.py`, unchanged, on each run's final `solution/`.
- **Logs:** `runs/sonnet/runN/log.md` holds every step of the agent, sanitized as in version 1 (local paths replaced,
  emails and host names redacted, tool results cut at 8000 characters, third party file contents withheld).
  `files/` holds the text files the agent wrote, with the same path replacement. `grade.json` is the grader's output.

## Results

All five runs pass: pass@k is 1.00 for every k from 1 to 5 (`python summarize.py`).

| Run | Verdict | Worst settling time (s) | Gain margin at 32 m/s (dB) | Largest overshoot (%) | Peak elevator at 20 m/s (deg) | Tool calls | Wall time (min) |
|---|---|---|---|---|---|---|---|
| 1 | PASS | 5.481 | 6.41 | 9.25 | 21.65 | 166 | 58 |
| 2 | PASS | 5.389 | 6.41 | 9.63 | 21.65 | 283 | 91 |
| 3 | PASS | 5.549 | 6.63 | 9.42 | 21.65 | 127 | 61 |
| 4 | PASS | 5.678 | 6.75 | 9.03 | 21.65 | 174 | 179 |
| 5 | PASS | 5.794 | 6.77 | 8.66 | 21.65 | 140 | 69 |
| Reference | PASS | 5.595 | 6.50 | 8.92 | 21.65 | | |

Every worst case is at 20 m/s, and every report matched the grader's recomputation within the stated tolerances.
Runs 1, 2 and 3 beat the reference on worst case settling time, at the cost of more overshoot and, for runs 1 and 2,
less gain margin. The peak elevator at 20 m/s is the same for every design: it is set by the steady
hold at the sagging airspeed, not by the gains.

## What every run got right

From the runs' `NOTES.md` files and logs:
- every number in the report taken from the nonlinear aircraft, as the task requires; no run fell into the linear
  model trap in its deliverables;
- the elevator limit computed with each airspeed's own trim;
- the 32 m/s gain margin as the binding limit, and 20 m/s as the slowest airspeed;
- the version 1 basics: negative gains, the exact delay, and the setpoint weight kept out of the margins.

Runs 1 and 5 also tested the one ordering choice the README leaves open within a time step, and found it moves the
results by at most 0.003 s.

## Failure taxonomy

None of these changed a verdict. They are what the logs show beyond the grade.

| Category | What happened | Runs | Evidence |
|---|---|---|---|
| Tool artifact taken for physics | Each run's second stability check built the closed loop with python-control transfer function arithmetic, which keeps the open loop phugoid as a spurious pole. Both reported slowest poles of -0.114, -0.143 and -0.182 1/s at 20, 25 and 32 m/s, the phugoid's real parts, and run 2 gave a physical reason: the attitude feedback "barely touches" the phugoid. For every run's design the true slowest poles are real, at about -0.33, -0.34 and -0.39 1/s, as run 5 reported. | 2, 4 | their `NOTES.md` and final reports |
| Margins trusted on an unstable loop, then misdiagnosed | Run 4 first maximized the crossover frequency on the linear models under margin constraints only. The optimizer ran to the edge of its search box, K_p = K_i = -4 with a positive rate gain, and the margin sweep gave those gains 90 to 152 deg of phase margin. Yet that closed loop is unstable at every airspeed, with real poles up to +18.4 1/s, which margins read from crossings cannot show. (Unbounded, the same search went on to K_p = -129, also unstable.) With full setpoint weight the boxed gains overshot about 470% to 730% on the nonlinear aircraft; the run blamed integrator windup against the rate limit, the wrong cause, and recovered by moving its search onto the nonlinear model. These gains are now the grader test `broken/unstable_good_margins`. | 4 | steps 116, 117 and 121 to 123, and `NOTES.md` |
| Answer changed after the report | Run 2 reported its design, then a background search it had left running found a better one; it replaced the solution files and sent a correction. The graded design is the final one. | 2 | log |
| Blocked process kill | Run 1 tried to stop a background scan it had started; the harness's safety classifier refused, and the run let the job finish. | 1 | steps 69 and 70 |
| Unrelated tool use | Run 4 called a tool of the host application three times: a chapter marker that labels progress in the view of the session that launched the run, outside the task. No effect on the task, but it shows that the agent under test could reach that session's tools. | 4 | steps 111, 123 and 142 |
| Instruction breach, harmless | Read python-control's source code in the Python installation, outside the working folder. | 3, 5 | a Read of `control/margins.py` |
| Cost | Every candidate needs three nonlinear simulations. Runs took 58 to 179 minutes; run 4 spent about three hours in background optimization. | all | the table |
| A knife edge noticed | Run 4 found its 32 m/s response dips to within 0.00006 deg of the 2% band edge, so its settling time there reads anywhere from 2.2 to 3.35 s depending on the band. It documented this; the grader's band range tolerance is built for it. | 4 | `NOTES.md` |

## Isolation audit

Every tool call was checked as in version 1.
- No run read the reference, the grader, the repository or any other project file. The only files read outside the
  run folders were python-control's source (runs 3 and 5).
- The runs went one at a time. Two overlaps remained: run 2's leftover background job and correction ran during the
  first 22.6 minutes of run 3, and run 1's last step fell 0.5 minutes into run 2. The folders were separate, and no
  run listed or touched another run's folder.
- Process listings were used only to watch each run's own jobs. The one kill attempt (run 1, its own job) was
  refused by the harness.

## What this says about the task

Version 2 is still not model breaking for Claude Sonnet 5 at the level of pass or fail: pass@1 is 1.00. All five
runs handled one set of gains across the speed range and the nonlinear truth model. The difficulty showed in the
trajectories instead: one to three hours per run, an unstable design that looked excellent by its margins, and two
runs whose "independent" stability check was a tool artifact they explained as physics. A pass or fail grade cannot
see that; the logs can.

Two changes follow. The unstable design from run 4 is now a broken solution the grader must reject (it does, on
stability alone; 13 of 13 grader tests pass). And the next version should ask for the slowest closed loop pole at
each airspeed in `report.json` and check it; runs 2 and 4 would have failed that check. `../DIFFICULTY.md` has the
details.
