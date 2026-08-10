#!/usr/bin/env Rscript
#
# mgcv_conformance.R — the R side of the penalized-MI conformance suite.
#
# Slice 5 of docs/PLAN_penalized_mi_surface.md. Reads the exchange written by
# scripts/export_mgcv_case.py, fits every cell in the case matrix with mgcv, and writes
# ONE reference JSON. Nothing else: no plotting, no interpretation, no comparison. The
# comparison is scripts/compare_mgcv_conformance.py, offline, against this file.
#
# WHY THIS FITS `y ~ 0 + X` AND NOT `te(attained_age, calendar_year)`
# ------------------------------------------------------------------
# The exchange ships OUR tensor design and OUR difference penalties. mgcv accepts
# exactly that through `paraPen`. Fitting a `te()` instead would compare two bases, two
# knot placements and two identifiability constraints, and a disagreement would be
# uninterpretable. With the design and the penalties supplied, the penalized Poisson
# log-likelihood is strictly concave over a SHARED problem, its maximiser is unique, and
# every disagreement localises to arithmetic.
#
# THE ONE SETTING THAT IS LOAD-BEARING: scalePenalty = FALSE
# ---------------------------------------------------------
# mgcv rescales caller-supplied penalties by default (gam.control's scalePenalty,
# documented default TRUE) so that penalties of very different magnitudes are comparable.
# That redefines what `sp` multiplies — and this whole suite rests on `sp` multiplying the
# supplied S directly. With the default left in place, every fixed-lambda cell could
# disagree for a reason that is not our arithmetic, which is the most expensive kind of
# false finding available here. It is turned off, and the value used is recorded.
#
# ADOPTED FROM THE DOCUMENTATION, NOT VERIFIED — and deliberately flagged, because this
# slice exists to stop exactly that kind of claim from going unmarked (PLAN Anchor 8).
# `scalePenalty` is the documented gam.control argument governing penalty rescaling, but
# whether and how it applies to `paraPen` penalties specifically was NOT verifiable in the
# container this script was written in: there is no R there. So the script does three
# things rather than assume:
#   1. sets scalePenalty = FALSE, which is strictly the safer direction;
#   2. FAILS LOUDLY with a readable message if gam.control rejects the argument, rather
#      than falling back to the default and quietly comparing a rescaled penalty;
#   3. records every scaling artefact the fitted object exposes (`penalty_scaling`), so a
#      level-1 disagreement is attributable to rescaling on sight instead of being
#      mysterious. If that field comes back non-trivial, THAT is the first finding of the
#      run and the fix is a one-line R change, not a re-derivation of our arithmetic.
#
# REQUIREMENTS: R with `mgcv` (a base R recommended package) and `jsonlite`. No
# reticulate, no RcppCNPy — which is why the exchange is TSV + JSON rather than .npz.
#
# USAGE (no arguments needed; both paths default):
#     Rscript scripts/mgcv_conformance.R
#     Rscript scripts/mgcv_conformance.R <exchange-dir> <output-json>
#
# EXIT STATUS: 0 on a completed run, 1 on any R-side error — so a batch run that dies
# halfway cannot be mistaken for a run whose numbers disagreed.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

main <- function(argv) {
  exchange_dir <- if (length(argv) >= 1) argv[[1]] else "data/mgcv_exchange/synthetic"
  out_path <- if (length(argv) >= 2) argv[[2]] else file.path(exchange_dir, "mgcv_reference.json")

  if (!dir.exists(exchange_dir)) {
    stop(sprintf("Exchange directory '%s' does not exist.", exchange_dir))
  }
  manifest_path <- file.path(exchange_dir, "manifest.json")
  hash_path <- file.path(exchange_dir, "exchange.sha256")
  for (p in c(manifest_path, hash_path)) {
    if (!file.exists(p)) stop(sprintf("Exchange is missing '%s'.", p))
  }

  # simplifyVector = FALSE: plain nested lists. The default simplification turns the
  # cell array into a data.frame and collapses the NULL lambdas of the free-sp cells,
  # which is a silent shape change in the middle of a loop.
  manifest <- jsonlite::fromJSON(manifest_path, simplifyVector = FALSE)
  if (manifest$schema_version != 1L) {
    stop(sprintf("Exchange schema version %s; this script reads 1.", manifest$schema_version))
  }
  exchange_sha256 <- trimws(readLines(hash_path, warn = FALSE)[[1]])

  # Built ONCE, up front, so an argument-name change in mgcv stops the run here with a
  # sentence rather than silently reverting to the rescaling default halfway through.
  scale_penalty_requested <- isFALSE(manifest$r_requirements$gam_control_scalePenalty)
  control <- tryCatch(
    mgcv::gam.control(scalePenalty = !scale_penalty_requested),
    error = function(e) {
      stop(sprintf(
        paste0(
          "mgcv::gam.control() rejected `scalePenalty` (%s). This suite requires `sp` to ",
          "multiply the supplied paraPen penalties DIRECTLY, so falling back to the ",
          "default would compare a rescaled penalty and report it as our arithmetic. ",
          "Find the argument that governs penalty rescaling in this mgcv version, set it, ",
          "and record the change in docs/RUNBOOK_mgcv_conformance.md."
        ),
        conditionMessage(e)
      ))
    }
  )

  # Every scaling artefact the fitted object exposes, probed defensively — a field that
  # does not exist in this mgcv version comes back NULL rather than erroring, and a
  # non-trivial value is the run's first finding.
  penalty_scaling <- function(m) {
    probe <- function(expr) tryCatch(expr, error = function(e) NULL)
    out <- list(
      S_scale = probe(as.numeric(m$paraPen$S.scale)),
      smooth_S_scale = probe(as.numeric(unlist(lapply(m$smooth, function(s) s$S.scale)))),
      full_sp = probe(as.numeric(m$full.sp))
    )
    out[!vapply(out, function(v) is.null(v) || length(v) == 0L, logical(1))]
  }

  # --- Load every design once; cells over a shared design are then nearly free -------
  designs <- list()
  for (design_id in names(manifest$designs)) {
    meta <- manifest$designs[[design_id]]
    tbl <- as.matrix(read.table(
      file.path(exchange_dir, meta$files$data),
      header = TRUE, sep = "\t", colClasses = "numeric"
    ))
    n_coef <- as.integer(meta$n_coef)
    if (ncol(tbl) != n_coef + 2L) {
      stop(sprintf(
        "Design '%s' has %d columns; the manifest declares n_coef=%d plus y and offset.",
        design_id, ncol(tbl), n_coef
      ))
    }
    read_penalty <- function(key) {
      s <- as.matrix(read.table(
        file.path(exchange_dir, meta$files[[key]]),
        header = TRUE, sep = "\t", colClasses = "numeric"
      ))
      dimnames(s) <- NULL
      if (nrow(s) != n_coef || ncol(s) != n_coef) {
        stop(sprintf("Penalty '%s' of design '%s' is not %dx%d.", key, design_id, n_coef, n_coef))
      }
      s
    }
    x <- tbl[, -(1:2), drop = FALSE]
    dimnames(x) <- NULL
    designs[[design_id]] <- list(
      y = as.numeric(tbl[, 1]),
      off = as.numeric(tbl[, 2]),
      X = x,
      S_age = read_penalty("penalty_age"),
      S_year = read_penalty("penalty_year"),
      n_tensor = as.integer(meta$n_tensor),
      n_coef = n_coef
    )
  }

  # --- Fit every cell ---------------------------------------------------------------
  cells <- list()
  for (spec in manifest$cells) {
    d <- designs[[spec$design]]
    if (is.null(d)) stop(sprintf("Cell '%s' names unknown design '%s'.", spec$name, spec$design))

    # `offset(off)` in the formula rather than the `offset=` argument: with a matrix
    # predictor supplied through `data`, the formula form is the one whose scoping does
    # not depend on where do.call was invoked from.
    frame <- list(y = d$y, X = d$X, off = d$off)
    args <- list(
      formula = y ~ 0 + X + offset(off),
      data = frame,
      family = poisson(),
      paraPen = list(X = list(d$S_age, d$S_year)),
      method = "REML",
      gamma = as.numeric(spec$gamma),
      control = control
    )
    if (!isTRUE(spec$free_sp)) {
      args$sp <- c(as.numeric(spec$lambda_age), as.numeric(spec$lambda_year))
    }
    m <- do.call(mgcv::gam, args)

    edf <- as.numeric(m$edf)
    tensor_idx <- seq_len(d$n_tensor)
    v <- vcov(m)
    dimnames(v) <- NULL
    # Vc exists ONLY when the smoothing parameters were estimated. vcov(unconditional =
    # TRUE) silently falls back to the conditional matrix with a warning when it does
    # not, so the presence of Vc is tested rather than the call's success.
    has_vc <- !is.null(m$Vc)
    vc <- if (has_vc) {
      x <- vcov(m, unconditional = TRUE)
      dimnames(x) <- NULL
      x
    } else {
      NULL
    }

    cells[[spec$name]] <- list(
      design = spec$design,
      levels = spec$levels,
      gamma = as.numeric(spec$gamma),
      free_sp = isTRUE(spec$free_sp),
      sp = as.numeric(m$sp),
      sp_supplied = if (isTRUE(spec$free_sp)) NULL else as.numeric(args$sp),
      penalty_scaling = penalty_scaling(m),
      coef = as.numeric(coef(m)),
      edf_total = sum(edf),
      edf_tensor = sum(edf[tensor_idx]),
      edf_factors = if (d$n_coef > d$n_tensor) sum(edf[-tensor_idx]) else 0,
      edf_per_coef = edf,
      deviance = as.numeric(m$deviance),
      null_deviance = as.numeric(m$null.deviance),
      scale = as.numeric(m$sig2),
      scale_estimated = isTRUE(m$scale.estimated),
      reml_score = as.numeric(m$gcv.ubre),
      n_iter = as.integer(m$iter),
      rank = as.integer(m$rank),
      converged = isTRUE(m$converged),
      # Mirrors the Python side's payload exactly: the full matrix only where the
      # comparison is exact (fixed sp), diagonals always, because a diagonal is what
      # lets an implementer bisect offline at p floats rather than p^2.
      vcov_unscaled = if (isTRUE(spec$free_sp)) NULL else v,
      vcov_diag = diag(v),
      vcov_unconditional_diag = if (has_vc) diag(vc) else NULL,
      has_unconditional = has_vc
    )
  }

  out <- list(
    schema_version = 1L,
    case = manifest$case,
    side = "mgcv",
    exchange_sha256 = exchange_sha256,
    mgcv_version = as.character(packageVersion("mgcv")),
    jsonlite_version = as.character(packageVersion("jsonlite")),
    r_version = R.version.string,
    scale_penalty = !scale_penalty_requested,
    r_session_info = paste(capture.output(print(sessionInfo())), collapse = "\n"),
    cells = cells
  )
  # digits = NA: full precision. Anything shorter would make a level-1 disagreement
  # partly a formatting artefact, which is the same reason the exchange uses %.17g.
  # matrix = "rowmajor" is stated rather than defaulted: the Python side reads each vcov
  # as a list of ROWS, and a column-major dump of a non-symmetric matrix would transpose
  # silently. (These are symmetric, so it would not even show up here — which is exactly
  # why the convention is pinned rather than left to hold by luck.)
  jsonlite::write_json(
    out, out_path,
    digits = NA, auto_unbox = TRUE, null = "null", matrix = "rowmajor"
  )
  cat(sprintf(
    "Wrote %s — %d cells over %d designs, mgcv %s, exchange %s\n",
    out_path, length(cells), length(designs), as.character(packageVersion("mgcv")),
    substr(exchange_sha256, 1, 12)
  ))
  invisible(NULL)
}

status <- tryCatch(
  {
    main(commandArgs(trailingOnly = TRUE))
    0L
  },
  error = function(e) {
    message("mgcv_conformance.R FAILED: ", conditionMessage(e))
    1L
  }
)
quit(status = status)
