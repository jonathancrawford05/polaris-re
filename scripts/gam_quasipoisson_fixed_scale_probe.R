#!/usr/bin/env Rscript
#
# gam_quasipoisson_fixed_scale_probe.R -- capability ladder slice 7:
# quasipoisson(log) with an EXTERNALLY SUPPLIED, FIXED scale
# (docs/PLAN_mgcv_capability_ladder.md slice 7).
#
# WHAT THIS PROBES
# ------------------
# The IDENTICAL three-term design as scripts/gam_quasipoisson_free_sp_probe.R
# (fresh overdispersed negative-binomial draw, own seed), fit by
#
#   gam(family = quasipoisson(link = "log"), method = "REML", scale = phi)
#
# at TWO supplied phi: 2.0 (near the free-scale estimate on this data, ~2.4)
# and 6.0 (far from it, so agreement cannot be vacuous). mgcv chooses its own
# smoothing parameters with the scale held at phi.
#
# MEASURED FIRST (tier 1, recorded in the ledger): mgcv IGNORES `scale=` for
# poisson(log) -- it reports scale 1 and the Poisson fit -- so "quasi-Poisson
# fixed scale" is reachable ONLY through quasipoisson(). The plan's
# hypothesis that poisson(scale=phi) and quasipoisson(scale=phi) might be the
# same call is refuted; this probe therefore fits quasipoisson only, and
# exports the poisson(scale=phi) result as a diagnostic tripwire
# (poisson_ignores_scale) so the refutation is re-measured on the pinned oracle.
#
# THE eta OFFSET TRAP: read m$linear.predictors, never predict(type="link").
#
# INDEPENDENCE (ADR-193): phi is a SUPPLIED INPUT to both sides (it is in the
# recipe, like the data) -- it is not a compared quantity. eta, sp and edf are
# each computed by their own implementation; Python never reads mgcv's.
#
# REQUIREMENTS: R with mgcv and jsonlite.
# USAGE:  Rscript scripts/gam_quasipoisson_fixed_scale_probe.R [output.json]
# EXIT STATUS: 0 on a completed run, 1 on any R-side error.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

fit_one <- function(formula, df, knots_arg, family, phi) {
  m <- mgcv::gam(formula, data = df, family = family,
                 knots = knots_arg, method = "REML", scale = phi)
  list(
    eta = as.numeric(m$linear.predictors),
    offset_gap = max(abs(as.numeric(m$linear.predictors) -
                         as.numeric(predict(m, type = "link")))),
    sp = as.numeric(m$sp),
    edf_total = as.numeric(sum(m$edf)),
    term_edf = as.numeric(summary(m)$s.table[, "edf"]),
    term_labels = I(rownames(summary(m)$s.table)),
    scale = as.numeric(m$scale),
    converged = isTRUE(m$converged)
  )
}

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_quasipoisson_fixed_scale_probe.json"
  set.seed(20261001)
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

  formula <- y ~ s(AttdAge, k = 13, bs = "cr") +
    s(AttdAge, by = StudyYear_C, k = 13, bs = "cr") +
    ti(AttdAge, PolYear, k = c(13, 6), bs = "cr")
  scales <- c(2.0, 6.0)
  fits <- lapply(scales, function(phi)
    fit_one(formula, df, knots_arg, quasipoisson(link = "log"), phi))
  pois <- fit_one(formula, df, knots_arg, poisson(link = "log"), 2.0)

  out <- list(
    schema_version = 1L,
    n = n,
    AttdAge = AttdAge, PolYear = PolYear, StudyYear_C = StudyYear_C,
    y = y,
    age_knots = age_knots, year_knots = year_knots,
    scales = scales,
    mgcv_version = as.character(packageVersion("mgcv")),
    r_version = R.version.string,
    fits = fits,
    poisson_scale_arg_reported = pois$scale,
    poisson_ignores_scale = isTRUE(all.equal(pois$scale, 1))
  )
  jsonlite::write_json(
    out, out_path,
    digits = NA, auto_unbox = TRUE, null = "null", matrix = "rowmajor"
  )
  for (k in seq_along(scales)) cat(sprintf(
    "phi=%g: edf_total=%.6f, sp=%s\n", scales[k], fits[[k]]$edf_total,
    paste(round(fits[[k]]$sp, 4), collapse = ",")))
  cat(sprintf("Wrote %s -- n=%d, mgcv %s, poisson(scale=2) reports scale %g\n",
              out_path, n, as.character(packageVersion("mgcv")), pois$scale))
  invisible(NULL)
}

status <- tryCatch(
  {
    main(commandArgs(trailingOnly = TRUE))
    0L
  },
  error = function(e) {
    message("gam_quasipoisson_fixed_scale_probe.R FAILED: ", conditionMessage(e))
    1L
  }
)
quit(status = status)
