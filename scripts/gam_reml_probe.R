#!/usr/bin/env Rscript
#
# gam_reml_probe.R — mgcv-parity engine, slice 4 part A (docs/PLAN_mgcv_parity_engine.md).
#
# Slice 4 is the outer N-dimensional (f)REML optimiser. Before any optimiser is built,
# the criterion it would search over has to itself agree with mgcv's, for the target
# formula's own family (binomial) and for more than the tensor MI surface's fixed two
# penalty blocks. This probe builds a SHARED (X, S1, S2, y, weights) recipe — two
# independently-scaled penalty blocks on one binomial/logit design, extending slice 3's
# single-block binomial-logit case — and fits it at three FIXED (sp1, sp2) points via
# `paraPen`, with `method="REML"` so `m$gcv.ubre` reports the REML criterion at that
# fixed point rather than a GCV/UBRE score (no optimisation happens: paraPen's own `sp`
# is fully supplied, the same idiom scripts/mgcv_conformance.R already uses for its
# fixed-lambda cells).
#
# WHY SCORE *DIFFERENCES*, NOT THE ABSOLUTE VALUE
# -------------------------------------------------
# ADR-189 amendment 1 already measured, for the already-verified Poisson case, that the
# absolute REML score carries a convention offset against mgcv's own (~ -l_sat/gamma,
# the saturated log-likelihood) PLUS a further residual of 0.93-3.17 that amendment
# left "unexplained" and explicitly "not a compared metric". Re-litigating that residual
# is not this probe's job. What actually matters for an optimiser is the criterion's
# SHAPE in lambda — score(point A) - score(point B) — which cancels any constant
# additive offset regardless of its source, known or not. This probe reports three
# points so the Python side can form differences pairwise.
#
# WHY THIS BUILDS ITS OWN CASE, WITH NO EXCHANGE DEPENDENCY
# -----------------------------------------------------------
# Same reasoning as scripts/gam_family_probe.R: builds X, S1, S2, y, weights
# deterministically (set.seed, ADR-074) and writes them into its own output JSON. The
# Python side reads ONLY those recipe fields — never this script's own `gcv_ubre` per
# point — and fits + scores independently via gam_fit.penalized_irls_general and
# gam_reml.reml_score_general, which is what makes the comparison INDEPENDENT
# (ADR-193's mechanical test).
#
# WHY BINOMIAL/LOGIT, AND TWO BLOCKS
# -------------------------------------
# The target formula's own family (PLAN §1) is binomial, and every one of its eight
# smooth terms is a separately-scaled penalty block. Slice 3 verified `eta` for a single
# combined block; this probe is the first case with more than one independently-scaled
# block under a family other than Poisson.
#
# REQUIREMENTS: R with `mgcv` and `jsonlite`.
#
# USAGE:
#     Rscript scripts/gam_reml_probe.R [output.json]
#
# EXIT STATUS: 0 on a completed run, 1 on any R-side error.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

build_shared_design <- function(n = 200, p1 = 3, p2 = 3) {
  # Intercept (unpenalized) + two Fourier blocks, each with its own second-difference
  # penalty padded to the full design width — the same "penalty spans the full design,
  # not a literal sub-block" convention scripts/mgcv_conformance.R's tensor case uses,
  # which is what makes two INDEPENDENTLY-scaled penalties on one coefficient vector
  # (rather than a block-diagonal single one) the right analogue of the target
  # formula's own multi-term structure.
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

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_reml_probe.json"
  set.seed(20260818)

  design <- build_shared_design()
  t <- design$t
  X <- design$X
  S1 <- design$S1
  S2 <- design$S2
  n <- nrow(X)
  p <- design$p

  beta_true <- c(0.2, 0.5, -0.35, 0.25, -0.3, 0.2, -0.15)[seq_len(p)]
  eta_true <- as.numeric(X %*% beta_true)
  prob <- 1 / (1 + exp(-eta_true))
  trials <- round(25 + 15 * sin(4 * pi * t))
  successes <- round(trials * prob)
  y <- successes / trials

  # Deliberately off-diagonal, mirroring scripts/mgcv_conformance.R's
  # `l1-scale-convention` cell: a convention error mixing the two penalties'
  # scaling would not show at (1,1) but would at points several decades apart
  # in opposite directions.
  sp_points <- list(c(1.0, 1.0), c(5.0, 0.2), c(0.5, 8.0))

  points_out <- list()
  for (i in seq_along(sp_points)) {
    sp <- sp_points[[i]]
    frame <- list(y = y, X = X, w = as.numeric(trials))
    args <- list(
      formula = y ~ 0 + X,
      data = frame,
      family = binomial(link = "logit"),
      weights = quote(w),
      paraPen = list(X = list(S1, S2, sp = sp)),
      method = "REML"
    )
    m <- do.call(mgcv::gam, args)
    points_out[[i]] <- list(
      sp = sp,
      gcv_ubre = as.numeric(m$gcv.ubre),
      edf_total = sum(as.numeric(m$edf)),
      deviance = as.numeric(m$deviance),
      converged = isTRUE(m$converged)
    )
  }

  out <- list(
    schema_version = 1L,
    n = n,
    p = p,
    t = t,
    X = X,
    S1 = S1,
    S2 = S2,
    y = y,
    weights = as.numeric(trials),
    family = "binomial",
    link = "logit",
    points = points_out,
    mgcv_version = as.character(packageVersion("mgcv")),
    r_version = R.version.string
  )
  jsonlite::write_json(
    out, out_path,
    digits = NA, auto_unbox = TRUE, null = "null", matrix = "rowmajor"
  )
  cat(sprintf(
    "Wrote %s — %d sp points, mgcv %s\n", out_path, length(points_out),
    as.character(packageVersion("mgcv"))
  ))
  for (pt in points_out) {
    cat(sprintf(
      "  sp=(%.4g, %.4g)  gcv.ubre=%.10g  edf_total=%.6g  converged=%s\n",
      pt$sp[1], pt$sp[2], pt$gcv_ubre, pt$edf_total, pt$converged
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
    message("gam_reml_probe.R FAILED: ", conditionMessage(e))
    1L
  }
)
quit(status = status)
