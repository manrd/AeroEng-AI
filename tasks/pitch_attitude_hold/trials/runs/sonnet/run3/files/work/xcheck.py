import sys
sys.path.insert(0, "work")
import numpy as np
import control as ct
import core

num_theta, den_theta = core.theta_tf()
print("Gtheta num", num_theta, "den", den_theta)

def trial(Kp, Ki, Kq, n_pade=10):
    # exact-delay margins (fewer points for speed during this check)
    res = core.compute_margins(Kp, Ki, Kq, num_theta, den_theta, n=40001)
    print(f"[exact]  PM={res['phase_margin_deg']:.2f} deg  GM_incr={res['gain_margin_incr_db']:.2f} dB  GM_decr={res['gain_margin_decr_db']:.2f} dB")
    print("   pm_all:", [f"{x:.1f}" for x in res['pm_all'][:6]])
    print("   gm_incr_freqs:", [f"{x:.2f}" for x in res['gm_incr_freqs'][:6]])
    print("   gm_decr_freqs:", [f"{x:.2f}" for x in res['gm_decr_freqs'][:6]])

    # pade cross check
    num_p, den_p = ct.pade(core.DELAY, n_pade)
    Gtheta = ct.tf(num_theta, den_theta)
    Act = ct.tf([1.0], [core.TAU_ACT, 1.0])
    Delay = ct.tf(num_p, den_p)
    Cs = ct.tf([Kq, Kp, Ki], [1.0, 0.0])  # (Kq s^2 + Kp s + Ki)/s
    L = Gtheta * Act * Delay * Cs
    gm, pm, wg, wp = ct.margin(L)
    gm_db = 20*np.log10(gm) if np.isfinite(gm) else np.inf
    print(f"[pade{n_pade}] PM={pm:.2f} deg (wgc={wg:.3f})  GM={gm_db:.2f} dB (wpc={wp:.3f})")
    print()

trial(3.0, 3.0, 0.2)
trial(8.0, 6.0, 0.15)
trial(1.0, 1.0, 0.5)
