#!/usr/bin/env Rscript
#
# gam_by_factor_probe.R -- capability ladder rung L3 (factor-by), Stage B,
# FIXED sp. (docs/PLAN_mgcv_capability_ladder.md slice 4.)
#
# WHAT THIS PROBES
# ------------------
# A two-term model pairing the already-verified `cr` basis (on PolYear) with
# the NEW factor-by construction (on AttdAge), fit at a FIXED, externally-
# supplied sp for every block:
#
#   y ~ s(PolYear, k = 6, bs = "cr")             # already tier-3 verified (ADR-194)
#     + s(AttdAge, by = GroupFac, k = 13, bs = "cr")  # the ONLY unverified thing here
#   family = gaussian(link = "identity")
#
# The two smoothed covariates are DELIBERATELY DIFFERENT (PolYear vs AttdAge)
# so the reference term and the by-term cannot be confounded with each other
# the way two terms sharing one covariate could be.
#
# WHY gaussian(identity) FOR BOTH REGIMES
# ------------------------------------------
# Ladder rung L5 (ADR-231) already closed reml_score_general's free-scale
# branch, so — unlike ladder rung L2's own re probes, which had to route
# free sp through poisson(log) to avoid a since-closed blocker — this slice
# needs no family switch between the fixed- and free-sp probes. One family
# throughout is simpler and there is no remaining reason to avoid it.
#
# THE eta OFFSET TRAP (carried constraint 4)
# --------------------------------------------
# predict(m, type = "link") DROPS an argument-supplied offset. This model
# carries none, so m$linear.predictors and predict(type="link") must agree --
# both are read and their gap exported as a tripwire (never gated).
#
# INDEPENDENCE (ADR-193)
# -------------------------
# The Python side (polaris_re.analytics.gam_by_factor_conformance) assembles
# its own design from the already-verified `cr` producer plus the NEW
# factor-by producer (gam_basis_cr.by_factor_mask_design, via
# gam_term_spec.factor_by_terms) and fits with
# gam_fit.penalized_irls_general at the SAME supplied sp, reading only the
# shared recipe this script exports -- never this script's eta, coef or edf.
#
# REQUIREMENTS: R with mgcv and jsonlite.
# USAGE:  Rscript scripts/gam_by_factor_probe.R [output.json]
# EXIT STATUS: 0 on a completed run, 1 on any R-side error.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_by_factor_probe.json"
  set.seed(20260926) # ADR-074: pinned, never the wall clock.

  n <- 900
  n_levels <- 3L
  age_knots <- c(1, 2, 4, 7, 14, 18, 24, 35, 50, 70, 85, 90, 95)
  polyear_knots <- c(1, 2, 3, 5, 10, 21)

  PolYear <- runif(n, 1, 21)
  AttdAge <- runif(n, 1, 95)
  levs <- LETTERS[1:n_levels]
  GroupFac <- factor(sample(levs, n, replace = TRUE), levels = levs)
  # A per-level "true" age slope, so the by-block carries real signal for
  # edf_total to move against (the same "suspicion, not just a check"
  # instruction ADR-229/ADR-230 already carried for their own near-exact
  # agreements).
  level_slope <- setNames(c(0.4, -0.2, 0.6), levs)
  mu_true <- 1.5 + 0.05 * PolYear + level_slope[as.character(GroupFac)] * sin(AttdAge / 20)
  y <- as.numeric(mu_true) + rnorm(n, sd = 0.3)

  df <- data.frame(PolYear = PolYear, AttdAge = AttdAge, GroupFac = GroupFac, y = y)
  knots_arg <- list(PolYear = polyear_knots, AttdAge = age_knots)

  # Fixed sp, one per penalty block, in mgcv's own formula order:
  # [s(PolYear), s(AttdAge):A, s(AttdAge):B, s(AttdAge):C] -- 1 + n_levels
  # blocks (confirmed by direct probe before this script was written: a
  # factor-by term contributes exactly n_levels separate smoothing
  # parameters, one per level, MGCV_NOTATION_PRIMER.md §4).
  sp_fixed <- c(3.0, 1.5, 2.5, 0.8)

  m <- mgcv::gam(
    y ~ s(PolYear, k = 6, bs = "cr") + s(AttdAge, by = GroupFac, k = 13, bs = "cr"),
    data = df, family = gaussian(link = "identity"),
    knots = knots_arg, sp = sp_fixed
  )

  eta <- as.numeric(m$linear.predictors)
  eta_predict <- as.numeric(predict(m, type = "link"))
  offset_gap <- max(abs(eta - eta_predict))

  out <- list(
    schema_version = 1L,
    n = n,
    n_levels = n_levels,
    PolYear = PolYear,
    AttdAge = AttdAge,
    group = as.integer(GroupFac) - 1L,
    y = y,
    polyear_knots = polyear_knots,
    age_knots = age_knots,
    sp = sp_fixed,
    mgcv_version = as.character(packageVersion("mgcv")),
    r_version = R.version.string,
    eta = eta,
    edf_total = as.numeric(sum(m$edf)),
    term_edf = as.numeric(summary(m)$s.table[, "edf"]),
    offset_gap = offset_gap,
    coef = as.numeric(coef(m)),
    scale_estimated = isTRUE(m$scale.estimated),
    scale = as.numeric(m$scale),
    converged = isTRUE(m$converged)
  )
  jsonlite::write_json(
    out, out_path,
    digits = NA, auto_unbox = TRUE, null = "null", matrix = "rowmajor"
  )
  cat(sprintf(
    "Wrote %s -- n=%d, n_levels=%d, mgcv %s, edf_total=%.6f, offset_gap=%.3e\n",
    out_path, n, n_levels, as.character(packageVersion("mgcv")),
    sum(m$edf), offset_gap
  ))
  invisible(NULL)
}

status <- tryCatch(
  {
    main(commandArgs(trailingOnly = TRUE))
    0L
  },
  error = function(e) {
    message("gam_by_factor_probe.R FAILED: ", conditionMessage(e))
    1L
  }
)
quit(status = status)
