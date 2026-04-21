# Architecture Decision Records — Polaris RE

This document records significant architecture and design decisions. Each entry explains the context, options considered, and rationale for the choice made. Claude Code must update this file after completing each milestone with any new decisions made.

---

## ADR-001: Pydantic v2 as the primary data validation layer

**Date:** Project inception  
**Status:** Accepted

**Context:** Policy data, assumption sets, and cash flow results all require structured validation. Options: dataclasses, attrs, Pydantic v1, Pydantic v2.

**Decision:** Pydantic v2 throughout.

**Rationale:** Pydantic v2 (Rust-based core) is significantly faster than v1. The `model_validator` / `field_validator` API is more explicit. JSON serialization is built-in. `model_config = ConfigDict(frozen=True)` enforces immutability on assumption objects — critical for ensuring assumption sets cannot be mutated mid-projection.

---

## ADR-002: Polars over pandas as the primary DataFrame library

**Date:** Project inception  
**Status:** Accepted

**Context:** Inforce block data manipulations require a DataFrame abstraction. Options: pandas, Polars, cuDF.

**Decision:** Polars by default; pandas only for interoperability (e.g. matplotlib, legacy format reading).

**Rationale:** Polars is 5–10× faster than pandas on typical actuarial workloads. Lazy evaluation API suits large inforce blocks. Stricter type system catches errors earlier. Pandas conversion utilities provided in `utils/` for interop.

---

## ADR-003: NumPy arrays (not DataFrames) as the projection compute layer

**Date:** Project inception  
**Status:** Accepted

**Context:** The projection engine needs vectorized calculations across N policies × T time steps.

**Decision:** Raw NumPy 2.0+ arrays with shape `(N, T)` for all projection intermediates.

**Rationale:** NumPy is the lowest-overhead option with the most predictable memory layout. xarray adds labeling but also overhead. PyTorch tensors would enable GPU (Phase 3 option) but add a heavy dependency now. The `(N, T)` layout allows efficient column-wise (time-step) and row-wise (policy) operations equally.

---

## ADR-004: Monthly time step for projections

**Date:** Project inception  
**Status:** Accepted

**Context:** Life insurance cash flows can be modeled at annual, quarterly, or monthly granularity.

**Decision:** Monthly time step throughout.

**Rationale:** Monthly is the industry standard for individual life reinsurance. It captures seasonal mortality and mid-year anniversary effects that annual models miss. The 12× cost is negligible given vectorization. Annual summaries are trivially produced by summing 12-month windows.

---

## ADR-005: Net premium reserves for Phase 1

**Date:** Project inception  
**Status:** Accepted; IFRS 17 BBA in Phase 3

**Context:** Multiple reserve bases exist: net premium (NP), gross premium (GP), IFRS 17 BBA/PAA, US GAAP LDTI.

**Decision:** Net premium reserves for Phase 1.

**Rationale:** NP reserves are the simplest auditable basis — fully deterministic from mortality table and valuation interest rate. The reserve recursion is clean and hand-verifiable. IFRS 17 added in Phase 3. `BaseProduct.compute_reserves()` is designed to be overridden for different bases without changing projection logic.

---

## ADR-006: CSV-based mortality table storage

**Date:** Project inception  
**Status:** Accepted

**Context:** Mortality tables could be stored in SQLite, binary formats (parquet, HDF5), or CSV.

**Decision:** CSV with a standardized column schema.

**Rationale:** CSV is auditable — an actuary can open it in Excel and verify values directly. No binary dependencies. Tables change rarely (new industry studies every 5–10 years). CSV load cost is amortized by caching in `MortalityTable`. A parquet loader can be added as an alternative without changing the API.

---

## ADR-007: Separation of product logic from treaty logic

**Date:** Project inception  
**Status:** Accepted

**Context:** Should treaty calculations be embedded in product code, or applied as a post-processing step?

**Decision:** Treaties are transformations applied to `CashFlowResult` objects. Product code is treaty-unaware.

**Rationale:** Enables modeling the same inforce block under multiple treaty structures without re-running the projection. Enables stacking treaties. Makes each component independently testable. Treaties receive the full `CashFlowResult` including reserves, so NAR and reserve transfer calculations have everything they need.

---

## ADR-008: Python 3.12+ as the minimum version

**Date:** Project inception  
**Status:** Accepted

**Context:** Python 3.10/3.11 are still common. Options were to support 3.10+ or require 3.12+.

**Decision:** Python 3.12+ minimum. Tested against 3.12 and 3.13 in CI.

**Rationale:** Python 3.12 eliminates the need for `from __future__ import annotations` (PEP 563 deferred evaluation is native). It enables `X | Y` union syntax, `list[X]` / `dict[K, V]` built-in generics, `type` statement for type aliases, and `Self` from `typing`. These reduce boilerplate and improve readability throughout the codebase. The `UP` ruleset in Ruff enforces 3.12+ style automatically.

---

## ADR-009: uv as the package manager (replacing pip/venv/poetry)

**Date:** Project inception  
**Status:** Accepted

**Context:** Options were pip+venv, Poetry, PDM, or uv.

**Decision:** uv throughout. `uv sync` to install, `uv run <cmd>` to execute. `uv.lock` committed for reproducible installs.

**Rationale:** uv is 10–100× faster than pip for resolution and installation. It handles both virtualenv creation and lockfile management in a single tool. It is fully `pyproject.toml` native (no secondary config files). `uv.lock` committed to VCS enables `--frozen` installs in CI, guaranteeing every run uses identical dependency versions. The `.python-version` file (pinned to `3.12`) is read automatically by uv.

---

## ADR-010: uv.lock committed to VCS for reproducible CI

**Date:** Initial CI setup  
**Status:** Accepted

**Context:** `uv.lock` was initially excluded from `.gitignore` (treating Polaris RE as a library). The first CI run failed because `setup-uv@v4` could not find `uv.lock` for cache-dependency-glob.

**Decision:** Commit `uv.lock`. Use `uv sync --frozen` in CI. Cache keyed on `pyproject.toml`.

**Rationale:** Although libraries conventionally omit lock files, the `--frozen` flag in CI provides a meaningful reproducibility guarantee that offsets the maintenance cost. The lock file is updated intentionally via `uv lock` when dependencies change, making dependency updates an explicit, reviewable commit. The `setup-uv@v4` cache is keyed on `pyproject.toml` (always present) rather than `uv.lock` to avoid a chicken-and-egg failure on first run.

---

## ADR-011: Synthetic CSV fixtures for mortality table testing

**Date:** Milestone 1.2
**Status:** Accepted

**Context:** Production mortality tables (SOA VBT 2015, CIA 2014) are copyrighted or require licensing agreements. Testing the CSV loader and vectorized lookups needs data.

**Decision:** Create synthetic CSV mortality table fixtures in `tests/fixtures/` with realistic but fabricated rates. Two fixtures: a select-and-ultimate table (3-year select period, ages 18-60) and an ultimate-only table (same age range).

**Rationale:** Synthetic data eliminates licensing concerns while allowing comprehensive testing of the full load-validate-lookup pipeline. Known values in the fixture enable closed-form verification tests. The fixture structure exactly mirrors the production CSV schema, so any loader that passes fixture tests will work with real tables.

---

## ADR-012: MortalityTable stores table arrays as a Pydantic field

**Date:** Milestone 1.2
**Status:** Accepted

**Context:** `MortalityTable` needs to hold `MortalityTableArray` objects (numpy arrays) but inherits from `PolarisBaseModel` which is frozen and forbids extra fields. Options: (1) store arrays outside the model in a module-level cache, (2) add a `tables` field with `arbitrary_types_allowed=True`, (3) don't use Pydantic for this class.

**Decision:** Override `model_config` in `MortalityTable` to add `arbitrary_types_allowed=True` and store table arrays in a `tables: dict[str, MortalityTableArray]` field (excluded from serialization). A `from_table_array()` factory method enables easy construction for testing.

**Rationale:** Keeping `MortalityTable` as a Pydantic model preserves the project's "Pydantic-first" principle and allows it to participate in `AssumptionSet` validation. The `arbitrary_types_allowed` override is scoped only to this class. The `exclude=True` on the field prevents serialization issues with numpy arrays.

---

## ADR-013: Vectorized lapse lookup using numpy advanced indexing

**Date:** Milestone 1.2
**Status:** Accepted

**Context:** `LapseAssumption.get_lapse_vector()` needs to map duration months to annual lapse rates (select or ultimate) for N policies. Options: (1) Python loop over policies, (2) numpy advanced indexing.

**Decision:** Build a lookup array `[select_rate_1, ..., select_rate_N, ultimate_rate]` and use `np.minimum(policy_years - 1, select_period)` as indices for vectorized lookup.

**Rationale:** Fully vectorized with no Python loops. The lookup array is tiny (typically 10-20 elements) so construction cost is negligible. `np.minimum` provides the select/ultimate boundary capping in a single operation.

---

## ADR-014: Scale AA improvement factors embedded as constants

**Date:** Milestone 1.2
**Status:** Accepted

**Context:** SOA Scale AA is a simple age-only improvement scale (constant over calendar years). Options: (1) load from CSV like mortality tables, (2) embed as a numpy array constant.

**Decision:** Embed Scale AA factors as a module-level `_SCALE_AA_FACTORS` numpy array in `improvement.py`. Representative rates by age band (0-120).

**Rationale:** Scale AA is small (121 floats), publicly known, and never changes. Embedding avoids file I/O dependencies and makes the module self-contained. MP-2020 and CPM-B (Phase 2) are 2D tables that will need CSV loading, but Scale AA is simple enough to hardcode.

---

## ADR-015: YRT treaty uses total_face_amount parameter for aggregate NAR

**Date:** Milestone 1.4
**Status:** Accepted

**Context:** YRT premiums are based on Net Amount at Risk (NAR = face - reserves). However, `CashFlowResult` carries aggregate cash flows without per-policy face amounts. Options: (1) require seriatim output from the product engine, (2) add a `total_face_amount` parameter to the treaty, (3) back-calculate face from premium/claim ratios.

**Decision:** Add a `total_face_amount` field to `YRTTreaty`. Approximate in-force face at each time step using the premium runoff ratio: `total_face_t = total_face_amount * (premium_t / premium_0)`.

**Rationale:** This keeps the treaty interface clean — it receives a `CashFlowResult` and doesn't need to know about `InforceBlock`. The premium runoff proxy is actuarially reasonable for level-premium term products where premiums decrease proportionally with in-force count. A full seriatim NAR calculation can be added in Phase 2 when seriatim treaty application is supported.

---

## ADR-016: Coinsurance treaty splits all cash flow lines uniformly

**Date:** Milestone 1.4
**Status:** Accepted

**Context:** Coinsurance transfers a proportional share of all cash flows including reserves. The `include_expense_allowance` flag controls whether expenses are also split.

**Decision:** All cash flow lines (premiums, claims, lapses, reserves, reserve increases) are multiplied by `cession_pct` for ceded and `(1 - cession_pct)` for net. Expenses follow the same split when `include_expense_allowance=True`, otherwise stay fully with the cedant.

**Rationale:** Uniform proportional scaling guarantees the `net + ceded == gross` additivity invariant by construction. The `include_expense_allowance` flag provides flexibility for treaties where the reinsurer does not share in acquisition costs.

---

## ADR-017: IRR via scipy.optimize.brentq root-finding

**Date:** Milestone 1.5
**Status:** Accepted

**Context:** IRR computation requires finding the discount rate at which NPV = 0. Options: (1) numpy_financial.irr (based on polynomial root-finding), (2) scipy.optimize.brentq (bracket-based root-finding), (3) scipy.optimize.newton (derivative-based).

**Decision:** Use `scipy.optimize.brentq` with bracket `[-0.50, 10.0]`, returning `None` when no sign change exists.

**Rationale:** Brentq is guaranteed to converge when a sign change exists in the bracket, unlike Newton's method which can diverge. The bracket [-50%, 1000%] covers all reasonable reinsurance deal IRRs. When all profits have the same sign (e.g., all positive with no initial outflow), brentq correctly raises ValueError which we catch and return None. numpy_financial's irr uses polynomial companion matrix eigenvalues which can produce spurious complex roots.

---

## ADR-018: ScenarioRunner creates scaled AssumptionSets via deep copy

**Date:** Milestone 1.5
**Status:** Accepted

**Context:** AssumptionSet is frozen (immutable Pydantic model). Scenarios need to apply multiplicative adjustments (e.g., mortality * 1.10). Options: (1) create a proxy/wrapper that scales on-the-fly, (2) create new objects with scaled rate arrays.

**Decision:** Create new `MortalityTableArray` objects with `rates * multiplier` (clipped to [0,1]) and new `LapseAssumption` objects with scaled select/ultimate rates. Construct a new `AssumptionSet` with version string appended with scenario name.

**Rationale:** Creating new objects respects the frozen/immutable constraint and produces independent assumption sets that can be inspected and audited. The version string (e.g., "v1_MORT_110") provides full traceability. The memory overhead of duplicated rate arrays is negligible for typical table sizes (~5K floats per table).

---

## ADR-019: Whole Life terminal reserve uses one-period prospective estimate

**Date:** Phase 2
**Status:** Accepted

**Context:** Unlike term life (V_T = 0 at policy expiry), a whole life projection truncated at a finite horizon T has a non-zero terminal reserve. The "correct" prospective reserve requires projecting to infinity. Options: (1) force V_T = 0 (incorrect — overstates profits), (2) use face amount as terminal reserve (conservative), (3) use one-period prospective estimate V_T = face * q_T * v.

**Decision:** V_T = face_amount * q_last * v where v = 1/(1 + i/12). The backward recursion then proceeds from this starting point.

**Rationale:** The one-period prospective estimate is conservative and actuarially grounded. It understates the terminal reserve slightly compared to the true prospective value, which biases profits conservatively. Phase 3 will add true prospective reserves from extended projections, but this is an acceptable Phase 2 approximation.

---

## ADR-020: Universal Life forced lapse when account value reaches zero

**Date:** Phase 2
**Status:** Accepted

**Context:** A UL policy lapses if the account value becomes insufficient to pay COI charges and the policyholder does not increase premium. The model must handle this gracefully.

**Decision:** At each time step, if the projected new AV ≤ 0 and current AV > 0, the policy is treated as forcibly lapsed. Forced lapse is combined with voluntary lapse rate via `w_total = min(w_voluntary + forced_lapse_indicator, 1.0)`.

**Rationale:** Forced lapse is economically correct — a policyholder cannot maintain insurance with a negative account value. The indicator pattern (0 or 1 per policy) integrates cleanly into the existing vectorized lapse framework. This handles adverse scenarios (high COI + low premium + credited rate crash) robustly.

---

## ADR-021: Modco cedant retains full reserves; reinsurer pays modco interest

**Date:** Phase 2
**Status:** Accepted

**Context:** Modified coinsurance differs from coinsurance in that the cedant retains the assets backing ceded reserves. The reinsurer's NCF must account for this retention.

**Decision:** In `ModcoTreaty.apply()`: (1) premiums and claims split proportionally by `cession_pct`, (2) NO reserve transfer (cedant retains 100%), (3) reinsurer pays `modco_interest = ceded_reserve * modco_interest_rate / 12` each month as a negative item in ceded NCF and positive item in net NCF.

**Rationale:** The NCF additivity property holds algebraically: modco_interest appears with opposite signs in net and ceded NCF, cancelling to zero in (net + ceded). Cedant retains full reserve_increase in net_cash_flow, so the reserve line in the aggregate is unchanged. This is the standard actuarial definition of modco.

---

## ADR-022: Stop Loss uses pro-rated attachment/exhaustion for partial final year

**Date:** Phase 2
**Status:** Accepted

**Context:** Projections may end mid-year (e.g., 241 months = 20 years + 1 month). The final year has fewer than 12 months. If attachment/exhaustion are defined as annual amounts, the partial year must be treated consistently.

**Decision:** For the partial final year with `n_months < 12`: `year_fraction = n_months / 12`. Effective attachment = `attachment_point * year_fraction`. Effective exhaustion = `exhaustion_point * year_fraction`. The stop loss premium for the partial year is also pro-rated by `year_fraction`.

**Rationale:** Pro-rating is industry-standard for aggregate covers with mid-year inception or expiry. It correctly maintains the economic equivalence between annual and sub-annual periods. The alternative (treating a partial year at full attachment) would overstate the cedant's retention in the final year.

---

## ADR-023: MP-2020 improvement factors embedded as 2D array (age × year)

**Date:** Phase 2
**Status:** Accepted

**Context:** SOA MP-2020 is a 2D improvement scale indexed by age (0–120) and calendar year (2015–2031). Options: (1) load from CSV, (2) embed as module-level constant, (3) use a simplified 1D approximation.

**Decision:** Embed as a module-level `_MP2020_FACTORS` numpy array with shape (121, 17) — ages 0–120 × years 2015–2031. After 2031, rates are held constant at the 2031 values.

**Rationale:** MP-2020 is a published SOA table with fixed values that will not change. Embedding eliminates file I/O at startup and makes the module self-contained. The (121, 17) array is ~15KB — negligible memory. The post-2031 constant extrapolation is the SOA's own recommendation for long-horizon projections.

---

## ADR-024: CPM-B factors embedded as 1D age-only array

**Date:** Phase 2
**Status:** Accepted

**Context:** CIA CPM-B is a Canadian improvement scale indexed by age only (no calendar year dimension). This differs from SOA MP-2020.

**Decision:** Embed as module-level `_CPM_B_FACTORS` numpy array with shape (121,) and apply via `improved_q = base_q * (1 - factor)^years`.

**Rationale:** CPM-B's simpler age-only structure matches CIA's Canadian Life Table calibration. The power formula `(1 - factor)^n` accumulates improvement correctly over n projection years, consistent with the CIA's published methodology.

---

## ADR-025: Morbidity tables use synthetic constructors for testing

**Date:** Phase 2
**Status:** Accepted

**Context:** Real CI and DI morbidity tables are proprietary industry studies. Tests require known values to verify projection logic.

**Decision:** `MorbidityTable` provides two factory classmethods: `synthetic_ci()` and `synthetic_di()` that return tables with realistic but fabricated incidence and termination rates, following the same pattern as the `MortalityTable` approach using synthetic CSV fixtures.

**Rationale:** Synthetic constructors allow comprehensive testing of the DI multi-state model (active↔disabled transitions) and CI single-decrement model without requiring proprietary data. The rates are designed to increase with age in a realistic pattern, making tests actuarially meaningful while remaining audit-friendly.

---

## ADR-026: Monte Carlo UQ uses lognormal multipliers and normal rate shifts

**Date:** Phase 2
**Status:** Accepted

**Context:** Distributional assumptions for assumption uncertainty require a choice of distribution. Options: (1) normal multipliers (can be negative), (2) lognormal multipliers (always positive), (3) uniform on a range.

**Decision:** Mortality and lapse multipliers drawn from `LogNormal(mu=0, sigma)` so they are strictly positive with E[multiplier] ≈ exp(sigma²/2) ≈ 1. Interest rate shifts drawn from `Normal(0, sigma)` as additive shifts to the annual discount rate (floored at 0%).

**Rationale:** Lognormal multipliers cannot produce negative rates (which would be unphysical) and their mean is approximately 1 for small sigma, preserving the base scenario. The normal additive shift for interest rates is standard in actuarial sensitivity analysis. All sampling uses `np.random.default_rng(seed)` for reproducibility.

---

## ADR-027: IFRS 17 BEL computed via backward recursion (prospective method)

**Date:** Phase 3 (Milestone 3.1)
**Status:** Accepted

**Context:** BEL = PV of future fulfilment cash flows. Options: (1) forward simulation then PV sum, (2) backward recursion.

**Decision:** Backward recursion: `BEL[T-1] = FCF[T-1] * v`; `BEL[t] = FCF[t] * v + BEL[t+1] * v`.

**Rationale:** The backward recursion is numerically equivalent to the prospective formula `BEL[t] = sum_{s>=t} FCF[s] * v^(s-t+1)` but computes in O(T) instead of O(T^2). It naturally handles the prospective view at every time step, making it easy to produce a full BEL schedule rather than just the initial recognition value.

---

## ADR-028: IFRS 17 CSM stores opening-period balances; end-of-period in csm_schedule

**Date:** Phase 3 (Milestone 3.1)
**Status:** Accepted

**Context:** The CSM roll-forward produces both opening and end-of-period balances. The `IFRS17Result.csm` field must carry one of these.

**Decision:** `IFRS17Result.csm[t]` = CSM at the START of period t (opening balance, before accretion and release). `_compute_csm_schedule()` returns `csm_schedule[t]` = end-of-period balance (after release), which is the opening of period t+1.

**Rationale:** Opening balances are what appear on the IFRS 17 balance sheet at each period start. The accretion and release in period t are then derived from the opening balance, matching the IASB presentation requirements. Tests verify total CSM released equals initial CSM plus cumulative accretion (not that closing CSM reaches zero — it is zero only at contract expiry, which is csm_schedule[-1]).

---

## ADR-029: Hull-White and CIR both discretised via Euler-Maruyama on monthly steps

**Date:** Phase 3 (Milestone 3.2)
**Status:** Accepted

**Context:** Stochastic SDE discretisation options include Euler-Maruyama (first-order), Milstein (adds diffusion correction), and exact simulation (for affine models like CIR).

**Decision:** Euler-Maruyama for both models with `dt = 1/12` (monthly). CIR applies a positivity floor `max(r_prev, 0)` in the diffusion term to prevent negative rates in the discrete approximation.

**Rationale:** Euler-Maruyama is straightforward to implement, easy to audit, and sufficiently accurate for monthly steps with typical parameter values. The exact CIR simulation (via non-central chi-squared) adds significant complexity for marginal accuracy gains at monthly granularity. The positivity floor is the standard discrete-time fix for CIR and is equivalent to the full truncation scheme recommended by Lord et al. (2010).

---

## ADR-030: Experience study uses limited-fluctuation credibility with n_full = 1082

**Date:** Phase 3 (Milestone 3.3)
**Status:** Accepted

**Context:** Credibility weighting requires a choice of method (limited-fluctuation vs. Buhlmann) and the full-credibility threshold.

**Decision:** Limited-fluctuation credibility `Z = min(1, sqrt(n / n_full))` with `n_full = 1082` as the default (standard actuarial value for 90% probability within 5% of true mean for mortality).

**Rationale:** Limited-fluctuation (classical) credibility is the industry standard for experience studies and is required by most pricing actuaries and regulators. Buhlmann credibility requires a prior distribution estimate (`k` parameter) that is difficult to specify without extensive historical data. The 1082 threshold is derived from `(z_{0.95} / 0.05)^2 * p*(1-p) / p^2` at typical mortality rates and is published in the CAS/SOA credibility syllabus. The `n_full_credibility` parameter is configurable so users can adjust for lapse studies (where the full-credibility threshold is lower).

---

## ADR-031: FastAPI as the REST API framework with httpx for test client

**Date:** Phase 3 (Milestone 3.5)
**Status:** Accepted

**Context:** REST API framework options: Flask, FastAPI, Django REST framework. Test client options: requests-mock, httpx TestClient.

**Decision:** FastAPI with Pydantic v2 request/response models. Tests use `fastapi.testclient.TestClient` (backed by httpx).

**Rationale:** FastAPI is the natural choice given the project already uses Pydantic v2 — FastAPI's request validation and response serialization are built on Pydantic natively. The OpenAPI schema is auto-generated for free. `TestClient` from FastAPI's testclient module provides synchronous test execution without needing a running server, making tests fast and self-contained. FastAPI and httpx added as optional `[api]` dependencies so they don't inflate the base install.

---

## ADR-032: Streamlit dashboard excluded from coverage and as an optional dependency

**Date:** Phase 3 (Milestone 3.6)
**Status:** Accepted

**Context:** The Streamlit dashboard requires a running browser session to test meaningfully. Unit testing Streamlit apps requires mocking the entire rendering pipeline, which provides low value.

**Decision:** `dashboard/app.py` is excluded from pytest coverage via `omit = ["*/dashboard/app.py"]` in `pyproject.toml`. Streamlit added as an optional dependency under `[project.optional-dependencies] dashboard`.

**Rationale:** Excluding dashboard from coverage prevents the 94%+ coverage on the core analytical modules from being diluted by untestable UI rendering code. The dashboard is a thin presentation layer over already-tested business logic — its correctness is best verified by visual inspection in a running Streamlit session. Users who don't need the dashboard install with `uv sync` (no Streamlit); users who do install with `uv sync --extra dashboard`.

---

## ADR-033: Lapse CSV schema uses 1D policy_year,rate format

**Date:** Phase 4 (Milestone 4.1)
**Status:** Accepted

**Context:** Mortality tables are 2D (age × select duration). Lapse tables could follow the same 2D layout, or use a simpler 1D layout since lapse rates are fundamentally driven by policy year (duration since issue), not by attained age.

**Decision:** Lapse CSV schema is `policy_year,rate` — one row per policy year. The last row is treated as the ultimate rate. No age or sex/smoker dimensions in the base CSV; if sex/smoker-distinct rates are needed, separate CSV files are used (matching the mortality pattern of one file per sex/smoker combination).

**Rationale:** Real-world lapse experience studies produce rates by policy year, not by attained age. A simpler schema reduces friction for data ingestion from cedant lapse studies. The `LapseTableArray` wrapper mirrors the `MortalityTableArray` API (`get_rate()`, `get_rate_vector()`) for consistency, while using a 1D array internally. `LapseAssumption.load()` mirrors `MortalityTable.load()` for API symmetry. The convention that the last CSV row is the ultimate rate avoids needing a separate "ultimate" column for a 1D table.

---

## ADR-034: ML assumption protocol — same get_*_vector() interface as table assumptions

**Date:** Phase 4 (Milestone 4.3)
**Status:** Accepted

**Context:** ML-enhanced mortality and lapse assumptions need to integrate with the existing projection engine without code changes to `AssumptionSet`, product engines, or treaty code. Two approaches: (1) a formal Python Protocol class that both table and ML assumptions satisfy, or (2) duck typing where ML classes implement the same method signatures.

---

## ADR-036: Treaty-default with policy-level cession override

**Date:** Phase 4 (user testing)
**Status:** Accepted

**Context:** The `Policy.reinsurance_cession_pct` field existed but was never consumed by any treaty's `apply()` method. All four treaty implementations (`YRTTreaty`, `CoinsuranceTreaty`, `ModcoTreaty`, `StopLossTreaty`) used only the treaty-level `cession_pct` parameter. This meant changing the policy-level cession had zero effect on output — a silent, confusing bug discovered during user testing.

In practice, reinsurance treaties can have both a blanket cession percentage (simple deals) and per-policy cession overrides (excess-of-retention structures, facultative arrangements, or treaties where cession depends on face amount).

Options considered:
1. Remove `Policy.reinsurance_cession_pct` entirely — simplest, but loses the per-policy capability.
2. Make treaty read only from policy — breaks backward compatibility, forces all users to set per-policy values.
3. Treaty-default with policy-level override — treaty `cession_pct` is the default; policy values override when set.

**Decision:** Option 3. The design is:
- `Policy.reinsurance_cession_pct` changed from required `float` to `float | None = None`.
- `None` means "use the treaty-level default" — backward compatible.
- An explicit value (e.g., `0.70`) overrides the treaty default for that policy.
- `InforceBlock.effective_cession_vec(treaty_default)` resolves per-policy rates.
- `InforceBlock.face_weighted_cession(treaty_default)` computes the face-weighted average for aggregate cash flow splitting.
- `BaseTreaty.apply()` accepts an optional `inforce: InforceBlock | None` parameter. When provided, `_resolve_cession()` computes the face-weighted blend. When omitted, the treaty's `cession_pct` is used directly.
- `StopLossTreaty` accepts the `inforce` parameter for interface consistency but does not use it (stop loss is not a proportional treaty).

**Rationale:** This design provides full backward compatibility (existing callers pass no `inforce=` and get unchanged behaviour), supports the simple case (blanket treaty cession), and enables the complex case (per-policy overrides with face-weighted blending) through a single optional parameter. The face-weighted average is the actuarially correct aggregation method because it preserves the economic equivalence between seriatim and aggregate treaty application.

---

**Decision:** Duck typing. `MLMortalityAssumption.get_qx_vector()` matches the signature of `MortalityTable.get_qx_vector()`. `MLLapseAssumption.get_lapse_vector()` matches `LapseAssumption.get_lapse_vector()`. No formal Protocol class is introduced — the `AssumptionSet.mortality` field accepts either `MortalityTable` or `MLMortalityAssumption` since both satisfy Pydantic's `PolarisBaseModel` contract. ML assumptions clip predictions to [0, 1] and convert annual to monthly rates internally.

**Rationale:** A formal Protocol adds an abstraction layer that provides minimal value given there are only two implementations per assumption type. Duck typing is simpler, avoids breaking changes to `AssumptionSet`, and follows Python conventions. The projection engines only call `get_qx_vector()` and `get_lapse_vector()` — as long as ML classes implement these with the same return shape and dtype contract, they are drop-in replacements. Model persistence uses joblib, which handles scikit-learn and XGBoost models natively.

---

## ADR-035: Feature engineering conventions — standard bands and transforms

**Date:** Phase 4 (Milestone 4.3)
**Status:** Accepted

**Context:** ML models require engineered features beyond raw policy attributes. Need to standardise feature transforms so all ML assumption models use consistent preprocessing.

**Decision:** Standard feature transforms in `utils/features.py`: 5-year age bands (`add_age_bands`), actuarial duration bands (0-1, 2-5, 6-10, 11-15, 16+ years via `add_duration_bands`), log-transformed face amount (`log_face_amount`), and a `build_feature_matrix` function that produces the canonical feature DataFrame from policy attributes. Binary encoding for sex (male=1) and smoker status (smoker=1).

**Rationale:** Consistent feature engineering ensures reproducibility across training and inference. Age bands and duration bands are standard actuarial groupings used in experience studies and pricing. Log-transform for face amount handles the heavy-tailed distribution of policy sizes. Binary encoding for categorical variables is the simplest approach and sufficient for tree-based models (GBM, XGBoost) which dominate actuarial ML use cases.

---

## ADR-037: Mortality-calibrated premium formula for synthetic blocks

**Date:** Phase 5
**Status:** Accepted

**Context:** The synthetic block generator used an illustrative linear premium
formula (`0.8 + age * 0.05` per $1,000) that was not calibrated to any mortality
table. When real tables (SOA VBT 2015, CIA 2014) were used for projection, the
block was universally onerous — claims exceeded premiums for policies with
attained ages above ~45, producing a fully loss-making IFRS 17 result with
CSM = 0.

**Decision:** Replace the illustrative formula with a mortality-table-calibrated
premium calculation:
  1. For each policy, compute the average annual q_x across the policy term
     using the ultimate column of the chosen mortality table.
  2. Derive annual premium = (face_amount x avg_annual_qx) / target_loss_ratio.
  3. Apply smoker loading by using the smoker-specific table rates (no separate
     multiplier).
  4. The target_loss_ratio parameter (default 0.60) replaces the manual premium
     input in all dashboard flows.

**Rationale:** Using average q_x over the term is a pragmatic approximation of
an actuarially fair level premium. It avoids the complexity of a full APV
calculation (which would require survival probabilities and discounting) while
being far more accurate than the previous linear formula. The target loss ratio
gives the user a single, interpretable control that directly determines
profitability — a 60% loss ratio means 40% of premium is available for
expenses, margins, and profit.

---

## ADR-038: Mortality-based YRT rate derivation as the canonical pipeline pattern

**Date:** Phase 5 (user testing / cross-module consistency fix)
**Status:** Accepted

**Context:** All three interface layers (Streamlit dashboard, REST API, CLI) were
constructing `YRTTreaty` with `flat_yrt_rate_per_1000=None`. The YRT treaty
implementation correctly treats `None` as "no rate available" and sets ceded YRT
premiums to $0. This caused ceded premium cash flows to be zero, inflating the
cedant's NET profit metrics (up to 47% error on test blocks). The bug was silent
— no exception was raised, and results looked plausible but were actuarially wrong.

**Root cause:** The YRT rate cannot be known before the gross projection runs, because
it depends on the expected mortality claims. The previous pipeline pattern constructed
the treaty before running the projection, making it impossible to derive the rate from
actual projected claims.

**Decision:** Adopt a two-stage pipeline pattern across all interfaces:
1. Build `InforceBlock`, `AssumptionSet`, and `ProjectionConfig` (no treaty).
2. Run `TermLife.project()` to obtain the GROSS `CashFlowResult`.
3. Derive the YRT rate: `rate = (first_year_claims / total_face) * 1000 * (1 + loading)`.
4. Construct `YRTTreaty(flat_yrt_rate_per_1000=rate)` with the derived rate.
5. Call `treaty.apply(gross)` → `(net, ceded)`.

The `loading` parameter (default 10%) represents the reinsurer's margin over
expected mortality — it is exposed as `yrt_loading` in API request models and
hardcoded to 0.10 in CLI demo mode, matching the dashboard default.

This pattern is implemented in:
- `dashboard/components/projection.py::derive_yrt_rate()` + `run_treaty_projection()`
- `api/main.py::_derive_yrt_rate()` + `_build_components()` (replaces `_build_pipeline()`)
- `cli.py::_derive_yrt_rate()` + all commands that use a YRT treaty

**Rationale:** The rate must be derived from the projection, not estimated before
it. Deriving from first-year claims is the simplest actuarially defensible approach
and matches standard YRT pricing practice where the cedant's mortality experience
in Year 1 sets the base rate. All interfaces must use the same pattern so that
identical inputs produce identical results regardless of access method.

---

## ADR-039: `ceded_to_reinsurer_view()` for reinsurer profit testing

**Date:** Phase 5 (user testing / dashboard redesign)
**Status:** Accepted

**Context:** `ProfitTester` explicitly rejects `CashFlowResult` objects with
`basis="CEDED"` by raising `ValueError`. This is correct by design — profit-testing
the cedant's ceded portion in isolation is actuarially meaningless. However, the
reinsurer's perspective requires exactly this: the reinsurer's inflows (YRT premiums
received from cedant) and outflows (ceded death claims paid, expense allowances) are
precisely the ceded cash flows.

**Decision:** Provide a `ceded_to_reinsurer_view()` helper in every interface layer
that creates a shallow copy of a CEDED `CashFlowResult` with `basis` relabelled to
`"NET"`. This allows `ProfitTester` to accept it and compute reinsurer profitability
metrics (PV profits, IRR, profit margin, break-even year) correctly.

The convention is:
- **Cedant view**: `ProfitTester(net, hurdle_rate).run()` where `net` is the NET
  result from `treaty.apply(gross)`.
- **Reinsurer view**: `ProfitTester(ceded_to_reinsurer_view(ceded), hurdle_rate).run()`
  where `ceded` is the CEDED result from `treaty.apply(gross)`.

This pattern is implemented as:
- `dashboard/components/projection.py::ceded_to_reinsurer_view()`
- `api/main.py::_ceded_to_reinsurer_view()` (reinsurer metrics in `PriceResponse`)
- `cli.py::_ceded_to_reinsurer_view()` (reinsurer table in `polaris price` output)

**Rationale:** The relabelling is semantically correct: from the reinsurer's
perspective, the ceded flows ARE their net position. The helper is a deliberate,
named operation — not a silent bypass — so it is auditable and understandable.
`ProfitTester`'s CEDED rejection remains intact, preserving its contract.
Both cedant and reinsurer views are now exposed in all profit-test outputs so that
deal economics are visible to both parties from a single API call or CLI run.

---

## ADR-040: Whole Life honours ProjectionConfig expense fields

**Date:** Phase 5 (product direction blocker)
**Status:** Accepted

**Context:** `WholeLife.project()` hardcoded `ser_expenses = np.zeros((n, t))` and
ignored `ProjectionConfig.acquisition_cost_per_policy` and
`ProjectionConfig.maintenance_cost_per_policy_per_year`. TERM and UL applied
expenses correctly, so WL blocks silently understated deal costs — a latent
actuarial correctness bug discovered during the 2026-04-19 commercial
readiness assessment (see `docs/PRODUCT_DIRECTION_2026-04-19.md`, BLOCKER #1).

**Decision:** WL follows the TERM expense pattern:
- `expenses[:, 0] += acquisition_cost_per_policy` — one-time issue expense per
  policy at projection start, **gated on `duration_inforce == 0`** so that only
  genuine new-business policies incur acquisition cost. Seasoned inforce policies
  (duration > 0) already paid acquisition at original issue and are excluded.
- `expenses += lx * (maintenance_cost_per_policy_per_year / 12)` — monthly admin
  cost scaled by in-force factor.
- No remaining-term mask (unlike TERM): whole life has no expiry, so maintenance
  runs for the full projection horizon weighted by lx.
- The same `duration_inforce == 0` gating applies to TERM as well, ensuring
  consistent treatment across both product engines.

**Rationale:** The fix matches the existing TERM pattern verbatim with the
single adjustment that WL has no term-expiry mask. Whole life is a permanent
product, so maintenance expenses accrue while the policy remains in-force (lx
captures mortality + lapse decrement). The `duration_inforce == 0` gate on
acquisition cost is actuarially correct: acquisition is a one-time cost at
policy issue, and seasoned inforce policies have already incurred it in a
prior accounting period. This gate was applied consistently to both TERM
and WL engines. The change is additive when the
config fields are zero (preserves backward compatibility in tests that do not
set expense loadings) and fixes a silent understatement of costs when they are
set. Golden baselines (`tests/qa/golden_outputs/golden_flat.json`,
`golden_yrt.json`) were regenerated to reflect the corrected WL cash flows —
cedant PV profits decreased by ~$6K on each WL cohort, consistent with
20 years of $75/policy/year maintenance plus $500/policy acquisition on 6
policies discounted at 6%.

---

## ADR-041: Reporting guardrails on ProfitTester (IRR and profit_margin)

**Date:** Phase 5 (product direction IMPORTANT fix)
**Status:** Accepted

**Context:** The 2026-04-19 commercial readiness assessment
(`docs/PRODUCT_DIRECTION_2026-04-19.md`) identified two metric-level results
in golden outputs that a pricing actuary would never present without caveat:

1. **Spurious large IRRs on loss-making deals.** The WL cohort under YRT
   produced a reinsurer IRR of 899.04% on a deal with PV profits of
   −$4.32M and total undiscounted profit of −$13.89M. The 899% was a
   mathematically valid brentq root of a cash-flow stream that started with
   a single small positive ($3,839 in year 1) and turned monotonically
   negative — a degenerate sign change with no economic meaning.

2. **Sign-flipped profit margins.** The FLAT TERM cohort showed
   `profit_margin = +1.40` (140%) while `pv_profits = −$35,292`. Root
   cause: the NET view's `pv_premiums` was **negative** (−$25,171) because
   ceded YRT premiums exceeded gross premiums. The ratio of two negative
   numbers flipped sign, producing a misleading "positive margin" on a
   loss-making deal.

**Decision:** Add two reporting guardrails to `ProfitTester.run()`:

1. **IRR guardrail:** After the brentq solve, if the deal has
   `total_undiscounted_profit < 0` AND `|irr| > IRR_SUPPRESS_MAGNITUDE`
   (default 0.5 = 50%), set `irr = None`. Large-magnitude IRRs are
   retained when the deal is genuinely profitable (total undiscounted
   > 0), so legitimate high-return structures are not suppressed. The
   threshold is a class constant (`ProfitTester.IRR_SUPPRESS_MAGNITUDE`)
   so it can be tuned or overridden in future experiments.

2. **Profit-margin guardrail:** If `pv_premiums <= 0`, set
   `profit_margin = None` instead of computing a sign-ambiguous ratio.
   Previously the code returned `0.0` when `pv_premiums == 0` and
   computed the sign-flipped ratio when `pv_premiums < 0`; both are
   misleading. The type of `ProfitTestResult.profit_margin` changes from
   `float` to `float | None`.

All downstream consumers were updated to handle `None`:

- `analytics/uq.py`: `profit_margins` array stores `np.nan` when the
  underlying value is `None`; `UQResult.percentile()` masks NaN before
  computing the percentile (mirroring the existing IRR handling).
- `api/main.py`: `PriceResponse.profit_margin`,
  `PriceResponse.reinsurer_profit_margin`, and
  `ScenarioSummary.profit_margin` typed `float | None`.
- `cli.py`: the Rich-rendered cedant/reinsurer/scenario tables format
  `profit_margin` as `"N/A"` when `None` (same pattern as `irr`).
- `dashboard/views/pricing.py`, `treaty_compare.py`, `scenario.py`:
  `st.metric`/table cells format `"N/A"` when `profit_margin is None`.

**Rationale:** Reinsurance deal committee packets demand numbers that are
both correct and economically interpretable. An IRR of 899% or a margin
of +140% on a loss-making deal fails the second test even when it passes
the first. Suppressing these values (returning `None` → `"N/A"`) is the
standard industry practice, mirroring how the existing non-convergent
IRR case is already handled. The guardrails are additive and conservative:

- They only suppress values on loss-making deals (IRR guardrail) or
  degenerate denominators (margin guardrail).
- Legitimate high-IRR profitable deals, and loss-making deals with
  modest IRRs, are unchanged.
- Typical well-behaved golden outputs (positive pv_premiums, modest
  IRRs) retain their prior numeric values up to floating-point noise.

**Impact on golden baselines:** Regenerated. Only one semantic change:
`golden_flat.json::TERM.cedant_profit_margin` went from
`1.4020878265412453` → `null`, correctly reflecting the negative
`pv_premiums` for that cohort. All other golden values changed only at
the float-noise level (final ULP).

**Tests:** Six new tests in
`tests/test_analytics/test_profit_test.py::TestProfitTesterReportingGuardrails`
verify each guardrail closed-form: IRR suppression vs preservation under
the four cross-product combinations of (magnitude small/large) × (deal
profitable/unprofitable); margin suppression when `pv_premiums < 0` and
`pv_premiums == 0`; margin preservation when `pv_premiums > 0` (even on
losses — well-defined). Two existing margin tests were tightened with
`is not None` assertions to confirm the common path returns a concrete
float.

---

## ADR-042: Per-policy substandard rating fields on `Policy`

**Date:** 2026-04-20
**Status:** Accepted (Slice 1 of 3 — data model only)

**Context:** Polaris RE cannot currently price substandard business. The
`Policy` model has an `underwriting_class` string (free-form) but no
numeric mortality multiplier or flat extra, and the only mortality
multiplier available is block-level on `AssumptionSet`. This blocks any
deal where the cedant has priced rated lives (Table 2, Table 4, etc.) or
flat extras ($/1000 face amount for tobacco, aviation, occupational
hazard, etc.) — which is most commercial individual life reinsurance.

Options considered:

1. Keep rating in `underwriting_class` as a string and translate at
   projection time. Rejected: the projection engine must remain
   decoupled from rating-code dictionaries, and the string type loses
   precision (Table 2½ is common).
2. Add per-policy multipliers to `AssumptionSet`. Rejected: an
   `AssumptionSet` is meant to be a block-level, immutable input;
   tying a per-policy rating into it violates the existing separation
   of "per-policy data" (Policy) from "how we project" (AssumptionSet).
3. **Add `mortality_multiplier: float = 1.0` and
   `flat_extra_per_1000: float = 0.0` directly to `Policy`, with
   defaults that make standard business unchanged.** Chosen.

**Decision:** Extend `Policy` with two new fields:

- `mortality_multiplier: float = 1.0` (validated `0.0 ≤ x ≤ 20.0`) —
  dimensionless factor applied to base `q_x`. 1.0 is standard; 2.0 is
  Table 2 (200%); 5.0 is Table 8 (500%).
- `flat_extra_per_1000: float = 0.0` (validated `0.0 ≤ x ≤ 100.0`) —
  annual flat extra premium expressed as dollars per $1,000 of face
  amount. Applied as `flat_extra / 1000 / 12` added to the monthly
  mortality decrement inside each product engine.

Expose them vectorized on `InforceBlock` as
`mortality_multiplier_vec` and `flat_extra_vec` (shape `(N,)`,
dtype `float64`), matching the established vectorization contract.
Extend `InforceBlock.from_csv()` to read the two optional columns,
defaulting to `1.0` / `0.0` when absent so all pre-existing CSV fixtures
continue to load unchanged.

**Rationale:** The fields sit on `Policy` because substandard rating is
a per-life property and must survive block filtering, aggregation, and
round-trip through CSV. Defaults of `1.0` and `0.0` are the identity
elements for their respective operations (multiply by 1; add 0), which
preserves every existing test and golden baseline — Slice 1 is a pure
structural addition with no behavioural change. Slices 2 and 3 (wiring
into product engines and ingestion/CLI/dashboard) are tracked in
`docs/CONTINUATION_substandard_rating.md` and will land in separate PRs.

The effective mortality formula

    q_eff = q_base * mortality_multiplier + flat_extra_per_1000 / 1000 / 12

mirrors standard reinsurance pricing practice: the multiplier scales the
base probability, and the flat extra is an additive monthly increment
derived from the annual $/1000 quote.  The formula is documented here so
that Slice 2 implementers in each product engine use identical semantics;
`q_eff` must be capped at `1.0` to preserve the invariant that mortality
rates are probabilities.

**Bounds rationale:** `mortality_multiplier` is capped at `20.0` because
lives rated above Table 16 (1600%) are declined in practice — anything
above this is almost certainly a data error.  `flat_extra_per_1000` is
capped at `100.0` ($100 per $1,000/year ≈ 10% annual mortality from the
flat extra alone on level face), which is well beyond any realistic
commercial quote.

**Impact on golden baselines:** None. All existing policies are
constructed without these fields, so they default to 1.0 / 0.0. No
product engine consumes the fields yet (Slice 2), so projections produce
byte-identical results.

**Tests:** `tests/test_core/test_models.py::TestPolicySubstandardRating`
(field defaults, explicit values, bound validation on both fields) and
`TestInforceBlockSubstandardVecs` (vec shape/dtype, neutral defaults,
explicit-rating round-trip). `tests/test_core/test_inforce_csv.py` adds
backward-compat for CSVs without the new columns plus a positive test
that values in CSV flow through to Policy.

---

## ADR-043: Wiring substandard rating into life product engines

**Date:** 2026-04-20
**Status:** Accepted (Slice 2 of 3 for the substandard-rating feature;
supersedes the "Slice 1 of 3" scope note in ADR-042 for behavioural
effects only — ADR-042 remains authoritative on the data model)

**Context:** ADR-042 added `mortality_multiplier` and
`flat_extra_per_1000` to `Policy` with defaults of `1.0` / `0.0` and
exposed them as `InforceBlock.mortality_multiplier_vec` and
`flat_extra_vec`. No product engine read these fields, so the slice was
behaviour-neutral by construction. Slice 2 wires them into the
life-insurance product engines so that projected claims reflect
substandard rating.

**Decision:** Inside the monthly rate-array construction of each life
product engine, apply

    q_eff = min(q_base * multiplier + flat_extra / 1000 / 12, 1.0)

where `q_base` is the monthly base mortality (post-improvement for
TermLife), `multiplier` is `mortality_multiplier_vec`, and the flat-extra
monthly increment is `flat_extra_vec / 12000.0`. Implemented in:

- `TermLife._build_rate_arrays()` — after mortality-improvement
  adjustment, before the `active` mask zeros out expired policies.
- `WholeLife._build_rate_arrays()` — after base lookup, before the
  max-age override that forces certain death at `omega`.
- `UniversalLife._build_mortality_arrays()` — after base lookup, before
  the max-age override.

**YRT ceded premium policy:** YRT rates remain unmultiplied by
`mortality_multiplier`. Under the current treaty layer, ceded claims
are a function of the GROSS `death_claims` column which already reflects
`q_eff`, so substandard risk flows through to the reinsurer in ceded
claims automatically. The `yrt_rate` schedule itself is not adjusted,
matching common reinsurance practice where the cedant bears incremental
rating risk on premium unless the treaty is explicitly written to bill
rated YRT. This is a reversible default — a future treaty-level field
can override without touching the product engines.

**Disability out of scope for Slice 2:** `DisabilityProduct` is
unaffected by this change. CI/DI substandard rating is a separate
concept (morbidity rating, not mortality rating). If reinsurers want
substandard decrements on CI/DI active lives, that will land in a
future slice after the ingestion and CLI surface (Slice 3) confirms
how cedant rating codes should map onto morbidity products.

**Flat extra reporting:** The flat-extra component is folded into
aggregate `CashFlowResult.death_claims` — it is not reported as a
separate cash-flow line. This matches the CONTINUATION default and
keeps the `CashFlowResult` contract unchanged; splitting the flat-extra
component into its own line would be a Phase-3 feature.

**Rationale for placement in the rate-array construction:** Substandard
rating is conceptually a per-policy modifier of the base mortality
vector, not a downstream adjustment to claims. Applying inside
`_build_rate_arrays` means every downstream calculation — claim
projection, in-force factor `lx`, net-premium reserves, COI charges in
UL — all consistently see the post-rating `q_eff`. Applying it later
(e.g., only to `death_claims`) would decouple reserves and `lx` from
the rated mortality, producing actuarially incorrect projections.

**Impact on golden baselines:** None. All existing inforce fixtures
carry default `mortality_multiplier = 1.0` and `flat_extra_per_1000 =
0.0`, and `q_base * 1.0 + 0.0 = q_base`, which in turn is always
below the cap of 1.0 for realistic ages. Golden regression outputs are
byte-identical with Slice 1.

**Tests:** `tests/test_products/test_term_life.py::TestTermLifeSubstandardRating`,
`tests/test_products/test_whole_life.py::TestWholeLifeSubstandardRating`,
`tests/test_products/test_universal_life.py::TestUniversalLifeSubstandardRating`
— five closed-form / edge-case tests per product (15 total): default-is-
identity, multiplier scales first-month claim exactly 2x, flat-extra
first-month increment equals `face * $5 / 12000`, zero-rating produces
zero claims, and extreme multiplier is capped at 1.0.

---

## ADR-044: Cedant rating-code registry and block rating composition

**Date:** 2026-04-20
**Status:** Accepted (Slice 3 of 3 for the substandard-rating feature —
ingestion, CLI pass-through, and dashboard surface. ADR-042 remains
authoritative on the data model; ADR-043 on the product-engine
effect.)

**Context:** ADR-042 added `mortality_multiplier` and
`flat_extra_per_1000` to `Policy`; ADR-043 wired them into every life
product engine. Both slices kept the I/O surface unchanged: the CLI
accepted rated CSVs only because `InforceBlock.from_csv` was extended
in Slice 1, and there was no way for a cedant to express rating as a
string code like `TBL2` or `FE5` — users had to pre-translate codes
into numeric multipliers externally. That gap forced Excel-based
workarounds and prevented the pipeline from being self-contained
end-to-end.

**Decision:** Extend `polaris_re.utils.ingestion.IngestConfig` with an
optional `rating_code_map: RatingCodeMap` field. The registry
translates ONE cedant column (e.g. `RATE_CLASS`) into the TWO
Polaris-side fields:

    q_eff contributors  ←  mortality_multiplier
                          flat_extra_per_1000

Semantics:

- `RatingCodeEntry` mirrors the `Policy` bounds (`mortality_multiplier`
  `∈ [0, 20]`, `flat_extra_per_1000 ∈ [0, 100]`). Validation at the
  ingestion boundary is identical to validation at the projection
  boundary — no ingestion path can produce a Policy that would fail
  later.
- Unknown codes fall back to `default` (standard 1.0 / 0.0). This is
  intentional: a typo in the cedant's code column should not crash the
  pipeline silently, and treating unknowns as standard is the
  conservative reinsurer-facing default.
- The rating map overwrites pre-existing `mortality_multiplier` /
  `flat_extra_per_1000` columns, because when both are supplied the
  rating code is the audit-trail-bearing source of truth.
- The map is applied AFTER `column_mapping` renames (so
  `source_column` always refers to the post-rename Polaris column
  name) and AFTER `code_translations` (so value-to-value cedant
  translations do not interfere with the rating registry).

**Supporting surface:**

- `DataQualityReport` gains `n_rated`, `pct_rated_by_count`,
  `pct_rated_by_face`, `mean_multiplier_rated` so the ingestion CLI
  can report at a glance how much of a block carries substandard
  ratings.
- `polaris_re.utils.rating.rating_composition(InforceBlock)` is the
  single source of truth for block-level rating metrics. It is used
  by both the CLI (`polaris price` JSON output, `rated_block` key) and
  the Streamlit dashboard (inforce view, "Substandard Rating" panel
  and face-by-rating-band chart). Duplicating the computation in two
  places would let the dashboard and CLI drift — the shared helper
  prevents that by construction.
- The `polaris price` JSON output always includes `rated_block`. For
  all-standard blocks this is a zero-rated shape — it costs one float
  per key and zero CI churn, and it lets downstream consumers treat
  the key as always-present.

**InforceBlock interface impact:** None. The helper is a read-only
function over the existing `mortality_multiplier_vec` /
`flat_extra_vec` / `face_amount_vec` properties added in Slice 1. No
new fields, no new methods on the core contract.

**Backward compatibility:** All existing ingestion configs remain
valid — `rating_code_map` defaults to `None`, in which case ingestion
behaviour is byte-identical to pre-ADR-044. Golden regression outputs
are unchanged (golden CSVs carry no rating columns, and the default
path never synthesises them).

**Rationale for a nested (RatingCodeEntry) shape:** A flat
`dict[str, float]` for each Polaris field would require the user to
spell out two parallel maps, and it would be easy to keep one in
sync while forgetting the other. A nested per-code entry makes the
invariant "one code → one (multiplier, flat_extra) pair" explicit and
validates both fields together at load time.

**Tests:** `tests/test_utils/test_ingestion.py::TestRatingCodeMap`
(7 tests — multiplier derivation, flat-extra derivation, missing
map, custom default, round-trip into InforceBlock, bound
validation, YAML load), `TestValidateRatingReport` (4 tests —
count-based and face-based rating share, mean multiplier over rated
subset, zero-rating baseline), `tests/test_utils/test_rating.py`
(5 tests — the `rating_composition` helper over a hand-built block),
`tests/qa/test_cli_golden.py::TestCLIRatedBlockOutput` (2 tests —
all-standard golden CSV emits zeroed `rated_block`; rated CSV
surfaces correct `max_multiplier`, `max_flat_extra_per_1000`, and
non-zero `pct_rated_by_count`).

## ADR-045: Deal-pricing Excel export format

**Date:** 2026-04-21
**Status:** Accepted (Slice 1 of 2 for the deal-pricing Excel-export
feature — this slice ships the workbook writer as a library function
and the DTOs that bound it. Slice 2 will wire the writer into
`polaris price --excel-out`.)

**Context:** Polaris RE already emits JSON results from `polaris
price`, and the rate-schedule command ships a rate-schedule Excel
workbook via `write_rate_schedule_excel`. Committee packets at a
reinsurer are Excel artefacts — a pricing actuary circulates a
formatted workbook with a one-page Summary, an annual Cash Flows
table, a list of key assumptions, and a sensitivity table. JSON is
not a committee deliverable. The PRODUCT_DIRECTION_2026-04-19
assessment flagged "Deal-pricing Excel export" as the third BLOCKER
for first-deal submission.

**Decision:** Add `polaris_re.utils.excel_output.write_deal_pricing_excel(
export, path)` that renders a formatted four-sheet workbook from a
single `DealPricingExport` bundle:

    1. Summary      — profit metrics (IRR, PV, margin, breakeven, etc.)
                       with one column per side (Cedant / Reinsurer).
    2. Cash Flows   — annual rollup of the NET CashFlowResult, seven
                       canonical columns (Year / Gross Premiums /
                       Death Claims / Lapse Surrenders / Expenses /
                       Reserve Increase / Net Cash Flow).
    3. Assumptions  — flat label/value table sourced from
                       `DealMetaExport` + `AssumptionsMetaExport`.
    4. Sensitivity  — OMITTED when `export.scenario_results` is None;
                       otherwise one row per `ScenarioMetric`.

**DTO design:** The writer takes a single `DealPricingExport`
dataclass rather than a long keyword list. Sub-DTOs
(`DealMetaExport`, `AssumptionsMetaExport`, `ScenarioMetric`) are
`@dataclass(frozen=True)` with explicit typing — no `dict[str, Any]`,
per the project typing rules. This keeps the CLI wiring (Slice 2) a
mechanical translation from `CohortResult` + `PipelineInputs` into
an export bundle, and it keeps the writer itself free of CLI or
pipeline imports.

**Rationale for annual rather than monthly cash flows:** Committee
packets never present 240-month granularity — the reviewers' mental
model is annual. Aggregating monthly → annual inside the writer
matches what `ProfitTester.profit_by_year` already does and gives a
20-row table for a standard 20-year projection. Partial trailing
years are rendered as an additional Year N+1 row, mirroring
`ProfitTester` exactly, so both outputs agree on what "Year 21"
means for a 241-month projection.

**Rationale for mandatory NET cash flows:** Net-basis cash flows are
the input a `ProfitTester` accepts and the Summary sheet's metrics
describe. Gross and ceded bases are interesting for audit, but for
Slice 1 the contract stays narrow — `gross_cashflows` and
`ceded_cashflows` are currently accepted as optional fields on the
bundle but not yet rendered, to avoid committing to a presentation
(separate sheets? merged columns?) before the CLI wiring
(Slice 2) confirms what downstream consumers need. Adding those
sheets later is purely additive.

**Guardrail handling:** `ProfitTestResult.irr` and
`ProfitTestResult.profit_margin` are `float | None` under ADR-041.
The writer renders `None` as the string `"N/A"` in the affected
cell (and falls back to no number format for that cell). This keeps
the workbook lossless with respect to the JSON output — a cell that
JSON reports as `null` becomes an explicit `"N/A"` in Excel, and a
float cell always carries a numeric format so the committee sees
percentages as percentages.

**Reinsurer column conditional on `reinsurer_result`:** The Summary
sheet grows a third column only when a reinsurer side exists. For a
stand-alone gross projection (no treaty), the Cedant column is the
only metric column, which keeps standalone pricing runs visually
clean.

**Out of scope for Slice 1:** (1) CLI flag `polaris price
--excel-out path.xlsx`, (2) gross/ceded cash-flow sheets, (3)
per-cohort workbooks for mixed-product blocks (one file vs one per
cohort). All three will be decided in Slice 2 on the basis of
concrete CLI behaviour.

**Tests:** `tests/test_utils/test_excel_output.py` (20 tests) —
structure (file created, expected sheets for minimal/full export,
workbook roundtrips), Summary (cedant IRR/PV match source, reinsurer
column presence/absence, IRR=None → "N/A", profit_margin=None →
"N/A"), Cash Flows (row count = projection_years, year-1 premium
aggregation matches monthly sum, all required columns present, total
NCF equals monthly sum), Assumptions (mortality source, treaty,
cession, hurdle rate value), and Sensitivity (row per scenario,
scenario name preservation, PV profits cell match).

