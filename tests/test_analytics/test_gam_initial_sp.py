"""Closed-form and R-parity checks for :mod:`polaris_re.analytics.gam_initial_sp`
(``mgcv``'s ``initial.sp`` recipe, ladder slice 3d)."""

import subprocess
import textwrap

import numpy as np
import pytest

from polaris_re.analytics.experience_mgcv_conformance import rscript_mgcv_available
from polaris_re.analytics.gam_family import binomial_logit, gaussian_identity, poisson_log
from polaris_re.analytics.gam_initial_sp import initial_log10_lambda
from polaris_re.core.exceptions import PolarisValidationError


def test_single_block_closed_form() -> None:
    # y = 0.9 -> mu = 1.0 (y + 0.1) -> W = mu = 1; X = 2 I -> diag(X'WX) = 4.
    y = np.full(3, 0.9)
    x = 2.0 * np.eye(3)
    for scale in (1.0, 100.0):
        s = scale * np.eye(3)
        got = initial_log10_lambda(y, x, poisson_log(), (s,))
        # def_sp = 4/scale; ldss = def_sp*diag(S) = 4 -> ratio 0.5, already >= 0.4
        np.testing.assert_allclose(got, [np.log10(4.0 / scale)], rtol=1e-12)


def test_balance_loop_moves_lambda_by_decades() -> None:
    # Two blocks on disjoint columns with different data size: ratio ends in [0.4, 4].
    y = np.full(4, 0.9)
    x = np.diag([1.0, 1.0, 5.0, 5.0])
    s1 = np.zeros((4, 4))
    s1[:2, :2] = np.eye(2)
    s2 = np.zeros((4, 4))
    s2[2:, 2:] = np.eye(2)
    got = initial_log10_lambda(y, x, poisson_log(), (s1, s2))
    lam = 10.0**got
    ldxx = np.array([1.0, 1.0, 25.0, 25.0])
    ldss = np.array([lam[0], lam[0], lam[1], lam[1]])
    assert np.mean(ldxx / (ldxx + ldss)) >= 0.4
    assert np.mean(ldxx / (ldxx + 10.0 * ldss)) < 0.4  # one decade more would undershoot
    # relative spacing before rescaling is sizeXX/sizeS per block: 1 vs 25
    np.testing.assert_allclose(got[1] - got[0], np.log10(25.0), rtol=1e-12)


def test_gaussian_and_binomial_initialisation_run() -> None:
    rng = np.random.default_rng(0)
    x = rng.normal(size=(30, 4))
    s = np.eye(4)
    assert initial_log10_lambda(rng.normal(size=30), x, gaussian_identity(), (s,)).shape == (1,)
    yb = (rng.uniform(size=30) > 0.5).astype(float)
    assert initial_log10_lambda(yb, x, binomial_logit(), (s,)).shape == (1,)


def test_zero_block_raises() -> None:
    with pytest.raises(PolarisValidationError, match="all zero"):
        initial_log10_lambda(np.ones(3), np.eye(3), poisson_log(), (np.zeros((3, 3)),))


@pytest.mark.slow
@pytest.mark.skipif(not rscript_mgcv_available(), reason="Rscript with mgcv not available")
def test_matches_mgcv_initial_sp_on_shared_inputs(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """R's ``mgcv:::initial.sp`` on the SAME (sqrt(W) X, S) the Python side builds."""
    rng = np.random.default_rng(5)
    n, p = 60, 8
    x = rng.normal(size=(n, p))
    y = rng.poisson(3.0, size=n).astype(float)
    a = rng.normal(size=(4, 4))
    s1 = np.zeros((p, p))
    s1[:4, :4] = a @ a.T + np.eye(4)
    s2 = np.zeros((p, p))
    s2[4:, 4:] = 7.0 * np.eye(4)
    mu = y + 0.1
    wx = np.sqrt(mu)[:, None] * x
    np.savetxt(tmp_path / "wx.csv", wx, delimiter=",", fmt="%.17g")
    np.savetxt(tmp_path / "s1.csv", s1[:4, :4], delimiter=",", fmt="%.17g")
    np.savetxt(tmp_path / "s2.csv", s2[4:, 4:], delimiter=",", fmt="%.17g")
    script = textwrap.dedent(
        f"""
        suppressMessages(library(mgcv))
        rd <- function(f) as.matrix(read.csv(file.path("{tmp_path}", f), header=FALSE))
        wx <- rd("wx.csv"); S <- list(rd("s1.csv"), rd("s2.csv"))
        cat(sprintf("%.15g", log10(mgcv:::initial.sp(wx, S, c(1, 5)))), sep="\\n")
        """
    )
    out = subprocess.run(["Rscript", "-e", script], check=True, capture_output=True, text=True)
    r_log = np.array([float(v) for v in out.stdout.split()])
    got = initial_log10_lambda(y, x, poisson_log(), (s1, s2))
    np.testing.assert_allclose(got, r_log, rtol=1e-10)


def test_fit_polaris_gam_rejects_initial_sp_start_with_x0_or_multistart() -> None:
    from polaris_re.analytics.gam_model import fit_polaris_gam
    from polaris_re.analytics.gam_quasipoisson_conformance import quasipoisson_model_spec

    model = quasipoisson_model_spec((1.0, 2.0, 3.0, 4.0), (1.0, 2.0, 3.0))
    with pytest.raises(PolarisValidationError, match="mutually exclusive"):
        fit_polaris_gam(model, {}, np.ones(3), initial_sp_start=True, x0=np.zeros(1))
    with pytest.raises(PolarisValidationError, match="mutually exclusive"):
        fit_polaris_gam(model, {}, np.ones(3), initial_sp_start=True, multistart=True)
