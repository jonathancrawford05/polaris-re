#!/usr/bin/env Rscript
#
# gam_real_data_trial_rehearsal_probe.R -- Slice R2 (docs/PLAN_gam_real_data_readiness.md,
# ADR-259): a SYNTHETIC dress rehearsal of the ILEC trial, run in the pinned oracle image.
#
# Why it exists: the trial itself runs on the maintainer's machine on data this repository never
# holds. Before that trip, the SAME formula strings, the SAME mgcv extraction
# (extract_mgcv in scripts/gam_real_data_trial.R, sourced here) and the SAME Python comparison
# (polaris_re.gam.real_data_trial.compare) are exercised at tier 3 on synthetic cells
# that have the real data's STRUCTURE: integer issue ages, a policy-year duration, the banded
# durations' representative values, attained age = issue age + duration - 1 (a parallelogram
# support, not a rectangle), exposures, Poisson deaths. Nothing here is ILEC data.
#
# mgcv fits gam(<formula>, method = "REML") on each cell; Polaris reads only the "data" keys
# and the formula name (scripts/gam_real_data_trial_rehearsal_compare.py).
#
# USAGE: Rscript scripts/gam_real_data_trial_rehearsal_probe.R [out.json]
suppressPackageStartupMessages({ library(mgcv); library(jsonlite) })
source("scripts/gam_real_data_trial.R")   # defines extract_mgcv; does not run main()

# Formula strings: copies of polaris_re.gam.real_data_trial.FORMULAS. The compare
# script ASSERTS equality with the Python table, so a drift fails loudly.
T1S <- 's(attained_age, bs="cr", k=13) + s(duration, bs="cr", k=6) + ti(attained_age, duration, bs="cr", k=c(13, 6))'
T2B <- "face_band + smoker + face_band:smoker"
forms <- list(
  T1  = list(formula = paste0("deaths ~ ", T1S, " + offset(log_exposure)"), select = FALSE),
  T2  = list(formula = paste0("deaths ~ ", T1S, " + ", T2B, " + offset(log_exposure)"), select = FALSE),
  T3c = list(formula = paste0('deaths ~ s(duration, bs="cr", k=6) + ', T2B,
                              ' + s(attained_age, bs="cr", k=13, by=smoker) + offset(log_exposure)'),
             select = TRUE))

make_cells <- function(seed) {
  set.seed(seed)
  g <- expand.grid(issue = seq(25, 64, 3), duration = 1:26,
                   calendar_year = 2014:2016, smoker = c("NS", "S", "U"),
                   face_band = c("B00", "B01", "B02"), stringsAsFactors = FALSE)
  g$attained_age <- g$issue + g$duration - 1
  e <- runif(nrow(g), 5, 120)
  q <- exp(-9.5 + 0.085 * g$attained_age - 0.0009 * (g$attained_age - 50)^2 -
           0.9 * exp(-g$duration / 4) + 0.02 * sin(g$calendar_year / 1.7) +
           0.012 * (g$attained_age - 50) * exp(-g$duration / 5)) * ifelse(g$smoker == "S", 1.6, 1)
  g$exposure <- e; g$log_exposure <- log(e)
  g$deaths <- as.numeric(rpois(nrow(g), e * q * 2))
  g[, c("attained_age", "duration", "smoker", "face_band", "exposure", "log_exposure", "deaths")]
}

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_real_data_trial_rehearsal_probe.json"
  cells <- list()
  for (seed in c(7001, 7002)) {
    d <- make_cells(seed)
    d$smoker <- factor(d$smoker, levels = c("NS", "S", "U"))
    d$face_band <- factor(d$face_band, levels = c("B00", "B01", "B02"))
    for (nm in names(forms)) {
      f <- forms[[nm]]
      t <- system.time(m <- mgcv::gam(as.formula(f$formula), data = d, family = poisson(),
                                       method = "REML", select = f$select))[["elapsed"]]
      cells[[length(cells) + 1]] <- list(
        name = sprintf("%s_seed%d", nm, seed), formula_name = nm, formula = f$formula,
        select = f$select, seed = seed,
        data = lapply(as.list(d), function(col) if (is.factor(col)) as.character(col) else col),
        mgcv = extract_mgcv(m, t))
    }
  }
  jsonlite::write_json(list(schema_version = 1L, mgcv_version = as.character(packageVersion("mgcv")),
    r_version = R.version.string, cells = cells), out_path, digits = NA, auto_unbox = TRUE,
    null = "null", na = "null")
  cat(sprintf("Wrote %s -- %d cells, mgcv %s\n", out_path, length(cells),
              as.character(packageVersion("mgcv"))))
}
status <- tryCatch({ main(commandArgs(trailingOnly = TRUE)); 0L },
  error = function(e) { message("gam_real_data_trial_rehearsal_probe.R FAILED: ", conditionMessage(e)); 1L })
quit(status = status)
