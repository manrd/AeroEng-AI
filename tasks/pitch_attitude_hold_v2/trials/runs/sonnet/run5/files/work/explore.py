"""Explore plant characteristics: poles, zeros, DC gains, short period modes."""
import json
import pathlib
import numpy as np

HERE = pathlib.Path(__file__).parent
ENV = HERE.parent / "environment"

SPEEDS = (20, 25, 32)

for spd in SPEEDS:
    plant = json.loads((ENV / f"plant_{spd}.json").read_text())
    A = np.array(plant["A"])
    B = np.array(plant["B"])
    trim = plant["trim"]
    eigs = np.linalg.eigvals(A)
    print(f"--- {spd} m/s ---")
    print("trim delta_e (deg):", np.degrees(trim["delta_e_rad"]), "theta (deg):", np.degrees(trim["theta_rad"]))
    print("eigenvalues:", eigs)
    for lam in eigs:
        if abs(lam.imag) > 1e-9:
            wn = abs(lam)
            zeta = -lam.real/wn
            print(f"  mode wn={wn:.4f} rad/s  zeta={zeta:.4f}  (period {2*np.pi/wn:.2f}s)")
        else:
            print(f"  real pole: {lam.real:.5f}  (tau={-1/lam.real:.3f}s)" if lam.real!=0 else f"  real pole: {lam.real:.5f}")
    # transfer function residues: P(s) = C (sI-A)^-1 B = sum_i (C v_i)(w_i^T B)/(s-lam_i)  using left/right eigenvectors
    w_eig, V = np.linalg.eig(A)
    Vinv = np.linalg.inv(V)
    Ctheta = np.array([0,0,0,1.0])
    Cq = np.array([0,0,1.0,0])
    CVtheta = Ctheta @ V
    CVq = Cq @ V
    VinvB = Vinv @ B[:,0]
    print("theta residues:", CVtheta*VinvB)
    print("q residues:", CVq*VinvB)
    # DC gain (s=0): sum residue/(-lam)
    dc_theta = np.sum(CVtheta*VinvB/(-w_eig))
    dc_q = np.sum(CVq*VinvB/(-w_eig))
    print("DC gain theta/delta_e (should blow up if pole at origin; else finite):", dc_theta)
    print("DC gain q/delta_e:", dc_q)
    print()
