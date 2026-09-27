#!/usr/bin/env Rscript
#
# gam_parametric_free_sp_probe.R -- capability ladder rung L4 (unpenalized
# parametric block), Stage B, FREE sp. (docs/PLAN_mgcv_capability_ladder.md
# slice 5.)
#
# Same model as gam_parametric_probe.R (module docstring there for the full
# rationale), but mgcv selects the smooth's own sp itself via method="REML"
# rather than being handed one. gaussian(identity) throughout (ladder rung L5,
# ADR-231, already closed the free-scale blocker).
#
# REQUIREMENTS: R with mgcv and jsonlite.
# USAGE:  Rscript scripts/gam_parametric_free_sp_probe.R [output.json]
# EXIT STATUS: 0 on a completed run, 1 on any R-side error.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_parametric_free_sp_probe.json"
  set.seed(20260927) # ADR-074: pinned, never the wall clock -- SAME seed as the
  # fixed-sp probe, so the two probes fit the identical dataset and differ
  # only in whether sp is supplied or selected.

  n <- 900
  age_knots <- c(1, 2, 4, 7, 14, 18, 24, 35, 50, 70, 85, 90, 95)
  face_levels <- c("Band1", "Band2", "Band3")
  smoke_levels <- c("N", "Y")

  FaceSize <- factor(sample(face_levels, n, replace = TRUE), levels = face_levels)
  Smoke <- factor(sample(smoke_levels, n, replace = TRUE), levels = smoke_levels)
  AttdAge <- runif(n, 1, 95)

  face_effect <- setNames(c(0.0, 0.6, -0.4), face_levels)
  smoke_effect <- setNames(c(0.0, 0.9), smoke_levels)
  interaction_effect <- outer(face_effect, smoke_effect, "+") * 0
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

  m <- mgcv::gam(
    y ~ FaceSize + Smoke + FaceSize:Smoke + s(AttdAge, k = 13, bs = "cr"),
    data = df, family = gaussian(link = "identity"),
    knots = knots_arg, method = "REML"
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
    mgcv_version = as.character(packageVersion("mgcv")),
    r_version = R.version.string,
    eta = eta,
    # I(): only one penalized block / one smooth term, so both of these are
    # length 1 -- jsonlite's auto_unbox would otherwise collapse them to bare
    # scalars (the same trap ADR-191 documented for a single-penalty `rank`).
    sp = I(as.numeric(m$sp)),
    edf_total = as.numeric(sum(m$edf)),
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
    "Wrote %s -- n=%d, mgcv %s, sp=%.6f, edf_total=%.6f, offset_gap=%.3e\n",
    out_path, n, as.character(packageVersion("mgcv")),
    m$sp, sum(m$edf), offset_gap
  ))
  invisible(NULL)
}

status <- tryCatch(
  {
    main(commandArgs(trailingOnly = TRUE))
    0L
  },
  error = function(e) {
    message("gam_parametric_free_sp_probe.R FAILED: ", conditionMessage(e))
    1L
  }
)
quit(status = status)
