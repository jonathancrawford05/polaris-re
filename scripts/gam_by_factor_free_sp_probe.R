#!/usr/bin/env Rscript
#
# gam_by_factor_free_sp_probe.R -- capability ladder rung L3 (factor-by),
# Stage B, FREE sp. (docs/PLAN_mgcv_capability_ladder.md slice 4.)
#
# WHAT THIS PROBES
# ------------------
# The SAME two-term structure as gam_by_factor_probe.R --
#
#   y ~ s(PolYear, k = 6, bs = "cr") + s(AttdAge, by = GroupFac, k = 13, bs = "cr")
#
# -- but with mgcv choosing every smoothing parameter itself via
# method="REML", rather than a caller-supplied fixed sp.
#
# WHY gaussian(identity), SAME AS THE FIXED-sp PROBE
# -----------------------------------------------------
# Ladder rung L5 (ADR-231) already closed reml_score_general's free-scale
# branch, so this free-sp probe needs no family switch away from Gaussian --
# unlike ladder rung L2's own free-sp probe, which had to route through
# poisson(log) because L5 did not exist yet when it was written.
#
# THE eta OFFSET TRAP (carried constraint 4)
# --------------------------------------------
# Read m$linear.predictors, never predict(type="link") -- this model carries
# no offset, so both must agree; the gap is exported as a tripwire.
#
# INDEPENDENCE (ADR-193)
# -------------------------
# The Python side (polaris_re.analytics.gam_by_factor_conformance) assembles
# its own design from the shared recipe via gam_model.fit_polaris_gam, which
# selects its OWN log10(lambda) per block by minimizing
# gam_reml.reml_score_general (never reading mgcv's own sp/eta/coef/edf) via
# gam_reml_optimize.select_lambdas_continuous.
#
# REQUIREMENTS: R with mgcv and jsonlite.
# USAGE:  Rscript scripts/gam_by_factor_free_sp_probe.R [output.json]
# EXIT STATUS: 0 on a completed run, 1 on any R-side error.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_by_factor_free_sp_probe.json"
  set.seed(20260926) # ADR-074: pinned, never the wall clock -- SAME seed as
  # gam_by_factor_probe.R deliberately (the identical covariate/response
  # recipe; only the fitting regime differs).

  n <- 900
  n_levels <- 3L
  age_knots <- c(1, 2, 4, 7, 14, 18, 24, 35, 50, 70, 85, 90, 95)
  polyear_knots <- c(1, 2, 3, 5, 10, 21)

  PolYear <- runif(n, 1, 21)
  AttdAge <- runif(n, 1, 95)
  levs <- LETTERS[1:n_levels]
  GroupFac <- factor(sample(levs, n, replace = TRUE), levels = levs)
  level_slope <- setNames(c(0.4, -0.2, 0.6), levs)
  mu_true <- 1.5 + 0.05 * PolYear + level_slope[as.character(GroupFac)] * sin(AttdAge / 20)
  y <- as.numeric(mu_true) + rnorm(n, sd = 0.3)

  df <- data.frame(PolYear = PolYear, AttdAge = AttdAge, GroupFac = GroupFac, y = y)
  knots_arg <- list(PolYear = polyear_knots, AttdAge = age_knots)

  m <- mgcv::gam(
    y ~ s(PolYear, k = 6, bs = "cr") + s(AttdAge, by = GroupFac, k = 13, bs = "cr"),
    data = df, family = gaussian(link = "identity"),
    knots = knots_arg, method = "REML"
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
    mgcv_version = as.character(packageVersion("mgcv")),
    r_version = R.version.string,
    eta = eta,
    sp = as.numeric(m$sp),
    edf_total = as.numeric(sum(m$edf)),
    term_edf = as.numeric(summary(m)$s.table[, "edf"]),
    offset_gap = offset_gap,
    coef = as.numeric(coef(m)),
    converged = isTRUE(m$converged)
  )
  jsonlite::write_json(
    out, out_path,
    digits = NA, auto_unbox = TRUE, null = "null", matrix = "rowmajor"
  )
  cat(sprintf(
    "Wrote %s -- n=%d, n_levels=%d, mgcv %s, edf_total=%.6f, sp=%s, offset_gap=%.3e\n",
    out_path, n, n_levels, as.character(packageVersion("mgcv")),
    sum(m$edf), paste(round(m$sp, 4), collapse = ","), offset_gap
  ))
  invisible(NULL)
}

status <- tryCatch(
  {
    main(commandArgs(trailingOnly = TRUE))
    0L
  },
  error = function(e) {
    message("gam_by_factor_free_sp_probe.R FAILED: ", conditionMessage(e))
    1L
  }
)
quit(status = status)
