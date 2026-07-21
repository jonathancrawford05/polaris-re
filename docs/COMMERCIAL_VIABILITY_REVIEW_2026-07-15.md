# Commercial Viability Review — 2026-07-15

## Purpose

This review is triggered by **Tier-A ladder exhaustion**, not by the calendar.
The three Tier-A "big rocks" that the previous review
(`COMMERCIAL_VIABILITY_REVIEW_2026-07-05.md`) constituted to drive the
productization frontier — **A1′ validation & benchmark pack**, **A2′
production hardening & observability**, and **A3′ cedant data-ingestion
robustness** — have **all shipped** in the ten days since (PRs #130–#139). No
unstarted Tier-A item remains, so the daily-dev routine's step 5b has nothing
to "start", and promoting a Tier-B/C item to epic status without a fresh
re-rank would be precisely the "smallest-available-becomes-the-default"
failure this regeneration exists to prevent. Per the routine's own precedent
(the 2026-07-05 reserve-basis checkpoint regenerated the review "because the
Tier-A ladder is exhausted"), and per §6 of the prior review (guard against
the *epic-level* polish spiral), this is the moment to re-rank.

The prior review is only 10 days old, well inside the routine's ~30-day
age trigger — but, exactly as the 2026-07-05 review itself argued when it was
17 days old, "the catalogue underneath it has changed so much that a refresh
is warranted regardless." Three Tier-A epics closing in ten days is a
material change to the catalogue.

Like its predecessors, this is a **strategic / direction document, not a
reasonability assessment**. The canonical reasonability baseline remains the
nightly `PRODUCT_DIRECTION_*` line (latest: `PRODUCT_DIRECTION_2026-06-18.md`).

**Bottom line up front:** Polaris RE has now shipped its **entire written
roadmap** — the Phase 1–5 modeling roadmap *and* the Phase 6.2 production-
hardening milestone *and* the whole 2026-07-05 productization ladder. The one
remaining **structurally-incomplete roadmap milestone** is **Phase 6.1 —
Experience-Monitoring Automation** (the ML assumption feedback loop). It is
the last multi-session "big rock" with a written specification, and it serves
the project's *core differentiating thesis* (ML-native, self-improving
assumptions — the thing AXIS/Prophet structurally do not do). **This review
constitutes Experience-Monitoring Automation (ROADMAP 6.1) as the next active
epic**, and — importantly — flags that after it, the roadmap as written is
**complete**: the product crosses an inflection from "build the roadmap" into
"harvest quick wins / maintain, or chart a Phase 7." That Phase-7 go/no-go is
surfaced for the maintainer (§7).

---

## 1. Review of the Last 10 PRs (#130–#139)

| PR   | ADR | Epic | One-line scope | Est. size |
|------|-----|------|----------------|-----------|
| #130 | 130 | A1′ Validation & benchmark | Validation-pack framework + closed-form seed set | ~1 d |
| #131 | 131 | A1′ Validation & benchmark | Published-deck validation — SOA Illustrative Life Table (WholeLife) | ~1 d |
| #132 | 132 | A1′ Validation & benchmark | Surface the pack as `polaris benchmark` + README/QUICKSTART | ~1 d |
| #133 | 133 | A2′ Production hardening | API observability core — JSON access logging + correlation IDs (Slice 1) | ~1 d |
| #134 | 134 | A2′ Production hardening | API security — optional API-key auth + rate limiting (Slice 2) | ~1 d |
| #135 | 135 | A2′ Production hardening | Deployment & metrics — Prometheus `/metrics`, K8s/Helm, proxy keying (Slice 3) | ~1½ d |
| #136 | 136 | A3′ Cedant ingestion | Row-level quarantine + richer `DataQualityReport` (Slice 1) | ~1 d |
| #137 | 137 | A3′ Cedant ingestion | Robust value coercion — mixed dates + unit/currency (Slice 2) | ~1 d |
| #138 | 138 | A3′ Cedant ingestion | Surfaces — CLI/API rejects file + report + thresholded exit (Slice 3) | ~1½ d |
| #139 | 138 | A3′ Cedant ingestion | Post-review: rejects-on-breach + named `missing_<field>` + reason catalogue | ~½ d |

### What the table shows — the epic track held; three Tier-A epics closed clean

The 2026-06-18 review diagnosed a *slice-level* polish spiral and prescribed
an always-on epic track. The 2026-07-05 review confirmed that track worked
through the modeling roadmap and then re-pointed it at a *productization*
ladder (A1′/A2′/A3′). **This window shows that ladder fully executed:**

- **A1′ Validation & benchmark pack** (#130–#132, ADR-130–132): a
  CI-executable validation suite (closed-form seed set + the SOA Illustrative
  Life Table published-deck reproduction), surfaced as `polaris benchmark`.
  The single biggest *credibility* gap the 2026-07-05 review named — "no
  published numerical validation" — is now closed for every obtainable
  reference class. (The AXIS/Prophet side-by-side, Slice 4, remains
  reference-blocked and parked; see §3.)
- **A2′ Production hardening & observability** (#133–#135, ADR-133–135):
  structured JSON access logging + correlation IDs, optional API-key auth,
  dependency-free sliding-window rate limiting with proxy-aware keying,
  Prometheus `/metrics`, K8s manifests + Helm chart, and a Grafana compose
  stack. ROADMAP Milestone 6.2 is now ✅ end to end.
- **A3′ Cedant data-ingestion robustness** (#136–#139, ADR-136–138):
  row-level quarantine, a richer `DataQualityReport`, robust value coercion
  (mixed date formats, unit/currency normalisation), and a full CLI/API
  surface (rejects file, per-reason breakdown, thresholded exit) — with a
  disciplined post-review refinement round (#139).

Every PR is decomposed, byte-identical on goldens where intended,
independently mergeable, and carries an ADR. The queue continues to shrink in
the *direction* dimension. **The polish-spiral diagnosis remains resolved;
this review does not re-litigate it.**

---

## 2. Where the Product Actually Stands — the written roadmap is essentially done

As of today the modeling roadmap (Phases 1–5), the 2026-07-05 productization
ladder, and ROADMAP Milestone 6.2 are all shipped:

| Frontier item | Status today | Evidence |
|---|---|---|
| **Modeling roadmap** (TERM/WL/UL/DI; YRT/Coins/Modco/Stop-Loss; NET_PREMIUM/CRVM/VM-20/GAAP; IFRS 17 BBA/PAA/VFA + movement; LICAT/US-RBC/Solvency-II; Asset/ALM; expense-allowance) | ✅ COMPLETE | ROADMAP Phases 1–5 ✅; `CONTINUATION_*` all COMPLETE; ADRs through ADR-129 |
| **A1′ Validation & benchmark pack** | ✅ COMPLETE | `CONTINUATION_validation_benchmark` COMPLETE (#130–#132, ADR-130–132); `polaris benchmark` |
| **A2′ Production hardening (ROADMAP 6.2)** | ✅ COMPLETE | `CONTINUATION_production_hardening` COMPLETE (#133–#135, ADR-133–135); ROADMAP 6.2 boxes checked |
| **A3′ Cedant ingestion robustness** | ✅ COMPLETE | `CONTINUATION_cedant_ingestion` COMPLETE (#136–#139, ADR-136–138) |

The suite stands at **~2,195 unit tests passing** (3 skipped on absent CIA
tables, 110 slow-deselected), coverage ≥ 90% enforced in CI, ADRs current
through **ADR-138**.

**The commercial-readiness boundary has moved once more.** In 2026-04-19 it
was "can it price a first deal." In 2026-06-18, "can it survive a
sophisticated buyer's diligence across jurisdictions." In 2026-07-05, "can a
buyer *validate* the numbers and can ops *deploy* it." As of today all three
are **yes**. What is left is not a modeling gap, not a validation gap, and not
a deployment gap — it is the **one capability the roadmap always promised but
never built: the ML assumption feedback loop** (Phase 6.1). That is both the
last unstarted roadmap milestone and the clearest expression of the project's
differentiating thesis.

---

## 3. Is there a genuine next Tier-A epic? — yes: Experience-Monitoring Automation (6.1)

With the productization ladder exhausted, the honest question is whether *any*
remaining item deserves Tier-A / epic status, or whether the product has
crossed into quick-win-harvest mode. Walking the candidates:

- **Experience-Monitoring Automation (ROADMAP 6.1 / prior C2, ~6 d, 3–4
  slices).** The last unstarted roadmap milestone with a *written
  specification* (ROADMAP 6.1: `ExperienceStudy.export_to_*_csv()` →
  `scripts/update_assumptions.py` → `polaris experience run` → assumption
  versioning). It closes the loop between the Phase-3 experience-study module
  and the Phase-4 assumption pipeline, delivering the "self-improving with
  experience data" property. **This is the differentiator** — CLAUDE.md §1
  names "no native ML integration" as a defining weakness of the incumbents;
  6.1 is where Polaris RE's ML-native thesis becomes an operational loop, not
  just a model class. Multi-session, plan-drivable, and genuinely
  Tier-A-worthy on both *thesis value* and *roadmap completeness*. **→ the
  recommended next epic.**

- **AXIS/Prophet side-by-side benchmark (validation Slice 4).** Would be the
  highest *credibility* win, but it is **reference-blocked**: it needs a
  maintainer-supplied AXIS/Prophet reference output. Parked correctly; cannot
  be autonomously constituted. Revive on a maintainer-supplied reference.

- **Tier-B quick wins (B1 capital surfaces, B2 scale benchmark, B4 deficiency
  reserve).** Real value, but each is single-session — fallback picks, not
  epics (see §4).

- **Deeper NICE-TO-HAVE queue** (funds-withheld coinsurance, per-deal hurdle
  rates, parallel portfolio execution, dashboard scenario page, etc.): Tier-C
  enabling work, none of it a Tier-A "big rock."

**Verdict:** Experience-Monitoring Automation (6.1) is a legitimate Tier-A
epic — the last one the written roadmap contains — and it out-ranks every
available alternative on value (differentiating thesis + roadmap completeness)
per unit effort. It becomes the next active epic. **After 6.1, the roadmap as
written is complete** (only 6.3's load-test quality-gate item and the
reference-blocked validation Slice 4 remain), and the product reaches the
inflection surfaced in §7.

---

## 4. Feature Catalogue — Re-ranked for 2026-07-15

Value is judged against a paying reinsurance client (pricing actuary,
CRO/CFO, IT/ops). Effort is in developer-days; "phases" is the recommended
number of staggered slices.

### Tier A — High value, multi-session (the remaining big rock)

| # | Feature | Value | Effort | Phases | Source |
|---|---------|-------|--------|--------|--------|
| **A4′** | **Data-Driven Experience Analysis & Assumption-Setting (GAM)** — reframes ROADMAP 6.1 from a black-box `--retrain-ml` loop into an **interpretable GAM layer**: marginal feature-effect isolation → **tensor mortality-improvement surface `te(age, calendar_year)` (headline)** → hierarchical partial pooling (smooth credibility) → CLI/versioning. New `analytics/experience_gam.py`; exports plug into `MortalityImprovement.apply_improvement`. **PLAN locked: `docs/PLAN_experience_gam.md`.** | ★★★★☆ | ~7 d | 4 | ROADMAP 6.1; 2026-07-05 C2; ML-native thesis (CLAUDE.md §1); maintainer scoping 2026-07-15 |

**Why A4′ leads (and is the last roadmap epic).** It is the only unstarted
multi-session item backed by a written roadmap spec, and it directly realises
the project's stated reason to exist versus AXIS/Prophet. Per the maintainer
scoping discussion (2026-07-15), the meaningful ML enablement is the
**auditable middle** between the grouped-A/E credibility already in
`analytics/experience_study.py` and the black-box XGBoost in
`assumptions/ml_mortality.py` — a GAM that isolates standard feature effects
with honest uncertainty and sets bases actuaries can defend. The **headline
deliverable is a tensor MI surface** (age-varying improvement estimated from
experience, emitted as a `MortalityImprovement`-compatible scale), built on a
static select-base offset with the Lexis/APC identifiability handled
explicitly (calendar trend → improvement; issue-year drift constrained, with an
optional `underwriting_era` factor). Backend: `statsmodels GLMGam` (marginal) →
`bambi`/`pymc` HSGP (anisotropic tensor + partial pooling + honest forward
projection); `mgcv` used offline only as a validation oracle. Full four-slice
decomposition, design anchors, and dependency staging: **`docs/PLAN_experience_gam.md`**.

### Tier B — High value, single-to-short (between-epic quick wins)

| # | Feature | Value | Effort | Phases | Source |
|---|---------|-------|--------|--------|--------|
| B1 | **Switch capital surfaces to `for_product_interim`** — expose the built C-1/C-3 factors everywhere (behaviour change → golden rebaseline + ADR) | ★★★★☆ | ~1–2 d | 1 | 2026-06-18 B1 / 2026-07-05 B1 (still unshipped) |
| B2 | **Scale benchmark at 100K–500K policies** — publish a timing table; back the README performance claim | ★★★★☆ | ~1 d | 1 | 2026-06-18 B2 / 2026-07-05 B2 (still unshipped) |
| B4 | **Premium-deficiency reserve / loss recognition** — turn the sufficiency analyzer into a reserve floor | ★★★☆☆ | ~1–2 d | 1 | 2026-06-18 B4 / 2026-07-05 B4 (still unshipped) |

B1 and B2 have now survived **two** reviews unshipped — the epic track
(correctly) drove the Tier-A ladders instead. They remain the cleanest
between-epic fallback picks and are the obvious candidates whenever an A4′
slice is blocked on an unmerged predecessor.

### Tier C — Medium value, enabling / operational

| # | Feature | Value | Effort | Source |
|---|---------|-------|--------|--------|
| C3 | Funds-withheld coinsurance (`FWCoinsuranceTreaty`) | ★★★☆☆ | ~2 d | 2026-06-18 C3 |
| C4 | Parallel portfolio execution + caching + `remove_deal` | ★★★☆☆ | ~2 d | CONT-portfolio #6 |
| C5 | Per-deal hurdle rates on `Portfolio` | ★★★☆☆ | ~5 d | CONT-portfolio #4 |
| C6 | Phase-6.3 load test (100 concurrent `/api/v1/price` < 2s) + QUICKSTART K8s guide | ★★★☆☆ | ~1–2 d | ROADMAP 6.3 |

### Tier D — Exactness polish / low value (deprioritise)

- **Interest-exactness helper** (`CONTINUATION_reserve_basis_correctness`
  Slices 2–3) — still parked as a NICE-TO-HAVE per the 2026-07-05 checkpoint;
  revive on a real cedant reproduction that demands penny-exact CRVM interest.
- The A1′/A2′/A3′ out-of-scope harvest now in
  `PRODUCT_DIRECTION_2026-06-18` "Promoted Follow-ups" (machine-readable
  ingestion report sidecar, `--rejects-format`, streaming ingestion,
  OpenTelemetry spans, engine-level metrics, free-text column coercion) — all
  NICE-TO-HAVE automation/scale polish.
- GAAP PADs on the deal path, sex/smoker statutory-table composition,
  CSO-version selection, and the usual Excel/dashboard micro-polish.

### The picture in one view

```
        HIGH VALUE
            │  A4' Experience-monitoring loop (last roadmap epic)
            │                         B1 capital surfaces
            │                         B2 scale benchmark
   ─────────┼───────────────────────────────────────────
            │  C5 per-deal hurdle      B4 deficiency reserve
            │  C3 funds-withheld       C6 load test / 6.3 gate
            │  C4 parallel portfolio   [Tier D: interest-exactness, polish]
        LOW │
            └───────────────────────────────────────────
              HIGH EFFORT                     LOW EFFORT
              (AXIS/Prophet side-by-side: reference-blocked — off-grid)
```

---

## 5. Verdict & Recommended Sequence

**Verdict:** The 2026-07-05 productization ladder is fully shipped. The next
active epic is **A4′ Data-Driven Experience Analysis & Assumption-Setting
(GAM)** — the reframed ROADMAP 6.1, the last unstarted roadmap milestone and
the operational form of the project's ML-native thesis. It out-ranks the
Tier-B quick wins (single-session fallbacks) and every Tier-C/D item. **The
PLAN was locked this session (`docs/PLAN_experience_gam.md`) via a maintainer
scoping discussion** — the epic is constituted; Slice 1 is NEXT.

**Recommended sequence:**

1. **A4′ is constituted** — `docs/PLAN_experience_gam.md` is written and
   locked (four slices, design anchors, dependency staging). Next dev session
   writes `docs/CONTINUATION_experience_gam.md` (status IN PROGRESS) and ships
   **Slice 1** (experience-data contract + marginal effect isolation, additive
   / byte-identical to the engine). Shipping Slice 1 is that session's
   deliverable.
2. **B1 + B2 as the between-epic Sprint-0 quick wins** — pick them up only
   when an A4′ slice is blocked on an unmerged predecessor (the epic advances
   ~one slice per human merge; see the routine's merge-cadence note).
3. **After A4′ closes**, the written roadmap is complete bar the 6.3
   load-test quality gate (C6) and the reference-blocked validation Slice 4.
   At that point the routine has no further Tier-A "big rock" — see §7.

**This session's deliverable is this regenerated review plus the locked A4′
PLAN** (Tier-A ladder exhausted; the re-rank + epic constitution is a
substantial analytical task). Per routine step 6, when the re-rank and a code
slice would together blow the wall-clock guardrail, the analysis is the
deliverable and the slice is **deferred to the next run**. No code slice ships
this session; A4′ Slice 1 ships next.

---

## 6. A4′ Decomposition — LOCKED (`docs/PLAN_experience_gam.md`)

The full plan (design anchors, canonical model form, backends, dependency
staging, out-of-scope, open decisions) lives in `docs/PLAN_experience_gam.md`,
locked 2026-07-15 via the maintainer scoping discussion. Four slices, each
additive / byte-identical to the engine until the Slice-4 surface:

- **Slice 1 — Experience-data contract + marginal effect isolation (NEXT).**
  New `analytics/experience_gam.py`; the experience-record schema; static
  select-base offset via `MortalityTable.get_qx_vector`; additive A/E GAM
  (`s(age)+s(duration)+Σ factors`, Poisson/NB) with per-feature effects + CIs;
  `export_to_mortality_csv` round-trip. Backend: `statsmodels GLMGam`. No
  tensor/hierarchy — de-risks the data-contract + offset + export plumbing.
- **Slice 2 — Tensor MI surface (HEADLINE).** `te(age, calendar_year)`
  age-varying improvement with static select-base offset + residual
  `s_resid(duration)`; anisotropic `bambi`/`pymc` HSGP; extract `MI_x(y)` grid
  with credible intervals; posterior-predictive forward projection anchored to
  a long-term rate → emit a `MortalityImprovement`-compatible scale. Encodes
  the Lexis/APC identifiability rule (calendar → improvement; issue-year
  constrained; optional `underwriting_era` factor).
- **Slice 3 — Hierarchical partial pooling (credibility).** Segment-level
  deviations shrunk toward the global surface (Pedersen GS/GI HGAM);
  generalizes `ExperienceStudy`'s limited-fluctuation `Z`.
- **Slice 4 — Surface + versioning + validation + docs (CLOSES EPIC).**
  `polaris experience improvement`/`fit`; assumption versioning; diagnostics;
  `mgcv`-via-`rpy2` offline validation oracle; ADR + ARCHITECTURE + QUICKSTART.

**Key design anchors (full list in the PLAN):** A/E on the log-mortality scale
offset by a **static** (never generational) select base; duration enters twice
(primary in the offset, residual smoother for company-specific select drift);
`bambi`/`pymc` deps staged into `[ml]` with the slice that imports them
(`pymc` is compile-heavy — not added ahead of Slice 2); `mgcv` never a runtime
dependency; all fixtures pin dates (ADR-074); Dockerfile COPY + `.dockerignore`
updated in-PR for any test-referenced data (#61/#66 trap). **Out of scope:** the
maintainer's new-data-source risk segmentation is a *forward / prospective-
rating* capability (a later Phase-7 candidate reusing this machinery), not this
retrospective experience epic.

---

## 7. Decision Surfaced for the Maintainer — the post-roadmap inflection

> **Q: After Experience-Monitoring Automation (6.1) closes, what drives the
> routine — quick-win harvest, or a new Phase 7?**
>
> With 6.1 shipped, Polaris RE will have completed its **entire written
> roadmap** (Phases 1–6 bar the 6.3 load-test gate) and every productization
> epic. There is no further Tier-A "big rock" in the current plans. The
> routine will then, correctly, fall to the Tier-B/C quick-win queue (B1
> capital surfaces, B2 scale benchmark, B4 deficiency reserve, C3/C4/C5/C6) —
> which is legitimate maintenance work, but is *not* a growth frontier and
> risks the very "quick-win-becomes-the-default" pattern the epic track was
> built to avoid, only one tier up.
>
> **Recommended:** before 6.1 closes, decide the next frontier. Candidate
> **Phase 7** themes (any one of which would re-establish a Tier-A ladder):
> - **Real AXIS/Prophet reconciliation** — supply a reference output so the
>   parked validation Slice 4 can ship; this is the single highest *external*
>   credibility win and the only thing blocking a "matches the incumbent"
>   claim.
> - **New product frontier** — indexed/variable annuities with living
>   benefits (GMxB), or group/worksite blocks — the largest *un-modelled*
>   liability classes a reinsurer would bring.
> - **Stochastic ALM / nested stochastic** — the economic-scenario-generator
>   and nested-stochastic capability that VM-21 / principle-based reserves and
>   real economic-capital work require (extends the Phase-5.4 Asset/ALM base).
> - **Multi-user / persistence / audit** — a deal database, run history, and
>   user-level audit trail — the "team of actuaries, not one" operational
>   layer that a purchased tool needs.
>
> **If you have no Phase-7 preference yet**, the autonomous default after 6.1
> is to harvest B1 → B2 → B4 as single-session quick wins (each independently
> valuable) while this decision stays open — but flag that the routine is then
> in *maintenance* mode, not *growth* mode, and say so in each session log.

---

## 8. Reconciliation with `PRODUCT_DIRECTION_2026-06-18`

The latest nightly reasonability line is `PRODUCT_DIRECTION_2026-06-18.md` (27
days old, still < 30 — not regenerated here; this is a strategic doc, and the
nightly line remains the reasonability authority). Its three lead IMPORTANT
items (reserve-basis matching, IFRS 17 movement, cross-jurisdiction capital)
are all **SHIPPED and struck through**; its NICE-TO-HAVE queue already carries
"Experience monitoring automation loop (Phase 6.1) — ~6 dev-days" and the
Tier-B quick wins (scale benchmark, deficiency reserve, capital-surface
switch). This review does not contradict it — it **elevates** the
Phase-6.1 automation loop from that NICE-TO-HAVE queue to the active Tier-A
epic, on the strategic grounds that (a) it is the last unstarted roadmap
milestone and (b) it realises the ML-native differentiator, now that
everything ranked above it has shipped. The nightly line's reasonability
profile is unchanged; no new reasonability flag emerged from this window.

Note for the next nightly: `PRODUCT_DIRECTION_2026-06-18.md` turns 30 days old
on ~2026-07-18. The next `PRODUCT_DIRECTION` regeneration should list the
A1′/A2′/A3′ epics as shipped-since-prior and carry forward the harvested
follow-ups already appended to the 2026-06-18 file's "Promoted Follow-ups"
section.
