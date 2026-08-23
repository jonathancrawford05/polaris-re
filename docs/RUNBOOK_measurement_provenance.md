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

```bash
git fetch origin && git checkout <the branch carrying this runbook>

# 1. Regenerate both, into the committed paths.
uv run python scripts/experience_diligence.py --source hmd \
    --markdown docs/MEASUREMENT_experience_gam_hmd.md
uv run python scripts/experience_diligence.py --source ilec \
    --markdown docs/MEASUREMENT_experience_gam_ilec.md

# 2. LOOK AT THE DIFF. This is the whole point of the exercise.
git diff --stat docs/MEASUREMENT_experience_gam_*.md
git diff docs/MEASUREMENT_experience_gam_hmd.md

# 3. Stamp each, with a note recording where and against what.
uv run python scripts/measurement_stamp.py stamp \
    docs/MEASUREMENT_experience_gam_hmd.md \
    --assert --note "regenerated <DATE> in a session holding the HMD cache <VERSION>; diff: <none | summary>"
uv run python scripts/measurement_stamp.py stamp \
    docs/MEASUREMENT_experience_gam_ilec.md \
    --assert --note "regenerated <DATE> in a session holding the ILEC extract <VERSION>; diff: <none | summary>"

uv run python scripts/measurement_stamp.py check
```

### The diff is the finding, not the chore

Step 2 is the measurement. Whichever way it goes, say so in the note and in the
commit message:

| what the diff shows | what it means | what to record |
|---|---|---|
| **no change** | `4e7dd64` was behaviour-preserving on this path, as believed | "diff: none" — now a fact rather than an assumption |
| **numbers moved** | a second silently-stale measurement, like ADR-203's | say by how much; if any ADR or plan cites the old figures, correct them the way ADR-203 corrected its seven |
| **it fails to run** | the producer has rotted against the current cache | that is the finding; do not stamp, open it as a defect |

**Do not stamp a document you did not regenerate.** An `asserted` stamp is one
person's word that a regeneration happened somewhere this checkout cannot see. The
tool requires `--note` for exactly that reason, and a note that does not say when,
where, and against what version is not a note.

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
- **Data is not fingerprinted.** The stamp covers code, not inputs. A document
  regenerated against a different experience cache would carry an unchanged
  fingerprint, which is precisely why §3's note asks for the cache version in
  words.
- **Hardware-bound documents.** `MEASUREMENT_portfolio_parallel_macbook_air.md`
  reports timings from named hardware, so regenerating it here would not reproduce
  them by design. Its stamp answers only the narrower question: has the measured
  code moved?
- **The stamp says nothing about correctness.** Worth repeating, because a green
  gate is easy to read as more than it is.
