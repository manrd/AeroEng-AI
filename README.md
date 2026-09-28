# Engineering AI benchmarks

Simulation based engineering design tasks for evaluating AI coding agents. Each task has competing constraints,
an explicit optimization target, a validated reference solution and an objective autograder that is itself tested
against deliberately broken solutions.

| Task | Domain | Tools | Status |
|---|---|---|---|
| [Pitch attitude hold for a small UAV](tasks/pitch_attitude_hold/README.md) | flight control | python-control, numpy, scipy | version 1: reference, validation, grader, and five agent trials (Claude Sonnet 5, all passed; [results](tasks/pitch_attitude_hold/trials/RESULTS.md)) |
| [Pitch attitude hold across the speed range](tasks/pitch_attitude_hold_v2/README.md) | flight control, nonlinear truth model | python-control, numpy, scipy | version 2: reference, validation, grader, and five agent trials (Claude Sonnet 5, all passed; [results](tasks/pitch_attitude_hold_v2/trials/RESULTS.md)) |

## Layout of a task

| Folder or file | Contents |
|---|---|
| `README.md` | The task exactly as the agent receives it |
| `environment/` | Model files and the scripts that generated them |
| `reference/` | The reference solution, how it was designed, and how it was validated (`VALIDATION.md`) |
| `grader/` | The autograder and its truth model; `grader/tests/` holds the broken solutions it must reject |
| `trials/` | Agent runs, their verdicts and the failure analysis |
| `DIFFICULTY.md` | What makes the task hard, and how it was calibrated |

## Reproduce

With Python 3.12:

```
python -m pip install -r requirements.txt
cd tasks/pitch_attitude_hold
python environment/aircraft_model.py
python reference/design_reference.py
python reference/validate_reference.py
python grader/tests/make_broken.py
python -m pytest grader/tests -q
python grader/grade.py reference
```

The same steps work in `tasks/pitch_attitude_hold_v2`. On 10 cores the reference design search takes about a
minute for version 1 and about ten minutes for version 2.

## Sources

- Aerosonde parameters: R. W. Beard and T. W. McLain, *Small Unmanned Aircraft: Theory and Practice*, Princeton
  University Press, 2012, with the values published in
  [byu-magicc/mavsim_public](https://github.com/byu-magicc/mavsim_public) (GPL 3.0). Only the numerical values are
  used; the model code here is an independent implementation.

## Author

Manuel Alejandro Rodríguez Díaz, aeronautical engineer (PhD, ITA).
[linkedin.com/in/m-a-rodriguez-d](https://www.linkedin.com/in/m-a-rodriguez-d)

Built with AI coding agents. The models and references are checked by independent methods (each task's
`reference/VALIDATION.md`), and each grader by the broken solutions in its `grader/tests/`.

## License

- **Code:** the Python files, and the JSON files they read and write, are under the MIT License ([LICENSE](LICENSE)).
- **Everything else:** the documentation, task statements, results, trial logs and figures (the Markdown and PNG
  files) are under Creative Commons Attribution 4.0 ([LICENSE-CC-BY-4.0.md](LICENSE-CC-BY-4.0.md)).
- **Not covered:** third party material keeps its own terms. The trial logs quote output from tools such as
  python-control, and the Aerosonde parameter values are credited under Sources. A portfolio PDF attached to a
  release is not covered either; its photographs belong to their owners.
