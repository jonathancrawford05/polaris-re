#!/usr/bin/env Rscript
# =============================================================================
# ADR-190's decisive measurement, on the authoritative oracle.
# =============================================================================
# Is `vcov(m, unconditional = TRUE)` equal to `Vb + J V_rho J'`?
#
# ADR-189 amendment 1 refuted our Kass-Steffey correction against mgcv and blamed our
# arithmetic. ADR-190 refutes that diagnosis instead. The decisive step is this script:
# build `J V_rho J'` using NOTHING of ours -- mgcv's own coefficients at perturbed sp,
# mgcv's own outer Hessian, mgcv's own selected lambda -- and compare it against mgcv's
# own `Vc - Vp`. If the two agree, the formula is right and our arithmetic is wrong. If
# they do not, the formula is wrong and no amount of arithmetic will close the gap.
#
# WHY THIS IS A COMMITTED SCRIPT AND A CI STEP rather than a one-off.
# `ROUTINE_MGCV_PARITY.md` SETUP step 2 permits committing only TIER 3 numbers -- CI on
# the digest-pinned image -- because local apt R is a different mgcv release against a
# different BLAS. ADR-190 was first measured on tier 1 and PR #195's review correctly
# refused to let the ADR grant itself an exemption. This script is how the finding earns
# a tier-3 label instead of an argument for why it did not need one.
#
# It is DIAGNOSTIC, not a gate: it asserts nothing and cannot fail the build. The
# conformance comparison is what gates, and it is untouched by this file.
# =============================================================================
suppressPackageStartupMessages(library(mgcv))
suppressPackageStartupMessages(library(jsonlite))

args <- commandArgs(trailingOnly = TRUE)
exchange_dir <- if (length(args) >= 1) args[1] else "data/mgcv_exchange/synthetic"
out_path <- if (length(args) >= 2) args[2] else "ks_formula_probe.json"

manifest <- jsonlite::fromJSON(file.path(exchange_dir, "manifest.json"), simplifyVector = FALSE)

scale_penalty <- manifest$r_requirements$gam_control_scalePenalty
if (!is.logical(scale_penalty) || length(scale_penalty) != 1L || is.na(scale_penalty)) {
  stop("manifest.json has no usable r_requirements$gam_control_scalePenalty.")
}
control <- mgcv::gam.control(scalePenalty = scale_penalty)

load_design <- function(design_id) {
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
    S_age = read_penalty("penalty_age"), S_year = read_penalty("penalty_year")
  )
}

fit_at <- function(d, sp) {
  pp <- list(d$S_age, d$S_year)
  pp$sp <- as.numeric(sp)
  mgcv::gam(y ~ 0 + X + offset(off),
    data = list(y = d$y, X = d$X, off = d$off), family = poisson(),
    paraPen = list(X = pp), method = "REML", gamma = 1, control = control
  )
}

# The step must match KS_LOG_STEP in experience_gam_penalized.py: log(10) * REFINE_STEP,
# i.e. one refinement-grid step of 0.25 decade expressed in NATURAL log lambda. ADR-190
# measured the correction as converged to ~1.7% across an 8x sweep, so the exact value is
# not load-bearing -- but using a different one here would compare two different things.
h <- log(10) * 0.25

results <- list()
for (spec in manifest$cells) {
  if (!isTRUE(spec$free_sp)) next
  if (is.null(spec$gamma) || as.numeric(spec$gamma) != 1) next
  d <- load_design(spec$design)

  m <- mgcv::gam(y ~ 0 + X + offset(off),
    data = list(y = d$y, X = d$X, off = d$off), family = poisson(),
    paraPen = list(X = list(d$S_age, d$S_year)), method = "REML",
    gamma = 1, control = control
  )
  if (is.null(m$Vc)) {
    stop(sprintf("Cell '%s' produced no Vc; sp was not estimated.", spec$name))
  }
  hess <- m$outer.info$hess
  if (is.null(hess)) stop(sprintf("Cell '%s' exposed no outer.info$hess.", spec$name))

  sp <- as.numeric(m$sp)
  v_rho <- solve(hess)
  b_ap <- coef(fit_at(d, c(sp[1] * exp(h), sp[2])))
  b_am <- coef(fit_at(d, c(sp[1] * exp(-h), sp[2])))
  b_yp <- coef(fit_at(d, c(sp[1], sp[2] * exp(h))))
  b_ym <- coef(fit_at(d, c(sp[1], sp[2] * exp(-h))))
  jac <- cbind((b_ap - b_am) / (2 * h), (b_yp - b_ym) / (2 * h))

  delta_actual <- mean(diag(m$Vc - m$Vp))
  delta_formula <- mean(diag(jac %*% v_rho %*% t(jac)))
  base <- mean(diag(m$Vp))

  results[[spec$name]] <- list(
    design = spec$design,
    sp = sp,
    outer_hessian = as.numeric(hess),
    mean_diag_vp = base,
    mean_diag_vc = mean(diag(m$Vc)),
    mean_diag_vc_minus_vp = delta_actual,
    mean_diag_j_vrho_jt = delta_formula,
    ratio_actual_over_formula = delta_actual / delta_formula,
    inflation_reported = mean(diag(m$Vc)) / base,
    inflation_from_formula = 1 + delta_formula / base
  )
  cat(sprintf(
    "%-22s ratio %.4f | inflation from J V_rho J' %.4f vs mgcv reported %.4f\n",
    spec$name, delta_actual / delta_formula,
    1 + delta_formula / base, mean(diag(m$Vc)) / base
  ))
}

if (length(results) == 0L) stop("No free-sp gamma=1 cells found; nothing was measured.")

jsonlite::write_json(
  list(
    schema_version = 1L,
    r_version = R.version.string,
    mgcv_version = as.character(packageVersion("mgcv")),
    log_step_natural = h,
    scale_penalty = scale_penalty,
    cells = results
  ),
  out_path,
  auto_unbox = TRUE, digits = NA, pretty = TRUE
)
cat(sprintf("Wrote %s — %d cells, mgcv %s\n", out_path, length(results),
            as.character(packageVersion("mgcv"))))
