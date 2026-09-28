"""The grader's truth model: plant, actuator, sensor delay and controller, as the task README defines them.

Time domain: fixed 1 ms step. The plant is discretized exactly (zero order hold on the surface deflection); the
actuator is a first order lag with rate and position limits, integrated with forward Euler; both measurements are
delayed by a whole number of steps.
Frequency domain: the loop is broken at the elevator command, with the actuator lag and the exact delay e^(-s tau).
"""
import json
import pathlib

import numpy as np
from scipy.linalg import expm

TASK = pathlib.Path(__file__).resolve().parents[1]
SPEC = {
    "tau_actuator_s": 0.05,        # elevator servo time constant
    "rate_limit_deg_s": 60.0,      # elevator slew limit
    "position_limit_deg": 25.0,    # absolute elevator deflection limit, both directions
    "delay_s": 0.040,              # sensor and computation delay on theta and q
    "step_deg": 5.0,               # pitch attitude command step, from trim
    "horizon_s": 20.0,             # simulation length
    "dt_s": 0.001,
    "band": 0.02,                  # settling band, fraction of the step
}


def load_plant(path=TASK / "environment" / "plant.json"):
    p = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    return {k: np.array(p[k], dtype=float) for k in ("A", "B", "C", "D")} | {"trim": p["trim"]}


def simulate(plant, ctrl, spec=SPEC, limits=True, step_deg=None, horizon_s=None):
    """Step response of the closed loop. ctrl: dict with K_p, K_i, K_q, b (radians and seconds).

    Returns a dict of time histories (numpy arrays, radians and seconds).
    """
    dt = spec["dt_s"]
    n = int(round((horizon_s or spec["horizon_s"]) / dt)) + 1
    nd = int(round(spec["delay_s"] / dt))
    A, B = plant["A"], plant["B"]
    # exact zero order hold discretization
    M = expm(np.block([[A, B], [np.zeros((1, A.shape[0] + 1))]]) * dt)
    Phi, Gam = M[:4, :4], M[:4, 4:]
    trim_de = plant["trim"]["delta_e_rad"]
    lim = np.radians(spec["position_limit_deg"])
    lo, hi = -lim - trim_de, lim - trim_de          # limits on the perturbation, from the absolute limit
    rate = np.radians(spec["rate_limit_deg_s"])
    tau = spec["tau_actuator_s"]
    ref = np.radians(step_deg if step_deg is not None else spec["step_deg"])

    t = np.arange(n) * dt
    x = np.zeros(4)
    theta, q, de, de_cmd, u, w = (np.zeros(n) for _ in range(6))
    sat_pos, sat_rate = np.zeros(n, bool), np.zeros(n, bool)
    integ, d = 0.0, 0.0
    for k in range(n):
        u[k], w[k], q[k], theta[k] = x
        j = k - nd
        th_m, q_m = (theta[j], q[j]) if j >= 0 else (0.0, 0.0)
        e = ref - th_m
        cmd = ctrl["K_p"] * (ctrl["b"] * ref - th_m) + ctrl["K_i"] * integ - ctrl["K_q"] * q_m
        integ += e * dt
        de_cmd[k] = cmd
        if limits:
            target = min(max(cmd, lo), hi)
            sat_pos[k] = target != cmd
            rdot = (target - d) / tau
            sat_rate[k] = abs(rdot) > rate
            rdot = min(max(rdot, -rate), rate)
        else:
            rdot = (cmd - d) / tau
        de[k] = d
        x = Phi @ x + Gam[:, 0] * d
        d = d + rdot * dt
        if limits:
            d = min(max(d, lo), hi)
    return {"t": t, "theta": theta, "q": q, "de": de, "de_cmd": de_cmd, "u": u, "w": w,
            "sat_pos": sat_pos, "sat_rate": sat_rate, "ref": ref, "trim_de": trim_de}


def step_metrics(sim, spec=SPEC):
    """Overshoot (% of the step), 2% settling time (s), and elevator use, from a step response."""
    th, t, ref = sim["theta"], sim["t"], sim["ref"]
    if not np.all(np.isfinite(th)):
        return {"diverged": True}
    err = np.abs(th - ref)
    outside = np.nonzero(err > spec["band"] * abs(ref))[0]
    if len(outside) == 0:
        settling = 0.0
    elif outside[-1] == len(t) - 1:
        settling = float("inf")                     # still outside the band at the end of the horizon
    else:
        settling = float(t[outside[-1] + 1])
    cmd_abs = sim["de_cmd"] + sim["trim_de"]          # absolute elevator command, the quantity R4 limits
    return {
        "diverged": bool(np.max(np.abs(th)) > 10 * abs(ref)),
        "overshoot_pct": float(max(0.0, (np.max(th) - ref) / ref * 100.0)),
        "settling_time_s": settling,
        "final_error_pct": float((th[-1] - ref) / ref * 100.0),
        "max_elevator_deg": float(np.degrees(np.max(np.abs(cmd_abs)))),
        "max_surface_deg": float(np.degrees(np.max(np.abs(sim["de"] + sim["trim_de"])))),
        "position_limited_s": float(np.sum(sim["sat_pos"]) * spec["dt_s"]),
        "rate_limited_s": float(np.sum(sim["sat_rate"]) * spec["dt_s"]),
        "max_u_change_m_s": float(np.max(np.abs(sim["u"]))),
    }


def plant_frequency_response(plant, w):
    """G_theta(jw) and G_q(jw), responses of theta and q to the elevator deflection."""
    A, B, C = plant["A"], plant["B"], plant["C"]
    n = A.shape[0]
    M = 1j * np.asarray(w)[:, None, None] * np.eye(n) - A          # one (sI - A) per frequency
    X = np.linalg.solve(M, np.broadcast_to(B, (len(w), n, 1)))
    G = (C @ X)[:, :, 0]
    return G[:, 0], G[:, 1]


def loop_response(plant, ctrl, w, spec=SPEC, delay=True):
    """L(jw), broken at the elevator command: L = (K_q G_q + (K_p + K_i/s) G_theta) Act e^(-s tau)."""
    s = 1j * w
    G_th, G_q = plant_frequency_response(plant, w)
    act = 1.0 / (spec["tau_actuator_s"] * s + 1.0)
    L = (ctrl["K_q"] * G_q + (ctrl["K_p"] + ctrl["K_i"] / s) * G_th) * act
    if delay:
        L = L * np.exp(-s * spec["delay_s"])
    return L


def margins(plant, ctrl, spec=SPEC, w=None, delay=True):
    """Gain and phase margins from a dense frequency sweep with the exact delay.

    gm_db: smallest margin against a gain increase (from -180 deg crossings with |L| < 1).
    gm_low_db: smallest margin against a gain decrease (from -180 deg crossings with |L| > 1); inf if none.
    pm_deg: smallest phase margin over all gain crossovers.
    """
    w = np.logspace(-3, 3, 200001) if w is None else w
    L = loop_response(plant, ctrl, w, spec, delay)
    mag = np.abs(L)
    ph = np.unwrap(np.angle(L))
    # gain crossovers
    idx = np.nonzero(np.diff(np.sign(mag - 1.0)))[0]
    pms, wcs = [], []
    for i in idx:
        f = (1.0 - mag[i]) / (mag[i + 1] - mag[i])
        phc = ph[i] + f * (ph[i + 1] - ph[i])
        pm = (np.degrees(phc) + 180.0) % 360.0
        pms.append(pm if pm <= 180.0 else pm - 360.0)
        wcs.append(w[i] + f * (w[i + 1] - w[i]))
    # phase crossovers: phase = -180 deg + k 360
    shifted = (ph + np.pi) / (2 * np.pi)
    jdx = np.nonzero(np.diff(np.floor(shifted)))[0]
    gm_up, gm_down, wps = [np.inf], [np.inf], []
    for j in jdx:
        k = np.floor(shifted[j + 1]) if shifted[j + 1] > shifted[j] else np.floor(shifted[j])
        target = 2 * np.pi * k - np.pi
        f = (target - ph[j]) / (ph[j + 1] - ph[j])
        m = mag[j] + f * (mag[j + 1] - mag[j])
        wps.append(w[j] + f * (w[j + 1] - w[j]))
        if m < 1.0:
            gm_up.append(-20 * np.log10(m))
        else:
            gm_down.append(20 * np.log10(m))
    return {
        "pm_deg": float(min(pms)) if pms else float("inf"),
        "gm_db": float(min(gm_up)),
        "gm_low_db": float(min(gm_down)),
        "crossover_rad_s": [float(x) for x in wcs],
        "phase_crossover_rad_s": [float(x) for x in wps[:5]],
    }


def closed_loop_matrix(plant, ctrl, spec=SPEC, pade_order=8):
    """State matrix of the linear closed loop (no limits), with a Pade approximation of each delayed measurement.

    State: [plant x (4), surface deflection, integrator, Pade states of theta_m, Pade states of q_m]. Built directly
    in state space, so no pole can survive a transfer function cancellation.
    """
    import control as ct
    A, B, C = plant["A"], plant["B"], plant["C"]
    Ad, Bd, Cd, Dd = (np.atleast_2d(np.asarray(m, dtype=float))
                      for m in ct.ssdata(ct.tf2ss(*ct.pade(spec["delay_s"], pade_order))))
    n, nd, tau = A.shape[0], Ad.shape[0], spec["tau_actuator_s"]
    N = n + 2 + 2 * nd
    ix, idl, ii = slice(0, n), n, n + 1
    izt, izq = slice(n + 2, n + 2 + nd), slice(n + 2 + nd, N)
    th_row, q_row = C[0], C[1]
    # delayed measurements as rows over the full state
    th_m = np.zeros(N)
    th_m[ix] = Dd[0, 0] * th_row
    th_m[izt] = Cd[0]
    q_m = np.zeros(N)
    q_m[ix] = Dd[0, 0] * q_row
    q_m[izq] = Cd[0]
    u_c = -ctrl["K_p"] * th_m - ctrl["K_q"] * q_m      # theta_cmd = 0 for the poles
    u_c[ii] += ctrl["K_i"]
    Acl = np.zeros((N, N))
    Acl[ix, ix] = A
    Acl[ix, idl] = B[:, 0]
    Acl[idl] = u_c / tau
    Acl[idl, idl] -= 1.0 / tau
    Acl[ii] = -th_m
    Acl[izt, izt] = Ad
    Acl[izt, ix] = np.outer(Bd[:, 0], th_row)
    Acl[izq, izq] = Ad
    Acl[izq, ix] = np.outer(Bd[:, 0], q_row)
    return Acl


def closed_loop_poles(plant, ctrl, spec=SPEC, pade_order=8):
    """Closed loop poles of the linear loop (no limits), with a Pade approximation of the delay.

    With K_i = 0 the integrator state is disconnected and adds a pole at the origin that no output sees, so it is
    dropped.
    """
    poles = np.linalg.eigvals(closed_loop_matrix(plant, ctrl, spec, pade_order))
    if ctrl["K_i"] == 0:
        poles = np.delete(poles, np.argmin(np.abs(poles)))
    return poles
