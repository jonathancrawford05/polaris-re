#!/usr/bin/env Rscript
#
# gam_multiterm_sp_delta_probe.R -- PR #212 review [P1], mgcv-parity engine
# slice 5b follow-up (ADR-208 amendment).
#
# WHAT THIS PROBES
# ------------------
# ADR-208's original diagnosis of the free-sp N=4 disagreement used ONLY our
# own (already-verified) reml_score_general to compare mgcv's own selected
# point against Python's own selected point -- and concluded "not evidence of
# a formula gap" because our criterion scored Python's point lower. Review
# [P1] pointed out that inference cannot discriminate two explanations:
#
#   (a) same criterion, flat plateau, mgcv's own outer optimiser stops short
#       of its own true minimum -- a finding about mgcv's convergence, not a
#       criterion defect;
#   (b) our criterion differs from mgcv's in an sp-DEPENDENT way that the
#       existing fixed-sp verification (ADR-196/197, 2 disjoint blocks) never
#       had the structure to detect -- a real, reopened formula gap, scoped
#       to this N=4 / ti-sharing-a-span structure specifically.
#
# The discriminating measurement mgcv's own gcv.ubre at BOTH points:
#
#   delta_mgcv = mgcv_score(mgcv_own_point) - mgcv_score(python_own_point)
#
# compared against the already-measured delta_ours (same two points, OUR
# criterion). Same SIGN and rough magnitude -> (a). Opposite sign or very
# different magnitude -> (b): the two criteria disagree about which of the
# two points is better, which is a criterion question, not an optimiser one.
#
# WHY THIS IS A SEPARATE, UNGATED SCRIPT
# ------------------------------------------
# Reading mgcv's own score at Python's own selected point makes this read the
# OTHER side's output by construction -- the same reason ADR-190's
# ks_formula_probe.R and ADR-201/202's gam_deriv_probe.R / gam_vc_probe.R are
# diagnostic-only, never part of the committed INDEPENDENT comparator
# (ROUTINE_MGCV_PARITY.md SETUP step 2: "IF TIER 3 CANNOT MEASURE YOUR
# QUANTITY, ADD A PROBE -- DO NOT FALL BACK TO TIER 1"). Unlike those two
# probes, this one also needs Python's OWN selection as an input, which the
# two-job CI split (R job produces a reference, Python job consumes it) has
# no path for without a third stage. So this script takes Python's selected
# sp as a literal, documented, hand-supplied argument tied to one specific
# measurement -- the same convention gam_reml_probe.R's three fixed (sp1,sp2)
# points already use (ADR-074: pinned values, never derived at runttime).
#
# WHY THE SAME RECIPE, REPRODUCED HERE RATHER THAN READ FROM A FILE
# ----------------------------------------------------------------------
# Reproduces gam_multiterm_free_sp_probe.R's exact recipe (same seed,
# 20260825) so both readings -- mgcv's own free-sp fit and the fixed-sp
# refit at Python's point -- share one design, matching what the original
# ADR-208 diagnostic did on the Python side.
#
# USAGE
# -------
#   Rscript scripts/gam_multiterm_sp_delta_probe.R <p1> <p2> <p3> <p4> [output.json]
#
# where p1..p4 are Python's own selected log10(lambda) values, in the SAME
# block order as scripts/gam_multiterm_free_sp_probe.R's `sp` field: [s(AttdAge),
# s(AttdAge,by=StudyYear_C), ti()#1, ti()#2]. Read off a
# gam_model_conformance.compare_free_sp_case run (the tier this script's
# reading should be labelled with is whichever tier produced those four
# numbers -- this script's own R/mgcv version, printed in the output, is a
# SEPARATE fact from where the sp values came from).
#
# REQUIREMENTS: R with mgcv and jsonlite.
# EXIT STATUS: 0 on a completed run, 1 on any R-side error.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

main <- function(argv) {
  if (length(argv) < 4) {
    stop("usage: gam_multiterm_sp_delta_probe.R <p1> <p2> <p3> <p4> [output.json]")
  }
  python_log10_sp <- as.numeric(argv[1:4])
  out_path <- if (length(argv) >= 5) argv[[5]] else "gam_multiterm_sp_delta_probe.json"

  set.seed(20260825) # SAME seed as gam_multiterm_free_sp_probe.R -- one shared design.
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

  # mgcv's own free-sp optimum -- its own score at its own point.
  m_free <- mgcv::gam(form,
    data = df, family = binomial(link = "cloglog"), weights = ExposCnt,
    knots = knots_arg, method = "REML"
  )
  mgcv_pt_sp <- as.numeric(m_free$sp)
  score_at_mgcv_pt <- m_free$gcv.ubre

  # mgcv's own score AT Python's own selected point: a FIXED-sp fit (no
  # optimisation runs -- sp is fully supplied), reading gcv.ubre off it.
  python_pt_sp <- 10^python_log10_sp
  m_fixed <- mgcv::gam(form,
    data = df, family = binomial(link = "cloglog"), weights = ExposCnt,
    knots = knots_arg, sp = python_pt_sp, method = "REML"
  )
  score_at_python_pt <- m_fixed$gcv.ubre

  out <- list(
    schema_version = 1L,
    mgcv_version = as.character(packageVersion("mgcv")),
    r_version = R.version.string,
    python_log10_sp_input = python_log10_sp,
    mgcv_pt_sp = mgcv_pt_sp,
    python_pt_sp = python_pt_sp,
    score_at_mgcv_pt = score_at_mgcv_pt,
    score_at_python_pt = score_at_python_pt,
    delta_mgcv = score_at_mgcv_pt - score_at_python_pt
  )
  jsonlite::write_json(out, out_path, digits = NA, auto_unbox = TRUE, null = "null")
  cat(sprintf(
    "Wrote %s -- delta_mgcv (mgcv_pt - python_pt, mgcv's own score) = %.6f\n",
    out_path, out$delta_mgcv
  ))
  invisible(NULL)
}

status <- tryCatch(
  {
    main(commandArgs(trailingOnly = TRUE))
    0L
  },
  error = function(e) {
    message("gam_multiterm_sp_delta_probe.R FAILED: ", conditionMessage(e))
    1L
  }
)
quit(status = status)
