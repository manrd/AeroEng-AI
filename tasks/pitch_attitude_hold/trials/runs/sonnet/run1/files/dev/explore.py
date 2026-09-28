import json
import numpy as np
import control as ct

np.set_printoptions(precision=6, suppress=False)

plant = json.loads(open("../environment/plant.json").read())
A = np.array(plant["A"])
B = np.array(plant["B"])
C = np.array(plant["C"])
D = np.array(plant["D"])

print("A=\n", A)
print("B=\n", B)
print("C=\n", C)
print("D=\n", D)

eig = np.linalg.eigvals(A)
print("\nOpen loop eigenvalues of A:")
for lam in eig:
    wn = abs(lam)
    zeta = -lam.real/wn if wn>0 else float('nan')
    print(f"  {lam:.6f}   wn={wn:.5f} rad/s  zeta={zeta:.5f}")

sys = ct.ss(A, B, C, D)
print("\nis stable (open loop)?", np.all(np.real(eig) < 0))

# transfer functions theta/delta_e and q/delta_e
sys_theta = ct.ss2tf(ct.ss(A, B, C[0:1,:], D[0:1,:]))
sys_q = ct.ss2tf(ct.ss(A, B, C[1:2,:], D[1:2,:]))
print("\nP_theta(s) = theta/delta_e:")
print(sys_theta)
print("\nP_q(s) = q/delta_e:")
print(sys_q)

print("\nP_theta poles:", ct.poles(sys_theta))
print("P_theta zeros:", ct.zeros(sys_theta))
print("P_q poles:", ct.poles(sys_q))
print("P_q zeros:", ct.zeros(sys_q))

# DC gains
print("\nDC gain P_theta:", sys_theta(0))
print("DC gain P_q:", sys_q(0))

# trim info
print("\ntrim:", plant["trim"])
print("trim delta_e deg:", np.degrees(plant["trim"]["delta_e_rad"]))
