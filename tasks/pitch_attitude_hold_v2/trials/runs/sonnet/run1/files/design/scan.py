import numpy as np
from loop import load_plant, loop_gain, find_margins

PLANTS = {va: load_plant(va) for va in (20, 25, 32)}
OMEGA = np.logspace(-3, 3, 30001)


def eval_gains(Kp, Ki, Kq, omega=OMEGA, verbose=False):
    worst_gm = np.inf
    worst_pm = np.inf
    wgc_min = np.inf
    details = {}
    for va, (A, B, C, trim) in PLANTS.items():
        L = loop_gain(Kp, Ki, Kq, A, B, C, omega)
        GM_db, PM_deg, wpc, wgc = find_margins(L, omega)
        gm = np.min(np.abs(GM_db)) if len(GM_db) else np.inf
        pm = np.min(PM_deg) if len(PM_deg) else np.inf
        worst_gm = min(worst_gm, gm)
        worst_pm = min(worst_pm, pm)
        if len(wgc):
            wgc_min = min(wgc_min, np.min(wgc))
        details[va] = dict(gm=gm, pm=pm, wgc=wgc, wpc=wpc, GM_db=GM_db, PM_deg=PM_deg)
        if verbose:
            print(f"  va={va}: worst_gm_db={gm:.2f} worst_pm={pm:.2f} wgc={np.round(wgc,3)}")
    return worst_gm, worst_pm, wgc_min, details


if __name__ == "__main__":
    import itertools
    candidates = []
    for kp in (0.5, 1, 1.5, 2, 3, 4, 5, 7):
        for ki in (0.1, 0.2, 0.3, 0.5, 0.8, 1.2, 2.0):
            for kq in (0.05, 0.1, 0.2, 0.3, 0.5, 0.8, 1.2):
                Kp, Ki, Kq = -kp, -ki, -kq
                wgm, wpm, wgc_min, _ = eval_gains(Kp, Ki, Kq)
                if wgm >= 6.0 and wpm >= 45.0:
                    candidates.append((kp, ki, kq, wgm, wpm, wgc_min))
    candidates.sort(key=lambda c: -c[5])  # prefer highest min gain-crossover freq
    print(f"{len(candidates)} feasible candidates (of {8*7*7})")
    for c in candidates[:25]:
        print(f"kp={c[0]:.2f} ki={c[1]:.2f} kq={c[2]:.2f}  GM={c[3]:.2f}dB PM={c[4]:.2f}deg  wgc_min={c[5]:.3f}")
