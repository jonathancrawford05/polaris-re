#!/usr/bin/env Rscript
#
# gam_quasipoisson_free_sp_probe.R -- capability ladder slice 3b: the
# quasipoisson(log) FIT-level free-sp re-run (docs/PLAN_mgcv_capability_ladder.md
# slice 3b, registered by PR #240's review per ADR-209 decision 1).
#
# WHAT THIS PROBES
# ------------------
# The IDENTICAL three-term design (formula, k, knots, n = 900) as
# scripts/gam_gaussian_free_sp_probe.R (ladder L5 fit level), with a fresh
# overdispersed-count draw (own seed, negative-binomial response) --
#
#   y ~ s(AttdAge, k = 13, bs = "cr")
#     + s(AttdAge, by = StudyYear_C, k = 13, bs = "cr")
#     + ti(AttdAge, PolYear, k = c(13, 6), bs = "cr")
#   family = quasipoisson(link = "log"), method = "REML"
#
# with mgcv choosing its OWN smoothing parameters AND its own dispersion.
# The response is an OVERDISPERSED count (negative binomial, size 4), so the
# estimated scale is genuinely > 1 and a criterion that silently assumed
# scale = 1 (i.e. was really Poisson) would land on a visibly different sp.
# Slice 3 measured quasipoisson at the SCORE level only; this is the fit level.
#
# THE eta OFFSET TRAP (carried constraint 4): read m$linear.predictors, never
# predict(type="link"); the gap is exported as a tripwire (no offset here).
#
# INDEPENDENCE (ADR-193): the Python side assembles its own design from the
# shared recipe via gam_model.fit_polaris_gam and selects its OWN
# log10(lambda) under the free-scale REML branch -- never reading mgcv's own
# sp/eta/coef/edf/scale.
#
# REQUIREMENTS: R with mgcv and jsonlite.
# USAGE:  Rscript scripts/gam_quasipoisson_free_sp_probe.R [output.json]
# EXIT STATUS: 0 on a completed run, 1 on any R-side error.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_quasipoisson_free_sp_probe.json"
  set.seed(20260930)

  n <- 900
  age_knots <- c(1, 2, 4, 7, 14, 18, 24, 35, 50, 70, 85, 90, 95)
  year_knots <- c(1, 2, 3, 5, 10, 21)

  AttdAge <- runif(n, 1, 95)
  PolYear <- runif(n, 1, 21)
  StudyYear_C <- runif(n, -5, 5)

  # Genuinely non-linear in age AND in the by-term's age profile, so no block
  # is driven to mgcv's "sp -> infinity" null-space corner (a first draft with
  # linear signal did exactly that and would have measured the bound, not the
  # criterion).
  eta_true <- 1.5 + 0.5 * sin(AttdAge / 12) - 0.02 * PolYear +
    0.08 * StudyYear_C * sin(AttdAge / 15) +
    0.3 * sin(AttdAge / 10) * cos(PolYear / 3)
  y <- as.numeric(rnbinom(n, mu = exp(eta_true), size = 4))

  df <- data.frame(
    AttdAge = AttdAge, PolYear = PolYear,
    StudyYear_C = StudyYear_C, y = y
  )
  knots_arg <- list(AttdAge = age_knots, PolYear = year_knots)

  m <- mgcv::gam(
    y ~ s(AttdAge, k = 13, bs = "cr") +
      s(AttdAge, by = StudyYear_C, k = 13, bs = "cr") +
      ti(AttdAge, PolYear, k = c(13, 6), bs = "cr"),
    data = df, family = quasipoisson(link = "log"),
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
    message("gam_quasipoisson_free_sp_probe.R FAILED: ", conditionMessage(e))
    1L
  }
)
quit(status = status)
