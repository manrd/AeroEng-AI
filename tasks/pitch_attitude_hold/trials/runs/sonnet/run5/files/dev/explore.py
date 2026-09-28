import json
import numpy as np
import control as ct

plant = json.loads(open("environment/plant.json").read())
A = np.array(plant["A"])
B = np.array(plant["B"])
C = np.array(plant["C"])
D = np.array(plant["D"])
trim = plant["trim"]
print("trim:", trim)
print("trim delta_e deg:", np.degrees(trim["delta_e_rad"]))
print("trim theta deg:", np.degrees(trim["theta_rad"]))

print("A=\n", A)
print("B=\n", B)
print("eigenvalues of A:", np.linalg.eigvals(A))

sys = ct.ss(A, B, C, D)
print(sys)

# transfer functions theta/delta_e and q/delta_e
sys_theta = ct.ss(A, B, C[0:1, :], D[0:1, :])
sys_q = ct.ss(A, B, C[1:2, :], D[1:2, :])
tf_theta = ct.tf(sys_theta)
tf_q = ct.tf(sys_q)
print("theta/delta_e TF:", tf_theta)
print("q/delta_e TF:", tf_q)

print("poles theta:", ct.poles(sys_theta))
print("zeros theta:", ct.zeros(sys_theta))
print("poles q:", ct.poles(sys_q))
print("zeros q:", ct.zeros(sys_q))

# modes
for lam in np.linalg.eigvals(A):
    wn = abs(lam)
    zeta = -lam.real/wn if wn>0 else float('nan')
    print(f"eig={lam:.5f}  wn={wn:.5f} zeta={zeta:.5f}")
