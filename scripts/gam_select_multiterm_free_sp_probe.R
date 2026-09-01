#!/usr/bin/env Rscript
#
# gam_select_multiterm_free_sp_probe.R -- mgcv-parity engine, PLAN slice 7b
# (docs/PLAN_mgcv_parity_engine.md, docs/CONTINUATION_mgcv_parity_engine.md).
#
# WHAT THIS PROBES
# ------------------
# The SAME three-term formula gam_select_multiterm_probe.R fits under
# select=TRUE (slice 7, ADR-217), but at FREE sp -- mgcv chooses its own 7
# smoothing parameters via method="REML", rather than being handed a fixed
# sp_fixed:
#
#   y ~ s(AttdAge, k = 13, bs = "cr")                          # reference age
#     + s(AttdAge, by = StudyYear_C, k = 13, bs = "cr")        # the MI term
#     + ti(AttdAge, PolYear, k = c(13, 6), bs = "cr")          # age x duration
#   family = binomial(link = "cloglog"), weights = ExposCnt    # Anchor 5, absolute
#   select = TRUE, method = "REML"                             # free sp, 7 blocks
#
# This is slice 7's own registered remaining scope (ADR-217): slice 7 only
# ever compared eta at a FIXED sp under select=TRUE (gam_select_multiterm_
# probe.R) or free sp WITHOUT select=TRUE (gam_multiterm_free_sp_probe.R,
# slice 5b). Neither exercised free selection on the doubled (7-block)
# structure select=TRUE produces -- this probe is the first to combine both.
#
# THE ASYMMETRY THE WORK ORDER NAMES (same as gam_multiterm_free_sp_probe.R
# Sec. 3, restated here for the select=TRUE case)
# ----------------------------------------------
# sp is a COMPARED QUANTITY, not a shared input: both sides select all 7
# smoothing parameters independently, from the same criterion (Wood 2011's
# REML score, INDEPENDENT-verified at fixed sp under select=TRUE by ADR-217,
# and at free sp on the non-select N=4 structure by ADR-208/210/211/212).
# This script's JSON carries NO "sp" input field -- only the recipe needed to
# POSE the regression problem. mgcv's own selected sp (m$sp, 7 entries) is
# exported for comparison, not supplied.
#
# WHY THE SAME KNOTS, WHY A DIFFERENT SEED
# -------------------------------------------
# Same target-formula knot vectors as every other slice-5/7 case (PLAN
# Section 1) -- the literal knots, not a stand-in. A distinct seed from both
# gam_select_multiterm_probe.R's 20260901 and gam_multiterm_free_sp_probe.R's
# 20260825, so this is a genuinely new draw (ADR-074: pinned, never the wall
# clock).
#
# WHY THE COMPARISON IS ON eta/sp/edf, NEVER coef (Anchor 2)
# ----------------------------------------------------------
# Same reasoning as every prior slice-5/7 probe: mgcv reparameterises
# internally, so coef is basis-dependent and is reported here for diagnostic
# reading only, never compared.
#
# PER-TERM EDF, READ POSITIONALLY, NOT BY LABEL
# ------------------------------------------------
# summary(m)$s.table has one row per SMOOTH TERM (3 here -- select=TRUE adds
# an extra penalty block per term, not an extra row; ti()'s two-plus-one
# penalties still collapse to one row), in formula order -- same convention
# gam_multiterm_free_sp_probe.R and gam_model._per_term_edf already use.
#
# REQUIREMENTS: R with mgcv and jsonlite.
# USAGE:  Rscript scripts/gam_select_multiterm_free_sp_probe.R [output.json]
# EXIT STATUS: 0 on a completed run, 1 on any R-side error.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_select_multiterm_free_sp_probe.json"
  set.seed(20260902) # ADR-074: pinned, never the wall clock. Distinct from
  # gam_select_multiterm_probe.R's 20260901 and gam_multiterm_free_sp_probe.R's
  # 20260825 -- a genuinely new draw, not data reuse.

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

  m <- mgcv::gam(
    y ~ s(AttdAge, k = 13, bs = "cr") +
      s(AttdAge, by = StudyYear_C, k = 13, bs = "cr") +
      ti(AttdAge, PolYear, k = c(13, 6), bs = "cr"),
    data = df, family = binomial(link = "cloglog"), weights = ExposCnt,
    knots = knots_arg, select = TRUE, method = "REML"
  )

  eta <- as.numeric(predict(m, type = "link"))
  s_table <- summary(m)$s.table
  term_edf <- as.numeric(s_table[, "edf"])

  out <- list(
    schema_version = 1L,
    n = n,
    AttdAge = AttdAge, PolYear = PolYear, StudyYear_C = StudyYear_C,
    ExposCnt = as.numeric(ExposCnt), y = y,
    age_knots = age_knots, year_knots = year_knots,
    mgcv_version = as.character(packageVersion("mgcv")),
    r_version = R.version.string,
    eta = eta,
    coef = as.numeric(coef(m)), # diagnostic only, never compared (Anchor 2)
    sp = as.numeric(m$sp), # mgcv's OWN free-sp selection under select=TRUE --
    # a compared quantity here, not a shared input (see the header note on
    # the asymmetry). 7 entries: [s(AttdAge) existing, null;
    # s(AttdAge,by=StudyYear_C) existing, null; ti(...) existing x2, null].
    edf_total = sum(m$edf),
    term_edf = term_edf, # one per SMOOTH term, formula order (3 entries)
    converged = isTRUE(m$converged)
  )
  jsonlite::write_json(
    out, out_path,
    digits = NA, auto_unbox = TRUE, null = "null", matrix = "rowmajor"
  )
  cat(sprintf(
    "Wrote %s -- n=%d, mgcv %s, n(sp)=%d, sp=[%s]\n", out_path, n,
    as.character(packageVersion("mgcv")), length(m$sp),
    paste(signif(m$sp, 4), collapse = ", ")
  ))
  invisible(NULL)
}

status <- tryCatch(
  {
    main(commandArgs(trailingOnly = TRUE))
    0L
  },
  error = function(e) {
    message("gam_select_multiterm_free_sp_probe.R FAILED: ", conditionMessage(e))
    1L
  }
)
quit(status = status)
