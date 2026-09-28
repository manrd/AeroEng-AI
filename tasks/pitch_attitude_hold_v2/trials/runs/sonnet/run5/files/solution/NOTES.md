# Method

## 1. Loop structure and the key structural simplification

The plant state includes both `theta` and `q`, with the exact kinematic row `theta_dot = q`
(the last row of `A` is `[0,0,1,0]`, last row of `B` is `0`). That means, as an identity of
the Laplace transforms of the *perturbation* signals (zero initial conditions),

    P_theta(s) = P_q(s) / s        exactly, for every plant.

I verified this numerically: `P_q(0) = 0` to machine precision at all three speeds, which is
exactly the zero needed to cancel the `1/s` and leave `P_theta(s)` finite (no pole at the
origin in the open-loop plant itself — confirmed independently by the eigenvalues of `A`,
none of which is zero).

Using that identity, the controller

    de_cmd = Kp(b*th_cmd - th_m) + Ki*INT(th_cmd - th_m) - Kq*q_m

collapses to a **plain PID acting on `P_theta(s)`**, because `-Kq*q_m` is exactly a derivative
term on the (delayed) attitude measurement:

    de_cmd_feedback_path = -[ Kp + Ki/s + Kq*s ] * theta_m(s)

So `K_q` is a genuine derivative gain (on rate, not a differentiated attitude signal — no
noise penalty since sensors are noiseless here), `K_p` is proportional, `K_i` is integral, and
`b` is the classical PID set-point weight applied only to the proportional path. This is the
same architecture as a textbook attitude-hold PID; it just happens to be built from directly
measured theta and q rather than a numerically differentiated theta.

## 2. Loop transfer function for the margin check (R2)

Breaking the loop "at the elevator command" (between controller and actuator) and closing it
through actuator -> plant -> delay -> controller feedback terms gives the characteristic
equation `1 + L(s) = 0` with

    L(s) = Act(s) * exp(-s*0.04) * [ (Kp + Ki/s)*P_theta(s) + Kq*P_q(s) ]
    Act(s) = 1 / (1 + 0.05 s)

`L(s)` does **not** depend on `b`: `b` only scales the reference feed-forward path, so it can
be tuned purely for step-response shaping without touching stability margins. `P_theta(s)` and
`P_q(s)` were built from the residues of `A`'s eigendecomposition (`C(sI-A)^{-1}B` as a sum of
`r_i/(s-lam_i)`), which is exact and lets `L(jw)` be evaluated on the full 200001-point grid
(`0.001` to `1000` rad/s, log-spaced) cheaply.

**Margin extraction.** Rather than track unwrapped phase (ambiguous once phase has wrapped
past +/-180 deg multiple times, which it does here at high frequency because of the pure
delay), I found every crossing of the Nyquist locus with the *negative real axis*
(`Im(L)=0`, `Re(L)<0`) — this is exactly equivalent to, and as robust as, the classical
`Im(H(iw))=0` root used internally by `control.margins`, but works directly off sampled
`L(jw)` data. At each such crossing the loop gain in dB gives a gain-margin candidate:
gain below 0 dB -> margin against a gain *increase* = `-dB`; gain at or above 0 dB -> margin
against a gain *decrease* = `+dB` (must be >= 6 dB either way, matching R2's wording). Gain
crossovers (`|L|=1`) give the phase margin the ordinary way.

**Validation of this method** (see `work/validate_margins.py`, `work/margins_fast.py`):
- Checked against `control.margin`'s polynomial method on a delay-free reference system: exact
  agreement.
- Checked against `control.stability_margins((mag,phase,omega), returnall=True)` (which uses
  `scipy.optimize.brentq` root polishing on a smoothed FRD) on a system with **both an
  integrator and an exact delay** `exp(-sT)`: agreement to 5+ significant figures, and that in
  turn matches a 10th-order Pade approximation solved with the exact polynomial method. I also
  ran this same cross-check directly against the final chosen gains on the real problem
  (`work/cross_validate.py`) at all three speeds — again matching to 5+ significant figures.
- Independently re-verified closed-loop stability (R1, linear model) a second way: built the
  closed-loop system with a **12th-order Pade** approximation of the 40 ms delay (plant 4
  states + actuator 1 state + integrator 1 state + Pade states) and computed its eigenvalues
  directly. Worst closed-loop pole real part: -0.326 (20 m/s), -0.338 (25 m/s), -0.389 (32 m/s)
  — comfortably stable, consistent with the frequency-domain margins.

## 3. Nonlinear time-domain simulation (R1, R3-R5)

`work/lib.py: simulate()` reproduces the grader's stated algorithm directly, importing
`aircraft_model.derivatives` and `aircraft_model.load_params` from the given environment file
(not reimplemented, to guarantee it matches the "truth" model exactly rather than merely
approximately):
- 4th-order Runge-Kutta, fixed 1 ms step, elevator held at that step's *actuator* position
  (the value produced by the previous actuator update) across all four RK4 stages.
- Actuator: `sat_rate((sat_position(delta_cmd) - delta)/0.05)`, forward Euler, plus a final
  clip of the resulting position — exactly as specified.
- Measurement delay: an exact 40-step ring buffer (`0.04 s / 0.001 s = 40`); zero for any
  negative time index, matching "measurements before t=0 are zero".
- Controller integrator: forward Euler on `theta_cmd - theta_m`, using the pre-update integral
  value to form that step's command (i.e. the integral value represents `INT_0^t`).
- `max_elevator_deg` / R4 tracks the peak **unsaturated** `trim + controller output`, per the
  requirement's literal wording (not the post-saturation actuator position).
- Divergence flag: `|theta - theta0| > 1.5 rad` or airspeed outside `[5, 60]` m/s, or any
  non-finite state.

One implementation choice worth flagging: the RK4 step for the plant uses the elevator
position from the *start* of that 1 ms interval (the natural causal reading of "held constant
over each step" together with a forward-Euler actuator update computed from the same-step
command). I checked this is not a real risk rather than just assuming it: `work/robustness_check.py`
reruns the whole nonlinear simulation with the *other* plausible ordering (actuator position
from the *end* of the interval feeding that same interval's plant RK4) for the final gains, at
all three speeds. Worst change: settling time +0.003 s, overshoot -0.029 percentage points, peak
elevator -0.004 deg — two to three orders of magnitude inside the stated grading tolerances, so
"reasonable variations... agree within the claim tolerances" is directly confirmed rather than
just trusted.

## 4. Gain search

A pure-proportional sweep (`Ki=Kq=0`) showed phase margin is not the binding constraint here:
PM stays above 90 deg for `Kp` from -0.5 to about -2, then collapses quickly as the gain
crossover approaches the short-period frequency (8.8-14.1 rad/s across the speed range). The
**actual** binding constraint is the *gain* margin at a second, higher-frequency crossing of
the negative real axis (just above the short-period/actuator-corner region): it shrinks
steadily as `|Kp|` grows and is tightest at 32 m/s (largest control effectiveness /highest
loop gain for a given gain set). This bounds `Kp` to about -2.0 to -2.2 before the 6 dB floor
is violated.

Rate feedback `Kq` has a narrow beneficial band around -0.08 to -0.12: it improves both PM and
GM modestly there, but larger magnitudes push the effective crossover up toward the
short-period frequency and both margins collapse quickly (the same failure mode as too much
`Kp`). `Ki` barely moves the frequency-domain margins (confirmed by scanning the integrator
corner over a wide range at fixed `Kp`) but directly trades nonlinear settling speed against
overshoot: increasing `|Ki|` sped up the 20 m/s settling time from ~19 s (at a conservative
`Ki`) down to a few seconds, at the cost of growing overshoot past the 10% cap. `b` (set-point
weight, provably decoupled from the margins) was used last, as a small extra speed knob traded
against overshoot headroom.

The three airspeeds behave differently under one shared gain set because control
effectiveness scales strongly with dynamic pressure: `B` (elevator-to-q) grows by about 2.56x
from 20 to 32 m/s, and the open-loop DC gain `P_theta(0)` by about 4.5x. **20 m/s is
consistently the slowest case** (least control authority for the same gains) and also has by
far the tightest elevator budget: its trim deflection is already -15.41 deg of the 25 deg
limit, leaving only 9.59 deg of nose-up (more negative) authority for the whole transient,
versus 17.9 deg at 25 m/s and 23.7 deg at 32 m/s (pitching nose-up needs negative elevator
perturbation, since positive elevator is defined trailing-edge-down/nose-down here). 32 m/s
turned out to be the tightest case for gain margin instead. Both constraints, together with
the 10% overshoot cap, are what limit how fast the shared gain set can be.

All four gains came out negative. This is a direct consequence of the sign convention: `P_theta(0)`
is negative at every speed (elevator trailing-edge-down pitches the nose down and reduces
theta), so stabilizing negative feedback requires `Kp * P_theta(0) > 0`, i.e. `Kp < 0`; `Ki`
and `Kq` follow the same sign for consistency (a positive-sign derivative/integral term with
the wrong sign removes damping instead of adding it — confirmed numerically: flipping `Kq`'s
sign, or dropping it, measurably worsens both margins).

Search process, concretely: frequency-domain-only screening (fast, ~6000-8000 point grid) over
a `(Kp, Ki, Kq)` grid to shortlist gains clearing R2 with a small buffer; nonlinear-simulation
evaluation (full `aircraft_model` dynamics) of the shortlist to check R3-R5 and the true
worst-case settling time; a bisection on `|Ki|` per `(Kp, Kq)` pair to map how far the
integrator can be pushed before margins fail; by hand, this converged on
`Kp=-2.0, Ki=-4.15, Kq=-0.1, b=0.1` (worst-case settle 5.793 s, all buffers positive).

I then ran `scipy.optimize.minimize` (Nelder-Mead, `work/optimize_local.py`/`optimize_local2.py`)
twice as a check on that manual result, not as a replacement for it:
- **Unconstrained** (penalty only for violating the raw R2/R3/R4/R5 thresholds), seeded from the
  manual point: converged toward 5.116 s, but by sitting exactly on top of two different
  constraints at once — 32 m/s gain margin at 6.03 dB (0.03 dB above the 6 dB floor) and 25 m/s
  overshoot at 9.81% (0.19 points below the 10% cap). Both are far inside the stated grading
  tolerances (0.5 dB, 1.0 point) and therefore too fragile to submit: a grader recomputation
  landing on the other side of either tolerance band would flip a pass to a fail.
- **Buffer-constrained** (same objective, but the penalty now also fires below 7 dB gain margin
  and above 9% overshoot — one point of headroom past R2/R3's raw numbers), seeded from the
  manual point again: converged to `Kp=-1.958, Ki=-4.038, Kq=-0.106, b=0.100`, worst-case settle
  **5.827 s** — slightly *slower* than the manual point, with more gain-margin buffer at 32 m/s
  (1.01 dB) but less overshoot buffer at 25 m/s (1.04 vs. the manual point's 1.34 points). Neither
  run (both stopped by the function-evaluation budget, not full convergence) found a point that
  is both faster and at least as safely buffered as the manual design in every column, which is
  the evidence used here to stop searching and keep it.

## 5. Final gains and results

    K_p = -2.0,  K_i = -4.15,  K_q = -0.1,  b = 0.1

| Speed | PM (deg) | GM (dB, vs increase) | GM vs decrease | Overshoot (%) | Settle (s) | Max |elevator| (deg) |
|---|---|---|---|---|---|---|
| 20 m/s | 70.99 | 9.01 | n/a (no crossing with gain >= 1) | 8.05 | 5.793 | 21.65 |
| 25 m/s | 73.37 | 8.02 | n/a | 8.66 | 4.513 | 11.11 |
| 32 m/s | 75.60 | 6.77 | n/a | 7.70 | 2.233 | 4.89 |

All computed on the exact 200001-point log grid (0.001 to 1000 rad/s) specified in the task,
using the exact `exp(-s*0.04)` delay and the exact `A,B` residues (no Pade approximation in the
reported numbers — Pade was used only for the independent stability cross-check above). Every
`-180` deg crossing beyond the first has magnitude tens of dB below 0 dB (the delay causes many
high-frequency wraps, but the actuator pole and the plant's own roll-off kill the gain there),
so none of them binds; the "gain margin against a gain decrease" clause of R2 is satisfied
trivially at all three speeds (no crossing has loop gain >= 1 there at all).

Worst-case (optimization target) settling time: **5.793 s, at 20 m/s** — the airspeed with the
least control authority and the tightest elevator budget, as expected from the analysis above.
All of R1-R5 pass at all three airspeeds with margin beyond the stated grading tolerances:
- R1: stable in both the linear (margins above) and nonlinear (no run diverges) sense.
- R2: PM >= 70 deg (need 45), GM >= 6.77 dB (need 6).
- R3: overshoot <= 8.66% (need <= 10%).
- R4: peak elevator command <= 21.65 deg (need <= 25 deg); tightest at 20 m/s as predicted from
  the trim/limit bookkeeping.
- R5: settling <= 5.793 s (need <= 6.0 s).

## 6. Assumptions / notes

- `b` in `[0,1]` inclusive; used 0.1 (near the low end, since larger `b` measurably increases
  overshoot for only a very small settling-time benefit at these gains).
- Assumed the actuator and integrator both start exactly at their trim/zero values at `t=0`
  (aircraft in steady trim before the step), matching "the integrator starts at zero" and
  "measurements before t=0 are zero" in the task.
- All work used only the installed `numpy`, `scipy`, and `control` (no plots were needed, so
  `matplotlib` was not actually exercised); nothing was installed. Scratch/search scripts are
  kept in `work/` alongside this solution folder for reference; only `controller.json`,
  `report.json`, and this file are the deliverables.
