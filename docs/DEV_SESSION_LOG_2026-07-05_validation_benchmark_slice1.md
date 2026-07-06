# Dev Session Log — 2026-07-05

## Item Selected
- **Source:** `COMMERCIAL_VIABILITY_REVIEW_2026-07-05.md` §4–§5 (Tier-A A1′) →
  new epic `PLAN_validation_benchmark.md` / `CONTINUATION_validation_benchmark.md`
- **Priority:** IMPORTANT / Tier-A (★★★★★) — the highest-value unshipped item
  now that the modeling roadmap is complete (trust-and-deployment frontier)
- **Title:** Validation & Benchmark Pack (A1′) — framework + closed-form seed set
- **Slice:** 1 of 3 (+ optional Slice 4)
- **Branch:** `claude/loving-gauss-bab9og`

## Selection Rationale
Step 5 found the only IN-PROGRESS CONTINUATION to be
`reserve_basis_correctness`, whose next slice (Slice 2, interest-exactness) was
**deprioritised at its post-Slice-1 checkpoint** (this-morning's regenerated
`COMMERCIAL_VIABILITY_REVIEW_2026-07-05.md`), which recommended **redirecting** to
a productization epic and reserved the go/no-go for the maintainer. The review's
§5 gives the explicit autonomous instruction for exactly this state: *"absent a
maintainer decision [the next dev session] should run the A1′/A2′ scoping pass as
a new epic while leaving the interest-exactness CONTINUATION open-but-deprioritised,
so exactly one active epic always exists."* That is step 5b(b): **constitute a new
epic — writing the PLAN + Slice 1 IS the session's deliverable.**

A1′ (validation & benchmark pack) leads over A2′ (production hardening) / A3′
(ingestion robustness) because it is the single biggest *credibility* gap — the
README's "credible alternative to AXIS/Prophet" thesis has, until now, no
published numerical validation — and it is fully unblocked (the models it
validates all exist). The scoping pass (PLAN §"Scoping outcome") confirms
closed-form textbook identities are CI-executable *now* with no external
dependency, so Slice 1 is a clean, self-contained start.

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Validation framework (`ValidationCase`/`Result`/`Report`) + closed-form seed set | ✅ Done | (this PR) |
| 2 | Published-deck reference set (`STATUTORY_DECK`: SOA ILT / VM-20 worked example, vendored+cited) | ⏳ Next | — |
| 3 | Surface: `polaris validate` CLI + `05_validation_report.ipynb` notebook | 🔲 Planned | — |
| 4 | AXIS/Prophet side-by-side | ⏸ Parked (reference-blocked) | — |

## What Was Done
Constituted the **Validation & Benchmark Pack (A1′)** epic and shipped Slice 1.
New module `polaris_re.analytics.validation` provides an engine-agnostic reference
framework — `ValidationCase` (an authoritative expected value + source citation +
documented tolerance/rationale), `ValidationResult`, and `ValidationReport` (scored
collection with pass/fail counts and a `to_markdown()` diligence table). A case
holds only the reference; the caller drives the engine and `case.evaluate(computed)`
scores it with `numpy.isclose` semantics. This separation lets the later CLI /
notebook slices reuse the models verbatim.

Slice 1 seeds the pack with **closed-form actuarial benchmarks** — deliberately
mathematical *identities*, not recalled published numbers, so they are unimpeachable
and network-free. Under a constant force of mortality: (1) an *n*-year term-insurance
net single premium vs the exact discrete geometric-series closed form; (2) a
temporary life annuity-due APV vs its geometric closed form; (3) the same
term-insurance APV vs the continuous-force textbook identity
`(μ/(μ+δ))(1−e^{−(μ+δ)n})` (Bowers §4.2). `run_closed_form_benchmarks()` builds a
synthetic constant-q, zero-lapse single-policy TermLife block, projects it, and
evaluates all four cases into a report.

**Verify-premise step (7b) was run first:** a scratch reproduction confirmed the
TermLife engine reproduces the exact discrete closed form to `2e-15` and the
continuous textbook identity to `~0.2%` (captured as the textbook case's documented
`rtol=5e-3`) before any module code was written. Docs-adjacent: ADR-130 records the
decision; the interest-exactness CONTINUATION got a "superseded as active epic"
banner (open-but-deprioritised, not killed).

## Files Changed
- `src/polaris_re/analytics/validation.py` — **new**: framework + closed-form pack
- `src/polaris_re/analytics/__init__.py` — export the new public API
- `tests/validation/__init__.py`, `tests/validation/test_closed_form_pack.py` — **new**
- `docs/DECISIONS.md` — ADR-130
- `docs/PLAN_validation_benchmark.md` — **new** (epic plan + scoping outcome)
- `docs/CONTINUATION_validation_benchmark.md` — **new** (IN PROGRESS)
- `docs/CONTINUATION_reserve_basis_correctness.md` — superseded-as-active-epic banner
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — harvest (A1′ acted-on + 2 NICE-TO-HAVE follow-ups)

## Tests Added
`tests/validation/test_closed_form_pack.py` (18 tests): `evaluate` scoring
(exact / within-rtol / outside-rtol / zero-expected-atol); reference-derivation
consistency and known limits (zero-mortality → zero insurance + annuity-certain;
discrete < continuous by <1%); engine reproduces both exact closed forms to 1e-9
across three (q, i, age, term) parameter sets; assembled report passes all four
cases, spans both categories, holds exact cases to machine precision and the
textbook case within its documented tolerance, and renders a Markdown table.

## Baseline (for the next run's step-4 diff)
Full fast suite (`pytest -m "not slow"`): **2019 passed, 2 skipped, 110
deselected, 0 failures** (this session's baseline = the prior session's 2001
passed + the 18 new validation tests; no new/changed failures — tolerance-aware
check passes). **SOA-conversion state:** the 4 CIA-2014 tables were MISSING from
this run's pymort conversion (VBT/CSO OK), but no test hard-depends on the CIA
tables, so the standing "4 SOA-conversion failures" baseline manifested as **0
failures** here. QA suite (`tests/qa/`, 76 tests incl. the 23 CLI + pipeline
golden cases): all green.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| Scope A1′: confirm CI-executable references | ✅ | PLAN §"Scoping outcome": closed-form now, decks Slice 2, AXIS parked |
| Write `PLAN_validation_benchmark.md` | ✅ | 3 slices (+1 parked) |
| Ship Slice 1 (framework + first reference set) | ✅ | module + 18 tests, all green |
| References are identities/cited, never guessed | ✅ | closed-form + Bowers §4.2; verify-premise run first |
| Exactly one active epic maintained | ✅ | validation_benchmark active; interest-exactness parked open |
| Goldens byte-identical | ✅ | new module + tests only; QA suite (`tests/qa/`, 76; the 23 CLI + pipeline golden cases among them) green; `polaris price` regression run |

## Open Questions / Follow-ups
- **For Jonathan (redirect go/no-go — still reserved from the checkpoint):** this
  session took the review's recommended default (make A1′ validation the active
  epic; park interest-exactness open-but-deprioritised). If you'd rather finish
  interest-exactness first, its PLAN/CONTINUATION are intact and its Slice 2 ships
  unchanged next session.
- **Slice 2 reference choice:** SOA Illustrative Life Table (clean textbook APVs) vs
  a published VM-20/CRVM reserve deck (closer to the cedant-reproduction use case)?
  Both are CI-tractable as vendored, cited constants. Guardrail: if Slice 2 adds
  files under `data/`, update the Dockerfile `COPY` + `.dockerignore` allowlist in
  the same PR.

## Parked Polish
None this session. (The two harvested ADR-130 out-of-scope items — AXIS/Prophet
side-by-side and a WholeLife-to-omega closed-form case — are 2nd-order follow-ups of
the A1′ epic and were promoted as NICE-TO-HAVE, within the step-17 order cap, not
parked.)

## Impact on Golden Baselines
None. Slice 1 adds a new analytics module + a new test package only; it never
touches the pricing path. The QA suite (`tests/qa/`, 76 tests — of which 23 are the
CLI + pipeline golden cases) is green and a `polaris price` regression run was
executed. No rebaseline.
