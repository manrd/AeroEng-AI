import sys
sys.path.insert(0, "work")
import numpy as np
import core

num_theta, den_theta = core.theta_tf()

def P2(w):
    """-Act(jw)*delay(jw)*Gtheta(jw): the 'positive' plant seen by the PID-like compensator."""
    s = 1j*w
    Gtheta = np.polyval(num_theta, s) / np.polyval(den_theta, s)
    Act = 1.0/(core.TAU_ACT*s + 1.0)
    delay = np.exp(-s*core.DELAY)
    return -Act*delay*Gtheta

def design_at_crossover(wc, N, pm_target_deg=45.0):
    Mp = abs(P2(wc))
    phip = np.angle(P2(wc), deg=True)
    ang_target = -180.0 + pm_target_deg - phip
    mag_target = 1.0/Mp
    Ctarget = mag_target*np.exp(1j*np.radians(ang_target))
    kp = Ctarget.real
    X = Ctarget.imag  # = kq*wc - ki/wc
    ki = kp*wc/N
    kq = (X + ki/wc)/wc
    return kp, ki, kq

for wc in [1,2,3,4,5,6,7,8,9,10,12]:
    for N in [6, 10, 15]:
        kp,ki,kq = design_at_crossover(wc, N, pm_target_deg=45.0)
        Kp,Ki,Kq = -kp,-ki,-kq
        res = core.compute_margins(Kp,Ki,Kq, num_theta, den_theta, n=20001)
        print(f"wc={wc:2d} N={N:2d}: kp={kp:7.3f} ki={ki:7.3f} kq={kq:7.4f}  "
              f"PM_min={res['phase_margin_deg']:7.2f} GM_incr={res['gain_margin_incr_db']:7.2f} GM_decr={res['gain_margin_decr_db']:7.2f}")
