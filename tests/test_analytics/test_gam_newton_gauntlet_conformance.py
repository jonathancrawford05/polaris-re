"""Outer-solver slice 4 (ADR-245): the gauntlet's plumbing — ``outer`` reaches
every fit helper, one Newton start per scale (no seeded second start), failures
are reported rather than dropped, and the parity gate refuses a harness claim."""

import inspect

import pytest

from polaris_re.analytics import gam_quasipoisson_fixed_scale_conformance as fixed_scale
from polaris_re.analytics.gam_by_factor_conformance import fit_by_factor_free_sp_case
from polaris_re.analytics.gam_cr_re_ti_conformance import fit_cr_re_ti_free_sp_case
from polaris_re.analytics.gam_gaussian_conformance import fit_gaussian_free_sp_case
from polaris_re.analytics.gam_newton_gauntlet_conformance import (
    REQUIRED_CASE_PREFIXES,
    GauntletReading,
    gate_failures,
    gauntlet_claims,
    require_gauntlet_parity_evidence,
    run_gauntlet,
)
from polaris_re.analytics.gam_parametric_conformance import fit_parametric_free_sp_case
from polaris_re.analytics.gam_production_mi_conformance import (
    PRODUCTION_MI_NEWTON_CLAIM,
    fit_production_mi_case,
)
from polaris_re.analytics.gam_quasipoisson_conformance import fit_quasipoisson_free_sp_case
from polaris_re.analytics.gam_select_free_sp_conformance import fit_select_free_sp_case
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)


@pytest.mark.parametrize(
    "fit",
    [
        fit_gaussian_free_sp_case,
        fit_by_factor_free_sp_case,
        fit_parametric_free_sp_case,
        fit_cr_re_ti_free_sp_case,
        fit_quasipoisson_free_sp_case,
        fixed_scale.fit_quasipoisson_fixed_scale_case,
        fit_select_free_sp_case,
    ],
)
def test_every_gauntlet_fit_helper_accepts_outer_and_defaults_to_lbfgsb(fit: object) -> None:
    param = inspect.signature(fit).parameters["outer"]  # type: ignore[arg-type]
    assert param.default == "lbfgsb"


def test_fixed_scale_newton_is_one_start_per_scale(monkeypatch: pytest.MonkeyPatch) -> None:
    """The gauntlet's rule is ONE start: no gamma=1 seed, no best-of-two."""
    calls: list[dict[str, object]] = []

    def spy(*args: object, **kwargs: object) -> str:
        calls.append(dict(kwargs))
        return "fit"

    monkeypatch.setattr(fixed_scale, "_model_and_data", lambda r: ("m", {}, None))
    monkeypatch.setattr(fixed_scale, "fit_polaris_gam", spy)
    out = fixed_scale.fit_quasipoisson_fixed_scale_case(
        {"scales": [2.0, 6.0]},  # type: ignore[typeddict-item]
        outer="newton",
    )
    assert out == ["fit", "fit"]
    assert [c["gamma"] for c in calls] == [2.0, 6.0]
    assert all(c["outer"] == "newton" and "x0" not in c and "multistart" not in c for c in calls)


def test_a_case_that_raises_is_reported_not_dropped() -> None:
    readings = run_gauntlet({})  # every payload lookup fails
    assert len(readings) == 9  # six free-scale cells + fixed scale + select + HGAM
    assert all(r.error is not None and not r.agrees for r in readings)


def _claim(provenance: ComparisonProvenance) -> VerificationClaim:
    return VerificationClaim(
        claim="x",
        quantities=(
            ComparedQuantity(
                quantity="eta",
                left_producer="polaris",
                right_producer="mgcv"
                if provenance is ComparisonProvenance.INDEPENDENT
                else "polaris",
                provenance=provenance,
            ),
        ),
    )


def _reading(claim: VerificationClaim) -> GauntletReading:
    return GauntletReading("c", 0.0, 0.0, 1, False, True, True, claim)


def test_gate_passes_on_independent_and_refuses_a_harness_claim() -> None:
    require_gauntlet_parity_evidence([_reading(_claim(ComparisonProvenance.INDEPENDENT))])
    with pytest.raises(PolarisValidationError):
        require_gauntlet_parity_evidence([_reading(_claim(ComparisonProvenance.TRANSPORT))])


def test_claims_are_deduplicated_by_text() -> None:
    c = _claim(ComparisonProvenance.INDEPENDENT)
    assert len(gauntlet_claims([_reading(c), _reading(c)])) == 1


def _row(case: str, *, agrees: bool = True, converged: bool = True) -> GauntletReading:
    return GauntletReading(
        case=case,
        max_abs_eta_diff=0.0,
        edf_total_diff=0.0,
        n_function_evals=1,
        at_bound=False,
        converged=converged,
        agrees=agrees,
        evidence=None,
    )


def test_gate_passes_only_on_both_fixed_scale_rows_agreeing() -> None:
    ok = [_row("quasipoisson fixed scale=2"), _row("quasipoisson fixed scale=6"), _row("other")]
    assert gate_failures(ok) == []


@pytest.mark.parametrize(
    "rows",
    [
        [_row("quasipoisson fixed scale=2")],  # a dropped scale never passes by omission
        [],
        [_row("quasipoisson fixed scale=2"), _row("quasipoisson fixed scale=6", agrees=False)],
        [_row("quasipoisson fixed scale=2"), _row("quasipoisson fixed scale=6", converged=False)],
    ],
)
def test_gate_fails_on_missing_disagreeing_or_unconverged_rows(rows: list[GauntletReading]) -> None:
    assert gate_failures(rows)


def test_gate_surfaces_an_error_row_as_a_failure() -> None:
    errored = run_gauntlet({})
    assert any("error=" in f for f in gate_failures(errored))


def test_gate_does_not_block_on_other_cases() -> None:
    rows = [
        _row("quasipoisson fixed scale=2"),
        _row("quasipoisson fixed scale=6"),
        _row("select=TRUE N=7", agrees=False),
    ]
    assert gate_failures(rows) == []
    assert REQUIRED_CASE_PREFIXES == ("quasipoisson fixed scale",)


def test_hgam_producer_signature_takes_the_recipe_only_and_defaults_to_lbfgsb() -> None:
    params = inspect.signature(fit_production_mi_case).parameters
    assert params["outer"].default == "lbfgsb"
    assert not {"eta", "coef", "sp", "edf", "r_fit", "anova", "te"} & set(params)


def test_hgam_newton_claim_declares_only_the_two_columns_it_compares() -> None:
    assert [q.quantity.split(" ")[0] for q in PRODUCTION_MI_NEWTON_CLAIM.quantities] == [
        "eta",
        "edf_total",
    ]
    assert all(
        q.provenance is ComparisonProvenance.INDEPENDENT
        for q in PRODUCTION_MI_NEWTON_CLAIM.quantities
    )
    assert "multistart=True" not in PRODUCTION_MI_NEWTON_CLAIM.claim
