#!/usr/bin/env Rscript
#
# gam_family_probe.R — mgcv-parity engine, slice 3 (docs/PLAN_mgcv_parity_engine.md).
#
# Fits a SHARED (X, S) design under four family/link/weight combinations named by
# slice 3: binomial cloglog and logit on a proportion response with prior weights,
# quasi-Poisson with an estimated dispersion, and Poisson with a log offset (the
# combination the tensor MI surface's own fitter already uses, included here as the
# check that this probe's shared machinery reduces to the already-verified case).
#
# WHY THIS BUILDS ITS OWN CASE, WITH NO EXCHANGE DEPENDENCY
# -----------------------------------------------------------
# Same reasoning as scripts/smoothcon_lpmatrix_probe.R: a probe script for a specific
# hypothesis does not need the full ADR-189 committed-golden exchange (hash guard,
# manifest schema, multi-design matrix) — it needs a SHARED design both sides solve.
# Here "shared" means this script builds X, S, y, weights/offset deterministically
# (set.seed, ADR-074 — no wall clock, so a no-change re-run is byte-identical) and
# writes them into its own output JSON alongside its fit. The Python side
# (polaris_re.analytics.gam_family_conformance) reads ONLY those recipe fields back —
# never this script's `eta` or `coef` — and fits independently via
# polaris_re.analytics.gam_fit.penalized_irls_general, so the eta comparison is
# INDEPENDENT (ADR-193's mechanical test: the Python producer's signature takes the
# recipe, not this script's fitted output).
#
# WHY THE COMPARISON IS ON eta, NEVER coef (Anchor 2)
# -----------------------------------------------------
# mgcv reparameterises internally; two conformant IRLS implementations can agree
# exactly on the fitted surface while sharing no coefficient. This script reports
# `coef` for diagnostic reading only — the Python comparator must never gate on it.
#
# WHY FIXED sp, NOT REML
# -----------------------
# PLAN slice 3's acceptance criterion is "at fixed sp on a shared design, eta
# matches for each family/link/weight combination" — generalising the outer
# smoothing-parameter optimiser to non-Poisson families is slice 4's scope.
#
# REQUIREMENTS: R with `mgcv` and `jsonlite`. Same two packages every other script
# in this epic needs.
#
# USAGE:
#     Rscript scripts/gam_family_probe.R [output.json]
#
# EXIT STATUS: 0 on a completed run, 1 on any R-side error.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

build_shared_design <- function(n = 150, p = 6) {
  # A deterministic smooth-ish design (not any particular mgcv basis — it does not
  # need to be, since it is supplied directly through paraPen exactly as the
  # existing Poisson conformance suite's tensor design is, ADR-189 decision 1). An
  # intercept plus low-order Fourier terms gives a well-conditioned, full-rank X
  # without needing a basis-construction module this probe has no reason to depend
  # on.
  t <- seq(0, 1, length.out = n)
  cols <- list(rep(1, n))
  for (k in seq_len(p - 1)) {
    cols[[length(cols) + 1]] <- if (k %% 2 == 1) {
      sin(2 * pi * ((k + 1) %/% 2) * t)
    } else {
      cos(2 * pi * (k %/% 2) * t)
    }
  }
  X <- do.call(cbind, cols)
  # Second-difference penalty on the p coefficients — same construction as
  # experience_gam_penalized.difference_penalty (D^T D for order-2 differences),
  # reproduced here rather than imported so this probe has no Python dependency at
  # fit time.
  D <- diff(diag(p), differences = 2)
  S <- t(D) %*% D
  list(t = t, X = X, S = S)
}

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_family_probe.json"
  set.seed(20260817)

  design <- build_shared_design()
  t <- design$t
  X <- design$X
  S <- design$S
  n <- nrow(X)
  p <- ncol(X)
  sp <- 2.0

  beta_true <- c(0.1, 0.6, -0.4, 0.3, -0.2, 0.15)[seq_len(p)]
  eta_true <- as.numeric(X %*% beta_true)

  cases <- list()

  # -- binomial / logit, prior weights ------------------------------------------
  prob_logit <- 1 / (1 + exp(-eta_true))
  trials <- round(30 + 20 * sin(4 * pi * t))
  successes <- round(trials * prob_logit)
  y_logit <- successes / trials
  cases[["binomial-logit"]] <- list(
    family = "binomial", link = "logit",
    y = y_logit, weights = as.numeric(trials), offset = NULL
  )

  # -- binomial / cloglog, prior weights -----------------------------------------
  prob_cloglog <- 1 - exp(-exp(eta_true - 1.0))  # shift so eta stays in a sane range
  successes_c <- round(trials * prob_cloglog)
  y_cloglog <- successes_c / trials
  cases[["binomial-cloglog"]] <- list(
    family = "binomial", link = "cloglog",
    y = y_cloglog, weights = as.numeric(trials), offset = NULL
  )

  # -- quasi-Poisson, log link ----------------------------------------------------
  # log(20) baseline: keeps counts in the tens (real Poisson variation) rather than
  # clustering at 0/1, where rounding would erase the signal a dispersion estimate
  # needs to be meaningful.
  mu_pois <- exp(log(20) + 0.3 * eta_true)
  y_pois <- round(mu_pois)
  cases[["quasipoisson-log"]] <- list(
    family = "quasipoisson", link = "log",
    y = as.numeric(y_pois), weights = NULL, offset = NULL
  )

  # -- Poisson, log link, WITH an offset (the tensor MI surface's own idiom) -----
  offset_vec <- log(20) + 0.2 * cos(2 * pi * t)
  mu_off <- exp(offset_vec + 0.3 * eta_true)
  y_off <- round(mu_off)
  cases[["poisson-log-offset"]] <- list(
    family = "poisson", link = "log",
    y = as.numeric(y_off), weights = NULL, offset = as.numeric(offset_vec)
  )

  results <- list()
  for (case_name in names(cases)) {
    spec <- cases[[case_name]]
    fam <- switch(spec$family,
      binomial = binomial(link = spec$link),
      poisson = poisson(link = spec$link),
      quasipoisson = quasipoisson(link = spec$link),
      stop(sprintf("Unhandled family '%s'.", spec$family))
    )

    frame <- list(y = spec$y, X = X)
    args <- list(
      formula = y ~ 0 + X,
      data = frame,
      family = fam,
      paraPen = list(X = list(S, sp = sp))
    )
    if (!is.null(spec$weights)) {
      frame$w <- spec$weights
      args$data <- frame
      args$formula <- y ~ 0 + X
      args$weights <- quote(w)
    }
    if (!is.null(spec$offset)) {
      frame$off <- spec$offset
      args$data <- frame
      args$formula <- y ~ 0 + X + offset(off)
    }

    m <- do.call(mgcv::gam, args)
    eta <- as.numeric(predict(m, type = "link"))

    results[[case_name]] <- list(
      family = spec$family,
      link = spec$link,
      y = spec$y,
      weights = spec$weights,
      offset = spec$offset,
      sp = sp,
      eta = eta,
      coef = as.numeric(coef(m)),
      dispersion = as.numeric(m$sig2),
      scale_estimated = isTRUE(m$scale.estimated),
      converged = isTRUE(m$converged)
    )
  }

  out <- list(
    schema_version = 1L,
    n = n,
    p = p,
    t = t,
    X = X,
    S = S,
    mgcv_version = as.character(packageVersion("mgcv")),
    r_version = R.version.string,
    cases = results
  )
  jsonlite::write_json(
    out, out_path,
    digits = NA, auto_unbox = TRUE, null = "null", matrix = "rowmajor"
  )
  cat(sprintf(
    "Wrote %s — %d cases, mgcv %s\n", out_path, length(results),
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
    message("gam_family_probe.R FAILED: ", conditionMessage(e))
    1L
  }
)
quit(status = status)
