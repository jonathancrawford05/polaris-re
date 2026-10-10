#!/usr/bin/env Rscript
# =============================================================================
# Slice 10 step 2: is the coefficient `mgcv` eliminates from a rank-deficient fit a RULE?
# =============================================================================
# DIAGNOSTIC, asserts nothing, gates nothing (workflow step: continue-on-error).
# `mgcv` 1.9.x eliminates the unidentified coefficient in `gdiPK` (src/gdi.c): it forms
# M = [R1/||R1||_F ; Es/||Es||_F], R1 the R factor of sqrt(W) X T, Es = Eb T the balanced
# penalty root, T = U1 blockdiag(Qs, I) the sp-dependent stable reparameterisation, and
# takes the columns after the estimated rank in a LAPACK dgeqp3 (column-pivoted QR) of M.
# This script (a) reads which coefficient of T'beta is exactly eliminated in the fitted
# model, (b) re-runs that recipe on the inputs of the last gam.fit3 call, and (c) reports
# how tied the candidates are: the null vector v of M'M, and the spread of |v| over the
# candidates within 10% of its maximum. Candidates tied to ~1e-15 are decided by rounding
# noise in dgeqp3, so the choice is not a function of the model and data.
# Producer: mgcv only (a MEASUREMENT of mgcv against itself and its own recipe; no Polaris).
suppressPackageStartupMessages(library(mgcv))
suppressPackageStartupMessages(library(jsonlite))
args <- commandArgs(trailingOnly = TRUE)
out_path <- if (length(args) >= 1) args[1] else "gam_pivot_stability_probe.json"
.last <- NULL
suppressMessages(trace(mgcv:::gam.fit3,
  tracer = quote(.last <<- list(sp = sp, x = x, Eb = Eb, UrS = UrS, U1 = U1)),
  print = FALSE, where = asNamespace("mgcv")))
one <- function(label, form, seed, perm = 1:4, n = 300, k = 8) {
  set.seed(seed); x <- runif(n); lv <- letters[1:4]
  f <- factor(sample(lv, n, TRUE), levels = lv[perm])
  g3 <- factor(sample(c("p", "q", "r"), n, TRUE))
  y <- sin(2 * pi * x) + as.integer(factor(f, levels = lv)) * 0.2 * x + rnorm(n) * 0.3
  d <- data.frame(x = x, f = f, g = g3, y = y)
  fm <- switch(form,
    main = y ~ s(x, bs = "cr", k = k) + s(x, by = f, bs = "cr", k = k),
    fmain = y ~ f + s(x, bs = "cr", k = k) + s(x, by = f, bs = "cr", k = k),
    two_by = y ~ s(x, bs = "cr", k = k) + s(x, by = f, bs = "cr", k = k) + s(x, by = g, bs = "cr", k = k))
  m <- gam(fm, data = d, method = "REML")
  L <- .last; nm <- length(L$UrS)
  rp <- mgcv:::gam.reparam(L$UrS, L$sp[1:nm], 0)
  q <- ncol(L$x); T <- diag(q); T[1:ncol(rp$Qs), 1:ncol(rp$Qs)] <- rp$Qs; T <- L$U1 %*% T
  XT <- L$x %*% T; Es <- L$Eb %*% T
  qq <- qr(XT, LAPACK = TRUE); R1 <- qr.R(qq)[, order(qq$pivot)]
  M <- rbind(R1 / sqrt(sum(R1^2)), Es / sqrt(sum(Es^2)))
  pv <- qr(M, LAPACK = TRUE)$pivot; pred <- sort(tail(pv, q - m$rank))
  bT <- as.numeric(t(T) %*% coef(m)); obs <- which(abs(bT) < 1e-10 * max(abs(bT)))
  av <- abs(svd(M)$v[, q]); cand <- which(av > 0.9 * max(av))
  pv_c <- predict(m, se.fit = TRUE, unconditional = TRUE)$se.fit
  pv_p <- predict(m, se.fit = TRUE, unconditional = FALSE)$se.fit
  term_edf <- vapply(m$smooth, function(sm) sum(m$edf[sm$first.para:sm$last.para]), numeric(1))
  list(label = label, form = form, seed = seed, perm = paste(perm, collapse = ""), q = q,
       rank = m$rank, observed = as.list(sort(obs)), predicted = as.list(pred),
       predicted_equals_observed = setequal(pred, obs), n_candidates = length(cand),
       candidate_spread = (max(av[cand]) - min(av[cand])) / max(av),
       edf_total = sum(m$edf), term_edf = as.list(term_edf),
       se_vc_mean = mean(pv_c), se_vp_mean = mean(pv_p))
}
cases <- list()
for (s in 1:6) cases[[length(cases) + 1]] <- one("baseline", "main", s)
for (s in 1:6) cases[[length(cases) + 1]] <- one("relevel", "main", s, perm = c(2, 4, 1, 3))
for (s in 1:6) cases[[length(cases) + 1]] <- one("bare_main", "fmain", s)
for (s in 1:6) cases[[length(cases) + 1]] <- one("two_by", "two_by", s)
writeLines(jsonlite::toJSON(list(
  r_version = R.version.string, mgcv_version = as.character(packageVersion("mgcv")),
  openblas_num_threads = Sys.getenv("OPENBLAS_NUM_THREADS", "unset"), cases = cases),
  auto_unbox = TRUE, digits = 8, pretty = TRUE), out_path)
cat("wrote", out_path, "\n")
