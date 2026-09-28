"""Shared model-building and analysis code for the pitch attitude hold design.

Everything here is derived directly from environment/plant.json and the README's exact
specifications for the actuator, delay, controller structure, and the grader's simulation /
frequency-response method.
"""
import json
import pathlib

import numpy as np
from scipy.signal import cont2discrete

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
ENV = ROOT / "environment"

TAU_ACT = 0.05      # actuator time constant, s
RATE_LIM_DEG = 60.0  # deg/s
POS_LIM_DEG = 25.0   # deg (absolute)
TAU_DELAY = 0.04     # sensor delay, s
DT = 0.001           # grader time step, s
N_DELAY = 40         # exact number of steps of delay at dt=1ms
T_END = 20.0
THETA_CMD_DEG = 5.0


def load_plant():
    data = json.loads((ENV / "plant.json").read_text(encoding="utf-8"))
    A = np.array(data["A"], dtype=float)
    B = np.array(data["B"], dtype=float)
    C = np.array(data["C"], dtype=float)
    D = np.array(data["D"], dtype=float)
    trim = data["trim"]
    return A, B, C, D, trim


A, B, C, D, TRIM = load_plant()
TRIM_DELTA_E_DEG = np.degrees(TRIM["delta_e_rad"])
# perturbation position limits (deg), from absolute +-25 deg
PERT_MIN_DEG = -POS_LIM_DEG - TRIM_DELTA_E_DEG
PERT_MAX_DEG = POS_LIM_DEG - TRIM_DELTA_E_DEG

C_THETA = C[0:1, :]
C_Q = C[1:2, :]


def plant_poles():
    return np.linalg.eigvals(A)


def eig_decomp():
    """Eigen-decomposition of A, used for fast vectorized frequency response."""
    lam, V = np.linalg.eig(A)
    Vinv = np.linalg.inv(V)
    return lam, V, Vinv


def freq_grid(n=200001, wmin=1e-3, wmax=1e3):
    return np.logspace(np.log10(wmin), np.log10(wmax), n)


def plant_frd(w, C_row):
    """G(jw) = C_row (jwI - A)^-1 B, vectorized via eigen-decomposition of A."""
    lam, V, Vinv = eig_decomp()
    CV = C_row @ V            # (1,4)
    VinvB = Vinv @ B          # (4,1)
    coeff = (CV.flatten()) * (VinvB.flatten())   # (4,), residues
    jw = 1j * w
    # G(jw) = sum_i coeff_i / (jw - lam_i)
    G = np.zeros_like(jw, dtype=complex)
    for i in range(4):
        G += coeff[i] / (jw - lam[i])
    return G


def actuator_frd(w):
    return 1.0 / (1.0 + 1j * w * TAU_ACT)


def delay_frd(w):
    return np.exp(-1j * w * TAU_DELAY)


def loop_frd(w, Kp, Ki, Kq, Gtm=None, Gqm=None):
    """Exact loop transfer function L(jw), broken at the elevator command.

    L(jw) = (Kp + Ki/(jw)) * Gtm(jw) + Kq * Gqm(jw)
    where Gtm, Gqm are the (actuator*plant*delay) transfers from delta_cmd to theta_m, q_m.
    """
    if Gtm is None or Gqm is None:
        Gact = actuator_frd(w)
        Gdel = delay_frd(w)
        Gtm = plant_frd(w, C_THETA) * Gact * Gdel
        Gqm = plant_frd(w, C_Q) * Gact * Gdel
    jw = 1j * w
    L = (Kp + Ki / jw) * Gtm + Kq * Gqm
    return L


def precompute_Gtm_Gqm(w):
    Gact = actuator_frd(w)
    Gdel = delay_frd(w)
    Gtm = plant_frd(w, C_THETA) * Gact * Gdel
    Gqm = plant_frd(w, C_Q) * Gact * Gdel
    return Gtm, Gqm


def margins_from_L(w, L):
    """Replicates the classical margin definitions from an exact frequency response.

    Returns a dict with:
      gain_crossings: list of (w_gc, PM_deg)
      phase_crossings: list of (w_pc, kind, margin_db)   kind in {'increase','decrease'}
    Uses unwrapped phase for PM (correct even if the phase has already wrapped past -180
    multiple times before a later gain crossover), and Im(L)=0 & Re(L)<0 for phase crossings
    (exact, no unwrap ambiguity).
    """
    mag = np.abs(L)
    mag_db = 20 * np.log10(mag)
    phase_rad = np.unwrap(np.angle(L))
    phase_deg = np.degrees(phase_rad)

    gain_crossings = []
    s = np.sign(mag_db)
    idx = np.where(np.diff(s) != 0)[0]
    for i in idx:
        x0, x1 = np.log10(w[i]), np.log10(w[i + 1])
        y0, y1 = mag_db[i], mag_db[i + 1]
        if y1 == y0:
            continue
        t = -y0 / (y1 - y0)
        wc = 10 ** (x0 + t * (x1 - x0))
        ph0, ph1 = phase_deg[i], phase_deg[i + 1]
        ph = ph0 + t * (ph1 - ph0)
        pm = 180.0 + ph
        gain_crossings.append((wc, pm))

    phase_crossings = []
    Im = L.imag
    Re = L.real
    si = np.sign(Im)
    idxp = np.where(np.diff(si) != 0)[0]
    for i in idxp:
        x0, x1 = np.log10(w[i]), np.log10(w[i + 1])
        y0, y1 = Im[i], Im[i + 1]
        if y1 == y0:
            continue
        t = -y0 / (y1 - y0)
        wc = 10 ** (x0 + t * (x1 - x0))
        re0, re1 = Re[i], Re[i + 1]
        re = re0 + t * (re1 - re0)
        if re >= 0:
            continue  # crossing on positive real axis, not a -180 phase crossing
        if abs(re) < 1.0:
            gm_db = -20 * np.log10(abs(re))
            phase_crossings.append((wc, "increase", gm_db))
        else:
            gm_db = 20 * np.log10(abs(re))
            phase_crossings.append((wc, "decrease", gm_db))

    return {"gain_crossings": gain_crossings, "phase_crossings": phase_crossings}


def discretize_plant(dt=DT):
    Ad, Bd, Cd, Dd, _ = cont2discrete((A, B, C, D), dt, method="zoh")
    return Ad, Bd, Cd, Dd


def simulate(Kp, Ki, Kq, b, t_end=T_END, dt=DT, theta_cmd_deg=THETA_CMD_DEG):
    """Exact replica of the grader's discrete-time simulation.

    Returns a dict of time series (deg / deg-s units where noted) and derived quantities.
    """
    Ad, Bd, Cd, Dd = discretize_plant(dt)
    n_steps = int(round(t_end / dt))
    theta_cmd = np.radians(theta_cmd_deg)

    x = np.zeros(4)  # u, w, q, theta (perturbation states)
    delta = 0.0       # actuator state (perturbation, rad)
    xi = 0.0          # controller integrator state (rad*s)

    # measurement delay buffers (rad), pre-t=0 measurements are zero
    theta_hist = np.zeros(n_steps + 1)
    q_hist = np.zeros(n_steps + 1)

    rate_lim = np.radians(RATE_LIM_DEG)
    pos_min = np.radians(PERT_MIN_DEG)
    pos_max = np.radians(PERT_MAX_DEG)

    t_arr = np.zeros(n_steps + 1)
    theta_arr = np.zeros(n_steps + 1)
    q_arr = np.zeros(n_steps + 1)
    delta_arr = np.zeros(n_steps + 1)       # actual surface perturbation (rad)
    delta_cmd_arr = np.zeros(n_steps + 1)   # raw controller output (rad), unsaturated

    theta_arr[0] = x[3]
    q_arr[0] = x[2]
    delta_arr[0] = delta
    delta_cmd_arr[0] = 0.0
    theta_hist[0] = x[3]
    q_hist[0] = x[2]

    for k in range(n_steps):
        # delayed measurements available at step k (exactly N_DELAY steps old; zero before t=0)
        idx = k - N_DELAY
        theta_m = theta_hist[idx] if idx >= 0 else 0.0
        q_m = q_hist[idx] if idx >= 0 else 0.0

        error_p = theta_cmd - theta_m
        delta_cmd = Kp * (b * theta_cmd - theta_m) + Ki * xi - Kq * q_m
        delta_cmd_arr[k] = delta_cmd  # value used to command the actuator at this step

        # actuator: forward Euler with rate and position limits
        target = min(max(delta_cmd, pos_min), pos_max)
        rate = (target - delta) / TAU_ACT
        rate = min(max(rate, -rate_lim), rate_lim)
        delta_next = delta + dt * rate
        delta_next = min(max(delta_next, pos_min), pos_max)

        # controller integrator: forward Euler
        xi_next = xi + dt * error_p

        # plant: exact ZOH discretization, held input = current delta (this step's actuator output)
        x_next = Ad @ x + Bd.flatten() * delta

        # advance
        x = x_next
        delta = delta_next
        xi = xi_next

        t_arr[k + 1] = (k + 1) * dt
        theta_arr[k + 1] = x[3]
        q_arr[k + 1] = x[2]
        delta_arr[k + 1] = delta
        theta_hist[k + 1] = x[3]
        q_hist[k + 1] = x[2]

    # last delta_cmd sample (k=n_steps) for completeness of the array (not used for the last actuator step)
    idx = n_steps - N_DELAY
    theta_m = theta_hist[idx] if idx >= 0 else 0.0
    q_m = q_hist[idx] if idx >= 0 else 0.0
    delta_cmd_arr[n_steps] = Kp * (b * theta_cmd - theta_m) + Ki * xi - Kq * q_m

    return {
        "t": t_arr,
        "theta_rad": theta_arr,
        "q_rad_s": q_arr,
        "delta_rad": delta_arr,
        "delta_cmd_rad": delta_cmd_arr,
    }


def closed_loop_eigs(Kp, Ki, Kq, pade_order=8):
    """Independent LTI stability check (R1): closes the loop using an 8th order Pade
    approximation of the 40 ms delay (as the README suggests is a reasonable variation),
    building the interconnection in state-space (robust; avoids high-order polynomial algebra),
    and returns the eigenvalues of the resulting closed-loop system.

    This mirrors the exact loop-break point of R2 (elevator command), so the same
    characteristic equation 1 + L(s) = 0 applies; we build it directly rather than via L(s)
    to avoid numerical issues from transfer-function multiplication at 8th+ order.
    """
    import control

    plant = control.ss(A, B, C, D, inputs=["delta"], outputs=["theta", "q"], name="plant")
    act_ss0 = control.tf2ss(control.tf([1.0], [TAU_ACT, 1.0]))
    act = control.ss(act_ss0.A, act_ss0.B, act_ss0.C, act_ss0.D,
                      inputs=["u_test"], outputs=["delta"], name="act")
    num, den = control.pade(TAU_DELAY, pade_order)
    delay_tf = control.tf(num, den)
    delay_ss = control.tf2ss(delay_tf)
    delay_theta = control.ss(delay_ss.A, delay_ss.B, delay_ss.C, delay_ss.D,
                              inputs=["theta"], outputs=["theta_m"], name="delay_theta")
    delay_q = control.ss(delay_ss.A, delay_ss.B, delay_ss.C, delay_ss.D,
                          inputs=["q"], outputs=["q_m"], name="delay_q")
    # controller feedback block: state xi with dxi/dt = theta_m; delta_fb = -Kp*theta_m -Ki*xi -Kq*q_m
    ctrl_fb = control.ss([[0.0]], [[1.0, 0.0]], [[-Ki]], [[-Kp, -Kq]],
                         inputs=["theta_m", "q_m"], outputs=["delta_fb"], name="ctrl_fb")

    M = control.interconnect(
        [plant, act, delay_theta, delay_q, ctrl_fb],
        inplist=["act.u_test"], outlist=["ctrl_fb.delta_fb"],
    )
    # M maps u_test -> delta_fb = -L(s) u_test (see NOTES.md derivation). Close the loop with
    # POSITIVE unity feedback (u_test = delta_fb) to reproduce 1 - M(s) = 0, i.e. 1 + L(s) = 0.
    closed = control.feedback(M, 1, sign=1)
    eigs = np.linalg.eigvals(closed.A)
    return eigs


def requirements_from_sim(sim, theta_cmd_deg=THETA_CMD_DEG):
    t = sim["t"]
    theta_deg = np.degrees(sim["theta_rad"])
    delta_cmd_deg = np.degrees(sim["delta_cmd_rad"])
    abs_elevator_cmd_deg = TRIM_DELTA_E_DEG + delta_cmd_deg

    overshoot_pct = (max(0.0, theta_deg.max() - theta_cmd_deg) / theta_cmd_deg) * 100.0

    band = 0.1
    outside = np.abs(theta_deg - theta_cmd_deg) > band
    if np.any(outside):
        settling_time_s = t[np.where(outside)[0].max()]
    else:
        settling_time_s = 0.0

    max_elevator_deg = np.max(np.abs(abs_elevator_cmd_deg))

    return {
        "overshoot_pct": overshoot_pct,
        "settling_time_s": settling_time_s,
        "max_elevator_deg": max_elevator_deg,
        "theta_peak_deg": theta_deg.max(),
    }
