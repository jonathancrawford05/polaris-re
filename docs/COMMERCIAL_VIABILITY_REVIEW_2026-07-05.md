# Commercial Viability Review — 2026-07-05

## Purpose

This is the **post-Slice-1 checkpoint** mandated by
`docs/PLAN_reserve_basis_correctness.md` and
`docs/CONTINUATION_reserve_basis_correctness.md`: before the active epic
commits to its interest-exactness slices (Slices 2–3), regenerate the
commercial-viability ranking to confirm interest-exactness is still the
highest-value continuation — or redirect the epic if a *productization*
theme now out-ranks it. It also satisfies the routine's ~30-day
regeneration trigger (step 6): the prior review
(`COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md`) is now 17 days old but the
catalogue underneath it has changed so much that a refresh is warranted
regardless.

Like its predecessor, this is a **strategic / direction document, not a
reasonability assessment**. The canonical reasonability baseline remains the
nightly `PRODUCT_DIRECTION_*` line.

**Bottom line up front:** the entire modeling roadmap the 2026-06-18 review
was built to drive is now **shipped**. Interest-exactness (the active epic's
Slices 2–3) is real but is *exactness polish* on an already-working
capability, and it **no longer ranks as the highest-value work**. The
frontier has moved from "can it model X" to "can a sophisticated buyer trust
and deploy it." This review recommends **demoting Slices 2–3 to a
NICE-TO-HAVE follow-up and constituting a productization/credibility epic
next** — with the go/no-go surfaced for the maintainer (the CONTINUATION
explicitly reserved this redirect for a human decision).

---

## 1. Review of the Last 10 PRs (#119–#128)

| PR   | ADR | Epic | One-line scope | Est. size |
|------|-----|------|----------------|-----------|
| #119 | 120 | B3 Expense-allowance | `ExperienceRefund` model + computation primitive | ~½ day |
| #120 | 121 | B3 Expense-allowance | Wire `ExperienceRefund` into Coinsurance + YRT treaties | ~½ day |
| #121 | 122 | B3 Expense-allowance | Surface allowance/refund on the CLI config deal path | ~½ day |
| #122 | 123 | B3 Expense-allowance | Surface allowance/refund on the REST API | ~½ day |
| #123 | 124 | B3 Expense-allowance | Surface allowance/refund on the deal-pricing Excel export | ~½ day |
| #124 | 125 | Reserve-Basis Exactness | Statutory `valuation_mortality` table for CRVM / VM-20 NPR (Slice 1) | ~1 day |
| #125 | 126 | Reserve-Basis Exactness | Surface `valuation_mortality` on config / CLI / API (Slice 2) | ~1 day |
| #126 | 127 | Reserve-Basis Exactness | GAAP (FAS 60) net-premium reserve for TermLife (Slice 3) | ~1 day |
| #127 | 128 | Reserve-Basis Exactness | GAAP (FAS 60) net level premium reserve for WholeLife (Slice 4) | ~1 day |
| #128 | 129 | Reserve-Basis Correctness | WholeLife honours the mortality-improvement scale (Slice 1) | ~1 day |

### What the table shows — the polish spiral is gone

The 2026-06-18 review's central finding was a **polish spiral**: ten
consecutive PRs (#69–#78) collapsed into three *sub-day* themes (perspective
plumbing, Excel sheets, sufficiency surfacing) while the genuinely important
epics sat untouched. The routine change it proposed — an always-on Epic track
that decomposes and drives one Tier-A feature per session before any fallback
pick — was adopted (`DAILY_DEV_ROUTINE_PROPOSED_CHANGES_2026-06-18.md`).

**It worked.** The last ten PRs are not polish — they are disciplined epic
slices spanning exactly three plan-driven epics:

- **B3 Expense-allowance / experience-refund** (#119–#123): the model
  primitive, treaty wiring, then a controlled surface-by-surface rollout
  (CLI → API → Excel). Closed the B3 Tier-B epic.
- **Reserve-Basis Exactness** (#124–#127): prescribed statutory
  `valuation_mortality` for CRVM/VM-20-NPR, its deal-path surfacing, then
  GAAP (FAS 60) for Term and WholeLife. Closed the Reserve-Basis Exactness
  epic (ADR-128).
- **Reserve-Basis Correctness** (#128): the WholeLife mortality-improvement
  correctness bug fix — Slice 1 of the *current* active epic (ADR-129).

Every PR is decomposed, byte-identical on goldens where intended,
independently mergeable, and carries an ADR. The queue is now shrinking in
the *direction* dimension, not growing in the *polish* dimension. **The
2026-06-18 diagnosis is resolved; this review does not need to re-litigate
it.**

---

## 2. Where the Product Actually Stands — the modeling roadmap is complete

Since 2026-06-18, the three Tier-A "big rocks," the Tier-C Asset/ALM big
rock, and the Tier-B expense-allowance epic have **all shipped**:

| 2026-06-18 item | Status today | Evidence |
|---|---|---|
| **A1 Reserve-basis matching** (CRVM / VM-20 / GAAP) | ✅ COMPLETE | `CONTINUATION_reserve_basis*` COMPLETE; ARCHITECTURE §4 Reserve-Basis Selection; ADR-087–092, 127, 128 |
| **A2 IFRS 17 movement table** | ✅ COMPLETE | `CONTINUATION_ifrs17_movement` COMPLETE (#87–#90); ARCHITECTURE §7 |
| **A3 Cross-jurisdiction capital** (US RBC + Solvency II) | ✅ COMPLETE | `CONTINUATION_cross_jurisdiction_capital` COMPLETE (all slices); ARCHITECTURE §7 |
| **C0 Asset / ALM model** | ✅ COMPLETE | `CONTINUATION_asset_alm` COMPLETE (ADR-108–117) |
| **B3 Sliding-scale expense allowances / experience refunds** | ✅ COMPLETE | `CONTINUATION_expense_allowance`; ARCHITECTURE §5 (ADR-118–124) |

`docs/ROADMAP.md` reflects this: **Phases 1–5 are ✅ COMPLETE** end to end
(Milestones 5.1 LICAT, 5.2 Portfolio, 5.3 IFRS 17, 5.4 Asset/ALM, 5.6
Reserve-Basis Matching, 5.7 Cross-Jurisdiction Capital all closed). The suite
stands at **2,001 unit tests + QA green**, coverage ≥ 90% enforced in CI,
ADRs current through ADR-129.

The engine can, today, price TERM / WL / UL / Disability-CI seriatim; apply
YRT (flat + tabular), Coinsurance, Modco, Stop-Loss with expense
allowances and experience refunds; reserve on NET_PREMIUM / CRVM / VM-20 /
GAAP with prescribed statutory valuation mortality; profit-test; run
scenario + Monte-Carlo UQ; measure IFRS 17 BBA/PAA/VFA **and** period
movement; compute return-on-capital under **LICAT, US RBC, and EU Solvency
II**; run asset-liability duration-gap; aggregate portfolios; and surface all
of it via CLI / FastAPI / Streamlit / a committee-grade Excel workbook.

**The commercial-readiness boundary has moved again.** In 2026-04-19 it was
"can it price a first deal." In 2026-06-18 it was "can it stand up to a
sophisticated buyer's diligence across jurisdictions." As of today, the
*modeling* answer to both is **yes**. The remaining gap is no longer a
modeling gap at all — it is a **trust-and-deployment gap**: can a buyer
*validate* the numbers against the incumbent tools, and can an IT/ops
organisation *run* the engine in production.

---

## 3. The Checkpoint Question — does interest-exactness still rank first?

The active epic (`Reserve-Basis Correctness & Interest Exactness`) has one
slice shipped (Slice 1, the WholeLife improvement bug — a genuine correctness
fix that deserved its front-of-queue priority) and two planned:

- **Slice 2** — prescribed statutory valuation-interest helper (issue-year →
  SVL max valuation rate / VM-20 NPR discount rate), wired into CRVM / VM-20
  NPR discounting.
- **Slice 3** — surface that helper on the deal path + docs.

Together these deliver **penny-exact** CRVM/VM-20 reproduction: today the
engine takes a single manual `ProjectionConfig.valuation_interest_rate`, so
statutory reserve reproduction is *directional* (right method, right
prescribed mortality via ADR-125/126) but not *penny-exact* on the interest
basis.

**Value assessment of interest-exactness: ★★★☆☆ (real, narrow).** It
completes the "reproduce the cedant's held statutory reserve" story to the
last decimal. But:

1. The **correctness** half of this epic — the part that fixed *wrong*
   behaviour — already shipped in Slice 1. What remains is *exactness* on a
   capability that already works directionally.
2. A pricing actuary reproducing a cedant reserve can already set the
   valuation rate manually to the cedant's basis and get the right answer;
   the helper removes a lookup, it does not unlock a blocked workflow.
3. The PLAN itself frames Slices 2–3 as "exactness polish that completes the
   Reserve-Basis Exactness value proposition" and prioritised Slice 1 ahead
   of them precisely because "a bug … outranks penny-exactness."

Against a frontier that has moved to trust-and-deployment, **★★★☆☆
exactness polish is no longer the highest-value continuation.** This is the
epic-level polish-spiral risk the checkpoint was written to catch — and it
has caught it.

---

## 4. Feature Catalogue — Re-ranked for 2026-07-05

Value is judged against a paying reinsurance client (pricing actuary,
CRO/CFO, IT/ops). Effort is in developer-days; "phases" is the recommended
number of staggered slices.

### Tier A — High value, multi-session (the new "big rocks")

| # | Feature | Value | Effort | Phases | Source |
|---|---------|-------|--------|--------|--------|
| **A1′** | **Validation & benchmark pack** — reproduce a published set of worked statutory reserves / textbook APVs / regulatory test decks (and, where feasible, an AXIS/Prophet side-by-side) into an executable-in-CI validation suite + a published "validation report" notebook | ★★★★★ | ~8–12 d | 3–4 | README value prop; PD-04-19 NICE (benchmark) |
| **A2′** | **Production hardening & observability** (ROADMAP 6.2 / old C1) — structured logging + correlation IDs, optional API-key auth, rate limiting, K8s manifests + Helm chart, Prometheus/Grafana compose | ★★★★☆ | ~8 d | 3 | ROADMAP 6.2 |
| **A3′** | **Cedant data-ingestion robustness** — harden the existing 4.2 ingestion pipeline for messy real-world blocks (missing/ambiguous fields, mixed date formats, unit/currency normalisation, richer `DataQualityReport` with actionable diagnostics + a rejects file) | ★★★★☆ | ~5–7 d | 2–3 | Checkpoint productization list |

**Why A1′ leads.** Polaris RE's entire thesis is "a *credible* open-source
alternative to AXIS/Prophet." The modeling is now feature-complete, but there
is **no published numerical validation** demonstrating that its reserves,
APVs, IRRs, and capital match an authoritative reference. That is the single
biggest remaining *credibility* gap and the first thing a sceptical
diligence team asks for. It is high-value and now unblocked (the models it
would validate all exist). Feasibility caveat: directly running AXIS/Prophet
may be out of reach, so the tractable form is validation against *published*
worked examples, regulatory test decks (e.g. VM-20 reserve examples, SOA
illustrative-value tables), and closed-form textbook cases — assembled into a
CI-executed suite. This needs a short scoping pass (see §6) before it becomes
a PLAN.

**Why A2′ / A3′ next.** Both are *market-access / deployability* gates. A2′
is fully specified in ROADMAP 6.2 and decomposes cleanly; A3′ hardens a
pipeline (4.2) that already exists but was built against clean sample data.

### Tier B — High value, single-to-short (quick credibility wins)

| # | Feature | Value | Effort | Phases | Source |
|---|---------|-------|--------|--------|--------|
| B1 | **Switch capital surfaces to `for_product_interim`** — expose the built C-1/C-3 factors everywhere (behaviour change → golden rebaseline + ADR) | ★★★★☆ | ~1–2 d | 1 | 2026-06-18 B1 (unshipped) |
| B2 | **Scale benchmark at 100K–500K policies** — publish a timing table; back the README performance claim | ★★★★☆ | ~1 d | 1 | 2026-06-18 B2 (unshipped) |
| B4 | **Premium-deficiency reserve / loss recognition** — turn the sufficiency analyzer into a reserve floor | ★★★☆☆ | ~1–2 d | 1 | 2026-06-18 B4 (unshipped) |

B1 and B2 are the 2026-06-18 "Sprint 0" quick wins that were **never
picked up** — the epic track (correctly) drove the Tier-A ladder instead.
They remain the cleanest between-epic fallback picks.

### Tier C — Medium value, enabling / operational

| # | Feature | Value | Effort | Source |
|---|---------|-------|--------|--------|
| C2 | Experience-monitoring automation loop (ROADMAP 6.1) — study→export→retrain | ★★★☆☆ | ~6 d | ROADMAP 6.1 |
| C3 | Funds-withheld coinsurance (`FWCoinsuranceTreaty`) | ★★★☆☆ | ~2 d | 2026-06-18 C3 |
| C4 | Parallel portfolio execution + caching + `remove_deal` | ★★★☆☆ | ~2 d | CONT-portfolio #6 |
| C5 | Per-deal hurdle rates on `Portfolio` | ★★★☆☆ | ~5 d | CONT-portfolio #4 |

### Tier D — Exactness polish / low value (deprioritise)

- **Interest-exactness helper (current epic Slices 2–3)** — reclassified here
  from Tier-A-epic to Tier-D exactness polish per §3. ★★★☆☆ but narrow;
  keep as a NICE-TO-HAVE follow-up, revive when a real cedant reproduction
  demands penny-exact interest.
- GAAP PADs on the deal path (ADR-127/128 out-of-scope follow-up), sex/smoker
  statutory-table composition, CSO-version selection, and the usual
  Excel/dashboard micro-polish.

### The picture in one view

```
        HIGH VALUE
            │  A1' Validation/benchmark pack
            │  A2' Prod hardening      B1 capital surfaces
            │  A3' Ingestion robustness B2 scale benchmark
   ─────────┼───────────────────────────────────────────
            │  C5 per-deal hurdle      B4 deficiency reserve
            │  C2 experience loop      C3 funds-withheld
            │                          [Tier D: interest-exactness, polish]
        LOW │
            └───────────────────────────────────────────
              HIGH EFFORT                     LOW EFFORT
```

---

## 5. Checkpoint Verdict & Recommended Sequence

**Verdict:** Slices 2–3 (interest-exactness) do **NOT** remain the
highest-value continuation. A productization/credibility epic out-ranks them.
Per the PLAN's checkpoint instruction ("if a productization epic out-ranks
interest-exactness, re-scope Slices 2–3 or spin up the higher-value epic and
demote these to follow-ups"), the recommendation is to **demote Slices 2–3 to
a NICE-TO-HAVE follow-up and constitute a productization epic as the next
active epic.**

**Recommended sequence:**

1. **Scoping pass on A1′ (validation & benchmark pack)** — half a session to
   confirm which authoritative references are *obtainable and executable in
   CI* (published VM-20 reserve decks, SOA illustrative values, closed-form
   textbook cases; AXIS/Prophet side-by-side only if a reference output is
   available). Output: `docs/PLAN_validation_benchmark.md` + slice 1.
   *If A1′ proves reference-blocked*, lead with **A2′ (production hardening)**
   instead — it is fully specified in ROADMAP 6.2 and has no external
   dependency.
2. **B1 + B2 as the between-epic Sprint-0 quick wins** — still unshipped from
   2026-06-18; pick them up when the new epic's next slice is blocked.
3. Interest-exactness Slices 2–3 revert to the follow-up backlog (harvested
   to `PRODUCT_DIRECTION`), revivable on a real penny-exact cedant
   reproduction requirement.

**Reserved for the maintainer (per CONTINUATION Open Question):** the
CONTINUATION explicitly asked whether, after Slice 1, the interest-exactness
slices should proceed *or* the regenerated review should be allowed to
redirect the epic. This review's recommendation is **redirect**. The final
go/no-go is surfaced for Jonathan — see §7. The next dev session should not
kill the active epic unilaterally; absent a maintainer decision it should run
the A1′/A2′ scoping pass as a *new* epic while leaving the interest-exactness
CONTINUATION open-but-deprioritised, so exactly one active epic always
exists.

---

## 6. Guard Against the *Epic-Level* Polish Spiral

The 2026-06-18 review fixed the *slice-level* polish spiral (sub-day PRs
crowding out epics). This checkpoint exists to prevent its successor: an
*epic-level* polish spiral, where the routine keeps constituting narrow
exactness epics (each individually defensible) now that the modeling roadmap
is done, rather than crossing into the harder productization/credibility
work. Interest-exactness is the first such candidate, and the recommendation
is to stop it before it starts. The rule going forward: **once the modeling
roadmap is complete, an exactness/polish epic must out-rank the best
available productization epic on value to be constituted — and it does not.**

---

## 7. Decision Surfaced for the Maintainer

> **Q: Redirect the active epic from interest-exactness to productization?**
>
> This review recommends **YES — redirect.** The modeling roadmap
> (Phases 1–5, all Tier-A epics, Asset/ALM, expense-allowance) is complete;
> interest-exactness (Slices 2–3) is ★★★☆☆ exactness polish, while a
> validation/benchmark pack (A1′) or production hardening (A2′) is the genuine
> commercial frontier. Recommended: demote Slices 2–3 to a NICE-TO-HAVE
> follow-up; next session runs a scoping pass on A1′ (validation & benchmark),
> falling back to A2′ (production hardening, ROADMAP 6.2) if A1′ is
> reference-blocked.
>
> **If you prefer to finish interest-exactness first** (e.g. a specific
> cedant reproduction requires penny-exact CRVM interest now), say so and the
> next session ships Slice 2 as planned — the CONTINUATION/PLAN remain intact
> and ready.

---

## 8. Reconciliation with `PRODUCT_DIRECTION_2026-06-18`

The latest nightly reasonability line is `PRODUCT_DIRECTION_2026-06-18.md`
(17 days old, < 30 — not regenerated here; this is a strategic doc). It
already carried the WholeLife-improvement bug (now SHIPPED, PR #128, struck
through in that file by the morning ledger-healing step) and the
prescribed-valuation-interest helper as its two lead IMPORTANT follow-ups —
i.e. exactly the two items this epic was constituted from. This review does
not contradict it; it **re-ranks** the second of those two items (interest
helper) *below* the productization frontier now that the first (the bug) is
fixed and the modeling roadmap is complete. The interest helper is not
dropped — it is demoted to a NICE-TO-HAVE follow-up with its full PLAN/
CONTINUATION preserved for revival.
