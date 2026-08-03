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
`PLAN_experience_gam.md` Design Anchor 6, and it is also what keeps you inside
both licences. Everything lands in a cache directory that is outside the repo
tree by default.

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
2. Note the licence terms. HMD is open-data-principled but attribution-bearing —
   redistribution of the raw files is not ours to do, which is why only *findings*
   get committed.

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
   as such.
3. Unzip somewhere under the cache:

```bash
mkdir -p "$POLARIS_EXPERIENCE_CACHE_DIR/ilec"
# unzip the SOA release into that directory
```

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
takes a per-vintage map. Send me the diff and I'll write the override map.

### 2c. Verify it parses

```bash
uv run python -c "
from polaris_re.analytics.experience_loaders import load_ilec
cells = load_ilec('PATH/TO/ilec.csv')
print(cells.shape); print(cells.head())
"
```

---

## 3. What to send back

The data stays on your machine. What comes back into the repo is **findings**,
the same pattern that worked for the parallel measurement earlier today — I wrote
the harness, you ran it, the numbers got committed and the raw JSON did not:

- The `load_hmd` / `load_ilec` verification output from §1d and §2c (shapes, year
  ranges, totals).
- For ILEC, the header diff from §2b if anything is missing.
- Later, once the fitting harness exists: the fitted surface's summary
  statistics, the comparison against the published reference, and the verdict —
  not the cells.

## Why you and not the routine

Two independent reasons, and both are structural rather than fixable:

1. **Credentials.** HMD needs your account; ILEC needs you to accept SOA terms.
   An autonomous session has neither and should not have either.
2. **Ephemeral containers.** Remote sessions clone the repo fresh and are
   reclaimed afterwards. Even if a session could download the data, it could not
   keep it, and committing it is forbidden by the licences and by Design Anchor 6.

So the division of labour is fixed: autonomous sessions build the loaders, the
fitting harness and the report generator, and exercise them on synthetic
fixtures. You run them against the real cache. The findings come back as commits.
Any epic plan that assumes otherwise is planning something that cannot happen.
