#!/usr/bin/env Rscript
#
# gam_re_free_sp_probe.R -- capability ladder rung L2 (bs="re"), Stage B,
# FREE sp. (docs/PLAN_mgcv_capability_ladder.md slice 2.)
#
# WHAT THIS PROBES
# ------------------
# The SAME two-term structure as gam_re_probe.R --
#
#   y ~ s(AttdAge, k = 13, bs = "cr") + s(GroupFac, bs = "re")
#
# -- but under poisson(log) with mgcv choosing BOTH smoothing parameters
# itself via method="REML", rather than a caller-supplied fixed sp.
#
# WHY poisson(log), NOT gaussian(identity)
# -------------------------------------------
# Gaussian has an unknown scale and gam_reml.reml_score_general RAISES on a
# free scale until capability-ladder rung L5 (slice 3) -- the blocker
# PLAN_mgcv_capability_ladder.md §2.2 names. poisson(log) has
# dispersion_fixed=True and its free-sp search is ALREADY verified elsewhere
# in this epic (gam_multiterm_free_sp_probe.R uses binomial(cloglog); slice
# 4 part A / ADR-196-199 verify the REML criterion and its continuous outer
# search under a fixed-dispersion family). So the "re" term's free-sp search
# can be measured WITHOUT waiting for L5 -- exactly the plan's own point
# (PLAN_mgcv_capability_ladder.md, slice 2: "its free-sp search runs under an
# already-supported fixed-dispersion family, so it does NOT wait on slice 3").
#
# THE eta OFFSET TRAP (carried constraint 4)
# --------------------------------------------
# Read m$linear.predictors, never predict(type="link") -- this model carries
# no offset, so both must agree; the gap is exported as a tripwire.
#
# INDEPENDENCE (ADR-193)
# -------------------------
# The Python side (polaris_re.analytics.gam_re_conformance) assembles its own
# design from the shared recipe via gam_model.fit_polaris_gam, which selects
# its OWN log10(lambda) per block by minimizing gam_reml.reml_score_general
# (never reading mgcv's own sp/eta/coef/edf) via
# gam_reml_optimize.select_lambdas_continuous -- the same already-verified
# search FREE_SP_MODEL_CLAIM / gam_gaussian_conformance's fixed-sp sibling use.
#
# REQUIREMENTS: R with mgcv and jsonlite.
# USAGE:  Rscript scripts/gam_re_free_sp_probe.R [output.json]
# EXIT STATUS: 0 on a completed run, 1 on any R-side error.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_re_free_sp_probe.json"
  set.seed(20260921) # ADR-074: pinned, never the wall clock -- SAME seed as
  # gam_re_probe.R deliberately: this is the identical covariate/response
  # RECIPE (age, group, y), only the fitting regime (fixed vs free sp, and
  # therefore the family that makes free sp reachable) differs. Reusing the
  # seed is not required for correctness -- it just means a reader comparing
  # the two probes side by side sees the same synthetic population.

  n <- 900
  n_levels <- 6L
  age_knots <- c(1, 2, 4, 7, 14, 18, 24, 35, 50, 70, 85, 90, 95)

  AttdAge <- runif(n, 1, 95)
  levs <- LETTERS[1:n_levels]
  GroupFac <- factor(sample(levs, n, replace = TRUE), levels = levs)
  level_effect <- setNames(c(-0.5, -0.2, 0.05, 0.15, 0.35, 0.55), levs)
  eta_true <- 1.0 + 0.01 * AttdAge + as.numeric(level_effect[as.character(GroupFac)])
  y <- rpois(n, lambda = exp(eta_true))

  df <- data.frame(AttdAge = AttdAge, GroupFac = GroupFac, y = y)
  knots_arg <- list(AttdAge = age_knots)

  m <- mgcv::gam(
    y ~ s(AttdAge, k = 13, bs = "cr") + s(GroupFac, bs = "re"),
    data = df, family = poisson(link = "log"),
    knots = knots_arg, method = "REML"
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
    message("gam_re_free_sp_probe.R FAILED: ", conditionMessage(e))
    1L
  }
)
quit(status = status)
