# Agent trials

**Status: five runs with Claude Sonnet 5 on 2026-09-26, all passed.** Results, failure taxonomy and isolation audit
are in `RESULTS.md`; `python summarize.py` recomputes pass@k from the graded runs in `runs/`.

## Protocol

- **The agent under test:** a coding agent in a clean folder that holds only the task `README.md` and
  `environment/`. It gets no reference, no grader and no hints.
- **Runs:** five per model by default. Every run is reported, including failures and runs that crash.
- **Grading:** `python grader/grade.py <run folder>/solution` on each run, unchanged between runs.
- **Logs:** the full transcript of each run is kept in `runs/<model>/<run number>/`, next to the grader's verdict.
- **Results:** `RESULTS.md` will give the model and its version, the number of runs, pass@k for k = 1 to N with
  the unbiased estimator, and a failure taxonomy taken from the transcripts.
