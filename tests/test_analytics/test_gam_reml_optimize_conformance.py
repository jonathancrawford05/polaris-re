"""``gam_reml_optimize_conformance.compare_fixed_sp_multiterm_case`` — PR #215
review [P1-1]'s fix: the fixed-`sp` REML score/deviance comparison PLAN
slice 5c measures needed its own declared ``VerificationClaim``, distinct
from ``REML_SCORE_CLAIM`` (a different fixture/producer). R-free: builds a
synthetic two-block Poisson design and a hand-computed "mgcv" comparand
directly, rather than depending on the R probe payload's schema.
"""

import numpy as np
import pytest

from polaris_re.analytics.gam_family import poisson_log
from polaris_re.analytics.gam_fit import penalized_irls_general
from polaris_re.analytics.gam_reml import reml_score_general
from polaris_re.analytics.gam_reml_optimize_conformance import (
    FIXED_SP_MULTITERM_REML_CLAIM,
    compare_fixed_sp_multiterm_case,
)
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import require_parity_evidence


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(20260829)


def _design(rng: np.random.Generator, n: int, p: int) -> np.ndarray:
    return np.column_stack([np.ones(n), rng.normal(size=(n, p - 1))])


class TestComparesFixedSpMultitermCase:
    def test_matches_a_direct_call_when_the_comparand_is_ours(
        self, rng: np.random.Generator
    ) -> None:
        """The comparison must reproduce ZERO diff when the "mgcv" side is
        literally our own score/deviance at the same point — the simplest
        possible correctness check, independent of any R payload."""
        n, p1, p2 = 150, 3, 4
        p = p1 + p2
        x = _design(rng, n, p)
        beta_true = rng.normal(scale=0.2, size=p)
        mu_true = np.exp(x @ beta_true)
        y = rng.poisson(mu_true).astype(np.float64)
        weights = np.ones(n)

        s1 = np.zeros((p, p))
        s1[:p1, :p1] = np.eye(p1)
        s2 = np.zeros((p, p))
        s2[p1:, p1:] = np.eye(p2)
        blocks = (s1, s2)
        family = poisson_log()

        log10_sp = np.array([0.5, 1.0])
        lambdas = 10.0**log10_sp
        penalty = lambdas[0] * s1 + lambdas[1] * s2
        fit = penalized_irls_general(x, y, family=family, penalty=penalty, weights=weights)
        eta = x @ fit.coef
        mu = family.link.linkinv(eta)
        own_score = reml_score_general(y, x, family, fit.coef, blocks, lambdas, weights=weights)
        own_deviance = family.deviance(y, mu, weights)

        points = (
            {
                "name": "p1",
                "log10_sp": log10_sp,
                "mgcv_score": own_score,
                "mgcv_deviance": own_deviance,
            },
        )
        comparison = compare_fixed_sp_multiterm_case(y, x, family, blocks, weights, points)

        assert comparison.score_diff_spread == pytest.approx(0.0, abs=1e-9)
        assert comparison.max_abs_deviance_diff == pytest.approx(0.0, abs=1e-9)
        assert comparison.points[0].score_diff == pytest.approx(0.0, abs=1e-9)

    def test_detects_a_nonzero_deviance_artifact(self, rng: np.random.Generator) -> None:
        """A comparand deviance that does NOT match ours must show up as a
        nonzero max_abs_deviance_diff — the rescaled-penalty artifact this
        companion quantity exists to catch (module docstring)."""
        n, p = 100, 4
        x = _design(rng, n, p)
        beta_true = rng.normal(scale=0.2, size=p)
        mu_true = np.exp(x @ beta_true)
        y = rng.poisson(mu_true).astype(np.float64)
        weights = np.ones(n)
        block = np.eye(p)
        family = poisson_log()
        log10_sp = np.array([1.0])

        points = (
            {
                "name": "artifact",
                "log10_sp": log10_sp,
                "mgcv_score": 0.0,
                "mgcv_deviance": 1.0e6,  # deliberately wrong
            },
        )
        comparison = compare_fixed_sp_multiterm_case(y, x, family, (block,), weights, points)
        assert comparison.max_abs_deviance_diff > 1.0

    def test_rejects_a_log10_sp_length_mismatch(self, rng: np.random.Generator) -> None:
        n, p = 60, 3
        x = _design(rng, n, p)
        y = rng.poisson(5.0, size=n).astype(np.float64)
        weights = np.ones(n)
        block = np.eye(p)
        points = (
            {
                "name": "bad",
                "log10_sp": np.array([1.0, 2.0]),
                "mgcv_score": 0.0,
                "mgcv_deviance": 0.0,
            },
        )
        with pytest.raises(PolarisValidationError, match="log10_sp"):
            compare_fixed_sp_multiterm_case(y, x, poisson_log(), (block,), weights, points)


class TestFixedSpMultitermClaim:
    def test_every_quantity_is_independent(self) -> None:
        """The provenance gate (ADR-193): a harness result must not be able
        to satisfy this claim silently."""
        require_parity_evidence(
            FIXED_SP_MULTITERM_REML_CLAIM.quantities, claim=FIXED_SP_MULTITERM_REML_CLAIM.claim
        )
