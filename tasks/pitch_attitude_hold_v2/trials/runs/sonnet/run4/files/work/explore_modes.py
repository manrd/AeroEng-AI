import json
import pathlib
import numpy as np

HERE = pathlib.Path(__file__).parent
ENV = HERE.parent / "environment"

for spd in (20, 25, 32):
    d = json.loads((ENV / f"plant_{spd}.json").read_text())
    A = np.array(d["A"])
    B = np.array(d["B"])
    eig = np.linalg.eigvals(A)
    print(f"--- {spd} m/s ---")
    print("eigenvalues:", eig)
    for lam in eig:
        if abs(lam.imag) > 1e-9:
            wn = abs(lam)
            zeta = -lam.real / wn
            print(f"  complex pair: wn={wn:.4f} rad/s, zeta={zeta:.4f}")
        else:
            print(f"  real pole: {lam.real:.5f}  (tau={-1/lam.real if lam.real!=0 else float('inf'):.3f} s)")
    print("B:", B.ravel())
    print("trim delta_e (deg):", np.degrees(d["trim"]["delta_e_rad"]))
