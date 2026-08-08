# Data provenance, attribution and licensing

**Covers:** the two external experience datasets this repository has been run
against — the **Human Mortality Database (HMD)** and the **SOA Individual Life
Experience Committee (ILEC)** 2012–2019 release — and the findings committed
under `docs/measurements/`.

**Status, 2026-08-07:**

| | |
|---|---|
| Attribution | **Added** (§2), pinned by `tests/test_docs/test_data_attribution.py` |
| Inventory of what is committed | **Verified by inspection** (§1) |
| **SOA** Terms of Use | **Read** (§3) — and they are **restrictive**. Permission not yet sought; request drafted at §6 |
| **HMD** User Agreement | **NOT read** (§4) — open, and the SOA answers do not transfer |
| Position taken | §5 — the maintainer's, dated, with the triggers that would change it |

**The short version.** The SOA Terms contain no dataset-specific licence, permit
use only for "personal or other non-commercial, educational purposes", prohibit
public **or** commercial reproduction and distribution, bar derivative works, and
provide **no attribution formula** — the mechanism they offer instead is prior
written permission. That is a materially worse answer than this repository
previously assumed, and §3e records what it assumed. HMD remains unread.

Nothing here is legal advice, and nobody involved is a lawyer. It is a faithful
record of clause text, of what is actually published, and of a decision taken
knowingly by the one person who gets to take it.

---

## 1. What is actually committed — the verified inventory

This is not a summary; it is the result of reading every committed report. There
are four, all under `docs/measurements/`, all generated verbatim by
`scripts/experience_diligence.py`.

### 1a. Derived from the licensed data (real figures, not model output)

**Both HMD reports** (`experience_gam_hmd_usa`, `experience_gam_hmd_gbrtenw`) carry
**totals only**:

| Field | USA | GBRTENW |
|---|---:|---:|
| cells loaded / grouped / fitted | 4,260 | 4,260 |
| total exposure (person-years) | 5,750,237,304 | 1,117,115,546 |
| total deaths | 68,998,510 | 15,153,718 |
| base strata (`attained_age, sex`) | 142, none dropped | 142 |

No rate is published per stratum — the `base` block records *counts and
diagnostics* about the empirical base, never the base rates themselves. There is
no age–year table of deaths or exposures anywhere in these files.

**Both ILEC reports** carry the same class of totals (exposure 420,365,573
policy-years, 4,354,590 deaths, 11,059,501 cells loaded → 126,223 grouped) **plus
three aggregate tables that are genuinely data-derived**:

- `ae_by_year.rows` — **8 rows**, one per calendar year, each carrying *absolute*
  actual and expected death counts (e.g. 2012: actual 518,386, expected
  474,583.8, expected-with-MI 482,055.8) and the two ratios.
- `standardised_ae.rows` — **8 rows**, ratios and mix effects only, no counts.
- `soa_surface_comparison.rows` — **35 rows**; the `soa_mi` column is SOA's *own*
  implied improvement rate at each (age, year), recovered from SOA's published
  `ExpDth_VBT2015_Cnt` / `..._MI` columns. This is a derived reading of an SOA
  quantity, not of ours.

### 1b. Model output (ours, not theirs)

`improvement_surface` (145 rows on HMD, 35 on ILEC), `window_comparison` (5 rows),
the standardisation slopes, and the fit diagnostics (dispersion φ, degrees of
freedom, band inflation).

### 1c. Not present, in any report

Cell-level rows. Policy-level anything. Rates by stratum. Contributor identities.
Filesystem paths — the `inputs` block carries **basenames and byte sizes only**
(`ILEC_2012_19 - 20240429.txt`, 12,477,136,749 bytes), which is asserted by
`tests/test_notebooks/test_experience_gam_diligence_notebook.py`.

### 1d. The line that has never been crossed

The **grouped cell table** — 126,223 rows keyed by
`(attained_age, calendar_year, sex, smoker, uw_class, duration_months)` with
exposure and deaths — has never been committed and must not be. It is not a
finding; it is the dataset at a coarser grain, and it would let someone reproduce
most of this work without obtaining the original. **Row count is not the test;
substitutability is.**

---

## 2. Attribution

These are the canonical blocks. `docs/measurements/README.md` and both
`docs/MEASUREMENT_experience_gam_*.md` carry them; a guard test fails if they are
dropped.

### 2a. Human Mortality Database

> **HMD.** Human Mortality Database. Max Planck Institute for Demographic Research
> (Germany), University of California, Berkeley (USA), and French Institute for
> Demographic Studies (France). Available at <https://www.mortality.org>.

**Series used:** `Deaths_1x1.txt` and `Exposures_1x1.txt` for **USA** and
**GBRTENW** (England & Wales, total population), calendar years 1990–2019, ages
25–95, both sexes. Downloaded by the maintainer in **August 2026** under their own
HMD account.

### 2b. SOA Individual Life Experience Committee

> **Society of Actuaries Research Institute**, Individual Life Experience Committee
> (ILEC). Individual life insurance mortality experience study covering study
> years **2012–2019**; dataset file `ILEC_2012_19 - 20240429.txt`. Available at
> <https://www.soa.org>.

**Also SOA's, and used as such:** the `ExpDth_VBT2015_Cnt` and
`ExpDth_VBT2015_MI_Cnt` columns — SOA's own expected deaths on the **2015 VBT**
basis, which are what make the A/E level check in
`MEASUREMENT_experience_gam_ilec.md` §1 an *independent* check rather than an
identity. The 2015 VBT is likewise an SOA product. Obtained by the maintainer in
**August 2026** through SOA's own download, accepting the terms presented there.

### 2c. Disclaimer

Neither the HMD nor the Society of Actuaries has reviewed, approved, endorsed or
been consulted about this analysis. Every modelling choice — the tensor basis, the
degrees of freedom, the duration banding, the overdispersion handling — is ours,
as is every error. Where a finding disagrees with a published SOA scale (see the
ILEC measurement §1b), that is a statement about **our fit**, not a correction to
SOA.

---

## 3. What the SOA Terms of Use actually say

**Read 2026-08-07** by the maintainer, from
<https://www.soa.org/legal/about-terms-cond-website/>. The clauses below are the
maintainer's quotation of that page; this session did not read it directly (§4a
explains why) and does not claim to have verified the transcription.

### 3a. There is no dataset-specific licence

The ILEC 2012–2019 report page, the data-file link and the SOA Legal Center index
carry **no separate licence for this dataset**. The site-wide Website Terms of Use
is the only governing document, and it was written for a website rather than for
a research dataset — which is why it reads more restrictively than a data licence
would.

### 3b. The clauses that govern

| | |
|---|---|
| Permission grant | material may be saved and used only for "personal or other non-commercial, educational purposes" |
| Prohibition | no reproducing, publicly displaying, distributing or otherwise using the materials "for any public or commercial purpose" |
| Derivative works | a separate bar on creating "any derivative work" |
| Reuse mechanism | **prior written permission** — "requests to use information … can be made by contacting the Society of Actuaries" (customerservice@soa.org) |
| Attribution | **no formula, no citation requirement, no credit clause anywhere** |

### 3c. What that means for this repository, stated against our own facts

**Derived aggregates are not carved out.** The Terms neither mention nor exempt
summary statistics, so there is no textual basis for the assumption that ratios
escape the restriction. §1a's ILEC tables are in scope on the plain text.

**Attribution is not the gate — permission is.** §2 gives a full scholarly
citation, which is good practice and remains correct to publish. It does not,
however, satisfy anything the Terms ask for, because the Terms ask for something
else entirely. A well-worded credit line is not a substitute for written
permission, and this document should not be read as implying otherwise.

**The binding hook is "public", not "commercial".** This is the correction most
worth carrying. The restriction is on public **or** commercial purpose, and a
public repository is public display and distribution *today* — independent of who
contributes, whether anyone is paid, or whether the work is educational in intent.
Private educational analysis of the file is squarely inside the grant; publishing
findings from it in a public repository is the part that engages the prohibition.
Any remediation framed as "if this ever becomes commercial" would therefore be
aimed at the wrong trigger.

**And `CLAUDE.md` §1 already states the commercial hook.** It describes the
project's long-term vision as "a credible open-source Python alternative to
proprietary actuarial modeling systems (AXIS, Prophet)". That sentence is public
and is in this repository now. It is not a future risk to be monitored for; it is
the disclosure that the permission request in §6 makes explicitly, so the two do
not contradict each other.

### 3d. Correcting §4c of the previous revision — the remedy was scoped to the wrong clause

The previous revision of this document argued that if the terms came back
unfavourable the fix was narrow: drop the ILEC absolute death counts, keep the
ratios, lose no finding. That reasoning was about **substitutability** — it
assumed the concern was republishing SOA's dataset in recoverable form.

The derivative-work clause is not about substitutability. If creating "any
derivative work" is barred, ratios are derivative too, and reducing the reports to
ratios **lowers exposure without eliminating it**. The remedy is still worth doing
(§5b) and is still cheap, but it was argued against the wrong clause and is
recorded here as a correction rather than quietly restated.

### 3e. What this repository asserted before any of that was read

Recorded verbatim, because the fix is not to delete it quietly.

| Where | What it said |
|---|---|
| `RUNBOOK_experience_data_acquisition.md` §0 | "it is also what keeps you inside both licences" |
| `RUNBOOK...` §1a | "HMD is open-data-principled but attribution-bearing — redistribution of the raw files is not ours to do" |
| `RUNBOOK...` §6 | "committing it is forbidden by the licences and by Design Anchor 6" |
| `docs/measurements/README.md` | a section headed "Why committing these is not a licence problem" |

Not one of them cited a licence — no section number, no quotation, no URL appeared
anywhere in the tree. On the SOA side the conventional reading has now turned out
to be **wrong in a specific way**: the assumption was that aggregate findings are
obviously fine, and the actual text neither says that nor leaves room to infer it.
That is the concrete cost of asserting a conclusion nobody had checked.

---

## 4. HMD — still unread, and still open

The research above covers **SOA only**. The HMD User Agreement at
<https://www.mortality.org/Data/UserAgreement> has not been read by anyone on this
project, and nothing in this document should be taken as a statement about it.

### 4a. Why not from here

An in-session attempt on 2026-08-07 to read `www.mortality.org` and `www.soa.org`
returned **HTTP 403 at the network gateway, before reaching either host** — this
container's egress is a GitHub/PyPI allowlist, and archive and text-extraction
mirrors are denied too. The denials are recorded in the proxy's own
`recentRelayFailures`. Search-engine summaries were available and were **not**
used: substituting one layer of paraphrase for another produces text that reads as
verified while carrying the defect §3e describes.

### 4b. The open HMD questions

The same three that were asked of SOA, and the SOA answers do **not** transfer —
the two bodies are unrelated and HMD is a research data provider rather than a
professional society publishing website material:

1. Do the terms reach derived aggregates, or only the dataset?
2. Is there a prescribed citation wording that §2a does not meet? HMD is widely
   described as requiring acknowledgement, so this one is more likely to have a
   real answer than it was for SOA.
3. Is there a non-commercial or research-only condition?

The commonly repeated claim that HMD data are released under **CC BY 4.0** is
plausible and widely echoed. It is deliberately not asserted here. If it is true,
the HMD side of this is close to resolved — CC BY permits derivative works and
commercial use and asks only for attribution — which is precisely why it should be
confirmed rather than assumed.

---

## 5. The position taken, and by whom

### 5a. The maintainer's decision, 2026-08-07

Recorded because a risk position with a name and a date on it is auditable and a
vague one is not.

> This is a single-contributor repository. The ILEC data is being used by one
> person to develop GAM mortality-improvement models for personal educational
> purposes. The maintainer has read §3, accepts the position as stated there
> — including that the "public" hook binds today — and elects to (a) seek written
> permission from the SOA per §6, and (b) carry the caveat rather than unpublish
> the findings while that request is outstanding.

This is the maintainer's call to make and it is made knowingly, not by default.
What this document does is make sure the call is on the record with the actual
clause text next to it, so nobody later mistakes it for a settled licence
position — including the maintainer.

### 5b. What would change the position

Concrete triggers, not a vibe. Any of these means revisiting before continuing:

- **A second contributor**, or any pull request accepted from outside.
- **Any revenue, sponsorship or commercial engagement** touching the repository.
- **A reply from the SOA** — in either direction. A grant narrows this document to
  its terms; a refusal triggers removal of the §1a ILEC content.
- **No reply within 90 days** of the §6 request being sent. Silence is not
  permission, and an unanswered request should not become a permanent state.

### 5c. The remediation available now

Independent of the permission request, and worth doing rather than deferring: the
`ae_by_year.rows` **absolute actual and expected death counts** are the only
committed content that could be characterised as republishing SOA figures rather
than describing them. Removing them is a re-run of
`scripts/experience_diligence.py`, not a rewrite, and every finding in
`MEASUREMENT_experience_gam_ilec.md` survives — §1's A/E level, §4's decomposition
and §5's insured-versus-population comparison are all ratios. Per §3d this reduces
exposure rather than eliminating it, and it is not a substitute for §6.

---

## 6. Permission request to the SOA

Status: **drafted 2026-08-07, to be sent by the maintainer** from their own
address, so any permission granted attaches to them personally. Record the reply
here when it arrives — including a non-reply at the 90-day mark (§5b).

Two things this draft does deliberately. It **discloses the commercial-alternative
positioning up front**, quoting CLAUDE.md §1, because a permission obtained by
soft-pedalling the highest-risk element would not cover the actual use. And it
**states what is published exactly**, including the absolute death counts, for the
same reason — the description in §1a is the one to send, not a summary of it.

> **To:** customerservice@soa.org
> **Subject:** Permission request — publication of derived values from ILEC 2012-19 in a public repository
>
> Dear Society of Actuaries,
>
> I am writing to request written permission regarding use of data from the ILEC
> 2012–2019 individual life mortality experience study, following the reuse-request
> process in the SOA Website Terms of Use. I would like to describe the intended use
> precisely and ask you to confirm what is and is not permitted.
>
> **Who I am.** I am an individual developer working alone on a personal,
> open-source actuarial modelling project. There is one contributor, no revenue and
> no commercial engagement of any kind at present.
>
> **What I have done.** I downloaded the ILEC 2012–2019 dataset
> (`ILEC_2012_19 - 20240429.txt`, approximately 12.5 GB uncompressed) under the
> terms presented at download, and used it to fit a mortality-improvement model for
> my own education. The dataset itself is held only on my own machine and is not
> distributed, published or committed to the repository in any form or at any
> resolution.
>
> **What I have published, exactly.** In a public GitHub repository I have committed
> a small number of derived values. Being precise, because I would rather you assess
> the actual content than a summary of it:
>
> - **Model output** (mine): a fitted improvement surface at five reference ages
>   (35 rows), a five-row comparison of two calendar windows, and fit diagnostics.
> - **Book-level totals** derived from the data: total exposure (420,365,573
>   policy-years) and total deaths (4,354,590), plus cell counts.
> - **Actual-to-expected by calendar year, 8 rows, including absolute counts** —
>   for example, 518,386 actual deaths against 474,584 expected in 2012. These are
>   computed against SOA's own `ExpDth_VBT2015` expected-death columns.
> - **A 35-row comparison** in which one column is SOA's own implied improvement
>   rate, recovered from those same published expected-death columns.
>
> No cell-level or policy-level data is published, and no filesystem paths or
> contributor identities appear.
>
> **The disclosure I want to make explicitly.** The repository's stated long-term
> vision, in its own documentation, is "a credible open-source Python alternative to
> proprietary actuarial modeling systems (AXIS, Prophet)". No commercial activity
> exists today, but I would rather state that positioning plainly than obtain a
> permission that does not cover what the project says it intends to become.
>
> I would be grateful for guidance on four points:
>
> 1. **Derived aggregates.** Do the Terms' restrictions extend to derived aggregate
>    values and summary statistics computed from the dataset, or only to
>    redistribution of the dataset itself?
> 2. **The absolute counts specifically.** If aggregates are generally acceptable,
>    are the absolute actual/expected death counts above treated differently from
>    ratios? I can remove them readily if that is the distinction that matters.
> 3. **Public availability.** The Terms restrict use "for any public or commercial
>    purpose". Does publishing derived values in a publicly readable repository
>    engage that restriction even where the use is non-commercial and educational?
> 4. **Attribution.** If reuse is permitted, is there attribution or citation wording
>    the SOA requires? I did not find a prescribed format in the Terms and have used
>    a standard scholarly citation.
>
> If formal written authorization is required, please let me know the process and any
> conditions. I would rather adjust or withdraw the published material than rely on
> an interpretation the SOA does not share.
>
> Thank you for your time.
>
> Best regards,
> [name]
> [contact email]

### 6a. Also worth sending — HMD

The same exercise has not been done for HMD (§4). If the HMD User Agreement turns
out to answer its three questions on its face — which is likely if the CC BY 4.0
reports are accurate — no correspondence is needed and §4 simply gets rewritten
with the clause text. Read it before assuming either way.
