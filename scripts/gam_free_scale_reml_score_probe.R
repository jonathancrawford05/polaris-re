#!/usr/bin/env Rscript
#
# gam_free_scale_reml_score_probe.R -- capability ladder rung L5, scale-estimated
# REML (docs/PLAN_mgcv_capability_ladder.md slice 3).
#
# WHAT THIS PROBES
# ------------------
# The SAME shape as scripts/gam_reml_probe.R (a shared two-block design, three
# fixed (sp1, sp2) points, method="REML" so m$gcv.ubre reports the REML
# criterion at that exact point with no optimisation) -- but under TWO
# FREE-SCALE families (dispersion_fixed=False): gaussian(identity) and
# quasipoisson(log). gam_reml_probe.R's own binomial/logit case is a KNOWN-scale
# family (dispersion held at 1); this probe is what gam_reml.reml_score_general's
# FREE-scale branch needs to be measured against.
#
# WHY BOTH FAMILIES IN ONE PROBE
# --------------------------------
# PLAN_mgcv_capability_ladder.md slice 3: "It unblocks four families at once --
# Gaussian, quasi-Poisson, Gamma, Tweedie -- though only the first two are
# registered today." Both carry dispersion_fixed=False (gam_family.py), so both
# exercise the SAME new branch in reml_score_general -- one probe, one shared
# design, two families is the minimal case that tests the branch is not an
# accident of one family's own deviance shape.
#
# WHY SCORE DIFFERENCES, ALSO CHECKED AGAINST THE ABSOLUTE VALUE
# -------------------------------------------------------------------
# Unlike gam_reml_probe.R's binomial case (known-scale, ADR-196's own
# "unexplained residual" precedent), the derivation behind the free-scale
# branch was checked DIRECTLY against mgcv's own gcv.ubre, ABSOLUTE VALUE, for
# Gaussian, and reproduced it to float round-trip precision INCLUDING every
# additive constant (docs/CONFORMANCE_LEDGER.md). Quasi-Poisson has no proper
# saturated log-likelihood (quasi-likelihood's own a(y,phi) term is not
# uniquely defined), so it carries a small, nearly-lambda-independent
# additive residual against gcv.ubre -- the SAME shape of finding ADR-196
# already accepted for the known-scale Poisson criterion's own convention
# offset. This probe reports BOTH the absolute score and the pairwise
# differences so the Python side can check whichever is meaningful per family,
# rather than assuming one convention for both.
#
# WHY THIS BUILDS ITS OWN CASE, WITH NO EXCHANGE DEPENDENCY
# -----------------------------------------------------------
# Same reasoning as gam_reml_probe.R / gam_family_probe.R: builds X, S1, S2, y
# deterministically (set.seed, ADR-074) and writes them into its own output
# JSON. The Python side reads ONLY the recipe fields back -- never this
# script's own gcv_ubre -- and fits + scores independently via
# gam_fit.penalized_irls_general / gam_reml.reml_score_general, which is what
# makes the comparison INDEPENDENT (ADR-193's mechanical test).
#
# REQUIREMENTS: R with mgcv and jsonlite.
# USAGE:  Rscript scripts/gam_free_scale_reml_score_probe.R [output.json]
# EXIT STATUS: 0 on a completed run, 1 on any R-side error.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

build_shared_design <- function(n = 200, p1 = 3, p2 = 3) {
  # Same construction as gam_reml_probe.R's own build_shared_design: intercept
  # (unpenalized) + two Fourier blocks, each with its own second-difference
  # penalty padded to the full design width.
  t <- seq(0, 1, length.out = n)
  p <- 1 + p1 + p2
  cols <- list(rep(1, n))
  for (k in seq_len(p1)) {
    cols[[length(cols) + 1]] <- sin(2 * pi * k * t)
  }
  for (k in seq_len(p2)) {
    cols[[length(cols) + 1]] <- cos(2 * pi * (k + 0.5) * t)
  }
  X <- do.call(cbind, cols)

  d1 <- diff(diag(p1), differences = 2)
  block1 <- t(d1) %*% d1
  S1 <- matrix(0, p, p)
  S1[2:(1 + p1), 2:(1 + p1)] <- block1

  d2 <- diff(diag(p2), differences = 2)
  block2 <- t(d2) %*% d2
  S2 <- matrix(0, p, p)
  idx2 <- (2 + p1):(1 + p1 + p2)
  S2[idx2, idx2] <- block2

  list(t = t, X = X, S1 = S1, S2 = S2, p = p)
}

fit_one_family <- function(X, S1, S2, y, family_obj, sp_points) {
  points_out <- list()
  for (i in seq_along(sp_points)) {
    sp <- sp_points[[i]]
    frame <- list(y = y, X = X)
    args <- list(
      formula = y ~ 0 + X,
      data = frame,
      family = family_obj,
      paraPen = list(X = list(S1, S2, sp = sp)),
      method = "REML"
    )
    m <- do.call(mgcv::gam, args)
    points_out[[i]] <- list(
      sp = sp,
      gcv_ubre = as.numeric(m$gcv.ubre),
      edf_total = sum(as.numeric(m$edf)),
      deviance = as.numeric(m$deviance),
      scale = as.numeric(m$scale),
      converged = isTRUE(m$converged)
    )
  }
  points_out
}

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_free_scale_reml_score_probe.json"
  set.seed(20260926) # ADR-074: pinned, never the wall clock.

  design <- build_shared_design()
  X <- design$X
  S1 <- design$S1
  S2 <- design$S2
  n <- nrow(X)
  p <- design$p

  beta_true <- c(2.0, 0.5, -0.35, 0.25, -0.3, 0.2, -0.15)[seq_len(p)]
  eta_true <- as.numeric(X %*% beta_true)

  # Same off-diagonal sp points as gam_reml_probe.R, for the same reason
  # (l1-scale-convention): a convention error mixing the two penalties'
  # scaling would not show at (1,1) but would several decades apart.
  sp_points <- list(c(1.0, 1.0), c(5.0, 0.2), c(0.5, 8.0))

  y_gaussian <- eta_true + rnorm(n, sd = 0.3)
  y_qp <- rpois(n, lambda = pmax(exp(eta_true * 0.15), 1e-6))

  points_gaussian <- fit_one_family(X, S1, S2, y_gaussian, gaussian(link = "identity"), sp_points)
  points_qp <- fit_one_family(X, S1, S2, y_qp, quasipoisson(link = "log"), sp_points)

  out <- list(
    schema_version = 1L,
    n = n,
    p = p,
    X = X,
    S1 = S1,
    S2 = S2,
    y_gaussian = y_gaussian,
    y_quasipoisson = y_qp,
    mgcv_version = as.character(packageVersion("mgcv")),
    r_version = R.version.string,
    points_gaussian = points_gaussian,
    points_quasipoisson = points_qp
  )
  jsonlite::write_json(
    out, out_path,
    digits = NA, auto_unbox = TRUE, null = "null", matrix = "rowmajor"
  )
  cat(sprintf(
    "Wrote %s -- %d sp points, mgcv %s\n", out_path, length(sp_points),
    as.character(packageVersion("mgcv"))
  ))
  for (pt in points_gaussian) {
    cat(sprintf(
      "  gaussian     sp=(%.4g, %.4g)  gcv.ubre=%.10g  scale=%.6g  converged=%s\n",
      pt$sp[1], pt$sp[2], pt$gcv_ubre, pt$scale, pt$converged
    ))
  }
  for (pt in points_qp) {
    cat(sprintf(
      "  quasipoisson sp=(%.4g, %.4g)  gcv.ubre=%.10g  scale=%.6g  converged=%s\n",
      pt$sp[1], pt$sp[2], pt$gcv_ubre, pt$scale, pt$converged
    ))
  }
  invisible(NULL)
}

status <- tryCatch(
  {
    main(commandArgs(trailingOnly = TRUE))
    0L
  },
  error = function(e) {
    message("gam_free_scale_reml_score_probe.R FAILED: ", conditionMessage(e))
    1L
  }
)
quit(status = status)
