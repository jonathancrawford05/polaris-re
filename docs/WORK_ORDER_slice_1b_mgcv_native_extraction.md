> **Status update (2026-08-16, same day as this order):** §6's three docs-only edits and
> §7's sweep items are **already done**, folded into PR #197 before merge rather than as a
> follow-up — see `docs/PLAN_mgcv_parity_engine.md` slice 1 / slice 1b,
> `docs/CONTINUATION_mgcv_parity_engine.md`, and commit `9154023` (the sweep: dropped
> `Any` for `RTermPayload`, fixed the two new mypy errors, `gam_term_extract.R` now reads
> its fixed λ from the manifest's `l1-interior` cell, `d3` added to both comparison sites,
> dtype added to the 8 test fixtures, the job-summary header's literal pipes fixed).
>
> **§§1-5 and §8-9 — DONE, 2026-08-16 (this session).** The R-side `smoothCon` branch
> (`extract_smooth_one`), the Python-side `extract_smooth_terms` and `knots` comparison,
> the index-range design question settled as ADR-192, and the R-gated end-to-end test are
> all shipped — see `docs/PLAN_mgcv_parity_engine.md` slice 1b and
> `docs/CONTINUATION_mgcv_parity_engine.md` for what shipped and the bug the harness caught
> on its first run. Tier 1 confirmed (`docs/CONFORMANCE_LEDGER.md`); tier-3 dispatched with
> this PR. The order is kept verbatim below as the authoritative spec this session followed.

---

# Work order — mgcv-parity slice 1b: mgcv-native per-term extraction

**Raised by:** PR #197 review (2026-08-16)
**Epic:** `docs/PLAN_mgcv_parity_engine.md` / `docs/CONTINUATION_mgcv_parity_engine.md`
**Gate:** provision this **before** slice 2 opens.
**Disposition of PR #197:** the code is correct, tested and green — it should merge. What
needs to change before merge is only the *labelling* (§6 below, three docs-only edits).
Do not hold the code for slice 1b.

---

## 1. Why this exists — a premise correction

`docs/CONTINUATION_mgcv_parity_engine.md` and PR #197 both defer mgcv-native extraction
(`cr`/`ti`/`sz` via `smoothCon()`) to slice 2 on the grounds that building it now would be
speculative work "with nothing yet to verify it against" (Anchor 8).

**That premise does not hold.** The referent exists, is committed, and is already green at
tier 3 — from the *previous* slice:

`scripts/smoothcon_lpmatrix_probe.R` already calls
`smoothCon(s(x, k=k, bs="cr"), data=df, knots=knots_arg, absorb.cons=TRUE)[[1]]` and
cross-checks the resulting `X` and `S` against an **independent route to the same
matrices** — the fitted model's `predict(type="lpmatrix")` smooth block and
`m$smooth[[1]]$S[[1]]` — across three cases (`k=8` default knots, `k=13` default knots,
`k=8` supplied knots). Max abs diff `0.0`. Confirmed at tier 3, CI run
[31907362222](https://github.com/jonathancrawford05/polaris-re/actions/runs/31907362222),
and recorded as ADR-191.

That is the *same shape of proof* PR #197 just performed for the `raw` path: read the
fitted object, check it against a second route to the same thing. It needs no Python `cr`
basis, so Anchor 8 does not bite.

What is actually missing is **packaging**, not verification. The probe emits ad-hoc scalar
diffs; it does not emit the per-term JSON schema `gam_stage_a.py` consumes, and there is no
Python counterpart to receive it.

**The tell that slice 1 is unfinished rather than cleanly bounded:**
`TermExtract.knots` (`src/polaris_re/analytics/gam_stage_a.py:82`) exists, is *always*
`None`, is never compared by `compare_term_extract`, and its own docstring says
"Populated once slice 2 adds mgcv-native extraction." A field on the data contract with no
producer and no assertion is half a harness, not a slice boundary.

---

## 2. Scope of slice 1b

**R side — `scripts/gam_term_extract.R`**

Add a `smoothCon` branch that emits the **existing** per-term JSON schema (`label`,
`index_start`, `index_end`, `X`, `S`, `rank`, `knots`) for an mgcv-native term, alongside
the current `raw` branch. Do not fork the schema.

Include the probe's own assertion as the extractor's **internal consistency guard**: the
extracted `X` must equal the corresponding block of `predict(m, type="lpmatrix")`, and the
extracted `S`/`rank`/`knots` must equal `m$smooth[[j]]$S`/`$rank`/`$xp`. This promotes a
one-off diagnostic into a standing guard, and it is what makes the extractor
self-verifying without any Python basis.

**Python side — `src/polaris_re/analytics/gam_stage_a.py`**

- `extract_smooth_terms()` (or equivalent) — the mgcv-native counterpart to
  `extract_raw_terms`, which currently raises on any non-`"raw"` term (`:138`).
- Extend `compare_term_extract` (`:181`) to compare **knots**. It presently compares index
  range, design, every `S_j`, and rank — knots are silently ignored, which is exactly the
  field slice 1b makes meaningful.

**Tests — `tests/test_analytics/test_gam_stage_a.py`**

Mirror the existing structure: pure-Python validation/refusal tests that always run, plus
an R-gated end-to-end test alongside
`test_the_r_extractor_agrees_with_the_python_side_on_every_design`.

---

## 3. Verified field mapping — every quantity is available

Measured directly on R 4.3.3 / mgcv 1.9.1 during the #197 review (`bs="cr"`, `k=8`,
`n=200`, seed 20120101), so this does not need rediscovering:

| `TermExtract` field | `smoothCon(absorb.cons=TRUE)` source | Independent referent | Agrees |
|---|---|---|---|
| `label` | `sm$label` → `"s(x)"` | — | — |
| `design` | `sm$X` → 200×7 | `lpmatrix` smooth block | ✅ (ADR-191, 0.0) |
| `s` | `sm$S[[1]]` → 7×7 | `m$smooth[[1]]$S[[1]]` | ✅ (ADR-191, 0.0) |
| `rank` | `sm$rank` → 6 | `m$smooth[[1]]$rank` → 6 | ✅ |
| `knots` | `sm$xp` → 8 values | `m$smooth[[1]]$xp` | ✅ identical |

---

## 4. One genuine design question — settle it in 1b, not mid-slice-2

`first.para` / `last.para` come back **empty on a bare `smoothCon` object** and are only
populated on the fitted model (`2`..`8` in the measurement above). `TermExtract` *requires*
an index range and validates the design/penalty shapes against it
(`gam_stage_a.py:88-108`).

So decide, in writing: is a term's coefficient index range read from a fit, or assigned by
the harness when it assembles terms into a model? The isolated-term harness that ADR-191's
referent decision makes possible is precisely the case where no fit exists. Settle this
while the `raw` path is fresh — it is a property of the assembled model, not of a term, and
getting it wrong later means reworking the data contract mid-epic.

---

## 5. Acceptance criteria for slice 1b

- `gam_term_extract.R` emits the same per-term schema for an mgcv-native `cr` term, with
  both **default** and **supplied** knots.
- The extractor's internal guard passes: extracted `X`/`S`/`rank`/`knots` agree with the
  fitted model's `lpmatrix` block and `m$smooth[[j]]$S`/`$rank`/`$xp`.
- Python counterpart consumes it; `compare_term_extract` compares knots.
- The index-range question of §4 is decided **in writing** (ADR, following ADR-191's form).
- Confirmed at **tier 3** per `ROUTINE_MGCV_PARITY.md` step 2 — this is a structural claim
  about reading a specific mgcv version's fitted object, the same class that earned ADR-191
  and #197 a tier-3 requirement. Tier 1 alone is not sufficient.
- `docs/CONFORMANCE_LEDGER.md` carries both readings.
- Suite green; `tests/qa/` untouched; goldens byte-identical (non-final epic slice).

---

## 6. Fix the acceptance criterion that allowed the drift — and the three docs-only edits to #197

> **Done 2026-08-16** — see the status banner at the top of this file.

Slice 1's criterion reads *"Stage A runs green on the existing basis."* The existing basis
is precisely the one with **no `smoothCon` path**, so raw-only work satisfies it literally
while leaving the mgcv-native half — the half every later slice depends on — unbuilt. That
wording is the root cause, not the implementer's judgement.

**Rewrite it to:** *the extractor handles both a supplied basis and an mgcv-native basis,
each cross-checked against the fitted model.*

**Amend PR #197 before merge (documentation only, no code):**

1. `docs/PLAN_mgcv_parity_engine.md` §3 slice 1 — `Status: NEXT` is stale; set it to
   `DONE (raw path only)` and insert slice 1b with the scope above. Also fix the criterion
   wording per this section.
2. `docs/CONTINUATION_mgcv_parity_engine.md` — slice 1 currently reads a flat **DONE**;
   relabel to **DONE (raw path only)**, add **slice 1b → NEXT**, and move slice 2 behind it.
3. `docs/DEV_SESSION_LOG_2026-08-15b_…md` line ~18 — "PR #196 itself was closed without
   merging on GitHub" is factually wrong. #196 **was merged** (`merged_at`
   2026-08-15T21:59:13Z; `main`'s tip `1534b1f` *is* its merge commit, from branch
   `claude/sharp-galileo-hxklz3`). No code consequence, but the audit trail should read true.

Slice 2's own scope then narrows to the actual math question — does Python's `cr` basis
match mgcv's — which is what it was scoped as in the first place.

---

## 7. Sweep in with 1b (from the #197 review — same files, no separate polish PR)

> **Done 2026-08-16, commit `9154023`** — see the status banner at the top of this file.
> Kept verbatim below as the record of what the review found and why each fix was made.

- **[P1]** `gam_stage_a.py:31,181` — `from typing import Any` / `dict[str, Any]`. CLAUDE.md
  §5 and §10 name this a *never*, and it is the only occurrence of `Any` in all of `src/`.
  The docstring cites `compare_mgcv_conformance.py` as precedent, but that script passes
  `json.loads(...)` results **unannotated** — it never writes `dict[str, Any]`. A `TypedDict`
  for the R payload's keys documents the schema in the type and drops the `Any`.
- **[P1]** `gam_stage_a.py:123` and `:151` — two new mypy errors: `terms` inferred as
  `tuple[TermSpec]`, and `s_blocks = ()` against a branch assigning a 2-tuple of arrays.
  Annotate `terms: tuple[TermSpec, ...]` and `s_blocks: tuple[np.ndarray, ...]`. CI's mypy
  is `continue-on-error`, so these otherwise land silently in the ~207-error baseline.
- **[P1]** `gam_term_extract.R:72` — `lambda_age = 10, lambda_year = 100` hardcoded with a
  comment claiming they match the committed `l1-interior` cell. They do today
  (`ConformanceCell("l1-interior", "d1", (1,3,4), 10.0, 100.0)`), but the same
  `manifest.json` the script already parses carries `cells[].lambda_age`/`lambda_year`, and
  the sibling `scripts/mgcv_conformance.R` reads them from it (`spec$lambda_age`). Read the
  cell from the manifest so the comment is enforced rather than asserted.
- **[P1]** `tests/test_analytics/test_gam_stage_a.py` — 8 `np.zeros(...)`/`np.eye(...)`
  without explicit `dtype` (REVIEW.md rates dtype omission P1). These are now 8 of the 10
  dtype-implicit constructions in the whole suite; the sibling
  `test_experience_mgcv_conformance.py` passes `dtype=np.float64`.
- **[P2]** `gam_term_extract.R:124` — the extractor probes **three** designs (filter is
  `n_coef > 0`) and prints "3 design(s)", but both comparison sites (the pytest test and the
  CI step) hardcode `d1`/`d2`, so `d3`'s output is produced and discarded. Verified during
  review that **`d3` agrees** (`n_tensor = 50` — a third design width neither current case
  exercises; max abs X diff 4.996e-16, S diff 0.0, rank diff `(0, 0)`). Either compare it or
  narrow the filter so "3 design(s)" cannot be misread as three verified.
- **[P2]** `.github/workflows/mgcv-conformance.yml:428` — job-summary table header has
  literal pipes (`max|X diff|`), splitting the cells and breaking the rendered table (10
  header cells vs 6 separators). Inherited pattern — line 227 does the same. `max abs X diff`
  fixes both.
- **[P2]** Rank is derived from `np.linalg.matrix_rank`'s **default** tolerance while R
  reports mgcv's own. Fine on well-conditioned difference penalties and measured — but rank
  is the one field both sides compute independently, so 1b should choose the tolerance
  deliberately rather than inherit numpy's default.

---

## 8. Non-goals for 1b

- **Do not** build the Python `cr` basis — that stays slice 2. 1b is the harness half only.
- **Do not** touch `tests/qa/` or regenerate `tests/qa/golden_outputs/`. Non-final epic
  slice: goldens stay byte-identical.
- **Do not** touch `products/`, `reinsurance/`, or the CLI.
- **Do not** fix the `data/mortality_tables` environment gap — separately harvested as
  2nd-order NICE-TO-HAVE. (Review confirmed the diagnosis: with the tables converted, all 5
  failures and 22 skips disappear — 3344 passed / 0 failed, `tests/qa/` 94/94.)

---

## 9. Routine obligations

- State the **baseline** in the session log (`ROUTINE` step 4) — note that it varies with
  whether `data/mortality_tables` is populated, so record which.
- One `perf/history.jsonl` row, append-only, commit-pinned (ADR-177), with the **creep
  verdict** stated in the log or PR body — #197 omitted the verdict (it is: no structural
  creep, `insufficient_data: false`, 15 rows).
- Harvest follow-ups into the latest `PRODUCT_DIRECTION` with provenance **and order tags**.
- Record the actual `claude/*` branch used.
- Ledger closures use the house style — `~~entry~~` — **SHIPPED** (PR #N) — never delete.
