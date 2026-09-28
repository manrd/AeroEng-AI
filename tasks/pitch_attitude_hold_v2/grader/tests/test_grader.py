"""The grader must pass the reference and fail every broken solution with exactly the expected checks.

    python -m pytest grader/tests -q        (from the task folder; regenerate the cases with make_broken.py)
"""
import pathlib
import sys

import numpy as np
import pytest

TESTS = pathlib.Path(__file__).resolve().parent
TASK = TESTS.parents[1]
sys.path.insert(0, str(TASK / "grader"))
sys.path.insert(0, str(TASK / "environment"))
import aircraft_model as am  # noqa: E402
import grade  # noqa: E402
import truth_model as tm  # noqa: E402

EXPECTED = {
    "cruise_only": {"CLAIMS@20", "CLAIMS@25", "PHASE_MARGIN@32", "GAIN_MARGIN@32", "CLAIMS@32"},
    "linear_only": {"CLAIMS@20", "CLAIMS@25"},
    "wrong_trim": {"OVERSHOOT@20", "POSITION_LIMIT@20", "CLAIMS@20", "OVERSHOOT@25", "OVERSHOOT@32", "CLAIMS@32"},
    "high_gain": {"GAIN_MARGIN@32"},
    "sign_flipped": {"STABILITY@20", "STABILITY@25", "STABILITY@32"},
    "unstable_good_margins": {"STABILITY@20", "STABILITY@25", "STABILITY@32"},
    "slow_but_safe": {"SETTLING@20", "SETTLING@25", "SETTLING@32"},
    "unsupported_claims": {"CLAIMS@20"},
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


def test_grader_model_matches_the_environment_model():
    p = am.load_params()
    rng = np.random.default_rng(1)
    for _ in range(500):
        x = np.array([rng.uniform(15, 35), rng.uniform(-3, 5), rng.uniform(-1, 1), rng.uniform(-0.3, 0.4)])
        de, dth = rng.uniform(-0.5, 0.5), rng.uniform(0.2, 1.0)
        a = am.derivatives(p, x, [de, dth])
        b = np.array(tm.AIRCRAFT.derivatives(*x, de, dth))
        assert np.allclose(a, b, rtol=1e-10, atol=1e-10)


def test_grader_is_deterministic():
    a = grade.grade(TASK / "reference")["recomputed"]
    b = grade.grade(TASK / "reference")["recomputed"]
    assert a == b
