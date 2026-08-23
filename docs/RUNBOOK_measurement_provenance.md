# Runbook — measurement provenance stamps

**What this is for.** ADR-203 found `docs/MEASUREMENT_unconditional_coverage.md`
carrying figures that no longer reproduced. The cause was `ce0b9f1` — a *correct*,
maintainer-authorized fix to `experience_gam_penalized.reml_score` that changed the
REML criterion and therefore the selected λ on every replicate. Nothing re-ran the
study, so the numbers were silently invalidated and stayed cited as current for four
days across seven documents, including the ADR whose registered prediction was being
tested against them.

The stamp makes that visible. It is the SHA-256 of the *transitive* `polaris_re`
import closure of a document's producer. If any module the producer reaches changes,
CI says so.

**A stamp is not evidence the numbers are right.** It says only that the code the
document was generated from is the code that is here now. Read `ADR-204` and the
module docstring of `polaris_re/utils/measurement_provenance.py` before relying on it
for more than that.

---

## 1. Everyday use

```bash
# What is the state of every measurement document?
uv run python scripts/measurement_stamp.py list

# The CI gate, run locally. Exit 1 iff a stamped document has drifted.
uv run python scripts/measurement_stamp.py check
```

`check` fails **only** on drift in a document that carries a stamp. Unstamped
documents warn and pass — six were unstamped when this landed and two cannot be
regenerated outside a session holding the experience cache. A gate that failed the
build for those on day one would have been switched off inside a week.

---

## 2. When CI tells you a document drifted

You changed code a committed measurement depends on. Three legitimate responses, in
order of preference:

**(a) Re-run and re-stamp.** The document is regenerable here:

```bash
uv run python scripts/measurement_stamp.py stamp docs/MEASUREMENT_unconditional_coverage.md --run
```

`--run` executes the manifest's regeneration command, and **refuses to stamp if it
exits non-zero** — a stamp on a document whose producer just failed would be a false
vouching. Commit the regenerated document *and* its stamp together.

**(b) Re-run elsewhere, then assert.** See §3.

**(c) Record why the change does not touch the measured path.** This is a real
answer and sometimes the right one — `ce0b9f1` was correct, and the extraction of
the band layer in `4e7dd64` was behaviour-preserving. But it is a *claim*, so make
it in the ADR that accompanies the change, then re-stamp with `--assert --note`
pointing at that ADR. Do not silently re-stamp.

**What is never an answer:** removing the manifest entry, or wrapping the CI step in
`continue-on-error`. Both convert "nobody checked" back into "CI is green", which is
the condition this exists to end.

---

## 3. Refreshing the cache-backed documents

`MEASUREMENT_experience_gam_hmd.md` and `MEASUREMENT_experience_gam_ilec.md` are
produced by `scripts/experience_diligence.py`, which reads a local experience cache
that is **not in the repository** (see `RUNBOOK_experience_data_acquisition.md`).
They cannot be regenerated in CI, in a fresh container, or in any session without
that cache.

Both are currently **unverified**: ADR-203's audit flagged them as older than
`experience_gam.py`'s 2026-08-09 change (`4e7dd64`, a behaviour-preserving
extraction of the band layer), and nobody has confirmed either way.

### From a session that has the cache

> **Read this box before running anything.** `MEASUREMENT_experience_gam_hmd.md`
> and `..._ilec.md` are **written readings, not harness output.** The files the
> script generates are in `docs/measurements/`, and that directory's own README is
> explicit: *"generated verbatim and never hand-edited. A re-run overwrites them
> and the diff is the finding. That is why they are separate from the
> `docs/MEASUREMENT_*.md` documents one level up."*
>
> So **never** point `--markdown` at a `docs/MEASUREMENT_*.md` path. Doing so
> replaces a hand-written analysis — caveats, licensing text, verdict — with raw
> output. An earlier version of this runbook told you to do exactly that; it was
> wrong and is corrected here.

```bash
git fetch origin && git checkout main

# 1. Regenerate the RAW output only. Flags are from docs/measurements/README.md;
#    they are not defaults, and running without them produces a spurious diff.
uv run python scripts/experience_diligence.py --source hmd \
    --country USA --min-year 1990 --max-year 2019 \
    --markdown docs/measurements/experience_gam_hmd_usa.md \
    -o docs/measurements/experience_gam_hmd_usa.json
uv run python scripts/experience_diligence.py --source hmd \
    --country GBRTENW --min-year 1990 --max-year 2019 \
    --markdown docs/measurements/experience_gam_hmd_gbrtenw.md \
    -o docs/measurements/experience_gam_hmd_gbrtenw.json

uv run python scripts/experience_diligence.py --source ilec --year-df 3 \
    --markdown docs/measurements/experience_gam_ilec.md \
    -o docs/measurements/experience_gam_ilec.json
uv run python scripts/experience_diligence.py --source ilec --year-df 3 \
    --duration-bands \
    --markdown docs/measurements/experience_gam_ilec_duration_banded.md \
    -o docs/measurements/experience_gam_ilec_duration_banded.json
uv run python scripts/experience_diligence.py --source ilec --year-df 2 \
    --year-degree 2 --duration-bands \
    --markdown docs/measurements/experience_gam_ilec_duration_banded_quadratic.md \
    -o docs/measurements/experience_gam_ilec_duration_banded_quadratic.json

# 2. THE DIFF IS THE MEASUREMENT. Read it before doing anything else.
git diff --stat docs/measurements/
git diff docs/measurements/

# 3. Only if step 2 is clean (or you have revised the analyses to match), stamp.
uv run python scripts/measurement_stamp.py stamp \
    docs/MEASUREMENT_experience_gam_hmd.md \
    --assert --note "raw output regenerated <DATE> against HMD cache <VERSION>; docs/measurements diff: <none | summary>"
uv run python scripts/measurement_stamp.py stamp \
    docs/MEASUREMENT_experience_gam_ilec.md \
    --assert --note "raw output regenerated <DATE> against ILEC <FILE/VERSION>; docs/measurements diff: <none | summary>"

uv run python scripts/measurement_stamp.py check
```

### The diff is the finding, not the chore

Step 2 is the measurement. Whichever way it goes, say so in the note and in the
commit message:

| what the diff shows | what it means | what to do |
|---|---|---|
| **no change** | the harness is unchanged on this path | note "diff: none" — now a fact rather than an assumption; stamp both |
| **numbers moved** | a second silently-stale measurement, like ADR-203's | **the `MEASUREMENT_*.md` analyses above may now be wrong.** Read them against the new numbers and revise before stamping; correct anything citing the old figures |
| **it fails to run** | the producer has rotted against the current cache | that is the finding. Do not stamp; open it as a defect |

**Do not stamp a document you did not verify.** An `asserted` stamp is one
person's word that a regeneration happened somewhere this checkout cannot see.

### Cache version, please

The notes above ask for a cache version because a regeneration is only as
reproducible as its inputs. If the HMD or ILEC extract is versioned or dated,
record that; if it is not, record the acquisition date from
`RUNBOOK_experience_data_acquisition.md`. A document whose stamp says "regenerated
against something" is barely better than an unstamped one.

---

## 4. Adding a new measurement document

Add a `MeasurementSource` row to `MANIFEST` in
`src/polaris_re/utils/measurement_provenance.py`, then stamp it.

`test_the_manifest_covers_every_measurement_document_on_disk` fails if a
`docs/MEASUREMENT_*.md` exists with no manifest row — otherwise a new document would
sit outside the gate forever and nothing would ever say so.

---

## 5. Known limitations, stated rather than discovered later

- **Absolute imports only.** The closure walker does not follow relative imports.
  `polaris_re` uses none today (checked). If they are introduced,
  `dependency_closure` must be extended *before* they land — a walker that skips
  them under-reports the closure, and under-reporting is a false pass.
- **Package re-exports ARE followed, since 2026-08-23.** `from polaris_re.core
  import ReserveBasis` resolves through `core/__init__.py` to the defining module.
  It did not originally, and that was a live false-pass channel rather than a
  hypothetical one: measured on this repository, such a producer omitted
  `core/reserve_basis.py` from its closure entirely while the document still
  looked vouched-for. Found by PR #208's review; pinned by
  `test_a_from_package_import_name_reaches_the_defining_module`. The general
  lesson for anyone extending the walker: **every unfollowed import is a false
  pass**, and a false pass is the only failure this gate cannot survive.
- **Data is not fingerprinted.** The stamp covers code, not inputs. A document
  regenerated against a different experience cache would carry an unchanged
  fingerprint, which is precisely why §3's note asks for the cache version in
  words.
- **Hardware-bound documents.** `MEASUREMENT_portfolio_parallel_macbook_air.md`
  reports timings from named hardware, so regenerating it here would not reproduce
  them by design. Its stamp answers only the narrower question: has the measured
  code moved?
- **One known producer defect is deliberately NOT fixed, and the gate is why.**
  The `.md` files `scripts/experience_diligence.py` writes still claim *"report
  schema v1 … reproduces this file byte for byte"*. Both halves are now doubtful:
  the schema gained fields on 2026-08-23 (`age_degree`, `year_degree`,
  `duration_degree`, `interior_knots`) while still calling itself v1, and the
  byte-for-byte claim is contradicted by observed last-ulp jitter and already
  withdrawn in `docs/measurements/README.md`.

  Fixing it means editing `experience_diligence.py` — which is **in the import
  closure of both cache-backed documents**, so it would immediately drift their
  stamps, and re-stamping needs a session with the experience cache. This is the
  first case of the gate constraining a change rather than merely reporting on
  one, and the constraint is correct: the fix and the re-stamp belong in the same
  cache-holding session, not in a drive-by edit that leaves two documents drifted
  with no way to clear them.

- **The stamp says nothing about correctness.** Worth repeating, because a green
  gate is easy to read as more than it is.
