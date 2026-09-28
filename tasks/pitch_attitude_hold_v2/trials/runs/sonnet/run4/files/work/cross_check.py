import sys, pathlib
import numpy as np

HERE = pathlib.Path(__file__).parent
ENV = HERE.parent / "environment"
sys.path.insert(0, str(ENV))
sys.path.insert(0, str(HERE))

import aircraft_model as am  # noqa: E402
import model_fast as mf  # noqa: E402

p_np = am.load_params()
p_fast = mf.load_params()

rng = np.random.default_rng(0)
maxerr = 0.0
for trial in range(2000):
    u = rng.uniform(15, 35)
    w = rng.uniform(-5, 5)
    q = rng.uniform(-0.5, 0.5)
    theta = rng.uniform(-0.3, 0.3)
    de = rng.uniform(-0.5, 0.5)
    dt = rng.uniform(0.0, 1.0)
    d_np = am.derivatives(p_np, [u, w, q, theta], [de, dt])
    d_fast = mf.derivatives(p_fast, u, w, q, theta, de, dt)
    err = np.max(np.abs(np.array(d_fast) - d_np))
    maxerr = max(maxerr, err)

print("max abs error across 2000 random points:", maxerr)

# also check at the three actual trims
import json
for spd in (20, 25, 32):
    d = json.loads((ENV / f"plant_{spd}.json").read_text())
    st = d["trim"]["state"]
    de = d["trim"]["delta_e_rad"]
    dth = d["trim"]["delta_t"]
    d_np = am.derivatives(p_np, st, [de, dth])
    d_fast = mf.derivatives(p_fast, *st, de, dth)
    print(spd, "trim residual np:", d_np, " fast:", d_fast)
