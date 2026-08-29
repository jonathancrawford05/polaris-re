"""Anchor 2's primary metric, measured. Contrast = the by-term's own smooth.

Also resolves PLAN section 6's registered prediction, open since before slice 1:
"The MI contrast agrees better than eta does."
"""

import json
import pathlib
import sys

import numpy as np

from polaris_re.analytics.gam_fit import penalized_irls_general
from polaris_re.analytics.gam_model import assemble_model_design, resolve_family
from polaris_re.analytics.gam_model_conformance import _multiterm_model_spec

payload = json.loads(pathlib.Path(sys.argv[1]).read_text())
age_knots = tuple(float(v) for v in payload["age_knots"])
year_knots = tuple(float(v) for v in payload["year_knots"])
model = _multiterm_model_spec(age_knots, year_knots)
data = {
    k: np.asarray(payload[k], dtype=np.float64)
    for k in ("AttdAge", "PolYear", "StudyYear_C", "ExposCnt")
}
y = np.asarray(payload["y"], dtype=np.float64)
design = assemble_model_design(model, data)
family = resolve_family(model.family, model.link)
weights = data["ExposCnt"]
sy = data["StudyYear_C"]

# Fit at the SHARED sp (an input to both sides, ADR-206's arrangement).
sp_fixed = np.asarray(payload["sp_fixed"], dtype=np.float64)
penalty = np.zeros_like(design["penalty_blocks"][0])
for lam, block in zip(sp_fixed, design["penalty_blocks"], strict=True):
    penalty = penalty + lam * block
fit = penalized_irls_general(design["x"], y, family=family, penalty=penalty, weights=weights)
coef = fit.coef

eta_ours = design["x"] @ coef
eta_mgcv = np.asarray(payload["eta"], dtype=np.float64)

# The by-term's own span. Its design columns are already scaled by StudyYear_C,
# so dividing the block's contribution by StudyYear_C recovers f(age) -- which IS
# the contrast, exactly, for any StudyYear_C.
by_block = next(b for b in design["term_blocks"] if "by" in b["label"] or "StudyYear" in b["label"])
sl = slice(by_block["start"], by_block["end"])
contribution = design["x"][:, sl] @ coef[sl]
mi_ours = contribution / sy
mi_mgcv = np.asarray(payload["mi_contrast"], dtype=np.float64)

# mgcv centres predict(type="terms") per term; ours carries whatever the shared
# design implies. The contrast's LEVEL is not basis-invariant, its SHAPE is, so
# report both the raw and the mean-centred comparison and say which is which.
d_eta = np.abs(eta_ours - eta_mgcv)
d_mi_raw = np.abs(mi_ours - mi_mgcv)
d_mi_centred = np.abs((mi_ours - mi_ours.mean()) - (mi_mgcv - mi_mgcv.mean()))

print(
    f"n={len(y)}  p={design['x'].shape[1]}  by-term span={by_block['label']} "
    f"[{by_block['start']}:{by_block['end']}]"
)
print(f"shared sp (INPUT, not compared): {sp_fixed.tolist()}")
print(f"iterations: {getattr(fit, 'iterations', 'n/a')}")
print()
print(f"{'quantity':<34}{'max abs diff':>16}{'rms':>16}")
print("-" * 66)
print(f"{'eta (Anchor 2 SECONDARY)':<34}{d_eta.max():>16.6e}{np.sqrt((d_eta**2).mean()):>16.6e}")
print(f"{'MI contrast, raw':<34}{d_mi_raw.max():>16.6e}{np.sqrt((d_mi_raw**2).mean()):>16.6e}")
print(
    f"{'MI contrast, mean-centred':<34}"
    f"{d_mi_centred.max():>16.6e}{np.sqrt((d_mi_centred**2).mean()):>16.6e}"
)
print("-" * 66)
print(f"contrast range (ours): [{mi_ours.min():.6f}, {mi_ours.max():.6f}]")
print(f"contrast range (mgcv): [{mi_mgcv.min():.6f}, {mi_mgcv.max():.6f}]")
print()
better = d_mi_centred.max() < d_eta.max()
print("PLAN section 6 prediction -- 'the MI contrast agrees better than eta does':")
print(f"  contrast (centred) {d_mi_centred.max():.6e}  vs  eta {d_eta.max():.6e}")
print(f"  => {'CONFIRMED' if better else 'REFUTED'}")
