"""``docs/PLAN_mgcv_parity_engine.md`` slice 7 — ``select = TRUE``'s Stage-B
conformance on the same three-term model ADR-206 already verified at fixed
``sp``. Gated on R being present, same discipline as
``test_gam_multiterm_conformance.py``.
"""

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.experience_mgcv_conformance import rscript_mgcv_available
from polaris_re.analytics.gam_select_multiterm_conformance import (
    SELECT_MULTITERM_CLAIM,
    RSelectMultiTermPayload,
    RSelectMultiTermRecipe,
    compare_select_multiterm_case,
    fit_select_multiterm_case,
)
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import require_parity_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]

_AGE_KNOTS = [1, 2, 4, 7, 14, 18, 24, 35, 50, 70, 85, 90, 95]
_YEAR_KNOTS = [1, 2, 3, 5, 10, 21]


def _small_recipe() -> RSelectMultiTermRecipe:
    """A minimal, R-free recipe — small ``n``, the real target knots, values
    kept strictly inside the knot range (``gam_basis_cr``'s extrapolation
    behaviour is explicitly unverified, module docstring)."""
    n = 60
    rng = np.random.default_rng(20260901)
    age = rng.uniform(_AGE_KNOTS[0], _AGE_KNOTS[-1], size=n)
    year = rng.uniform(_YEAR_KNOTS[0], _YEAR_KNOTS[-1], size=n)
    study_year = rng.uniform(-5.0, 5.0, size=n)
    expos = rng.uniform(50.0, 500.0, size=n)
    y = rng.uniform(0.001, 0.05, size=n)
    return RSelectMultiTermRecipe(
        n=n,
        AttdAge=age.tolist(),
        PolYear=year.tolist(),
        StudyYear_C=study_year.tolist(),
        ExposCnt=expos.tolist(),
        y=y.tolist(),
        age_knots=[float(v) for v in _AGE_KNOTS],
        year_knots=[float(v) for v in _YEAR_KNOTS],
        sp=[2.0, 5.0, 3.0, 6.0, 1.5, 4.0, 7.0],
    )


def test_select_multiterm_claim_is_independent_on_every_declared_quantity() -> None:
    """ADR-193's gate: a harness result must not be able to satisfy this."""
    require_parity_evidence(SELECT_MULTITERM_CLAIM.quantities, claim=SELECT_MULTITERM_CLAIM.claim)
    assert SELECT_MULTITERM_CLAIM.is_parity_claim


def test_fit_select_multiterm_case_signature_takes_no_r_fit_output() -> None:
    """ADR-193's mechanical test, applied structurally at the type — same
    discipline established for
    :func:`~polaris_re.analytics.gam_multiterm_conformance.fit_multiterm_case`."""
    import inspect
    import typing

    params = set(inspect.signature(fit_select_multiterm_case).parameters)
    assert params == {"r_case"}

    hints = typing.get_type_hints(fit_select_multiterm_case)
    assert hints["r_case"] is RSelectMultiTermRecipe

    recipe_keys = set(RSelectMultiTermRecipe.__annotations__)
    payload_keys = set(RSelectMultiTermPayload.__annotations__)
    fit_only_keys = {"eta", "coef", "converged"}
    assert recipe_keys.isdisjoint(fit_only_keys)
    assert fit_only_keys <= payload_keys
    assert recipe_keys < payload_keys


def test_fit_select_multiterm_case_assembles_seven_blocks() -> None:
    """R-free: the block count select=True adds — 2 (s(AttdAge)) + 2
    (s(AttdAge,by=StudyYear_C)) + 3 (ti(...): its own existing 2 plus one
    null-space block) — never one extra block per existing penalty."""
    fit, penalty_blocks = fit_select_multiterm_case(_small_recipe())
    assert len(penalty_blocks) == 7
    assert fit.eta.shape == (60,)


def test_fit_select_multiterm_case_rejects_wrong_sp_length() -> None:
    """R-free: :func:`fit_select_multiterm_case`'s own guard — exactly 7 sp
    values."""
    recipe = _small_recipe()
    recipe["sp"] = [2.0, 5.0, 3.0]  # 3, not 7
    with pytest.raises(PolarisValidationError, match="7 sp values"):
        fit_select_multiterm_case(recipe)


def test_compare_select_multiterm_case_rejects_eta_shape_mismatch() -> None:
    """R-free: :func:`compare_select_multiterm_case`'s own guard against a
    payload whose ``eta`` doesn't match the Python fit's row count."""
    recipe = _small_recipe()
    fit, _blocks = fit_select_multiterm_case(recipe)
    bad_payload: RSelectMultiTermPayload = {
        **recipe,
        "eta": [0.0] * (recipe["n"] - 1),  # one row short
        "coef": [0.0] * len(fit.coef),
        "converged": True,
    }
    with pytest.raises(PolarisValidationError, match="shape"):
        compare_select_multiterm_case(fit, bad_payload)


@pytest.mark.skipif(not rscript_mgcv_available(), reason="R with mgcv is not installed here")
def test_the_r_probe_runs_end_to_end_and_agrees(tmp_path) -> None:  # pragma: no cover
    """The real conformance run, when R happens to be present.

    A disagreement here is a real result (PLAN Anchor 9: the null-space
    penalty rule, the multi-term assembly, or the per-block penalty padding
    differs from mgcv's for this combination), not a test bug to paper over.
    """
    out_path = tmp_path / "gam_select_multiterm_probe.json"
    done = subprocess.run(
        [
            "Rscript",
            str(REPO_ROOT / "scripts" / "gam_select_multiterm_probe.R"),
            str(out_path),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr

    payload = json.loads(out_path.read_text())
    fit, _blocks = fit_select_multiterm_case(payload)
    comparison = compare_select_multiterm_case(fit, payload)
    assert comparison["agrees"], comparison
