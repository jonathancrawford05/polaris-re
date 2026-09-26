#!/usr/bin/env Rscript
#
# gam_re_probe.R -- capability ladder rung L2 (bs="re"), Stage B, FIXED sp.
# (docs/PLAN_mgcv_capability_ladder.md slice 2.)
#
# WHAT THIS PROBES
# ------------------
# A two-term model mixing the already-verified `cr` basis with the NEW `re`
# basis, fit at a FIXED, externally-supplied sp for both blocks:
#
#   y ~ s(AttdAge, k = 13, bs = "cr")   # already tier-3 verified (ADR-194)
#     + s(GroupFac, bs = "re")          # the ONLY unverified thing here
#   family = gaussian(link = "identity")
#
# WHY gaussian(identity) AND WHY FIXED sp
# ------------------------------------------
# Same reasoning as gam_gaussian_probe.R (ladder slice 1): at fixed sp the
# Gaussian fit is ordinary penalized least squares and the (estimated) scale
# never enters it, so this is a complete measurement of the "re" TERM's
# construction and its interaction with the (already-verified) cr term and
# the fitter -- it is not a hedge, it is the regime with no IRLS convergence
# behaviour to hide behind. Free-sp for "re" is measured separately
# (gam_re_free_sp_probe.R) under a fixed-dispersion family (poisson-log), per
# the plan's own instruction that L2's free-sp half does not need to wait for
# L5 (scale-estimated REML).
#
# THE eta OFFSET TRAP (carried constraint 4)
# --------------------------------------------
# predict(m, type = "link") DROPS an argument-supplied offset. This model
# carries none, so m$linear.predictors and predict(type="link") must agree --
# both are read and their gap exported as a tripwire (never gated), exactly
# as gam_gaussian_probe.R does.
#
# INDEPENDENCE (ADR-193)
# -------------------------
# The Python side (polaris_re.analytics.gam_re_conformance) assembles its own
# design from the already-verified `cr` producer plus the NEW `re` producer
# (gam_basis_re.re_basis) and fits with gam_fit.penalized_irls_general at the
# SAME supplied sp, reading only the shared recipe this script exports --
# never this script's eta, coef or edf.
#
# REQUIREMENTS: R with mgcv and jsonlite.
# USAGE:  Rscript scripts/gam_re_probe.R [output.json]
# EXIT STATUS: 0 on a completed run, 1 on any R-side error.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_re_probe.json"
  set.seed(20260921) # ADR-074: pinned, never the wall clock.

  n <- 900
  n_levels <- 6L
  age_knots <- c(1, 2, 4, 7, 14, 18, 24, 35, 50, 70, 85, 90, 95)

  AttdAge <- runif(n, 1, 95)
  levs <- LETTERS[1:n_levels]
  GroupFac <- factor(sample(levs, n, replace = TRUE), levels = levs)
  # A per-level "true" random effect, so the re block carries real signal for
  # edf_total to move against (ADR-229's own "suspicion, not just a check":
  # the comparison must be sensitive to the term under test).
  level_effect <- setNames(c(-0.8, -0.3, 0.1, 0.4, 0.7, 1.1), levs)
  mu_true <- 2.0 + 0.03 * AttdAge + level_effect[as.character(GroupFac)]
  y <- as.numeric(mu_true) + rnorm(n, sd = 0.3)

  df <- data.frame(AttdAge = AttdAge, GroupFac = GroupFac, y = y)
  knots_arg <- list(AttdAge = age_knots)

  # Fixed sp, one per penalty block, in mgcv's own formula order:
  # [s(AttdAge), s(GroupFac, bs="re")] -- 2 blocks (re carries exactly one,
  # regardless of n_levels -- module docstring / MGCV_NOTATION_PRIMER.md §4).
  sp_fixed <- c(2.0, 1.2)

  m <- mgcv::gam(
    y ~ s(AttdAge, k = 13, bs = "cr") + s(GroupFac, bs = "re"),
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
    AttdAge = AttdAge,
    group = as.integer(GroupFac) - 1L,
    y = y,
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
    message("gam_re_probe.R FAILED: ", conditionMessage(e))
    1L
  }
)
quit(status = status)
