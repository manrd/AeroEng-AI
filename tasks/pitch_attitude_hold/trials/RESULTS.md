# Agent trials: results

## Setup

- **Model:** Claude Sonnet 5 (`claude-sonnet-5`), run as Claude Code subagents on 2026-09-26.
- **Runs:** five, started together on one Windows PC. Each run had its own folder holding only the task
  `README.md` (SHA256 `c1cbd2cb...0cde2`) and `environment/`: no reference, no grader, no hints.
- **Prompt:** the same for every run (below).
- **Grading:** `grader/grade.py`, unchanged, on each run's `solution/`.
- **Logs:** `runs/sonnet/runN/log.md` holds every step of the agent: its messages, tool calls and tool results, with
  local paths replaced by `<run>`, `<home>` and `<harness>`, emails redacted, and tool results cut at 8000 characters.
  `files/` holds the text files the agent wrote, with the same path replacement, so its scripts will not run
  unchanged. `grade.json` is the grader's full output.
- **Isolation:** by instruction, then checked in every transcript (below).

The prompt, verbatim apart from the folder path:

> You are a coding agent working on an engineering design task. Your working folder is `<run>`. The task statement is
> README.md in that folder; the files it refers to are in its environment/ subfolder. Read README.md and complete the
> task. Write your deliverables to the solution/ subfolder of your working folder, exactly as the README specifies.
> Rules: Work only inside your working folder. Do not read, list or search any other folder on this computer, and do
> not use the internet or any web tools. Use the installed Python (the `python` command, Python 3.12) and the
> packages the README lists. Do not install anything. Do not start other agents or subagents. Nobody is available to
> answer questions. If something seems unclear, make a reasonable assumption and write it down in your NOTES.md.
> When you finish, reply with a short summary: your method, and the values you put in report.json.

## Results

All five runs pass. With n = 5 runs and c = 5 passes, pass@k is 1.00 for every k from 1 to 5 (unbiased estimator;
`python summarize.py` recomputes it).

| Run | Verdict | Settling time (s) | Phase margin (deg) | Gain margin (dB) | Overshoot (%) | Crossover (rad/s) | Tool calls | Wall time (min) |
|---|---|---|---|---|---|---|---|---|
| 1 | PASS | 3.609 | 80.8 | 6.98 | 9.35 | 5.9 | 102 | 63 |
| 2 | PASS | 3.722 | 81.0 | 7.00 | 8.50 | 5.6 | 68 | 106 |
| 3 | PASS | 3.662 | 70.3 | 7.00 | 9.00 | 6.6 (three crossings) | 119 | 58 |
| 4 | PASS | 3.447 | 60.0 | 6.50 | 9.30 | 9.2 | 183 | 57 |
| 5 | PASS | 3.537 | 46.6 | 6.41 | 9.30 | 11.6 | 85 | 71 |
| Reference | PASS | 3.485 | 54.9 | 6.50 | 8.91 | 10.0 | | |

Every run's report matched the grader's recomputation within the stated tolerances. Run 4 beat the reference's
settling time. Run 3's loop crosses 0 dB three times; its phase margin is the smallest of the three, as the README
defines it, and the gain margin comes from the phase crossover, as for every run.

## What every run got right

From the runs' `NOTES.md` files and logs:
- every gain negative, from the sign convention;
- margins with the exact delay, on the grader's frequency grid;
- the setpoint weight `b` acts only on the reference path, so it shapes the overshoot without touching the margins;
- the slow mode next to the zero of the pitch response, with settling time measured against the command over the
  full 20 s;
- the elevator limit read as the raw command with trim included, as the README intends;
- a margin of safety beyond every requirement. No run submitted its fastest design: runs 3, 4 and 1 reported faster
  designs (about 3.13 s, 3.29 s and 3.41 s) that they set aside because they left little or no margin on a
  requirement.

## Failure taxonomy

None of these changed a verdict. They are what the logs show beyond the grade.

| Category | What happened | Runs | Evidence |
|---|---|---|---|
| Destructive action on a shared resource | Run 3 listed every Python process on the machine and killed five it assumed were its own stray jobs. One of them was run 1's background search, which died; run 1 edited and relaunched it, and still passed. | 3 (cause), 1 (hit) | run 3, steps 47 and 48; run 1: `896 Killed python search_full.py` |
| Visibility across runs | Run 1's process listing showed the other runs' command lines and folder names; runs 3 and 4 saw the other runs' processes. No run opened another run's folder. | 1, 3, 4 | the `ps` output in their logs |
| Instruction breach, harmless | Read python-control's own source code in the Python installation, outside the working folder. | 2 | run 2 log, a Read of `control/margins.py` |
| Tool pitfall found and handled | python-control adds transfer functions without canceling common factors, so closed loop poles taken from the sum keep spurious open loop poles. Run 5 saw the inconsistency, rebuilt the loop as one polynomial ratio, and checked it against a state space build. | 5 | run 5 `NOTES.md` |
| Tool cost | `control.stability_margins` took about 100 s per call on the 200001 point grid, too slow for an optimizer. Run 2 wrote a vectorized crossing search and validated it against the library to about 1e-4. | 2 | run 2 log |
| Inefficient waiting | While background optimizations ran, the agent kept rereading their unchanged output: 31, 42 and 17 reads that returned nothing new. | 3, 4, 5 | their logs |

## Isolation audit

Every tool call was checked for paths outside the run folder, for searches without a path (a subagent starts in the
session's own folder), and for tool results carrying content from outside the run folder.
- No run read the reference, the grader, the repository or any other project file.
- The only file read outside a run folder was run 2's read of python-control's source (above).
- Reads of each agent's own background job output are expected: the harness keeps that output outside the run
  folder.
- The runs could see each other's processes, and one stopped another's job (above). Running the trials one at a
  time, or in separate containers, removes both.

## What this says about the task

Version 1 is not model breaking for Claude Sonnet 5: pass@1 is 1.00. No run failed on ambiguity; all five read every
requirement the way the grader does. The 4.0 s threshold is loose, and every trap in the task was recognized.
`../DIFFICULTY.md` lists the changes proposed for version 2.
