# Diagnostic (session-only, tier 1): is the criterion discrepancy present at
# FIXED sp, or only under free selection?
#
# ADR-208's amendment established that mgcv's own score and ours RANK mgcv's
# free-sp point and Python's free-sp point in opposite order. That is consistent
# with two different things:
#   (b1) the two criteria are genuinely different functions of sp, or
#   (b2) they are the same function up to an additive constant (identical argmin)
#        and something else produced the ranking flip.
#
# The discriminator: evaluate BOTH criteria at the SAME fixed sp, at several
# well-separated points, and look at the DIFFERENCE ours - mgcv across points.
#   constant across sp  -> same function up to a constant -> same argmin -> the
#                          criterion is NOT the defect
#   varies with sp      -> a genuine sp-dependent criterion discrepancy
#
# This R side is mgcv's own independent fit and score/deviance at a
# caller-supplied fixed sp -- it never reads Python's score, so pairing it
# with gam_reml_optimize_conformance.compare_fixed_sp_multiterm_case (which
# never reads mgcv's eta/coef either) is INDEPENDENT parity evidence, the
# same mechanical shape as gam_reml_conformance.score_reml_point /
# REML_SCORE_CLAIM (PR #215 review [P1-1]; an earlier revision of this
# comment called it DIAGNOSTIC, written while reml_score_general was still
# the suspect rather than the verified criterion -- ADR-210 fixed it).
#
# Data generation is byte-identical to scripts/gam_multiterm_free_sp_probe.R and
# scripts/gam_multiterm_sp_delta_probe.R (same seed, same n, same knots), so the
# design is the one those measurements were taken on.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "fixed_sp_score_probe.json"

  set.seed(20260825) # SAME seed as the two committed probes -- one shared design.
  n <- 900
  age_knots <- c(1, 2, 4, 7, 14, 18, 24, 35, 50, 70, 85, 90, 95)
  year_knots <- c(1, 2, 3, 5, 10, 21)
  AttdAge <- runif(n, 1, 95)
  PolYear <- runif(n, 1, 21)
  StudyYear_C <- runif(n, -5, 5)
  ExposCnt <- round(runif(n, 50, 500))
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
  form <- y ~ s(AttdAge, k = 13, bs = "cr") +
    s(AttdAge, by = StudyYear_C, k = 13, bs = "cr") +
    ti(AttdAge, PolYear, k = c(13, 6), bs = "cr")

  # mgcv's own free-sp optimum, for reference and as one of the evaluation points.
  m_free <- mgcv::gam(form,
    data = df, family = binomial(link = "cloglog"), weights = ExposCnt,
    knots = knots_arg, method = "REML"
  )
  mgcv_opt_log10 <- log10(as.numeric(m_free$sp))

  # The evaluation grid: both sides' own free-sp optima, plus a deliberate
  # spread so that any sp-dependence in the difference has room to show.
  python_opt_log10 <- c(6.753, 9.096, 3.099, 3.054) # ADR-208 tier-1 reading
  points <- list(
    mgcv_opt          = mgcv_opt_log10,
    python_opt        = python_opt_log10,
    flat_2            = c(2, 2, 2, 2),
    flat_4            = c(4, 4, 4, 4),
    flat_6            = c(6, 6, 6, 6),
    mixed_lo_hi       = c(3, 8, 2, 5),
    mixed_hi_lo       = c(8, 3, 5, 2),
    mid               = c(5, 5, 3, 3)
  )

  rows <- lapply(names(points), function(nm) {
    lg <- as.numeric(points[[nm]])
    m <- mgcv::gam(form,
      data = df, family = binomial(link = "cloglog"), weights = ExposCnt,
      knots = knots_arg, sp = 10^lg, method = "REML"
    )
    list(
      name = nm, log10_sp = lg, mgcv_score = as.numeric(m$gcv.ubre),
      mgcv_deviance = as.numeric(m$deviance)
    )
  })

  out <- list(
    schema_version = 1L,
    mgcv_version = as.character(packageVersion("mgcv")),
    r_version = R.version.string,
    n = n,
    age_knots = age_knots,
    year_knots = year_knots,
    AttdAge = AttdAge,
    PolYear = PolYear,
    StudyYear_C = StudyYear_C,
    ExposCnt = ExposCnt,
    y = y,
    mgcv_opt_log10_sp = mgcv_opt_log10,
    points = rows
  )
  write_json(out, out_path, digits = 17, auto_unbox = TRUE)
  cat(sprintf(
    "Wrote %s -- n=%d, mgcv %s, %d evaluation points\n",
    out_path, n, as.character(packageVersion("mgcv")), length(rows)
  ))
}

main(commandArgs(trailingOnly = TRUE))
