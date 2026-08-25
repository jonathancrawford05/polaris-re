#!/usr/bin/env Rscript
#
# gam_multiterm_free_sp_probe.R -- mgcv-parity engine, PLAN slice 5b
# (docs/WORK_ORDER_multi_term_assembly.md).
#
# WHAT THIS PROBES
# ------------------
# The same three-term formula gam_multiterm_probe.R fits (ADR-206), but at
# FREE sp -- mgcv chooses its own smoothing parameters via method="REML",
# rather than being handed a fixed sp_fixed. This is the work order's own
# "genuinely new measurement": ADR-206 compared at fixed sp, so Polaris's own
# lambda selection (gam_reml_optimize.select_lambdas_continuous) has never
# been exercised on a multi-term (N=4-block) design before this probe.
#
#   y ~ s(AttdAge, k = 13, bs = "cr")                          # reference age
#     + s(AttdAge, by = StudyYear_C, k = 13, bs = "cr")        # the MI term
#     + ti(AttdAge, PolYear, k = c(13, 6), bs = "cr")          # age x duration
#   family = binomial(link = "cloglog"), weights = ExposCnt    # Anchor 5, absolute
#   method = "REML"                                            # free sp
#
# THE ASYMMETRY THE WORK ORDER NAMES (Sec. 3)
# ----------------------------------------------
# In gam_multiterm_probe.R, sp was a SHARED INPUT: both sides fit at the same
# externally-supplied sp_fixed. Here, sp is a COMPARED QUANTITY: each side
# selects its own smoothing parameters independently, from the same criterion
# (Wood 2011's REML score, already verified INDEPENDENT at fixed sp by ADR-196/
# ADR-197, and now at free sp on 2-block designs by ADR-199). This script's
# JSON therefore carries NO "sp" input field -- only the recipe needed to POSE
# the regression problem (AttdAge, PolYear, StudyYear_C, ExposCnt, y, knots).
# mgcv's own selected sp (m$sp) is exported for comparison, not supplied.
#
# WHY THE SAME KNOTS, WHY A DIFFERENT SEED
# -------------------------------------------
# Same target-formula knot vectors as every other slice-5 case (PLAN Section
# 1) -- the literal knots, not a stand-in. A different seed from
# gam_multiterm_probe.R's 20260824, so this is a genuinely new draw rather
# than the fixed-sp case's data reused under a different fit (ADR-074: pinned,
# never the wall clock).
#
# WHY THE COMPARISON IS ON eta/sp/edf, NEVER coef (Anchor 2)
# ----------------------------------------------------------
# Same reasoning as every prior slice-5 probe: mgcv reparameterises
# internally, so coef is basis-dependent and is reported here for diagnostic
# reading only, never compared.
#
# PER-TERM EDF, READ POSITIONALLY, NOT BY LABEL
# ------------------------------------------------
# summary(m)$s.table has one row per SMOOTH TERM (3 here -- ti()'s two
# penalties collapse to one row, matching gam_model._per_term_edf's own
# per-term aggregation), in formula order. Exported as a plain array in that
# order rather than keyed by mgcv's own row-label text, which need not match
# Polaris's TermSpec.label strings and is not itself a quantity under test.
#
# REQUIREMENTS: R with mgcv and jsonlite.
# USAGE:  Rscript scripts/gam_multiterm_free_sp_probe.R [output.json]
# EXIT STATUS: 0 on a completed run, 1 on any R-side error.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_multiterm_free_sp_probe.json"
  set.seed(20260825) # ADR-074: pinned, never the wall clock. Distinct from
  # gam_multiterm_probe.R's 20260824 -- a genuinely new draw, not data reuse.

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
    knots = knots_arg, method = "REML"
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
    sp = as.numeric(m$sp), # mgcv's OWN free-sp selection -- a compared
    # quantity here, not a shared input (see the header note on the asymmetry)
    edf_total = sum(m$edf),
    term_edf = term_edf, # one per SMOOTH term, formula order (3 entries)
    converged = isTRUE(m$converged)
  )
  jsonlite::write_json(
    out, out_path,
    digits = NA, auto_unbox = TRUE, null = "null", matrix = "rowmajor"
  )
  cat(sprintf(
    "Wrote %s -- n=%d, mgcv %s, sp=[%s]\n", out_path, n,
    as.character(packageVersion("mgcv")), paste(signif(m$sp, 4), collapse = ", ")
  ))
  invisible(NULL)
}

status <- tryCatch(
  {
    main(commandArgs(trailingOnly = TRUE))
    0L
  },
  error = function(e) {
    message("gam_multiterm_free_sp_probe.R FAILED: ", conditionMessage(e))
    1L
  }
)
quit(status = status)
