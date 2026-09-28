"""Cross-check the fast find_margins() against control.stability_margins on a grid small enough
that control's implementation is fast, plus a timing test on the full 200001-point grid."""
import time
import numpy as np
import control
from loop import load_plant, loop_gain, find_margins, OMEGA_GRID

A, B, C, trim = load_plant(20)
omega_small = np.logspace(-3, 3, 4001)

for Kp, Ki, Kq in [(-1, -0.3, -0.3), (-2, -1, -0.5), (-0.5, -0.05, -0.1)]:
    L = loop_gain(Kp, Ki, Kq, A, B, C, omega_small)
    mag, phase = np.abs(L), np.degrees(np.angle(L))
    GM, PM, SM, wpc_c, wgc_c, wms = control.stability_margins((mag, phase, omega_small), returnall=True)
    GM_db_c = 20 * np.log10(GM)

    GM_db_f, PM_f, wpc_f, wgc_f = find_margins(L, omega_small)

    print(f"Kp={Kp} Ki={Ki} Kq={Kq}")
    print("  control wpc:", np.round(wpc_c, 4), "GM_db:", np.round(GM_db_c, 3))
    print("  fast    wpc:", np.round(wpc_f, 4), "GM_db:", np.round(GM_db_f, 3))
    print("  control wgc:", np.round(wgc_c, 4), "PM:", np.round(PM, 3))
    print("  fast    wgc:", np.round(wgc_f, 4), "PM:", np.round(PM_f, 3))
    print()

print("Timing on the full 200001-pt grid:")
t0 = time.time()
for Kp, Ki, Kq in [(-1, -0.3, -0.3), (-2, -1, -0.5), (-0.5, -0.05, -0.1)]:
    L = loop_gain(Kp, Ki, Kq, A, B, C, OMEGA_GRID)
    GM_db_f, PM_f, wpc_f, wgc_f = find_margins(L, OMEGA_GRID)
    print(f"  Kp={Kp}: worst GM_db={np.min(np.abs(GM_db_f)):.2f}, worst PM={np.min(PM_f):.2f}, "
          f"n_phase_cross={len(wpc_f)}, n_gain_cross={len(wgc_f)}")
print("total time for 3 evals at 200001 pts:", time.time() - t0)
