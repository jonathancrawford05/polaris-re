#!/usr/bin/env Rscript
#
# gam_select_multiterm_probe.R -- mgcv-parity engine, PLAN slice 7
# (docs/PLAN_mgcv_parity_engine.md, docs/CONTINUATION_mgcv_parity_engine.md).
#
# WHAT THIS PROBES
# ------------------
# Stage B for `select = TRUE`: the SAME three-term multi-term model
# gam_multiterm_probe.R (slice 5, ADR-206) already verified --
#
#   y ~ s(AttdAge, k = 13, bs = "cr")                          # reference age
#     + s(AttdAge, by = StudyYear_C, k = 13, bs = "cr")        # the MI term
#     + ti(AttdAge, PolYear, k = c(13, 6), bs = "cr")          # age x duration
#   family = binomial(link = "cloglog"), weights = ExposCnt    # Anchor 5, absolute
#
# -- fit with `select = TRUE`, at a FIXED, externally-supplied sp for every
# block INCLUDING the extra null-space block `select = TRUE` appends per
# term (gam_select_penalty.R's own measurement: one extra block per term,
# never one per existing penalty). 7 blocks total: [s(AttdAge)'s own 2,
# s(AttdAge,by=StudyYear_C)'s own 2, ti(...)'s own 3 (its existing 2 plus
# its null space, which is of dimension 1 -- see
# scripts/gam_select_penalty_probe.R's own "ti-attdage-polyear" case)].
# Verified once, at tier 1, that mgcv's own `sp=` argument takes this same
# flat, per-smooth-grouped (existing-then-null) ordering under
# `select = TRUE` exactly as it already does without it (structure only,
# ROUTINE_MGCV_PARITY.md step 2 tier 1 -- never a committed value from that
# check).
#
# WHY THIS BUILDS ITS OWN CASE, WITH NO EXCHANGE DEPENDENCY
# -----------------------------------------------------------
# Same reasoning as gam_multiterm_probe.R: a probe for a specific hypothesis
# needs a SHARED recipe both sides fit, not the full ADR-189 exchange.
#
# WHY THE COMPARISON IS ON eta, NEVER coef (Anchor 2)
# -----------------------------------------------------
# Unchanged from gam_multiterm_probe.R's own reasoning -- select=TRUE gives
# mgcv strictly more penalty blocks to reparameterise across, not fewer.
#
# INDEPENDENCE (ADR-193)
# -------------------------
# The Python side (polaris_re.analytics.gam_select_multiterm_conformance)
# assembles its own design via
# polaris_re.analytics.gam_model.assemble_model_design(ModelSpec(..., select=True))
# -- the three ALREADY-INDEPENDENTLY-VERIFIED basis producers (ADR-194,
# ADR-200, ADR-205) plus gam_select_penalty.null_space_penalty (ADR-217,
# itself independently verified against mgcv's own select=TRUE setup path)
# -- and fits with gam_fit.penalized_irls_general at the SAME externally-
# supplied sp. It reads only the shared recipe this script exports, never
# this script's own eta or coef.
#
# REQUIREMENTS: R with mgcv and jsonlite.
# USAGE:  Rscript scripts/gam_select_multiterm_probe.R [output.json]
# EXIT STATUS: 0 on a completed run, 1 on any R-side error.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_select_multiterm_probe.json"
  set.seed(20260901) # ADR-074: pinned, never the wall clock.

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

  # 7 blocks: s(AttdAge) [existing, null], s(AttdAge,by=StudyYear_C)
  # [existing, null], ti(...) [existing#1, existing#2, null].
  sp_fixed <- c(2.0, 5.0, 3.0, 6.0, 1.5, 4.0, 7.0)

  m <- mgcv::gam(
    y ~ s(AttdAge, k = 13, bs = "cr") +
      s(AttdAge, by = StudyYear_C, k = 13, bs = "cr") +
      ti(AttdAge, PolYear, k = c(13, 6), bs = "cr"),
    data = df, family = binomial(link = "cloglog"), weights = ExposCnt,
    knots = knots_arg, select = TRUE, sp = sp_fixed
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
    message("gam_select_multiterm_probe.R FAILED: ", conditionMessage(e))
    1L
  }
)
quit(status = status)
