# Plan: stabilise the HGAM in the dashboard, then re-wire and deprecate the older experience-GAM

> **STATUS: ACTIVE from 2026-11-08 (ADR-264 ACCEPTED; the maintainer confirmed the plan, the slice order and the 0.95 saturation threshold). The next session takes S1 (release: none).** R1 (docs only) may run in parallel. It replaces `PLAN_gam_dashboard.md`'s D3 (CLI/MCP/API), which is PARKED with no release condition.

**Source:** maintainer, 2026-11-08: *"lets not do D3 for now, I want to get to a stable point where we have the HGAM python implemented in streamlit, then we need to re-wire and deprecate the prior approach."* This changes ADR-263 decision (2) ("retirement is NOT a D2 task and not a priority"): retirement is now the epic's goal, after stabilisation.
**Routine:** `ROUTINE_MGCV_PARITY.md`. Not a parity epic: ADR-193 still binds any comparison, and a number Polaris computes alone is MEASUREMENT.

## 1. Where we stand (measured)
D2 is merged (PR #279, ADR-263): the page leads with the HGAM (partial effects, `MI_x(y)` surface with a delta-method band, CSV download); the older model is behind a "Legacy model" expander. Maintainer real-data runs (2012-2019 ILEC, aggregated; tier L, MEASUREMENT, `gam` and `bam`, 965 and 5,573 cells) found, in order of weight:
1. **Basis saturation.** At the default `k` the age smooth had edf 7.00 of 7 and the year smooth 3.90 of 4; raising to `k=20`/`7` gave age 18.83 of 19, year 5.32 of 6, `ti` 10.4 -> 47.2, REML 2882 -> 1181. The basis, not the penalty, limited the fit, and may still.
2. **Uninformative cells shown as results.** Band widths of about 1.2 at age 120 and 0.4-0.6 at ages 0-20 (MI units), while ages 30-90 were under 0.1.
3. **Exposure <= 0.** 86 cells had non-positive `central_exposure`; the page refuses with "`log_exposure` contains non-finite values", which names the symptom not the cause.
4. **`slogdet` warnings: two records that differ, kept both.** The tier-L readings on row-level cells (CONTINUATION, PRODUCT_DIRECTION 2026-11-07) report the warnings on EVERY `gam` fit and none on `bam`. The 2026-11-08 aggregated-ILEC runs (965 and 5,573 cells) logged none at the default `k` and logged the numerical-events caption at `k=20`. Whether `k`, the data grain (row-level vs aggregated cells) or the formula triggers them is NOT established; S2 must not assume `k` is the trigger.
5. The `amount` basis is not wired into the HGAM section; `bam`'s `Vp` for the contrast was checked on three smooth-truth seeds only.

## 2. Definition of done
**Stable:** a maintainer can load their data, get a fit whose report states when a smooth is saturated, a surface that does not present uninformative cells as results, a clear message for bad exposure, the `amount` basis, and a documented reading of the `slogdet` warnings. **Retired:** every caller of the older experience-GAM is classified (migrate, keep, retire) and acted on; the older API carries a `DeprecationWarning` and a replacement pointer; nothing is REMOVED without the maintainer's written go; goldens byte-identical unless the maintainer says otherwise.

## 3. Slices (each with its own release condition; no splitting without a maintainer comment)
- **S1 — fit-report honesty. Release: none (first slice).** (a) A shared saturation flag: any smooth term with edf >= 0.95 x (its coefficient count after constraints) is named on the fit report and the page (threshold stated, not tuned; derivation: edf cannot exceed the term's constrained coefficient count, which is k-1 for `s(x, k)`, (k1-1)(k2-1) for `ti`, k-1 per level for a factor-`by` smooth and the level count for `re`; the count comes from the term's design block width). (b) Surface masking: cells with no exposure, or a band wider than a stated multiple of the surface's median band, are shown masked and counted, never plotted as values; the multiple is chosen BEFORE the first run and written in the ADR. (c) A clear message and a drop option for cells with exposure <= 0. All MEASUREMENT (own criterion); tests assert the messages and the mask.
- **S2 — the `slogdet` warnings. Release: S1 merged.** One measured session on `reml_score_general`: does the warning mean a real numerical problem or a benign evaluation at a bound? Reproduce on synthetic data at the DEFAULT `k` and at a larger `k`, at row-level and aggregated grain (the two records in §1.4 disagree), state the mechanism class, and pre-decide the outcomes: benign -> the page keeps the R-04 handling and the ADR names the cause; real -> record the limitation and the affected formulas; no solver work (PLAN_gam_dashboard rule 2).
- **S3 — `amount` basis and a harder truth. Release: S1 merged.** Wire `amount_exposed`/`death_amount` into the HGAM section; extend the D2 truth-recovery suite to a SHARPLY varying truth (tolerances derived and written before the first run) for `gam` and `bam`. A miss is a result.
- **R1 — inventory (docs only). Release: S1 merged (can run in parallel with S2/S3 as it writes no code).** Classify every caller of the older model; see §4 for the first-pass list. Output: a table in the CONTINUATION and an ADR deciding each row.
- **R2 — re-wire. Release: R1 merged and the maintainer's written go.** Move what R1 marks "migrate" onto the HGAM; the Bayesian projection fan is decided here (HGAM Bayesian feature = its own plan, wanted eventually).
- **R3 — deprecate. Release: R2 merged and the maintainer's written go.** `DeprecationWarning`s with a replacement pointer; docs; the page's legacy expander retired or kept per R1. REMOVAL of code is a separate maintainer decision.

## 4. First-pass inventory (grep; R1 confirms, this list is NOT the classification)
Older-model classes: `ExperienceGAM`, `TensorMIModel`, `PenalizedTensorMIModel`, `BayesianTensorMIModel` (+ `attach_base_rate`, `MISurface`, `MIProjection`).
- `src/polaris_re/cli.py`: the experience commands (Bayesian fit, `TensorMIModel`, `ExperienceGAM`, `attach_base_rate`).
- `analytics/experience_diligence.py`, `experience_validation.py`, `experience_loaders.py` (loaders and `attach_base_rate` are data plumbing, probably KEEP), `experience_oracle.py`, `experience_mgcv_conformance.py`.
- `viz/experience_plots.py` (consumes `MISurface`/`MIProjection`).
- `dashboard/views/experience_improvement.py` (the legacy expander, incl. the Bayesian fan).
- `assumptions/improvement.py` (documents the versioned scale; pricing consumes a stored scale via `improvement_version_id` in `pipeline.py`, `services/pricing.py`, `dashboard/views/pricing.py` - whether any fit runs on that path is to be CONFIRMED in R1).
- Scripts and many tests under `tests/test_analytics/test_experience_*`, which pin the older model's behaviour.
Pricing-adjacent paths and goldens are the constraint: nothing here changes a pricing number.

## 5. Rules that keep it from spiralling
1. One slice per session; S2/S3/R-slices do not start before their release condition. 2. No solver work, no new start strategy. 3. No new `mgcv` constructs. 4. A number without a second producer is MEASUREMENT. 5. Real data never enters the repo or the cloud; maintainer runs report derived scalars only. 6. Thresholds (saturation 0.95, mask multiple) are stated and fixed BEFORE the first run; a miss is a result, not a reason to retune. 7. Deprecation is not removal. 8. Questions go to the maintainer in the session they arise, with a recommended answer.
