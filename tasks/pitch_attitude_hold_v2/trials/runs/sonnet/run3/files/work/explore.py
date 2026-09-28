"""Explore open-loop plant dynamics for the three airspeeds."""
import json
import pathlib
import numpy as np

HERE = pathlib.Path(__file__).parent
ENV = HERE.parent / "environment"

for spd in (20, 25, 32):
    d = json.loads((ENV / f"plant_{spd}.json").read_text())
    A = np.array(d["A"])
    B = np.array(d["B"])
    eigs = np.linalg.eigvals(A)
    print(f"--- {spd} m/s ---")
    print("trim delta_e (deg):", np.degrees(d["trim"]["delta_e_rad"]))
    print("eigenvalues:", eigs)
    for lam in eigs:
        if abs(lam.imag) > 1e-9:
            wn = abs(lam)
            zeta = -lam.real / wn
            print(f"  mode wn={wn:.4f} rad/s, zeta={zeta:.4f}, pole={lam:.4f}")
        else:
            print(f"  real pole={lam.real:.5f}  (tau={-1/lam.real if lam.real!=0 else float('inf'):.3f} s)")
    print("B:", B.ravel())
