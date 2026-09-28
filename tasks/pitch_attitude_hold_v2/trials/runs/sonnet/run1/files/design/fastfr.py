"""Fast vectorized state-space frequency response via eigendecomposition, plus a check against
python-control's own frequency_response for correctness."""
import time
import json
import numpy as np
import control


def freqresp_eig(A, B, C, omega):
    """G(jw) = C (jwI - A)^-1 B for a SISO-input system, vectorized over omega.

    Returns array shape (n_outputs, len(omega)) complex.
    """
    eigvals, V = np.linalg.eig(A)
    Vinv = np.linalg.inv(V)
    CV = C @ V            # (n_out, n)
    VinvB = Vinv @ B       # (n, 1)
    coeff = CV * VinvB[:, 0]   # (n_out, n) broadcasting column
    # denom[i, k] = 1j*omega[k] - eigvals[i]
    denom = 1j * omega[None, :] - eigvals[:, None]   # (n, n_omega)
    # G[o,k] = sum_i coeff[o,i] / denom[i,k]
    G = coeff @ (1.0 / denom)   # (n_out, n) @ (n, n_omega) -> (n_out, n_omega)
    return G


if __name__ == "__main__":
    d = json.load(open("environment/plant_20.json"))
    A = np.array(d["A"]); B = np.array(d["B"]); C = np.array(d["C"]); Dm = np.array(d["D"])
    omega = np.logspace(np.log10(0.001), np.log10(1000), 200001)

    t0 = time.time()
    G = freqresp_eig(A, B, C, omega)
    t1 = time.time()
    print("fast eig method time:", t1 - t0, "shape", G.shape)

    # cross check against control library on a coarser grid (for speed of the check)
    omega_small = np.logspace(np.log10(0.001), np.log10(1000), 2001)
    sys = control.ss(A, B, C, Dm)
    resp = sys.frequency_response(omega_small)
    Gc = resp.complex  # shape (n_out, n_in, n_omega) typically
    Gc = np.squeeze(Gc, axis=1)
    Gf = freqresp_eig(A, B, C, omega_small)
    err = np.max(np.abs(Gc - Gf))
    print("max abs error vs control library:", err)
    print("max relative error:", np.max(np.abs(Gc - Gf) / (np.abs(Gc) + 1e-12)))
