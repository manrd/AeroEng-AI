"""Shared library: plant loading, loop frequency response, margins, and the nonlinear
time-domain simulator that replicates the grader's method (README "How the grader simulates").
"""
import json
import pathlib

import numpy as np
import control as ct

HERE = pathlib.Path(__file__).parent
ENV = HERE.parent / "environment"

DEG = np.pi / 180.0

# ---- plant -----------------------------------------------------------------
_plant = json.loads((ENV / "plant.json").read_text(encoding="utf-8"))
A = np.array(_plant["A"], dtype=float)
B = np.array(_plant["B"], dtype=float)
C = np.array(_plant["C"], dtype=float)   # row0 = theta, row1 = q
D = np.array(_plant["D"], dtype=float)
C_THETA = C[0:1, :]
C_Q = C[1:2, :]

TRIM_DELTA_E_RAD = float(_plant["trim"]["delta_e_rad"])  # -0.12391805205152141

# ---- actuator / delay / limits ---------------------------------------------
TAU_ACT = 0.05         # s, first order lag time constant
RATE_LIMIT = 60.0 * DEG   # rad/s
POS_LIMIT_ABS = 25.0 * DEG  # rad, absolute deflection limit (trim + perturbation)
PERT_MIN = -POS_LIMIT_ABS - TRIM_DELTA_E_RAD   # most-TEU perturbation allowed
PERT_MAX = POS_LIMIT_ABS - TRIM_DELTA_E_RAD    # most-TED perturbation allowed
DELAY_S = 0.04         # s
DT_GRADER = 0.001      # s, grader's fixed time step
DELAY_STEPS = round(DELAY_S / DT_GRADER)  # exactly 40
assert DELAY_STEPS == 40

THETA_CMD_DEG = 5.0
THETA_CMD_RAD = THETA_CMD_DEG * DEG
SIM_T = 20.0


# ---- frequency response of the plant (state-space, exact, vectorized) ------
# Partial-fraction / eigendecomposition form: (jwI-A)^-1 B = V diag(1/(jw-lam)) Vinv B,
# so C(jwI-A)^-1B = sum_i  (C V)[i] * (Vinv B)[i] / (jw - lam[i])  -- O(1) numpy call per
# frequency ARRAY (not per scalar frequency), unlike a per-frequency matrix inverse/solve.
_eigval, _V = np.linalg.eig(A)
_Vinv = np.linalg.inv(_V)
_VinvB = (_Vinv @ B[:, 0])              # (4,)
_CV_theta = (C_THETA[0] @ _V)           # (4,)
_CV_q = (C_Q[0] @ _V)                   # (4,)
_residue_theta = _CV_theta * _VinvB     # (4,)
_residue_q = _CV_q * _VinvB             # (4,)


def plant_freqresp(w):
    """Return (Ptheta(jw), Pq(jw)) arrays for angular frequency array w (rad/s)."""
    w = np.asarray(w, dtype=float)
    jw = 1j * w[:, None] - _eigval[None, :]        # (Nw, 4)
    Ptheta = np.sum(_residue_theta[None, :] / jw, axis=1)
    Pq = np.sum(_residue_q[None, :] / jw, axis=1)
    return Ptheta, Pq


def actuator_freqresp(w):
    w = np.asarray(w, dtype=float)
    return 1.0 / (1.0 + 1j * w * TAU_ACT)


def delay_freqresp(w):
    w = np.asarray(w, dtype=float)
    return np.exp(-1j * w * DELAY_S)


def loop_gain(w, Kp, Ki, Kq):
    """L(jw): loop broken at the elevator command, between controller and actuator."""
    w = np.asarray(w, dtype=float)
    Ptheta, _ = plant_freqresp(w)
    Act = actuator_freqresp(w)
    Delay = delay_freqresp(w)
    ctrl = Kp + Ki / (1j * w) + Kq * (1j * w)
    return Act * Delay * Ptheta * ctrl


GRADER_W = np.logspace(np.log10(0.001), np.log10(1000.0), 200001)


def _find_crossings(w, L):
    """Fast, direct crossing finder (avoids python-control's slow FRD/spline path).

    Gain crossovers: |L(jw)| == 1  -> each gives a phase margin (signed distance, in
        degrees, from that point's phase to the nearest instability point +-180 deg).
    Phase crossovers: L(jw) real and negative (Im=0, Re<0), i.e. phase == +-180 exactly
        -> each gives a loop-gain magnitude there, from which a gain margin follows.
    Both use linear interpolation between the (very finely spaced) grid points.
    """
    mag = np.abs(L)
    re = np.real(L)
    im = np.imag(L)

    gain_crossings = []
    gm1 = mag - 1.0
    sgn = np.sign(gm1)
    idx = np.where(np.diff(sgn) != 0)[0]
    for i in idx:
        f0, f1 = gm1[i], gm1[i + 1]
        frac = 0.0 if f1 == f0 else -f0 / (f1 - f0)
        wc = w[i] + frac * (w[i + 1] - w[i])
        Lc = L[i] + frac * (L[i + 1] - L[i])
        phase_deg = np.degrees(np.angle(Lc))
        pm = (phase_deg % 360.0) - 180.0
        gain_crossings.append((wc, pm))

    phase_crossings = []
    sgn_im = np.sign(im)
    idx_im = np.where(np.diff(sgn_im) != 0)[0]
    for i in idx_im:
        f0, f1 = im[i], im[i + 1]
        frac = 0.0 if f1 == f0 else -f0 / (f1 - f0)
        wc = w[i] + frac * (w[i + 1] - w[i])
        Lc = L[i] + frac * (L[i + 1] - L[i])
        if np.real(Lc) <= 0:
            phase_crossings.append((wc, abs(Lc)))

    return gain_crossings, phase_crossings


def compute_margins(Kp, Ki, Kq, w=None, verbose=False):
    """Gain/phase margins per R2, evaluated on the grader's exact frequency grid.

    Returns a dict with:
      phase_margin_deg : worst (minimum) phase margin over all gain crossovers
      gain_margin_db   : worst margin against a gain INCREASE, over phase crossovers with |L|<1
      gain_margin_decrease_db : worst margin against a gain DECREASE, over phase crossovers with |L|>1
                          (None if there is no such crossover -- not a conditionally stable case)
      n_gain_crossings, n_phase_crossings, ok : bool combining R2's rule
      crossings : diagnostic list
    """
    if w is None:
        w = GRADER_W
    L = loop_gain(w, Kp, Ki, Kq)
    gain_crossings, phase_crossings = _find_crossings(w, L)

    increase_margins_db = []
    decrease_margins_db = []
    crossings = []
    for wc, Lmag_here in phase_crossings:
        db = -20.0 * np.log10(Lmag_here)
        if Lmag_here < 1.0:
            increase_margins_db.append(db)
            crossings.append(("phase_180", wc, Lmag_here, db, "against_increase"))
        else:
            dec_db = -db  # = 20*log10(Lmag_here)
            decrease_margins_db.append(dec_db)
            crossings.append(("phase_180", wc, Lmag_here, dec_db, "against_decrease"))

    phase_margins = []
    for wc, pm in gain_crossings:
        phase_margins.append(pm)
        crossings.append(("gain_1", wc, 1.0, pm, "phase_margin"))

    worst_pm = min(phase_margins) if phase_margins else float("inf")
    worst_gm_inc = min(increase_margins_db) if increase_margins_db else float("inf")
    worst_gm_dec = min(decrease_margins_db) if decrease_margins_db else None

    ok = True
    if not phase_margins or worst_pm < 45.0:
        ok = False
    if not increase_margins_db or worst_gm_inc < 6.0:
        ok = False
    if worst_gm_dec is not None and worst_gm_dec < 6.0:
        ok = False

    result = dict(
        phase_margin_deg=worst_pm,
        gain_margin_db=worst_gm_inc,
        gain_margin_decrease_db=worst_gm_dec,
        n_gain_crossings=len(phase_margins),
        n_phase_crossings=len(increase_margins_db) + len(decrease_margins_db),
        ok=ok,
        crossings=crossings,
    )
    if verbose:
        print(result)
    return result


# ---- discrete-time nonlinear simulation, matching the grader --------------
_sys_c = ct.ss(A, B[:, 0], np.vstack([C_THETA, C_Q]), np.zeros((2, 1)))
_sys_d = ct.c2d(_sys_c, DT_GRADER, method="zoh")
AD = np.asarray(_sys_d.A)
BD = np.asarray(_sys_d.B).reshape(-1)

# ---- exact discrete-time LINEAR closed loop (no saturation) --------------
# Rigorous R1 check: build the exact dt=0.001s discrete update matrix for the augmented
# state [plant(4); actuator(1); integrator(1); theta-delay-fifo(40); q-delay-fifo(40)]
# (86 states) and confirm all its eigenvalues are inside the unit circle. This matches the
# grader's discretization exactly (fixed 1ms step, plant ZOH, actuator Euler, exact 40-step
# delay), differing from the true nonlinear closed loop only by omitting saturation --
# the same linearization margins (R2) already ignore for the identical reason.
_NX_AUG = A.shape[0] + 1
_Ac_aug = np.zeros((_NX_AUG, _NX_AUG))
_Ac_aug[: A.shape[0], : A.shape[0]] = A
_Ac_aug[: A.shape[0], A.shape[0]] = B[:, 0]
_Ac_aug[A.shape[0], A.shape[0]] = -1.0 / TAU_ACT
_Bc_aug = np.zeros(_NX_AUG)
_Bc_aug[A.shape[0]] = 1.0 / TAU_ACT
_sys_c_aug = ct.ss(_Ac_aug, _Bc_aug.reshape(-1, 1), np.eye(_NX_AUG), np.zeros((_NX_AUG, 1)))
_sys_d_aug = ct.c2d(_sys_c_aug, DT_GRADER, method="zoh")
_AD_AUG = np.asarray(_sys_d_aug.A)   # (5,5)
_BD_AUG = np.asarray(_sys_d_aug.B).reshape(-1)  # (5,)
_C_THETA_AUG = np.zeros(_NX_AUG); _C_THETA_AUG[3] = 1.0
_C_Q_AUG = np.zeros(_NX_AUG); _C_Q_AUG[2] = 1.0

_N_TOTAL = _NX_AUG + 1 + DELAY_STEPS + DELAY_STEPS  # aug(5) + integ(1) + 2*40 fifo


def _closed_loop_step(state, Kp, Ki, Kq):
    """One homogeneous (theta_cmd=0) step of the augmented linear discrete system.
    state layout: [x_aug(5), integ(1), fifo_theta(40), fifo_q(40)]."""
    x_aug = state[:_NX_AUG]
    integ = state[_NX_AUG]
    fifo_theta = state[_NX_AUG + 1: _NX_AUG + 1 + DELAY_STEPS]
    fifo_q = state[_NX_AUG + 1 + DELAY_STEPS: _NX_AUG + 1 + 2 * DELAY_STEPS]

    theta_m = fifo_theta[-1]
    q_m = fifo_q[-1]
    delta_cmd = Kp * (-theta_m) + Ki * integ - Kq * q_m

    x_aug_next = _AD_AUG @ x_aug + _BD_AUG * delta_cmd
    integ_next = integ + DT_GRADER * (-theta_m)
    theta_now = _C_THETA_AUG @ x_aug
    q_now = _C_Q_AUG @ x_aug
    fifo_theta_next = np.concatenate(([theta_now], fifo_theta[:-1]))
    fifo_q_next = np.concatenate(([q_now], fifo_q[:-1]))

    return np.concatenate(([*x_aug_next], [integ_next], fifo_theta_next, fifo_q_next))


def discrete_closed_loop_matrix(Kp, Ki, Kq):
    M = np.zeros((_N_TOTAL, _N_TOTAL))
    for i in range(_N_TOTAL):
        e = np.zeros(_N_TOTAL)
        e[i] = 1.0
        M[:, i] = _closed_loop_step(e, Kp, Ki, Kq)
    return M


def discrete_closed_loop_eigs(Kp, Ki, Kq):
    M = discrete_closed_loop_matrix(Kp, Ki, Kq)
    return np.linalg.eigvals(M)


def is_discrete_stable(Kp, Ki, Kq, tol=1e-9):
    eigs = discrete_closed_loop_eigs(Kp, Ki, Kq)
    max_mag = np.max(np.abs(eigs))
    return bool(max_mag < 1.0 - tol), max_mag


def simulate(Kp, Ki, Kq, b, T=SIM_T, dt=DT_GRADER, theta_cmd=THETA_CMD_RAD):
    n_steps = round(T / dt)
    nx = AD.shape[0]

    x = np.zeros(nx)          # plant perturbation state [u,w,q,theta]
    delta = 0.0                # actuator output perturbation (rad)
    integ = 0.0                # controller integrator state

    theta_hist = np.zeros(n_steps + 1)
    q_hist = np.zeros(n_steps + 1)
    delta_cmd_hist = np.zeros(n_steps + 1)   # controller raw output (perturbation, rad)
    delta_act_hist = np.zeros(n_steps + 1)   # actuator output (perturbation, rad)
    t_hist = np.arange(n_steps + 1) * dt

    theta_hist[0] = x[3]
    q_hist[0] = x[2]
    delta_act_hist[0] = delta

    for k in range(n_steps):
        # delayed measurements (zero before t=0)
        idx = k - DELAY_STEPS
        theta_m = theta_hist[idx] if idx >= 0 else 0.0
        q_m = q_hist[idx] if idx >= 0 else 0.0

        error = theta_cmd - theta_m
        delta_cmd = Kp * (b * theta_cmd - theta_m) + Ki * integ - Kq * q_m
        delta_cmd_hist[k] = delta_cmd

        # controller integrator, forward Euler
        integ = integ + dt * error

        # actuator: position-saturate the command, rate-limit, forward-Euler integrate,
        # then position-saturate the resulting surface position too.
        cmd_sat = min(max(delta_cmd, PERT_MIN), PERT_MAX)
        rate = (cmd_sat - delta) / TAU_ACT
        rate = min(max(rate, -RATE_LIMIT), RATE_LIMIT)
        delta = delta + dt * rate
        delta = min(max(delta, PERT_MIN), PERT_MAX)

        # plant: exact ZOH discretization, input held at the actuator's PRE-step value
        x = AD @ x + BD * delta_act_hist[k]

        theta_hist[k + 1] = x[3]
        q_hist[k + 1] = x[2]
        delta_act_hist[k + 1] = delta

    # last sample's commanded value (for completeness; loop above filled 0..n_steps-1)
    idx = n_steps - DELAY_STEPS
    theta_m = theta_hist[idx] if idx >= 0 else 0.0
    q_m = q_hist[idx] if idx >= 0 else 0.0
    delta_cmd_hist[n_steps] = Kp * (b * theta_cmd - theta_m) + Ki * integ - Kq * q_m

    return dict(t=t_hist, theta=theta_hist, q=q_hist,
                delta_cmd=delta_cmd_hist, delta_act=delta_act_hist)


def evaluate(Kp, Ki, Kq, b, T=SIM_T, dt=DT_GRADER, theta_cmd=THETA_CMD_RAD):
    sim = simulate(Kp, Ki, Kq, b, T=T, dt=dt, theta_cmd=theta_cmd)
    theta_deg = sim["theta"] / DEG
    t = sim["t"]

    overshoot_pct = max(0.0, (np.max(theta_deg) - THETA_CMD_DEG) / THETA_CMD_DEG * 100.0)

    band = 0.1  # deg, 2% of 5 deg
    outside = np.where(np.abs(theta_deg - THETA_CMD_DEG) > band)[0]
    settling_time_s = 0.0 if len(outside) == 0 else t[outside[-1]]

    max_elevator_deg = float(np.max(np.abs(TRIM_DELTA_E_RAD + sim["delta_cmd"]))) / DEG
    max_elevator_actual_deg = float(np.max(np.abs(TRIM_DELTA_E_RAD + sim["delta_act"]))) / DEG

    margins = compute_margins(Kp, Ki, Kq)

    R1_ok = np.all(np.isfinite(theta_deg)) and np.max(np.abs(theta_deg)) < 1000  # crude boundedness
    R2_ok = margins["ok"]
    R3_ok = np.max(theta_deg) <= 5.5 + 1e-9
    R4_ok = max_elevator_deg <= 25.0 + 1e-9
    R5_ok = settling_time_s <= 4.0 + 1e-9

    return dict(
        phase_margin_deg=margins["phase_margin_deg"],
        gain_margin_db=margins["gain_margin_db"],
        gain_margin_decrease_db=margins["gain_margin_decrease_db"],
        overshoot_pct=overshoot_pct,
        settling_time_s=settling_time_s,
        max_elevator_deg=max_elevator_deg,
        max_elevator_actual_deg=max_elevator_actual_deg,
        R1_ok=bool(R1_ok), R2_ok=bool(R2_ok), R3_ok=bool(R3_ok),
        R4_ok=bool(R4_ok), R5_ok=bool(R5_ok),
        all_ok=bool(R1_ok and R2_ok and R3_ok and R4_ok and R5_ok),
        margins_detail=margins,
        sim=sim,
    )


if __name__ == "__main__":
    print("A eigenvalues:", np.linalg.eigvals(A))
    print("TRIM_DELTA_E_RAD", TRIM_DELTA_E_RAD, "deg", TRIM_DELTA_E_RAD / DEG)
    print("PERT_MIN deg", PERT_MIN / DEG, "PERT_MAX deg", PERT_MAX / DEG)
    print("DELAY_STEPS", DELAY_STEPS)
