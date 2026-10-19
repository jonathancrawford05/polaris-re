#!/usr/bin/env Rscript
#
# bam_local_design_probe.R -- Slice R3 Stage B, MAINTAINER-RUN (real cells, tier L).
#
# The DESIGN-CONDITIONED diagnostic on a REAL cell (ADR-260 amendment 8). Writes, into <out_dir>
# (scratch, never committed): bam's own design X (rebuilt column by column through mgcv:::Xbd, as
# raw float64, column-major), its penalties S/off, and the bam(maxit = 1..K) iteration trace
# (log(sp) and eta per iteration). bam_local_design_run.py hands X and S to Polaris's bam_fitd
# and reduces the comparison to scalars. By the ADR-193 mechanical test that comparison is ECHO
# (Polaris is handed mgcv's design), a diagnostic: it separates "the design differs" from "the
# algorithm differs" on the one cell where the two engines disagree by 1.19.
#
# USAGE: Rscript scripts/bam_local_design_probe.R <cells.csv> <spec.json> <out_dir> [max_iter=30]
suppressPackageStartupMessages({ library(mgcv); library(jsonlite) })

main <- function(argv) {
  stopifnot(length(argv) >= 3)
  maxk <- if (length(argv) >= 4) as.integer(argv[[4]]) else 30L
  spec <- jsonlite::read_json(argv[[2]], simplifyVector = FALSE)
  d <- utils::read.csv(argv[[1]], stringsAsFactors = FALSE)
  for (nm in names(spec$factors)) d[[nm]] <- factor(d[[nm]], levels = unlist(spec$factors[[nm]]))
  fam <- eval(parse(text = paste0(spec$family, if (grepl("\\(", spec$family)) "" else "()")))
  w <- if (is.null(spec$weights)) NULL else d[[spec$weights]]
  f <- as.formula(spec$formula)
  sel <- isTRUE(spec$select)
  out <- argv[[3]]; dir.create(out, showWarnings = FALSE, recursive = TRUE)

  G <- suppressWarnings(mgcv::bam(f, data = d, family = fam, weights = w, method = "fREML",
                                  discrete = TRUE, select = sel, fit = FALSE))
  npar <- length(G$term.names)
  con <- file(file.path(out, "X.bin"), "wb")
  for (j in seq_len(npar)) {
    cf <- numeric(npar); cf[j] <- 1
    writeBin(as.numeric(Xbd(G$Xd, cf, G$kd, G$ks, G$ts, G$dt, G$v, G$qc, G$drop)), con)
  }
  close(con)
  pen <- lapply(seq_along(G$S), function(i) list(S = G$S[[i]], off = G$off[i]))
  trace_lsp <- list(); con <- file(file.path(out, "trace_eta.bin"), "wb"); K <- 0L
  for (k in seq_len(maxk)) {
    m <- suppressWarnings(mgcv::bam(f, data = d, family = fam, weights = w, method = "fREML",
      discrete = TRUE, select = sel, control = gam.control(maxit = k)))
    writeBin(as.numeric(m$linear.predictors), con)
    trace_lsp[[k]] <- log(as.numeric(m$sp)); K <- k
    cat(sprintf("maxit %d: iter %d converged %s\n", k, m$iter, isTRUE(m$mgcv.conv)))
    if (isTRUE(m$mgcv.conv)) break
  }
  close(con)
  jsonlite::write_json(list(n = nrow(d), p = npar, K = K, pen = pen, trace_log_sp = trace_lsp,
    mgcv_version = as.character(packageVersion("mgcv")), r_version = R.version.string),
    file.path(out, "meta.json"), digits = I(17), auto_unbox = TRUE, matrix = "rowmajor")
  cat("wrote", out, "\n")
}
if (sys.nframe() == 0L) main(commandArgs(trailingOnly = TRUE))
