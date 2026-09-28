"""Run ONCE on the final chosen (Kp,Ki,Kq): the slow but authoritative control.stability_margins path
(full 200001-point grid) at all three speeds, to cross-check margins_report_fast's numbers before they
go in report.json. Expect ~100s per speed (FRD smoothing-spline construction dominates, not grid size
sensitivity) -- run in the background.
"""
import sys
import time
import loopgain as lg


def main(Kp, Ki, Kq):
    for spd in (20, 25, 32):
        plant = lg.load_plant(spd)
        L = lg.loop_L(lg.GRADER_OMEGA, Kp, Ki, Kq, plant)
        fast = lg.margins_report_fast(lg.GRADER_OMEGA, L)
        t0 = time.time()
        slow = lg.margins_report(lg.GRADER_OMEGA, L)
        dt = time.time() - t0
        print(f"{spd} m/s (slow call took {dt:.1f}s):")
        print(f"  fast: PM={fast['phase_margin_deg']:.4f} GM={fast['gain_margin_db']:.4f} "
              f"ok={fast['ok_pm45'] and fast['ok_gm6_increase'] and fast['ok_gm6_decrease']}")
        print(f"  slow: PM={slow['phase_margin_deg']:.4f} GM={slow['gain_margin_db']:.4f} "
              f"ok={slow['ok_pm45'] and slow['ok_gm6_increase'] and slow['ok_gm6_decrease']}")
        print(f"  diff: dPM={fast['phase_margin_deg']-slow['phase_margin_deg']:.5f} "
              f"dGM={fast['gain_margin_db']-slow['gain_margin_db']:.5f}")


if __name__ == "__main__":
    Kp, Ki, Kq = (float(x) for x in sys.argv[1:4])
    main(Kp, Ki, Kq)
