"""Core model: plant loading, frequency response, discretization, time-domain simulation, margins."""
import json
import pathlib
import numpy as np

ENV = pathlib.Path(__file__).resolve().parent.parent / "environment"

DEG = np.pi / 180.0

def load_plant():
    d = json.loads((ENV / "plant.json").read_text(encoding="utf-8"))
    A = np.array(d["A"], dtype=float)
    B = np.array(d["B"], dtype=float)
    C = np.array(d["C"], dtype=float)
    D = np.array(d["D"], dtype=float)
    trim = d["trim"]
    return A, B, C, D, trim


# ---- constants from README (exact, not the rounded README text) ----
ACT_TAU = 0.05          # s
RATE_LIMIT = 60.0 * DEG  # rad/s
POS_LIMIT_ABS = 25.0 * DEG  # rad, absolute
DELAY_S = 0.040          # s
DT = 0.001                # s, grader fixed step
N_STEPS = 20000            # 20 s / 1 ms
DELAY_STEPS = 40           # exactly 40 steps


def pert_limits(trim_delta_e_rad):
    """Perturbation elevator limits (rad) equivalent to +-25 deg absolute."""
    lo = -POS_LIMIT_ABS - trim_delta_e_rad
    hi = POS_LIMIT_ABS - trim_delta_e_rad
    return lo, hi


def plant_freq_response(A, B, C, w):
    """Batched exact frequency response C (jw I - A)^-1 B for all w (array). Returns shape (len(w), C.shape[0])."""
    n = A.shape[0]
    I = np.eye(n)
    jw = 1j * w
    # M[k] = jw[k]*I - A   shape (N,n,n)
    M = jw[:, None, None] * I[None, :, :] - A[None, :, :]
    Bc = np.broadcast_to(B[None, :, :], (len(w), n, B.shape[1]))
    X = np.linalg.solve(M, Bc)         # (N, n, 1)
    Y = np.einsum('on,knp->kop', C, X)  # (N, noutputs, 1)
    return Y[:, :, 0]  # (N, noutputs)


def discretize(A, B, dt=DT):
    """Exact zero-order-hold discretization via matrix exponential of the augmented matrix."""
    n = A.shape[0]
    m = B.shape[1]
    M = np.zeros((n + m, n + m))
    M[:n, :n] = A
    M[:n, n:] = B
    from scipy.linalg import expm
    Md = expm(M * dt)
    Ad = Md[:n, :n]
    Bd = Md[:n, n:]
    return Ad, Bd


def simulate(Kp, Ki, Kq, b, A, B, trim_delta_e_rad, theta_cmd_rad,
             dt=DT, n_steps=N_STEPS, delay_steps=DELAY_STEPS, Ad=None, Bd=None):
    """Discrete-time simulation replicating the grader's method exactly.

    Returns dict of time histories (length n_steps+1): t, theta_deg, q_radps, delta_cmd_deg_abs, delta_actual_deg_abs

    If Ad/Bd (already discretized at dt) are supplied, skips the (relatively expensive) expm call.
    """
    if Ad is None or Bd is None:
        Ad, Bd = discretize(A, B, dt)
    n = A.shape[0]
    pert_lo, pert_hi = pert_limits(trim_delta_e_rad)

    # unrolled 4-state core for speed (plain python floats: much faster than numpy in a tight
    # 20000-iteration loop for objects this small)
    a = [[float(Ad[i, j]) for j in range(n)] for i in range(n)]
    bcol = [float(Bd[i, 0]) for i in range(n)]

    x0 = x1 = x2 = x3 = 0.0
    delta = 0.0
    I = 0.0

    theta_hist = [0.0] * (n_steps + 1)
    q_hist = [0.0] * (n_steps + 1)
    cmd_hist = [0.0] * (n_steps + 1)
    act_hist = [0.0] * (n_steps + 1)

    theta_hist[0] = x3
    q_hist[0] = x2
    act_hist[0] = delta

    inv_tau = 1.0 / ACT_TAU
    rate_lim = RATE_LIMIT
    bthetacmd = b * theta_cmd_rad

    for k in range(0, n_steps + 1):
        km = k - delay_steps
        theta_m = theta_hist[km] if km >= 0 else 0.0
        q_m = q_hist[km] if km >= 0 else 0.0

        cmd = Kp * (bthetacmd - theta_m) + Ki * I - Kq * q_m
        cmd_hist[k] = cmd

        if k == n_steps:
            break

        cmd_sat = cmd
        if cmd_sat < pert_lo:
            cmd_sat = pert_lo
        elif cmd_sat > pert_hi:
            cmd_sat = pert_hi
        rate_sat = (cmd_sat - delta) * inv_tau
        if rate_sat < -rate_lim:
            rate_sat = -rate_lim
        elif rate_sat > rate_lim:
            rate_sat = rate_lim
        delta_next = delta + dt * rate_sat
        if delta_next < pert_lo:
            delta_next = pert_lo
        elif delta_next > pert_hi:
            delta_next = pert_hi

        nx0 = a[0][0] * x0 + a[0][1] * x1 + a[0][2] * x2 + a[0][3] * x3 + bcol[0] * delta
        nx1 = a[1][0] * x0 + a[1][1] * x1 + a[1][2] * x2 + a[1][3] * x3 + bcol[1] * delta
        nx2 = a[2][0] * x0 + a[2][1] * x1 + a[2][2] * x2 + a[2][3] * x3 + bcol[2] * delta
        nx3 = a[3][0] * x0 + a[3][1] * x1 + a[3][2] * x2 + a[3][3] * x3 + bcol[3] * delta

        I_next = I + dt * (theta_cmd_rad - theta_m)

        x0, x1, x2, x3 = nx0, nx1, nx2, nx3
        delta = delta_next
        I = I_next

        theta_hist[k + 1] = x3
        q_hist[k + 1] = x2
        act_hist[k + 1] = delta

    theta_hist = np.array(theta_hist)
    q_hist = np.array(q_hist)
    cmd_hist = np.array(cmd_hist)
    act_hist = np.array(act_hist)
    t = np.arange(n_steps + 1) * dt
    trim_deg = np.degrees(trim_delta_e_rad)
    return {
        "t": t,
        "theta_deg": np.degrees(theta_hist),
        "q_radps": q_hist,
        "cmd_abs_deg": trim_deg + np.degrees(cmd_hist),
        "act_abs_deg": trim_deg + np.degrees(act_hist),
        "cmd_pert_rad": cmd_hist,
    }


def loop_gain(w, Kp, Ki, Kq, Ptheta_jw, Pq_jw, delay_s=DELAY_S, act_tau=ACT_TAU):
    jw = 1j * w
    Aact = 1.0 / (1.0 + act_tau * jw)
    Delay = np.exp(-jw * delay_s)
    C_ = (Kp + Ki / jw) * Ptheta_jw + Kq * Pq_jw
    return Aact * Delay * C_


def margins_from_L(w, L):
    """Replicate the grader's margin computation: gain margins at every -180 phase crossing (both
    directions), phase margins at every 0 dB gain crossing. Fully vectorized.

    Returns dict with worst-case phase_margin_deg, gain_margin_up_db (against increase),
    gain_margin_down_db (against decrease), and full crossing lists for diagnostics.
    """
    mag_db = 20 * np.log10(np.abs(L))
    phase_deg = np.degrees(np.unwrap(np.angle(L)))
    logw = np.log(w)

    # --- gain crossovers: |L| = 1 (0 dB) ---
    sgn = np.sign(mag_db)
    idx = np.where(np.diff(sgn) != 0)[0]
    if len(idx):
        frac = (0.0 - mag_db[idx]) / (mag_db[idx + 1] - mag_db[idx])
        gc_w = np.exp(logw[idx] + frac * (logw[idx + 1] - logw[idx]))
        ph = phase_deg[idx] + frac * (phase_deg[idx + 1] - phase_deg[idx])
        # PM = 180 + (continuously unwrapped) phase at the crossover, taken as-is (no
        # re-wrapping): a crossover reached while phase is still far from -180 legitimately
        # gets a large PM (very safe); a crossover past -180 legitimately gets a small or
        # negative one. The worst (minimum) over all crossovers is what matters.
        gc_pm = 180.0 + ph
    else:
        gc_w = np.array([])
        gc_pm = np.array([])

    # --- phase crossovers: phase = -180 deg (mod 360) ---
    ph_rel = phase_deg + 180.0
    k = np.floor(ph_rel / 360.0)
    idx2 = np.where(np.diff(k) != 0)[0]
    if len(idx2):
        boundary = np.maximum(k[idx2], k[idx2 + 1]) * 360.0
        frac2 = (boundary - ph_rel[idx2]) / (ph_rel[idx2 + 1] - ph_rel[idx2])
        frac2 = np.clip(frac2, 0.0, 1.0)
        pc_w = np.exp(logw[idx2] + frac2 * (logw[idx2 + 1] - logw[idx2]))
        pc_gain_db = mag_db[idx2] + frac2 * (mag_db[idx2 + 1] - mag_db[idx2])
    else:
        pc_w = np.array([])
        pc_gain_db = np.array([])

    gm_up = pc_gain_db[pc_gain_db < 0]
    gm_down = pc_gain_db[pc_gain_db >= 0]

    return {
        "phase_margins": list(zip(gc_w.tolist(), gc_pm.tolist())),
        "gain_crossings": list(zip(pc_w.tolist(), pc_gain_db.tolist())),
        "worst_phase_margin_deg": float(np.min(gc_pm)) if len(gc_pm) else float("inf"),
        "worst_gain_margin_up_db": float(np.min(-gm_up)) if len(gm_up) else float("inf"),
        "worst_gain_margin_down_db": float(np.min(gm_down)) if len(gm_down) else float("inf"),
        "n_gain_crossovers": len(gc_pm),
        "n_phase_crossovers": len(pc_gain_db),
    }


def default_w_grid():
    return np.logspace(np.log10(0.001), np.log10(1000.0), 200001)
