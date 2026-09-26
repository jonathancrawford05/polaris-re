"""``docs/PLAN_mgcv_capability_ladder.md`` slice 3 — L5, scale-estimated REML,
the score-level Stage-C conformance.

``scripts/gam_free_scale_reml_score_probe.R`` fits a shared two-block design
under BOTH gaussian(identity) and quasipoisson(log) at three fixed ``sp``
points via ``method="REML"``, reporting ``mgcv``'s own REML criterion
(``m$gcv.ubre``) at each. This module's
:func:`~polaris_re.analytics.gam_free_scale_reml_conformance.compare_free_scale_absolute`
compares Gaussian's ABSOLUTE score;
:func:`~polaris_re.analytics.gam_free_scale_reml_conformance.compare_free_scale_pairwise`
compares quasi-Poisson's PAIRWISE DIFFERENCES (see the module docstring for
why the two families are held to different comparison conventions).

Gated on R being present, same discipline as
``test_experience_mgcv_conformance.py``'s
``test_the_r_script_runs_end_to_end_and_agrees`` (ADR-151 / Anchor 5).
"""

import inspect
import json
import subprocess
import typing
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.experience_mgcv_conformance import rscript_mgcv_available
from polaris_re.analytics.gam_free_scale_reml_conformance import (
    FREE_SCALE_REML_SCORE_CLAIM,
    RFreeScaleReplPayload,
    RFreeScaleReplPoint,
    compare_free_scale_absolute,
    compare_free_scale_pairwise,
    score_free_scale_point,
)
from polaris_re.core.verification import require_parity_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_free_scale_reml_score_claim_is_independent_on_every_declared_quantity() -> None:
    """ADR-193's gate: a harness result must not be able to satisfy this."""
    require_parity_evidence(
        FREE_SCALE_REML_SCORE_CLAIM.quantities, claim=FREE_SCALE_REML_SCORE_CLAIM.claim
    )
    assert FREE_SCALE_REML_SCORE_CLAIM.is_parity_claim


def test_score_free_scale_point_signature_takes_no_r_score_output() -> None:
    """ADR-193's mechanical test, structurally: :func:`score_free_scale_point`
    takes plain arrays, the family and the ``sp`` setting itself — never any
    dict shaped like the R payload."""
    params = set(inspect.signature(score_free_scale_point).parameters)
    assert params == {"x", "s1", "s2", "y", "family", "sp"}

    hints = typing.get_type_hints(score_free_scale_point)
    assert "gcv_ubre" not in str(hints)

    point_keys = set(RFreeScaleReplPoint.__annotations__)
    payload_point_only_keys = {"gcv_ubre", "edf_total", "deviance", "scale", "converged"}
    assert point_keys.isdisjoint(payload_point_only_keys)
    assert "points_gaussian" in RFreeScaleReplPayload.__annotations__
    assert "points_quasipoisson" in RFreeScaleReplPayload.__annotations__


@pytest.mark.skipif(not rscript_mgcv_available(), reason="R with mgcv is not installed here")
def test_the_r_probe_runs_end_to_end_and_agrees(tmp_path) -> None:  # pragma: no cover
    """Runs ``scripts/gam_free_scale_reml_score_probe.R`` and the Python
    comparator end to end.

    **Gaussian is asserted on the ABSOLUTE score** — the free-scale branch
    was derived by profiling Wood (2011) eq. (4) over the unknown scale and
    was directly confirmed (a standalone check, before this module existed)
    to reproduce ``mgcv``'s own ``gcv.ubre`` including every additive
    constant, so an absolute disagreement here is a real regression, not an
    expected finding — same CLAUDE.md discipline as
    ``test_gam_reml_conformance``'s own end-to-end test.

    **Quasi-Poisson is asserted on PAIRWISE DIFFERENCES only** — it carries
    its own small, near-constant additive residual (module docstring), the
    SAME shape of finding ADR-196 already accepted for the known-scale
    Poisson criterion. This is not a looser bound tuned to pass; it is the
    quantity this family's own criterion was declared comparable on from the
    start (``docs/VERIFICATION_STANDARD.md`` §3.2 — the claim names the
    quantity BEFORE the code, and quasi-Poisson's absolute score was never
    named).
    """
    out_path = tmp_path / "gam_free_scale_reml_score_probe.json"
    done = subprocess.run(
        [
            "Rscript",
            str(REPO_ROOT / "scripts" / "gam_free_scale_reml_score_probe.R"),
            str(out_path),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr

    payload: RFreeScaleReplPayload = json.loads(out_path.read_text())
    x = np.asarray(payload["X"], dtype=np.float64)
    s1 = np.asarray(payload["S1"], dtype=np.float64)
    s2 = np.asarray(payload["S2"], dtype=np.float64)

    absolute = compare_free_scale_absolute(x, s1, s2, payload)
    assert len(absolute) == 3
    for c in absolute:
        assert c["agrees"], f"gaussian REML score disagreed at sp={c['sp']}: {c}"

    pairwise = compare_free_scale_pairwise(x, s1, s2, payload)
    assert len(pairwise) == 3
    for c in pairwise:
        assert c["agrees"], (
            f"quasipoisson REML score pairwise diff disagreed at {c['point_a']}-{c['point_b']}: {c}"
        )
