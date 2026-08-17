"""``docs/PLAN_mgcv_parity_engine.md`` slice 3 — the family/link Stage-B conformance.

The genuine parity check: :func:`fit_family_case` (an independent Python IRLS)
against ``scripts/gam_family_probe.R``'s own ``mgcv::gam()`` fit, on the SAME
shared design/penalty/response/weights/offset at a fixed ``sp``. Gated on R being
present, same discipline as ``test_experience_mgcv_conformance.py``'s
``test_the_r_script_runs_end_to_end_and_agrees`` (ADR-151 / Anchor 5: R stays out
of ordinary CI).
"""

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.experience_mgcv_conformance import rscript_mgcv_available
from polaris_re.analytics.gam_family_conformance import (
    FAMILY_BY_CASE,
    FAMILY_CLAIM,
    compare_family_case,
    fit_family_case,
)
from polaris_re.core.verification import require_parity_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_family_claim_is_independent_on_every_declared_quantity() -> None:
    """ADR-193's gate: a harness result must not be able to satisfy this."""
    require_parity_evidence(FAMILY_CLAIM.quantities, claim=FAMILY_CLAIM.claim)
    assert FAMILY_CLAIM.is_parity_claim


def test_fit_family_case_signature_takes_no_r_fit_output() -> None:
    """ADR-193's mechanical test, applied directly: the function's parameters
    are the shared recipe (``x``, ``s``, and the recipe fields of ``r_case``),
    never ``eta``/``coef``/``dispersion`` fed in as an argument."""
    import inspect

    params = set(inspect.signature(fit_family_case).parameters)
    assert params == {"case_name", "x", "s", "r_case"}


@pytest.mark.skipif(not rscript_mgcv_available(), reason="R with mgcv is not installed here")
def test_the_r_probe_runs_end_to_end_and_agrees(tmp_path) -> None:  # pragma: no cover
    """The real slice-3 conformance run, when R happens to be present.

    A disagreement here is a real result (PLAN Anchor 9: this engine's IRLS or
    family/link formulas differ from mgcv's for this combination), not a test
    bug to paper over.
    """
    out_path = tmp_path / "gam_family_probe.json"
    done = subprocess.run(
        ["Rscript", str(REPO_ROOT / "scripts" / "gam_family_probe.R"), str(out_path)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr

    payload = json.loads(out_path.read_text())
    x = np.asarray(payload["X"], dtype=np.float64)
    s = np.asarray(payload["S"], dtype=np.float64)

    failures = []
    for case_name in FAMILY_BY_CASE:
        r_case = payload["cases"][case_name]
        fit = fit_family_case(case_name, x, s, r_case)
        comparison = compare_family_case(case_name, x, s, fit, r_case)
        if not comparison["agrees"]:
            failures.append((case_name, comparison))
    assert not failures, f"slice 3 disagreed on: {failures}"
