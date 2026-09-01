#!/usr/bin/env Rscript
#
# gam_select_penalty_probe.R -- mgcv-parity engine, PLAN slice 7
# (docs/PLAN_mgcv_parity_engine.md, docs/CONTINUATION_mgcv_parity_engine.md).
#
# WHAT THIS PROBES
# ------------------
# `select = TRUE`'s double penalty (Marra & Wood 2011): mgcv adds ONE extra
# penalty per smooth term, penalising exactly the null space its existing
# penalty block(s) leave unpenalised -- what lets a term shrink to nothing
# under REML rather than only becoming smoother. This script reads that
# extra penalty directly off mgcv's own setup path, WITHOUT fitting any
# model (`fit = FALSE`): `gam(formula, family, data, knots, select = TRUE,
# fit = FALSE)` returns a "gam.prefit" object whose `$smooth[[i]]$S` is the
# term's full list of penalty blocks -- the term's own already-existing
# block(s) unchanged, PLUS one more appended when `select = TRUE`. Since the
# S matrices depend only on the model's structure (knots, basis, `by`/factor
# variables) and never on `y`, `fit = FALSE` is exact, not an approximation
# of fitting -- and far cheaper.
#
# ONE CASE PER TARGET-FORMULA TERM ARCHETYPE (PLAN Section 1), at the
# target's own knot vectors where the term has one -- the same discipline
# ADR-194/200/205/215 used for their own Stage-A cases:
#   - cr-ref-attdage-k13:  s(AttdAge, k=13, bs="cr")                  -- reference age
#   - cr-ref-polyear-k6:   s(PolYear, k=6, bs="cr")                   -- reference duration
#   - cr-by-mi-attdage-k13: s(AttdAge, by=StudyYear_C, k=13, bs="cr") -- the MI term
#   - ti-attdage-polyear:  ti(AttdAge, PolYear, k=c(13,6), bs="cr")
#   - sz-facesize-attdage-k13: s(FaceSize, AttdAge, bs="sz", k=13, xt=list(bs="cr"))
#   - sz-facesize-polyear-k6:  s(FaceSize, PolYear, bs="sz", k=6, xt=list(bs="cr"))
# `Smoke`'s own two `sz` terms are the identical construction over the same
# two margins as `FaceSize`'s (PLAN Section 1) and are not duplicated here.
#
# WHY THIS ONLY CONFIRMS STRUCTURE MEASURED IN AN EARLIER TIER-1 SESSION
# --------------------------------------------------------------------------
# Read directly off this probe's own tier-1 run before any Python code was
# written (ROUTINE_MGCV_PARITY.md step 2 -- tier 1 is for "does this call
# exist, what shape does it return"): the extra penalty equals `U0 %*% t(U0)`,
# where `U0` spans the null space (below `matrix_rank`'s own tolerance) of
# the SUM of the term's own EXISTING penalty block(s), each at its natural
# (unscaled, lambda=1) magnitude. That rule is basis-agnostic -- it held,
# unchanged, across all four archetypes above (single-block cr, two-block by,
# three-block sz, two-margin ti) at that tier-1 reading. This script exists
# to CONFIRM the same rule on the pinned oracle, at the target's own knots,
# not to discover it again.
#
# INDEPENDENCE (ADR-193)
# -------------------------
# The Python side (polaris_re.analytics.gam_select_penalty.null_space_penalty)
# takes only a term's own ALREADY-INDEPENDENTLY-VERIFIED penalty block(s)
# (ADR-194/200/205/215's cr/by/ti/sz producers) and computes the null-space
# penalty from NumPy's own eigendecomposition and `matrix_rank` tolerance --
# never from this script's own S. That is what makes the comparison
# INDEPENDENT rather than a transport of this script's own output.
#
# REQUIREMENTS: R with mgcv and jsonlite.
# USAGE:  Rscript scripts/gam_select_penalty_probe.R [output.json]
# EXIT STATUS: 0 on a completed run, 1 on any R-side error.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

# A term's `$smooth[[1]]$S`/`$rank` from mgcv's own setup-only path
# (`fit = FALSE` -- exact for this purpose, see header: S never depends on
# `y`). `extra_data` supplies any covariate the formula needs beyond `x`
# (a `by` variable, a factor, a second tensor margin).
extract_case <- function(formula_rhs, knots_arg, n, x, extra_data = list(),
                          echo_extra = list()) {
  df <- data.frame(x = x)
  for (nm in names(extra_data)) df[[nm]] <- extra_data[[nm]]
  df$y <- rpois(n, 5) # never read by the S/rank comparison -- setup only.

  form <- as.formula(paste("y ~", formula_rhs))
  G <- mgcv::gam(form, data = df, family = poisson(), knots = knots_arg,
                 select = TRUE, fit = FALSE)
  sm <- G$smooth[[1]]
  # `x` (and any extra covariate, in the form the PYTHON side's own producer
  # takes it -- e.g. a 0-indexed integer group code, not an R factor) is
  # echoed back so the Python side builds its OWN penalty blocks from the
  # IDENTICAL sample: the constrained cr constraint (colMeans(X)) is
  # data-dependent, so a different draw of `x` would legitimately produce a
  # different (still-correct) null space and make an unrelated draw look
  # like a disagreement (ADR-193's shared-recipe convention, the same one
  # build_python_cr_term's own `x` argument already uses).
  result <- list(S = sm$S, rank = as.integer(sm$rank), x = x)
  for (nm in names(echo_extra)) result[[nm]] <- echo_extra[[nm]]
  result
}

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_select_penalty_probe.json"
  set.seed(20260901) # ADR-074: pinned, never the wall clock.

  n <- 300
  age_knots <- c(1, 2, 4, 7, 14, 18, 24, 35, 50, 70, 85, 90, 95)
  year_knots <- c(1, 2, 3, 5, 10, 21)

  age <- runif(n, 1, 95)
  year <- runif(n, 1, 21)
  study_year_c <- runif(n, -5, 5)
  face_size <- factor(sample(c("Small", "Large"), n, replace = TRUE),
                       levels = c("Small", "Large"))

  cases <- list(
    `cr-ref-attdage-k13` = extract_case(
      's(x, k = 13, bs = "cr")', list(x = age_knots), n, age
    ),
    `cr-ref-polyear-k6` = extract_case(
      's(x, k = 6, bs = "cr")', list(x = year_knots), n, year
    ),
    `cr-by-mi-attdage-k13` = extract_case(
      's(x, by = by_var, k = 13, bs = "cr")', list(x = age_knots), n, age,
      extra_data = list(by_var = study_year_c),
      echo_extra = list(by_var = study_year_c)
    ),
    `ti-attdage-polyear` = extract_case(
      'ti(x, x2, k = c(13, 6), bs = "cr")',
      list(x = age_knots, x2 = year_knots), n, age,
      extra_data = list(x2 = year), echo_extra = list(x2 = year)
    ),
    `sz-facesize-attdage-k13` = extract_case(
      's(fac, x, bs = "sz", k = 13, xt = list(bs = "cr"))',
      list(x = age_knots), n, age, extra_data = list(fac = face_size),
      echo_extra = list(group = as.integer(face_size) - 1L, n_levels = length(levels(face_size)))
    ),
    `sz-facesize-polyear-k6` = extract_case(
      's(fac, x, bs = "sz", k = 6, xt = list(bs = "cr"))',
      list(x = year_knots), n, year, extra_data = list(fac = face_size),
      echo_extra = list(group = as.integer(face_size) - 1L, n_levels = length(levels(face_size)))
    )
  )

  out <- list(
    schema_version = 1L,
    mgcv_version = as.character(packageVersion("mgcv")),
    r_version = R.version.string,
    cases = cases
  )
  jsonlite::write_json(
    out, out_path,
    digits = NA, auto_unbox = TRUE, null = "null", matrix = "rowmajor"
  )
  cat(sprintf(
    "Wrote %s -- %d cases, mgcv %s\n", out_path, length(cases),
    as.character(packageVersion("mgcv"))
  ))
  invisible(NULL)
}

status <- tryCatch(
  {
    main(commandArgs(trailingOnly = TRUE))
    0L
  },
  error = function(e) {
    message("gam_select_penalty_probe.R FAILED: ", conditionMessage(e))
    1L
  }
)
quit(status = status)
