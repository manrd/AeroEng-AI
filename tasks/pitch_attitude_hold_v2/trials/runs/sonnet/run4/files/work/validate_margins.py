"""Cross-check find_all_margins_fast (my vectorized crossing finder) against control.stability_margins
(the authoritative, presumably grader-matching method), on a few test gain sets and all three plants,
using a moderate grid (fast enough for the FRD/spline path to complete quickly) since this validates
the *margin formula*, not grid resolution / crossing-detection completeness (that's a separate concern,
handled by always using the full 200001-point grader grid for both methods in the final check).
"""
import numpy as np
import loopgain as lg

TEST_GAINS = [
    (-1.0, -0.5, -0.5),
    (-2.0, -1.0, 1.0),
    (0.3, 0.9, 2.5),   # the messy multi-crossing case found earlier
    (-0.5, -3.0, -2.0),
]

OMEGA = np.logspace(np.log10(0.001), np.log10(1000.0), 8001)


def compare(Kp, Ki, Kq, spd):
    plant = lg.load_plant(spd)
    L = lg.loop_L(OMEGA, Kp, Ki, Kq, plant)
    gcs_fast, pcs_fast = lg.find_all_margins_fast(OMEGA, L)
    m_slow = lg.all_margins(OMEGA, L)
    gcs_slow, pcs_slow = m_slow["gain_crossings"], m_slow["phase_crossings"]

    print(f"Kp={Kp} Ki={Ki} Kq={Kq} spd={spd}")
    print("  fast gcs:", [(round(w, 4), round(p, 3)) for w, p in gcs_fast])
    print("  slow gcs:", [(round(w, 4), round(p, 3)) for w, p in gcs_slow])
    print("  fast pcs:", [(round(w, 4), round(p, 3)) for w, p in pcs_fast])
    print("  slow pcs:", [(round(w, 4), round(p, 3)) for w, p in pcs_slow])

    ok = True
    if len(gcs_fast) != len(gcs_slow) or len(pcs_fast) != len(pcs_slow):
        ok = False
    else:
        for (wf, pf), (ws, ps) in zip(gcs_fast, gcs_slow):
            if abs(wf - ws) > 1e-2 * max(1, ws) or abs(pf - ps) > 0.5:
                ok = False
        for (wf, gf), (ws, gs) in zip(pcs_fast, pcs_slow):
            if abs(wf - ws) > 1e-2 * max(1, ws) or abs(gf - gs) > 0.5:
                ok = False
    print("  AGREE:", ok)
    print()
    return ok


if __name__ == "__main__":
    all_ok = True
    for Kp, Ki, Kq in TEST_GAINS:
        for spd in (20, 25, 32):
            all_ok &= compare(Kp, Ki, Kq, spd)
    print("ALL AGREE:", all_ok)
