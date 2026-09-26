"""Capability ladder rung **L1** — ``gaussian(identity)`` against ``mgcv`` at
fixed ``sp`` (``docs/PLAN_mgcv_capability_ladder.md`` slice 1).

The provenance gate (ADR-193): both quantities
:data:`GAUSSIAN_CLAIM` declares are ``INDEPENDENT``, and
:func:`fit_gaussian_case`'s signature structurally cannot see ``mgcv``'s fit
(:class:`RGaussianRecipe` has no ``eta``/``edf_total`` key). The R round trip is
gated on R being present, same discipline as the sibling conformance modules.

**What these tests pin, and what they do not.** They pin the *structure* that
makes the measurement legible — the block count, the claim's shape, the two
independence guarantees — rather than a particular agreement magnitude, which is
a property of the recipe and the oracle version and belongs in the ledger.
"""

import json
import subprocess
import typing
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.experience_mgcv_conformance import rscript_mgcv_available
from polaris_re.analytics.gam_gaussian_conformance import (
    GAUSSIAN_CLAIM,
    GAUSSIAN_FREE_SP_CLAIM,
    RGaussianFreeSpPayload,
    RGaussianFreeSpRecipe,
    RGaussianPayload,
    RGaussianRecipe,
    compare_gaussian_case,
    compare_gaussian_free_sp_case,
    fit_gaussian_case,
    fit_gaussian_free_sp_case,
    gaussian_model_spec,
)
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import require_parity_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]

_AGE_KNOTS = [1.0, 2.0, 4.0, 7.0, 14.0, 18.0, 24.0, 35.0, 50.0, 70.0, 85.0, 90.0, 95.0]
_YEAR_KNOTS = [1.0, 2.0, 3.0, 5.0, 10.0, 21.0]
_SP = [2.0, 3.0, 1.5, 4.0]

_MGCV_PRODUCED_KEYS = ("eta", "edf_total", "offset_gap", "coef", "converged")
"""Every ``mgcv``-produced key :class:`RGaussianPayload` **declares**. The
independence tests plant exactly these, so one cannot be added to the type
without the strip test noticing."""

_MGCV_DIAGNOSTIC_KEYS = (
    "edf_per_smooth",
    "scale",
    "scale_estimated",
    "mgcv_version",
    "r_version",
    "schema_version",
)
"""``mgcv``-produced keys the R probe ALSO writes but the payload type does not
declare — diagnostics, never compared.

They are named here rather than ignored because "the type has no ``eta`` key" is
a claim about :class:`RGaussianPayload`, not about the JSON, and the JSON is what
the round trip actually hands :func:`fit_gaussian_case`. The strip test plants
these too, so the guarantee covers what the probe really exports."""


def _recipe(n: int = 240, seed: int = 20260919) -> RGaussianRecipe:
    """A recipe of the probe's own shape, small enough for an R-free unit test."""
    rng = np.random.default_rng(seed)
    age = rng.uniform(1.0, 95.0, size=n)
    year = rng.uniform(1.0, 21.0, size=n)
    by = rng.uniform(-5.0, 5.0, size=n)
    mu = (
        2.5
        + 0.03 * age
        - 0.02 * year
        + 0.01 * by * (age - 50.0) / 50.0
        + 0.15 * np.sin(age / 10.0) * np.cos(year / 3.0)
    )
    y = mu + rng.normal(scale=0.25, size=n)
    return RGaussianRecipe(
        n=n,
        AttdAge=age.tolist(),
        PolYear=year.tolist(),
        StudyYear_C=by.tolist(),
        y=y.tolist(),
        age_knots=list(_AGE_KNOTS),
        year_knots=list(_YEAR_KNOTS),
        sp=list(_SP),
    )


# --------------------------------------------------------------------------
# Provenance (ADR-193 / ADR-228)
# --------------------------------------------------------------------------


def test_both_declared_quantities_are_parity_evidence() -> None:
    """Rung L1 IS a two-producer comparison: this engine is one of the two in
    each column, so both are INDEPENDENT and the gate must pass on the full set.

    Contrast with the production-MI claim, where three columns are
    ``REFERENCE_INTERNAL`` (mgcv on both sides) and the gate raises on the full
    set — ADR-228. There are no such columns here.
    """
    require_parity_evidence(GAUSSIAN_CLAIM.quantities, claim=GAUSSIAN_CLAIM.claim)
    assert GAUSSIAN_CLAIM.is_parity_claim
    assert len(GAUSSIAN_CLAIM.parity_quantities) == 2
    assert GAUSSIAN_CLAIM.reference_internal_quantities == ()


def test_fit_signature_structurally_cannot_read_mgcvs_fit() -> None:
    """ADR-193's mechanical test, applied at the type."""
    hints = typing.get_type_hints(fit_gaussian_case)
    assert hints["r_case"] is RGaussianRecipe

    recipe_keys = set(RGaussianRecipe.__annotations__)
    payload_keys = set(RGaussianPayload.__annotations__)
    assert recipe_keys.isdisjoint(_MGCV_PRODUCED_KEYS)
    assert set(_MGCV_PRODUCED_KEYS) <= payload_keys
    # The diagnostics are by construction NOT part of either type — that is what
    # makes them diagnostics. Pinned so that promoting one to the payload without
    # thinking about provenance fails here.
    assert recipe_keys.isdisjoint(_MGCV_DIAGNOSTIC_KEYS)
    assert payload_keys.isdisjoint(_MGCV_DIAGNOSTIC_KEYS)


def test_the_fit_is_unchanged_when_every_mgcv_key_is_stripped() -> None:
    """The RUNTIME complement to the structural guarantee above.

    The type says :func:`fit_gaussian_case` cannot see ``mgcv``'s fit; Python
    does not enforce ``TypedDict`` at runtime, so this proves the *code* does not
    read them either. Both ``eta`` and ``edf_total`` must be bit-identical with
    those keys absent.

    This exists because the tier-1 ``edf_total`` agreement was **exactly zero**
    — a number worth interrogating rather than celebrating. It is real, and this
    is what makes that checkable rather than asserted. (Tier 3, on a different
    ``mgcv`` build, reads ``-7.105e-15`` instead: the floating-point floor
    without bit coincidence, which is what two independent implementations
    should look like. See ADR-229.)

    The planted values cover BOTH the keys the payload type declares and the
    diagnostics the R probe additionally writes — the round trip hands this
    function the real JSON, not a value of the declared type, so a guarantee
    that stopped at the type would not cover what actually arrives.
    """
    recipe = _recipe()
    payload = typing.cast(
        RGaussianPayload,
        {
            **recipe,
            "eta": [0.0],
            "edf_total": -999.0,
            "offset_gap": 0.0,
            "coef": [0.0],
            "converged": True,
            # Undeclared diagnostics the probe also exports (_MGCV_DIAGNOSTIC_KEYS).
            "edf_per_smooth": [-999.0],
            "scale": -999.0,
            "scale_estimated": True,
            "mgcv_version": "0.0.0",
            "r_version": "not a version",
            "schema_version": -1,
        },
    )
    with_payload = fit_gaussian_case(typing.cast(RGaussianRecipe, payload))
    recipe_only = fit_gaussian_case(recipe)

    assert with_payload.edf_total == recipe_only.edf_total
    np.testing.assert_array_equal(with_payload.fit.eta, recipe_only.fit.eta)
    # The planted edf_total is absurd; if it leaked, the number would show it.
    assert with_payload.edf_total > 0.0


def test_edf_total_is_computed_and_moves_with_the_penalty() -> None:
    """The other half of "computed, not echoed": a genuinely derived ``edf``
    responds to ``sp``. A constant would pass the strip test above and fail this
    one."""
    recipe = _recipe()
    base = fit_gaussian_case(recipe).edf_total
    stiffer = fit_gaussian_case({**recipe, "sp": [20.0, 3.0, 1.5, 4.0]}).edf_total
    assert stiffer < base, "a larger smoothing parameter must reduce the edf"


def test_claim_sentence_names_its_tolerances_and_its_limit() -> None:
    """``VERIFICATION_STANDARD.md`` §3.2 / ADR-219 amendment 1: the sentence
    names the quantities, the tolerances and the regime it does NOT reach, and
    never says bare "parity"."""
    claim = GAUSSIAN_CLAIM.claim
    assert "2e-2" in claim
    assert "1.0" in claim
    assert "FIXED sp only" in claim
    assert "IMPORTED and not redeclared" in claim
    assert "mgcv parity" not in claim.lower()


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------


def test_model_spec_is_the_multiterm_design_with_only_the_family_changed() -> None:
    """The comparison's whole design: every basis is already tier-3 verified, so
    the FAMILY is the only unverified thing in it."""
    model = gaussian_model_spec(tuple(_AGE_KNOTS), tuple(_YEAR_KNOTS))
    assert model.family == "gaussian"
    assert model.link == "identity"
    assert [t.basis for t in model.terms] == ["cr", "cr", "ti"]
    assert model.terms[1].by == "StudyYear_C"
    assert model.weights_column is None


def test_fit_rejects_a_wrong_block_count() -> None:
    recipe = _recipe()
    with pytest.raises(PolarisValidationError, match="expected 4 sp values"):
        fit_gaussian_case({**recipe, "sp": [1.0, 2.0]})


def test_compare_rejects_a_length_mismatch() -> None:
    recipe = _recipe()
    fit = fit_gaussian_case(recipe)
    payload = typing.cast(
        RGaussianPayload,
        {
            **recipe,
            "eta": [0.0, 1.0],
            "edf_total": 10.0,
            "offset_gap": 0.0,
            "coef": [0.0],
            "converged": True,
        },
    )
    with pytest.raises(PolarisValidationError, match="R eta has shape"):
        compare_gaussian_case(fit, payload)


def test_comparison_gates_on_both_quantities() -> None:
    """A large ``edf`` disagreement must fail even when ``eta`` agrees — the
    two-part criterion is ADR-221's, and gating on ``eta`` alone would silently
    weaken it."""
    recipe = _recipe()
    fit = fit_gaussian_case(recipe)
    good = typing.cast(
        RGaussianPayload,
        {
            **recipe,
            "eta": fit.fit.eta.tolist(),
            "edf_total": fit.edf_total,
            "offset_gap": 0.0,
            "coef": [0.0],
            "converged": True,
        },
    )
    assert compare_gaussian_case(fit, good)["agrees"]

    edf_off = typing.cast(RGaussianPayload, {**good, "edf_total": fit.edf_total + 5.0})
    result = compare_gaussian_case(fit, edf_off)
    assert not result["agrees"]
    assert result["max_abs_eta_diff"] == pytest.approx(0.0, abs=1e-15)


# --------------------------------------------------------------------------
# The end-to-end round trip, gated on R
# --------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.skipif(not rscript_mgcv_available(), reason="Rscript with mgcv not available")
def test_round_trip_against_mgcv(tmp_path: Path) -> None:
    """Tier 1: run the probe and measure against it.

    A local reading is a HYPOTHESIS (``ROUTINE_MGCV_PARITY.md``); only the pinned
    digest settles it, which is what the ``mgcv-conformance.yml`` step is for.
    This asserts the committed criterion, not a particular magnitude.
    """
    out = tmp_path / "gam_gaussian_probe.json"
    subprocess.run(
        ["Rscript", str(REPO_ROOT / "scripts" / "gam_gaussian_probe.R"), str(out)],
        check=True,
        capture_output=True,
    )
    payload = typing.cast(RGaussianPayload, json.loads(out.read_text()))

    result = compare_gaussian_case(fit_gaussian_case(payload), payload)
    assert result["agrees"], result
    # The offset tripwire: this recipe carries no offset, so the probe's two eta
    # readings must coincide. A non-zero would mean predict() was dropping one.
    assert result["offset_gap"] == 0.0


# --------------------------------------------------------------------------
# FREE sp — capability ladder rung L5 (PLAN_mgcv_capability_ladder.md slice 3).
# Removes THIS module's own "fixed sp only" qualifier from slice 1.
# --------------------------------------------------------------------------


def test_free_sp_claim_is_independent_on_every_declared_quantity() -> None:
    require_parity_evidence(GAUSSIAN_FREE_SP_CLAIM.quantities, claim=GAUSSIAN_FREE_SP_CLAIM.claim)
    assert GAUSSIAN_FREE_SP_CLAIM.is_parity_claim


def test_free_sp_fit_signature_structurally_cannot_read_mgcvs_fit() -> None:
    """ADR-193's mechanical test, applied at the type — the free-sp sibling of
    :func:`test_fit_signature_structurally_cannot_read_mgcvs_fit`."""
    hints = typing.get_type_hints(fit_gaussian_free_sp_case)
    assert hints["r_case"] is RGaussianFreeSpRecipe

    recipe_keys = set(RGaussianFreeSpRecipe.__annotations__)
    payload_only_keys = {"eta", "sp", "edf_total", "term_edf", "offset_gap", "coef", "converged"}
    payload_keys = set(RGaussianFreeSpPayload.__annotations__)
    assert recipe_keys.isdisjoint(payload_only_keys)
    assert payload_only_keys <= payload_keys
    assert "sp" not in recipe_keys  # free sp is what this measures, not a shared input


def test_free_sp_claim_sentence_names_its_tolerances() -> None:
    claim = GAUSSIAN_FREE_SP_CLAIM.claim
    assert "2e-2" in claim
    assert "1.0" in claim
    assert "IMPORTED and not redeclared" in claim


@pytest.mark.slow
@pytest.mark.skipif(not rscript_mgcv_available(), reason="Rscript with mgcv not available")
def test_free_sp_round_trip_against_mgcv(tmp_path: Path) -> None:
    """Tier 1: run the free-sp probe and measure against it. The deliverable
    that lifts slice 1's own "fixed sp only" qualifier
    (``PLAN_mgcv_capability_ladder.md`` slice 3's own acceptance)."""
    out = tmp_path / "gam_gaussian_free_sp_probe.json"
    subprocess.run(
        ["Rscript", str(REPO_ROOT / "scripts" / "gam_gaussian_free_sp_probe.R"), str(out)],
        check=True,
        capture_output=True,
        timeout=120,
    )
    payload = typing.cast(RGaussianFreeSpPayload, json.loads(out.read_text()))

    result = compare_gaussian_free_sp_case(fit_gaussian_free_sp_case(payload), payload)
    assert result["agrees"], result
    # The offset tripwire: this recipe carries no offset. Unlike the fixed-sp
    # probe's exact 0.0 (a single linear solve), mgcv's free-sp REML fit goes
    # through its own internal outer-iteration code path before
    # m$linear.predictors/predict() are compared, so this is float round-trip
    # noise rather than an exact bit match — still ~1e12x smaller than
    # ADR-221's eta tolerance, and nowhere near the ~2 the epic's own false
    # 1.9751-against-2e-2 reading (the trap this tripwire exists to catch).
    assert result["offset_gap"] < 1e-9
