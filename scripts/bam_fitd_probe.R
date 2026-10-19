#!/usr/bin/env Rscript
#
# bam_fitd_probe.R -- Slice R3 Stage B (ADR-260 amendments 2-4), checkpoint (iii).
#
# For each ILEC-SHAPED REPLICATED cell (many rows over few distinct covariate cells; the
# offset is continuous, so discrete.mf pads its frame to 1000 rows exactly as on the ILEC
# trial) this writes, to ONE JSON file:
#
#   * bam(method="fREML", discrete=TRUE) re-run with control = gam.control(maxit = k) for
#     k = 1, 2, ... until it converges: log(sp), eta, deviance, edf at EACH iteration.
#     That is the iteration trace polaris_re.gam.bam_fitd.bam_fitd is compared against.
#   * the design bam itself used (X rebuilt column by column through mgcv:::Xbd, and the
#     penalty list S/off from bam(fit=FALSE)). Polaris is handed THIS design in one
#     comparison (isolating the algorithm from the design: the design is an ECHO there) and
#     builds its OWN design in the other (the design is then part of what is compared).
#   * gam(method="REML") eta/edf on the same cell (the approximation-cost baseline;
#     REFERENCE_INTERNAL, never part of the parity claim).
#   * se of eta under bam's Vp, sqrt(rowSums((X %*% Vp) * X)).
#
# USAGE: Rscript scripts/bam_fitd_probe.R <out.json> [comma-separated cell names]
#   (the optional filter keeps the R-gated unit test to one cell)
suppressPackageStartupMessages({ library(mgcv); library(jsonlite) })

set.seed(20261017)
MAXK <- 60

make_cell <- function(name, formula, select) {
  g <- expand.grid(age = 40:80, dur = 1:20)
  g <- g[rep(seq_len(nrow(g)), each = 8), ]
  g$smoker <- factor(sample(c("NS", "S"), nrow(g), TRUE, prob = c(0.7, 0.3)))
  g$expo <- runif(nrow(g), 5, 60)
  lin <- -6 + 0.07 * (g$age - 40) - 0.03 * g$dur + 0.002 * (g$age - 60) * g$dur / 10 +
    0.3 * (g$smoker == "S") + 0.01 * (g$smoker == "S") * (g$age - 60)
  g$y <- rpois(nrow(g), g$expo * exp(lin))
  list(name = name, formula = formula, select = select, data = g, export_design = TRUE)
}

# The DISCRIMINATING cell: many rows over few distinct covariate cells (98 ages x 26 durations x
# 12 replicates), a lognormal exposure offset, low counts (~0.1 death per row) and a surface that
# needs smoothing. Tier 1 (R 4.3.3 / mgcv 1.9.1) puts exact-REML gam 1.25e-2 from bam(discrete=TRUE)
# here, i.e. the same order as the 1.9e-2..2.1e-2 seen on the real ILEC cells, so agreement to
# the 2e-2 gate means something on this cell. (On a high-signal cell gam and bam agree to 1e-4 and
# any fitter passes.)
make_ilec_shaped <- function() {
  set.seed(20261017)  # own seed: the draw matters (a flat REML surface is what makes gam and bam differ)
  g <- expand.grid(age = 20:117, dur = 1:26)
  g <- g[rep(seq_len(nrow(g)), each = 12), ]
  g$smoker <- factor("NS")
  g$expo <- rlnorm(nrow(g), log(15), 1.2)
  ageeff <- 0.045 * (g$age - 60) + 0.0004 * (g$age - 60)^2 + 0.35 * sin((g$age - 20) / 9)
  lin <- -7 + ageeff - 0.06 * g$dur + 0.15 * (g$dur > 10) * sin(g$dur / 3) +
    0.003 * (g$age - 60) * g$dur / 5
  g$y <- rpois(nrow(g), g$expo * exp(lin))
  list(name = "ilec_shaped_replicated",
       formula = 'y ~ s(age, bs="cr", k=13) + s(dur, bs="cr", k=6) + ti(age, dur, bs="cr", k=c(13,6)) + offset(log(expo))',
       select = FALSE, data = g, export_design = TRUE)
}

# UNBALANCED factor-by + select=TRUE cell (ADR-260 amendment 9/10): rows per age fall off steeply
# with age and the third smoker level is rare, so colMeans over the DATA rows and colMeans over the
# distinct covariate values (what discrete.mf's compressed frame gives bam) differ. The select=TRUE
# null-space penalty is coordinate-dependent, so this is where the two constraints give different models.
make_unbalanced <- function() {
  set.seed(20261018)
  g <- expand.grid(age = 20:99, dur = 1:12, smoker = factor(c("NS", "S", "U")))
  keep <- (g$smoker == "NS") | (g$smoker == "S" & g$age < 90) | (g$smoker == "U" & g$age >= 35 & g$age < 80)
  g <- g[keep, ]
  reps <- pmax(1L, as.integer(round(40 * exp(-0.045 * (g$age - 20)) * ifelse(g$smoker == "U", 0.15, 1))))
  g <- g[rep(seq_len(nrow(g)), times = reps), ]
  g$expo <- rlnorm(nrow(g), log(30), 1.0)
  lin <- -7 + 0.055 * (g$age - 40) + 0.0004 * (g$age - 60)^2 - 0.04 * g$dur +
    c(NS = 0, S = 0.4, U = 0.1)[as.character(g$smoker)] * (1 + sin(g$age / 12))
  g$y <- rpois(nrow(g), g$expo * exp(lin))
  list(name = "unbalanced_factor_by_select",
       formula = 'y ~ smoker + s(dur, bs="cr", k=5) + s(age, bs="cr", k=10, by=smoker) + offset(log(expo))',
       select = TRUE, data = g, export_design = TRUE)
}

# RANK-DEFICIENT cell (ADR-256): a bare s(age) beside s(age, by=smoker) over ALL smoker levels shares
# the penalty null space, so one direction is unidentified. bam pivots its Cholesky; Polaris pivots the
# design (as its REML path does). Design is not exported (bam's has the redundant column).
make_rank_deficient <- function() {
  set.seed(20261019)
  g <- expand.grid(age = 30:85, dur = 1:15, smoker = factor(c("NS", "S", "U")))
  reps <- pmax(1L, as.integer(round(14 * exp(-0.03 * (g$age - 30)) * ifelse(g$smoker == "U", 0.3, 1))))
  g <- g[rep(seq_len(nrow(g)), times = reps), ]
  g$expo <- rlnorm(nrow(g), log(25), 0.8)
  lin <- -7 + 0.06 * (g$age - 40) - 0.04 * g$dur + c(NS = 0, S = 0.35, U = 0.1)[as.character(g$smoker)] *
    (1 + 0.5 * sin(g$age / 10))
  g$y <- rpois(nrow(g), g$expo * exp(lin))
  list(name = "rank_deficient_bare_plus_factor_by",
       formula = 'y ~ smoker + s(age, bs="cr", k=10) + s(age, bs="cr", k=8, by=smoker) + s(dur, bs="cr", k=5) + offset(log(expo))',
       select = FALSE, data = g, export_design = FALSE)
}

# BINOMIAL(cloglog) cell with prior weights (the S1 shape: a proportion response, weights = trials).
make_binomial <- function() {
  set.seed(20261019)
  g <- expand.grid(age = 40:80, dur = 1:15)
  g <- g[rep(seq_len(nrow(g)), each = 3), ]
  g$smoker <- factor(sample(c("NS", "S"), nrow(g), TRUE, prob = c(0.7, 0.3)))
  g$n <- sample(40:400, nrow(g), TRUE)
  lin <- -4.2 + 0.05 * (g$age - 40) - 0.05 * g$dur + 0.4 * (g$smoker == "S") + 0.3 * sin(g$age / 9)
  g$y <- rbinom(nrow(g), g$n, 1 - exp(-exp(lin))) / g$n
  list(name = "binomial_cloglog_weights",
       formula = 'y ~ smoker + s(age, bs="cr", k=10) + s(dur, bs="cr", k=5)',
       family = 'binomial(link="cloglog")', weights = "n",
       select = FALSE, data = g, export_design = TRUE)
}

cells <- list(
  make_cell("ti_plain",
    'y ~ s(age, bs="cr", k=10) + s(dur, bs="cr", k=5) + ti(age, dur, bs="cr", k=c(8,4)) + offset(log(expo))',
    FALSE),
  make_cell("ti_select",
    'y ~ s(age, bs="cr", k=10) + s(dur, bs="cr", k=5) + ti(age, dur, bs="cr", k=c(8,4)) + offset(log(expo))',
    TRUE),
  make_cell("factor_by_select",
    'y ~ smoker + s(dur, bs="cr", k=5) + s(age, bs="cr", k=8, by=smoker) + offset(log(expo))',
    TRUE),
  make_ilec_shaped(),
  make_unbalanced(),
  make_rank_deficient(),
  make_binomial())

# ---- seed sensitivity (REFERENCE_INTERNAL: mgcv against mgcv) --------------------------------
# discrete.mf pads each variable's unique values with a seeded sample() (seed 8547, hard-coded).
# Patch that constant in the namespace copy and re-run bam: the spread of eta across seeds is the
# reference's OWN noise floor, the yardstick for any residual attributed to the padded frame.
SEEDS <- c(8547, 1, 2, 3, 4, 5, 6)
orig_discrete_mf <- get("discrete.mf", asNamespace("mgcv"))
replace_const <- function(e, from, to) {
  if (is.numeric(e) && length(e) == 1 && e == from) return(to)
  if (is.call(e)) {
    for (i in seq_along(e)) if (!is.null(e[[i]])) e[[i]] <- replace_const(e[[i]], from, to)
    return(e)
  }
  e
}
set_discrete_seed <- function(seed) {
  f <- orig_discrete_mf
  body(f) <- replace_const(body(orig_discrete_mf), 8547, seed)
  assignInNamespace("discrete.mf", f, ns = "mgcv")
}
seed_sensitivity <- function(form, g, select, fam, wts) {
  on.exit(assignInNamespace("discrete.mf", orig_discrete_mf, ns = "mgcv"))
  out <- list()
  for (sd in SEEDS) {
    set_discrete_seed(sd)
    b <- suppressWarnings(bam(form, data = g, family = fam, weights = wts, method = "fREML", discrete = TRUE,
      select = select))
    out[[length(out) + 1]] <- list(seed = sd, eta = as.numeric(b$linear.predictors),
      edf_total = sum(b$edf), iter = b$iter, log_sp = log(as.numeric(b$sp)))
  }
  out
}

design_of <- function(G) {
  npar <- length(G$term.names)
  X <- vapply(seq_len(npar), function(j) {
    cf <- numeric(npar); cf[j] <- 1
    as.numeric(Xbd(G$Xd, cf, G$kd, G$ks, G$ts, G$dt, G$v, G$qc, G$drop))
  }, numeric(nrow(G$mf)))
  X
}

run_cell <- function(cell) {
  g <- cell$data; form <- as.formula(cell$formula)
  fam_txt <- if (is.null(cell$family)) "poisson()" else cell$family
  fam <- eval(parse(text = fam_txt))
  wts <- if (is.null(cell$weights)) NULL else g[[cell$weights]]
  fit <- function(maxit) suppressWarnings(bam(form, data = g, family = fam, weights = wts, method = "fREML",
    discrete = TRUE, select = cell$select, control = gam.control(maxit = maxit)))
  trace <- list()
  for (k in seq_len(MAXK)) {
    b <- fit(k)
    trace[[k]] <- list(maxit = k, iter = b$iter, converged = isTRUE(b$mgcv.conv),
      log_sp = log(as.numeric(b$sp)), eta = as.numeric(b$linear.predictors),
      edf = as.numeric(b$edf), deviance = b$deviance)
    if (isTRUE(b$mgcv.conv)) break
  }
  final <- b
  # The design bam used (small cells only). Xbd evaluates the discretised design at the n data
  # rows through the index matrix G$kd, so X is n x p; S/off are bam's penalties.
  X <- NULL; pen <- NULL
  if (isTRUE(cell$export_design)) {
    G <- suppressWarnings(bam(form, data = g, family = fam, weights = wts, method = "fREML", discrete = TRUE,
      select = cell$select, fit = FALSE))
    npar <- length(G$term.names)
    X <- vapply(seq_len(npar), function(j) {
      cf <- numeric(npar); cf[j] <- 1
      as.numeric(Xbd(G$Xd, cf, G$kd, G$ks, G$ts, G$dt, G$v, G$qc, G$drop))
    }, numeric(nrow(g)))
    pen <- lapply(seq_along(G$S), function(i) list(S = G$S[[i]], off = G$off[i]))
  }
  # X depends on the covariates only, so ship its UNIQUE rows plus a row -> unique-row index
  # (1-based); Polaris expands it. 30,576 rows x 78 columns would be ~40 MB of JSON.
  X_unique <- NULL; X_index <- NULL
  if (!is.null(X)) {
    key <- paste(g$age, g$dur, as.character(g$smoker))
    first <- !duplicated(key)
    X_unique <- X[first, , drop = FALSE]
    X_index <- match(key, key[first])
  }
  # Checkpoint (i) (ADR-260 amendment 2 rule 4): mgcv's own discretised accumulation at FIXED
  # deterministic weights/working response, X'WX via XWXd and X'Wz via XWyd.
  acc <- NULL
  if (isTRUE(cell$export_design)) {
    wfix <- 0.5 + (seq_len(nrow(g)) %% 7) / 4; zfix <- sin(seq_len(nrow(g)) / 37)
    acc <- list(w = wfix, z = zfix,
      xwx = XWXd(G$Xd, wfix, G$kd, G$ks, G$ts, G$dt, G$v, G$qc, 1, G$drop, -1, -1, -1),
      xwy = as.numeric(XWyd(G$Xd, wfix, zfix, G$kd, G$ks, G$ts, G$dt, G$v, G$qc, G$drop, -1, -1, -1)))
  }
  se <- as.numeric(predict(final, se.fit = TRUE, type = "link")$se.fit)
  m <- suppressWarnings(gam(form, data = g, family = fam, weights = wts, method = "REML", select = cell$select))
  list(name = cell$name, formula = cell$formula, select = cell$select, n = nrow(g),
    p = length(coef(final)),
    unique_age_dur = nrow(unique(g[c("age", "dur")])),
    data = c(list(age = g$age, dur = g$dur, smoker = as.character(g$smoker), y = g$y),
      if (!is.null(g$expo)) list(expo = g$expo), if (!is.null(wts)) list(n = as.numeric(wts))),
    family = fam_txt, weights = cell$weights,
    X_unique = X_unique, X_index = X_index, pen = pen, trace = trace, accumulation = acc,
    final = list(log_sp = log(as.numeric(final$sp)), eta = as.numeric(final$linear.predictors),
      edf = as.numeric(final$edf), edf_total = sum(final$edf), se = se, iter = final$iter,
      converged = isTRUE(final$mgcv.conv)),
    seeds = seed_sensitivity(form, g, cell$select, fam, wts),
    gam = list(eta = as.numeric(m$linear.predictors), edf_total = sum(m$edf),
      log_sp = log(as.numeric(m$sp))))
}

args <- commandArgs(trailingOnly = TRUE)
if (length(args) >= 2) {
  keep <- strsplit(args[[2]], ",")[[1]]
  cells <- Filter(function(c) c$name %in% keep, cells)
}
out <- list(mgcv_version = as.character(packageVersion("mgcv")), r_version = R.version.string,
            cells = lapply(cells, run_cell))
jsonlite::write_json(out, args[[1]], digits = I(17), auto_unbox = TRUE, null = "null", na = "null",
                     matrix = "rowmajor")
cat("wrote", args[[1]], "\n")
for (c in out$cells) cat(sprintf("%s: n=%d p=%d iters=%d conv=%s\n", c$name, c$n, c$p,
  c$final$iter, c$final$converged))
