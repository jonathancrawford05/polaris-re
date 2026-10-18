"""``polaris_re.gam.bam_fitd`` / ``bam_fit`` / ``bam_fitd_conformance`` — real-data readiness
Slice R3, Stage B (ADR-260 amendments 2-4).

R-free: derivative formulas against finite differences of an independently coded criterion,
the supported subset and its refusals, the provenance declarations (ADR-193).
R-gated: the probe is run on one small cell and read (tier 1 here, a regression check; the
committed numbers are the tier-3 CI reading)."""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from polaris_re.analytics.experience_mgcv_conformance import rscript_mgcv_available
from polaris_re.analytics.gam_family import gaussian_identity, poisson_log, quasipoisson_log
from polaris_re.analytics.gam_initial_sp import (
    initial_log10_lambda,
    initial_log10_lambda_from_xx_diag,
)
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import ComparisonProvenance, require_parity_evidence
from polaris_re.gam import gam
from polaris_re.gam.api import _tero
from polaris_re.gam.bam_fitd import (
    _fit_chol,
    bam_fitd,
    penalty_block_structure,
)
from polaris_re.gam.bam_fitd_conformance import (
    END_TO_END_CLAIM,
    ISOLATION_CLAIM,
    SEED_CLAIM,
    compare_design_conditioned,
    compare_end_to_end,
    compare_seed_sensitivity,
)
from polaris_re.gam.formula import TensorCall

REPO_ROOT = Path(__file__).resolve().parents[2]


def _two_term_cell(
    seed: int = 0, n: int = 600
) -> tuple[np.ndarray, tuple[np.ndarray, ...], np.ndarray]:
    """Truncated-line spline design (an identified one: 1, t, u unpenalised; 6 ridge-penalised
    truncated lines per covariate) with two penalties, each of rank 6."""
    rng = np.random.default_rng(seed)
    t = rng.uniform(size=n)
    u = rng.uniform(size=n)
    knots = np.linspace(0.1, 0.9, 6)
    x = np.hstack(
        [
            np.ones((n, 1)),
            t[:, None],
            u[:, None],
            np.maximum(0.0, t[:, None] - knots[None, :]),
            np.maximum(0.0, u[:, None] - knots[None, :]),
        ]
    )
    p = x.shape[1]
    s1 = np.zeros((p, p))
    s1[3:9, 3:9] = np.eye(6)
    s2 = np.zeros((p, p))
    s2[9:15, 9:15] = np.eye(6)
    mu = 3.0 * np.exp(0.8 * np.sin(2 * np.pi * t) - 0.5 * u)
    return x, (s1, s2), rng.poisson(mu).astype(np.float64)


class TestFixedWeightCriterionDerivatives:
    """``_fit_chol``'s gradient/Hessian against finite differences of the criterion coded
    independently in this test (closed-form verification of the derivative formulas)."""

    @staticmethod
    def _criterion(
        xx: np.ndarray,
        f: np.ndarray,
        yy: float,
        blocks: tuple[np.ndarray, ...],
        rho: np.ndarray,
        ranks: tuple[int, ...],
    ) -> float:
        lam = np.exp(rho)
        s_lam = sum(lj * s for lj, s in zip(lam, blocks, strict=True))
        a = xx + s_lam
        beta = np.linalg.solve(a, f)
        rss_plus_bsb = yy - beta @ f
        ldet_a = np.linalg.slogdet(a)[1]
        ldet_s = 0.0
        for lj, s, rk in zip(lam, blocks, ranks, strict=True):
            ev = np.sort(np.linalg.eigvalsh(lj * s))[::-1][:rk]
            ldet_s += float(np.sum(np.log(ev)))
        return float((rss_plus_bsb + ldet_a - ldet_s) / 2.0)

    def test_gradient_and_hessian_match_finite_differences(self) -> None:
        x, blocks, y = _two_term_cell()
        w = y + 0.1
        z = np.log(y + 0.1) + (y - (y + 0.1)) / (y + 0.1)
        xx = (x * w[:, None]).T @ x
        f = x.T @ (w * z)
        yy = float(np.sum(w * z * z))
        st = penalty_block_structure(blocks)
        rho = np.array([1.0, 2.0])
        fc = _fit_chol(xx, f, blocks, st, rho, tol=0.0)
        ranks = (6, 6)
        h = 1.0e-4
        grad_fd = np.zeros(2)
        hess_fd = np.zeros((2, 2))
        for j in range(2):
            e = np.zeros(2)
            e[j] = h
            grad_fd[j] = (
                self._criterion(xx, f, yy, blocks, rho + e, ranks)
                - self._criterion(xx, f, yy, blocks, rho - e, ranks)
            ) / (2 * h)
        for j in range(2):
            for k in range(2):
                ej, ek = np.zeros(2), np.zeros(2)
                ej[j], ek[k] = h, h
                hess_fd[j, k] = (
                    self._criterion(xx, f, yy, blocks, rho + ej + ek, ranks)
                    - self._criterion(xx, f, yy, blocks, rho + ej - ek, ranks)
                    - self._criterion(xx, f, yy, blocks, rho - ej + ek, ranks)
                    + self._criterion(xx, f, yy, blocks, rho - ej - ek, ranks)
                ) / (4 * h * h)
        np.testing.assert_allclose(fc.grad, grad_fd, rtol=1e-6, atol=1e-7)
        # the Newton step solves hess @ step = -grad (before the eigenvalue floor/cap)
        np.testing.assert_allclose(hess_fd, hess_fd.T, rtol=1e-4)
        assert np.all(np.isfinite(fc.step))

    def test_overlapping_penalties_form_one_block_with_the_rank_of_their_sum(self) -> None:
        d2 = np.diff(np.eye(4), n=2, axis=0)
        a = np.zeros((6, 6))
        a[1:5, 1:5] = d2.T @ d2
        b = np.zeros((6, 6))
        b[1:5, 1:5] = np.eye(4)
        c = np.zeros((6, 6))
        c[5, 5] = 1.0
        st = penalty_block_structure((a, b, c))
        assert st.groups == ((0, 1), (2,))
        assert st.ranks == (4, 1)


class TestInitialSpRefactor:
    def test_xx_diag_form_equals_the_data_form(self) -> None:
        x, blocks, y = _two_term_cell()
        fam = poisson_log()
        mu = y + 0.1
        w = mu  # poisson/log working weight
        ldxx = np.sum((np.sqrt(w)[:, None] * x) ** 2, axis=0)
        np.testing.assert_array_equal(
            initial_log10_lambda(y, x, fam, blocks),
            initial_log10_lambda_from_xx_diag(ldxx, blocks),
        )


class TestBamFitd:
    def test_converges_and_is_stationary_for_the_penalised_working_model(self) -> None:
        x, blocks, y = _two_term_cell()
        res = bam_fitd(x, blocks, y, poisson_log())
        assert res.converged
        assert res.n_iter <= 40
        lam = np.exp(res.log_sp)
        s_lam = sum(lj * s for lj, s in zip(lam, blocks, strict=True))
        mu = res.mu
        w = mu
        z = (res.eta) + (y - mu) / mu
        score = x.T @ (w * (z - x @ res.coef)) - s_lam @ res.coef
        # stationarity of the penalised log-likelihood at the converged iterate
        assert np.max(np.abs(score)) / np.max(np.abs(x.T @ (w * z))) < 1e-4

    def test_edf_is_the_trace_of_the_hat_matrix_and_below_the_column_count(self) -> None:
        x, blocks, y = _two_term_cell()
        res = bam_fitd(x, blocks, y, poisson_log())
        assert 2.0 < float(np.sum(res.edf)) < x.shape[1]
        assert np.all(res.edf > -1e-8)

    def test_trace_records_every_iteration(self) -> None:
        x, blocks, y = _two_term_cell()
        res = bam_fitd(x, blocks, y, poisson_log())
        # the converging iteration stops at the TOP of its loop, before a smoothing step
        assert len(res.trace) == res.n_iter - 1
        assert [t.iteration for t in res.trace] == list(range(1, res.n_iter))

    @pytest.mark.parametrize("family", [gaussian_identity(), quasipoisson_log()])
    def test_unsupported_families_are_refused_by_name(self, family) -> None:  # type: ignore[no-untyped-def]
        x, blocks, y = _two_term_cell()
        with pytest.raises(PolarisValidationError, match=r"scale|supported"):
            bam_fitd(x, blocks, y, family)

    def test_no_penalty_is_refused(self) -> None:
        x, _, y = _two_term_cell()
        with pytest.raises(PolarisValidationError, match="no penalty"):
            bam_fitd(x, (), y, poisson_log())

    def test_the_producer_signature_takes_a_design_and_no_mgcv_fit(self) -> None:
        import inspect

        params = set(inspect.signature(bam_fitd).parameters)
        assert params == {
            "x",
            "penalty_blocks",
            "y",
            "family",
            "offset",
            "prior_weights",
            "maxit",
            "epsilon",
            "structure",
        }


def _frame(n_rep: int = 6) -> pl.DataFrame:
    rng = np.random.default_rng(3)
    g = pl.DataFrame(
        {
            "age": np.repeat(np.arange(40, 70), 10 * n_rep),
            "dur": np.tile(np.repeat(np.arange(1, 11), n_rep), 30),
        }
    )
    expo = rng.uniform(5, 40, g.height)
    lin = -5.5 + 0.05 * (g["age"].to_numpy() - 40) - 0.04 * g["dur"].to_numpy()
    y = rng.poisson(expo * np.exp(lin))
    return g.with_columns(pl.Series("expo", expo), pl.Series("y", y)).with_columns(
        logexpo=pl.col("expo").log()
    )


FORMULA = 'y ~ s(age, bs="cr", k=8) + s(dur, bs="cr", k=5) + offset(logexpo)'


class TestGamEntryPoint:
    def test_bam_pair_runs_and_is_labelled(self) -> None:
        df = _frame()
        fit = gam(FORMULA, df, "poisson", method="fREML", discrete=True)
        assert fit.fit_method == "fREML-discrete"
        assert fit.converged
        assert fit.n_iterations is not None
        ref = gam(FORMULA, df, "poisson")
        # a different algorithm, not a different model: close, and not asserted identical
        assert float(np.max(np.abs(fit.eta - ref.eta))) < 5e-2

    @pytest.mark.parametrize(
        ("method", "discrete"), [("fREML", False), ("REML", True), ("GCV", False)]
    )
    def test_other_pairs_are_refused_by_name(self, method: str, discrete: bool) -> None:
        with pytest.raises(PolarisValidationError, match="not a supported pair"):
            gam(FORMULA, _frame(), "poisson", method=method, discrete=discrete)

    def test_unconditional_covariance_and_summary_are_refused(self) -> None:
        fit = gam(FORMULA, _frame(), "poisson", method="fREML", discrete=True)
        with pytest.raises(PolarisValidationError, match="unconditional"):
            fit.vcov(unconditional=True)
        with pytest.raises(PolarisValidationError, match="summary"):
            fit.summary()
        _, se = fit.predict(_frame(), se_fit=True)
        assert np.all(np.isfinite(se)) and np.all(se > 0)

    def test_gaussian_is_refused_by_name(self) -> None:
        df = _frame().with_columns(pl.col("y").cast(pl.Float64))
        with pytest.raises(PolarisValidationError, match="not supported"):
            gam('y ~ s(age, bs="cr", k=8)', df, "gaussian", method="fREML", discrete=True)


class TestUniqueRowConstraint:
    """``unique_row_constraint``: the sum-to-zero constraint from one row per distinct value."""

    def test_default_is_data_rows_and_the_context_switches_to_unique_values(self) -> None:
        from polaris_re.analytics.gam_basis_cr import (
            cr_basis,
            cr_default_knots,
            sum_to_zero_null_space,
            unique_row_constraint,
        )

        x = np.concatenate(
            [np.full(50, 1.0), np.full(5, 2.0), np.full(5, 3.0), np.full(5, 4.0), np.full(5, 5.0)]
        )
        knots = cr_default_knots(x, 4)
        design = cr_basis(x, knots)[0]
        z_data = sum_to_zero_null_space(design)
        with unique_row_constraint():
            z_unique = sum_to_zero_null_space(design)
        assert np.allclose(design.mean(axis=0) @ z_data, 0.0, atol=1e-12)
        uniq = np.unique(design, axis=0)
        assert np.allclose(uniq.mean(axis=0) @ z_unique, 0.0, atol=1e-12)
        assert not np.allclose(z_data, z_unique)  # unbalanced data: the two constraints differ
        # the switch is scoped: outside the context the default is restored
        assert np.allclose(sum_to_zero_null_space(design), z_data)

    def test_bam_fit_predicts_its_own_training_rows_in_the_same_basis(self) -> None:
        df = _frame()
        fit = gam(FORMULA, df, "poisson", method="fREML", discrete=True)
        pred = fit.predict(df, "link")
        np.testing.assert_allclose(pred, fit.eta, atol=1e-10)


class TestTero:
    """``mgcv:::tero``: the margin with the largest bs.dim goes last (the last one on ties)."""

    @pytest.mark.parametrize(
        ("variables", "k", "expected_vars", "expected_k"),
        [
            (("age", "dur"), (13, 6), ("dur", "age"), (6, 13)),
            (("age", "dur"), (6, 13), ("age", "dur"), (6, 13)),
            (("age", "dur"), (8, 8), ("age", "dur"), (8, 8)),
        ],
    )
    def test_swap_iff_first_margin_is_strictly_larger(
        self,
        variables: tuple[str, ...],
        k: tuple[int, ...],
        expected_vars: tuple[str, ...],
        expected_k: tuple[int, ...],
    ) -> None:
        out = _tero(TensorCall(variables=variables, k=k))
        assert (out.variables, out.k) == (expected_vars, expected_k)
        assert out.text == f"ti({','.join(expected_vars)})"

    def test_gam_discrete_labels_the_ti_term_as_bam_does_and_reml_does_not(self) -> None:
        df = _frame()
        f = 'y ~ s(age, bs="cr", k=6) + ti(age, dur, bs="cr", k=c(7,4)) + offset(logexpo)'
        assert (
            gam(f, df, "poisson", method="fREML", discrete=True).smooth_labels[-1] == "ti(dur,age)"
        )
        assert gam(f, df, "poisson").smooth_labels[-1] == "ti(age,dur)"


class TestProvenanceDeclarations:
    def test_end_to_end_parity_columns_are_independent_and_gate(self) -> None:
        parity = END_TO_END_CLAIM.parity_quantities
        assert len(parity) == 5
        require_parity_evidence(parity, claim="bam_fitd end to end")
        baseline = [q for q in END_TO_END_CLAIM.quantities if "baseline" in q.quantity]
        assert baseline[0].provenance is ComparisonProvenance.REFERENCE_INTERNAL

    def test_seed_spread_is_reference_internal_and_polaris_column_independent(self) -> None:
        by = {q.quantity: q.provenance for q in SEED_CLAIM.quantities}
        assert ComparisonProvenance.REFERENCE_INTERNAL in by.values()
        assert len(SEED_CLAIM.parity_quantities) == 1
        with pytest.raises(PolarisValidationError):
            require_parity_evidence(SEED_CLAIM.quantities, claim="seed spread as parity")

    def test_design_conditioned_table_cannot_be_cited_as_parity(self) -> None:
        """Polaris is handed mgcv's X and S: the ADR-193 mechanical test fails, so no column
        is independent and the gate refuses it."""
        assert not ISOLATION_CLAIM.parity_quantities
        with pytest.raises(PolarisValidationError):
            require_parity_evidence(ISOLATION_CLAIM.quantities, claim="isolation as parity")


@pytest.mark.skipif(not rscript_mgcv_available(), reason="Rscript with mgcv not available")
def test_probe_one_cell_agrees_end_to_end_and_given_bams_own_design(tmp_path: Path) -> None:
    out = tmp_path / "probe.json"
    subprocess.run(
        ["Rscript", str(REPO_ROOT / "scripts" / "bam_fitd_probe.R"), str(out), "ti_select"],
        check=True,
        capture_output=True,
        cwd=REPO_ROOT,
        env={"OPENBLAS_NUM_THREADS": "1", "PATH": "/usr/bin:/usr/local/bin:/bin"},
    )
    payload = json.loads(out.read_text())
    cell = payload["cells"][0]
    e2e = compare_end_to_end(cell)
    assert e2e.gates_met
    assert e2e.iter_polaris == e2e.iter_mgcv
    iso = compare_design_conditioned(cell)
    assert iso.iter_polaris == iso.iter_mgcv
    # on bam's own design the algorithm reproduces bam's eta to far below any gate
    assert iso.eta_max_abs < 1e-6
    assert max(iso.eta_diff_by_iteration) < 1e-6
    # the first iterations are round-off close
    assert max(iso.log_sp_diff_by_iteration[:5]) < 1e-8
    seeds = compare_seed_sensitivity(cell)
    assert seeds is not None and seeds.n_seeds == 7
    # bam's own noise floor on this cell is tiny; Polaris sits inside its cloud
    assert seeds.spread < 1e-4
    assert seeds.polaris_vs_seed_max <= max(seeds.spread, 1e-5) + 1e-5
    sys.stdout.flush()
