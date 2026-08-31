"""``docs/PLAN_mgcv_parity_engine.md`` slice 6b — the first multi-term
mgcv-native model's Stage-B conformance for an ``sz`` term.

The genuine parity check: :func:`fit_sz_multiterm_case` (an independent
Python assembly + fit) against ``scripts/gam_multiterm_sz_probe.R``'s own
native ``mgcv::gam()`` fit of the identical two-term formula, on the SAME
shared recipe at a fixed ``sp`` for every block. Gated on R being present,
same discipline as ``test_gam_multiterm_conformance.py``.
"""

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.experience_mgcv_conformance import rscript_mgcv_available
from polaris_re.analytics.gam_multiterm_sz_conformance import (
    SZ_MULTITERM_CLAIM,
    RSzMultiTermPayload,
    RSzMultiTermRecipe,
    compare_sz_multiterm_case,
    fit_sz_multiterm_case,
)
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import require_parity_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]

_AGE_KNOTS = [1, 2, 4, 7, 14, 18, 24, 35, 50, 70, 85, 90, 95]
"""PLAN Section 1's own target-formula knot vector for AttdAge, k=13 — the
same vector ADR-215's "sz-target-attdage-k13" Stage-A case already used."""


def _small_recipe() -> RSzMultiTermRecipe:
    """A minimal, R-free recipe — small ``n``, the real target knots (so the
    assembled shape matches production usage), values kept strictly inside
    the knot range (``gam_basis_cr``'s extrapolation behaviour is explicitly
    unverified, module docstring)."""
    n = 40
    rng = np.random.default_rng(20260831)
    age = rng.uniform(_AGE_KNOTS[0], _AGE_KNOTS[-1], size=n)
    group = rng.integers(0, 2, size=n)
    expos = rng.uniform(50.0, 500.0, size=n)
    y = rng.uniform(0.001, 0.05, size=n)
    return RSzMultiTermRecipe(
        n=n,
        AttdAge=age.tolist(),
        face_size_group=group.tolist(),
        face_size_n_levels=2,
        ExposCnt=expos.tolist(),
        y=y.tolist(),
        age_knots=[float(v) for v in _AGE_KNOTS],
        sp=[2.5, 3.5, 1.8],
    )


def test_sz_multiterm_claim_is_independent_on_every_declared_quantity() -> None:
    """ADR-193's gate: a harness result must not be able to satisfy this."""
    require_parity_evidence(SZ_MULTITERM_CLAIM.quantities, claim=SZ_MULTITERM_CLAIM.claim)
    assert SZ_MULTITERM_CLAIM.is_parity_claim


def test_fit_sz_multiterm_case_signature_takes_no_r_fit_output() -> None:
    """ADR-193's mechanical test, applied structurally at the type, same
    discipline established for
    :func:`~polaris_re.analytics.gam_multiterm_conformance.fit_multiterm_case`:
    ``r_case`` is annotated :class:`RSzMultiTermRecipe`, which has no
    ``eta``/``coef`` key at all, so a body that indexed one would be a
    `mypy` error rather than merely a convention nobody enforces."""
    import inspect
    import typing

    params = set(inspect.signature(fit_sz_multiterm_case).parameters)
    assert params == {"r_case"}

    hints = typing.get_type_hints(fit_sz_multiterm_case)
    assert hints["r_case"] is RSzMultiTermRecipe

    recipe_keys = set(RSzMultiTermRecipe.__annotations__)
    payload_keys = set(RSzMultiTermPayload.__annotations__)
    fit_only_keys = {"eta", "coef", "converged"}
    assert recipe_keys.isdisjoint(fit_only_keys)
    assert fit_only_keys <= payload_keys
    assert recipe_keys < payload_keys


def test_fit_sz_multiterm_case_shape_and_block_support() -> None:
    """R-free: the column/block-padding arithmetic through
    ``gam_model.assemble_model_design``'s ``sz`` dispatch (this slice's own
    new code path)."""
    fit, design = fit_sz_multiterm_case(_small_recipe())
    x = design["x"]
    blocks = design["penalty_blocks"]

    # p = 1 (intercept) + 12 (reference, k=13 constrained to k-1) +
    # 13 * (2 - 1) = 13 (sz, k=13, 2 levels, ADR-215's own p0*(n_levels-1)
    # design-width contract) = 26.
    assert x.shape == (40, 26)
    assert fit.eta.shape == (40,)
    assert len(blocks) == 3  # 1 reference + 2 (one per sz factor level)
    for block in blocks:
        assert block.shape == (26, 26)

    # Reference term: columns [1, 13). sz term: columns [13, 26), BOTH of
    # its two (one-per-level) blocks occupying the same range — the same
    # "not disjoint" shape ti()'s two blocks already have (ADR-206 decision 2).
    ref_s, sz_s1, sz_s2 = blocks
    for block, (lo, hi) in ((ref_s, (1, 13)), (sz_s1, (13, 26)), (sz_s2, (13, 26))):
        support = np.flatnonzero(np.any(block != 0.0, axis=0))
        assert support.size > 0, "penalty block must not be identically zero"
        assert support.min() >= lo
        assert support.max() < hi
        assert np.all(block[:lo, :] == 0.0)
        assert np.all(block[hi:, :] == 0.0)


def test_fit_sz_multiterm_case_rejects_wrong_sp_length() -> None:
    """R-free: ``fit_sz_multiterm_case``'s own guard — exactly 1 + n_levels
    sp values (reference, one per sz factor level)."""
    recipe = _small_recipe()
    recipe["sp"] = [2.5, 3.5]  # 2, not 3
    with pytest.raises(PolarisValidationError, match="3 sp values"):
        fit_sz_multiterm_case(recipe)


def test_compare_sz_multiterm_case_rejects_eta_shape_mismatch() -> None:
    """R-free: ``compare_sz_multiterm_case``'s own guard against a payload
    whose ``eta`` doesn't match the Python fit's row count."""
    recipe = _small_recipe()
    fit, _design = fit_sz_multiterm_case(recipe)
    bad_payload: RSzMultiTermPayload = {
        **recipe,
        "eta": [0.0] * (recipe["n"] - 1),  # one row short
        "coef": [0.0] * len(fit.coef),
        "converged": True,
    }
    with pytest.raises(PolarisValidationError, match="shape"):
        compare_sz_multiterm_case(fit, bad_payload)


@pytest.mark.skipif(not rscript_mgcv_available(), reason="R with mgcv is not installed here")
def test_the_r_probe_runs_end_to_end_and_agrees(tmp_path) -> None:  # pragma: no cover
    """The real conformance run, when R happens to be present.

    A disagreement here is a real result (PLAN Anchor 9: the ``sz`` term's
    own sum-to-zero constraint, the multi-term assembly's column order, or
    the per-block penalty padding differs from mgcv's for this combination),
    not a test bug to paper over.
    """
    out_path = tmp_path / "gam_multiterm_sz_probe.json"
    done = subprocess.run(
        ["Rscript", str(REPO_ROOT / "scripts" / "gam_multiterm_sz_probe.R"), str(out_path)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr

    payload = json.loads(out_path.read_text())
    fit, _design = fit_sz_multiterm_case(payload)
    comparison = compare_sz_multiterm_case(fit, payload)
    assert comparison["agrees"], comparison
