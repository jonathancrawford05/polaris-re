"""``docs/PLAN_mgcv_parity_engine.md`` slice 4 part A — the REML-score Stage-C conformance.

``scripts/gam_reml_probe.R`` fits a shared binomial/logit design with two
independently-scaled penalty blocks at three fixed ``sp`` points and reports
``mgcv``'s own REML criterion (``m$gcv.ubre``) and deviance at each. This
module's :func:`~polaris_re.analytics.gam_reml_conformance.compare_reml_points`
fits and scores the same points independently and compares PAIRWISE
DIFFERENCES (see that module's docstring for why the absolute value is not
compared); :func:`~polaris_re.analytics.gam_reml_conformance.compare_reml_deviance`
compares the deviance directly (per point, not pairwise — deviance carries no
additive convention offset to cancel).

Gated on R being present, same discipline as
``test_experience_mgcv_conformance.py``'s
``test_the_r_script_runs_end_to_end_and_agrees`` (ADR-151 / Anchor 5).
"""

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.experience_mgcv_conformance import rscript_mgcv_available
from polaris_re.analytics.gam_reml_conformance import (
    REML_SCORE_CLAIM,
    compare_reml_deviance,
    compare_reml_points,
)
from polaris_re.core.verification import require_parity_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_reml_score_claim_is_independent_on_every_declared_quantity() -> None:
    """ADR-193's gate: a harness result must not be able to satisfy this."""
    require_parity_evidence(REML_SCORE_CLAIM.quantities, claim=REML_SCORE_CLAIM.claim)
    assert REML_SCORE_CLAIM.is_parity_claim


def test_score_reml_point_signature_takes_no_r_score_output() -> None:
    """ADR-193's mechanical test, structurally: :func:`score_reml_point`
    takes plain arrays and the ``sp`` setting itself, never any dict shaped
    like the R payload — a stronger form of the recipe/payload TypedDict
    split PR #202 review [P1] established for slice 3, since there is no
    R-payload-shaped parameter at all for a body to misuse."""
    import inspect
    import typing

    from polaris_re.analytics.gam_reml_conformance import (
        RReplPayload,
        RReplPoint,
        score_reml_point,
    )

    params = set(inspect.signature(score_reml_point).parameters)
    assert params == {"x", "s1", "s2", "y", "weights", "sp"}

    hints = typing.get_type_hints(score_reml_point)
    assert "gcv_ubre" not in str(hints)

    point_keys = set(RReplPoint.__annotations__)
    payload_point_only_keys = {"gcv_ubre", "edf_total", "deviance", "converged"}
    assert point_keys.isdisjoint(payload_point_only_keys)
    assert "points" in RReplPayload.__annotations__


def test_deviance_reml_point_signature_takes_no_r_score_output() -> None:
    """Same mechanical-test shape as
    :func:`test_score_reml_point_signature_takes_no_r_score_output`, for the
    deviance producer PR #203 review [P1-1] added."""
    import inspect
    import typing

    from polaris_re.analytics.gam_reml_conformance import deviance_reml_point

    params = set(inspect.signature(deviance_reml_point).parameters)
    assert params == {"x", "s1", "s2", "y", "weights", "sp"}

    hints = typing.get_type_hints(deviance_reml_point)
    assert "gcv_ubre" not in str(hints)


@pytest.mark.skipif(not rscript_mgcv_available(), reason="R with mgcv is not installed here")
def test_the_r_probe_runs_end_to_end_and_agrees(tmp_path) -> None:  # pragma: no cover
    """Runs ``scripts/gam_reml_probe.R`` and the Python comparator end to end.

    **Asserts BOTH deviance and score agreement.** ADR-196's first
    measurement found the naive multi-block generalization of
    ``experience_gam_penalized.reml_score`` reproduced ``mgcv``'s deviance
    (the fit was correct) but NOT its REML score's pairwise dependence on
    lambda — all three pairwise comparisons missed the declared 1e-6
    tolerance. ADR-196's resolution (same day) found and fixed the cause:
    the score was missing the penalized-deviance term ``β̂ᵀSβ̂`` that Wood
    (2011) §2 eq. (4) requires (see ``gam_reml.reml_score_general``'s
    docstring for the citation). With the fix, all three pairs agree to
    float round-trip precision. A disagreement here is now a real
    regression, not an expected/documented finding — CLAUDE.md: never widen
    a tolerance to make a disagreement pass; if this test goes red, the
    formula broke again, it was not miscalibrated.
    """
    out_path = tmp_path / "gam_reml_probe.json"
    done = subprocess.run(
        ["Rscript", str(REPO_ROOT / "scripts" / "gam_reml_probe.R"), str(out_path)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr

    payload = json.loads(out_path.read_text())
    x = np.asarray(payload["X"], dtype=np.float64)
    s1 = np.asarray(payload["S1"], dtype=np.float64)
    s2 = np.asarray(payload["S2"], dtype=np.float64)

    deviance_comparisons = compare_reml_deviance(x, s1, s2, payload)
    assert len(deviance_comparisons) == 3
    for d in deviance_comparisons:
        assert d["agrees"], f"deviance disagreed at sp={d['sp']}: {d}"

    comparisons = compare_reml_points(x, s1, s2, payload)
    assert len(comparisons) == 3
    for c in comparisons:
        assert c["agrees"], f"REML score disagreed at {c['point_a']}-{c['point_b']}: {c}"
