"""Fast polynomial-based closed-loop pole computation (Pade-approximated delay), for use as an
optimization proxy for settling speed. Independent of the state-space interconnect method in
common.closed_loop_eigs; used to cross-check it and to search much faster (no control library
interconnection overhead per evaluation).
"""
import numpy as np
import control
from common import A, B, C_Q, TAU_ACT, TAU_DELAY

PADE_ORDER = 10


def _plant_q_tf():
    sys = control.ss(A, B, C_Q, [[0.0]])
    tf = control.ss2tf(sys)
    num = np.array(tf.num[0][0], dtype=float)
    den = np.array(tf.den[0][0], dtype=float)
    return num, den


_NUM_Q, _DEN_Q = _plant_q_tf()
# G_q(s) has an exact zero at s=0 (theta = integral of q settles to a nonzero value from a
# constant elevator, so q itself must return to 0 -- see NOTES.md). Factor that root out
# analytically before forming the characteristic equation, otherwise s=0 becomes a spurious
# root of the char. polynomial below (present for ANY gains) that is not a real closed-loop pole.
assert abs(_NUM_Q[-1]) < 1e-6 * max(abs(_NUM_Q)), "expected num_q(0) ~ 0 (G_q has a zero at s=0)"
_NUM_Q1 = _NUM_Q[:-1]  # divide out the s factor (drop the zero constant term)

_NUM_ACT, _DEN_ACT = np.array([1.0]), np.array([TAU_ACT, 1.0])
_NUM_D, _DEN_D = control.pade(TAU_DELAY, PADE_ORDER)
_NUM_D = np.array(_NUM_D, dtype=float)
_DEN_D = np.array(_DEN_D, dtype=float)

_NUM_QM1 = np.convolve(np.convolve(_NUM_Q1, _NUM_ACT), _NUM_D)
_DEN_QM = np.convolve(np.convolve(_DEN_Q, _DEN_ACT), _DEN_D)


def closed_loop_poles_poly(Kp, Ki, Kq):
    """Roots of den_qm(s)*s + num_qm1(s)*(Kq s^2 + Kp s + Ki) = 0, where num_qm1 = num_qm/s
    (the s=0 factor common to num_qm and the loop's s^2 already canceled analytically).
    """
    den_qm = np.poly1d(_DEN_QM)
    num_qm1 = np.poly1d(_NUM_QM1)
    s1 = np.poly1d([1.0, 0.0])
    ceq = np.poly1d([Kq, Kp, Ki])
    charpoly = den_qm * s1 + num_qm1 * ceq
    return np.roots(charpoly.coefficients)


def worst_pole_metric(poles):
    """A settling-speed proxy: for each pole, the exponential envelope decay rate is
    |Re(pole)|. The slowest (smallest |Re|) sets the long-term settling time
    (~4/|Re| for 2% band, for an isolated real or dominant complex pole). Returns
    (slowest_abs_re, the pole itself).
    """
    re = np.array([p.real for p in poles])
    stable = np.all(re < 0)
    idx = np.argmax(re)  # closest to imaginary axis (least negative)
    return -re[idx], poles[idx], stable


if __name__ == "__main__":
    from common import closed_loop_eigs
    for Kp, Ki, Kq in [(-2.0, -1.0, -0.2), (-1.206, -0.371, -0.4)]:
        poles = closed_loop_poles_poly(Kp, Ki, Kq)
        poles_sorted = sorted(poles, key=lambda z: -z.real)
        print(f"poly  Kp={Kp} Ki={Ki} Kq={Kq}")
        for p in poles_sorted[:8]:
            print(f"   {p:.4f}")
        m, p, stable = worst_pole_metric(poles)
        print(f"  slowest |Re|={m:.4f} at pole {p:.4f}  stable={stable}")

        eigs = closed_loop_eigs(Kp, Ki, Kq)
        eigs_sorted = sorted(eigs, key=lambda z: -z.real)
        print("ss-interconnect (cross-check):")
        for e in eigs_sorted[:8]:
            print(f"   {e:.4f}")
