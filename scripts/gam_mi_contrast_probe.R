# Anchor 2's PRIMARY metric: the MI contrast, measured for the first time.
#
# PLAN Anchor 2 names `eta(age, year+1) - eta(age, year)` the primary acceptance
# criterion -- "the number that reaches a reader" -- and it had never been
# measured (zero occurrences in docs/CONFORMANCE_LEDGER.md as of 2026-08-25).
#
# ADR-206 scoped it out on the grounds that it needs a PINNED PREDICTION GRID:
# evaluating the bases at covariate values away from the training rows, which
# needs the identifiability-constraint transform re-applied at unseen x, and
# gam_basis_cr.py marks extrapolation beyond the knot range unverified. That
# reasoning is correct FOR A GRID.
#
# But the metric itself does not need one. StudyYear_C enters this model ONLY
# through s(AttdAge, by = StudyYear_C), whose contribution is linear in the by
# variable: contribution_i = StudyYear_C_i * f(AttdAge_i). So
#
#   eta(age, sy + 1) - eta(age, sy) = (sy+1)*f(age) - sy*f(age) = f(age)
#
# exactly, for any sy -- the contrast CANCELS the intercept, the reference age
# smooth and ti() (Anchor 2's own stated reason for preferring it), and collapses
# to the by-term's own smooth. On the training rows that is
# predict(type="terms")[, by-term] / StudyYear_C, needing no new machinery and no
# extrapolation.
#
# This measures the contrast ON THE TRAINING DESIGN, not on a pinned grid. That
# is a partial delivery of Anchor 2's primary metric and must be reported as one.
#
# sp is a SHARED INPUT here (supplied to both sides), exactly as ADR-206's
# MULTITERM_CLAIM had it, so this isolates the metric from the separate free-sp
# selection gap (ADR-208). The contrast itself is INDEPENDENT: each side computes
# it from its own fit.
#
# Usage: Rscript scripts/gam_mi_contrast_probe.R [output.json]
# REQUIREMENTS: R with mgcv and jsonlite. EXIT: 0 on success, 1 on R-side error.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_mi_contrast_probe.json"

  set.seed(20260825) # SAME design as the free-sp and sp-delta probes.
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

  # The SHARED sp -- an input to both sides, not a compared quantity (ADR-206's
  # arrangement). Pinned, not selected, so this measurement is independent of the
  # free-sp selection gap ADR-208 reports.
  sp_fixed <- c(1e4, 1e4, 1e3, 1e3)

  m <- mgcv::gam(form,
    data = df, family = binomial(link = "cloglog"), weights = ExposCnt,
    knots = knots_arg, sp = sp_fixed, method = "REML"
  )

  terms_mat <- predict(m, type = "terms")
  by_col <- grep("StudyYear_C", colnames(terms_mat), fixed = TRUE)
  if (length(by_col) != 1L) {
    stop(sprintf(
      "expected exactly one by-term column, got %d: %s",
      length(by_col), paste(colnames(terms_mat), collapse = ", ")
    ))
  }
  # contribution = StudyYear_C * f(age)  =>  f(age) = contribution / StudyYear_C.
  # The contrast is f(age), independent of the StudyYear_C value it is read at.
  mi_contrast <- as.numeric(terms_mat[, by_col]) / StudyYear_C

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
    sp_fixed = sp_fixed,
    by_term_column = colnames(terms_mat)[by_col],
    mi_contrast = mi_contrast,
    eta = as.numeric(predict(m, type = "link"))
  )
  write_json(out, out_path, digits = 17, auto_unbox = TRUE)
  cat(sprintf(
    "Wrote %s -- n=%d, mgcv %s, by-term column '%s'\n",
    out_path, n, as.character(packageVersion("mgcv")), colnames(terms_mat)[by_col]
  ))
}

main(commandArgs(trailingOnly = TRUE))
