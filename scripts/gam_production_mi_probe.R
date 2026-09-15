#!/usr/bin/env Rscript
#
# gam_production_mi_probe.R -- production wiring epic, PLAN slice 1
# (docs/PLAN_gam_production_wiring.md, docs/CONTINUATION_gam_production_wiring.md).
#
# WHAT THIS PROBES, AND WHY IT IS DIFFERENT FROM EVERY OTHER PROBE HERE
# --------------------------------------------------------------------
# Every other gam_*_probe.R in this directory fits a TEST STRUCTURE invented by
# the parity epic. This one fits the model form the SHIPPED DASHBOARD actually
# renders -- `analytics/experience_gam.TensorMIModel`, reached from
# `dashboard/views/experience_improvement.py`:
#
#   deaths ~ offset(log(exposure * q_base))
#          + te(attained_age, calendar_year)     # the MI surface
#          + s(duration_years)                   # residual duration smooth
#          + SUM factors                         # parametric, see LIMITS below
#   family = poisson(link = "log")               # the COUNT basis
#
# In seven weeks of parity work this formula has never been measured against
# mgcv. That is what this probe exists to make possible.
#
# TWO FITS, NOT ONE -- AND THE SECOND ONE IS THE POINT
# ----------------------------------------------------
# `assemble_model_design` (src/polaris_re/analytics/gam_model.py) dispatches
# "cr" / "ti" / "sz" and RAISES on anything else. There is no `te`. The plan's
# blocker A proposes re-expressing
#
#   te(x, z)  ==  s(x) + s(z) + ti(x, z)
#
# and is explicit that this is a HYPOTHESIS, NOT AN IDENTITY: the ANOVA
# decomposition spans the same space, but te carries ONE penalty per margin
# over the whole tensor while the decomposition carries a separate smoothing
# parameter for each of s(x), s(z) and (two for) ti(x, z). Same span, different
# penalty => different fit, in general.
#
# So this probe fits BOTH forms, natively, with mgcv choosing its own smoothing
# parameters in each case:
#
#   m_te     -- the TARGET form.        te(age, year) + s(duration)
#   m_anova  -- the RE-EXPRESSION.      s(age) + s(year) + ti(age, year) + s(duration)
#
# Exporting both lets the Python comparator answer three separable questions
# instead of one conflated one:
#
#   (1) Polaris vs m_anova  -- does our engine reproduce the spec we CAN express?
#                              (INDEPENDENT; a parity question about Polaris)
#   (2) Polaris vs m_te     -- does what we can express reproduce the TARGET?
#                              (INDEPENDENT; the question Anchor W6 gates on)
#   (3) m_anova vs m_te     -- are the two forms the same fit AT ALL?
#                              (INDEPENDENT, but entirely inside R -- real
#                               evidence about mgcv, NONE about Polaris; the
#                               same class as the smoothCon/lpmatrix guard,
#                               docs/VERIFICATION_STANDARD.md Sec. 5)
#
# (3) is the localiser, and it is why both fits are exported rather than just
# the target. If (2) fails while (1) passes and (3) fails by a comparable
# amount, the finding is about the RE-EXPRESSION, not about our engine -- and
# that is a fact about mgcv that no amount of Polaris solver work would change.
#
# A THIRD FIT, TO CLOSE THE OBVIOUS OBJECTION TO (3)
# --------------------------------------------------
# mgcv's OWN ?ti documentation spells the decomposition `ti(x) + ti(z) +
# ti(x,z)`, not `s(x) + s(z) + ti(x,z)`, and demonstrates it beside `te(x,z)`
# as a DIFFERENT model ("tensor product" vs "tensor anova"). So the first
# challenge to a refutation of blocker A is "you tested the wrong
# decomposition". `m_ti_anova` below settles that by measurement rather than
# by argument -- see the `anova_spelling` block.
#
# THE k MAPPING IS DERIVED, NOT CHOSEN (PLAN Anchor 4: k is an input)
# -------------------------------------------------------------------
# The dashboard's margins are patsy `bs(col, df=D)` -- D columns, no intercept.
# mgcv's `s(x, bs="cr", k=K)` carries K basis functions, K-1 after the
# sum-to-zero constraint. So K = D + 1 reproduces the dashboard's own margin
# WIDTH exactly, and the block totals then agree cell for cell:
#
#   dashboard tensor block: age(6) + year(4) + age:year(6*4=24)      = 34
#   te(k = c(7, 5))       : 7*5 - 1                                  = 34
#   duration              : bs(duration_years, df=4)                 =  4
#   s(duration, k = 5)    : 5 - 1                                    =  4
#
# D comes from the page's own widget defaults (age_df=6, year_df=4 --
# dashboard/views/experience_improvement.py; duration_df=4 -- TensorMIModel's
# own default). Nothing here is tuned to make a comparison come out.
#
# KNOTS ARE SUPPLIED, NOT DEFAULTED (PLAN Anchor 4)
# --------------------------------------------------
# Both sides build from the same explicit knot vectors, the same way every
# slice-5/7 probe does, so a disagreement can never be knot placement. They
# span the recipe's own covariate ranges; they are inputs, not fitted.
#
# WHAT THIS PROBE DELIBERATELY DOES NOT COVER (state the limits up front)
# ----------------------------------------------------------------------
#  * THE AMOUNT BASIS. Quasi-Poisson, and `gam_reml.reml_score_general` raises
#    on `dispersion_fixed=False` -- the plan's blocker B. Count basis only,
#    which is PLAN slice 1's own stated scope.
#  * THE PARAMETRIC FACTOR BLOCK (`SUM factors`). `assemble_model_design` builds
#    an unpenalized intercept and then penalized cr/ti/sz terms; it has no way
#    to carry unpenalized parametric COLUMNS. So the recipe below carries no
#    factor column, and the measured form is the dashboard's formula with an
#    empty factor block -- which is exactly what the page fits on a frame whose
#    candidate factors are single-level. This is a SECOND expressibility gap
#    beside blocker A, named here rather than papered over.
#  * ANY BAND. Anchor W2 -- the point estimate and the interval are separate
#    slices, never the same one.
#
# WHY THE COMPARISON IS ON eta / edf, NEVER coef (PLAN Anchor 2)
# ---------------------------------------------------------------
# mgcv reparameterises internally, so coef is basis-dependent and eta is not.
# coef is exported for diagnostic reading only and is never compared. The gate
# is ADR-221's committed criterion -- eta and edf_total -- NOT raw log10(sp)
# (Anchor W5 forbids this epic re-gating anything; sp is reported, not gated).
#
# REQUIREMENTS: R with mgcv and jsonlite.
# USAGE:  Rscript scripts/gam_production_mi_probe.R [output.json]
# EXIT STATUS: 0 on a completed run, 1 on any R-side error.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_production_mi_probe.json"
  set.seed(20260915) # ADR-074: pinned, never the wall clock. Distinct from every
  # existing probe seed (20260825 / 20260901 / 20260902) -- a genuinely new draw.

  # --- The recipe: grouped experience cells, the shape the page is handed. ----
  # A full (age x calendar-year x duration-band) grid, which is what
  # `attach_base_rate` + a group_by produce upstream of TensorMIModel -- not a
  # scatter of random points. The design's balance matters here: te and its
  # ANOVA decomposition differ in PENALTY, and how that difference expresses
  # itself depends on the design it is applied to.
  # Age grain is every 2 years rather than every 5: grouped experience cells
  # are keyed on INTEGER attained age upstream, and a coarse age axis starves
  # the age margin (`cr` needs at least k distinct covariate values, so a
  # 5-year grid caps k at 9 and cannot carry the k-axis sweep below at all).
  ages <- seq(45, 85, by = 2)
  years <- 2010:2021
  durations <- c(2, 7, 12, 17, 22)
  grid <- expand.grid(
    attained_age = ages, calendar_year = years, duration_years = durations
  )
  n <- nrow(grid)

  attained_age <- grid$attained_age
  calendar_year <- grid$calendar_year
  duration_years <- grid$duration_years

  # A static base table (Design Anchor 1 -- TensorMIModel refuses a generational
  # base), Makeham-shaped and a function of attained age ALONE.
  q_base <- 0.0004 + 0.00003 * exp(0.085 * (attained_age - 45))

  # Exposure: heaviest at mid ages and mid durations, thinning at the edges --
  # the sparsity pattern that makes the age>=80 corner of a real book hard.
  exposure <- round(
    9000 * exp(-((attained_age - 62) / 26)^2) *
      exp(-((duration_years - 10) / 16)^2) *
      (1 + 0.03 * (calendar_year - 2010))
  )

  # The truth: AGE-VARYING mortality improvement (the thing the page exists to
  # show), a mild age wiggle, and a residual duration effect.
  log_rr <- -0.014 * (calendar_year - 2015) * (1 + 0.012 * (attained_age - 65)) +
    0.05 * sin(attained_age / 11) +
    -0.18 * exp(-duration_years / 9)
  deaths <- rpois(n, lambda = exposure * q_base * exp(log_rr))

  log_offset <- log(exposure * q_base)

  # --- Knots: INPUTS, spanning the recipe's own ranges (PLAN Anchor 4). -------
  age_knots <- c(45, 50, 57, 65, 72, 79, 85) # k = 7  -> 6 cols (age_df = 6)
  year_knots <- c(2010, 2013, 2016, 2019, 2021) # k = 5  -> 4 cols (year_df = 4)
  duration_knots <- c(2, 6, 11, 16, 22) # k = 5  -> 4 cols (duration_df = 4)

  df <- data.frame(
    attained_age = attained_age,
    calendar_year = calendar_year,
    duration_years = duration_years,
    exposure = exposure,
    q_base = q_base,
    deaths = deaths,
    log_offset = log_offset
  )
  knots_arg <- list(
    attained_age = age_knots,
    calendar_year = year_knots,
    duration_years = duration_knots
  )

  # --- Fit 1: the TARGET form, te(). ----------------------------------------
  m_te <- mgcv::gam(
    deaths ~ te(attained_age, calendar_year, bs = "cr", k = c(7, 5)) +
      s(duration_years, bs = "cr", k = 5),
    data = df, family = poisson(link = "log"), offset = log_offset,
    knots = knots_arg, method = "REML"
  )

  # --- Fit 2: the RE-EXPRESSION, s() + s() + ti(). ---------------------------
  # Same data, same knots, same family/link/offset, same method. The ONLY
  # difference is the decomposition of the age x year surface, which is exactly
  # the difference blocker A is about.
  m_anova <- mgcv::gam(
    deaths ~ s(attained_age, bs = "cr", k = 7) +
      s(calendar_year, bs = "cr", k = 5) +
      ti(attained_age, calendar_year, bs = "cr", k = c(7, 5)) +
      s(duration_years, bs = "cr", k = 5),
    data = df, family = poisson(link = "log"), offset = log_offset,
    knots = knots_arg, method = "REML"
  )

  # ------------------------------------------------------------------------
  # eta IS `m$linear.predictors`, NOT `predict(m, type = "link")`. This is not
  # a stylistic choice and it is not interchangeable.
  #
  # mgcv's `predict.gam(type = "link")` does NOT add back an offset that was
  # supplied through gam()'s own `offset=` ARGUMENT (as opposed to an
  # `offset()` term written inside the formula). `m$linear.predictors` does.
  # Polaris's `fit_polaris_gam` computes `eta = offset + X %*% coef`, so
  # `m$linear.predictors` is the like-for-like quantity and
  # `predict(type = "link")` is off by exactly the offset vector.
  #
  # Measured, on this recipe (tier 1), while writing this probe: using
  # `predict(type = "link")` made `max|d eta|` read 1.9751 against ADR-221's
  # 2e-2 bound -- a spurious 99x "failure" that was entirely
  # `max(log(exposure * q_base))`. The true reading is 6.85e-05. Every
  # existing probe here is unaffected because none of them uses an offset
  # (the parity epic's target formula uses weights -- PLAN Anchor 5's table),
  # which is exactly why this trap had not been hit before and why the
  # dashboard's own Poisson-offset form is where it first appears.
  #
  # The R-internal te-vs-anova reading below is invariant either way, since a
  # common offset cancels in the difference -- but it is computed from the
  # same corrected quantity so that one definition of eta is used throughout.
  # ------------------------------------------------------------------------
  eta_te <- as.numeric(m_te$linear.predictors)
  eta_anova <- as.numeric(m_anova$linear.predictors)

  # ------------------------------------------------------------------------
  # SPAN EQUIVALENCE, MEASURED RATHER THAN INFERRED FROM COLUMN COUNTS.
  #
  # The whole localisation this probe supports is "same span, DIFFERENT
  # penalty". Equal column counts are NECESSARY for that and nowhere near
  # SUFFICIENT -- two 39-column bases can span different 39-dimensional
  # subspaces. So test containment both ways directly: project each design's
  # columns onto the other's column space and report the worst residual. Zero
  # (to machine precision) in both directions IS mutual containment, i.e. the
  # two column spaces are the same subspace.
  #
  # If these ever read non-zero, the finding changes shape entirely: the forms
  # would differ in BASIS as well as penalty, and "the difference localises to
  # the penalty construction" would be wrong.
  # ------------------------------------------------------------------------
  x_te <- predict(m_te, type = "lpmatrix")
  x_anova <- predict(m_anova, type = "lpmatrix")
  span_residual_anova_in_te <- max(abs(x_anova - qr.fitted(qr(x_te), x_anova)))
  span_residual_te_in_anova <- max(abs(x_te - qr.fitted(qr(x_anova), x_te)))
  rank_te <- qr(x_te)$rank
  rank_anova <- qr(x_anova)$rank
  rank_combined <- qr(cbind(x_te, x_anova))$rank

  # Guard the paragraph above rather than trusting it: if a future mgcv makes
  # predict(type="link") include the argument-offset, this stops being a
  # silent no-op and says so.
  offset_gap_te <- max(abs(
    eta_te - (as.numeric(predict(m_te, type = "link")) + log_offset)
  ))
  offset_gap_anova <- max(abs(
    eta_anova - (as.numeric(predict(m_anova, type = "link")) + log_offset)
  ))

  # ------------------------------------------------------------------------
  # DOES THE SPELLING OF THE ANOVA DECOMPOSITION MATTER?
  #
  # The plan's blocker A proposes `s(x) + s(z) + ti(x,z)`. mgcv's OWN ?ti
  # documentation writes the decomposition as `ti(x) + ti(z) + ti(x,z)` and
  # demonstrates it beside `te(x,z)` as a DIFFERENT model ("tensor product"
  # vs "tensor anova"), not as an equivalent one.
  #
  # That difference in spelling is the most obvious challenge to a refutation
  # of blocker A -- "you tested the wrong decomposition" -- so it is measured
  # rather than argued. Purely R-internal: no Polaris side, and nothing here
  # is expressible through `assemble_model_design` anyway (a one-margin `ti`
  # is rejected by TermSpec, which requires >= 2 variables for basis="ti").
  # ------------------------------------------------------------------------
  m_ti_anova <- mgcv::gam(
    deaths ~ ti(attained_age, bs = "cr", k = 7) +
      ti(calendar_year, bs = "cr", k = 5) +
      ti(attained_age, calendar_year, bs = "cr", k = c(7, 5)) +
      s(duration_years, bs = "cr", k = 5),
    data = df, family = poisson(link = "log"), offset = log_offset,
    knots = knots_arg, method = "REML"
  )
  eta_ti_anova <- as.numeric(m_ti_anova$linear.predictors)
  spelling <- list(
    # Does the s()-spelled decomposition equal the ti()-spelled one?
    s_vs_ti_max_abs_eta_diff = max(abs(eta_anova - eta_ti_anova)),
    s_vs_ti_edf_total_diff = sum(m_ti_anova$edf) - sum(m_anova$edf),
    # Does mgcv's OWN spelling fare any better against te() than ours does?
    te_vs_ti_anova_max_abs_eta_diff = max(abs(eta_te - eta_ti_anova)),
    te_vs_ti_anova_edf_total_diff = sum(m_ti_anova$edf) - sum(m_te$edf),
    n_coef_ti_anova = length(coef(m_ti_anova)),
    n_sp_ti_anova = length(m_ti_anova$sp)
  )

  # --- R-INTERNAL SENSITIVITY: is the te-vs-anova gap structural? -----------
  # The headline reading is one recipe, and this routine's own ledger exists
  # because a single cell can agree BY ACCIDENT -- which applies just as much
  # to a single cell that DISAGREES. So repeat the te-vs-s+s+ti comparison
  # across a small sweep of seeds and basis dimensions, entirely inside R
  # (Polaris appears nowhere in it), and report the spread.
  #
  # This does NOT widen the slice's scope: it is the same question the headline
  # asks, measured over more than one cell so that "the equivalence fails" can
  # be distinguished from "the equivalence failed once".
  #
  # TWO AXES, and they are not interchangeable -- an earlier revision of this
  # sweep varied k at a SINGLE draw and read as though it had five independent
  # cells. It had two. So they are separated explicitly:
  #   * the DRAW axis (8 seeds at the headline k) -- how often the two forms
  #     coincide, which is the axis that decides whether the re-expression is
  #     dependable;
  #   * the k axis (4 basis dimensions at one seed) -- whether any gap is an
  #     artefact of the particular basis size.
  variants <- list()
  for (s in c(
    20260916L, 20260917L, 20260918L, 20260919L,
    20260920L, 20260921L, 20260922L, 20260923L
  )) {
    variants[[length(variants) + 1L]] <- list(seed = s, ka = 7L, ky = 5L, axis = "draw")
  }
  # The k axis is anchored on a draw that DISAGREES at the headline k (20260917
  # reads 5.5e-02 there). Anchoring it on an agreeing draw would sweep k
  # through a region where the two forms coincide anyway and prove nothing
  # about whether a gap is a basis-size artefact -- which is the only question
  # this axis exists to answer.
  for (kk in list(c(9L, 5L), c(7L, 7L), c(5L, 4L), c(11L, 6L))) {
    variants[[length(variants) + 1L]] <- list(
      seed = 20260917L, ka = kk[[1]], ky = kk[[2]], axis = "k"
    )
  }
  sensitivity <- list()
  for (variant in variants) {
    set.seed(variant$seed)
    v_ak <- seq(45, 85, length.out = variant$ka)
    v_yk <- seq(2010, 2021, length.out = variant$ky)
    v_deaths <- rpois(n, lambda = exposure * q_base * exp(log_rr))
    v_df <- df
    v_df$deaths <- v_deaths
    v_knots <- list(
      attained_age = v_ak, calendar_year = v_yk, duration_years = duration_knots
    )
    v_te <- mgcv::gam(
      deaths ~ te(attained_age, calendar_year, bs = "cr", k = c(variant$ka, variant$ky)) +
        s(duration_years, bs = "cr", k = 5),
      data = v_df, family = poisson(link = "log"), offset = log_offset,
      knots = v_knots, method = "REML"
    )
    v_anova <- mgcv::gam(
      deaths ~ s(attained_age, bs = "cr", k = variant$ka) +
        s(calendar_year, bs = "cr", k = variant$ky) +
        ti(attained_age, calendar_year, bs = "cr", k = c(variant$ka, variant$ky)) +
        s(duration_years, bs = "cr", k = 5),
      data = v_df, family = poisson(link = "log"), offset = log_offset,
      knots = v_knots, method = "REML"
    )
    sensitivity[[length(sensitivity) + 1L]] <- list(
      seed = variant$seed, age_k = variant$ka, year_k = variant$ky,
      axis = variant$axis,
      n_coef_te = length(coef(v_te)), n_coef_anova = length(coef(v_anova)),
      n_sp_te = length(v_te$sp), n_sp_anova = length(v_anova$sp),
      max_abs_eta_diff = max(abs(
        as.numeric(v_anova$linear.predictors) - as.numeric(v_te$linear.predictors)
      )),
      edf_total_diff = sum(v_anova$edf) - sum(v_te$edf),
      # The duration smooth is structurally IDENTICAL in both formulas -- it is
      # not part of what te decomposes. Its own edf is therefore the internal
      # control: if the gap is the re-expression, this stays ~0 while the
      # age x year block's does not.
      duration_edf_diff = (
        as.numeric(summary(v_anova)$s.table[, "edf"])[4] -
          as.numeric(summary(v_te)$s.table[, "edf"])[2]
      )
    )
  }

  out <- list(
    schema_version = 1L,
    n = n,
    # ---- the shared recipe (everything both sides need to POSE the problem) --
    attained_age = as.numeric(attained_age),
    calendar_year = as.numeric(calendar_year),
    duration_years = as.numeric(duration_years),
    exposure = as.numeric(exposure),
    q_base = as.numeric(q_base),
    deaths = as.numeric(deaths),
    log_offset = as.numeric(log_offset),
    age_knots = age_knots,
    year_knots = year_knots,
    duration_knots = duration_knots,
    age_k = 7L,
    year_k = 5L,
    duration_k = 5L,
    mgcv_version = as.character(packageVersion("mgcv")),
    r_version = R.version.string,
    # Tripwire for the eta-definition note above: `m$linear.predictors` minus
    # (`predict(type="link")` + offset), which is 0 while predict() continues
    # to exclude an argument-supplied offset. Reported, not gated.
    offset_gap_te = offset_gap_te,
    offset_gap_anova = offset_gap_anova,
    # Span equivalence, measured both ways (see the block that computes these).
    # Machine-precision zeros here are what license "same span, different
    # penalty"; anything larger would refute it.
    span_residual_anova_in_te = span_residual_anova_in_te,
    span_residual_te_in_anova = span_residual_te_in_anova,
    rank_te = rank_te,
    rank_anova = rank_anova,
    rank_combined = rank_combined,
    # ---- mgcv's own fit of the TARGET form ----------------------------------
    te = list(
      eta = eta_te,
      coef = as.numeric(coef(m_te)), # diagnostic only, never compared (Anchor 2)
      sp = as.numeric(m_te$sp),
      edf_total = sum(m_te$edf),
      term_edf = as.numeric(summary(m_te)$s.table[, "edf"]),
      n_coef = length(coef(m_te)),
      converged = isTRUE(m_te$converged),
      reml = as.numeric(m_te$gcv.ubre)
    ),
    # ---- mgcv's own fit of the RE-EXPRESSION --------------------------------
    anova = list(
      eta = eta_anova,
      coef = as.numeric(coef(m_anova)), # diagnostic only (Anchor 2)
      sp = as.numeric(m_anova$sp),
      edf_total = sum(m_anova$edf),
      term_edf = as.numeric(summary(m_anova)$s.table[, "edf"]),
      n_coef = length(coef(m_anova)),
      converged = isTRUE(m_anova$converged),
      reml = as.numeric(m_anova$gcv.ubre)
    ),
    # ---- Does the ANOVA decomposition's SPELLING matter? (R-internal) --------
    anova_spelling = spelling,
    # ---- R-internal robustness sweep of the te-vs-anova gap ------------------
    sensitivity = sensitivity
  )
  jsonlite::write_json(
    out, out_path,
    digits = NA, auto_unbox = TRUE, null = "null", matrix = "rowmajor"
  )
  cat(sprintf(
    paste0(
      "Wrote %s -- n=%d, mgcv %s\n",
      "  te():        p=%d, edf_total=%.4f, n(sp)=%d\n",
      "  s()+s()+ti(): p=%d, edf_total=%.4f, n(sp)=%d\n",
      "  R-internal te vs s+s+ti: max|d eta|=%.6e, d edf_total=%+.4f\n",
      "  offset tripwire (expect 0): te=%.3e, anova=%.3e\n",
      "  span residuals (expect ~0): anova-in-te=%.3e, te-in-anova=%.3e",
      " [ranks %d/%d/%d combined]\n",
      "  spelling: s+s+ti vs ti+ti+ti max|d eta|=%.3e; te vs ti+ti+ti max|d eta|=%.4e\n"
    ),
    out_path, n, as.character(packageVersion("mgcv")),
    length(coef(m_te)), sum(m_te$edf), length(m_te$sp),
    length(coef(m_anova)), sum(m_anova$edf), length(m_anova$sp),
    max(abs(eta_te - eta_anova)), sum(m_anova$edf) - sum(m_te$edf),
    offset_gap_te, offset_gap_anova,
    span_residual_anova_in_te, span_residual_te_in_anova,
    rank_te, rank_anova, rank_combined,
    spelling$s_vs_ti_max_abs_eta_diff, spelling$te_vs_ti_anova_max_abs_eta_diff
  ))
  invisible(NULL)
}

status <- tryCatch(
  {
    main(commandArgs(trailingOnly = TRUE))
    0L
  },
  error = function(e) {
    message("gam_production_mi_probe.R FAILED: ", conditionMessage(e))
    1L
  }
)
quit(status = status)
