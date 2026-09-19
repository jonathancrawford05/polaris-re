#!/usr/bin/env Rscript
#
# gam_gaussian_probe.R -- capability ladder rung L1
# (docs/PLAN_mgcv_capability_ladder.md slice 1).
#
# WHAT THIS PROBES
# ------------------
# gaussian(identity) -- the simplest family in mgcv, and until 2026-09-19 absent
# from this engine's `_FAMILY_LINKS` entirely. Fit at a FIXED, externally-supplied
# sp for every block, on the SAME three-term design gam_multiterm_probe.R already
# uses:
#
#   y ~ s(AttdAge, k = 13, bs = "cr")                          # reference age
#     + s(AttdAge, by = StudyYear_C, k = 13, bs = "cr")        # the MI term
#     + ti(AttdAge, PolYear, k = c(13, 6), bs = "cr")          # age x duration
#   family = gaussian(link = "identity")                       # <- the ONLY change
#
# WHY THE SAME DESIGN AS THE MULTI-TERM PROBE, DELIBERATELY
# -----------------------------------------------------------
# Every basis in it -- cr, cr with a numeric `by`, ti -- is already tier-3
# verified (ADR-194, ADR-200, ADR-205), and the design assembly itself is
# verified (ADR-208). So the family is the ONLY unverified thing in this
# comparison: a disagreement here cannot be a basis or an assembly defect,
# because those are held fixed against an already-measured case. Introducing a
# new design at the same time as a new family would confound the two.
#
# WHY FIXED sp, AND WHY THAT IS NOT A SHORTCUT
# ----------------------------------------------
# Gaussian ESTIMATES its scale (`dispersion_fixed=False`), and
# gam_reml.reml_score_general raises on a free scale -- the blocker
# PLAN_mgcv_capability_ladder.md Section 2.2 names, cleared by rung L5 at slice 3.
#
# But note WHY fixed sp is nonetheless a complete measurement of this rung: at
# fixed sp the Gaussian fit is ordinary PENALIZED LEAST SQUARES,
# (X'WX + S)^-1 X'Wz, and the scale parameter does not enter it at all. The scale
# is needed to CHOOSE sp (the REML criterion), not to fit at a given one. So this
# probe measures the whole of what L1 claims -- the family's IRLS recursion and
# its interaction with the penalty -- and the part it cannot reach is precisely
# the part L5 owns. Slice 1's acceptance says "fixed sp only" for that reason,
# not as a hedge.
#
# THE eta OFFSET TRAP (carried constraint 4)
# --------------------------------------------
# predict(m, type = "link") DROPS an offset supplied as a gam() argument, which
# produced one false 1.9751-against-2e-2 reading earlier in this epic. This model
# carries NO offset, so the two agree -- but the probe reads m$linear.predictors
# regardless and exports `offset_gap` so the tripwire is armed if anyone later
# adds an offset to this recipe. A zero there is a measured fact, not an
# assumption.
#
# INDEPENDENCE (ADR-193)
# -------------------------
# The Python side (polaris_re.analytics.gam_gaussian_conformance) assembles its
# own design from the already-verified basis producers and fits with
# gam_fit.penalized_irls_general at the SAME supplied sp, reading only the shared
# recipe this script exports -- never this script's eta, coef or edf. Both sides
# are producers of the compared quantity, and neither is the reference alone, so
# the quantities are INDEPENDENT rather than REFERENCE_INTERNAL (ADR-228).
#
# REQUIREMENTS: R with mgcv and jsonlite.
# USAGE:  Rscript scripts/gam_gaussian_probe.R [output.json]
# EXIT STATUS: 0 on a completed run, 1 on any R-side error.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_gaussian_probe.json"
  set.seed(20260919) # ADR-074: pinned, never the wall clock.

  n <- 900
  # PLAN_mgcv_parity_engine.md Section 1's own target-formula knot vectors --
  # the literal knots, the same ones every cr/ti case in this epic has used.
  age_knots <- c(1, 2, 4, 7, 14, 18, 24, 35, 50, 70, 85, 90, 95)
  year_knots <- c(1, 2, 3, 5, 10, 21)

  AttdAge <- runif(n, 1, 95)
  PolYear <- runif(n, 1, 21)
  StudyYear_C <- runif(n, -5, 5)

  # A synthetic "true" surface. Neither side reads this function; both read only
  # the resulting y. Gaussian noise on a continuous response -- the natural
  # response for this family, rather than a count or proportion forced into it.
  mu_true <- 2.5 + 0.03 * AttdAge - 0.02 * PolYear +
    0.01 * StudyYear_C * (AttdAge - 50) / 50 +
    0.15 * sin(AttdAge / 10) * cos(PolYear / 3)
  y <- mu_true + rnorm(n, sd = 0.25)

  df <- data.frame(
    AttdAge = AttdAge, PolYear = PolYear,
    StudyYear_C = StudyYear_C, y = y
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
    data = df, family = gaussian(link = "identity"),
    knots = knots_arg, sp = sp_fixed
  )

  # Carried constraint 4: read linear.predictors, never predict(type="link").
  eta <- as.numeric(m$linear.predictors)
  eta_predict <- as.numeric(predict(m, type = "link"))
  offset_gap <- max(abs(eta - eta_predict))

  out <- list(
    schema_version = 1L,
    n = n,
    AttdAge = AttdAge, PolYear = PolYear, StudyYear_C = StudyYear_C,
    y = y,
    age_knots = age_knots, year_knots = year_knots,
    sp = sp_fixed,
    mgcv_version = as.character(packageVersion("mgcv")),
    r_version = R.version.string,
    eta = eta,
    edf_total = as.numeric(sum(m$edf)),
    # The tripwire: 0 here says the two eta readings agree on THIS recipe (it
    # carries no offset). A non-zero would mean an offset had been added and
    # predict() was dropping it -- the epic's own 1.9751 false reading.
    offset_gap = offset_gap,
    # Diagnostic only, never compared (PLAN Anchor 2: mgcv reparameterises, so
    # coef is basis-dependent and eta is not).
    coef = as.numeric(coef(m)),
    edf_per_smooth = as.numeric(m$edf1),
    scale_estimated = isTRUE(m$scale.estimated),
    scale = as.numeric(m$scale),
    converged = isTRUE(m$converged)
  )
  jsonlite::write_json(
    out, out_path,
    digits = NA, auto_unbox = TRUE, null = "null", matrix = "rowmajor"
  )
  cat(sprintf(
    "Wrote %s -- n=%d, mgcv %s, edf_total=%.6f, offset_gap=%.3e\n",
    out_path, n, as.character(packageVersion("mgcv")),
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
    message("gam_gaussian_probe.R FAILED: ", conditionMessage(e))
    1L
  }
)
quit(status = status)
