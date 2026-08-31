#!/usr/bin/env Rscript
#
# gam_multiterm_sz_probe.R -- mgcv-parity engine, slice 6b
# (docs/PLAN_mgcv_parity_engine.md, docs/CONTINUATION_mgcv_parity_engine.md).
#
# WHAT THIS PROBES
# ------------------
# The epic's first multi-term mgcv-native model containing an `sz` term: a
# reference age smooth plus one of the target formula's own four `sz` terms
# (PLAN Section 1), fit TOGETHER, natively, by mgcv, at a FIXED,
# externally-supplied sp for every block -- the same "fixed sp" Stage-B regime
# gam_multiterm_probe.R (slice 5) already used.
#
#   y ~ s(AttdAge, k = 13, bs = "cr")                                # reference age
#     + s(FaceSize, AttdAge, bs = "sz", k = 13, xt = list(bs = "cr")) # level deviations
#   family = binomial(link = "cloglog"), weights = ExposCnt           # Anchor 5, absolute
#
# `s(FaceSize, AttdAge, ...)` is the target formula's own first `sz` term
# verbatim (PLAN Section 1), including its own AttdAge k=13 knot vector --
# the same knots ADR-215's "sz-target-attdage-k13" Stage-A case already used.
#
# WHY THIS BUILDS ITS OWN CASE, WITH NO EXCHANGE DEPENDENCY
# -----------------------------------------------------------
# Same reasoning as gam_multiterm_probe.R: a probe for a specific hypothesis
# needs a SHARED recipe both sides fit, not the full ADR-189 exchange.
# "Shared" means this script builds AttdAge/FaceSize/ExposCnt/y
# deterministically (set.seed, ADR-074 -- no wall clock) and writes the
# recipe into its own output JSON alongside its own fit.
#
# WHY THE COMPARISON IS ON eta, NEVER coef (Anchor 2)
# -----------------------------------------------------
# mgcv reparameterises internally, and an `sz` term's own sum-to-zero
# constraint gives it just as much freedom to do so as the `ti()`/`by` terms
# slice 5 already measured. This script reports `coef` for diagnostic
# reading only.
#
# INDEPENDENCE (ADR-193)
# -------------------------
# The Python side (polaris_re.analytics.gam_multiterm_sz_conformance) builds
# its own design from the two ALREADY-INDEPENDENTLY-VERIFIED basis producers
# (gam_basis_cr.cr_basis / absorb_sum_to_zero_constraint, gam_basis_cr.sz_basis,
# via gam_stage_a.build_python_cr_term / build_python_sz_term -- ADR-194,
# ADR-215) and fits with gam_fit.penalized_irls_general at the SAME
# externally-supplied sp. It reads only the shared recipe this script exports
# (AttdAge, FaceSize's 0-indexed level code, ExposCnt, y, the reference term's
# knot vector, sp) -- never this script's own eta or coef -- which is what
# makes the eta comparison INDEPENDENT rather than an echo of this script's
# fit.
#
# REQUIREMENTS: R with mgcv and jsonlite.
# USAGE:  Rscript scripts/gam_multiterm_sz_probe.R [output.json]
# EXIT STATUS: 0 on a completed run, 1 on any R-side error.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_multiterm_sz_probe.json"
  set.seed(20260831) # ADR-074: pinned, never the wall clock.

  n <- 700
  # PLAN Section 1's own target-formula knot vector for AttdAge -- the literal
  # knots, same discipline slice 2 (ADR-194) and ADR-215's own
  # "sz-target-attdage-k13" Stage-A case used.
  age_knots <- c(1, 2, 4, 7, 14, 18, 24, 35, 50, 70, 85, 90, 95)

  AttdAge <- runif(n, 1, 95)
  # FaceSize -- two-level factor, matching the target formula's own FaceSize
  # (PLAN Section 1: "FaceSize and Smoke both two-level").
  FaceSize <- factor(sample(c("Small", "Large"), n, replace = TRUE),
                      levels = c("Small", "Large"))
  ExposCnt <- round(runif(n, 50, 500))

  # A synthetic "true" surface -- not fitted to, just needs to produce a
  # reasonably-behaved binomial response under cloglog so the shared FIXED-sp
  # fit converges cleanly on both sides. Neither side reads this function;
  # both sides read only the resulting y/weights it produces.
  face_effect <- ifelse(FaceSize == "Large", 0.25, -0.15)
  eta_true <- -4.5 + 0.03 * AttdAge + face_effect * sin((AttdAge - 40) / 20)
  prob_true <- 1 - exp(-exp(eta_true))
  DthCnt <- rbinom(n, ExposCnt, prob_true)
  y <- DthCnt / ExposCnt

  df <- data.frame(AttdAge = AttdAge, FaceSize = FaceSize, ExposCnt = ExposCnt, y = y)
  knots_arg <- list(AttdAge = age_knots)

  # Fixed sp, one per penalty block, in the SAME order mgcv assigns to the
  # formula's smooth terms: [s(AttdAge), s(FaceSize,AttdAge)#level1,
  # s(FaceSize,AttdAge)#level2] -- 3 blocks (sz carries one per factor level,
  # ADR-215's own sz_basis contract; 2 levels here).
  sp_fixed <- c(2.5, 3.5, 1.8)

  m <- mgcv::gam(
    y ~ s(AttdAge, k = 13, bs = "cr") +
      s(FaceSize, AttdAge, k = 13, bs = "sz", xt = list(bs = "cr")),
    data = df, family = binomial(link = "cloglog"), weights = ExposCnt,
    knots = knots_arg, sp = sp_fixed
  )

  eta <- as.numeric(predict(m, type = "link"))

  out <- list(
    schema_version = 1L,
    n = n,
    AttdAge = AttdAge,
    # 0-indexed factor-level code per row, so the Python side builds its OWN
    # sz basis from the same (x, group, n_levels, knots) recipe, never
    # reading mgcv's own X/S/rank or eta/coef back (ADR-193's mechanical test,
    # ADR-215's own convention for extract_smooth_sz).
    face_size_group = as.integer(FaceSize) - 1L,
    face_size_n_levels = length(levels(FaceSize)),
    ExposCnt = as.numeric(ExposCnt), y = y,
    age_knots = age_knots,
    sp = sp_fixed,
    mgcv_version = as.character(packageVersion("mgcv")),
    r_version = R.version.string,
    eta = eta,
    coef = as.numeric(coef(m)), # diagnostic only, never compared (Anchor 2)
    edf_per_smooth = as.numeric(m$edf1), # diagnostic only
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
    message("gam_multiterm_sz_probe.R FAILED: ", conditionMessage(e))
    1L
  }
)
quit(status = status)
