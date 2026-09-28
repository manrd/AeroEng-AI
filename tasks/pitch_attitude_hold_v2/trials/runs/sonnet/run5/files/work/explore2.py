"""Get P_theta(s) as an explicit rational transfer function per speed, and confirm the
structural identity P_theta(s) = P_q(s)/s, i.e. that the whole controller collapses to a
plain PID acting on P_theta: L(s) = Act(s)*Delay(s)*P_theta(s)*(Kq s^2 + Kp s + Ki)/s.
"""
import sys
sys.path.insert(0, "<run>/work")
import numpy as np
import control as ct
from lib import PLANTS, SPEEDS

for spd in SPEEDS:
    pl = PLANTS[spd]
    A, B = pl.A, pl.B.reshape(-1, 1)
    Ctheta = np.array([[0, 0, 0, 1.0]])
    Cq = np.array([[0, 0, 1.0, 0]])
    sys_th = ct.ss(A, B, Ctheta, 0)
    sys_q = ct.ss(A, B, Cq, 0)
    tf_th = ct.tf(sys_th)
    tf_q = ct.tf(sys_q)
    print(f"--- {spd} m/s ---")
    print("P_theta poles:", np.sort_complex(ct.poles(tf_th)))
    print("P_theta zeros:", np.sort_complex(ct.zeros(tf_th)))
    print("P_theta gain (num/den leading):", tf_th)
    print("P_q zeros:", np.sort_complex(ct.zeros(tf_q)))
    print("DC gain P_theta(0):", float(np.real(tf_th(1e-9))))
    print()
