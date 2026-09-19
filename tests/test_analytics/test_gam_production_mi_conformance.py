"""PLAN slice 1 of ``docs/PLAN_gam_production_wiring.md``: the SHIPPED
dashboard's MI model form, expressed as a ``ModelSpec`` and measured against
``mgcv``.

The provenance gate (ADR-193): every quantity
:data:`PRODUCTION_MI_MODEL_CLAIM` declares is INDEPENDENT, and
:func:`fit_production_mi_case`'s signature structurally cannot see either of
``mgcv``'s fits (:class:`RProductionMIRecipe` has no ``te``/``anova`` key).
Gated on R being present for the end-to-end round trip, same discipline as
``test_gam_select_free_sp_conformance.py``.

**What this file is really pinning.** Slice 1's finding is that
``te(x, z) == s(x) + s(z) + ti(x, z)`` is NOT an identity, so the tests here
pin the *structure* that makes the finding legible — the block counts, the
span equivalence, the localiser's own arithmetic — rather than pinning a
particular disagreement magnitude, which is a property of the recipe and the
oracle version, not of this code.
"""

import inspect
import json
import subprocess
import typing
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.experience_mgcv_conformance import rscript_mgcv_available
from polaris_re.analytics.gam_production_mi_conformance import (
    PRODUCTION_MI_MODEL_CLAIM,
    ProductionMICaseComparison,
    RProductionMIPayload,
    RProductionMIRecipe,
    compare_production_mi_case,
    compare_r_internal_forms,
    fit_production_mi_case,
    production_mi_model_spec,
)
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import require_parity_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]

_AGE_KNOTS = [45.0, 50.0, 57.0, 65.0, 72.0, 79.0, 85.0]
_YEAR_KNOTS = [2010.0, 2013.0, 2016.0, 2019.0, 2021.0]
_DURATION_KNOTS = [2.0, 6.0, 11.0, 16.0, 22.0]


def _small_recipe() -> RProductionMIRecipe:
    """A grouped-cell recipe of the shape the dashboard is handed, small
    enough for an R-free unit test.

    Deliberately a full (age x calendar-year x duration) GRID rather than a
    scatter — that is what ``attach_base_rate`` plus a ``group_by`` produce
    upstream of ``TensorMIModel``, and ``te`` versus its ANOVA decomposition
    differ in PENALTY, whose expression depends on the design it is applied
    to. Coarser than ``scripts/gam_production_mi_probe.R``'s own grid (which
    steps age by 2 for a production-grain age margin); this one only has to
    exercise assembly and the guards.
    """
    ages = np.arange(45.0, 86.0, 5.0)
    years = np.arange(2010.0, 2022.0)
    durations = np.array([2.0, 7.0, 12.0, 17.0, 22.0])
    age, year, dur = (g.ravel() for g in np.meshgrid(ages, years, durations, indexing="ij"))
    n = age.size
    q_base = 0.0004 + 0.00003 * np.exp(0.085 * (age - 45.0))
    exposure = np.round(
        9000.0
        * np.exp(-(((age - 62.0) / 26.0) ** 2))
        * np.exp(-(((dur - 10.0) / 16.0) ** 2))
        * (1.0 + 0.03 * (year - 2010.0))
    )
    log_rr = (
        -0.014 * (year - 2015.0) * (1.0 + 0.012 * (age - 65.0))
        + 0.05 * np.sin(age / 11.0)
        - 0.18 * np.exp(-dur / 9.0)
    )
    deaths = np.random.default_rng(20260915).poisson(exposure * q_base * np.exp(log_rr))
    return RProductionMIRecipe(
        n=int(n),
        attained_age=age.tolist(),
        calendar_year=year.tolist(),
        duration_years=dur.tolist(),
        exposure=exposure.tolist(),
        q_base=q_base.tolist(),
        deaths=deaths.astype(float).tolist(),
        log_offset=np.log(exposure * q_base).tolist(),
        age_knots=list(_AGE_KNOTS),
        year_knots=list(_YEAR_KNOTS),
        duration_knots=list(_DURATION_KNOTS),
        age_k=len(_AGE_KNOTS),
        year_k=len(_YEAR_KNOTS),
        duration_k=len(_DURATION_KNOTS),
    )


def _payload_from(
    recipe: RProductionMIRecipe, *, span_residual: float = 3.0e-13, **fits: object
) -> RProductionMIPayload:
    """Build a full payload from a recipe plus hand-supplied ``mgcv``-shaped
    fits, so the comparator's arithmetic can be exercised without R.

    ``span_residual`` defaults to the magnitude a genuine two-way projection
    residual lands at on this design (~3e-13), so the default payload describes
    two forms that DO span the same space — which is the case the finding rests
    on. Pass a larger value to exercise the opposite."""
    span = {
        "span_residual_anova_in_te": span_residual,
        "span_residual_te_in_anova": span_residual,
        "rank_te": 39,
        "rank_anova": 39,
        "rank_combined": 39,
    }
    return typing.cast(RProductionMIPayload, {**recipe, **span, **fits})


def _synthetic_fit(
    eta: list[float], *, edf_total: float, n_sp: int, n_coef: int
) -> dict[str, object]:
    return {
        "eta": eta,
        "coef": [0.0] * n_coef,
        "sp": [1.0] * n_sp,
        "edf_total": edf_total,
        "term_edf": [1.0] * n_sp,
        "n_coef": n_coef,
        "converged": True,
        "reml": 0.0,
    }


# --------------------------------------------------------------------------
# Provenance (ADR-193) — this slice IS a two-producer comparison, unlike the
# several before it, so the claim must survive `require_parity_evidence`.
# --------------------------------------------------------------------------


def test_production_mi_claim_is_independent_on_every_declared_quantity() -> None:
    """ADR-193's gate: a harness result must not be able to satisfy this."""
    require_parity_evidence(
        PRODUCTION_MI_MODEL_CLAIM.quantities, claim=PRODUCTION_MI_MODEL_CLAIM.claim
    )
    assert PRODUCTION_MI_MODEL_CLAIM.is_parity_claim


def test_fit_production_mi_case_signature_takes_no_r_fit_output() -> None:
    """ADR-193's mechanical test, applied structurally at the type:
    :class:`RProductionMIRecipe` has no ``te`` or ``anova`` key at all, so the
    producing function cannot read either of ``mgcv``'s fits even if a caller
    hands it the wider payload."""
    params = set(inspect.signature(fit_production_mi_case).parameters)
    assert params == {"r_case", "multistart", "n_starts", "analytic_gradient"}

    hints = typing.get_type_hints(fit_production_mi_case)
    assert hints["r_case"] is RProductionMIRecipe

    recipe_keys = set(RProductionMIRecipe.__annotations__)
    payload_keys = set(RProductionMIPayload.__annotations__)
    fit_only_keys = {"te", "anova"}
    assert recipe_keys.isdisjoint(fit_only_keys)
    assert fit_only_keys <= payload_keys


def test_claim_sentence_names_the_tolerances_and_makes_no_bare_parity_claim() -> None:
    """ADR-219 amendment 1's marketing constraint: the claim names its
    quantity, its tolerance and its structure, and never says bare "parity"."""
    claim = PRODUCTION_MI_MODEL_CLAIM.claim
    assert "2e-2" in claim
    assert "1.0" in claim
    assert "multistart=True" in claim
    assert "mgcv parity" not in claim.lower()


# --------------------------------------------------------------------------
# Assembly — the ModelSpec, and the block count that makes blocker A countable
# --------------------------------------------------------------------------


def test_production_mi_model_spec_is_the_dashboard_form_re_expressed() -> None:
    """The four terms, the Poisson-log family, and the OFFSET idiom (no
    weights) ``TensorMIModel`` uses on the count basis — PLAN Anchor 5."""
    model = production_mi_model_spec(tuple(_AGE_KNOTS), tuple(_YEAR_KNOTS), tuple(_DURATION_KNOTS))
    assert model.family == "poisson"
    assert model.link == "log"
    assert model.offset_column == "log_offset"
    assert model.weights_column is None
    # `select` stays off: the shipped form has no `select = TRUE`, and adding
    # one would measure a different model.
    assert model.select is False
    assert [t.label for t in model.terms] == [
        "s(attained_age)",
        "s(calendar_year)",
        "ti(attained_age,calendar_year)",
        "s(duration_years)",
    ]
    # k is DERIVED from the page's widget defaults, not chosen: K = D + 1
    # reproduces the shipped margin width after the sum-to-zero constraint.
    assert [t.k for t in model.terms] == [(7,), (5,), (7, 5), (5,)]


def test_assembled_design_has_five_penalty_blocks_where_te_would_have_three() -> None:
    """R-free, and this is blocker A made countable: the re-expression carries
    1 + 1 + 2 + 1 = 5 independently-scaled penalties (ADR-205 decision 2 gives
    ``ti`` two), where ``mgcv``'s own ``te()`` fit of the SAME span carries 3.
    Same span, different penalty — which is exactly why the equivalence is a
    hypothesis rather than an identity."""
    fit = fit_production_mi_case(_small_recipe(), multistart=False)
    assert fit.log_lambda.shape == (5,)
    assert set(fit.edf_per_term) == {
        "s(attained_age)",
        "s(calendar_year)",
        "ti(attained_age,calendar_year)",
        "s(duration_years)",
    }
    # 1 intercept + 6 age + 4 year + 24 interaction + 4 duration = 39 columns,
    # which is also `te(k=c(7,5))`'s own 7*5 - 1. The SPAN matches; the
    # penalty does not.
    assert fit.design["x"].shape == (_small_recipe()["n"], 39)


def test_fit_production_mi_case_pins_multistart_on_by_default() -> None:
    """Blocker D: a plain single-start call is the configuration that fails
    ADR-221's gate elsewhere in this epic, and ADR-226 measured
    ``multistart(9)`` as the only configuration passing both reproducibility
    axes. Any wiring must pin it explicitly, so this module's own default
    differs from :func:`fit_polaris_gam`'s."""
    assert inspect.signature(fit_production_mi_case).parameters["multistart"].default is True
    assert inspect.signature(fit_production_mi_case).parameters["n_starts"].default == 9


# --------------------------------------------------------------------------
# The comparator's arithmetic, and its guards
# --------------------------------------------------------------------------


def test_compare_production_mi_case_rejects_an_unknown_target() -> None:
    recipe = _small_recipe()
    fit = fit_production_mi_case(recipe, multistart=False)
    payload = _payload_from(
        recipe,
        te=_synthetic_fit(fit.eta.tolist(), edf_total=1.0, n_sp=3, n_coef=39),
        anova=_synthetic_fit(fit.eta.tolist(), edf_total=1.0, n_sp=5, n_coef=39),
    )
    with pytest.raises(PolarisValidationError, match="target"):
        compare_production_mi_case(fit, payload, target="tensor")


def test_compare_production_mi_case_rejects_eta_shape_mismatch() -> None:
    """A payload whose ``eta`` does not match the Python fit's row count was
    not posed on the same recipe."""
    recipe = _small_recipe()
    fit = fit_production_mi_case(recipe, multistart=False)
    payload = _payload_from(
        recipe,
        te=_synthetic_fit([0.0] * (recipe["n"] - 1), edf_total=1.0, n_sp=3, n_coef=39),
        anova=_synthetic_fit(fit.eta.tolist(), edf_total=1.0, n_sp=5, n_coef=39),
    )
    with pytest.raises(PolarisValidationError, match="same recipe"):
        compare_production_mi_case(fit, payload, target="te")


def test_agrees_is_adr221s_committed_gate_and_is_never_widened_here() -> None:
    """Anchor W5: this epic may not widen a tolerance or re-gate anything.
    The bounds are ADR-221's, imported rather than redeclared, and ``agrees``
    is ``eta`` AND ``edf`` AND ``converged`` — never ``log10(sp)``."""
    recipe = _small_recipe()
    fit = fit_production_mi_case(recipe, multistart=False)
    exact = _payload_from(
        recipe,
        te=_synthetic_fit(fit.eta.tolist(), edf_total=fit.edf_total, n_sp=3, n_coef=39),
        anova=_synthetic_fit(fit.eta.tolist(), edf_total=fit.edf_total, n_sp=5, n_coef=39),
    )
    good = compare_production_mi_case(fit, exact, target="te")
    assert good.eta_tolerance == pytest.approx(2.0e-2)
    assert good.edf_tolerance == pytest.approx(1.0)
    assert good.agrees
    # `log10(sp)` plays no part: the two forms do not even carry the same
    # number of smoothing parameters, so the comparison is undefined.
    assert good.n_sp_mgcv == 3
    assert good.n_sp_python == 5
    assert not hasattr(good, "agrees_log10_sp")

    # eta just outside the bound fails, edf held exact.
    shifted = np.asarray(fit.eta) + 2.1e-2
    bad_eta = _payload_from(
        recipe,
        te=_synthetic_fit(shifted.tolist(), edf_total=fit.edf_total, n_sp=3, n_coef=39),
        anova=_synthetic_fit(fit.eta.tolist(), edf_total=fit.edf_total, n_sp=5, n_coef=39),
    )
    assert not compare_production_mi_case(fit, bad_eta, target="te").agrees

    # edf just outside the bound fails, eta held exact.
    bad_edf = _payload_from(
        recipe,
        te=_synthetic_fit(fit.eta.tolist(), edf_total=fit.edf_total + 1.1, n_sp=3, n_coef=39),
        anova=_synthetic_fit(fit.eta.tolist(), edf_total=fit.edf_total, n_sp=5, n_coef=39),
    )
    assert not compare_production_mi_case(fit, bad_edf, target="te").agrees


# --------------------------------------------------------------------------
# The blocker-A localiser: mgcv against itself
# --------------------------------------------------------------------------


def test_r_internal_localiser_reads_mgcv_against_mgcv_only() -> None:
    """The (3) axis: both producers are ``mgcv``, Polaris appears nowhere. It
    is what separates "our engine is wrong" from "the re-expression is not the
    target form"."""
    recipe = _small_recipe()
    eta = np.linspace(-3.0, 1.0, recipe["n"])
    payload = _payload_from(
        recipe,
        te=_synthetic_fit(eta.tolist(), edf_total=7.3, n_sp=3, n_coef=39),
        anova=_synthetic_fit((eta + 4.0e-2).tolist(), edf_total=7.05, n_sp=5, n_coef=39),
    )
    localiser = compare_r_internal_forms(payload)
    assert localiser.max_abs_eta_diff == pytest.approx(4.0e-2)
    assert localiser.edf_total_diff == pytest.approx(-0.25)
    assert localiser.n_sp_te == 3
    assert localiser.n_sp_anova == 5
    # Span equivalence is MEASURED (two-way projection residual + agreeing
    # ranks), not inferred from equal column counts — so an eta difference
    # beside it is attributable to the PENALTY, not the basis.
    assert localiser.spans_match
    assert localiser.max_span_residual == pytest.approx(3.0e-13)
    # 4e-2 is outside ADR-221's 2e-2, so the equivalence is refuted here.
    assert not localiser.equivalent_within_adr221


def test_spans_match_is_measured_not_inferred_from_column_counts() -> None:
    """Equal column counts do NOT establish equal span — two 39-column bases
    can span different 39-dimensional subspaces. ``spans_match`` must read
    False on a payload whose counts agree but whose projection residual says
    the column spaces differ."""
    recipe = _small_recipe()
    eta = np.linspace(-3.0, 1.0, recipe["n"])
    payload = _payload_from(
        recipe,
        span_residual=1.0e-3,  # counts still agree; the SPACES do not
        te=_synthetic_fit(eta.tolist(), edf_total=7.3, n_sp=3, n_coef=39),
        anova=_synthetic_fit(eta.tolist(), edf_total=7.3, n_sp=5, n_coef=39),
    )
    localiser = compare_r_internal_forms(payload)
    assert localiser.n_coef_te == localiser.n_coef_anova == 39
    assert not localiser.spans_match


def test_spans_match_is_false_when_the_ranks_disagree() -> None:
    """The second, independent route to the same structural fact:
    ``rank([X_te X_anova])`` exceeding either individual rank means one design
    carries a direction the other lacks."""
    recipe = _small_recipe()
    eta = np.linspace(-3.0, 1.0, recipe["n"])
    payload = _payload_from(
        recipe,
        te=_synthetic_fit(eta.tolist(), edf_total=7.3, n_sp=3, n_coef=39),
        anova=_synthetic_fit(eta.tolist(), edf_total=7.3, n_sp=5, n_coef=39),
    )
    payload["rank_combined"] = 40
    assert not compare_r_internal_forms(payload).spans_match


def test_r_internal_localiser_reports_equivalence_when_the_two_forms_coincide() -> None:
    """The same localiser must be able to report agreement — it is a
    measurement, not an assertion that the forms differ. (On the committed
    recipe they do differ; on 2 of 8 draws measured they did not.)"""
    recipe = _small_recipe()
    eta = np.linspace(-3.0, 1.0, recipe["n"])
    payload = _payload_from(
        recipe,
        te=_synthetic_fit(eta.tolist(), edf_total=7.30, n_sp=3, n_coef=39),
        anova=_synthetic_fit((eta + 1.0e-5).tolist(), edf_total=7.31, n_sp=5, n_coef=39),
    )
    assert compare_r_internal_forms(payload).equivalent_within_adr221


def test_r_internal_localiser_rejects_mismatched_shapes() -> None:
    recipe = _small_recipe()
    payload = _payload_from(
        recipe,
        te=_synthetic_fit([0.0] * recipe["n"], edf_total=1.0, n_sp=3, n_coef=39),
        anova=_synthetic_fit([0.0] * (recipe["n"] - 1), edf_total=1.0, n_sp=5, n_coef=39),
    )
    with pytest.raises(PolarisValidationError, match="same recipe"):
        compare_r_internal_forms(payload)


# --------------------------------------------------------------------------
# End to end, gated on R (ADR-151 / Anchor 5: never in ordinary CI)
# --------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.skipif(not rscript_mgcv_available(), reason="Rscript with mgcv not available")
def test_the_production_mi_probe_runs_end_to_end(tmp_path: Path) -> None:
    """The R probe produces a payload this module can read, the offset
    tripwire holds, and the three comparison axes all compute.

    Asserts the STRUCTURE, not the magnitudes: the disagreement size is a
    property of the recipe and the oracle version (tier 1 here, R 4.3.3 /
    mgcv 1.9.1 from apt), and this epic's own routine forbids treating a
    tier-1 number as established.
    """
    out = tmp_path / "gam_production_mi_probe.json"
    subprocess.run(
        ["Rscript", str(REPO_ROOT / "scripts" / "gam_production_mi_probe.R"), str(out)],
        check=True,
        capture_output=True,
    )
    payload: RProductionMIPayload = json.loads(out.read_text())

    # The offset tripwire: `m$linear.predictors` is the like-for-like eta,
    # and `predict(type="link")` excludes an argument-supplied offset.
    assert abs(payload["offset_gap_te"]) < 1e-12
    assert abs(payload["offset_gap_anova"]) < 1e-12

    # Span equivalence is the structural precondition for the whole question,
    # and it is MEASURED here rather than assumed: mutual containment of the
    # two column spaces to machine precision, plus agreeing ranks.
    localiser = compare_r_internal_forms(payload)
    assert localiser.spans_match
    assert localiser.max_span_residual < 1e-9
    assert localiser.rank_te == localiser.rank_anova == localiser.rank_combined
    assert (localiser.n_sp_te, localiser.n_sp_anova) == (3, 5)

    fit = fit_production_mi_case(payload, multistart=True, n_starts=9)
    for target in ("anova", "te"):
        comparison = compare_production_mi_case(fit, payload, target=target)
        assert isinstance(comparison, ProductionMICaseComparison)
        assert comparison.evidence is PRODUCTION_MI_MODEL_CLAIM
        assert np.isfinite(comparison.max_abs_eta_diff)
