#!/usr/bin/env Rscript
#
# gam_gaussian_free_sp_probe.R -- capability ladder rung L1 re-run at FREE sp,
# unblocked by rung L5 (docs/PLAN_mgcv_capability_ladder.md slice 3).
#
# WHAT THIS PROBES
# ------------------
# The IDENTICAL three-term design and synthetic recipe as
# scripts/gam_gaussian_probe.R (ladder slice 1, ADR-229) --
#
#   y ~ s(AttdAge, k = 13, bs = "cr")                          # reference age
#     + s(AttdAge, by = StudyYear_C, k = 13, bs = "cr")        # the MI term
#     + ti(AttdAge, PolYear, k = c(13, 6), bs = "cr")          # age x duration
#   family = gaussian(link = "identity")
#
# but with mgcv choosing its OWN smoothing parameters via method="REML",
# rather than a caller-supplied fixed sp. This is slice 1's own "fixed sp
# only" qualifier, lifted: gam_reml.reml_score_general's free-scale branch
# (this slice's own build) is what makes this recipe fittable at free sp at
# all -- until it existed, reml_score_general RAISED on
# dispersion_fixed=False (gam_reml.py:263, before this slice), so
# select_lambdas_continuous had no criterion to search.
#
# WHY THE IDENTICAL RECIPE TO SLICE 1, DOWN TO THE SEED
# ---------------------------------------------------------
# Same reasoning ADR-229 gave for holding the design fixed against the
# multi-term probe: introducing a new design alongside the newly-unblocked
# free-sp search would confound "does the free-scale criterion work" with
# "does this new design fit". Reusing slice 1's own recipe means a
# disagreement here is attributable to the free-sp SEARCH under a free-scale
# criterion, and nothing else.
#
# THE eta OFFSET TRAP (carried constraint 4)
# --------------------------------------------
# Read m$linear.predictors, never predict(type="link") -- this recipe
# carries no offset, so both must agree; the gap is exported as a tripwire.
#
# INDEPENDENCE (ADR-193)
# -------------------------
# The Python side (polaris_re.analytics.gam_gaussian_conformance) assembles
# its own design from the shared recipe via gam_model.fit_polaris_gam, which
# selects its OWN log10(lambda) per block by minimizing
# gam_reml.reml_score_general's free-scale branch via
# gam_reml_optimize.select_lambdas_continuous -- never reading mgcv's own
# sp/eta/coef/edf.
#
# REQUIREMENTS: R with mgcv and jsonlite.
# USAGE:  Rscript scripts/gam_gaussian_free_sp_probe.R [output.json]
# EXIT STATUS: 0 on a completed run, 1 on any R-side error.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_gaussian_free_sp_probe.json"
  set.seed(20260919) # SAME seed as gam_gaussian_probe.R deliberately -- the
  # identical synthetic population, only the fitting regime (fixed vs free
  # sp) differs.

  n <- 900
  age_knots <- c(1, 2, 4, 7, 14, 18, 24, 35, 50, 70, 85, 90, 95)
  year_knots <- c(1, 2, 3, 5, 10, 21)

  AttdAge <- runif(n, 1, 95)
  PolYear <- runif(n, 1, 21)
  StudyYear_C <- runif(n, -5, 5)

  mu_true <- 2.5 + 0.03 * AttdAge - 0.02 * PolYear +
    0.01 * StudyYear_C * (AttdAge - 50) / 50 +
    0.15 * sin(AttdAge / 10) * cos(PolYear / 3)
  y <- mu_true + rnorm(n, sd = 0.25)

  df <- data.frame(
    AttdAge = AttdAge, PolYear = PolYear,
    StudyYear_C = StudyYear_C, y = y
  )
  knots_arg <- list(AttdAge = age_knots, PolYear = year_knots)

  m <- mgcv::gam(
    y ~ s(AttdAge, k = 13, bs = "cr") +
      s(AttdAge, by = StudyYear_C, k = 13, bs = "cr") +
      ti(AttdAge, PolYear, k = c(13, 6), bs = "cr"),
    data = df, family = gaussian(link = "identity"),
    knots = knots_arg, method = "REML"
  )

  eta <- as.numeric(m$linear.predictors)
  eta_predict <- as.numeric(predict(m, type = "link"))
  offset_gap <- max(abs(eta - eta_predict))

  out <- list(
    schema_version = 1L,
    n = n,
    AttdAge = AttdAge, PolYear = PolYear, StudyYear_C = StudyYear_C,
    y = y,
    age_knots = age_knots, year_knots = year_knots,
    mgcv_version = as.character(packageVersion("mgcv")),
    r_version = R.version.string,
    eta = eta,
    sp = as.numeric(m$sp),
    edf_total = as.numeric(sum(m$edf)),
    term_edf = as.numeric(summary(m)$s.table[, "edf"]),
    offset_gap = offset_gap,
    coef = as.numeric(coef(m)),
    scale = as.numeric(m$scale),
    converged = isTRUE(m$converged)
  )
  jsonlite::write_json(
    out, out_path,
    digits = NA, auto_unbox = TRUE, null = "null", matrix = "rowmajor"
  )
  cat(sprintf(
    "Wrote %s -- n=%d, mgcv %s, edf_total=%.6f, sp=%s, offset_gap=%.3e\n",
    out_path, n, as.character(packageVersion("mgcv")),
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
    message("gam_gaussian_free_sp_probe.R FAILED: ", conditionMessage(e))
    1L
  }
)
quit(status = status)
