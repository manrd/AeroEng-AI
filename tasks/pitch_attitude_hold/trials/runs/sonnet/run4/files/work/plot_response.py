import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from common import simulate, requirements_from_sim, TRIM_DELTA_E_DEG

Kp, Ki, Kq, b = [float(v) for v in sys.argv[1:5]]
outpath = sys.argv[5] if len(sys.argv) > 5 else "response.png"

sim = simulate(Kp, Ki, Kq, b, t_end=20.0)
req = requirements_from_sim(sim)
t = sim["t"]
theta_deg = np.degrees(sim["theta_rad"])
q_deg = np.degrees(sim["q_rad_s"])
elev_cmd_deg = TRIM_DELTA_E_DEG + np.degrees(sim["delta_cmd_rad"])
elev_actual_deg = TRIM_DELTA_E_DEG + np.degrees(sim["delta_rad"])

fig, axs = plt.subplots(3, 1, figsize=(9, 9), sharex=True)
axs[0].plot(t, theta_deg, label="theta (deg)")
axs[0].axhline(5.0, color="k", ls="--", lw=0.8)
axs[0].axhline(5.5, color="r", ls=":", lw=0.8)
axs[0].axhline(4.9, color="g", ls=":", lw=0.8)
axs[0].axhline(5.1, color="g", ls=":", lw=0.8)
axs[0].set_ylabel("theta (deg)")
axs[0].set_xlim(0, 20)
axs[0].grid(True, alpha=0.3)
axs[0].set_title(f"Kp={Kp:.4f} Ki={Ki:.4f} Kq={Kq:.4f} b={b:.4f}\n"
                  f"overshoot={req['overshoot_pct']:.2f}% settle={req['settling_time_s']:.3f}s "
                  f"maxE={req['max_elevator_deg']:.2f}deg")

axs[1].plot(t, q_deg, label="q (deg/s)")
axs[1].set_ylabel("q (deg/s)")
axs[1].grid(True, alpha=0.3)

axs[2].plot(t, elev_cmd_deg, label="elevator command (deg)")
axs[2].plot(t, elev_actual_deg, label="elevator actual (deg)", alpha=0.7)
axs[2].axhline(25, color="r", ls=":", lw=0.8)
axs[2].axhline(-25, color="r", ls=":", lw=0.8)
axs[2].set_ylabel("elevator (deg)")
axs[2].set_xlabel("t (s)")
axs[2].legend()
axs[2].grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(outpath, dpi=110)
print("saved", outpath)
print(req)
