# Agent trials

**Status: five runs with Claude Sonnet 5 on 2026-09-27, all passed.** Results, failure taxonomy and isolation audit
are in `RESULTS.md`; `python summarize.py` recomputes pass@k from the graded runs in `runs/`.

## Protocol

The same as version 1, with one change learned there: the runs go **one at a time**, so that no run can see or stop
another.
- **The agent under test:** a coding agent in a clean folder that holds only the task `README.md` and
  `environment/`. It gets no reference, no grader and no hints.
- **Runs:** five with Claude Sonnet 5. Every run is reported, including failures and runs that crash.
- **Grading:** `python grader/grade.py <run folder>/solution` on each run, unchanged between runs.
- **Logs:** the agent's steps are kept in `runs/<model>/<run number>/log.md`, sanitized as in version 1, next to the
  grader's verdict and the text files the agent wrote.
- **Results:** `RESULTS.md` will give pass@k, the failure taxonomy and the isolation audit; `python summarize.py`
  recomputes pass@k.
