# Runbook: acquiring HMD and SOA-ILEC experience data for the GAM

**Purpose:** get real mortality-experience data onto your machine in the exact
shape `polaris_re.analytics.experience_loaders` already parses, so the tensor MI
GAM can be fitted against **real** experience rather than the synthetic
injected-surface fixtures every slice of the A4′ epic used.

**Who runs this:** you, locally. Not an autonomous session, and not CI — both by
design and by necessity. See "Why you and not the routine" below.

---

## 0. The one rule: loaders, not data

Nothing you download here goes into the repo, the Docker image, or CI. That is
`PLAN_experience_gam.md` Design Anchor 6. Everything lands in a cache directory
that is outside the repo tree by default.

Design Anchor 6 is a *conduct* rule and it is ours; it is deliberately stricter
than any licence would need to be. What the HMD and SOA terms themselves require
is a separate question, and one nobody on this project has yet answered from the
terms — see `DATA_LICENSING.md` §4, which states the open items rather than
asserting a conclusion. Attribution for both sources is in `DATA_LICENSING.md` §2.

```bash
# Where the loaders look, in precedence order:
#   1. $POLARIS_EXPERIENCE_CACHE_DIR
#   2. $POLARIS_DATA_DIR/experience_cache
#   3. ./data/experience_cache          <-- in-repo fallback (gitignored)

# Make it PERSISTENT, not just this shell — you will download data in one
# session and run the harness in another. A bare `export` dies with the window
# and the loaders then silently fall back to the in-repo path.
echo 'export POLARIS_EXPERIENCE_CACHE_DIR="$HOME/polaris-experience-cache"' >> ~/.zshrc
source ~/.zshrc
mkdir -p "$POLARIS_EXPERIENCE_CACHE_DIR"
```

Use the `$HOME` override rather than the in-repo fallback: it makes an accidental
`git add -A` structurally impossible rather than merely forbidden. (The fallback
`data/experience_cache/` *is* gitignored, so neither path leaks — but licensed
files are better off outside the repo tree entirely.)

### Verify it took

Do **not** check by typing the variable name, with or without a `$` — a bare name
is a command to zsh (`command not found`), and `$NAME` expands and then tries to
*execute* the path (`no such file or directory: /Users/you/...`). Confusingly,
that second error is what success looks like: only a correctly-set variable could
have expanded to that path.

```bash
echo "$POLARIS_EXPERIENCE_CACHE_DIR"    # the $ and the quotes both matter
```

The check that actually decides things is what **the loaders** resolve, since
that is the value the code uses:

```bash
uv run python -c "from polaris_re.analytics.experience_loaders import default_experience_cache_dir; print(default_experience_cache_dir())"
```

If that prints your `$HOME` path, everything below will land in the right place.

---

## 1. HMD — Human Mortality Database (population, free, registration required)

**What it gives you:** Deaths and Exposures as age × calendar-year matrices by
sex — exactly the `(attained_age, calendar_year)` Lexis structure the tensor
surface `te(age, calendar_year)` consumes. Population, not insured: no
select/duration, no smoker, no underwriting class. This is the **primary
real-data regression fixture** for the MI surface.

### 1a. Register

1. Go to <https://www.mortality.org> → **DATA** → **User Agreement**, read it,
   then create an account (free).
2. **Read the User Agreement while you are there** — and if you do, record what it
   says in `DATA_LICENSING.md` §4, which is currently an open item. HMD is widely
   described as open-data-principled and attribution-bearing, but this project has
   only ever repeated that second-hand. We commit *findings* only, which is
   conservative under any reading; the attribution block is in
   `DATA_LICENSING.md` §2a.

### 1b. Download — the simple path

From the site menu you screenshotted: **DATA → Zipped Data Files**, then pick a
country. You want the **"Statistics"** bundle (or the individual `STATS` files).
Inside it, the two files that matter:

```
Deaths_1x1.txt
Exposures_1x1.txt
```

`1x1` means one-year age × one-year period — do **not** substitute `1x5`, `5x1`
or `5x5`; the parser expects single-age, single-year cells.

Place them under the cache in the layout `fetch_hmd` would have produced, so
either acquisition route lands in the same place:

```bash
C=USA   # or GBRTENW, CAN, JPN, ... — see DATA → Country Codes
mkdir -p "$POLARIS_EXPERIENCE_CACHE_DIR/hmd/$C"
mv ~/Downloads/Deaths_1x1.txt     "$POLARIS_EXPERIENCE_CACHE_DIR/hmd/$C/Deaths_1x1.txt"
mv ~/Downloads/Exposures_1x1.txt  "$POLARIS_EXPERIENCE_CACHE_DIR/hmd/$C/Exposures_1x1.txt"
```

### 1c. Download — the programmatic path (optional)

`experience_loaders.fetch_hmd()` builds the URL
`{HMD_BASE_URL}/{country}/STATS/{Deaths|Exposures}_1x1.txt` and streams it to the
same cache layout. It needs an authenticated HMD session on your machine, and its
transport is injectable, so if the default `urllib` call 401s you can pass your
own downloader carrying a session cookie:

```python
from polaris_re.analytics.experience_loaders import fetch_hmd
paths = fetch_hmd("USA")          # -> {"deaths": Path(...), "exposures": Path(...)}
```

If that fights you, use 1b. Manual download is not a lesser path here — it is
one-time, and the parser cannot tell the difference.

### 1d. Verify it parses

```bash
uv run python -c "
from polaris_re.analytics.experience_loaders import load_hmd, default_experience_cache_dir
d = default_experience_cache_dir() / 'hmd' / 'USA'
cells = load_hmd(d / 'Deaths_1x1.txt', d / 'Exposures_1x1.txt',
                 min_year=1990, max_year=2019, min_age=25, max_age=95)
print(cells.shape)
print(cells.head())
print('years', cells['calendar_year'].min(), '-', cells['calendar_year'].max())
print('total deaths', cells['death_count'].sum())
"
```

You should get canonical cells with `attained_age`, `calendar_year`, `sex`,
`central_exposure`, `death_count`. If that runs, the data is usable.

### 1e. Which country and window to pull

Ask for **USA 1990–2019**, ages 25–95, both sexes, as the primary fixture.
Reasons, in order:

- The insured book Polaris prices is US/Canadian; a US population improvement
  surface is the closest free analogue.
- 1990–2019 spans the well-documented US **improvement slowdown after ~2010** —
  a real structural feature with an independent published record. That gives the
  GAM something falsifiable to recover, which synthetic data never can.
- Stopping at 2019 keeps COVID out of the fit. Pull 2020–2022 as well if you
  want, but as a *separate* window: a tensor surface fitted through the COVID
  shock will attribute it to smooth improvement, which is wrong and would
  discredit the output.

Optionally add **GBRTENW** (England & Wales) as a second country — it has its own
documented post-2011 slowdown, so agreement across two populations is a much
stronger claim than one.

---

## 2. SOA-ILEC — insured experience (manual download, terms of use)

**What it gives you:** the Individual Life Experience Committee grouped
exposed-and-deaths flat file — insured lives, with all three Lexis axes
(`issue_age`, `duration`, `attained_age`) plus gender, smoker, plan, face band
and preferred class, and **both** policy-count and amount exposure. This is the
*validation* source: it is what your actual product line looks like, where HMD is
a population proxy.

### 2a. Get it

1. SOA Research → Experience Studies → **Individual Life Experience Report /
   ILEC**. The dataset is published as a large zipped CSV per vintage
   (the 2009–2018 release is the commonly used one).
2. Accept the SOA terms of use. **There is no fetch helper for ILEC on purpose** —
   it is a manual, terms-accepting download, and `experience_loaders` documents it
   as such. **Read what you are accepting and record it in `DATA_LICENSING.md`
   §4** — specifically whether the terms speak to *derived aggregates* as well as
   to the dataset, which is the question that decides whether the committed A/E
   tables stay as they are. The attribution block is in `DATA_LICENSING.md` §2b.
3. Unzip **with `-d`**, or the files land in your current directory:

```bash
mkdir -p "$POLARIS_EXPERIENCE_CACHE_DIR/ilec"
unzip -d "$POLARIS_EXPERIENCE_CACHE_DIR/ilec" ~/Downloads/ilec-mort-text-*.zip
```

`unzip` extracts to the **current working directory**, not to the archive's
directory. Running it from inside the repo drops a multi-GB licensed file into
your working tree, where `.gitignore` does not cover it (the ignore rule is for
`data/experience_cache/`, not the repo root). If that has already happened, move
the files and confirm:

```bash
mv "ILEC_2012_19 - "*.txt "ILEC 2012_19 - Data Dictionary.xlsx" \
   "$POLARIS_EXPERIENCE_CACHE_DIR/ilec/"
git status --short          # must print nothing
```

### Known facts about the 2012-2019 release

Verified against a real download on 2026-08-03
(`ILEC_2012_19 - 20240429.txt`, ~12 GB, 30 columns):

- **Tab-delimited**, despite the `.txt` name. Pass `separator="\t"` — the
  extension carries no format information, the separator does.
- **Underscored headers** (`Observation_Year`, not `Observation Year`), and
  **`Sex` rather than `Gender`** — a genuine rename, so mechanically replacing
  spaces with underscores in the default map still misses it.
- **No distribution-channel column.** `channel` is optional; the loader carries
  only the keys present.
- Use the shipped map: `load_ilec(path, separator="\t",
  column_map=ILEC_2012_19_COLUMN_MAP)`.
- The release also carries `ExpDth_VBT2015_Cnt` / `_Amt` (SOA's own expected
  deaths on the VBT 2015 basis) and `ExpDth_VBT2015wMI_*` (with mortality
  improvement). These are the **independent A/E denominator** — an external check
  on the GAM's improvement surface computed by SOA on the same cells from the same
  exposure. Carried by `load_ilec(..., include_expected=True)` and used
  automatically by the diligence harness in §3.

### 2b. Check the column headers before anything else

**This is the step most likely to bite.** ILEC header spellings differ between
vintages, and the loader ships a default map targeting the common flat-file
names:

| ILEC source column | canonical |
|---|---|
| `Observation Year` | `calendar_year` |
| `Attained Age` | `attained_age` |
| `Issue Age` | `issue_age` |
| `Duration` | `duration` (1-based policy year) |
| `Gender` | `sex` |
| `Smoker Status` | `smoker` |
| `Insurance Plan` | `product` |
| `Face Amount Band` | `band` |
| `Preferred Class` | `uw_class` |
| `Distribution Channel` | `channel` |
| `Policies Exposed` | `central_exposure` |
| `Death Count` | `death_count` |
| `Amount Exposed` | `amount_exposed` |
| `Death Claim Amount` | `death_amount` |

Dump your file's actual header and diff it against that list:

```bash
uv run python -c "
import polars as pl
from polaris_re.analytics.experience_loaders import ILEC_COLUMN_MAP
cols = pl.scan_csv('PATH/TO/ilec.csv', infer_schema_length=0).collect_schema().names()
print('missing from your file:', sorted(set(ILEC_COLUMN_MAP) - set(cols)))
print('unmapped in your file :', sorted(set(cols) - set(ILEC_COLUMN_MAP))[:20])
"
```

Anything in "missing" needs an override — `load_ilec(..., column_map={...})`
takes a per-vintage map. For the 2012-2019 release that map already ships as
`ILEC_2012_19_COLUMN_MAP`; for any other vintage, send me the diff and I'll write
it.

If `n_cols` comes back as **1**, the separator is wrong — `load_ilec` now rejects
that up front with a message naming the likely fix, rather than letting it
surface later as a baffling "missing measure column" against a one-item list.

### 2c. Verify it parses

```bash
uv run python -c "
from polaris_re.analytics.experience_loaders import load_ilec, ILEC_2012_19_COLUMN_MAP
F = '$POLARIS_EXPERIENCE_CACHE_DIR/ilec/ILEC_2012_19 - 20240429.txt'
cells = load_ilec(F, separator='\t', column_map=ILEC_2012_19_COLUMN_MAP)
print(cells.shape); print(cells.head())
print('years', cells['calendar_year'].min(), '-', cells['calendar_year'].max())
print('total deaths', cells['death_count'].sum())
print('total exposure', cells['central_exposure'].sum())
"
```

This reads the file **lazily** and aggregates as it streams, so peak memory
tracks the number of output cells rather than the 12 GB of input. It will still
take a few minutes — that is disk throughput, not a hang.

---

### 2d. Settle `uw_class = "NA"` — pool or drop?

The load returns `uw_class` as the literal string `"NA"`, not null. That is
ambiguous in a way that changes the fit:

- **Not applicable** — the policy has no preferred-class structure at all (common
  for older permanent and simplified-issue business). Then `"NA"` is a legitimate
  category and must be **pooled as its own level**.
- **Not disclosed** — the contributor did not report a class that exists. Then it
  is missing data, and pooling it blends distinct underwriting populations into
  one cell.

The data dictionary `.xlsx` may say outright. **Faster and more reliable: let the
file answer.** The release carries `Preferred_Indicator` and
`Number_of_Pfd_Classes`, which the loader drops but which decide this:

```bash
F="$POLARIS_EXPERIENCE_CACHE_DIR/ilec/ILEC_2012_19 - 20240429.txt"
uv run python - "$F" <<'PY'
import sys
import polars as pl
lf = pl.scan_csv(sys.argv[1], separator="\t", infer_schema_length=0)
out = (
    lf.select("Preferred_Class", "Preferred_Indicator", "Number_of_Pfd_Classes")
      .group_by("Preferred_Class", "Preferred_Indicator", "Number_of_Pfd_Classes")
      .len()
      .sort("len", descending=True)
      .head(25)
      .collect(engine="streaming")
)
print(out)
PY
```

**Reading it.** If every `Preferred_Class == "NA"` row also has
`Preferred_Indicator` meaning *no* (0 / "N" / "No") and `Number_of_Pfd_Classes`
of 0 or 1, then `"NA"` is **not applicable** — a real category, pool it. If `"NA"`
appears alongside rows whose indicator says a preferred structure *does* exist,
it is **not disclosed** for those, and those cells should be dropped from any fit
that conditions on underwriting class.

**The 2012-2019 answer (run 2026-08-04, so you need not re-run it):**

| Preferred_Class | Indicator | N classes | rows |
|---|---|---|---|
| `NA` | 0 | `NA` | 14,615,884 |
| numbered 1–4 | 1 | 2 / 3 / 4 | ~26.9M |
| `U` | `U` | `U` | 798,461 |

`NA` is **not applicable** — pool it. `U` is **unknown** — hold it out of
class-conditioned inference. And the query turned up a third thing neither label
would have suggested: `Preferred_Class` alone is **ambiguous**, because class "2"
of 2 is the worst class while class "2" of 4 is second-best. `load_ilec` now
composes the two into `"2of2"` / `"2of4"` automatically for this vintage.

## 3. Run the diligence harness

`scripts/experience_diligence.py` (slice 1, ADR-182) is the fitting harness. It
loads from the cache, fits the tensor MI surface, and writes a findings report as
JSON plus Markdown. It reads and writes nothing inside the repo tree, emits no
plots, and carries no timestamp — so re-running over the same cache reproduces the
same bytes.

```bash
# HMD population — the primary fixture.
uv run python scripts/experience_diligence.py --source hmd \
    --country USA --min-year 1990 --max-year 2019 \
    -o ~/hmd_usa.json --markdown ~/hmd_usa.md

# Second population, for the cross-population claim.
uv run python scripts/experience_diligence.py --source hmd \
    --country GBRTENW --min-year 1990 --max-year 2019 \
    -o ~/hmd_gbrtenw.json --markdown ~/hmd_gbrtenw.md

# SOA-ILEC insured experience. Picks up SOA's own expected deaths automatically
# and adds the A/E-by-year and fitted-vs-SOA sections.
uv run python scripts/experience_diligence.py --source ilec \
    -o ~/ilec.json --markdown ~/ilec.md
```

Three things worth knowing before you read the output:

- **`--max-year 2019` on HMD is not a detail.** A smooth tensor surface fitted
  through the COVID shock attributes it to improvement. Pull 2020+ as a separate
  window if you want it. Leave the window open and the report says so in its
  caveats, but it still fits.
- **The verdict can disappoint, and that is the point.** The harness prints
  `slowdown`, `acceleration` or `mixed` for the early-vs-late comparison. A run
  that reports *no* slowdown is a **successful** run — PLAN §2 named the slowdown
  in advance precisely so the fit could fail to reproduce it. Nothing gets tuned
  until it agrees.
- **The ILEC run takes a while.** The 12 GB read streams; the fit itself is
  seconds. If the `ilec/` directory holds more than one file the harness refuses
  to guess — pass `--ilec-file "ILEC_2012_19 - 20240429.txt"`.

Exit status: 0 on a completed run whatever its verdict, **2** if the cache is
missing or ambiguous (with a sentence naming every location it looked in), 1 on
anything else.

## 4. What to send back

The data stays on your machine. What comes back into the repo is **findings**,
the same pattern that worked for the parallel measurement on 2026-08-03 — I wrote
the harness, you ran it, the numbers got committed and the raw data did not:

- The `load_hmd` / `load_ilec` verification output from §1d and §2c (shapes, year
  ranges, totals).
- For ILEC, the header diff from §2b if anything is missing.
- **The `--markdown` report from §3**, whole. It is already scrubbed of anything
  that should not be committed: file **basenames** only, no absolute paths, no
  cells, no plots. Paste it and it becomes
  `docs/MEASUREMENT_experience_gam_hmd.md` / `..._ilec.md` more or less as-is.
- The JSON too if you like — it carries the same content in a diffable form.

## Why you and not the routine

Two independent reasons, and both are structural rather than fixable:

1. **Credentials.** HMD needs your account; ILEC needs you to accept SOA terms.
   An autonomous session has neither and should not have either.
2. **Ephemeral containers.** Remote sessions clone the repo fresh and are
   reclaimed afterwards. Even if a session could download the data, it could not
   keep it, and committing it is ruled out by Design Anchor 6 regardless of what
   the licences permit.

So the division of labour is fixed: autonomous sessions build the loaders, the
fitting harness and the report generator, and exercise them on synthetic
fixtures. You run them against the real cache. The findings come back as commits.
Any epic plan that assumes otherwise is planning something that cannot happen.
