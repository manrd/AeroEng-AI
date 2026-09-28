"""The grader must pass the reference and fail every broken solution for the intended reason.

    python -m pytest grader/tests -q        (from the task folder; regenerate the cases with make_broken.py)
"""
import pathlib
import sys

import pytest

TESTS = pathlib.Path(__file__).resolve().parent
TASK = TESTS.parents[1]
sys.path.insert(0, str(TASK / "grader"))
import grade  # noqa: E402

# case: the exact set of checks it must fail
EXPECTED = {
    "sign_flipped": {"STABILITY"},
    "ignores_delay": {"PHASE_MARGIN", "GAIN_MARGIN", "CLAIMS"},
    "no_integrator": {"SETTLING", "CLAIMS"},
    "full_setpoint_weight": {"OVERSHOOT", "CLAIMS"},
    "q_in_degrees": {"PHASE_MARGIN", "GAIN_MARGIN", "CLAIMS"},
    "slow_but_safe": {"SETTLING"},
    "unsupported_claims": {"CLAIMS"},
    "perturbation_limit": {"OVERSHOOT", "POSITION_LIMIT", "CLAIMS"},
    "malformed": {"SCHEMA"},
}


def test_reference_passes():
    out = grade.grade(TASK / "reference")
    assert out["verdict"] == "PASS", out["checks"]


def test_every_broken_case_is_covered():
    on_disk = {p.name for p in (TESTS / "broken").iterdir() if p.is_dir()}
    assert on_disk == set(EXPECTED)


@pytest.mark.parametrize("case", sorted(EXPECTED))
def test_broken_case_fails_exactly_the_expected_checks(case):
    out = grade.grade(TESTS / "broken" / case)
    assert out["verdict"] == "FAIL"
    assert set(out["failed"]) == EXPECTED[case], f"{case}: expected {EXPECTED[case]}, got {set(out['failed'])}"


def test_grader_is_deterministic():
    a = grade.grade(TASK / "reference")["recomputed"]
    b = grade.grade(TASK / "reference")["recomputed"]
    assert a == b
