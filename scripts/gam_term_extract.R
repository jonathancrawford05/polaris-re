#!/usr/bin/env Rscript
# =============================================================================
# Slice 1's remaining scope, plus slice 1b: the R-side per-term extractor.
# =============================================================================
# docs/PLAN_mgcv_parity_engine.md slice 1 / docs/CONTINUATION_mgcv_parity_engine.md:
# an R-side extractor that emits, per term, the design block, every S_j, the
# coefficient index range, the rank, the knots actually used, and the label. ADR-191
# settled the referent question for mgcv-native bases (smoothCon(absorb.cons=TRUE));
# this script proves the *harness* — the extraction and serialization machinery — on
# the "raw" basis (TermSpec.basis == "raw", ADR-189 decision 1's paraPen route)
# BEFORE trusting it on a basis with no independent check, per Anchor 1's "known-good
# basis first."
#
# WHY "RAW" NEEDS ITS OWN CODE PATH, NOT SMOOTHCON(). A paraPen-only fit has an empty
# smooth list (`length(m$smooth) == 0`, ADR-189 amendment 1) — there is no mgcv
# smooth-class object to call smoothCon() on. So this script reads what mgcv actually
# FIT rather than re-echoing the exchange's own TSVs (which would prove nothing about
# mgcv's bookkeeping): `m$paraPen$S` for the penalties mgcv used, `m$paraPen$rank`
# for their rank (mgcv computes this itself; not re-derived here), and
# `predict(type="lpmatrix")` for the design. Interactively verified against this
# exchange's design d1 before being written into this script: `m$paraPen$S` and
# `predict(type="lpmatrix")` both reproduce the exchange's own supplied matrices at
# max-abs-diff exactly 0, and `m$paraPen$rank` is `(30, 28)` for d1's `(S_age,
# S_year)` — the rank mgcv itself relies on to compute `tr(F)`, already verified to
# 7.2e-13 (ADR-189 amendment 1).
#
# SLICE 1B (docs/WORK_ORDER_slice_1b_mgcv_native_extraction.md): mgcv-native
# (cr/ti/sz) extraction via smoothCon(), emitting the SAME per-term schema under a
# second top-level key (`smooth_designs`) rather than forking it. These are isolated
# single-term bs="cr" cases — same synthetic generation as
# scripts/smoothcon_lpmatrix_probe.R (seed 20120101, ADR-074) — so the internal guard
# below is directly comparable to ADR-191's tier-3 reading, and needs no exchange or
# fitted multi-term model (ADR-191's whole point: smoothCon() alone is the referent).
# The guard promotes that probe's own diagnostic assertion into a standing check: it
# now fails this script loudly (stop()) rather than silently accepting a schema this
# basis has stopped satisfying.
#
# DIAGNOSTIC, wired with continue-on-error, same contract as ks_formula_probe.R and
# smoothcon_lpmatrix_probe.R: it has explicit stop() paths and can exit non-zero, and
# that is what keeps a harness bug from blocking a merge before slice 2 exists to fix.
# =============================================================================
suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

main <- function(argv) {
  exchange_dir <- if (length(argv) >= 1) argv[[1]] else "data/mgcv_exchange/synthetic"
  out_path <- if (length(argv) >= 2) argv[[2]] else "gam_term_extract.json"

  manifest <- jsonlite::fromJSON(file.path(exchange_dir, "manifest.json"), simplifyVector = FALSE)

  read_design <- function(design_id) {
    meta <- manifest$designs[[design_id]]
    tbl <- as.matrix(read.table(
      file.path(exchange_dir, meta$files$data),
      header = TRUE, sep = "\t", colClasses = "numeric"
    ))
    read_penalty <- function(key) {
      s <- as.matrix(read.table(
        file.path(exchange_dir, meta$files[[key]]),
        header = TRUE, sep = "\t", colClasses = "numeric"
      ))
      dimnames(s) <- NULL
      s
    }
    x <- tbl[, -(1:2), drop = FALSE]
    dimnames(x) <- NULL
    list(
      y = as.numeric(tbl[, 1]), off = as.numeric(tbl[, 2]), X = x,
      S_age = read_penalty("penalty_age"), S_year = read_penalty("penalty_year"),
      n_tensor = as.integer(meta$n_tensor), n_coef = as.integer(meta$n_coef),
      factors = unlist(meta$factors)
    )
  }

  # Fixed lambda, READ from the manifest's committed `l1-interior` cell rather than
  # hardcoded — the harness proof does not need free-sp selection, and fixing sp is
  # what makes the design/penalty comparison exact rather than approximate
  # (RUNBOOK_mgcv_conformance.md level 1). Reading it from the manifest (rather than
  # literal 10/100 with a comment claiming they match) means a future change to that
  # cell's lambda is picked up automatically instead of silently drifting out of sync
  # with this script (PR #197 review [P1]).
  l1_interior <- Filter(function(c) identical(c$name, "l1-interior"), manifest$cells)
  if (length(l1_interior) != 1L) {
    stop("manifest.json has no (or more than one) cell named 'l1-interior' — this ",
         "script's fixed-lambda choice is read from it and needs exactly one match.")
  }
  fixed_lambda_age <- as.numeric(l1_interior[[1]]$lambda_age)
  fixed_lambda_year <- as.numeric(l1_interior[[1]]$lambda_year)

  extract_one <- function(design_id, lambda_age = fixed_lambda_age, lambda_year = fixed_lambda_year) {
    d <- read_design(design_id)
    frame <- list(y = d$y, X = d$X, off = d$off)
    pp <- list(d$S_age, d$S_year)
    pp$sp <- c(lambda_age, lambda_year)
    m <- mgcv::gam(
      y ~ 0 + X + offset(off),
      data = frame, family = poisson(), paraPen = list(X = pp), method = "REML",
      control = mgcv::gam.control(scalePenalty = FALSE)
    )

    Xp <- predict(m, type = "lpmatrix")
    if (ncol(Xp) != d$n_coef) {
      stop(sprintf(
        "design '%s': lpmatrix has %d columns but the manifest declares n_coef=%d.",
        design_id, ncol(Xp), d$n_coef
      ))
    }
    if (length(m$paraPen$S) != 2L || length(m$paraPen$rank) != 2L) {
      stop(sprintf(
        "design '%s': m$paraPen$S/$rank did not come back as the two penalties supplied.",
        design_id
      ))
    }

    # m$paraPen$S is padded to the FULL design width (n_coef), matching how the
    # exchange itself supplies the penalties (DesignExport's own padding, so mgcv
    # knows the factor columns are unpenalized) — so the tensor TERM's own S block is
    # the leading n_tensor x n_tensor submatrix, not the padded matrix whole.
    tensor_idx <- seq_len(d$n_tensor)
    terms <- list()
    terms[["tensor"]] <- list(
      label = "tensor",
      index_start = 0L, index_end = d$n_tensor,
      X = Xp[, tensor_idx, drop = FALSE],
      S = list(m$paraPen$S[[1]][tensor_idx, tensor_idx], m$paraPen$S[[2]][tensor_idx, tensor_idx]),
      rank = as.integer(m$paraPen$rank),
      knots = NULL
    )
    if (d$n_coef > d$n_tensor) {
      factor_idx <- (d$n_tensor + 1L):d$n_coef
      factor_label <- paste0("factor:", paste(d$factors, collapse = ","))
      terms[[factor_label]] <- list(
        label = factor_label,
        index_start = d$n_tensor, index_end = d$n_coef,
        X = Xp[, factor_idx, drop = FALSE],
        S = list(), rank = integer(0), knots = NULL
      )
    }
    list(design = design_id, n_coef = d$n_coef, n_tensor = d$n_tensor, terms = terms)
  }

  # ===========================================================================
  # Slice 1b: mgcv-native (smoothCon) per-term extraction.
  # ===========================================================================
  # Isolated single-term bs="cr" cases, no exchange dependency — ADR-191 needs no
  # fitted multi-term model, which is what makes an isolated-term harness possible.
  # index_start/index_end are 0/ncol(X): the work order §4 design question (is a
  # term's index range read from a fit, or assigned by the harness assembling terms
  # into a model?) is settled as the latter, ADR-192 — and the model an isolated
  # Stage-A case assembles is exactly this one term, so its range is [0, width).
  extract_smooth_one <- function(label, n, k, knots_x = NULL, bs = "cr", x_range = c(0, 10)) {
    set.seed(20120101) # ADR-074: pinned, never the wall clock.
    x <- sort(runif(n, x_range[1], x_range[2]))
    y <- sin(x) + rnorm(n, sd = 0.1)
    df <- data.frame(x = x, y = y)
    knots_arg <- if (is.null(knots_x)) NULL else list(x = knots_x)

    sm <- smoothCon(s(x, k = k, bs = bs), data = df, knots = knots_arg,
                     absorb.cons = TRUE)[[1]]
    m <- gam(y ~ s(x, k = k, bs = bs), data = df, knots = knots_arg)

    Xp <- predict(m, type = "lpmatrix")
    smooth_cols <- grep("^s\\(x\\)", colnames(Xp))
    Xp_smooth <- Xp[, smooth_cols, drop = FALSE]

    # The extractor's OWN internal consistency guard (work order §2): the
    # smoothCon() extraction must equal the independent lpmatrix/m$smooth route,
    # promoted from smoothcon_lpmatrix_probe.R's one-off diagnostic assertion into a
    # standing check every run of this script re-verifies.
    if (!identical(dim(Xp_smooth), dim(sm$X))) {
      stop(sprintf(
        "smooth design '%s': lpmatrix smooth block is %dx%d but smoothCon()$X is %dx%d.",
        label, nrow(Xp_smooth), ncol(Xp_smooth), nrow(sm$X), ncol(sm$X)
      ))
    }
    guard_x <- max(abs(Xp_smooth - sm$X))
    if (guard_x != 0) {
      stop(sprintf(
        "smooth design '%s': smoothCon() X disagrees with lpmatrix (max abs diff %.3e) — internal consistency guard failed.",
        label, guard_x
      ))
    }
    s_fit <- m$smooth[[1]]$S[[1]]
    guard_s <- max(abs(s_fit - sm$S[[1]]))
    if (guard_s != 0) {
      stop(sprintf(
        "smooth design '%s': smoothCon() S disagrees with m$smooth[[1]]$S (max abs diff %.3e) — internal consistency guard failed.",
        label, guard_s
      ))
    }
    guard_rank <- m$smooth[[1]]$rank - sm$rank
    if (guard_rank != 0L) {
      stop(sprintf(
        "smooth design '%s': smoothCon() rank (%d) disagrees with m$smooth[[1]]$rank (%d) — internal consistency guard failed.",
        label, sm$rank, m$smooth[[1]]$rank
      ))
    }
    guard_xp <- max(abs(m$smooth[[1]]$xp - sm$xp))
    if (guard_xp != 0) {
      stop(sprintf(
        "smooth design '%s': smoothCon() xp disagrees with m$smooth[[1]]$xp (max abs diff %.3e) — internal consistency guard failed.",
        label, guard_xp
      ))
    }

    list(
      label = label,
      index_start = 0L, index_end = ncol(sm$X),
      X = sm$X,
      S = list(sm$S[[1]]),
      # I() forces jsonlite to keep this an array even though it has one element —
      # a bare `sm$rank` (length-1 integer) would auto-unbox to a scalar, which
      # broke the Python side's `for v in r_term["rank"]` (not iterable). The raw
      # path's `rank` never hit this because it always carries two penalties.
      rank = I(sm$rank),
      knots = as.numeric(sm$xp),
      # Slice 2 (ADR-193): the covariate locations themselves, so the Python side
      # can build its OWN cr basis at the SAME x rather than reading mgcv's X/S —
      # x is shared recipe context (like a supplied knot vector), not a compared
      # quantity, so exporting it does not make the Python producer read "the
      # other side's payload" in the ADR-193 mechanical-test sense. Without this,
      # Python has no way to evaluate a comparable design at points drawn from R's
      # own RNG stream, which numpy cannot reproduce bit-for-bit from the same seed.
      x = as.numeric(x)
    )
  }

  smooth_cases <- list(
    extract_smooth_one("default-knots-k8", n = 200, k = 8),
    extract_smooth_one("default-knots-k13", n = 400, k = 13),
    extract_smooth_one("supplied-knots-k8", n = 200, k = 8,
                        knots_x = c(0, 1, 2, 3, 5, 8, 9, 10)),
    # PLAN §1's actual target formula's own hand-chosen knot vectors — not just the
    # harness's original synthetic cases — so slice 2's acceptance criterion #1
    # ("for the target's own knot vectors ... at both k=13 and k=6") is tested
    # against the literal knots the maintainer supplied, not a stand-in. x_range
    # keeps every point inside [knots[0], knots[-1]]: cr_basis.py's extrapolation
    # behaviour outside a knot range is explicitly unverified (module docstring),
    # so these cases must not exercise it.
    extract_smooth_one("target-attdage-k13", n = 400, k = 13,
                        knots_x = c(1, 2, 4, 7, 14, 18, 24, 35, 50, 70, 85, 90, 95),
                        x_range = c(1, 95)),
    extract_smooth_one("target-polyear-k6", n = 200, k = 6,
                        knots_x = c(1, 2, 3, 5, 10, 21),
                        x_range = c(1, 21))
  )
  names(smooth_cases) <- vapply(smooth_cases, function(c) c$label, character(1))

  designs_to_probe <- Filter(function(id) manifest$designs[[id]]$n_coef > 0, names(manifest$designs))
  out <- list(
    schema_version = 1L,
    r_version = R.version.string,
    mgcv_version = as.character(packageVersion("mgcv")),
    designs = setNames(lapply(designs_to_probe, extract_one), designs_to_probe),
    smooth_designs = smooth_cases
  )
  jsonlite::write_json(
    out, out_path,
    digits = NA, auto_unbox = TRUE, null = "null", matrix = "rowmajor"
  )
  cat(sprintf(
    "Wrote %s — %d design(s), %d smooth design(s), mgcv %s\n",
    out_path, length(designs_to_probe), length(smooth_cases),
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
    message("gam_term_extract.R FAILED: ", conditionMessage(e))
    1L
  }
)
quit(status = status)
