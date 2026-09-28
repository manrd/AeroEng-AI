"""Validate the (mag,phase,omega) -> stability_margins pipeline against the poly method
on a known transfer function, including one with a delay (via exact e^{-sT} in the FRD
data but Pade in the poly reference) and a pole at the origin (integrator), which is the
structure we actually need for the pitch loop.
"""
import numpy as np
import control as ct

w = np.logspace(-3, 3, 200001)

# Case 1: classic example, G = 10/((s+1)(s+2)(s+3)), no delay, cross-check poly vs FRD-tuple.
G = ct.tf([10], np.poly([-1, -2, -3]))
gm_poly, pm_poly, wpc_poly, wgc_poly = ct.margin(G)
resp = G(1j * w)
mag = np.abs(resp)
phase = np.degrees(np.angle(resp))
gm_frd, pm_frd, sm, wpc, wgc, wms = ct.stability_margins((mag, phase, w), returnall=True)
print("Case 1 (no delay, no integrator):")
print(" poly:", gm_poly, pm_poly, wpc_poly, wgc_poly)
print(" frd all GM:", gm_frd, "at w=", wpc)
print(" frd all PM:", pm_frd, "at w=", wgc)
print()

# Case 2: integrator + delay, G = 5*exp(-0.04 s)/(s*(s+2)*(1+0.05*s))
num = [5]
den = np.poly([0, -2])
den = np.polymul(den, [0.05, 1])
Gnd = ct.tf(num, den)  # without delay
resp2 = Gnd(1j * w) * np.exp(-0.04j * w)
mag2 = np.abs(resp2)
phase2 = np.degrees(np.angle(resp2))
gm2, pm2, sm2, wpc2, wgc2, wms2 = ct.stability_margins((mag2, phase2, w), returnall=True)
print("Case 2 (integrator + exact delay):")
print(" all GM (linear):", gm2, "-> dB:", 20*np.log10(gm2), "at w=", wpc2)
print(" all PM (deg):", pm2, "at w=", wgc2)

# cross-check with pade approx for sanity (poly method), order 10
Gpade = ct.tf(*ct.pade(0.04, 10))
Gtot = Gnd * Gpade
gm3, pm3, wpc3, wgc3 = ct.margin(Gtot)
print(" pade10 poly cross-check: gm(dB)=", 20*np.log10(gm3), "pm=", pm3, "wpc=", wpc3, "wgc=", wgc3)
