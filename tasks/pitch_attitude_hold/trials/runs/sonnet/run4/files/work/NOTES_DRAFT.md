# Draft notes (working copy, not the deliverable yet)

## Key derivation
theta_dot = q exactly (row 3 of A is [0,0,1,0], no direct D feedthrough), so G_theta(s) = G_q(s)/s
identically. Therefore the loop transfer function broken at the elevator command is

    L(s) = (Kp + Ki/s) * G_theta_m(s) + Kq * G_q_m(s)
         = G_qm(s) * (Kq + Kp/s + Ki/s^2)

where G_qm(s) = G_q(s) * Gact(s) * Gdelay(s) is the transfer from delta_cmd to the delayed q
measurement (actuator 1/(0.05s+1) and delay e^{-0.04s} included). This reduces the whole
3-gain feedback to a single equivalent "P + I + I^2" compensator acting on one SISO loop.

## Sign convention finding
Rate feedback alone (Kp=Ki=0): sweeping Kq shows NEGATIVE Kq increases short-period damping
(e.g. Kq=-0.2 -> poles -8.50+-8.91j vs open loop -4.89+-9.87j), positive Kq reduces damping and
destabilizes beyond about Kq=+0.3. Likewise Ki must be negative (matches sign of the plant's
DC gain -1.776 rad theta per rad elevator). All three gains end up negative.

## Method
1. Exact frequency-domain margin computation, replicating the grader's method exactly:
   200001-pt log grid 0.001-1000 rad/s, L(jw) with true e^{-jw*0.04} delay (no Pade). Gain
   crossings found by sign changes of |L|_dB; phase crossings found via Im(L)=0 & Re(L)<0
   (exact -180 deg crossing, avoids unwrap ambiguity), classified as "increase" (|Re|<1) or
   "decrease" (|Re|>1) margin per the README's R2 wording. Cross-validated against
   control.stability_margins(..., returnall=True) on the same frequency response: exact
   agreement (same wgc, wpc, gm, pm to displayed precision).
2. Exact time-domain simulation, replicating the grader's discrete method exactly: dt=1ms,
   plant discretized exactly via scipy.signal.cont2discrete (ZOH), actuator integrated with
   forward Euler with rate limit (60 deg/s) and position limit (surface absolute +-25 deg,
   i.e. perturbation in [-17.900, 32.100] deg given trim = -7.100 deg), measurement delay of
   exactly 40 steps (zero before t=0), controller integrator via forward Euler.
3. Independent LTI stability cross-check: closed the loop in state-space using an 8th/10th
   order Pade approximation of the delay (two ways: control.interconnect state-space build,
   and a fast polynomial characteristic-equation method using G_q(s)'s exact rational transfer
   function) -- both agree with each other to ~4 decimals on all poles.

## Search
- First tried maximizing the gain-crossover frequency subject to PM>=45+buffer, GM>=6+buffer
  (fast, frequency-domain only). This found very high bandwidth (~15 rad/s) at Kq~-0.4 but with
  tiny Ki (pushed to the edge of the grid), which turned out to leave a very slow dominant
  closed-loop pole (~-0.17 to -0.26 rad/s) -- settling in the linear model alone would need
  ~10-20s. Kq more negative than about -0.45 to -0.5 is infeasible altogether (no Kp,Ki gives
  PM>=45 and GM>=6dB simultaneously) -- confirmed with a wide/fine grid and a global
  (differential_evolution) search.
- Re-targeted the search to directly maximize the *dominant closed-loop pole speed*
  (min |Re(pole)|, via the fast polynomial method) subject to margins. This favours much larger
  |Ki|. But the README states there is NO anti-windup logic, and the actuator has hard rate
  (60 deg/s) and position (+-25 deg absolute) limits -- a large Ki that looks perfect in the
  *linear* analysis causes severe integrator windup once the elevator saturates during the
  initial transient (verified: Ki=-26 gives a 1210% overshoot and a 2357 deg commanded
  elevator in the real nonlinear sim, despite perfect linear margins/poles). So the true
  objective has to be the nonlinear nonlinear simulation itself, not a linear proxy.
- Final search: grid + Nelder-Mead refinement directly on the nonlinear simulation's settling
  time, with penalties for PM<45+buffer, GM<6+buffer, overshoot>ceiling, |elevator|>ceiling.
  The setpoint weight b turned out to want to be small (~0.01-0.1): a small b mutes the initial
  proportional "kick" from the commanded step (the integral and rate terms still see the full
  error), which controls overshoot without slowing down the underlying pole locations (b only
  shapes the reference-to-output zero, not the loop's poles/margins).

## Chosen design
(filled in after the final numbers are locked in)

## Assumptions
- The loop broken for R2 is the feedback path only (b*theta_cmd feedforward excluded from
  L(s)), standard practice for gain/phase margin definitions; b has no effect on stability
  margins (only shapes the numerator/zero of the closed-loop command response), confirmed
  numerically (margins identical for all b at fixed Kp,Ki,Kq).
- report.json's "max_elevator_deg" and R4's "elevator command" are the raw controller output
  (delta_cmd, before the actuator's own saturation), i.e. trim + Kp(...)+Ki*integral-Kq*q_m,
  not the (always-saturated-safe) actual surface deflection -- this is the stricter, more
  literal reading of "the absolute elevator command (trim plus controller output)".
- gain_margin_db in report.json is the margin against a gain *increase* specifically (as the
  README's field description says), even when a margin against a gain decrease also exists and
  is separately checked for R2.
