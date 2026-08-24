#!/usr/bin/env Rscript
#
# gam_multiterm_probe.R -- mgcv-parity engine, slice 5's remaining scope
# (docs/PLAN_mgcv_parity_engine.md, docs/CONTINUATION_mgcv_parity_engine.md).
#
# WHAT THIS PROBES
# ------------------
# The epic's first MULTI-TERM mgcv-native model: three of the target formula's
# eight terms (PLAN Section 1), fit TOGETHER, natively, by mgcv, at a FIXED,
# externally-supplied sp for every block -- the same "fixed sp" Stage-B regime
# gam_family_probe.R and gam_reml_probe.R already use, not REML selection.
#
#   y ~ s(AttdAge, k = 13, bs = "cr")                          # reference age
#     + s(AttdAge, by = StudyYear_C, k = 13, bs = "cr")        # the MI term
#     + ti(AttdAge, PolYear, k = c(13, 6), bs = "cr")          # age x duration
#   family = binomial(link = "cloglog"), weights = ExposCnt    # Anchor 5, absolute
#
# This is what docs/CONTINUATION_mgcv_parity_engine.md names as what remains of
# slice 5: "Nothing has run Stage B / Anchor 2's own criteria (the MI contrast,
# eta) on either this term or the `by` term -- that is what unblocks both slice 4
# part B's N>2 extension and Anchor 5's absolute/relative demonstration."
#
# WHY THIS BUILDS ITS OWN CASE, WITH NO EXCHANGE DEPENDENCY
# -----------------------------------------------------------
# Same reasoning as gam_family_probe.R / gam_reml_probe.R: a probe for a specific
# hypothesis needs a SHARED recipe both sides fit, not the full ADR-189 exchange.
# "Shared" means this script builds AttdAge/PolYear/StudyYear_C/ExposCnt/y
# deterministically (set.seed, ADR-074 -- no wall clock) and writes the recipe
# into its own output JSON alongside its own fit.
#
# WHY THE COMPARISON IS ON eta, NEVER coef (Anchor 2)
# -----------------------------------------------------
# mgcv reparameterises internally, and a multi-term model with a `by` smooth and
# a `ti()` tensor gives it even more freedom to do so than the single-term slice-2
# cases did. This script reports `coef` for diagnostic reading only.
#
# INDEPENDENCE (ADR-193)
# -------------------------
# The Python side (polaris_re.analytics.gam_multiterm_conformance) builds its own
# design from the three ALREADY-INDEPENDENTLY-VERIFIED basis producers
# (gam_basis_cr.cr_basis / by_scale_design / absorb_sum_to_zero_constraint /
# ti_basis, via gam_stage_a.build_python_cr_term / build_python_ti_term -- ADR-194,
# ADR-200, ADR-205) and fits with gam_fit.penalized_irls_general at the SAME
# externally-supplied sp. It reads only the shared recipe this script exports
# (AttdAge, PolYear, StudyYear_C, ExposCnt, y, the target formula's own knot
# vectors, sp) -- never this script's own eta or coef -- which is what makes the
# eta comparison INDEPENDENT rather than an echo of this script's fit.
#
# REQUIREMENTS: R with mgcv and jsonlite.
# USAGE:  Rscript scripts/gam_multiterm_probe.R [output.json]
# EXIT STATUS: 0 on a completed run, 1 on any R-side error.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_multiterm_probe.json"
  set.seed(20260824) # ADR-074: pinned, never the wall clock.

  n <- 900
  # PLAN Section 1's own target-formula knot vectors -- the literal knots, not a
  # stand-in, same discipline slice 2 (ADR-194) and slice 5's other cases used.
  age_knots <- c(1, 2, 4, 7, 14, 18, 24, 35, 50, 70, 85, 90, 95)
  year_knots <- c(1, 2, 3, 5, 10, 21)

  AttdAge <- runif(n, 1, 95)
  PolYear <- runif(n, 1, 21)
  StudyYear_C <- runif(n, -5, 5)
  ExposCnt <- round(runif(n, 50, 500))

  # A synthetic "true" surface -- not fitted to, just needs to produce a
  # reasonably-behaved binomial response under cloglog so the shared FIXED-sp fit
  # converges cleanly on both sides. Neither side reads this function; both sides
  # read only the resulting y/weights it produces.
  eta_true <- -4.5 + 0.03 * AttdAge - 0.02 * PolYear +
    0.01 * StudyYear_C * (AttdAge - 50) / 50 +
    0.15 * sin(AttdAge / 10) * cos(PolYear / 3)
  prob_true <- 1 - exp(-exp(eta_true))
  DthCnt <- rbinom(n, ExposCnt, prob_true)
  y <- DthCnt / ExposCnt

  df <- data.frame(
    AttdAge = AttdAge, PolYear = PolYear,
    StudyYear_C = StudyYear_C, ExposCnt = ExposCnt, y = y
  )
  knots_arg <- list(AttdAge = age_knots, PolYear = year_knots)

  # Fixed sp, one per penalty block, in the SAME order mgcv assigns to the
  # formula's smooth terms: [s(AttdAge), s(AttdAge,by=StudyYear_C), ti(...)#1,
  # ti(...)#2] -- 4 blocks (ti() carries two, ADR-205).
  sp_fixed <- c(2.0, 3.0, 1.5, 4.0)

  m <- mgcv::gam(
    y ~ s(AttdAge, k = 13, bs = "cr") +
      s(AttdAge, by = StudyYear_C, k = 13, bs = "cr") +
      ti(AttdAge, PolYear, k = c(13, 6), bs = "cr"),
    data = df, family = binomial(link = "cloglog"), weights = ExposCnt,
    knots = knots_arg, sp = sp_fixed
  )

  eta <- as.numeric(predict(m, type = "link"))

  out <- list(
    schema_version = 1L,
    n = n,
    AttdAge = AttdAge, PolYear = PolYear, StudyYear_C = StudyYear_C,
    ExposCnt = as.numeric(ExposCnt), y = y,
    age_knots = age_knots, year_knots = year_knots,
    sp = sp_fixed,
    mgcv_version = as.character(packageVersion("mgcv")),
    r_version = R.version.string,
    eta = eta,
    coef = as.numeric(coef(m)), # diagnostic only, never compared (Anchor 2)
    edf_per_smooth = as.numeric(m$edf1), # diagnostic only
    converged = isTRUE(m$converged)
  )
  jsonlite::write_json(
    out, out_path,
    digits = NA, auto_unbox = TRUE, null = "null", matrix = "rowmajor"
  )
  cat(sprintf(
    "Wrote %s -- n=%d, mgcv %s\n", out_path, n, as.character(packageVersion("mgcv"))
  ))
  invisible(NULL)
}

status <- tryCatch(
  {
    main(commandArgs(trailingOnly = TRUE))
    0L
  },
  error = function(e) {
    message("gam_multiterm_probe.R FAILED: ", conditionMessage(e))
    1L
  }
)
quit(status = status)
