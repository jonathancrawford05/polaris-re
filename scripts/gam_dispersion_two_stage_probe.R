#!/usr/bin/env Rscript
#
# gam_dispersion_two_stage_probe.R -- capability ladder slice 3c: the exposed
# dispersion estimate, and the optional two-stage Poisson -> fixed-scale
# workflow (docs/PLAN_mgcv_capability_ladder.md slice 3c).
#
# WHAT THIS PROBES  (the IDENTICAL three-term design as slices 3b / 7; own seed)
# ------------------------------------------------------------------------------
#   JOINT   gam(quasipoisson(log), method = "REML")        -- mgcv's own
#           free-sp, free-scale fit. Exports m$scale (mgcv's reported
#           dispersion; gam.control default scale.est = "fletcher") together
#           with the quantities needed to say WHICH estimator that is.
#   STAGE 1 gam(poisson(log),      method = "REML")        -- scale fixed at 1.
#           phi_P = Pearson dispersion of this fit, computed HERE from mgcv's
#           own mu and edf: sum((y - mu)^2 / mu) / (n - sum(edf)).
#   STAGE 2 gam(quasipoisson(log), method = "REML", scale = phi_P)
#           -- mgcv's own chain end to end, supplied its OWN stage-1 number.
#
# The Python side runs the same chain from the shared recipe (data + knots
# only), so the R and Python chains are independent end to end. Nothing in the
# recipe is an mgcv output.
#
# THE eta OFFSET TRAP: read m$linear.predictors, never predict(type="link").
#
# REQUIREMENTS: R with mgcv and jsonlite.
# USAGE:  Rscript scripts/gam_dispersion_two_stage_probe.R [output.json]
# EXIT STATUS: 0 on a completed run, 1 on any R-side error.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

estimators <- function(m, y) {
  mu <- as.numeric(m$fitted.values)
  n <- length(y)
  trA <- sum(m$edf)
  v <- mu                                    # V(mu) = mu for (quasi)poisson
  pearson_stat <- sum((y - mu)^2 / v)
  s_bar <- max(-0.9, mean(1 * (y - mu) / v)) # dvar = 1
  list(
    pearson = pearson_stat / (n - trA),
    fletcher = pearson_stat / (n - trA) / (1 + s_bar),
    deviance = sum(m$deviance) / (n - trA),
    s_bar = s_bar,
    edf_total = trA
  )
}

describe <- function(m, y) {
  list(
    eta = as.numeric(m$linear.predictors),
    offset_gap = max(abs(as.numeric(m$linear.predictors) -
                         as.numeric(predict(m, type = "link")))),
    sp = as.numeric(m$sp),
    edf_total = as.numeric(sum(m$edf)),
    term_edf = as.numeric(summary(m)$s.table[, "edf"]),
    term_labels = I(rownames(summary(m)$s.table)),
    scale = as.numeric(m$scale),
    converged = isTRUE(m$converged),
    estimators = estimators(m, y)
  )
}

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_dispersion_two_stage_probe.json"
  set.seed(20261002)
  n <- 900
  age_knots <- c(1, 2, 4, 7, 14, 18, 24, 35, 50, 70, 85, 90, 95)
  year_knots <- c(1, 2, 3, 5, 10, 21)

  AttdAge <- runif(n, 1, 95)
  PolYear <- runif(n, 1, 21)
  StudyYear_C <- runif(n, -5, 5)
  eta_true <- 1.5 + 0.5 * sin(AttdAge / 12) - 0.02 * PolYear +
    0.08 * StudyYear_C * sin(AttdAge / 15) +
    0.3 * sin(AttdAge / 10) * cos(PolYear / 3)
  y <- as.numeric(rnbinom(n, mu = exp(eta_true), size = 4))

  df <- data.frame(AttdAge = AttdAge, PolYear = PolYear,
                   StudyYear_C = StudyYear_C, y = y)
  knots_arg <- list(AttdAge = age_knots, PolYear = year_knots)
  formula <- y ~ s(AttdAge, k = 13, bs = "cr") +
    s(AttdAge, by = StudyYear_C, k = 13, bs = "cr") +
    ti(AttdAge, PolYear, k = c(13, 6), bs = "cr")

  joint <- mgcv::gam(formula, data = df, family = quasipoisson(link = "log"),
                     knots = knots_arg, method = "REML")
  stage1 <- mgcv::gam(formula, data = df, family = poisson(link = "log"),
                      knots = knots_arg, method = "REML")
  phi_p <- estimators(stage1, y)$pearson
  stage2 <- mgcv::gam(formula, data = df, family = quasipoisson(link = "log"),
                      knots = knots_arg, method = "REML", scale = phi_p)

  out <- list(
    schema_version = 1L,
    n = n,
    AttdAge = AttdAge, PolYear = PolYear, StudyYear_C = StudyYear_C,
    y = y,
    age_knots = age_knots, year_knots = year_knots,
    mgcv_version = as.character(packageVersion("mgcv")),
    r_version = R.version.string,
    joint = describe(joint, y),
    stage1 = describe(stage1, y),
    phi_stage1_pearson = phi_p,
    stage2 = describe(stage2, y)
  )
  jsonlite::write_json(out, out_path, digits = NA, auto_unbox = TRUE,
                       null = "null", matrix = "rowmajor")
  cat(sprintf(
    paste0("Wrote %s -- n=%d, mgcv %s\n  joint: m$scale=%.9f fletcher(R)=%.9f ",
           "pearson(R)=%.9f deviance(R)=%.9f\n  stage1 poisson: phi_P=%.9f\n",
           "  stage2 scale=%.9f edf_total=%.6f (joint %.6f)\n"),
    out_path, n, as.character(packageVersion("mgcv")),
    joint$scale, estimators(joint, y)$fletcher, estimators(joint, y)$pearson,
    estimators(joint, y)$deviance, phi_p, stage2$scale,
    sum(stage2$edf), sum(joint$edf)))
  invisible(NULL)
}

status <- tryCatch({ main(commandArgs(trailingOnly = TRUE)); 0L },
  error = function(e) {
    message("gam_dispersion_two_stage_probe.R FAILED: ", conditionMessage(e))
    1L
  })
quit(status = status)
