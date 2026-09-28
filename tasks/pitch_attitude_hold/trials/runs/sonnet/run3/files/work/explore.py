import json, numpy as np
import control as ct

p = json.loads(open("environment/plant.json").read())
A = np.array(p["A"]); B = np.array(p["B"]); C = np.array(p["C"]); D = np.array(p["D"])
trim = p["trim"]
print("A=\n", A)
print("B=\n", B)
print("trim=", trim)
print("trim delta_e deg=", np.degrees(trim["delta_e_rad"]))

eig = np.linalg.eigvals(A)
print("open loop eigenvalues:", eig)
for lam in eig:
    if abs(lam.imag) > 1e-9:
        wn = abs(lam)
        zeta = -lam.real/wn
        print(f"  mode wn={wn:.4f} rad/s zeta={zeta:.4f}")
    else:
        print(f"  real pole {lam.real:.4f}  tau={-1/lam.real if lam.real!=0 else np.inf:.4f}s")

# Gtheta(s): theta / delta_e
Ctheta = np.array([[0.,0.,0.,1.]])
sys_theta = ct.ss(A, B, Ctheta, [[0.]])
tf_theta = ct.ss2tf(sys_theta)
print("Gtheta(s) =", tf_theta)

# Gq(s): q/delta_e, should equal s*Gtheta(s)
Cq = np.array([[0.,0.,1.,0.]])
sys_q = ct.ss(A,B,Cq,[[0.]])
tf_q = ct.ss2tf(sys_q)
print("Gq(s) =", tf_q)
