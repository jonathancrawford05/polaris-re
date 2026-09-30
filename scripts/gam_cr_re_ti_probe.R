#!/usr/bin/env Rscript
#
# gam_cr_re_ti_probe.R -- capability ladder slice 6: `cr` + `re` + `ti` fit
# JOINTLY, Stage B. (docs/PLAN_mgcv_capability_ladder.md slice 6.)
#
# WHAT THIS PROBES
# ------------------
# Each of the three bases is independently tier-3 verified (cr ADR-194, re
# ADR-230, ti ADR-205/206) but they have never been fit TOGETHER in one model.
# This script fits, natively in mgcv:
#
#   y ~ s(AttdAge, k = 13, bs = "cr")
#     + s(GroupFac, bs = "re")
#     + ti(AttdAge, PolYear, k = c(13, 6), bs = "cr")
#
# in three regimes, one JSON with a `cases` object keyed by case name:
#
#   gaussian_fixed  gaussian(identity), sp SUPPLIED  (4 blocks: cr, re, ti#1, ti#2)
#   gaussian_free   gaussian(identity), method="REML" (mgcv selects sp)
#   poisson_free    poisson(log),       method="REML" (mgcv selects sp)
#
# gaussian first (plan slice 6: a single linear solve decouples the
# composition check from IRLS convergence); the poisson case then adds the
# IRLS path to the same composition. The PLAN names quasi-Poisson as the
# production family but that is slices 3b/7 -- fixed-dispersion poisson(log)
# is the already-verified stand-in that exercises the same iteration.
#
# THE SHARED COVARIATES
# ---------------------
# One design (AttdAge, PolYear, GroupFac) is drawn once and reused by all
# three cases; only the response differs by family. AttdAge feeds BOTH the cr
# reference smooth and the ti margin -- ti() excludes its margins' main
# effects by construction, which is exactly the identifiability interaction
# this composition is the first to exercise.
#
# THE eta OFFSET TRAP (carried constraint 4)
# --------------------------------------------
# Read m$linear.predictors; predict(type="link") is exported as a tripwire
# (no offset in this model, so the two must agree).
#
# INDEPENDENCE (ADR-193)
# -------------------------
# The Python side (polaris_re.analytics.gam_cr_re_ti_conformance) assembles
# its own design from the three already-verified basis producers via
# gam_model.assemble_model_design and fits with gam_fit /
# gam_model.fit_polaris_gam, reading only the RECIPE keys this script exports
# (covariates, y, knots, and -- for the fixed case only -- `sp_fixed`). It
# never reads `eta`, `mgcv_sp`, `edf_total`, `term_edf` or `coef`.
#
# REQUIREMENTS: R with mgcv and jsonlite.
# USAGE:  Rscript scripts/gam_cr_re_ti_probe.R [output.json]
# EXIT STATUS: 0 on a completed run, 1 on any R-side error.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

FORMULA <- y ~ s(AttdAge, k = 13, bs = "cr") +
  s(GroupFac, bs = "re") +
  ti(AttdAge, PolYear, k = c(13, 6), bs = "cr")

fit_case <- function(df, family, knots_arg, shared, sp_fixed = NULL) {
  m <- if (is.null(sp_fixed)) {
    mgcv::gam(FORMULA, data = df, family = family, knots = knots_arg, method = "REML")
  } else {
    mgcv::gam(FORMULA, data = df, family = family, knots = knots_arg, sp = sp_fixed)
  }
  eta <- as.numeric(m$linear.predictors)
  eta_predict <- as.numeric(predict(m, type = "link"))
  out <- c(
    shared,
    list(
      family = family$family,
      link = family$link,
      y = as.numeric(df$y),
      eta = eta,
      edf_total = as.numeric(sum(m$edf)),
      term_edf = I(as.numeric(summary(m)$s.table[, "edf"])),
      term_labels = I(rownames(summary(m)$s.table)),
      offset_gap = max(abs(eta - eta_predict)),
      coef = as.numeric(coef(m)), # diagnostic only, never compared (Anchor 2)
      converged = isTRUE(m$converged),
      scale_estimated = isTRUE(m$scale.estimated),
      scale = as.numeric(m$scale)
    )
  )
  if (is.null(sp_fixed)) {
    out$mgcv_sp <- I(as.numeric(m$sp))
  } else {
    out$sp_fixed <- I(as.numeric(sp_fixed))
  }
  out
}

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_cr_re_ti_probe.json"
  set.seed(20260928) # ADR-074: pinned, never the wall clock.

  n <- 900
  n_levels <- 6L
  # PLAN Section 1's own target-formula knot vectors (same literals slice 5b/6b used).
  age_knots <- c(1, 2, 4, 7, 14, 18, 24, 35, 50, 70, 85, 90, 95)
  year_knots <- c(1, 2, 3, 5, 10, 21)

  AttdAge <- runif(n, 1, 95)
  PolYear <- runif(n, 1, 21)
  levs <- LETTERS[1:n_levels]
  GroupFac <- factor(sample(levs, n, replace = TRUE), levels = levs)
  level_effect <- as.numeric(setNames(c(-0.5, -0.2, 0.05, 0.15, 0.35, 0.55), levs)[as.character(GroupFac)])
  # A genuine age x duration interaction, so the ti() block has real signal
  # to fit (a zero-signal ti would agree trivially -- suspicion, not just a check).
  interaction <- 0.4 * sin(AttdAge / 15) * cos(PolYear / 4)

  y_gauss <- 1.0 + 0.6 * sin(AttdAge / 20) + level_effect + interaction + rnorm(n, sd = 0.3)
  y_pois <- rpois(n, lambda = exp(0.5 + 0.6 * sin(AttdAge / 20) + level_effect + 0.5 * interaction))

  shared <- list(
    n = n, n_levels = n_levels,
    AttdAge = AttdAge, PolYear = PolYear,
    group = as.integer(GroupFac) - 1L,
    age_knots = age_knots, year_knots = year_knots
  )
  knots_arg <- list(AttdAge = age_knots, PolYear = year_knots)
  df_g <- data.frame(y = y_gauss, AttdAge = AttdAge, PolYear = PolYear, GroupFac = GroupFac)
  df_p <- data.frame(y = y_pois, AttdAge = AttdAge, PolYear = PolYear, GroupFac = GroupFac)

  # Fixed sp, one per penalty block in mgcv's formula order:
  # [s(AttdAge), s(GroupFac,re), ti(AttdAge,PolYear)#1, ti(...)#2].
  sp_fixed <- c(2.0, 1.2, 1.5, 4.0)

  cases <- list(
    gaussian_fixed = fit_case(df_g, gaussian(link = "identity"), knots_arg, shared, sp_fixed),
    gaussian_free = fit_case(df_g, gaussian(link = "identity"), knots_arg, shared),
    poisson_free = fit_case(df_p, poisson(link = "log"), knots_arg, shared)
  )

  out <- list(
    schema_version = 1L,
    mgcv_version = as.character(packageVersion("mgcv")),
    r_version = R.version.string,
    cases = cases
  )
  jsonlite::write_json(
    out, out_path,
    digits = NA, auto_unbox = TRUE, null = "null", matrix = "rowmajor"
  )
  for (nm in names(cases)) {
    cs <- cases[[nm]]
    cat(sprintf(
      "  %-15s edf_total=%.6f offset_gap=%.3e converged=%s sp=%s\n",
      nm, cs$edf_total, cs$offset_gap, cs$converged,
      paste(sprintf("%.5g", if (is.null(cs$mgcv_sp)) cs$sp_fixed else cs$mgcv_sp), collapse = ",")
    ))
  }
  cat(sprintf("Wrote %s -- n=%d, mgcv %s\n", out_path, n, as.character(packageVersion("mgcv"))))
  invisible(NULL)
}

status <- tryCatch(
  {
    main(commandArgs(trailingOnly = TRUE))
    0L
  },
  error = function(e) {
    message("gam_cr_re_ti_probe.R FAILED: ", conditionMessage(e))
    1L
  }
)
quit(status = status)
