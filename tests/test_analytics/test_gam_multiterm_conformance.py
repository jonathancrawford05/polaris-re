"""``docs/CONTINUATION_mgcv_parity_engine.md``, slice 5's remaining scope — the
first multi-term mgcv-native model's Stage-B conformance.

The genuine parity check: :func:`fit_multiterm_case` (an independent Python
assembly + fit) against ``scripts/gam_multiterm_probe.R``'s own native
``mgcv::gam()`` fit of the identical three-term formula, on the SAME shared
recipe at a fixed ``sp`` for every block. Gated on R being present, same
discipline as ``test_gam_family_conformance.py``.
"""

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.experience_mgcv_conformance import rscript_mgcv_available
from polaris_re.analytics.gam_multiterm_conformance import (
    MULTITERM_CLAIM,
    RMultiTermPayload,
    RMultiTermRecipe,
    assemble_multiterm_design,
    compare_multiterm_case,
    fit_multiterm_case,
)
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import require_parity_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]

_AGE_KNOTS = [1, 2, 4, 7, 14, 18, 24, 35, 50, 70, 85, 90, 95]
"""PLAN Section 1's own target-formula knot vector for AttdAge, k=13."""
_YEAR_KNOTS = [1, 2, 3, 5, 10, 21]
"""PLAN Section 1's own target-formula knot vector for PolYear, k=6."""


def _small_recipe() -> RMultiTermRecipe:
    """A minimal, R-free recipe — small ``n``, the real target knots (so the
    assembled shape matches production usage), values kept strictly inside
    each knot range (``gam_basis_cr``'s extrapolation behaviour is explicitly
    unverified, module docstring)."""
    n = 40
    rng = np.random.default_rng(20260825)
    age = rng.uniform(_AGE_KNOTS[0], _AGE_KNOTS[-1], size=n)
    year = rng.uniform(_YEAR_KNOTS[0], _YEAR_KNOTS[-1], size=n)
    study_year_c = rng.uniform(-5.0, 5.0, size=n)
    expos = rng.uniform(50.0, 500.0, size=n)
    y = rng.uniform(0.001, 0.05, size=n)
    return RMultiTermRecipe(
        n=n,
        AttdAge=age.tolist(),
        PolYear=year.tolist(),
        StudyYear_C=study_year_c.tolist(),
        ExposCnt=expos.tolist(),
        y=y.tolist(),
        age_knots=[float(v) for v in _AGE_KNOTS],
        year_knots=[float(v) for v in _YEAR_KNOTS],
        sp=[2.0, 3.0, 1.5, 4.0],
    )


def test_multiterm_claim_is_independent_on_every_declared_quantity() -> None:
    """ADR-193's gate: a harness result must not be able to satisfy this."""
    require_parity_evidence(MULTITERM_CLAIM.quantities, claim=MULTITERM_CLAIM.claim)
    assert MULTITERM_CLAIM.is_parity_claim


def test_fit_multiterm_case_signature_takes_no_r_fit_output() -> None:
    """ADR-193's mechanical test, applied structurally at the type, same
    discipline PR #202 review [P1] established for
    :func:`~polaris_re.analytics.gam_family_conformance.fit_family_case`:
    ``r_case`` is annotated :class:`RMultiTermRecipe`, which has no
    ``eta``/``coef`` key at all, so a body that indexed one would be a `mypy`
    error rather than merely a convention nobody enforces."""
    import inspect
    import typing

    params = set(inspect.signature(fit_multiterm_case).parameters)
    assert params == {"r_case"}

    hints = typing.get_type_hints(fit_multiterm_case)
    assert hints["r_case"] is RMultiTermRecipe

    recipe_keys = set(RMultiTermRecipe.__annotations__)
    payload_keys = set(RMultiTermPayload.__annotations__)
    fit_only_keys = {"eta", "coef", "converged"}
    assert recipe_keys.isdisjoint(fit_only_keys)
    assert fit_only_keys <= payload_keys
    assert recipe_keys < payload_keys


def test_assemble_multiterm_design_shape_and_block_support() -> None:
    """R-free (PR #210 review [P2-1]): the column/block-padding arithmetic —
    the exact thing the session that wrote this module got wrong on its first
    run (a ``ValueError`` from padding ``ti()``'s two penalty blocks at
    sequential rather than identical offsets) — is otherwise unexercised on
    any machine without R, including CI's Python job (ADR-151 never has R
    there). Locks the fix in without needing the oracle.
    """
    design = assemble_multiterm_design(_small_recipe())
    x = design["x"]
    blocks = design["penalty_blocks"]

    # p = 1 (intercept) + 12 (reference, k=13 constrained to k-1) +
    # 13 (MI by-term, k=13 UNCONSTRAINED) + 60 (ti(), (13-1)*(6-1)) = 86 —
    # the same arithmetic ADR-206 and the session log both cite.
    assert x.shape == (40, 86)
    assert len(blocks) == 4
    for block in blocks:
        assert block.shape == (86, 86)

    # Reference term: columns [1, 13). MI by-term: columns [13, 26). ti()'s
    # two blocks BOTH occupy columns [26, 86) — the same range, not disjoint
    # ranges (ADR-206 decision 2) — which is exactly what the first draft got
    # wrong.
    ref_s, by_s, ti_s1, ti_s2 = blocks
    for block, (lo, hi) in (
        (ref_s, (1, 13)),
        (by_s, (13, 26)),
        (ti_s1, (26, 86)),
        (ti_s2, (26, 86)),
    ):
        support = np.flatnonzero(np.any(block != 0.0, axis=0))
        assert support.size > 0, "penalty block must not be identically zero"
        assert support.min() >= lo
        assert support.max() < hi
        # And nothing spills outside [lo, hi) on the other axis either.
        assert np.all(block[:lo, :] == 0.0)
        assert np.all(block[hi:, :] == 0.0)


def test_fit_multiterm_case_rejects_wrong_sp_length() -> None:
    """R-free (PR #210 review [P2-2]): ``fit_multiterm_case``'s own guard —
    exactly 4 sp values (reference, by, ti#1, ti#2), one per penalty block."""
    recipe = _small_recipe()
    recipe["sp"] = [2.0, 3.0, 1.5]  # 3, not 4
    with pytest.raises(PolarisValidationError, match="4 sp values"):
        fit_multiterm_case(recipe)


def test_compare_multiterm_case_rejects_eta_shape_mismatch() -> None:
    """R-free (PR #210 review [P2-2]): ``compare_multiterm_case``'s own guard
    against a payload whose ``eta`` doesn't match the Python fit's row count."""
    recipe = _small_recipe()
    fit, _design = fit_multiterm_case(recipe)
    bad_payload: RMultiTermPayload = {
        **recipe,
        "eta": [0.0] * (recipe["n"] - 1),  # one row short
        "coef": [0.0] * len(fit.coef),
        "converged": True,
    }
    with pytest.raises(PolarisValidationError, match="shape"):
        compare_multiterm_case(fit, bad_payload)


@pytest.mark.skipif(not rscript_mgcv_available(), reason="R with mgcv is not installed here")
def test_the_r_probe_runs_end_to_end_and_agrees(tmp_path) -> None:  # pragma: no cover
    """The real conformance run, when R happens to be present.

    A disagreement here is a real result (PLAN Anchor 9: the multi-term
    assembly — column order, per-block penalty padding, or one of the three
    basis producers themselves — differs from mgcv's for this combination),
    not a test bug to paper over.
    """
    out_path = tmp_path / "gam_multiterm_probe.json"
    done = subprocess.run(
        ["Rscript", str(REPO_ROOT / "scripts" / "gam_multiterm_probe.R"), str(out_path)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr

    payload = json.loads(out_path.read_text())
    fit, _design = fit_multiterm_case(payload)
    comparison = compare_multiterm_case(fit, payload)
    assert comparison["agrees"], comparison
