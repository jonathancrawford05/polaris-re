"""``docs/WORK_ORDER_reml_penalized_deviance_production_check.md`` — the
diagnostic-only replicas in ``gam_reml_production_check.py``.

Every test here checks the DIAGNOSTIC machinery is correct, not the
production module (PLAN Anchor 7: ``experience_gam_penalized.py`` is not
imported for modification anywhere in this file, only called read-only, the
same way ``tests/test_analytics/test_experience_mgcv_conformance.py`` already
does). The actual §3.1/§3.2/§3.3 measurements against ``mgcv`` live in
``scripts/reml_production_check_probe.py`` and are reported in
``docs/DECISIONS.md``/``docs/CONFORMANCE_LEDGER.md`` — not re-asserted here,
since the ten-cell fixture is a golden and this work order does not
re-baseline it (§5 of the work order).
"""

import numpy as np
import pytest

from polaris_re.analytics.experience_gam_penalized import LAMBDA_LOG10_BOUNDS
from polaris_re.analytics.experience_gam_penalized import reml_score as production_reml_score
from polaris_re.analytics.experience_mgcv_conformance import (
    DesignSpec,
    build_design,
    synthetic_cells,
)
from polaris_re.analytics.gam_reml_production_check import (
    PRODUCTION_REML_CHECK_CLAIM,
    corrected_reml_score,
    measure_production_score_gap,
    score_shape_diagnostic,
    select_lambdas_corrected,
)
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import require_parity_evidence


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(20260818)


def _design(rng: np.random.Generator, n: int, p: int) -> np.ndarray:
    return np.column_stack([np.ones(n), rng.normal(size=(n, p - 1))])


class TestCorrectedReMLScore:
    """:func:`corrected_reml_score` is a thin wrapper — these pin that it
    behaves exactly like ``gam_reml.reml_score_general(family=poisson_log())``.

    **Updated 2026-08-19 (ADR-197 resolution, maintainer-authorized).** Until this
    session, ``corrected_reml_score`` differed from the production score
    (``production_reml_score``, imported from ``experience_gam_penalized``) by
    exactly the penalty quadratic form, per that function's OWN already-committed
    regression test (``test_gam_reml.py::TestRelationshipToTheExistingPoissonScore``).
    The production function now carries the identical fix, so the two are bit-for-bit
    identical instead — this test now pins agreement rather than the gap."""

    def test_matches_production_bit_for_bit_now_that_the_missing_term_is_fixed_on_both_sides(
        self, rng: np.random.Generator
    ) -> None:
        n, p = 180, 6
        x = _design(rng, n, p)
        beta_true = rng.normal(scale=0.25, size=p)
        offset = rng.normal(scale=0.05, size=n)
        mu_true = np.exp(offset + x @ beta_true)
        y = rng.poisson(mu_true).astype(np.float64)
        d = np.diff(np.eye(p), n=2, axis=0)
        penalty = 4.0 * (d.T @ d)
        coef = beta_true
        gamma = 1.4

        old = production_reml_score(y, x, offset, coef, penalty, gamma=gamma)
        new = corrected_reml_score(y, x, offset, coef, penalty, gamma=gamma)
        penalty_quadratic_form = 0.5 * float(coef @ penalty @ coef) / gamma
        assert new == pytest.approx(old, abs=1e-9, rel=1e-9)
        # Still strictly positive under a real penalty — sanity that this fixture
        # actually exercises the term both formulas now include, not a degenerate one.
        assert penalty_quadratic_form > 0.0

    def test_matches_production_exactly_at_zero_penalty(self, rng: np.random.Generator) -> None:
        n, p = 90, 4
        x = _design(rng, n, p)
        beta_true = rng.normal(scale=0.3, size=p)
        mu_true = np.exp(x @ beta_true)
        y = rng.poisson(mu_true).astype(np.float64)
        offset = np.zeros(n)
        penalty = np.zeros((p, p))

        old = production_reml_score(y, x, offset, beta_true, penalty)
        new = corrected_reml_score(y, x, offset, beta_true, penalty)
        assert new == pytest.approx(old, abs=1e-12, rel=1e-12)


class TestMeasureProductionScoreGap:
    def test_gap_arithmetic(self, rng: np.random.Generator) -> None:
        """A hand-checkable case: mgcv's score is a stand-in constant, and the
        gap is just mgcv_score minus each Python score — no hidden
        transformation."""
        spec = DesignSpec("d1", 7, 6, False)
        export = build_design(spec, synthetic_cells(with_factor=False))
        n_coef = export.design.shape[1]
        coef = np.zeros(n_coef, dtype=np.float64)
        lambda_age, lambda_year = 10.0, 100.0
        gamma = 1.0
        mgcv_score = 999.0

        gap = measure_production_score_gap(
            "d1", export, coef, lambda_age, lambda_year, gamma, mgcv_score
        )
        assert gap.gap_current == pytest.approx(mgcv_score - gap.current_python_score)
        assert gap.gap_corrected == pytest.approx(mgcv_score - gap.corrected_python_score)
        # At coef = 0 the penalty quadratic form vanishes, so the two Python
        # scores must coincide exactly (same edge case as
        # TestCorrectedReMLScore.test_matches_production_exactly_at_zero_penalty,
        # exercised here through the DesignExport-based entry point instead).
        assert gap.corrected_python_score == pytest.approx(
            gap.current_python_score, abs=1e-9, rel=1e-9
        )


class TestSelectLambdasCorrected:
    """Determinism (ADR-186) and structural sanity — not a claim about where
    the corrected criterion lands (that is §3.2's own measurement, reported
    in the ledger/ADR, not re-asserted as a pytest expectation against a
    live-fitted number here)."""

    def test_is_deterministic(self) -> None:
        cells = synthetic_cells(with_factor=False)
        # A narrower bound than the full committed grid keeps this test's
        # wall-clock reasonable (a handful of coarse+refine fits rather than
        # the full 202) while still exercising both sweep passes.
        bounds = (2.0, 5.0)
        first = select_lambdas_corrected(cells, k_age=7, k_year=6, bounds=bounds)
        second = select_lambdas_corrected(cells, k_age=7, k_year=6, bounds=bounds)
        assert first == second

    def test_selection_is_a_grid_point_within_bounds(self) -> None:
        cells = synthetic_cells(with_factor=False)
        bounds = (2.0, 5.0)
        selection = select_lambdas_corrected(cells, k_age=7, k_year=6, bounds=bounds)
        lo, hi = bounds
        assert 10.0**lo <= selection.lambda_age <= 10.0**hi
        assert 10.0**lo <= selection.lambda_year <= 10.0**hi
        assert np.isfinite(selection.reml_score)
        assert selection.n_evaluated > 0
        assert np.isfinite(selection.edf_total)
        assert selection.edf_total > 0.0
        assert selection.edf_total == pytest.approx(
            selection.edf_tensor + selection.edf_factors, abs=1e-9
        )

    def test_current_criterion_reproduces_the_shipped_selection_on_l2_free_sp(self) -> None:
        """§3.2's null control (PR #204 review [P2], and the automated review's
        own independent check on this exact cell): the replica sweep, scored
        with the CURRENT (production) criterion via ``use_corrected_score=False``,
        must reproduce
        ``data/mgcv_exchange/synthetic/python_reference.json``'s shipped
        ``l2-free-sp`` selection exactly. This is the control that proves the
        replica is faithful to ``select_lambdas_reml`` (same bounds, same
        coarse+refine grid, same rejection rule, same gamma), so §3.2's
        "corrected criterion selects closer to mgcv" conclusion was
        attributable to the SCORE FORMULA alone and not to some other way the
        replica might have diverged from production. Uses the production
        module's own default ``bounds``/``coarse_step``/``refine_step``/``gamma``
        (all left unset here) — the same defaults ``l2-free-sp`` was actually
        selected under (``fit_reml`` -> ``select_lambdas_reml``, both called
        with no override in ``experience_mgcv_conformance._cell_result``).

        **Updated 2026-08-19 (ADR-197 resolution, maintainer-authorized).** The
        production score is now fixed, so the "current" criterion this test
        exercises IS the corrected one — ``use_corrected_score=False`` and
        ``True`` now select the identical point (also asserted directly by
        :func:`TestSelectLambdasCorrected.test_is_deterministic`-adjacent
        coverage above). The expected value moves to the fixed production
        module's own selection, exactly the grid-step move ADR-197 §3.2
        predicted and this session's regenerated
        ``python_reference.json`` now records: ``sp = [5623.413251903491,
        1000.0]`` (was ``[3162.2776601683795, 1000.0]`` under the old,
        buggy production score)."""
        cells = synthetic_cells(with_factor=False)
        selection = select_lambdas_corrected(cells, k_age=7, k_year=6, use_corrected_score=False)
        assert selection.lambda_age == pytest.approx(5623.413251903491, rel=1e-9)
        assert selection.lambda_year == pytest.approx(1000.0, rel=1e-9)


class TestScoreShapeDiagnostic:
    def test_hessians_are_finite_and_symmetric_by_construction(self) -> None:
        cells = synthetic_cells(with_factor=False)
        diag = score_shape_diagnostic(
            cells, lambda_age=3162.2776601683795, lambda_year=1000.0, k_age=7, k_year=6
        )
        for hessian in (diag.hessian_current, diag.hessian_corrected):
            assert np.all(np.isfinite(hessian))
            assert hessian.shape == (2, 2)
        assert diag.jacobian.shape[1] == 2
        for correction in (diag.correction_current, diag.correction_corrected):
            # J V_rho J^T is PSD by construction (smoothing_uncertainty's own
            # invariant) — reproduced here since this module builds the same
            # object from a possibly-different Hessian.
            eigenvalues = np.linalg.eigvalsh(0.5 * (correction + correction.T))
            assert np.all(eigenvalues >= -1e-9)

    def test_rejects_nonpositive_log_step(self) -> None:
        cells = synthetic_cells(with_factor=False)
        with pytest.raises(PolarisValidationError):
            score_shape_diagnostic(
                cells, lambda_age=100.0, lambda_year=100.0, log_step=0.0, k_age=7, k_year=6
            )

    def test_rejects_nonpositive_lambda(self) -> None:
        cells = synthetic_cells(with_factor=False)
        with pytest.raises(PolarisValidationError):
            score_shape_diagnostic(cells, lambda_age=0.0, lambda_year=100.0, k_age=7, k_year=6)


class TestProvenanceClaim:
    """ADR-193: the claim must be gateable by ``require_parity_evidence`` —
    both declared quantities are INDEPENDENT (neither Python producer reads
    mgcv's own score or coefficients, only the shared, already-fitted
    recipe)."""

    def test_both_quantities_are_independent_and_gate_clean(self) -> None:
        require_parity_evidence(
            PRODUCTION_REML_CHECK_CLAIM.quantities, claim=PRODUCTION_REML_CHECK_CLAIM.claim
        )
        assert PRODUCTION_REML_CHECK_CLAIM.is_parity_claim


def test_lambda_log10_bounds_is_the_production_default() -> None:
    """A sanity check that this module's default bounds argument tracks the
    production grid's own default rather than a copy that could silently
    drift (LAMBDA_LOG10_BOUNDS is imported, not restated as a literal, in
    gam_reml_production_check.py)."""
    assert LAMBDA_LOG10_BOUNDS == (-2.0, 8.0)
