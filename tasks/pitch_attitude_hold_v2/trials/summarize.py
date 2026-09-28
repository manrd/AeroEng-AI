"""pass@k from the graded runs in runs/<model>/run*/grade.json.

    python summarize.py

Uses the unbiased estimator pass@k = 1 - C(n - c, k) / C(n, k), with n runs and c passes (Chen et al., 2021).
"""
import json
import pathlib
from math import comb

HERE = pathlib.Path(__file__).resolve().parent


def pass_at_k(n, c, k):
    return 1.0 if n - c < k else 1.0 - comb(n - c, k) / comb(n, k)


def main():
    for model_dir in sorted(p for p in (HERE / "runs").iterdir() if p.is_dir()):
        runs = sorted(model_dir.glob("run*/grade.json"), key=lambda p: int(p.parent.name[3:]))
        verdicts = [json.loads(p.read_text(encoding="utf-8")) for p in runs]
        n, c = len(verdicts), sum(v["verdict"] == "PASS" for v in verdicts)
        print(f"## {model_dir.name}: {c} of {n} runs pass")
        print("| k | " + " | ".join(str(k) for k in range(1, n + 1)) + " |")
        print("|---|" + "---|" * n)
        print("| pass@k | " + " | ".join(f"{pass_at_k(n, c, k):.2f}" for k in range(1, n + 1)) + " |")
        for p, v in zip(runs, verdicts):
            ts = v["recomputed"].get("worst_settling_time_s")
            print(f"- {p.parent.name}: {v['verdict']}"
                  + (f", failed {', '.join(v['failed'])}" if v["failed"] else "")
                  + (f", worst settling {ts:.3f} s" if isinstance(ts, (int, float)) else ""))


if __name__ == "__main__":
    main()
