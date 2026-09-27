#!/usr/bin/env Rscript
#
# gam_parametric_probe.R -- capability ladder rung L4 (unpenalized parametric
# block), Stage B, FIXED sp. (docs/PLAN_mgcv_capability_ladder.md slice 5.)
#
# WHAT THIS PROBES
# ------------------
# A model pairing the target formula's own opening parametric terms with the
# already-verified `cr` smooth (on AttdAge), fit at a FIXED, externally
# supplied sp for the smooth's own (only) penalty block:
#
#   y ~ FaceSize + Smoke + FaceSize:Smoke + s(AttdAge, k = 13, bs = "cr")
#   family = gaussian(link = "identity")
#
# FaceSize/Smoke are DELIBERATELY unrelated to AttdAge (independently drawn
# factors, no covariate shared with the smooth) so the parametric block and
# the smooth cannot be confounded with each other.
#
# WHY gaussian(identity)
# ------------------------
# Ladder rung L5 (ADR-231) already closed reml_score_general's free-scale
# branch, so this slice needs no family switch between the fixed- and
# free-sp probes -- same reasoning ladder rung L3's own by-factor probes
# already carry.
#
# THE eta OFFSET TRAP (carried constraint 4)
# --------------------------------------------
# predict(m, type = "link") DROPS an argument-supplied offset. This model
# carries none, so m$linear.predictors and predict(type="link") must agree --
# both are read and their gap exported as a tripwire (never gated).
#
# INDEPENDENCE (ADR-193)
# -------------------------
# The Python side (polaris_re.analytics.gam_parametric_conformance) assembles
# its own design from the already-verified `cr` producer plus the NEW
# unpenalized parametric-block producer
# (polaris_re.analytics.gam_basis_parametric.parametric_design) and fits with
# gam_fit.penalized_irls_general at the SAME supplied sp, reading only the
# shared recipe this script exports -- never this script's eta, coef or edf.
#
# REQUIREMENTS: R with mgcv and jsonlite.
# USAGE:  Rscript scripts/gam_parametric_probe.R [output.json]
# EXIT STATUS: 0 on a completed run, 1 on any R-side error.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_parametric_probe.json"
  set.seed(20260927) # ADR-074: pinned, never the wall clock.

  n <- 900
  age_knots <- c(1, 2, 4, 7, 14, 18, 24, 35, 50, 70, 85, 90, 95)
  face_levels <- c("Band1", "Band2", "Band3")
  smoke_levels <- c("N", "Y")

  FaceSize <- factor(sample(face_levels, n, replace = TRUE), levels = face_levels)
  Smoke <- factor(sample(smoke_levels, n, replace = TRUE), levels = smoke_levels)
  AttdAge <- runif(n, 1, 95)

  # Genuine per-level effects on the mean, so the parametric block's own
  # coefficients (and edf, though every parametric coefficient carries edf=1
  # regardless of signal) have something real to fit against -- the same
  # "suspicion, not just a check" discipline ladder slices 1-4 each carried
  # for their own near-exact agreements.
  face_effect <- setNames(c(0.0, 0.6, -0.4), face_levels)
  smoke_effect <- setNames(c(0.0, 0.9), smoke_levels)
  interaction_effect <- outer(face_effect, smoke_effect, "+") * 0 # placeholder, overwritten below
  interaction_effect["Band2", "Y"] <- 0.5
  interaction_effect["Band3", "Y"] <- -0.3

  mu_true <- 1.2 +
    face_effect[as.character(FaceSize)] +
    smoke_effect[as.character(Smoke)] +
    mapply(function(f, s) interaction_effect[f, s], as.character(FaceSize), as.character(Smoke)) +
    0.4 * sin(AttdAge / 20)
  y <- as.numeric(mu_true) + rnorm(n, sd = 0.3)

  df <- data.frame(FaceSize = FaceSize, Smoke = Smoke, AttdAge = AttdAge, y = y)
  knots_arg <- list(AttdAge = age_knots)

  # One penalty block: the cr smooth's own. FaceSize/Smoke/FaceSize:Smoke are
  # unpenalized (module docstring, gam_basis_parametric.py) and contribute
  # none.
  sp_fixed <- c(2.5)

  m <- mgcv::gam(
    y ~ FaceSize + Smoke + FaceSize:Smoke + s(AttdAge, k = 13, bs = "cr"),
    data = df, family = gaussian(link = "identity"),
    knots = knots_arg, sp = sp_fixed
  )

  eta <- as.numeric(m$linear.predictors)
  eta_predict <- as.numeric(predict(m, type = "link"))
  offset_gap <- max(abs(eta - eta_predict))

  out <- list(
    schema_version = 1L,
    n = n,
    face_levels = face_levels,
    smoke_levels = smoke_levels,
    face_group = as.integer(FaceSize) - 1L,
    smoke_group = as.integer(Smoke) - 1L,
    AttdAge = AttdAge,
    y = y,
    age_knots = age_knots,
    # I() forces jsonlite to keep this an array even though it has length 1
    # (auto_unbox would otherwise collapse it to a bare scalar -- the exact
    # trap ADR-191 documented for a single-penalty `rank`).
    sp = I(sp_fixed),
    mgcv_version = as.character(packageVersion("mgcv")),
    r_version = R.version.string,
    eta = eta,
    edf_total = as.numeric(sum(m$edf)),
    # I(): only one smooth term, so this is length 1 -- same auto_unbox trap
    # as `sp` above.
    term_edf = I(as.numeric(summary(m)$s.table[, "edf"])),
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
    message("gam_parametric_probe.R FAILED: ", conditionMessage(e))
    1L
  }
)
quit(status = status)
