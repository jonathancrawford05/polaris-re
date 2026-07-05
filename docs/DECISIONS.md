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


## ADR-046: `polaris price --excel-out` CLI wiring

**Date:** 2026-04-24
**Status:** Accepted (Slice 2 of 2 for the deal-pricing Excel-export
feature — the writer + DTOs were delivered in Slice 1 / ADR-045;
this ADR records the CLI wiring and the per-cohort file-layout
decision for mixed blocks.)

**Context:** ADR-045 added `write_deal_pricing_excel` as a library
function that consumes a `DealPricingExport` bundle. It had no
caller — `polaris price` still emitted JSON only. The committee
needs a single CLI invocation that produces the workbook alongside
the existing JSON. The CONTINUATION file flagged two open design
questions: (a) mixed-cohort workbook layout (one-workbook-many-sheets
vs one-workbook-per-cohort), and (b) whether to also render
gross/ceded cash-flow sheets.

**Decision:** Add `--excel-out PATH` to `polaris price`. When
provided, after the per-cohort pricing loop runs, each
`CohortResult` is translated into a `DealPricingExport` and written
via `write_deal_pricing_excel`. The existing JSON path is
unchanged — `--excel-out` is purely additive.

*Mixed-cohort layout (one-file-per-cohort).* For a homogeneous
block (single cohort) the workbook is written exactly at the
supplied path — `deal.xlsx` means `deal.xlsx`. For a mixed block,
the cohort id is appended to the stem: `deal.xlsx` becomes
`deal-TERM.xlsx` and `deal-WHOLE_LIFE.xlsx`. This preserves the
Slice-1 workbook schema exactly (one cohort per workbook — no sheet
collisions), keeps committee packets self-contained per product
(the common circulation pattern), and avoids ambiguity about what
"Summary" means when several cohorts are present.

*Cash flows are threaded through `CohortResult`.* The
`CohortResult` dataclass in `cli.py` now carries
`net_cashflows: CashFlowResult`, `gross_cashflows: CashFlowResult`,
and `ceded_cashflows: CashFlowResult | None`. This keeps the live
objects in scope for `_cohort_to_deal_pricing_export` without
touching any core contracts (the `CashFlowResult` layout itself is
unchanged). The `CashFlowResult` type was already imported by
`cli.py`, so the extension is a CLI-local change.

*Translation helpers live in `cli.py`.* `_cohort_to_deal_pricing_export`
builds `DealMetaExport` from `DealConfig` / `ProjectionConfig` and
`AssumptionsMetaExport` from `AssumptionSet` / `MortalityConfig`.
`_describe_lapse(LapseAssumption)` produces the one-line
`lapse_description` string. Both helpers are CLI-private so the
writer stays free of pipeline imports (a key Slice-1 invariant).

**Open-questions status (tracked in CONTINUATION_deal_pricing_excel):**

1. **Mixed-cohort layout** — resolved as "one file per cohort" (see
   above). Reviewers can still override in a follow-on ADR if the
   "one-workbook-many-sheets" ergonomics are preferred.
2. **Gross/ceded cash-flow sheets** — still deferred. The DTO
   already accepts them; Slice 2 does not render them. A later PR
   can add two sheets additively without a CLI contract change
   (no new flags, no new fields).
3. **Rated-block panel on Assumptions sheet** — deferred. The JSON
   output already carries `rated_block`; teaching the workbook to
   render it is an Assumptions-sheet-only change that can ship
   without touching the CLI.
4. **`--with-sensitivity` inline scenarios** — deferred. `polaris
   scenario` remains the authoritative sensitivity-analysis entry
   point. `polaris price --excel-out` never populates the
   Sensitivity sheet, and the writer omits the sheet entirely when
   `scenario_results is None` (ADR-045).

**Tests (`tests/qa/test_cli_golden.py::TestCLIExcelOut`, 4 tests):**
- Single-cohort run writes exactly the supplied path; Summary IRR
  cell matches the JSON `cedant.irr`; Cash Flows sheet has
  `projection_years` data rows; Sensitivity sheet is absent.
- Mixed-cohort run (golden CSV has TERM and WHOLE_LIFE) writes
  `deal-TERM.xlsx` and `deal-WHOLE_LIFE.xlsx` but NOT `deal.xlsx`.
- Omitting `--excel-out` produces no `.xlsx` (JSON-only regression
  guard).
- Assumptions sheet values match the config's treaty type, cession,
  hurdle, discount, and projection years.

---

## ADR-047: LICAT regulatory capital — factor-based v1 with NAR C-2

**Date:** 2026-04-25
**Status:** Accepted (Slice 1 of Phase 5.1)

**Context:** Reinsurer deal evaluation hinges on return-on-required-capital
(RoC), not IRR alone. PRODUCT_DIRECTION_2026-04-19 identified the absence
of a regulatory capital module as a BLOCKER. Polaris RE needed a
LICAT-aligned `required_capital(cashflows)` calculation as the foundation
for an RoC metric. OSFI's 2024 LICAT mortality risk framework uses a
shock-based scenario approach: required capital is the change in BEL under
a prescribed mortality stress (level shock + trend shock + catastrophe
shock). Replicating that approach requires re-running the projection under
each shock, which is a substantial engineering effort and is more naturally
deferred to a later phase once the calculator's interface is stable.

**Decision:** Implement LICAT capital as a factor-based proxy in Slice 1.
Required capital at each monthly step is the linear combination

```
capital_t = c1_factor × reserve_t + c2_factor × NAR_t + c3_factor × reserve_t
```

where `c2_factor` is calibrated per product type to approximate the
shock-based result for an individual life book of that product type, and
`c1_factor` / `c3_factor` are zero stubs to be populated once the asset /
ALM model lands in Phase 5.4.

Default C-2 factors via `LICATCapital.for_product(...)`:

| Product | c2_mortality_factor |
|---|---|
| TERM | 0.15 |
| WHOLE_LIFE | 0.10 |
| UNIVERSAL_LIFE | 0.08 |
| DISABILITY | 0.05 |
| CRITICAL_ILLNESS | 0.05 |
| ANNUITY | 0.03 |

NAR is sourced from `cashflows.nar` (populated by YRT treaty application)
or supplied explicitly as a `(T,)` array. CEDED basis is rejected — capital
is held against retained business.

**Rationale:**
- **Factor approach is auditable.** The output `c2_t = factor × NAR_t` is
  hand-verifiable from the published factor table; this is what a deal
  committee will demand on first review.
- **Factor approach is composable.** Slice 2 wires capital into
  `ProfitTester.run_with_capital`; Slice 3 surfaces RoC via CLI / API /
  Excel. None of that integration depends on the internal capital
  calculation, so a future shock-based v2 can replace the factor formula
  without touching the integration surface.
- **NAR from `CashFlowResult.nar` keeps the contract clean.** YRT treaty
  already populates that field; the CLI need not pass NAR around. For
  non-YRT runs, the explicit `nar=` override or a future
  `face_amount_in_force` derivation supplies the input.
- **Per-product factors expose the actuarial driver.** A WL block on a YRT
  treaty looks very different from a TERM block, and a single global factor
  would either understate WL or overstate TERM. Per-product defaults give
  pricing actuaries a credible starting point with one knob to override.

**Out of scope for Slice 1:**
- Shock-based mortality stress recomputation (Phase 5.1 v2 / Phase 5.4).
- C-1 asset default and C-3 interest-rate components (Phase 5.4).
- Lapse-risk and morbidity-risk components (separate ADRs once the
  underlying stress framework is in).
- `ProfitTester.run_with_capital` and the `return_on_capital` metric
  (Slice 2 of this CONTINUATION).
- CLI `--capital licat` flag, API `capital_model` field, Excel surfacing
  (Slice 3).

**Open questions deferred to Slice 2 / 3:**
1. Whether to introduce `face_amount_in_force` on `CashFlowResult` so
   non-YRT runs can derive NAR without an explicit caller-supplied vector.
   Slice 2 will address as part of the `run_with_capital` plumbing, since
   that is where the InforceBlock is still in scope.
2. Whether RoC denominator should be a stock metric (`pv_capital`) or a
   strain metric (PV of capital increases). Industry practice varies; we'll
   choose in Slice 2 with documented rationale.

**Tests (`tests/test_analytics/test_capital.py`, 31 tests):**
- `LICATFactors` validation: defaults, non-negativity, ≤1 cap, frozen.
- `LICATCapital.for_product` returns the right factor per product type
  (parametrised across all six `ProductType` values) and zero C-1 / C-3.
- `required_capital` closed-form: `c2 = factor × NAR`, zero C-1 / C-3,
  total = sum of components, initial = period 0, peak = max, doubling
  factor doubles C-2, zero factor zero capital.
- NAR resolution: uses `cashflows.nar` when present, explicit override
  takes precedence, missing NAR raises, length mismatch raises.
- Basis acceptance: GROSS / NET accepted, CEDED rejected.
- `CapitalResult.pv_capital` monotone in rate, zero-rate equals
  undiscounted sum.
- Closed-form OSFI verification: TERM 1M NAR @ 0.15 = 150K; WL 2M NAR
  @ 0.10 = 200K.
- Module exports: `LICATCapital`, `LICATFactors`, `CapitalResult`
  importable from `polaris_re.analytics`.

---

## ADR-048: ProfitTester capital integration — RoC denominator and capital-adjusted IRR

**Date:** 2026-04-26
**Status:** Accepted (Slice 2 of Phase 5.1)

**Context:** ADR-047 introduced the standalone `LICATCapital` calculator
producing a required-capital schedule from a `CashFlowResult`. Slice 2 of
the LICAT capital feature wires that calculator into `ProfitTester` so a
single call returns both the profit metrics and the
return-on-capital (RoC) figure that pricing actuaries need at deal
committee. The integration raises three design questions:

1. RoC denominator — PV of capital STOCK vs PV of capital STRAIN.
2. NAR sourcing for non-YRT runs.
3. How to express a capital-adjusted IRR that respects shareholder
   capital lock-up.

**Decision:**

1. **RoC denominator defaults to PV(capital STOCK)** at the hurdle rate.
   `return_on_capital = pv_profits / pv_capital`, where `pv_capital`
   discounts the period-end capital balance at each month back to t=0.
   This is the simpler and more widely cited definition and matches the
   "PV of profits per dollar-year of capital tied up" intuition pricing
   actuaries use at first-pass committee screening. The strain measure
   (`pv_capital_strain`) is exposed on `CapitalResult` so callers that
   prefer the incremental view can compute it without subclassing —
   future ADR can flip the default if firm policy evolves.

2. **NAR sourcing.** `ProfitTester.run_with_capital(capital_model, *,
   nar=None)` forwards the `nar=` keyword to `LICATCapital.required_capital`.
   The Slice 2 call sites (which all live in CLI / API / dashboard,
   covered by Slice 3) are responsible for deriving NAR from the
   `InforceBlock` when the upstream `CashFlowResult` does not already
   carry it (e.g. coinsurance/modco runs). This honours the PR-#33
   guard rail of NOT expanding `CashFlowResult` with a stock variable
   in this phase.

3. **Capital-adjusted IRR** is the IRR of distributable cash flow,
   defined as

       distributable_t = net_cash_flow_t - strain_t

   with `strain_t = capital_t - capital_{t-1}` (capital_{-1} = 0). The
   residual capital balance at month T-1 is released back to
   shareholders as a terminal positive (`distributable[T-1] +=
   capital[T-1]`), so the capital flows recycle to zero across the
   projection. Sign-change suppression and large-magnitude guard rails
   from ADR-041 apply unchanged via the shared `_solve_irr` helper.

**Rationale:**

- **Stock denominator is auditable.** PV(capital × discount factor) is
  a single hand-checkable calculation; PV(strain) requires a
  period-over-period diff that obscures the per-month capital level a
  reviewer wants to spot-check.
- **`run_with_capital` preserves backward compatibility.**
  `ProfitResultWithCapital` extends `ProfitTestResult` so every existing
  caller of `tester.run()` is unaffected; the new fields default to
  zero / None when constructed directly.
- **Capital-adjusted IRR captures shareholder economics.** Shareholders
  see distributable cash flow net of capital injections and gross of
  capital releases; the IRR of that stream is the rate of return on
  shareholder funds and is by construction no greater than the vanilla
  IRR for any deal that requires net positive capital strain.
- **Strain telescope is preserved.** Sum of `capital_strain` over the
  projection equals `capital[T-1]`. The terminal release sets the IRR
  cash-flow sum equal to the vanilla profit sum, ensuring the capital
  treatment does not change the undiscounted profit total — only its
  time profile.

**Out of scope for Slice 2:**
- CLI flag, API field, Excel surfacing (Slice 3).
- Strain-denominator default (deferred; `pv_capital_strain` is
  already exposed for callers that prefer it).
- Cost-of-capital interest credit on the held-capital balance (some
  firms add `capital_t × risk_free_rate / 12` as an offset to the
  capital charge — out of scope until Phase 5.4 lands a risk-free
  curve).
- Lapse-risk and morbidity-risk capital components (still pending the
  Phase 5.1.b ADR after Slice 3 ships).

**Tests (`tests/test_analytics/test_profit_test.py`):**

- `TestProfitTesterWithCapital` (12) — return type, base-field
  preservation, RoC closed-form (`pv_profits / pv_capital`),
  doubling-factor halves RoC, explicit `nar=` plumbing, missing NAR
  raises, zero-factor → RoC None, capital_by_period shape/values,
  pv_capital_strain for flat capital, capital-adjusted IRR < vanilla
  IRR for a strained deal, `run()` unaffected by `run_with_capital`,
  and module export of `ProfitResultWithCapital`.
- `TestPvCapitalStrainClosedForm` (2) — telescope at rate=0
  (sum of strain = `capital[T-1]`); flat-capital strain PV equals
  `K × v` (only initial injection has weight).

---

## ADR-049: LICAT capital surfacing — CLI / API / Excel / dashboard, NAR helper

**Date:** 2026-04-26
**Status:** Accepted (Slice 3 of Phase 5.1)

**Context:** ADR-047 (LICAT calculator) and ADR-048 (ProfitTester
integration) ship the capability internally. Slice 3 makes the metric
queryable from the three production surfaces — `polaris price` CLI,
`POST /api/v1/price`, and the deal-pricing Excel workbook — plus the
Streamlit dashboard. The user-visible question at every surface is
"what RoC does this deal generate?" so the metric must be opt-in
(no breakage for existing consumers) and consistent across surfaces.

The integration also needs a NAR-derivation helper at the call site:
`CashFlowResult.nar` is populated only by `YRTTreaty.apply` (and only
on the CEDED side); for coinsurance / modco / no-treaty runs and for
the cedant view of YRT, the call site must derive NAR explicitly. The
PR-#33 reviewer confirmed (and PR-#34 reviewer reaffirmed) that we do
NOT extend `CashFlowResult` with a stock variable in this phase.

**Decision:**

1. **`derive_capital_nar(gross, reserve_balance, face_amount_total, *,
   cession_pct=None, is_reinsurer=False)`** is the canonical helper for
   this NAR derivation and lives next to `derive_yrt_rate` /
   `ceded_to_reinsurer_view` in `polaris_re.core.pipeline`. It mirrors
   the inforce-ratio approximation that `YRTTreaty.apply` already uses:

       inforce_ratio_t = gross.gross_premiums / gross.gross_premiums[0]
       face_in_force_t = face_amount_total * face_share * inforce_ratio_t
       nar_t           = max(face_in_force_t - reserve_balance_t, 0.0)

   `face_share` is `1.0` when `cession_pct is None` (gross / no-treaty
   case), `(1 - cession_pct)` for the cedant view, and `cession_pct`
   for the reinsurer view. The same formula works across YRT,
   coinsurance, and modco — pass the cashflows-being-capitalised
   `reserve_balance` to get a consistent NAR.

2. **CLI: `polaris price --capital licat`.** Single-value enum (only
   `licat` is shipped). When set, both cedant and reinsurer profit
   tests call `ProfitTester.run_with_capital(LICATCapital.for_product(...))`
   with `nar=` derived per-side via `derive_capital_nar`. The JSON
   output gains an additive capital block on every cohort
   (`return_on_capital`, `peak_capital`, `pv_capital`,
   `pv_capital_strain`, `capital_adjusted_irr`); the Rich console
   adds rows for each metric. When `--capital` is not supplied, the
   JSON output schema and console output are byte-identical to
   pre-Slice-3.

3. **API: `PriceRequest.capital_model: Literal["licat"] | None`.**
   Default `None` keeps every existing API consumer unaffected.
   `PriceResponse` gains optional capital fields with default `None`
   on both the cedant and reinsurer sides; populated only when
   `capital_model="licat"`. Pydantic `Literal` validation rejects
   unknown values with a 422 — no string-bool / typo gotchas.

4. **Excel: `_CAPITAL_METRICS` rows on the Summary sheet, conditional
   on the rendered result being `ProfitResultWithCapital`.** The
   `DealPricingExport` DTO is unchanged; the writer detects capital
   results via `isinstance` and appends the rows below the existing
   `_SUMMARY_METRICS`. Workbooks produced without `--capital` are
   byte-identical pre-Slice-3. Per PR-#34 reviewer, `pv_capital_strain`
   is surfaced as an advisory metric alongside the primary RoC and
   peak capital rows.

5. **Dashboard: "Compute LICAT capital + RoC" checkbox** on the
   Pricing page. When checked, `_run_pricing_for_cohort` switches to
   the capital-aware code path; the cedant and reinsurer views each
   gain a row of three Streamlit `st.metric` tiles for Return on
   Capital, Peak Capital, and PV Capital Strain (with help-text
   explaining the stock-vs-strain choice from ADR-048).

**Rationale:**

- **Single NAR helper, four call sites.** Putting the NAR derivation
  in `pipeline.py` (the existing canonical home for treaty-aware
  helpers) means CLI, API, dashboard, and any future consumer all
  use the same formula. The cedant/reinsurer face-share split is a
  single keyword arg (`is_reinsurer`), so the call sites stay
  one-liners.
- **Inforce-ratio approximation is consistent with YRT.** Reusing
  the same `gross.gross_premiums / gross.gross_premiums[0]` runoff
  shape as `YRTTreaty.apply` means the LICAT NAR for non-YRT runs
  is comparable to the YRT NAR — no surprise step-changes when a
  user toggles between treaty types.
- **Opt-in everywhere.** The CLI flag is absent by default; the API
  field is `None` by default; the Excel writer detects the capital
  type via `isinstance`; the dashboard checkbox is unchecked. This
  preserves every existing consumer's contract and lets us merge
  Slice 3 without coordinated downstream releases.
- **Single capital model in this slice.** Only `licat` is shipped.
  CLI and API both reject unknown values with a clear error. Future
  models (e.g. EU `solvency2`, US `naic_rbc`) can be added by
  extending the same enum without changing the surface shape.
- **Dashboard surfacing matches Excel labels.** Both the dashboard
  tiles and the Excel rows use the same "Return on Capital" / "Peak
  Capital" / "PV Capital Strain" labels so committee deck producers
  can map them to the workbook 1-for-1.

**Out of scope:**

- Cost-of-capital interest credit on held capital (still deferred
  to Phase 5.4 / risk-free curve).
- Lapse-risk and morbidity-risk LICAT components.
- Multiple capital models per call (a deal-level comparison view
  is a separate ADR).
- Per-cohort RoC aggregation at the mixed-block summary level (the
  CLI summary table still reports total cedant / reinsurer PV
  profits only — capital aggregation across cohorts requires a
  weighting decision that is itself a separate ADR).

**Tests:**

- `tests/test_core/test_pipeline_capital_nar.py` (15) — basics
  (face−reserve, dtype/shape, floor at zero, zero-initial-premium
  fallback, empty projection), inforce-ratio scaling, cession-aware
  splits (cedant + reinsurer face-share, sum to total, parameterised
  cession sweep), reserve subtraction.
- `tests/test_analytics/test_cli.py::TestPriceCommandCapital` (4) —
  JSON capital block under `--capital licat`; absent without the
  flag; invalid value exits 1; console rendering of "Return on
  Capital" / "Peak Capital".
- `tests/test_api/test_main.py::TestPriceEndpoint` (4 added) —
  capital fields null when `capital_model` omitted; numeric and
  positive when `capital_model="licat"`; invalid value rejected
  with 422; cession-pct sensitivity (higher cession → larger
  reinsurer capital, smaller cedant capital).
- `tests/test_utils/test_excel_output.py::TestSummarySheetCapitalBlock`
  (7) — capital rows absent without capital, present with capital
  result; cedant RoC and reinsurer PV capital values match;
  advisory PV Capital Strain present (PR-#34 reviewer); RoC None
  renders as "N/A"; mixed cedant/reinsurer (only one side has
  capital) renders other side as "N/A".

Total: 30 new tests; full suite passes; QA suite unchanged; golden
baselines unchanged when `--capital` is not supplied.

---

## ADR-050: Tabular YRT rate table — standalone data model (Slice 1 of 3)

**Date:** 2026-04-27
**Status:** Accepted (Slice 1 of "YRT rate schedule by age × duration"
multi-session feature; PRODUCT_DIRECTION_2026-04-19 IMPORTANT item).

**Context:**

`YRTTreaty` accepts a single `flat_yrt_rate_per_1000` scalar to compute
ceded premiums against an aggregate NAR runoff. PRODUCT_DIRECTION_2026-
04-19 flags this as the source of the WL YRT rate-too-low pattern: real
YRT rates rise annually with attained age, so a flat rate calibrated at
the inforce midpoint understates reinsurer cost as the block ages. The
roadmap's Milestone 4.4 already shipped a flat-rate solver; the
IMPORTANT item is to extend the data model to the full age × sex ×
smoker × duration grid and to wire it through the treaty, the rate
solver, and the CLI / API / Excel surfaces.

This ADR covers Slice 1 only: the standalone rate-table data model. No
existing module is modified beyond `reinsurance/__init__.py`. Slices 2
and 3 are tracked in `docs/CONTINUATION_yrt_rate_table.md`.

**Decision:**

1. **New module `polaris_re.reinsurance.yrt_rate_table`** with two
   public symbols:

   - `YRTRateTableArray` — storage class, one per (sex, smoker)
     combination. Holds a 2-D `float64` array of shape
     `(n_ages, select_period + 1)` indexed by
     `[age - min_age, min(duration_years, select_period)]`. Provides
     scalar `get_rate(age, duration_years)` and vectorised
     `get_rate_vector(ages, durations_years)`.
   - `YRTRateTable` — frozen Pydantic model wrapping a dict of arrays
     keyed by `f"{sex.value}_{smoker.value}"`, mirroring the
     `MortalityTable` storage convention. Provides
     `get_rate_vector(ages, sex, smoker, durations_years)` and
     `get_rate_scalar(age, sex, smoker, duration_years)`. Smoker-
     specific lookups fall back to the aggregate (`UNKNOWN`) key when
     a smoker-distinct array is absent.

2. **Rates are quoted as annual dollars per $1,000 NAR.** The lookup
   contract returns the annual rate; consumers (Slice 2) convert to
   monthly per-dollar form via `/12 / 1000`. This matches the
   convention already used by `YRTTreaty` for the flat-rate path.

3. **No upper bound on rates.** Mortality probabilities are bounded
   above by 1.0 — `MortalityTableArray` validates this. YRT rates
   routinely exceed `$50/$1,000` at advanced ages, so reusing the
   mortality storage class would force us to weaken its probability
   invariant. A small parallel storage class keeps both invariants
   intact.

4. **Storage layout matches `MortalityTableArray`** (rows by age,
   columns by duration with a final "ultimate" column). This keeps
   the look-and-feel of the actuarial code consistent and means a
   future CSV loader (deferred to Slice 3) can largely mirror
   `load_mortality_csv`.

5. **No CSV file loading in Slice 1.** `from_arrays(...)` is the
   only construction entry point. CSV loading lives with the CLI/API
   surfacing in Slice 3 to avoid a half-finished file format that
   downstream slices might rewrite.

6. **`YRTTreaty` is unchanged in this slice.** The new field
   (`yrt_rate_table: YRTRateTable | None = None`) is added in Slice
   2 alongside the consumption logic. Adding the field today without
   the consumer would be a half-finished implementation, which CLAUDE.md
   explicitly forbids.

**Rationale:**

- **Data model first** is the safest decomposition for a treaty-level
  feature. Slice 1 is purely additive — no existing test, no QA
  golden, and no runtime path is altered. All 793 pre-existing
  non-slow tests still pass byte-identically.
- **Mirroring `MortalityTable`** lets the actuarial reader recognise
  the lookup pattern at a glance. The (sex, smoker) keying, the
  age-row × duration-column layout, and the "ultimate" column
  convention are all carried over.
- **Validation hardening at construction time** (shape check,
  non-negative rates, finite values, age-range and select-period
  consistency across arrays) prevents silent data corruption at the
  Slice 2 lookup boundary, where an incorrect rate would flow into
  ceded premium calculations and silently distort RoC.
- **Single-responsibility module.** Putting the rate-table model in
  its own file keeps `reinsurance/yrt.py` (already 193 lines, with
  the apply pipeline) from doubling in size. Slice 2 imports the
  table from the new module without touching its internals.

**Out of scope:**

- `YRTTreaty.apply()` consumption of the table (Slice 2).
- Per-policy in-force factor projection for tabular rate
  application (Slice 2 design decision: aggregate-via-inforce-ratio
  vs. seriatim).
- CSV file format and `YRTRateTable.load(path)` (Slice 3).
- `YRTRateSchedule.generate(...)` extension to solve a tabular
  schedule (Slice 2 / 3).
- CLI flag `polaris price --yrt-rate-table` (Slice 3).
- API field on `PriceRequest` and Excel surfacing (Slice 3).

**Tests:**

- `tests/test_reinsurance/test_yrt_rate_table.py` (34 new tests):
  - `TestYRTRateTableArrayConstruction` (8) — float64 promotion,
    shape mismatch, age-range / select-period / negative-rate / NaN
    rejection, large-rate acceptance.
  - `TestYRTRateTableArrayLookup` (11) — scalar known-cell, ultimate-
    column clamp, age out-of-range, negative duration, vector shape /
    dtype / values / clamp / shape-mismatch / age-out-of-range /
    negative-duration.
  - `TestYRTRateTableConstruction` (6) — smoker-distinct, aggregate-
    only, empty raises, age-range / select-period inconsistency,
    frozen-after-construction.
  - `TestYRTRateTableLookup` (7) — scalar smoker-vs-non-smoker
    closed-form, vector shape / dtype, smoker-fallback-to-aggregate,
    missing-sex raises, age-monotone increase, duration-monotone
    increase through select.
  - `TestPublicExports` (2) — `YRTRateTable` and `YRTRateTableArray`
    re-exported from `polaris_re.reinsurance`.

Total: 34 new tests; full suite is now 827 non-slow (up from 793); QA
suite unchanged at 33/33; golden baselines unchanged because no
existing pricing path consumes the new module.

---

## ADR-051: Tabular YRT consumption in `YRTTreaty.apply()` — seriatim default with aggregate fallback (Slice 2 of 3)

**Date:** 2026-04-28
**Status:** Accepted (Slice 2 of "YRT rate schedule by age × duration"
multi-session feature; depends on ADR-050).

**Context:**

Slice 1 (ADR-050) added the standalone `YRTRateTable` data model.
`YRTTreaty.apply()` still bills ceded YRT premiums solely from the
`flat_yrt_rate_per_1000` scalar. This slice wires the rate table into
the treaty so that a real (age, sex, smoker, duration) rate grid can
drive ceded premiums end-to-end. Two design questions had to be settled
to do this without breaking the existing flat-rate path or any QA
golden:

1. **Per-policy in-force projection method** — the table requires
   per-policy ages and durations at every projection month, but the
   current flat path uses an aggregate-runoff approximation
   (`inforce_ratio_t = gross_premiums[t] / gross_premiums[0]`). A
   tabular path can only honour the rate table per policy if it knows
   each policy's lx[t] and V[t]. Two options were on the table at the
   end of Slice 1: (a) consume `gross.seriatim_lx` and
   `gross.seriatim_reserves` directly; (b) approximate per-policy
   in-force by reusing the aggregate-runoff factor with face-weighted
   rates.

2. **Mutual exclusion of `flat_yrt_rate_per_1000` and `yrt_rate_table`**
   — PR #36's reviewer flagged that silently letting one win could mask
   a copy-paste error in deal config. The Slice 1 CONTINUATION recorded
   this as RESOLVED in favour of mutual exclusion.

**Decision:**

1. **Add `yrt_rate_table: YRTRateTable | None = None`** to `YRTTreaty`.
   Add a Pydantic `model_validator` that raises
   `PolarisValidationError` when both `flat_yrt_rate_per_1000` and
   `yrt_rate_table` are set. Setting neither is allowed (claims-only
   cession, ceded premiums = 0) and is the long-standing behaviour
   exercised by `TestYRTEdgeCases.test_no_yrt_rate_zero_premiums`.

2. **`apply()` requires `inforce` when `yrt_rate_table` is set.** A
   tabular rate cannot be looked up without policy-level (age, sex,
   smoker, duration). When `yrt_rate_table` is set and `inforce is
   None`, raise `PolarisComputationError` with a message naming
   `InforceBlock` so the call site knows what to pass.

3. **Default consumption is the seriatim path (option a).** When the
   gross result was produced with `seriatim=True` (so
   `gross.seriatim_lx` and `gross.seriatim_reserves` are populated),
   `apply()` uses the per-policy formula

       prem[i, t] = lx[i, t] * max(face[i] - V[i, t], 0)
                    * (R[i, t] / 12 / 1000) * cession[i]

   summed across policies. Per-policy effective cession comes from
   `InforceBlock.effective_cession_vec(treaty_default)`, which respects
   policy-level overrides (ADR-036). The aggregate `nar` series carried
   on the ceded result is `(lx * NAR_per_policy).sum(axis=0)` so the
   reported NAR matches the basis on which the rates were applied.

4. **Aggregate fallback (option b) is used only when seriatim arrays
   are absent.** In that case, per-policy rates `R[i, t]` are still
   computed from the table, then face-weight-averaged to a single
   `avg_R_t` per month; that average rate is applied to the same
   `total_face * inforce_ratio - reserve_balance` aggregate NAR the
   flat path uses. Cession is the face-weighted scalar. This loses
   per-policy lx weighting but preserves cohort-level aging behaviour
   and is documented as a degraded path — Slice 3 may force seriatim
   for tabular runs at the CLI layer.

5. **Per-(sex, smoker) cohort split.** Inside `_compute_tabular_premiums`,
   the per-policy rate matrix is built once per (sex, smoker) cohort
   and per-month, mirroring the pattern in
   `TermLife._build_rate_arrays`. Ages outside the table range are
   `np.clip`ed to `[min_age, max_age]` so a long projection past the
   table top doesn't raise — the table top is the natural extrapolation
   cap for ultimate-age rates.

6. **Claims and reserves stay on the existing path.** Claims continue
   to be cession-proportional via `_resolve_cession`'s face-weighted
   scalar. Reserves still stay with the cedant (no transfer in YRT).
   Only the YRT premium calculation is touched.

7. **`YRTRateSchedule.generate_table(...)`** is added as a closed-loop
   sanity check: solve the existing per-(age, sex, smoker) flat rate
   for each grid cell, pack into a `YRTRateTable`, and verify that
   feeding the result back through `YRTTreaty.apply()` produces a
   well-formed CashFlowResult. This is an internal helper; Slice 3
   will add a real per-duration solver and the CSV ingest path.

**Rationale:**

- **Seriatim-first** is the actuarially correct path: a YRT rate at
  age 65 must be applied to the policies that actually reach age 65,
  not to a face-weighted average of all policies that started in the
  block. The aggregate-runoff approximation is a known limitation
  flagged in PRODUCT_DIRECTION_2026-04-19 and the whole point of this
  feature is to fix it.
- **Aggregate fallback exists only because** several places in the
  codebase (`YRTRateSchedule._solve_rate`, the demo CLI flow) call
  `engine.project()` without `seriatim=True` for performance, and we
  do not want a treaty re-quote there to fail loudly. The fallback is
  documented as degraded; Slice 3 will likely flip the CLI to use
  seriatim for tabular runs.
- **Mutual exclusion at construction time** is the safest way to enforce
  the PR #36 reviewer's guidance. A model_validator catches it once
  per treaty instance, not once per `apply()` call, and the error is
  raised before any pricing happens.
- **Face-weighted average rate in the fallback path** is a defensible
  simplification: the average rate is what an actuary would compute by
  hand for a quick aggregate quote without seriatim machinery, and it
  preserves additivity of net + ceded = gross with no special-casing.
- **Backward compatibility is non-negotiable.** Every existing
  flat-rate test and the QA goldens hit the same code path they did
  before — the new tabular branch is mutually exclusive with the flat
  branch and is only entered when `yrt_rate_table` is set.

**Out of scope:**

- CSV file format and `YRTRateTable.load(path)` classmethod (Slice 3).
- `polaris price --yrt-rate-table PATH` CLI flag (Slice 3).
- `api/main.py` `PriceRequest.yrt_rate_table_path` field (Slice 3).
- Excel deal-pricing workbook `YRT Rate Table` sheet (Slice 3).
- Dashboard heatmap of the loaded table (Slice 3).
- A true per-duration rate solver in `YRTRateSchedule.generate_table()`
  (the current implementation broadcasts the per-age flat rate across
  every duration column; a real per-duration solver is deferred).

**Tests:**

- `tests/test_reinsurance/test_yrt_tabular.py` (12 new tests):
  - `TestYRTTreatyValidation` (5) — both/table-only/flat-only/neither
    constructors; table-without-inforce raises
    `PolarisComputationError`.
  - `TestFlatPathUnchanged` (1) — flat-rate output is identical with
    and without an `inforce` argument.
  - `TestConstantTableMatchesFlat` (2) — constant-rate table reproduces
    the flat-rate path within `1e-6`; net + ceded = gross holds.
  - `TestAgingBlockRisesWithAge` (2) — aging table collects strictly
    more total ceded premium than a flat table at the same starting
    rate; implied per-$1,000 rate (back-solved from prem / NAR) rises
    monotonically across the first 10 policy years.
  - `TestSeriatimVsAggregateFallback` (1) — gross without seriatim
    uses the fallback path; output is finite and additivity holds.
  - `TestMultiPolicyMixedCohort` (1) — UNKNOWN-only YRT table is
    looked up correctly for a mixed (NS, S) male block via the smoker
    fallback.
- `tests/test_analytics/test_rate_schedule.py` (2 new tests under
  `TestGenerateTable`):
  - Returns a populated `YRTRateTable` with the expected min/max age
    and select-period.
  - Round-trip: a generated table fed into `YRTTreaty.apply()` produces
    finite, non-zero ceded premiums with no errors.

Total: 14 new tests; full suite is now 845 non-slow (up from 833); QA
suite unchanged; golden baselines unchanged (the flat-rate path is the
only one any existing pricing run takes — tabular consumption is
opt-in via the new field).

---

## ADR-052: Tabular YRT — CSV loader, CLI / API / Excel surfacing (Slice 3 of 3)

**Date:** 2026-04-29
**Status:** Accepted (Slice 3 of "YRT rate schedule by age × duration"
multi-session feature; depends on ADR-050 and ADR-051).

**Context:**

Slice 1 (ADR-050) added the standalone `YRTRateTable` data model.
Slice 2 (ADR-051) wired tabular consumption into `YRTTreaty.apply()`.
Both are reachable only programmatically: an actuarial user has no way
to feed a real (age × sex × smoker × duration) rate table to a
`polaris price` run, and the API has no field for it. This slice closes
the loop by adding a CSV ingest path, a CLI flag, an API field, and an
Excel sheet so a tabular YRT deal can be priced end-to-end without
writing Python.

**Decision:**

1. **CSV schema mirrors `load_mortality_csv`.** One file per
   (sex, smoker) cohort with header
   `age,dur_1,...,dur_N,ultimate`. The user-facing column index is
   1-based (`dur_1` is the first policy year, `ultimate` is the
   `select_period+1`-th and applies for any duration ≥ select_period);
   the internal `YRTRateTableArray` stores the rates in a 0-based
   `(n_ages, select_period+1)` array. This 1-based user / 0-based
   storage convention is identical to `load_mortality_csv` so the
   actuarial reader has only one mental model. Resolves CONTINUATION
   Open Question 3.

2. **`load_yrt_rate_csv` lives in `utils/table_io.py`** (the same
   module that hosts `load_mortality_csv` and `load_lapse_csv`). The
   module's docstring is extended with a `YRT RATE CSV SCHEMA`
   section so the three CSV formats are documented in one place.
   Crucially, the YRT loader does **not** apply the `[0, 1]` rate cap
   that `load_mortality_csv` enforces — YRT rates are dollars per
   $1,000 NAR, not probabilities, and routinely exceed `1.0` at
   advanced ages. The non-negative + finite checks are preserved
   (delegated to `YRTRateTableArray.__init__`).

3. **`YRTRateTable.load(directory, ...)` classmethod** mirrors
   `MortalityTable.load`. It iterates over the standard
   {(MALE/FEMALE) × (NS/SMOKER)} cohort grid (or {sex × UNKNOWN} when
   `smoker_distinct=False`), formats the filename via a
   `file_pattern` template (default `"{label}_{sex}_{smoker}.csv"`),
   and packs the result through `YRTRateTable.from_arrays(...)`.

4. **CLI: `polaris price --yrt-rate-table DIR`** plus three optional
   tuning flags — `--yrt-rate-table-select-period`,
   `--yrt-rate-table-label`, and the boolean
   `--yrt-rate-table-smoker-distinct/--yrt-rate-table-aggregate`.
   When `--yrt-rate-table` is set, the CLI:
   - Loads the table once before the cohort loop.
   - Forces `seriatim=True` on the gross projection (so
     `YRTTreaty._compute_tabular_premiums` takes the per-policy
     seriatim path rather than the face-weighted-average fallback).
   - Forces `inforce` to be passed to `YRTTreaty.apply()` (the
     tabular path requires it).
   - Constructs `YRTTreaty(yrt_rate_table=...)` directly, bypassing
     the generic `build_treaty` factory's flat-rate path.

5. **API: `PriceRequest.yrt_rate_table_path: str | None`** plus the
   same three tuning fields. The path is **server-side, relative to
   `$POLARIS_DATA_DIR`**; `_resolve_yrt_rate_table_path` enforces
   that the resolved path lives inside the data root (rejects
   `..` traversal with HTTP 400) and that the directory exists
   (HTTP 404 otherwise). This avoids letting an API client read
   arbitrary server paths via the loader.

6. **API per-policy cession is now `None` (was `0.0`).** The previous
   hard-coded `0.0` was harmless under the flat-rate path because
   `YRTTreaty.apply(gross)` was called without `inforce`, so
   `_resolve_cession` returned the treaty default unchanged. Under the
   tabular path the seriatim consumer always honours
   `effective_cession_vec`, which would multiply premiums by zero for
   every policy. Switching to `None` lets the policies fall through to
   the request-level `cession_pct` (the long-standing default
   behaviour for an API that does not carry per-policy overrides),
   which preserves the flat-path response byte-for-byte and makes the
   tabular path usable. All 38 existing API tests pass byte-identically.

7. **Excel: optional `YRT Rate Table` sheet** appended to the deal-
   pricing workbook when `DealPricingExport.yrt_rate_table` is
   populated. The sheet renders one block per (sex, smoker) cohort
   with the loaded `(age × duration)` grid in human-readable form.
   When no tabular table was supplied, the sheet is omitted and the
   workbook is byte-identical to pre-Slice-3.

8. **Out of scope for this slice:** the dashboard file-uploader /
   heatmap and `polaris rate-schedule --table` flag. Those surfaces
   are deferred to a follow-on slice (CONTINUATION updated). The
   data path, deal-pricing CLI, API, and committee Excel packet —
   the surfaces an actuary uses to price a deal — are all delivered
   here.

**Rationale:**

- **Data path before surfaces.** A working CSV loader and `load()`
  classmethod is the linchpin; everything else (CLI / API / Excel) is
  a thin shim above it. Building the loader first (with 26 dedicated
  tests) means the surfaces inherit a verified contract.
- **Mirroring mortality CSV** keeps the user's actuarial-CSV mental
  model coherent — the same filename pattern, the same header
  convention, the same (sex, smoker) cohort split. This was the
  default the CONTINUATION recorded for Open Question 3.
- **Path-traversal safety on the API** is non-negotiable for a
  server-side load. Resolving against `POLARIS_DATA_DIR` and
  asserting the resolved path is inside the data root catches the
  obvious attacks (`..`, absolute paths) while still letting
  legitimate requests reference a relative subdirectory.
- **Forcing seriatim on tabular runs** at the CLI boundary
  resolves the ADR-051 caveat: the CLI demo flow now lands on the
  per-policy lx-weighted seriatim path automatically, so the
  PRODUCT_DIRECTION_2026-04-19 declining-premium concern is fully
  fixed end-to-end with no actuarial intervention.
- **Defaulting per-policy cession to `None` on the API** is the
  cleanest fix for the longstanding `0.0` quirk. The flat-rate path
  never observed it because `apply(gross)` was called without
  `inforce`; the tabular path observes it always. Setting `None`
  makes both paths behave identically — the request-level
  `cession_pct` is the single source of truth.
- **Optional Excel sheet rather than always-on** preserves the
  ADR-045 four-sheet workbook for legacy flat-rate runs and keeps
  the workbook size proportional to the deal complexity.

**Out of scope (deferred to a follow-on slice):**

- `polaris rate-schedule --table` flag for emitting a tabular
  schedule via `YRTRateSchedule.generate_table(...)`.
- Streamlit dashboard file-uploader for the rate-table directory
  and a heatmap preview of the loaded grid.
- A true per-duration solver in `YRTRateSchedule.generate_table()`
  (currently broadcasts the per-age flat rate across every duration
  column — see ADR-051's "Out of scope").

**Tests:**

- `tests/test_utils/test_yrt_rate_csv.py` (26 new tests):
  - `TestLoadYRTRateCSV` (15) — schema parsing, age filtering,
    economic invariants (smoker > NS, male > female), missing
    column detection, negative-rate rejection, age-gap rejection,
    rates >> 1 acceptance.
  - `TestYRTRateTableLoad` (9) — directory loading (smoker-distinct
    and aggregate-only), label override, default slug, smoker
    fallback after load, missing-CSV fail-fast, inconsistent-age-
    range detection, end-to-end round-trip through `YRTTreaty.apply()`.
  - `TestPublicExports` (2) — `__all__` re-export, polars round-trip.
- `tests/test_analytics/test_cli_yrt_rate_table.py` (7 new tests):
  - Demo runs with `--yrt-rate-table`, missing-dir fail-fast, label
    override, aggregate mode, seriatim implication, no-flag
    backward compat, non-zero ceded premium with custom inforce.
- `tests/test_api/test_yrt_rate_table.py` (7 new tests):
  - Tabular path returns 200 with non-zero reinsurer pv_profits,
    field default is None, path-traversal rejection,
    missing-directory error, missing-`POLARIS_DATA_DIR` error,
    aggregate mode via API, select-period validation.
- `tests/test_utils/test_excel_output.py::TestYRTRateTableSheet`
  (4 new tests): sheet absent without table, sheet present with
  table, table name + cohort labels rendered, known rate value
  appears in cells.

Total: 44 new tests (26 loader + 7 CLI + 7 API + 4 Excel). Full
suite is now 892 non-slow (up from 848); QA suite unchanged at
33/33; golden baselines unchanged because all of the new code is
opt-in via the new field/flag.

---

## ADR-053: `polaris rate-schedule --table` flag and standalone Excel writer (YRT Slice 4a)

**Date:** 2026-04-30
**Status:** Accepted
**Slice:** 4a of the YRT rate-table feature (split off from the
original Slice 4 which also bundled the dashboard upload + heatmap;
the dashboard work is deferred to Slice 4b so the present surface is
independently mergeable). See `CONTINUATION_yrt_rate_table.md`.

**Context:**

ADR-052 (Slice 3) added the CSV loader and CLI / API / Excel
*consumption* surfaces for tabular YRT rates. The corresponding
*production* surface — generating a tabular schedule from the
existing `YRTRateSchedule` solver — was deferred. Without it, an
actuary using Polaris cannot produce a deliverable rate-table
workbook directly from the CLI; they must call
`YRTRateSchedule.generate_table(...)` from Python and serialise the
result by hand. The CLI already exposes `polaris rate-schedule`
which solves a flat per-(age, sex, smoker) schedule and writes
CSV / Excel / JSON; the natural extension is a `--table` flag that
flips the solver call from `generate(...)` to `generate_table(...)`
and the output writer from `write_rate_schedule_excel` to a new
`write_yrt_rate_table_excel`.

**Decision:**

1. **`polaris rate-schedule --table/--no-table`** flag (default
   `False`). When set, the command calls
   `YRTRateSchedule.generate_table(...)` instead of `generate(...)`
   and renders the resulting `YRTRateTable` instead of the flat
   DataFrame. A companion `--select-period N` option (default `0`)
   controls the number of select columns in the generated table;
   `N=0` produces a single ultimate column.
2. **Output format constraints under `--table`:**
   - `-o NAME.xlsx` writes a workbook via the new
     `write_yrt_rate_table_excel` (Summary sheet + the shared
     `YRT Rate Table` sheet from ADR-052).
   - `-o NAME.csv` is rejected with exit code 1 because CSV does
     not preserve the cohort-keyed 2-D layout. The user-facing
     message points to the `.xlsx` re-run.
   - `--json PATH` emits a structured dict with `table_name`,
     `min_age`, `max_age`, `select_period_years`, and a `cohorts`
     map keyed by `f"{sex}_{smoker}"` carrying per-cohort
     `min_age` / `max_age` / `select_period` / `rates` (nested
     list, JSON-friendly via `arr.rates.tolist()`).
3. **`write_yrt_rate_table_excel(table, path)`** is a new public
   function in `src/polaris_re/utils/excel_output.py`. Internally
   it delegates the rate-grid block to the existing
   `_write_yrt_rate_table_sheet` helper so the layout is byte-
   identical to the deal-pricing workbook's appended sheet (one
   block per (sex, smoker) cohort, headers `Age | dur_1 ... dur_N |
   ultimate`). A `Summary` sheet is added in front carrying the
   table name, age range, select-period, cohort count, and total
   rate-cell count.
4. **Console rendering** when `--table` is set: one Rich `Table`
   per cohort, sorted by cohort key for deterministic output.
   Rows are `[age, dur_1, ..., dur_N, ultimate]` with rates
   formatted as `{:.4f}`.
5. **Backward compatibility:** the existing `--no-table` path is
   byte-identical to the pre-Slice-4a behaviour. None of the
   existing flags' semantics or defaults change. The new flags
   default to `False` / `0`.

**Why these choices:**

- **`generate_table` already exists (ADR-051) and emits a
  `YRTRateTable` directly.** The CLI flag is a thin orchestration
  layer on top — no new actuarial logic is added in this slice. The
  per-duration solver remains future work (called out in ADR-051's
  "Out of scope").
- **Reusing `_write_yrt_rate_table_sheet`** ensures the standalone
  workbook produced by `polaris rate-schedule --table` is visually
  consistent with the appended sheet in the deal-pricing workbook
  produced by `polaris price --excel-out` (ADR-052). One layout to
  learn, one regression to maintain.
- **Rejecting `-o NAME.csv` under `--table`** is a deliberate
  fail-fast. The actuarial reader expects the (age, duration) grid
  to round-trip back through `YRTRateTable.load(...)` (ADR-052),
  which requires the per-cohort filename convention; a single CSV
  cannot carry the cohort keying without inventing a new schema.
  Excel and JSON together cover both deliverable use cases.
- **JSON serialisation via nested list** (not a flattened DataFrame)
  matches the on-disk `YRTRateTable` structure and lets a
  downstream consumer reconstruct the table via
  `YRTRateTable.from_arrays(...)` after rebuilding `YRTRateTableArray`
  objects from the cohorts dict. This keeps the JSON format
  parallel to the in-memory model rather than the flat-schedule
  DataFrame.
- **No new actuarial defaults.** The grid axis defaults (ages,
  policy_term, target_irr) come from the existing CLI options.
  The only new defaults are `--table=False` and `--select-period=0`,
  both of which preserve pre-Slice-4a behaviour.

**Out of scope (deferred to Slice 4b):**

- Streamlit dashboard file-uploader for the rate-table directory
  (or zip), matplotlib heatmap preview per cohort, and wiring
  through to the Pricing page.
- A true per-duration solver in `YRTRateSchedule.generate_table()`
  (currently broadcasts the per-age flat rate across every
  duration column — ADR-051 "Out of scope"). The Slice 4b heatmap
  will be visually flat-along-rows until this lands, which is an
  acceptable interim signal.
- **`generate_table()` fill-in transparency disclosure.** The current
  implementation expands any sparse age grid to a contiguous
  `[min_age, max_age]` array and silently forward/back-fills unsolved
  rows. Console and Excel output render filled rows identically to
  solved rows. ADR-054 will pick between (a) marking filled rows
  visually and (b) restricting the table range to only requested ages;
  neither approach requires changes to `YRTRateTableArray`'s storage
  contract or `YRTTreaty.apply()`'s consumption logic. Raised in PR
  #39 review (Comment 4) — the current behaviour must not be
  presented as a production deliverable without disclosure.

**Tests:**

- `tests/test_utils/test_excel_output.py::TestWriteYrtRateTableExcel`
  (new) — workbook is created, has both `Summary` and `YRT Rate
  Table` sheets, the Summary sheet carries the cohort count and
  table name, the YRT Rate Table sheet carries the expected rate
  values per the existing `_write_yrt_rate_table_sheet` contract.
- `tests/test_analytics/test_cli_rate_schedule_table.py` (new,
  `@pytest.mark.slow`) — `polaris rate-schedule --table -o
  out.xlsx` produces a workbook openable via
  `YRTRateTable`-shaped inspection; `--json` emits the expected
  cohorts dict shape; `-o NAME.csv` with `--table` exits 1; the
  existing `--no-table` flat path still writes a CSV.
- `tests/test_analytics/test_rate_schedule.py::TestYrtRateTableJsonHelper`
  (new) — `_yrt_rate_table_to_dict` is a pure function on
  `YRTRateTable` and is unit-tested without the CLI.

**Backward compatibility:**

`polaris rate-schedule` invoked without `--table` produces the
exact same console output, CSV/Excel/JSON files, and exit codes as
before. All eight pre-existing `TestYRTRateSchedule` /
`TestExcelOutput` / `TestGenerateTable` tests remain green
unchanged. Golden regression baselines are unaffected (rate-schedule
is not part of the golden flat / YRT pricing harness).


---

## ADR-054: Disclosure of forward/back-filled cells in `generate_table()` (YRT Slice 4b-1)

**Status:** Accepted (2026-05-01)

**Context:**

`YRTRateSchedule.generate_table(...)` (introduced in ADR-051,
surfaced in ADR-053) takes a sparse list of ages and produces a
`YRTRateTable` whose `YRTRateTableArray` storage is contiguous from
`min(ages)` to `max(ages)`. The brentq solver only runs at the
explicitly requested ages; the intermediate rows are silently
forward/back-filled from the nearest solved row to satisfy the
contiguous-storage contract.

This was flagged in PR #39 (Slice 4a) review as a deliverable
blocker: the CLI / Excel / JSON renderers display filled rows
identically to solved rows. On the example
`polaris rate-schedule --table --ages 30,40 --select-period 3`,
ages 31..39 all display the same rate (forward-filled from age
30), and a reviewer cannot tell which rates are authoritative.
ADR-053 explicitly listed this as out of scope for Slice 4a.

**Two candidate fixes were considered (per CONTINUATION):**

A. **Mark filled rows visually** in console / Excel / JSON output.
   Storage shape stays contiguous; consumers (`YRTTreaty.apply`)
   stay unchanged. Renderers gain a per-cell solver-provenance
   signal.

B. **Restrict the generated table to only requested ages** —
   either by storing a sparse table or by making the consumer
   responsible for clamping to the table's effective age range.
   This would change the `YRTRateTable` storage contract and
   require corresponding changes in `YRTTreaty.apply` and any
   future loaders.

**Decision: Option A — visual disclosure via an optional
`solved_mask`.**

- Added an optional `solved_mask: np.ndarray | None = None` field
  to `YRTRateTableArray`. The mask is a boolean array of the same
  shape as `rates`; True = the cell came from a successful brentq
  solve at a requested age, False = the cell was forward/back-filled.
- Default `None` means "no provenance recorded — every cell is
  authoritative." This matches the CSV-loaded path
  (`YRTRateTable.load`) and any in-memory table built by callers
  who supply a complete grid. Renderers fall back to the
  pre-ADR-054 behaviour when the mask is absent.
- `YRTRateSchedule.generate_table()` now constructs the mask
  alongside the rates matrix, marking only the brentq-solved cells
  True.
- CLI `_render_yrt_rate_table()` appends `*` to the formatted rate
  string for any False cell and prints a footer caption per cohort
  when at least one cell is filled:
  `* = forward/back-filled from a solved row (age was not directly solved; ADR-054).`
- CLI `_yrt_rate_table_to_dict()` includes a `solved_mask`
  (`list[list[bool]]`) per cohort when the field is set; CSV-loaded
  tables omit the field entirely so machine consumers can detect
  the difference.
- Excel `_write_yrt_rate_table_sheet()` styles filled cells with
  italic + grey font (`#666666`) and a `#EEEEEE` `PatternFill`. A
  note row is inserted under the title when any cohort has filled
  cells:
  `Italic / grey-filled cells were forward/back-filled from a solved row (age not directly solved; ADR-054).`
- Excel `write_yrt_rate_table_excel()` Summary sheet adds
  `Solved cells: N` / `Filled cells: M` rows plus an explanatory
  italic note when any cohort carries a `solved_mask`. The four
  pre-existing Summary rows (table name, age range, select period,
  cohort count, total cells) are unchanged.

**Why Option A over B:**

1. **Backward compatibility.** Storage contract on `YRTRateTable`
   is unchanged — Slice 2's `YRTTreaty.apply()` consumption logic
   does not branch on solver provenance and never sees the mask.
   CSV-loaded tables (mask `None`) render byte-identically to
   pre-ADR-054 output.
2. **Minimum blast radius.** Loaders, the API surface, the
   dashboard, and the deal-pricing Excel sheet all keep their
   existing behaviour. Only the generator and three renderers
   change.
3. **More information surfaced.** Users who request a sparse age
   grid still get a contiguous output (useful for downstream
   consumption by `YRTTreaty.apply`'s clamping path) and can now
   distinguish the solved bookends from the interpolated middle.
4. **Option B's discoverability cost.** Restricting the table to
   only requested ages would either require sparse storage (a new
   contract) or would silently drop intermediate ages in lookups,
   shifting the disclosure problem to the consumer side without
   removing it.

**Acceptance criteria:**

- `polaris rate-schedule --table --ages 30,40 --json out.json`
  produces a JSON `cohorts.M_U.solved_mask` with True at indices 0
  and 10 and False at indices 1..9. ✅
- `_render_yrt_rate_table` prints `1.5000*` (with the trailing
  asterisk) for filled cells and `1.0000` (no asterisk) for solved
  cells. ✅
- `_render_yrt_rate_table` prints the disclosure caption once per
  cohort when any cell is filled, and never when all cells are
  solved. ✅
- `_write_yrt_rate_table_sheet` styles filled cells with italic
  font + `#EEEEEE` `PatternFill`; the note row at row 3 explains
  the convention. ✅
- `write_yrt_rate_table_excel` Summary sheet records the solved
  and filled cell counts when a mask is present. ✅
- CSV-loaded tables (`YRTRateTable.load(...)`, mask `None`) render
  exactly as pre-ADR-054 output: no asterisks, no caption, no
  italic styling, no NOTE row, no Summary count rows. ✅
- `YRTRateTableArray` defensive-copies the supplied mask; mutation
  of the caller's reference does not bypass storage. ✅

**Out of scope (deferred to Slice 4b-2):**

- Streamlit dashboard file-uploader for a tabular YRT rate file
  / zip / multi-cohort CSV (ADR-052 left this open).
- Heatmap preview per cohort in the dashboard.
- True per-duration solver in
  `YRTRateSchedule.generate_table()` (currently broadcasts the
  per-age flat rate across every duration column —
  ADR-051 / ADR-053 "Out of scope"). When the per-duration solver
  lands, the per-cell `solved_mask` will become genuinely 2-D
  (rather than uniform-along-rows) and the visual disclosure will
  immediately surface that finer-grained provenance with no
  additional work in renderers.
- Loader-side provenance for CSV-imported tables. CSV cells are
  always treated as authoritative; if a cedant supplies a sparse
  CSV with explicit fill-in markers in the future, that needs a
  new ADR.

**Tests:**

- `tests/test_reinsurance/test_yrt_rate_table.py::TestYRTRateTableArraySolvedMask`
  (6 new) — default-None construction, round-trip, all-True is
  fully solved, shape mismatch raises, integer dtype coerced to
  bool, defensive copy on caller mutation.
- `tests/test_analytics/test_rate_schedule.py::TestGenerateTableSolvedMask`
  (3 new) — dense grid is fully solved, sparse grid marks
  intermediate rows False, mask broadcasts uniformly across
  select-period columns (matches the per-row broadcast contract
  from ADR-051 / ADR-053).
- `tests/test_analytics/test_cli_rate_schedule_table.py::TestSolvedMaskDisclosure`
  (5 new) — render emits `*` and caption for filled cells, render
  is unchanged when mask is None, JSON includes / omits
  `solved_mask` per provenance, JSON is `json.dumps`-clean.
- `tests/test_analytics/test_cli_rate_schedule_table.py::TestSolvedMaskCLIIntegration`
  (1 new, `@pytest.mark.slow`) — end-to-end
  `polaris rate-schedule --table --ages 30,40 --json` writes a
  JSON `solved_mask` with True at the bookends and False between.
- `tests/test_utils/test_excel_output.py::TestSolvedMaskDisclosureExcel`
  (5 new) — italic font on filled cells, `#EEEEEE` fill on filled
  cells, note row at row 3 contains the disclosure text, Summary
  records solved/filled counts, no-mask path is byte-identical
  (no NOTE row, no italic, no fill, no Summary count rows).

**Backward compatibility:**

`YRTRateTableArray` constructed without `solved_mask` is
indistinguishable from a pre-ADR-054 instance: `solved_mask` is
`None`, `is_fully_solved` is True, all renderers fall back to the
pre-ADR-054 visual layout. CSV-loaded `YRTRateTable.load(...)`
results carry no mask. The deal-pricing Excel workbook (ADR-052
`_write_yrt_rate_table_sheet` consumer) is byte-identical when the
attached `yrt_rate_table` has no mask. The pre-existing
`TestYRTRateSchedule` / `TestExcelOutput` / `TestGenerateTable` /
`TestYRTRateTableSheet` / `TestWriteYrtRateTableExcel` /
`TestRateScheduleTableCLI` / `TestYrtRateTableJsonHelper` /
`TestHelperTypeGuards` test suites all remain green unchanged.
Golden regression baselines are unaffected (rate-schedule is not
part of the golden flat / YRT pricing harness).

---

## ADR-055: Streamlit upload UX for the tabular YRT rate schedule (YRT Slice 4b-2)

**Status:** Accepted (2026-05-02)

**Context:**

ADR-052 locked the on-disk YRT rate CSV layout at `age,dur_1,...,dur_N,
ultimate` per `(sex, smoker)` cohort and shipped `YRTRateTable.load(directory,
...)` for the CLI / API surfaces. The dashboard cannot accept a directory
through `st.file_uploader` — the widget yields one or more `UploadedFile`
objects backed by browser memory — so the tabular YRT path was unreachable
from Streamlit. The CONTINUATION_yrt_rate_table.md plan listed three
candidate UX patterns:

(a) **Zip upload.** Single `.zip` containing per-cohort CSVs, unzipped
    in-process. Familiar pattern for "directory upload" but adds a binary
    handling layer (and a temp-file lifecycle / archive-traversal
    surface) that does not exist on the CLI path.
(b) **Multi-file selector.** `st.file_uploader(accept_multiple_files=True)`
    accepts 1-4 CSVs. Filename suffix (`_{sex}_{smoker}.csv`) binds each
    file to its cohort key, mirroring the on-disk filename convention
    `YRTRateTable.load` already enforces (ADR-052).
(c) **Single multi-cohort CSV.** New schema with `sex` / `smoker` columns
    in the row dimension. Requires a new loader and breaks parity with
    the on-disk format the CLI / API consume.

**Decision:**

Adopt **option (b) — multi-file selector — and reuse the ADR-052 filename
convention as the cohort-binding mechanism.** The dashboard upload helper
delegates to a new buffer-based loader (`load_yrt_rate_csv_from_buffer` in
`utils/table_io.py`, refactored from the path-based `load_yrt_rate_csv` so
both paths share `_parse_yrt_rate_df`) and packs the result into a
`YRTRateTable` via `YRTRateTable.from_arrays`.

This keeps **CLI ↔ dashboard parity at the file level**: a tester can
prepare four CSVs once and consume them from either surface with no
conversion. It also avoids a bespoke zip-handling code path, an additional
multi-cohort schema, and the validation surprises that surround both.

**Consequences (Implementation):**

`src/polaris_re/utils/table_io.py`

- Extract `_parse_yrt_rate_df(df, source_name, select_period, ...)` from
  `load_yrt_rate_csv`. The existing path-based loader becomes a thin
  wrapper that reads via `pl.read_csv(path)` then delegates.
- Add `load_yrt_rate_csv_from_buffer(content: bytes, source_name: str, ...)`
  for the in-memory upload path. Validation behaviour is identical to
  `load_yrt_rate_csv`; `source_name` carries the uploaded filename into
  any error message so the user can map an error back to the file they
  uploaded.

`src/polaris_re/utils/yrt_rate_table_io.py` (new)

- `parse_yrt_rate_filename(filename) -> (Sex, SmokerStatus)`. Strips
  directory components (POSIX and Windows separators), lowercases, and
  decodes the trailing `_{sex}_{smoker}.csv`. `sex` ∈ `male` / `female`;
  `smoker` ∈ `smoker` / `ns` / `unknown`. Anything else raises
  `PolarisValidationError` with a message naming the offending suffix.
- `parse_uploaded_yrt_rate_table(uploads, table_name, select_period,
  min_age=None, max_age=None) -> YRTRateTable`. Iterates `(filename,
  content_bytes)` tuples, parses each filename for the cohort key, calls
  `load_yrt_rate_csv_from_buffer` for the array, then packs everything
  into `YRTRateTable.from_arrays`. Duplicate cohorts raise
  `PolarisValidationError`; per-CSV validation errors propagate verbatim.

`src/polaris_re/dashboard/components/yrt_rate_table.py` (new)

- `yrt_rate_table_heatmap_per_cohort(table) -> [(cohort_key, Figure)]`.
  Renders one matplotlib heatmap per cohort (sorted by key) using
  `imshow(viridis)` with a colour-bar in `$/$1,000 NAR / year`. Cells
  flagged as forward/back-filled by `solved_mask` (ADR-054) get a
  hatched white-edge `Rectangle` overlay; CSV-loaded uploads carry no
  mask and render without the overlay. Title appends a "✧ =
  forward/back-filled" marker only when at least one cell is filled.
- Returned figures are not closed by the helper — callers
  (`views/assumptions.py`) iterate, `st.pyplot(fig)`, then `plt.close`.

`src/polaris_re/dashboard/components/projection.py`

- `build_treaty(...)` gains a `yrt_rate_table: object | None = None` kwarg.
  When `treaty_type == "YRT"` and the kwarg is set, the dashboard
  constructs `YRTTreaty(... yrt_rate_table=...)` directly (the shared
  `core.pipeline.build_treaty` factory does not yet accept the kwarg —
  matching the CLI's tabular-bypass pattern in `cli.py:price`). A type
  guard rejects non-`YRTRateTable` arguments at the boundary.
- `run_gross_projection(...)` gains a `seriatim: bool = False` kwarg
  forwarded to `BaseProduct.project(seriatim=...)`. Required by the
  tabular YRT consumer (ADR-051).
- `run_treaty_projection(...)` gains a `yrt_rate_table` kwarg and reads
  `cfg["yrt_rate_table"]` as a fallback. When set, the function bypasses
  the flat-rate derivation, builds a tabular `YRTTreaty`, and calls
  `treaty.apply(gross, inforce=inforce)` — the inforce block is always
  passed in this branch because the tabular path requires it.

`src/polaris_re/dashboard/views/assumptions.py`

- `_treaty_section()` adds a third "YRT Rate Basis" option,
  `Tabular Schedule`, alongside `Mortality-based` and `Manual Rate`.
  Selecting it renders the `_yrt_rate_table_uploader` helper, which
  packs uploads via `parse_uploaded_yrt_rate_table` and previews the
  loaded grid with `yrt_rate_table_heatmap_per_cohort`. The treaty
  param dict gains a `yrt_rate_table` key persisted onto
  `deal_config["yrt_rate_table"]` when the user clicks
  "Save All Assumptions".

`src/polaris_re/dashboard/views/pricing.py`

- `_run_pricing_for_cohort(...)` reads `cfg["yrt_rate_table"]` (when
  `treaty_type == "YRT"`) and forwards it to both `run_gross_projection`
  (with `seriatim=True`) and `run_treaty_projection`. The "derived YRT
  rate" `st.info` panel is suppressed when a tabular schedule is loaded
  (the rate is per-cell and a single derived figure would be
  misleading); a parallel `st.info` reports the loaded table's cohort
  count, age range, and select period.

**Consequences (Tests):**

- `tests/test_utils/test_yrt_rate_table_io.py` (26 new):
  - `TestLoadYRTRateCSVFromBuffer` (6) — round-trip parity with the
    path loader, byte-level error handling, schema validation, negative
    rates rejected via the array `__init__`, `select_period` floor.
  - `TestParseYRTRateFilename` (12) — six suffix recognitions
    (parametrised), POSIX/Windows path stripping, multi-token labels,
    rejection of non-CSV / unrecognised sex / unrecognised smoker /
    too-few-tokens cases.
  - `TestParseUploadedYRTRateTable` (8) — four-cohort smoker-distinct
    pack, full directory-loader round-trip, two-cohort aggregate-only
    pack, empty-uploads / duplicate-cohort / inconsistent-age-range /
    propagated per-file validation errors.
- `tests/test_dashboard/test_yrt_rate_table_components.py` (8 new):
  - `TestHeatmapRenderer` (4) — one figure per cohort, deterministic
    sort order, axis labels, "forward/back-filled" title marker
    omitted when fully solved and present when the mask flags any cell.
  - `TestBuildTreatyTabular` (4) — YRT + table → `YRTTreaty` with the
    table attached and no flat rate, YRT without table falls back to
    pipeline factory, non-YRT silently drops the kwarg, non-table type
    rejected at the boundary.
- `tests/test_dashboard/test_pricing_with_table.py` (5 new):
  - Tabular dispatch returns non-zero ceded premium and 50%-of-gross
    ceded claims.
  - Constant-rate uploaded table reproduces the flat-rate ceded series
    within `rtol=1e-6, atol=1e-3`.
  - `cfg["yrt_rate_table"]` fallback path runs when the kwarg is omitted.
  - `run_gross_projection(seriatim=True)` populates `seriatim_lx` /
    `seriatim_reserves`; default `seriatim=False` does not.
- `tests/qa/test_dashboard_flows.py::TestTabularYRTUpload` (2 new):
  - YRT Rate Basis selector exposes the new `Tabular Schedule` option.
  - Injecting a `YRTRateTable` into `deal_config["yrt_rate_table"]`
    drives the tabular pricing branch end-to-end through the Streamlit
    `AppTest` harness.

**Backward compatibility:**

- The pricing flow defaults to `cfg.get("yrt_rate_table") = None`, so the
  flat-rate pricing path is byte-identical for users who never select
  "Tabular Schedule".
- `DealConfig` dataclass intentionally unchanged. The `yrt_rate_table`
  key lives only in the dashboard session-state dict; the CLI route
  continues to load tables via `--yrt-rate-table DIR` and the API via
  `yrt_rate_table_path` (ADR-052). Adding the field to `DealConfig`
  was deliberately deferred — neither the CLI nor the API has a
  natural way to round-trip a `YRTRateTable` through a JSON config.
- `utils/__init__.py` does NOT re-export `parse_uploaded_yrt_rate_table`
  / `parse_yrt_rate_filename` because the new module imports
  `YRTRateTable` from `polaris_re.reinsurance`, which would create a
  circular import via `utils.table_io.MortalityTableArray` if loaded as
  the very first `polaris_re.utils` symbol. Callers import directly:
  `from polaris_re.utils.yrt_rate_table_io import ...`. Documented in
  the `utils/__init__.py` NOTE block.
- All 909 pre-existing non-slow tests continue to pass; QA suite and
  golden regressions are unaffected (the tabular branch is opt-in and
  the flat-path code is untouched).

**Out of scope (deferred to a future slice):**

- **Per-duration solver in `YRTRateSchedule.generate_table()`.** The
  generator still broadcasts a per-(age, sex, smoker) flat rate across
  every duration column (ADR-051 / ADR-053). When the per-duration
  solver lands, the per-cell `solved_mask` (ADR-054) becomes genuinely
  2-D and the dashboard heatmap surfaces the finer provenance with no
  changes here.
- **In-dashboard generation of a tabular table.** Users who want a
  generated table run `polaris rate-schedule --table -o out.xlsx`
  on the CLI and upload the workbook elsewhere. A "Generate" button on
  the dashboard would duplicate the CLI's solver wiring without adding
  capability.
- **Persisting uploaded tables to disk** (e.g. saving the upload to
  `POLARIS_DATA_DIR` for later re-use). Out of scope; the upload lives
  in session state for the duration of the browser session only.

---

## ADR-056: Experience Study (A/E) dashboard page

**Status:** Accepted
**Date:** 2026-05-09

**Context.** `polaris_re.analytics.experience_study.ExperienceStudy` ships
the full A/E + credibility-weighting computation but had no Streamlit
surface. PRODUCT_DIRECTION_2026-04-19 lists "A/E dashboard page" as a
NICE-TO-HAVE deliverable: *experience_study.py exists but has no Streamlit
view*. Cedant assumption-review and reinsurer post-deal monitoring both
need a self-serve A/E surface; falling back to ad-hoc Polars in a
notebook is not a credible deliverable.

**Decision.** Add `dashboard/views/experience_study.py` with a single
`page_experience_study()` entry-point. The page is a thin
presentation layer over `ExperienceStudy`: input is either an uploaded
CSV (schema `actual,expected,exposure[+optional dimensions]`) or a
built-in sample data block; output is the credibility-adjusted summary
table plus two matplotlib charts (raw A/E by group; raw vs
credibility-adjusted multiplier). All math runs through
`ExperienceStudy.run()` and `AEResult.credibility_adjusted_multipliers()`
— no calculations are duplicated in the view.

**Key choices:**

- **CSV-as-input rather than session-state coupling.** Other dashboard
  pages depend on `inforce_block` / `assumption_set` being populated
  upstream. Experience study analyses *observed* data — the user's
  source of truth is a study extract, not the projected block — so the
  page accepts an upload directly. Coupling it to the inforce block
  would force users to load synthetic data they don't actually intend
  to study.
- **Sample-data fallback.** A built-in 8-row mortality dataset (age × sex)
  is shipped so the page is exercisable without an upload. This is the
  same pattern the YRT rate-schedule heatmap uses (heatmap renders
  immediately for the demo path), and it lets `AppTest`-driven QA
  flow tests cover the page end-to-end without filesystem fixtures.
- **`REQUIRED_COLUMNS` constant mirrors the engine.** The view re-asserts
  the engine's `ExperienceStudy.REQUIRED_COLUMNS` set so the user sees
  a clear missing-column message before the engine raises. A test
  pins the two sets to be equal so they cannot drift.
- **Optional age-banding via `ExperienceStudy.add_age_bands`.** When the
  uploaded CSV has an `age` column, an expander offers a checkbox that
  triggers `add_age_bands(...)` and adds `age_band` to the grouping
  dimensions. This is the same helper the test suite uses.
- **Group-by is multiselect, not selectbox.** Users can drill down by
  any combination of dimensions present in the uploaded CSV.
- **Chart suppression at >50 group rows.** The bar chart is the wrong
  visualisation for very high-cardinality groupings; in that regime the
  page suppresses the chart and points the user at the table / CSV
  download.

**Consequences:**

- New module: `src/polaris_re/dashboard/views/experience_study.py`
  (~225 lines). No engine code changes.
- `dashboard/app.py` gains an "Experience Study" radio option (page 8)
  and a corresponding dispatch branch.
- `dashboard/views/__init__.py` `__all__` extended with
  `"experience_study"` (alphabetised).
- New tests: 12 unit tests in
  `tests/test_dashboard/test_experience_study_view.py` covering the
  pure helpers (`_sample_data`, `_read_uploaded_csv`, `_ae_bar_chart`,
  `REQUIRED_COLUMNS` engine-parity, sample-data engine round-trip,
  upload→engine round-trip), and 3 AppTest end-to-end tests in
  `tests/qa/test_dashboard_flows.py::TestExperienceStudyPage`. The
  existing `TestPageNavigation::test_page_renders` parametrize is
  extended with `"Experience Study"` so the new page is covered by
  the bulk navigation smoke test.
- All 958 pre-existing non-slow tests continue to pass; the QA suite
  gains 4 tests; the analytics / engine layers and golden baselines
  are unchanged (purely additive presentation layer).

**Out of scope (deferred):**

- **Pulling actuals from a live data warehouse.** The page reads CSV
  bytes only; integration with cedant data feeds is a separate concern.
- **Time-series A/E (year-over-year tracking).** The current page is a
  single-snapshot study. Multi-period trending would warrant its own
  view.
- **Persisting study results to the deal-pricing Excel workbook.** A/E
  output stays as a downloadable CSV from the page; the deal Excel
  template (ADR-045) is unchanged.
- **Direct integration with the assumption calibration pipeline.** The
  page produces credibility-adjusted multipliers but does not
  automatically feed them back into a `MortalityTable` override —
  that workflow remains the analyst's responsibility.

---

## ADR-057: Portfolio aggregation — multi-deal runner (Milestone 5.2, Slice 1)

**Status:** Accepted
**Date:** 2026-05-20

**Context.** The engine prices one treaty at a time: `polaris price`
and the dashboard each run a single inforce block under a single
treaty. PRODUCT_DIRECTION_2026-04-19 lists "Portfolio aggregation
(multi-deal runner)" as an IMPORTANT gap — *reinsurers don't price a
single treaty in isolation; they need concentration metrics,
cross-deal diversification, and aggregate RoC*. Roadmap Milestone 5.2
specifies an `analytics/portfolio.py` `Portfolio` class that holds a
list of deals, aggregates their `CashFlowResult`s, and reports
portfolio-level profitability and concentration. This ADR covers
Slice 1 — the core analytics module. CLI / API surfacing is Slice 2
(see `docs/CONTINUATION_portfolio_aggregation.md`).

**Decision.** Add `analytics/portfolio.py` with a `Portfolio` builder
(`add_deal` → chainable), a `Deal` record, and `run(hurdle_rate)`
returning a `PortfolioResult`. Each deal is projected independently via
`get_product_engine`, its treaty is applied, and the *ceded* cash flow
— the reinsurer's assumed position — is re-viewed as NET (via the
canonical `ceded_to_reinsurer_view`, ADR-039) and profit-tested. The
portfolio aggregate is the month-by-month sum of the per-deal reinsurer
cash flows; total profitability is a single `ProfitTester` run on that
aggregate, so it inherits the ADR-041 reporting guardrails.

**Key choices:**

- **Portfolio = the reinsurer's assumed book.** A portfolio aggregates
  the *ceded* side of each deal. Concentration is grouped by **cedant**
  (the ceding company), confirming the reinsurer-side framing.
- **Proportional treaties only (this slice).** `add_deal` requires the
  treaty to expose a `cession_pct` (YRT / coinsurance / modco).
  Stop-loss and other non-proportional structures are rejected with a
  clear error — `ceded_face` would not be a single proportional figure.
- **Treaty-level cession governs; policy-level overrides are not
  applied.** `treaty.apply(gross)` is called without an `InforceBlock`,
  so `ceded_face = cession_pct × face` stays exact and consistent with
  the aggregated cash flows. Per-policy `reinsurance_cession_pct`
  blending (ADR-036) is deliberately out of scope for the portfolio
  runner.
- **Single-product deals.** Each deal's inforce block must contain
  exactly one product type (validated in `add_deal`). A mixed cedant
  block is modelled as one deal per product — the treaty applies per
  block, and `get_product_engine` dispatches on a homogeneous block.
- **Zero-pad to the longest horizon.** Deals may have different
  projection horizons; shorter streams are zero-padded at the tail.
  Cash-flow aggregation and PV both remain exactly linear, so
  `total_pv_profits` equals the sum of the per-deal PV profits.
- **Common valuation date enforced.** Aggregation sums cash flows by
  month index, so month 0 must be the same calendar month for every
  deal. `run()` rejects a portfolio whose deals do not share a
  `valuation_date` rather than silently producing an out-of-phase
  aggregate. Calendar-aligned aggregation (treaties with different
  inception dates) is a deferred follow-up (PR #44 review).
- **Concentration = face shares + Herfindahl index.** Each dimension
  (cedant / product / treaty) yields a label→share dict (shares of
  total ceded face) plus an HHI (sum of squared shares, `1/k`..`1.0`).

**Consequences:**

- New module `src/polaris_re/analytics/portfolio.py` (~330 lines)
  exporting `Deal`, `DealResult`, `Portfolio`, `PortfolioResult`.
  `analytics/__init__.py` `__all__` extended (alphabetised).
- No core data contracts changed — `CashFlowResult`, `Policy`,
  `InforceBlock`, and `ProfitTestResult` are consumed unchanged. The
  feature is purely additive; golden baselines are untouched.
- New tests: 29 unit tests in
  `tests/test_analytics/test_portfolio.py` — builder validation,
  closed-form two-deal NCF additivity (including mismatched horizons),
  PV-profit linearity, concentration shares / HHI, and a per-deal
  breakdown cross-checked against an independent projection.

**Out of scope (deferred to Slice 2 / later):**

- **CLI + API surfacing.** `polaris portfolio run|report` and
  `POST /api/v1/portfolio` are Slice 2.
- **Aggregate return-on-capital.** `run_with_capital` exists per-deal
  (ADR-048); a portfolio-level RoC roll-up is a follow-up once Slice 2
  lands the reporting surface.
- **Non-proportional treaties in a portfolio.** Stop-loss aggregation
  needs a non-proportional `ceded_face` definition — separate work.
- **Deal-specific hurdle rates.** `run` applies one hurdle to the whole
  book; per-cedant hurdles would be a later extension. PV profits at
  different discount rates do not sum, so this is a redesign of the
  aggregate `ProfitTester` pattern, not a parameter (PR #44 review).
- **Calendar-aligned aggregation.** Deals must currently share a
  valuation date; aggregating treaties with different inception dates on
  a common calendar grid is a separate slice. See
  `docs/CONTINUATION_portfolio_aggregation.md` "Refinement Backlog" for
  the full set of generality follow-ups raised in the PR #44 review.

---

## ADR-058: Portfolio CLI + API surfacing (Milestone 5.2, Slice 2)

**Status:** Accepted
**Date:** 2026-05-23

**Context.** ADR-057 introduced `analytics/portfolio.py` as a pure
analytics module — `Portfolio.run()` returns a `PortfolioResult`, but
nothing exposes it to end-users. Slice 2 wires the runner into the CLI
and the FastAPI service so reinsurers can run a multi-deal book from a
config file or an HTTP request.

**Decision.** Add a `polaris portfolio` Typer sub-app with two
sub-commands and a `POST /api/v1/portfolio` endpoint:

- `polaris portfolio run --config deals.yaml [--output result.json]` —
  loads a YAML or JSON portfolio config (format inferred from suffix),
  builds and runs a `Portfolio`, renders Rich tables for the overview /
  per-deal breakdown / three concentration dimensions, and writes the
  full result as JSON when `--output` is supplied.
- `polaris portfolio report --result result.json` — re-renders the
  same Rich tables from a previously written result JSON without
  re-running any projection. Cheap re-display of a stored run.
- `POST /api/v1/portfolio` — accepts a `PortfolioRequest` (a
  portfolio-level `hurdle_rate` + a list of `PortfolioDealRequest`
  entries, each one carrying everything `PriceRequest` carries plus
  `deal_id` and `cedant`) and returns the `PortfolioResult.to_dict()`
  payload directly.

A new `PortfolioResult.to_dict()` method flattens the dataclass for
JSON / Rich consumption: numpy arrays become lists, the per-deal
`DealResult` list becomes plain dicts each with a nested `profit_test`
block carrying the `ProfitTestResult` fields, and the three
`concentration_by_*` mappings are grouped under a single
`concentration` key keyed by dimension (`cedant` / `product` /
`treaty`). The CLI's Rich rendering and the API response consume the
same shape.

**Key choices:**

- **Per-deal config schema reuses `_parse_config_to_pipeline_inputs`.**
  Every entry in `deals[]` accepts the same `mortality` / `lapse` /
  `deal` keys that `polaris price --config` accepts, plus `deal_id`,
  `cedant`, and either inline `policies` or an `inforce_csv` reference.
  Zero schema duplication — the per-deal pipeline path is identical to
  a single-deal `polaris price` run.
- **YAML primary, JSON also accepted.** The config format is inferred
  from the file suffix (`.yaml` / `.yml` → YAML; otherwise JSON). YAML
  is the documented primary format because nested deal blocks are more
  readable, but JSON is supported so existing JSON consumers (CI
  fixtures, dashboards) don't need a YAML serialiser.
- **YRT rate derived when not supplied.** When `treaty_type='YRT'` and
  no `yrt_rate_per_1000` is provided, the CLI runs a one-off gross
  projection per deal and calls `derive_yrt_rate` (ADR-038) so ceded
  premiums are calibrated to the block's actual mortality, mirroring
  `polaris price`. Skipping this would yield a claims-only cession
  (`peak_ceded_nar = 0`), which is rarely what the user wants.
- **API endpoint returns a plain dict, not a fixed Pydantic response
  model.** Concentration / HHI / per-deal blocks contain
  caller-supplied keys (cedant labels, deal ids), so a typed schema
  would have to coerce them into a flat list. Returning
  `PortfolioResult.to_dict()` directly preserves the structure that
  the CLI also consumes.
- **Slice 1's API is preserved.** `Portfolio.add_deal` and `run` were
  not modified — only `to_dict()` was added. Slice 2 lives entirely in
  the CLI (`cli.py`) and the API (`api/main.py`), so the analytics
  core stays the single source of truth for portfolio math.

**Out of scope:**

- **Non-proportional treaties.** The CLI / API both reject
  stop-loss / null treaties — they need a non-proportional `ceded_face`
  definition (see Slice 1's "Refinement Backlog" item 4).
- **Aggregate return-on-capital.** Per-deal `run_with_capital` exists
  (ADR-048) but the portfolio-level RoC roll-up is deferred — see the
  CONTINUATION's refinement backlog.
- **Streamlit dashboard page.** The Slice 2 CONTINUATION only covers
  CLI + API; a portfolio dashboard view is a separate slice.

**Impact.**

- New `polaris portfolio run|report` Typer sub-commands in `cli.py`
  (~240 lines including the YAML loader, deal-config parsing, and the
  Rich rendering helper).
- New `POST /api/v1/portfolio` endpoint with `PortfolioRequest` and
  `PortfolioDealRequest` models in `api/main.py` (~110 lines).
- New `PortfolioResult.to_dict()` method and `_deal_result_to_dict`
  helper in `analytics/portfolio.py` (~70 lines).
- Sample portfolio config shipped at
  `data/configs/portfolio_demo.yaml`.
- New tests: 6 unit tests for `to_dict()`, 12 CLI tests
  (`test_cli_portfolio.py`), and 8 API tests (`test_portfolio.py`) —
  26 new tests in total. Golden regression baselines untouched.

---

## ADR-059: Portfolio aggregate `CashFlowResult` — full reinsurer-side cash flow lines

**Status:** Accepted
**Date:** 2026-05-27

**Context.** ADR-057 introduced `Portfolio.run()` and Slice 1 built the
aggregate `CashFlowResult` carrying only `gross_premiums` and
`net_cash_flow` — the minimum `ProfitTester` requires. That left
portfolio-level loss-ratio reporting (which needs `death_claims` and
`gross_premiums` together) and the planned portfolio-level
return-on-capital roll-up (which needs aggregate reserves) blind: both
consumers had to re-sum the per-deal reinsurer views themselves, which
also requires re-running the engine. The "Aggregate `CashFlowResult`
claims / expenses / reserves on `Portfolio.run()`" item in
PRODUCT_DIRECTION_2026-05-23 (sourced from
CONTINUATION_portfolio_aggregation — Refinement Backlog #2) called this
out as a 1-day quick win that unblocks the next slice.

**Decision.** Expand the aggregate `CashFlowResult` built inside
`Portfolio.run()` to carry every per-month line summed across deals:
`gross_premiums`, `death_claims`, `lapse_surrenders`, `expenses`,
`reserve_balance`, `reserve_increase`, and `net_cash_flow`. Each array
is the month-by-month sum of the per-deal reinsurer views, zero-padded
to the longest projection horizon — identical semantics to the existing
NCF aggregation, just applied uniformly across the seven cash-flow
lines. Expose the full result on `PortfolioResult.aggregate_cash_flow`
(new field of type `CashFlowResult`), and surface the seven arrays in
`PortfolioResult.to_dict()` under a new top-level `aggregate_cash_flow`
key.

The pre-existing `aggregate_net_cash_flow: np.ndarray` and
`aggregate_ceded_nar: np.ndarray` fields are kept as top-level
convenience handles for backward compatibility — both are wired to the
same data the new aggregate `CashFlowResult` carries, and a regression
test pins this equivalence.

**Rationale.** A single full-shape `CashFlowResult` is the right
handoff to `ProfitTester.run_with_capital` (the next slice — aggregate
RoC), and `CashFlowResult.loss_ratio()` already exists, so adding the
field makes portfolio-level loss-ratio reporting a one-call answer.
Re-using the existing month-by-month padded-sum pattern keeps the
"aggregate equals the sum of per-deal reinsurer views" invariant exact,
which is the property every existing portfolio aggregation test relies
on. No `CashFlowResult` contract change is required — the new fields
were already optional with default-empty arrays.

**Consequences.**
- `PortfolioResult` gains one new required dataclass field
  (`aggregate_cash_flow: CashFlowResult`). The only constructor is
  `Portfolio.run()`; no external code instantiates `PortfolioResult`.
- `to_dict()` gains one new top-level key, `aggregate_cash_flow`, with
  the seven arrays under it. Existing keys are untouched, so any
  consumer reading the existing keys continues to work.
- Backward-compatibility test (`test_aggregate_net_cash_flow_property_unchanged`)
  pins `PortfolioResult.aggregate_net_cash_flow ==
  aggregate_cash_flow.net_cash_flow`.

**Out of scope (future work).**
- Wiring the aggregate `CashFlowResult` into a portfolio-level
  `run_with_capital` helper for aggregate return-on-capital — that is
  the immediately-next item in PRODUCT_DIRECTION_2026-05-23
  (depends-on for this ADR).
- Exposing the new aggregate arrays in the CLI / API renderers. The
  raw arrays are already in `to_dict()`; CLI Rich rendering of summary
  metrics (e.g. aggregate loss ratio) is a small follow-up that can
  ship with the RoC slice.
- Dashboard surface — the Streamlit portfolio page does not yet exist
  (separate NICE-TO-HAVE item).

**Affected files.**
- `src/polaris_re/analytics/portfolio.py` (+~35 / -~10 lines).
- `tests/test_analytics/test_portfolio.py` (+~130 lines: 7 new tests
  + a shared `_independent_reinsurer_view` helper).

---

## ADR-060: Portfolio aggregate return-on-capital — single LICAT call on the aggregate

**Status:** Accepted
**Date:** 2026-05-28

**Context.** ADR-048 added `ProfitTester.run_with_capital` (per-deal RoC),
ADR-057 added `Portfolio.run()` (deal aggregation), and ADR-059 expanded
the aggregate `CashFlowResult` to carry every reinsurer-side cash flow
line — reserves and all. The portfolio-level RoC roll-up was deferred to
this slice (explicitly called out as "Out of scope" in ADR-058 and
flagged as the depends-on follow-up in ADR-059). PRODUCT_DIRECTION_2026-
05-23 promotes it as an IMPORTANT follow-up: "Aggregate return-on-capital
on `Portfolio`" — needs a single LICATCapital call against an aggregate
cash flow and aggregate NAR.

**Decision.** Add `Portfolio.run_with_capital(hurdle_rate, capital_model)`
returning a new `PortfolioResultWithCapital(PortfolioResult)` dataclass.
The method calls `Portfolio.run(hurdle_rate)` internally, then makes a
single `capital_model.required_capital(aggregate_cash_flow,
nar=aggregate_ceded_nar)` call to build the aggregate capital schedule.
The same metrics that `ProfitResultWithCapital` exposes per deal —
`initial_capital`, `peak_capital`, `pv_capital`, `pv_capital_strain`,
`return_on_capital`, `capital_adjusted_irr`, `capital_by_period` —
appear at the portfolio level, computed against the aggregate.

RoC denominator is `pv_capital` (stock at the hurdle rate), matching
ADR-048. `return_on_capital` is `None` when `pv_capital <= 0` (zero-
factor model or coinsurance-only book with no NAR). The capital-adjusted
IRR is the IRR of `aggregate_net_cash_flow - strain` with terminal
release of residual capital at month `T-1`, reusing the existing
`ProfitTester._solve_irr` so the IRR suppression rules from ADR-041 stay
consistent at deal and portfolio level.

`PortfolioResultWithCapital.to_dict()` extends the base `to_dict()` with
a new top-level `capital` block carrying the seven metrics. Every
existing `PortfolioResult` key is preserved unchanged, so any consumer of
the base contract — CLI, API endpoint, dashboard — keeps working.

**Rationale.** The aggregate `CashFlowResult` and aggregate ceded NAR
are already built inside `Portfolio.run()` (ADR-059 + ADR-057). With
LICAT's linear factor structure (`c1 * reserve + c2 * NAR + c3 *
reserve`), a single call against the aggregate inputs is identical to
summing per-deal calls — `test_capital_linearity_matches_sum_of_per_deal_capital`
pins this invariant. That equivalence is the actuarial justification the
PRODUCT_DIRECTION item asks for: a single call is not a simplification,
it IS the per-deal aggregation when the same factors apply across deals.

The subclass-with-additional-fields pattern matches ADR-048 (`Profit
ResultWithCapital` subclasses `ProfitTestResult`), so the analytics
contract is consistent at deal and portfolio level. No change to
`PortfolioResult` itself — purely additive.

**Consequences.**
- New public class `PortfolioResultWithCapital` exported from
  `polaris_re.analytics`.
- New method `Portfolio.run_with_capital`. The bare `Portfolio.run`
  signature and behaviour are unchanged.
- `to_dict()` gains a new `capital` block on
  `PortfolioResultWithCapital`. The base `PortfolioResult.to_dict()`
  output is unchanged.
- Same hurdle rate is used for per-deal IRR / breakeven, the aggregate
  profit test, and PV-capital — there is no separate "capital hurdle"
  parameter yet (deal-specific hurdle rates are tracked separately in
  PRODUCT_DIRECTION_2026-05-23 as NICE-TO-HAVE).

**Out of scope (future work).**
- CLI / API / Excel surfacing of the new `capital` block on the
  `polaris portfolio` command. The raw fields are in `to_dict()` so any
  JSON consumer can read them today; Rich rendering and Excel writer
  rows are a small follow-up that should land with a coherent set of
  portfolio-level summary numbers.
- Heterogeneous-product factor handling. The single `LICATCapital`
  applies one factor set to the whole portfolio. A mixed term / WL / UL
  book may need different C-2 factors per product type — workaround
  today: caller supplies a `LICATFactors` reflecting blended exposure,
  or runs per-product sub-portfolios. A built-in product-aware
  aggregation is a separate design ADR.
- LICAT lapse-risk / morbidity-risk capital and the C-1 / C-3 interim
  factors — tracked separately under PRODUCT_DIRECTION_2026-05-23
  "LICAT lapse-risk and morbidity-risk capital components" and
  "LICAT C-1 and C-3 capital components (interim)".

**Affected files.**
- `src/polaris_re/analytics/portfolio.py` (+~110 / -~5 lines: new
  `PortfolioResultWithCapital` dataclass + `Portfolio.run_with_capital`
  method + `__all__` update + capital import).
- `src/polaris_re/analytics/__init__.py` (+2 lines: re-export
  `PortfolioResultWithCapital`).
- `tests/test_analytics/test_portfolio.py` (+~210 lines: 10 new tests
  in `TestPortfolioRunWithCapital` + a small `_yrt` helper).

---

## ADR-061: Calendar-aligned portfolio aggregation — opt-in `align` mode

**Status:** Accepted
**Date:** 2026-05-29

**Context.** `Portfolio.run()` (ADR-057) aggregates per-deal reinsurer cash
flows by month index: month 0 of one deal lines up with month 0 of every
other deal. That is only actuarially valid when every deal shares a
valuation date, so Slice 1 *guarded* the invariant by rejecting mixed
valuation dates. A real reinsurer's assumed book, however, has treaties
inception-dated across years — the production workflow needs to aggregate
deals that start on different calendar dates. PRODUCT_DIRECTION_2026-05-23
promotes this as the lead IMPORTANT item ("Calendar-aligned portfolio
aggregation", Refinement Backlog #1 from CONTINUATION_portfolio_aggregation),
noting it "Just surfaced as a direct question on PR #45."

**Decision.** Add an opt-in `align` parameter to `Portfolio.run()` and
`Portfolio.run_with_capital()`:

- `align="strict"` (default) is the pre-existing behaviour: sum by month
  index, reject mixed valuation dates. The aggregate PV equals the sum of
  per-deal PVs. The default preserves every existing caller (CLI, API) and
  the `test_mismatched_valuation_dates_rejected` contract.
- `align="calendar"` keys a common monthly grid off the *earliest* deal
  valuation date and places each deal's cash flows at its whole-month offset
  from that origin. The generalised placement primitive `_place(arr, offset,
  length)` replaces the old trailing-only `_pad`; `_place(arr, 0, length)` is
  a plain zero-pad, so strict mode (all offsets zero) is byte-for-byte
  identical to the prior implementation.

Calendar mode requires all valuation dates to fall on the same day-of-month
(it raises otherwise), so the monthly grids line up exactly rather than
introducing a sub-month phase error. The aggregate `CashFlowResult`'s
`valuation_date` becomes the grid origin, and `projection_months` becomes
the span `max(offset_i + T_i)`.

**Rationale — the PV-summation subtlety.** PV in this engine discounts from
the array's month 0 (`v**arange(1, T+1)`). When a deal is placed at calendar
offset `o`, its cash flows are discounted by `v**o` extra relative to its
standalone profit test. Therefore, under `align="calendar"`,
`total_pv_profits` (the aggregate `ProfitTester` on the calendar-aligned
NCF) is the **portfolio NPV as of the common origin** and equals
`Σ_i v**(o_i) · PV_i`, which is *not* the naive `Σ_i PV_i` once inception
dates differ. This is the economically correct number — a deal that starts a
year later is worth less today — and is pinned by
`test_aggregate_pv_discounts_offset_deal_by_v_to_the_offset` (single offset
deal contributes exactly `v**o ·` its standalone PV). Per-deal `DealResult`
PVs remain as-of each deal's own inception, so both views are available to
the caller. This is the structural distinction Refinement Backlog #4
flagged: PV at different discount origins does not sum.

**Consequences.**
- `Portfolio.run` / `run_with_capital` gain a keyword-only `align` argument
  defaulting to `"strict"`. No existing caller changes behaviour.
- The strict error message now names `align='calendar'` as the alternative,
  but keeps the matched substring "same valuation date".
- No data-contract change: `PortfolioResult` / `PortfolioResultWithCapital`
  fields are unchanged. The grid origin is surfaced via the existing
  `aggregate_cash_flow.valuation_date`.
- `run_with_capital` threads `align` through unchanged — the single LICAT
  call (ADR-060) now operates on the calendar-aligned aggregate, and the
  linear-factor capital invariant still holds per deal at its grid offset.

**Out of scope (future work — Slice 2 and beyond).**
- CLI / API surfacing: `polaris portfolio run --align {strict,calendar}` and
  a `POST /api/v1/portfolio` `align` field, plus exposing the grid origin and
  per-deal grid offsets in `to_dict()` for transparent JSON consumption.
  Tracked in CONTINUATION_calendar_aligned_portfolio (Slice 2).
- Sub-month / non-common day-of-month inception dates. Today these are
  rejected; supporting them would require a finer (daily) grid or
  fractional-month discounting and is not warranted for monthly projections.
- Deal-specific hurdle rates interact with the PV-origin question
  (Refinement Backlog #4) and remain a separate NICE-TO-HAVE.

**Affected files.**
- `src/polaris_re/analytics/portfolio.py` (+~70 / -~15 lines: `align`
  parameter on `run` / `run_with_capital`, new `_grid_offsets` helper,
  `_pad` → offset-aware `_place`, `months_between` import, docstrings).
- `tests/test_analytics/test_portfolio.py` (+~180 lines: new
  `TestPortfolioCalendarAlignment` class — 10 tests — plus `start`-date
  parameters on the shared spec builders).

---

## ADR-062: Calendar-aligned portfolio aggregation — CLI / API surfacing (Slice 2)

**Status:** Accepted
**Date:** 2026-05-31

**Context.** ADR-061 introduced the `align="calendar"` mode on
`Portfolio.run` / `Portfolio.run_with_capital`, but Slice 1 stopped at the
core analytics layer. The CLI (`polaris portfolio run`) and the API
(`POST /api/v1/portfolio`) still called `portfolio.run(hurdle_rate)` with no
`align` kwarg, so the calendar-aligned mode was unreachable from any
user-facing surface and the grid origin / per-deal offsets were not
discoverable in JSON output. CONTINUATION_calendar_aligned_portfolio (Slice
2) tracks this gap.

**Decision.**

1. **CLI flag.** `polaris portfolio run` gains a `--align {strict,calendar}`
   option defaulting to `strict`. An unrecognised value exits cleanly. The
   Rich overview table grows a `Grid Origin` row, and the per-deal table
   carries an `Offset (mo)` column (always shown — `0` under strict / for
   the earliest deal under calendar; informative for the caller).

2. **API field.** `PortfolioRequest` gains an `align: Literal["strict",
   "calendar"]` field defaulting to `"strict"`. Pydantic's `Literal`
   validation rejects unrecognised values with a 422 before the endpoint
   logic runs. The endpoint passes `align=request.align` through to
   `portfolio.run`. Omitting `align` preserves the prior strict default.

3. **Grid metadata in `to_dict()`.** A top-level `grid_origin` key (ISO
   date) is added to `PortfolioResult.to_dict()`, equal to
   `aggregate_cash_flow.valuation_date`. Each per-deal block gains
   `valuation_date` (ISO date, the deal's projection start) and
   `grid_offset` (int, whole months from origin). JSON consumers can now
   reconstruct calendar placement without re-deriving dates from external
   state.

**Rationale for surfacing offsets on `DealResult`.** The CONTINUATION
flagged two options: stash the offsets on the `Portfolio` runner side, or
add a defaulted `valuation_date` / `grid_offset` field on `DealResult`. The
dataclass route is chosen because (a) `DealResult` is the per-deal artefact
already serialised by `_deal_result_to_dict`, so `to_dict()` does not need
to reach across two structures to render one row; (b) the additive defaults
(`valuation_date=None`, `grid_offset=0`) keep the dataclass
backward-compatible — only the internal `_run_deal` site constructs
`DealResult`, and existing tests that read `dr.deal_id`, `dr.cedant`, etc.
are untouched; and (c) future per-deal capital / IFRS17 hooks will want the
same date stamp on the deal record.

`Portfolio.run` constructs each `DealResult` with `grid_offset=0` inside
`_run_deal` and then uses `dataclasses.replace(dr, grid_offset=offset)` to
inject the resolved offset before appending — this keeps `_run_deal`
ignorant of grid alignment (single-deal projection has no notion of grid
origin) while letting `run` produce frozen results with the correct offsets.

**Consequences.**
- `--align calendar` and `align="calendar"` now unblock the production
  workflow described in ADR-061 from both CLI and API.
- `PortfolioResult.to_dict()` gains three keys (`grid_origin` top-level and
  `valuation_date` / `grid_offset` per deal). Existing top-level keys are
  unchanged. The portfolio-report dashboard re-renderer (`polaris portfolio
  report`) consumes the same dict shape and continues to work.
- The Rich per-deal table always shows the `Offset (mo)` column. For the
  common single-date case it shows `0` everywhere; for mixed-date calendar
  runs it shows each deal's whole-month offset from the origin.
- `DealResult` is additive: two new fields with safe defaults
  (`valuation_date: date | None = None`, `grid_offset: int = 0`). The
  single in-tree construction site is updated.

**Out of scope.**
- A Streamlit dashboard surface for calendar-aligned portfolios. The
  dashboard prices one deal at a time today (NICE-TO-HAVE in
  PRODUCT_DIRECTION_2026-05-23). A portfolio dashboard page would consume
  the same `to_dict()` shape but is its own feature.
- Backfilling grid metadata into prior dashboard portfolio JSON exports.
- Deal-specific hurdle rates (Refinement Backlog #4 / ADR-061 Out of
  scope) — still NICE-TO-HAVE, unchanged by this slice.

**Affected files.**
- `src/polaris_re/analytics/portfolio.py` (+~25 lines: `valuation_date` /
  `grid_offset` on `DealResult`, `grid_origin` in `to_dict()`,
  `dataclasses.replace` in `run` to thread offsets, `_deal_result_to_dict`
  surfaces new fields, `AlignMode` in `__all__`).
- `src/polaris_re/cli.py` (+~25 / -~5 lines: `--align` option,
  `PolarisValidationError` handling around `portfolio.run`, grid-origin row
  and offset column in the renderer).
- `src/polaris_re/api/main.py` (+~12 lines: `align` field on
  `PortfolioRequest`, passed through to `portfolio.run`).
- `tests/test_analytics/test_cli_portfolio.py` (+~120 lines: new
  `TestPortfolioRunAlignFlag` class — 7 tests — plus a `valuation_date`
  kwarg on the shared `_deal_block` helper).
- `tests/test_api/test_portfolio.py` (+~80 lines: new
  `TestPortfolioEndpointAlignField` class — 5 tests — plus a
  `valuation_date` kwarg on the shared `_deal_request` helper).
- `data/configs/portfolio_demo.yaml` (commentary describing how to flip the
  demo to calendar mode).

## ADR-063: Per-duration solver in `YRTRateSchedule.generate_table()`

**Status.** Accepted.

**Context.** `generate_table()` solves one flat YRT rate per `(age, sex, smoker)`
row and broadcasts it across every duration column of the resulting
`YRTRateTableArray`. The storage contract for `YRTRateTableArray` is 2-D
`(n_ages, select_period + 1)` and the `solved_mask` it carries (ADR-054) was
explicitly designed to disclose per-cell provenance, but the broadcast solver
produced a row-uniform mask, leaving the duration axis under-utilised. A real
per-duration solver was promoted to IMPORTANT in
PRODUCT_DIRECTION_2026-05-23 ("Source: CONTINUATION_yrt_rate_table — Out of
scope per ADR-055 follow-up #1 + ADR-053"); the renderers (CLI / Excel / JSON /
dashboard) already consume the 2-D `solved_mask`, so adding a per-duration
solver lands without surface changes.

**Decision.** `generate_table()` gains a `solve_mode: Literal["flat",
"per_duration"] = "flat"` parameter. The default `"flat"` preserves the
prior contract (and the existing row-uniform mask test). The new
`"per_duration"` mode solves a separate rate per `(age, duration)` cell by
projecting a synthetic policy that has been inforce for `d` years at the
row's issue age:

- `issue_age = age`, `attained_age = age + d`
- `duration_inforce = d * 12` months
- `issue_date = valuation_date` shifted back `d` years
- `policy_term` unchanged (so the projection covers `policy_term - d` years
  of remaining coverage)

The mortality lookup picks up at column `d` of the select-period table,
giving the actuarially correct "rate quoted today for a policy at duration
`d`" semantics. `solved_mask` becomes genuinely 2-D: True only for cells
that were directly solved at requested ages; cells filled by the column-
wise forward/back-fill (for unrequested age rows or brentq failures) stay
False.

A shared `_fill_and_pack_cohorts` helper handles the post-solve fill /
pack step for both modes. Column-wise forward/back-fill in per-duration
mode runs independently per duration column; the global cohort mean is
the last-resort fill for cohorts where no cell solved (same fallback as
the flat mode). At `select_period_years = 0` the two modes collapse to
the same single-column solve and produce numerically identical rates
(closed-form sanity test).

The `solve_mode` value also appears in the generated table's `table_name`
suffix so downstream artifacts can tell at a glance whether a schedule
was flat-broadcast or per-duration-solved.

**Consequences.**
- `YRTRateSchedule.generate_table(solve_mode="per_duration")` now produces
  schedules whose `solved_mask` is a genuinely 2-D per-cell map.
  Downstream renderers continue to work unchanged (they already loop over
  the 2-D mask).
- Default behaviour is unchanged: every call site that does not pass
  `solve_mode` keeps the row-uniform contract and the existing test fixtures
  (`TestGenerateTableSolvedMask`) keep passing.
- The new mode runs the rate solver `select_period_years + 1` times per
  `(age, sex, smoker)` instead of once, so wall-clock cost is roughly
  `(select_period_years + 1)x` the flat mode for the same grid. Acceptable
  for the deal-pricing workflows that consume this helper; future
  optimisation (warm-starting brentq from the adjacent column's solution)
  is left as a follow-up.

**Out of scope.**
- CLI / API surfacing of the `solve_mode` flag. The internal helper now
  supports it; surfacing through `polaris rate-schedule --table` is a
  separate (NICE-TO-HAVE) follow-up tracked in PRODUCT_DIRECTION.
- True per-duration cell-failure interpolation (e.g. linear across the
  duration axis when an interior column fails to solve). The current
  column-wise forward/back-fill is sufficient for the dense-grid case
  and is what `solved_mask` discloses; a richer interpolator can be
  added without changing the storage contract.
- Warm-starting `brentq` across adjacent cells.

**Affected files.**
- `src/polaris_re/analytics/rate_schedule.py` (~+150 / -~50 lines: new
  `_solve_cell` helper, `solve_mode` dispatch in `generate_table`,
  extracted `_forward_back_fill` and `_fill_and_pack_cohorts` helpers,
  `duration_inforce_years` kwarg on `_make_policy`, module docstring
  update).
- `tests/test_analytics/test_rate_schedule.py` (+~170 lines: new
  `TestGenerateTablePerDuration` class — 7 tests covering distinct
  per-column rates, monotonic select-period rates, dense and sparse
  mask shapes, the closed-form equivalence with flat mode at
  `select_period_years=0`, the YRTTreaty round-trip, and rejection of
  invalid `solve_mode` values).

## ADR-064: Portfolio-level scenario analysis (`Portfolio.run_scenarios`)

**Status.** Accepted.

**Context.** `ScenarioRunner` stresses one deal at a time, but a reinsurer
sees its book as a single portfolio: the deal-committee question is "what
happens to total PV / IRR / capital under a +10% mortality stress across
every cedant?", not "what happens to one deal in isolation?". The
`Portfolio` aggregator (ADR-057 / ADR-058 / ADR-059 / ADR-060 /
ADR-061 / ADR-062) supplies the aggregation surface; what was missing was
the per-scenario re-projection loop. The promoted follow-up
(PRODUCT_DIRECTION_2026-05-23, "Source: CONTINUATION_portfolio_aggregation —
Refinement Backlog #3") flagged the open design question between correlated
and independent stresses across cedants.

**Decision.** Add `Portfolio.run_scenarios(hurdle_rate, scenarios=None, *,
align="strict") -> PortfolioScenarioResult`. The semantics are:

- The same `ScenarioAdjustment` is applied uniformly to every deal — i.e.
  a "correlated" stress where every cedant experiences the shock
  simultaneously. This is the conservative reinsurer view: a +10%
  mortality scenario is "+10% on the entire book at once", not "the
  expected outcome under independent +10% shocks per cedant" (the latter
  reduces variance via diversification and would understate tail risk).
- For each scenario, a fresh `Portfolio` is built whose deals share the
  original inforce blocks, treaties, configs, and `cession_pct` but carry
  a scaled `AssumptionSet` (mortality + lapse multipliers via
  `apply_scenario_to_assumptions`). The full :meth:`Portfolio.run`
  pipeline then projects → applies treaties → aggregates → profit-tests
  the aggregate, producing a full :class:`PortfolioResult` for that
  scenario.
- `align` threads through to :meth:`run` unchanged so calendar-aligned
  portfolios (ADR-061 / ADR-062) participate in scenario analysis on the
  same grid.
- `_apply_scenario` is promoted to a public helper
  `apply_scenario_to_assumptions`. The same helper is reused by
  `uq.py`, keeping a single point of truth for the multiplier semantics.
- `PortfolioScenarioResult` carries `list[tuple[str, PortfolioResult]]`
  in the order scenarios were supplied. Helpers (`base_case`,
  `worst_case`, `irr_range`, `to_dict`) mirror
  :class:`~polaris_re.analytics.scenario.ScenarioResult`. `worst_case`
  picks the lowest aggregate `total_irr`, respecting the ADR-041
  suppression rules — scenarios whose IRR is `None` are skipped, not
  treated as `-inf`. Default scenarios (when `scenarios=None`) match
  `ScenarioRunner.standard_stress_scenarios()` so the deal-committee
  six-scenario set is the out-of-the-box default.

**Consequences.**
- The original portfolio is not mutated: `_with_scenario` builds a fresh
  `Portfolio` per scenario. A test verifies that calling
  :meth:`run` after :meth:`run_scenarios` reproduces the BASE result
  exactly.
- PV profits move in the expected direction under correlated stresses
  (+10% mortality reduces aggregate PV; -10% increases it), and every
  per-deal profit test inside each scenario also moves — there is no
  partial-stress regression where the scenario reaches only the first
  deal.
- Wall-clock cost scales as `len(scenarios) × cost(Portfolio.run)`. With
  the default six scenarios this is a 6x multiplier over a single
  :meth:`run`. Parallel execution is out of scope per the existing
  CONTINUATION_portfolio_aggregation backlog item (sequential `_run_deal`
  was a deliberate Slice 1 choice; the same constraint applies here).

**Out of scope.**
- **Per-deal scenario overrides ("independent / heterogeneous stresses").**
  The open design question from
  `CONTINUATION_portfolio_aggregation` Refinement Backlog #3 — where one
  cedant carries a +20% mortality stress while another stays at BASE —
  is deferred to a future ADR. The correlated-stress baseline shipped
  here is the actuarially conservative case and is the default deal-
  committee ask; the heterogeneous case requires a new
  `ScenarioAdjustment`-per-deal contract and result-shape changes.
- **CLI / API surfacing of `polaris portfolio --scenarios`.** The
  internal helper is in place; surfacing through the CLI / FastAPI
  endpoint is a NICE-TO-HAVE follow-up — separate JSON shape, separate
  golden baseline regenerations.
- **Streamlit dashboard page for scenario results.** Same story: a
  surface concern, not a contract concern.

**Affected files.**
- `src/polaris_re/analytics/scenario.py` (rename `_apply_scenario` →
  `apply_scenario_to_assumptions`, public alias added to `__all__`,
  internal callers updated, ~+15 lines / 0 net behaviour change).
- `src/polaris_re/analytics/uq.py` (single import + call-site rename).
- `src/polaris_re/analytics/portfolio.py` (+`PortfolioScenarioResult`
  dataclass with `base_case` / `worst_case` / `irr_range` / `to_dict`
  helpers, +`Portfolio.run_scenarios`, +`Portfolio._with_scenario`,
  ~+150 lines).
- `tests/test_analytics/test_portfolio.py` (+`TestPortfolioRunScenarios`
  with 14 closed-form / sensitivity / validation tests +
  `TestPortfolioScenarioResultHelpers` with 8 helper unit-tests; new
  `_stub_portfolio_result` builder, ~+260 lines).

## ADR-065: LICAT C-2 lapse-risk and morbidity-risk capital components

**Status.** Accepted.

**Context.** ADR-047 introduced `LICATCapital` with a single C-2 sub-
component — mortality risk — exposed as `c2_component = factor × NAR`.
OSFI's 2024 LICAT framework treats C-2 (insurance risk) as a basket that
also includes **lapse risk** (mass-lapse + level-lapse shocks) and
**morbidity risk** (incidence + termination shocks on DI / CI products).
Open Question #4 in `CONTINUATION_licat_capital.md` flagged this as a
straight extension of the factor model, and the harvest into
`PRODUCT_DIRECTION_2026-05-23.md` promoted it as an IMPORTANT follow-up
(source: CONTINUATION_licat_capital — Open Question #4 deferred to a
Phase 5.1.b ADR). Deal-committee work on multi-product books needs the
full C-2 number, not just the mortality slice, to defend a RoC tile.

**Decision.** Extend `LICATFactors` and `CapitalResult` additively, keep
the existing API surface stable:

- Add two new fields on `LICATFactors`:
  - `c2_lapse_factor: float` (default `0.0`, range `[0, 1]`) — applied
    to `reserve_balance` because mass-lapse exposure scales with the
    in-force reserve, not the NAR. This mirrors the LICAT 2024 mass-
    lapse-on-reserve formulation.
  - `c2_morbidity_factor: float` (default `0.0`, range `[0, 1]`) —
    applied to `NAR` because DI / CI morbidity capital scales with
    face-amount-at-risk under the standard incidence × benefit model.
    Zero by default for mortality-only products.
- Add two new array fields on `CapitalResult`:
  - `c2_lapse_component` — shape `(T,)`, dtype `float64`.
  - `c2_morbidity_component` — shape `(T,)`, dtype `float64`.
- Add a derived property `CapitalResult.c2_insurance_risk` that returns
  `c2_component + c2_lapse_component + c2_morbidity_component` — the
  aggregate C-2 figure that maps to the OSFI line item.
- `capital_by_period` now sums all five factor components
  (C-1 + mortality + lapse + morbidity + C-3). Existing test
  expectations `c2_component == factor × NAR` still pass because the
  field-name semantics for `c2_component` (mortality only) are
  preserved; the addition is a sibling field, not a redefinition.
- Add a new constructor `LICATCapital.for_product_extended(product_type)`
  that populates all three C-2 sub-factors per product. The existing
  `for_product` constructor is left unchanged — lapse and morbidity stay
  at zero — so any caller that has been audited against ADR-047 (the
  CLI `--capital licat` flag and the FastAPI `capital_model="licat"`
  surface) keeps the same capital number until it opts in.

**Default factor schedule.** Calibrated to the conservative committee-
screening range OSFI's 2024 LICAT documentation implies for each product
type; both factors are placeholders pending Phase 5.4 shock-based
calibration. Documented in `_C2_LAPSE_DEFAULT_BY_PRODUCT` and
`_C2_MORBIDITY_DEFAULT_BY_PRODUCT`:

| ProductType        | mortality | lapse | morbidity |
|--------------------|-----------|-------|-----------|
| TERM               | 0.15      | 0.05  | 0.00      |
| WHOLE_LIFE         | 0.10      | 0.03  | 0.00      |
| UNIVERSAL_LIFE     | 0.08      | 0.04  | 0.00      |
| DISABILITY         | 0.05      | 0.02  | 0.15      |
| CRITICAL_ILLNESS   | 0.05      | 0.02  | 0.12      |
| ANNUITY            | 0.03      | 0.06  | 0.00      |

The lapse factor on ANNUITY is the highest in the schedule because
deferred-annuity mass-lapse exposure on the in-force reserve is large
relative to mortality-only liabilities. Morbidity is non-zero only on
DI and CI as those are the products where the C-2 incidence shock
applies; for mortality-only products the LICAT morbidity component is
out of scope by construction.

**Consequences.**
- Backward compatibility: bare `LICATFactors()` and
  `LICATCapital.for_product(product_type)` produce the same capital
  number as before — both leave the new factors at zero. Existing
  ADR-047 / ADR-048 / ADR-049 wiring (CLI `--capital licat`, FastAPI
  `capital_model="licat"`, dashboard checkbox, Excel `_CAPITAL_METRICS`
  rows) keeps the same RoC tile. `ProfitTester.run_with_capital`
  integration surface is unchanged.
- A caller that wants the full LICAT 2024 C-2 number passes
  `LICATCapital.for_product_extended(...)` or constructs `LICATFactors`
  with explicit `c2_lapse_factor` / `c2_morbidity_factor`. The opt-in
  pattern matches ADR-049's "opt-in everywhere" stance on capital
  surfacing.
- `c2_component` field-name semantics (mortality only) are preserved.
  The aggregate insurance risk is available via the new
  `c2_insurance_risk` property; callers that prefer the aggregate to
  the mortality slice use that property without changing existing
  serialisation code.

**Out of scope.**
- **CLI / API / Excel / dashboard surfacing of the extended factors.**
  ADR-049's `--capital licat` integration uses `for_product(...)` and
  thus inherits the backward-compatible defaults. Switching the CLI to
  `for_product_extended(...)` is a behaviour change (golden baselines
  for capital tiles would move) and is a separate follow-up — promote
  to the next PRODUCT_DIRECTION once factor calibration is firmer.
- **Longevity risk for annuities.** OSFI's 2024 LICAT has a separate
  longevity component that flips the sign of the mortality shock for
  annuity products. The current `for_product(ANNUITY)` C-2 mortality
  factor of 0.03 is a placeholder that the annuity-specific factor
  follow-up (already in PRODUCT_DIRECTION_2026-05-23) will replace.
- **Diversification credits across C-1 / C-2 / C-3.** OSFI's
  standard-formula LICAT includes a diversification benefit between
  insurance and asset risks. The current sum-of-components approach is
  the conservative, no-diversification path. A future ADR can add a
  correlation matrix once the C-1 / C-3 components are non-zero.
- **Mass-lapse vs level-lapse decomposition.** The lapse factor here
  collapses both into a single number. Splitting into a transient
  mass-lapse shock and a permanent level-lapse shock is a Phase 5.4
  refinement.
- **Calibration against published OSFI factor tables.** The default
  schedule is a placeholder for committee screening. A QA-loop ADR
  will benchmark against published LICAT factor disclosures once a
  cedant provides annotated capital working papers.

**Affected files.**
- `src/polaris_re/analytics/capital.py` (+`c2_lapse_factor` /
  `c2_morbidity_factor` on `LICATFactors`, +`c2_lapse_component` /
  `c2_morbidity_component` on `CapitalResult`, +`c2_insurance_risk`
  property, +`for_product_extended` classmethod, updated
  `required_capital`, module docstring refresh, ~+85 lines).
- `tests/test_analytics/test_capital.py` (+`TestLICATFactorsExtendedC2`
  with 6 validation tests, +`TestLapseRiskComponent` with 4 closed-form
  tests, +`TestMorbidityRiskComponent` with 4 closed-form tests,
  +`TestExtendedC2Aggregate` with 4 sum / shape tests,
  +`TestForProductBackwardCompat` with 6 parametrised tests,
  +`TestForProductExtended` with 8 default / sensitivity tests,
  ~+250 lines).

## ADR-066: `polaris portfolio scenarios` CLI + `POST /api/v1/portfolio/scenarios` API surfacing

**Status.** Accepted.

**Date.** 2026-06-03.

**Context.** ADR-064 added `Portfolio.run_scenarios` at the analytics
layer with `PortfolioScenarioResult` and the deal-committee six-scenario
default set, but explicitly deferred CLI / API surfacing as "out of
scope — separate JSON shape, separate golden baseline regenerations". The
internal helper is only reachable from Python today; the deal-committee
workflow ("what happens to the whole book under +10% mortality?") still
requires hand-written notebook code rather than a one-liner from the
ops shell or a downstream system. The follow-up was promoted to
`PRODUCT_DIRECTION_2026-05-23.md` as a NICE-TO-HAVE ~2 dev-day item
(source: ADR-064 Out of scope).

**Decision.** Add a dedicated `polaris portfolio scenarios` CLI
subcommand and a `POST /api/v1/portfolio/scenarios` API endpoint that
both wrap :meth:`Portfolio.run_scenarios` and return the flat
:meth:`PortfolioScenarioResult.to_dict()` shape:

1. **CLI.** A new `portfolio_scenarios_cmd` subcommand on `portfolio_app`
   accepts:
   - `--config` (required) — the same YAML / JSON portfolio config the
     `run` subcommand consumes, parsed through the shared
     `_build_portfolio_from_config` helper so per-deal configuration is
     identical across the two paths.
   - `--scenarios` (optional, default `"standard"`) — comma-separated
     scenario names drawn from
     :meth:`ScenarioRunner.standard_stress_scenarios`, or the literal
     `"standard"` for the full six-scenario set. The order supplied is
     preserved in the JSON output. Empty values, duplicates, and unknown
     names exit cleanly with a Rich-rendered error message.
   - `--output` — optional path for the
     `PortfolioScenarioResult.to_dict()` JSON. When omitted the JSON
     prints to stdout via `console.print_json` (matches the existing
     `run` and `report` subcommand conventions).
   - `--hurdle-rate` — overrides the portfolio-level rate from the config,
     applied uniformly to every scenario.
   - `--align {strict,calendar}` — threaded through to every scenario's
     aggregate run unchanged so calendar-aligned portfolios from ADR-061 /
     ADR-062 participate in scenario analysis on the same grid.

2. **Rich console output.** A new `_render_portfolio_scenarios_summary`
   prints a one-row-per-scenario table with the scenario name, total PV
   profits, total IRR, total face, and peak ceded NAR — the same metric
   set the per-deal renderer surfaces from `PortfolioResult`. The full
   nested per-deal breakdown stays in the JSON output rather than the
   console (a six-scenario × N-deal table would dominate the terminal).

3. **API.** A new `POST /api/v1/portfolio/scenarios` endpoint accepts a
   :class:`PortfolioScenariosRequest` Pydantic model carrying the same
   `deals` / `hurdle_rate` / `align` / `name` fields as
   :class:`PortfolioRequest` plus an optional `scenarios: list[str] | None`
   field. The deal-build phase is shared with `POST /api/v1/portfolio` via
   a new private helper `_portfolio_from_request_deals` so the two
   endpoints consume identical per-deal payload shapes. Validation
   mirrors the CLI: an empty list 422s, duplicates 400, unknown names
   400, `None` (or omitted) defaults to the standard six.

4. **Shape.** The endpoint's response and the CLI's JSON output are
   both `PortfolioScenarioResult.to_dict()` unchanged — a flat
   `{"scenarios": [{"name", "result"}, ...]}` mapping where every
   `result` is itself a `PortfolioResult.to_dict()` payload. No new
   shape is introduced at the analytics layer; this is pure surfacing.

**Rationale for a separate `scenarios` subcommand (vs. a `--scenarios`
flag on `portfolio run`).** Two options were considered:

- (a) Add `--scenarios` to `portfolio run`. The output shape would then
  depend on whether the flag was set: `PortfolioResult.to_dict()` shape
  without it, `PortfolioScenarioResult.to_dict()` shape with it. Tools
  that consume the JSON would need to dispatch on the presence of a
  `scenarios` key.
- (b) Add a separate `scenarios` subcommand. Each command produces a
  single, predictable JSON shape. The shared
  `_build_portfolio_from_config` helper means there's no code
  duplication, and the existing `portfolio report` subcommand naturally
  consumes the single-portfolio shape without ambiguity.

Option (b) is the cleaner pattern: it composes with the existing
subcommand grammar (`portfolio run`, `portfolio report`,
`portfolio scenarios`), avoids polymorphic output, and leaves a clean
extension point for ADR-064's deferred "per-deal scenario overrides"
follow-up (a future `portfolio scenarios --per-deal-config X.json`).

**Consequences.**
- The deal-committee six-scenario workflow is now reachable via
  `polaris portfolio scenarios --config book.yaml --output stress.json`
  and via `POST /api/v1/portfolio/scenarios` without writing any Python.
- The `ScenarioRunner.standard_stress_scenarios()` set is the
  single point of truth for what `"standard"` and the API default mean.
  Adding scenarios there propagates automatically; deal-committee
  workflows must add explicit `--scenarios "BASE,...,NEW"` arguments to
  pin a fixed set against new defaults if reproducibility matters.
- Wall-clock cost on the CLI matches the analytics layer:
  `len(scenarios) × cost(Portfolio.run)`. Six scenarios on a 2-deal,
  10-policy test config completes in well under a second; parallel
  execution is still tracked separately (CONTINUATION_portfolio
  refinement #6 and the ADR-064 out-of-scope follow-up).
- `PortfolioRequest` and `PortfolioScenariosRequest` carry the same
  `deals` shape but are intentionally separate Pydantic models. A future
  refactor could lift the deal-list field into a shared mixin, but the
  per-endpoint validation difference (mandatory vs. optional `scenarios`)
  reads more clearly as two siblings than as a single class with a
  variant flag.

**Out of scope.**
- **Per-deal scenario overrides ("heterogeneous stresses across
  cedants").** Still tracked under PRODUCT_DIRECTION_2026-05-23 — Source:
  CONTINUATION_portfolio_aggregation Refinement Backlog #3 / ADR-064 Out
  of scope. This ADR ships the correlated-stress baseline only.
- **Streamlit dashboard page for portfolio scenario results.** A
  scenario-pivoted view consuming the same `to_dict()` shape — still a
  surface concern, separate work item.
- **Parallel `run_scenarios` execution.** Sequential by default; same
  scope as the parallel-portfolio-execution backlog item.
- **YAML config schema extension to embed a default scenario set.**
  Today the scenario set is a CLI flag / API field only. Embedding a
  `scenarios: [BASE, MORT_110]` field in the portfolio config YAML
  would let ops scripts pin a specific stress set per deal; deferred
  pending a deal-committee ask.
- **Golden baseline JSON for the scenarios endpoint.** Existing
  `tests/qa/` golden regression tests cover single-deal pricing
  pipelines. Adding a portfolio-scenarios golden requires a stable
  multi-deal fixture; out of scope for this slice.

**Affected files.**
- `src/polaris_re/cli.py` (+`portfolio_scenarios_cmd` subcommand,
  +`_resolve_scenarios_argument` helper, +`_render_portfolio_scenarios_summary`
  helper, +`_STANDARD_SCENARIO_KEYWORD` constant, updated module
  docstring header, ~+200 lines).
- `src/polaris_re/api/main.py` (+`PortfolioScenariosRequest` Pydantic
  model, +`api_portfolio_scenarios` endpoint, refactored shared
  `_portfolio_from_request_deals` helper used by both portfolio
  endpoints, updated module docstring header, ~+120 lines net).
- `tests/test_analytics/test_cli_portfolio.py`
  (+`TestPortfolioScenariosCommand` with 14 tests covering default
  standard set, named subset filtering, output shape, mortality-stress
  ordering, hurdle-rate override, calendar alignment, and validation
  failures, ~+260 lines).
- `tests/test_api/test_portfolio.py` (+`TestPortfolioScenariosEndpoint`
  with 11 tests covering endpoint contract, validation failures, and
  calendar-mode threading, ~+135 lines).

---

## ADR-067: `--solve-mode` flag on `polaris rate-schedule --table`

**Status.** Accepted.

**Date.** 2026-06-04.

**Context.** ADR-063 added a `solve_mode` parameter to
`YRTRateSchedule.generate_table()` with two modes — `"flat"` (default;
single rate per `(age, sex, smoker)` broadcast across the select columns)
and `"per_duration"` (independent solve per `(age, duration)` cell).
The internal helper is exercised by `TestGenerateTablePerDuration` at
the analytics layer, and the generated `YRTRateTable.table_name` is
already suffix-tagged with the mode (`..._flat` / `..._per_duration`).
What was missing: a CLI surface. `polaris rate-schedule --table` always
called `generate_table()` with the default `"flat"`, so ops users had no
way to opt into the per-duration solver from the command line. The
follow-up was promoted to `PRODUCT_DIRECTION_2026-05-23.md` as a
NICE-TO-HAVE ~1 dev-day item (source: ADR-063 Out of scope).

**Decision.** Add a `--solve-mode {flat,per_duration}` Typer option to
`rate_schedule_cmd` and thread it straight through to
`scheduler.generate_table(solve_mode=...)`. The option uses
`Annotated[Literal["flat", "per_duration"], typer.Option(...)]` so
Typer's auto-derived choice validation does the input check; an unknown
value exits with the standard Click usage error before any projection
runs.

The flag is only meaningful with `--table`. When `--table` is unset and
the user passes `--solve-mode per_duration`, the command exits with code
1 and a Rich-rendered error message ("--solve-mode is only meaningful
with --table"). The default `"flat"` is treated as a no-op without
`--table` so existing flat-schedule invocations are unchanged.

**Rationale for upfront rejection vs. silent ignore.** A silent ignore
would let users submit a flag combination that does nothing; the explicit
rejection means the CLI never silently does less than what was asked.
This matches the existing pattern from the `--table -o NAME.csv`
combination which also exits 1 with a clear error rather than silently
falling back to a different format. The `flat` default is allowed through
without `--table` only because it is the no-op identity — typing
`--solve-mode flat` is the same as omitting it.

**Rationale for Typer's `Literal` over `click.Choice`.** Typer 0.24
auto-derives choice validation from `Literal` annotations on options;
the `click.Choice` import is no longer needed. The `Literal` type also
flows through to the analytics layer (`SolveMode = Literal["flat",
"per_duration"]` in `analytics/rate_schedule.py`) so the CLI signature
and the helper signature carry the same type discipline.

**Consequences.**
- `polaris rate-schedule --table --solve-mode per_duration` now
  exercises the per-duration solver end-to-end from the command line.
  With `--select-period 0` the two modes produce identical output (one
  column to solve, nothing to differentiate), matching the analytics
  contract from `test_per_duration_select_period_zero_matches_flat`.
- The generated `YRTRateTable.table_name` already encodes the mode
  (`generated_term20_irr10_per_duration` vs. `..._flat`), so downstream
  consumers of the JSON / Excel output can detect the mode without a
  separate flag.
- The `--select-period` help text was updated to reflect that
  per-duration cells are no longer "until the per-duration solver
  lands" — the solver is here, and the flag controls whether it runs.
- No analytics-layer contract changes. `generate_table()` is unchanged;
  the CLI just exposes its existing parameter.

**Impact on golden baselines.** None. `polaris price` and the deal-
pricing pipeline do not call `rate-schedule`; the default `"flat"`
behaviour of `rate-schedule --table` is byte-identical to the prior
implementation. Existing CLI tests (`test_table_emits_xlsx`,
`test_table_json_emits_cohort_dict`, etc.) pass without modification.

**Out of scope.**
- **Per-duration cell-failure interpolation.** `generate_table(
  solve_mode="per_duration")` falls back to column-wise forward/back-fill
  when an individual `(age, duration)` cell fails to solve; a richer
  interpolator (e.g. linear across the duration axis) would be a quality
  improvement. Still tracked under PRODUCT_DIRECTION_2026-05-23 — Source:
  ADR-063 Out of scope.
- **Warm-start `brentq` across adjacent per-duration cells.** Pure
  performance, no contract change. Still tracked under
  PRODUCT_DIRECTION_2026-05-23 — Source: ADR-063 Out of scope.

**Affected files.**
- `src/polaris_re/cli.py` (+`Literal` import; +`--solve-mode` Typer
  option on `rate_schedule_cmd`; +upfront-rejection guard for
  `--solve-mode != "flat"` without `--table`; pass-through to
  `generate_table(solve_mode=...)`; tightened `--select-period` help
  text; ~+25 lines).
- `tests/test_analytics/test_cli_rate_schedule_table.py`
  (+`TestSolveModeFlagValidation` with 3 fast tests for input
  validation and the no-table guard; +`TestSolveModePerDurationCLI`
  with 4 slow end-to-end tests for the `_per_duration` table_name
  suffix, the `_flat` table_name suffix, per-cell distinct rates, and
  the genuinely 2-D `solved_mask`; ~+170 lines).

---

## ADR-068: Rated-block panel on the deal-pricing Excel Assumptions sheet

**Date:** 2026-06-05
**Status:** Accepted

**Context.** ADR-044 (Slice 3 of the substandard-rating feature) surfaced
the block-level rating composition via `polaris_re.utils.rating.
rating_composition` and rendered a Rich table in `polaris price` and a
metric panel in the dashboard. `CONTINUATION_deal_pricing_excel` Open
Question #3 noted that the deal-pricing Excel workbook's Assumptions
sheet should carry the same panel — committee reviewers will ask "how
much of this block is rated" when reading the workbook offline. The
question was deferred from Slice 2 of ADR-046 because the substandard
contract was not finalised at the time. Both contracts are now stable.

**Decision.** Add an optional `rated_block: RatedBlockExport | None`
field to `DealPricingExport`. The `RatedBlockExport` dataclass mirrors
the seven keys returned by `rating_composition` in typed form. When
populated AND `n_rated > 0`, `_write_assumptions_sheet` appends a
"Rated Block" section below the existing assumption rows containing:

- Policies Rated
- % Rated (by count)
- % Rated (by face)
- Face-weighted Avg Multiplier
- Max Multiplier
- Max Flat Extra / $1,000

The CLI builds the DTO once from the block-level `rating_composition`
result and passes the same instance into every per-cohort workbook in
mixed-cohort runs. This matches the once-per-run CLI Rich panel —
committee packets are block-level documents, so block-level rating
composition is the right number to embed even when the cohort is
sliced.

**Rationale.** A typed `RatedBlockExport` dataclass — rather than
threading the raw `dict[str, float | int]` returned by
`rating_composition` — keeps the writer signature stable and lets
`mypy` catch field renames at the boundary. Every other writer DTO in
`excel_output.py` (`DealMetaExport`, `AssumptionsMetaExport`,
`ScenarioMetric`) follows the same frozen-dataclass pattern.

Suppressing the panel when `n_rated == 0` keeps all-standard workbooks
byte-identical to pre-ADR-068 output. The CLI Rich panel applies the
same guard (`if int(rated_summary["n_rated"]) > 0: ...`), so the two
surfaces stay in lockstep.

**Consequences.**
- The Assumptions sheet grows by one section header + six labelled
  rows whenever the priced block contains at least one rated policy.
  All other sheets are unaffected.
- `DealPricingExport` gains a new optional field with default `None`,
  so callers that do not populate `rated_block` (test fixtures,
  downstream consumers) keep working untouched.
- The CLI's `_cohort_to_deal_pricing_export` gains a `rated_block`
  parameter (also default `None`). The Excel-out branch of
  `price_cmd` constructs the DTO from the existing block-level
  `rated_summary` dict — no new computation, just typed re-bundling.

**Impact on golden baselines.** None. The golden inforce
(`data/qa/golden_inforce.csv`) carries no substandard-rating columns,
so `n_rated == 0` and the panel is suppressed. The two golden
regression tests (`TestGoldenYRT`, `TestGoldenFlat`) and the
`polaris price` regression check produce byte-identical output.

**Out of scope.**
- **Per-cohort rated-block panels in mixed-cohort runs.** The
  workbook today reflects block-level composition (matching the CLI
  Rich panel). Mixed-cohort books that need per-cohort rating
  composition would require threading the per-cohort `InforceBlock`
  through `_cohort_to_deal_pricing_export` and calling
  `rating_composition` once per cohort. Defer until any committee
  asks for it.
- **Rated-block histogram / band breakdown on the workbook.** The
  dashboard renders a `_rating_histogram` (Standard / Flat-extra-only /
  Table 2 / Table 3+) — useful for a one-screen view but harder to
  reproduce in an openpyxl chart and not requested by Open Question #3.

**Affected files.**
- `src/polaris_re/utils/excel_output.py` (+`RatedBlockExport`
  dataclass; +`rated_block` field on `DealPricingExport`;
  +`_write_rated_block_panel` helper; +panel call site in
  `_write_assumptions_sheet`; ~+55 lines).
- `src/polaris_re/cli.py` (+`rated_block` parameter on
  `_cohort_to_deal_pricing_export`; +`RatedBlockExport` construction
  in the `excel_out` branch of `price_cmd`; ~+15 lines).
- `tests/test_utils/test_excel_output.py` (+`TestRatedBlockPanel`
  class with 6 tests covering: default-None suppression, n_rated=0
  suppression, label presence when rated lives present, n_rated
  value, face-weighted multiplier value, percentage formatting;
  ~+115 lines).

## ADR-069: Weighted concentration variants on `PortfolioResult`

**Date:** 2026-06-05
**Status:** Accepted

**Context.** Through ADR-058 the `Portfolio` runner exposed
concentration shares (cedant / product / treaty) and Herfindahl
indices weighted by **ceded face amount** — a static, point-in-time
view of exposure as of the projection start. Two reinsurer use cases
that the deal committee asks for are not well served by face-weighting:

- **Risk concentration.** A coinsurance treaty exposes the reinsurer
  to claim risk roughly proportional to ceded face, but a YRT treaty
  exposes the reinsurer only to the net amount at risk (NAR).
  Mixed-treaty books look very different concentrated by NAR than by
  face, and the NAR view is the one risk officers actually price.
- **Revenue concentration.** Two deals with equal ceded face but very
  different premium structures (term vs. permanent, different rate
  bases) contribute very differently to the reinsurer's revenue.
  Concentrating by PV of premiums surfaces the revenue-side
  concentration that finance committees ask about.

`CONTINUATION_portfolio_aggregation`'s Refinement Backlog #5 flagged
that `_concentration` already accepts generic `(label, weight)` pairs,
so surfacing additional weight bases is structurally trivial — the
work is design (which bases, how to name them, what to expose) plus
wiring.

**Decision.** Add a `concentration_by_basis: dict[str, dict[str,
dict[str, float]]]` field to `PortfolioResult` keyed as
`{basis: {dimension: {label: share}}}` and a matching
`hhi_by_basis: dict[str, dict[str, float]]` field keyed as
`{basis: {dimension: hhi}}`. Both default to `{}` so any caller that
constructs a `PortfolioResult` directly (test stubs, downstream
adapters) keeps working untouched.

Three weight bases are computed in `Portfolio.run`:

| Basis             | Per-deal weight                                  |
|-------------------|--------------------------------------------------|
| `ceded_face`      | `DealResult.ceded_face` (matches the flat view)  |
| `ceded_nar_peak`  | `DealResult.ceded_nar.max()` (zero when no NAR)  |
| `pv_premium`      | `DealResult.profit_test.pv_premiums`             |

`concentration_by_basis["ceded_face"]["cedant"]` IS
`concentration_by_cedant` — by construction, since the flat fields are
now populated from `concentration_by_basis["ceded_face"]`. Likewise
`hhi_by_basis["ceded_face"]` IS `hhi`. The two surfaces cannot drift.

`PortfolioResult.to_dict()` gains two new top-level keys —
`concentration_by_basis` and `hhi_by_basis` — alongside the unchanged
`concentration` and `hhi` keys. The CLI's `portfolio run` renderer
keeps consuming the flat `concentration` block; JSON downstream
consumers can pick up the nested view without breaking changes.

**Rationale.** A dictionary-of-dictionaries keyed by basis is the
ergonomic shape for the `concentration[dimension][weight_basis]` API
the routine's PRODUCT_DIRECTION entry proposed, and it matches the
existing `hhi: dict[str, float]` shape so the new field reads like a
natural extension rather than a parallel API. Pre-computing all three
bases in `Portfolio.run` (rather than exposing a `concentration(basis)`
method) is the simpler ergonomics — the cost is three calls to
`_concentration` per portfolio run, which is negligible next to the
projection itself.

Surfacing the three bases that were named in the original backlog
(face, NAR, PV-premium) is enough to cover the two use cases above
without picking up the capital-weighted basis suggested in the
backlog. Capital weights depend on a `LICATCapital` instance and only
exist on `PortfolioResultWithCapital`; folding them into the base
`PortfolioResult` would require either threading the capital model
into `run()` or restricting the field to the subclass. Defer until any
committee asks for it.

The peak-NAR weight (versus, say, time-integrated NAR or average NAR)
matches how risk capacity is typically allocated — the per-deal cap on
how much NAR the reinsurer is willing to assume at any one point. The
PV-premium weight comes from the deal's own profit test, so it
inherits the portfolio's hurdle rate consistently and does not
introduce a separate discount-rate choice.

**Consequences.**

- `PortfolioResult` and its `to_dict()` payload grow two additional
  keys. Every existing consumer (`polaris portfolio run` CLI, the
  Streamlit dashboard portfolio view, the `POST /api/v1/portfolio`
  endpoint) continues to work — the flat `concentration` / `hhi` keys
  are unchanged bit-for-bit on every test fixture and on the golden
  regression run (the bases agree on a single-deal portfolio).
- `PortfolioResultWithCapital` inherits the new fields without code
  changes because it shallow-copies `PortfolioResult` fields by name
  in `run_with_capital`.
- `PortfolioScenarioResult.to_dict()` carries the new keys for every
  scenario sub-result because each scenario is a `PortfolioResult`.
- A new public symbol `CONCENTRATION_BASES` (and the type alias
  `ConcentrationBasis`) is exported so downstream consumers can
  iterate the bases without re-listing the literal strings.

**Impact on golden baselines.** None. The `polaris price` golden
regression (`/tmp/dev_check.json`) is unchanged because the price
pipeline does not flow through `Portfolio.run`. The new keys appear
only on `PortfolioResult.to_dict()`, which only `polaris portfolio`
emits.

**Out of scope.**

- **Capital-weighted concentration.** Requires a `LICATCapital`
  instance per deal and only meaningfully exists on
  `PortfolioResultWithCapital`. Defer until any committee asks for
  the per-deal capital share alongside face / NAR / PV.
- **Surfacing `concentration_by_basis` in the CLI / dashboard.** The
  Rich table in `polaris portfolio run` renders only the
  face-weighted view. A `--concentration-basis` flag (or three
  per-basis tables, or a switchable dashboard control) would surface
  the new bases interactively; the JSON output already carries them
  for any downstream consumer.
- **Time-integrated or PV-NAR weighting.** Peak NAR is the natural
  capacity-allocation metric; PV-NAR or time-averaged NAR would
  weight more like revenue. If a use case lands, add as additional
  bases — the dict-of-dicts shape accommodates them without a
  contract change.

**Affected files.**

- `src/polaris_re/analytics/portfolio.py` (+`ConcentrationBasis` type
  alias and `CONCENTRATION_BASES` constant; +`_deal_weight` and
  +`_concentration_for_basis` helpers; +`concentration_by_basis` and
  +`hhi_by_basis` fields on `PortfolioResult`; rewires `Portfolio.run`
  to populate the flat fields from the `ceded_face` basis; +panels in
  `to_dict()`; ~+60 lines).
- `tests/test_analytics/test_portfolio.py` (+`TestPortfolioConcentrationByBasis`
  with 11 tests covering: supported bases, ceded-face equivalence,
  shares-sum-to-one across bases, NAR-peak concentrates on YRT,
  PV-premium weights by revenue, PV-premium matches per-deal pv_premiums,
  HHI-by-basis equals squared shares, single-deal full concentration,
  `to_dict` shape, JSON round-trip; ~+155 lines).

---

## ADR-070: `--concentration-basis` flag on `polaris portfolio run` / `report`

**Date:** 2026-06-05
**Status:** Accepted

**Context.** ADR-069 added `concentration_by_basis` and `hhi_by_basis`
to `PortfolioResult.to_dict()` — a three-basis nested view of
`{basis: {dimension: {label: share}}}` for the `ceded_face`,
`ceded_nar_peak`, and `pv_premium` weight bases. The JSON payload was
the contract change; the CLI was left to a follow-up. The
`polaris portfolio run` Rich tables and the `polaris portfolio report`
re-renderer continued to consume only the flat `concentration` /
`hhi` keys, so the new bases were reachable from a Python REPL or
the JSON output but not from the command line — which is the
production interface for an ops-driven deal committee. The follow-up
was promoted to `PRODUCT_DIRECTION_2026-05-23.md` as a NICE-TO-HAVE
1–2 dev-day item (source: ADR-069 Out of scope).

**Decision.** Add a `--concentration-basis` Typer option to both
`portfolio_run_cmd` and `portfolio_report_cmd`. The option accepts
`ceded_face` (default), `ceded_nar_peak`, `pv_premium`, or `all`.
Typer auto-validates the choice from a `Literal[...]` annotation —
matching the ADR-067 pattern for `--solve-mode` — so an unknown value
exits with the standard Click usage error before any projection runs.

The renderer was refactored to consume the new field. The
concentration / HHI block of `_render_portfolio_summary` is now a
loop over the basis tuple (one entry for the explicit single-basis
case, three entries for `"all"`), each rendered by a new
`_render_concentration_tables_for_basis` helper. The helper reads
from `result_dict["concentration_by_basis"][basis]` when the key is
present and from the flat `concentration` / `hhi` keys when it is not
(legacy result JSON written before ADR-069). Non-face bases on a
legacy file emit a one-line warning and skip rendering for that basis
rather than failing — `polaris portfolio report` is the upgrade-path
surface, and refusing to render a legacy file would force users to
re-run prior portfolio jobs just to view them.

Every concentration table title now discloses the weight basis:
"Concentration by Cedant — weighted by Ceded Face (HHI = 0.500)".
Previously the title was the unqualified
"Concentration by Cedant (HHI = 0.500)" which silently meant
face-weighting. Disclosing the basis costs nothing on the default
path and prevents the off-by-default misreading of the non-default
sections under `--concentration-basis all`.

**Rationale for `"all"` over multiple flag invocations.** A single
`--concentration-basis all` is friendlier than a hypothetical
multi-valued flag (`--concentration-basis ceded_face
--concentration-basis ceded_nar_peak`) and avoids defining a
custom Typer parameter parser. The deal committee's most common
read is "show me everything"; the per-basis values exist for the
narrower "I only care about NAR" case.

**Rationale for in-CLI fallback to flat keys.** The fallback is
~10 lines and removes a class of upgrade-path failure: a polaris-re
upgrade does not invalidate prior portfolio JSON outputs. The
warning-and-skip behaviour for non-face bases on legacy files keeps
the failure mode obvious without an abort.

**Rationale for changing every title to disclose the basis.** No
test asserts on the title strings, so this is a free clarity win.
Inside `--concentration-basis all`, the three sections would
otherwise be visually indistinguishable. The renderer never wins by
leaving the weight basis implicit.

**Consequences.**
- `polaris portfolio run --concentration-basis ceded_nar_peak` and
  `--concentration-basis pv_premium` surface the new bases without
  changing the JSON output (which still carries all three under
  `concentration_by_basis`).
- `polaris portfolio report --concentration-basis all` re-renders a
  result JSON in all three weighting views without re-running the
  projection — useful for committee-room review of an already-priced
  portfolio.
- The JSON output is unchanged by this ADR. The flag only controls
  the rendered Rich tables.
- The `--concentration-basis` flag is not added to `polaris portfolio
  scenarios` because the scenarios renderer (one row per scenario,
  no concentration tables) does not consume concentration data. The
  per-scenario JSON still carries `concentration_by_basis` for every
  scenario sub-result.

**Impact on golden baselines.** None. `polaris price` does not flow
through `Portfolio.run`. The default-basis rendered output is
visually similar to the prior format (only the title gains a
"— weighted by Ceded Face" suffix) and no test asserts on the prior
title text.

**Out of scope.**
- **Dashboard concentration-basis selector.** The Streamlit dashboard
  portfolio view (when it lands — currently in the NICE-TO-HAVE queue)
  would expose the same three bases via a Streamlit selectbox. Still
  tracked under PRODUCT_DIRECTION_2026-05-23 — Source: ADR-069 Out of
  scope.
- **Capital-weighted basis.** Same reasoning as ADR-069: capital
  weights only exist on `PortfolioResultWithCapital`. The CLI flag
  signature is forward-compatible with a fourth `capital` choice;
  adding it is a follow-up if the deal committee asks. Still tracked
  under PRODUCT_DIRECTION_2026-05-23 — Source: ADR-069 Out of scope.

**Affected files.**
- `src/polaris_re/cli.py` (+`_PORTFOLIO_CONCENTRATION_BASES` tuple
  and `_PORTFOLIO_CONCENTRATION_BASIS_LABELS` mapping;
  +`_render_concentration_tables_for_basis` helper;
  +`concentration_basis` parameter on `_render_portfolio_summary`;
  +`--concentration-basis` Typer option on `portfolio_run_cmd` and
  `portfolio_report_cmd`; ~+85 lines, ~-25 lines).
- `tests/test_analytics/test_cli_portfolio.py`
  (+`TestPortfolioRunConcentrationBasisFlag` with 7 tests:
  default basis matches face, explicit ceded_face matches default,
  ceded_nar_peak renders NAR-only section, pv_premium renders
  PV-only section, "all" renders three sections, invalid basis
  rejected by Typer, JSON output carries all three bases regardless
  of flag; +`TestPortfolioReportConcentrationBasisFlag` with 3 tests:
  report supports "all", report falls back to flat keys on legacy
  JSON, report warns and skips on non-face basis with legacy JSON;
  ~+225 lines).


---

## ADR-071: Ingestion strict mode for unknown rating codes

**Date:** 2026-06-06
**Status:** Accepted

**Context:** `RatingCodeMap` (ADR-044) silently falls back to its
`default` entry when a row's rating code is not registered in `codes`.
On a production pipeline this is the wrong default — a cedant feed
that suddenly contains `TBL3` because of an upstream code-list change
gets silently treated as standard mortality, and the resulting deal
is mispriced with no signal. The fallback is correct as a *default*
because it preserves backward compatibility (and is sometimes what a
small cedant actually wants for sparsely-rated books), but it must
be opt-out-able.

This was tracked as "Ingestion strict-mode for unknown rating codes"
under PRODUCT_DIRECTION_2026-05-23 — Source: CONTINUATION_substandard_
rating — Slice 3 follow-up.

**Decision:** Add a `strict: bool = False` field to `RatingCodeMap`.
When `True`, `_apply_rating_code_map` collects every distinct unknown
code in the source column (sorted, deduped), gathers up to five
example `policy_id`s if that column is present, and raises
`PolarisValidationError` with a message that names the column, the
unknown codes, and the example IDs. The `default` entry is not
consulted in strict mode.

**Rationale:**
- Default-False preserves byte-identical behaviour for every existing
  ingestion config — including the golden CSV path which carries no
  rating column at all.
- Reusing `PolarisValidationError` keeps the exception type
  consistent with the surrounding ingestion failure modes (missing
  required columns, out-of-range bounds on `RatingCodeEntry`).
- Listing **all** distinct unknown codes (not just the first) lets
  the user fix the rating-code map in one pass rather than
  whack-a-mole.
- Example policy_ids are capped at five to keep the error message
  bounded on large blocks; the codes themselves are unbounded
  because they are typically a small finite set.
- Implementation lives entirely in `_apply_rating_code_map` and is a
  single early-exit branch — no impact on the success path's
  performance.

**Out of scope.**
- Warn-mode (log a warning but continue) — the binary default-vs-
  strict choice is the recommended pattern; warn-mode would add a
  third behaviour to reason about with no clear use case.
- Per-row strict (allow some codes to default, others to fail) —
  this is a rating-code-registry curation problem, not an ingestion
  one. The user should curate `codes` instead.

**Affected files.**
- `src/polaris_re/utils/ingestion.py` (+`strict` field on
  `RatingCodeMap`; +unknown-code detection in
  `_apply_rating_code_map`; ~+25 lines).
- `tests/test_utils/test_ingestion.py`
  (+5 tests on `TestRatingCodeMap`: default is False, strict raises
  on unknown code with policy_id surfaced, strict passes when all
  codes known, error lists every distinct unknown code deduped and
  sorted, YAML round-trip of the strict flag; ~+135 lines).

**Impact on golden baselines.** None. The default value of `False`
preserves the existing behaviour everywhere. The flag only changes
behaviour when explicitly opted in.

## ADR-072: Interim C-1 / C-3 LICAT factors via `for_product_interim`

**Date:** 2026-06-07
**Status:** Accepted

**Context.** ADR-047 / ADR-049 introduced `LICATCapital` with C-1
(asset default) and C-3 (interest-rate) as zero stubs, deferred to
Phase 5.4's shock-based asset / ALM model. ADR-065 extended C-2 into
three sub-components (mortality, lapse, morbidity). Today's capital
tile on a `for_product(...)` or `for_product_extended(...)` run is
therefore C-2 only — visibly incomplete on a deal-committee deck where
"LICAT capital" reads as a single number that should include asset and
rate risk. Open Question #3 in `CONTINUATION_licat_capital.md` flagged
this gap and the 2026-05-23 PRODUCT_DIRECTION harvest promoted it as a
NICE-TO-HAVE follow-up ("an interim C-3 factor (e.g. 1% of reserves)
makes the capital number less visibly incomplete"). The fix needs to
be opt-in so existing capital surfaces (CLI `--capital licat`, FastAPI
`capital_model="licat"`, dashboard checkbox, Excel `_CAPITAL_METRICS`
rows wired to `for_product`) keep byte-identical output.

**Decision.** Add `LICATCapital.for_product_interim(product_type)`
classmethod that populates all five LICAT factors with conservative
committee-stage placeholders:

- C-2 mortality / lapse / morbidity: identical to
  `for_product_extended` (ADR-065 schedule, unchanged).
- C-1 asset default: uniform 0.005 (0.5% of reserves) across every
  product type — an investment-grade portfolio default-risk loading
  that does not vary by liability product.
- C-3 interest rate: scales with effective reserve duration:

  | ProductType        | C-1   | C-3   |
  |--------------------|-------|-------|
  | TERM               | 0.005 | 0.005 |
  | WHOLE_LIFE         | 0.005 | 0.010 |
  | UNIVERSAL_LIFE     | 0.005 | 0.015 |
  | DISABILITY         | 0.005 | 0.005 |
  | CRITICAL_ILLNESS   | 0.005 | 0.005 |
  | ANNUITY            | 0.005 | 0.020 |

  TERM has short reserves; WL longer; UL has crediting-rate exposure
  on the account value; ANNUITY has the longest duration and the
  largest rate sensitivity. C-1 stays uniform because the asset mix
  backing life reserves does not differ materially by liability
  product in the committee-screening regime.

The constructor is purely additive — it does not change `for_product`,
`for_product_extended`, the `LICATFactors` field defaults, or any of
the existing wiring. The new `_C1_INTERIM_DEFAULT_BY_PRODUCT` and
`_C3_INTERIM_DEFAULT_BY_PRODUCT` constants live alongside the existing
C-2 default tables.

**Rationale.**
- Opt-in surface preserves backward compatibility everywhere ADR-047 /
  ADR-049 was wired. No golden baselines move; the dashboard /
  CLI / API capital tile reads the same number until a caller
  explicitly switches to `for_product_interim`.
- Uniform C-1 reflects the reality that a reinsurer backing the
  business with an investment-grade portfolio carries roughly the
  same default-risk loading regardless of the liability product. A
  cedant-specific calibration is a Phase 5.4 refinement.
- C-3 schedule mirrors the qualitative duration ordering deal
  committees expect: ANNUITY > UL > WL > TERM ≈ DI ≈ CI. The
  absolute levels (50-200 bps of reserves) are intentionally
  conservative placeholders; Phase 5.4's shock-based engine will
  replace them with KRD-driven numbers.
- Naming `for_product_interim` (not `for_product_full`) makes the
  placeholder status explicit at the call site — readers see "this is
  a stop-gap until Phase 5.4" rather than mistaking it for the
  definitive LICAT calculation.

**Out of scope.**
- **CLI / API / dashboard / Excel surfacing of `for_product_interim`.**
  All of those wire through `for_product` today. Switching them to
  `for_product_interim` would move every capital tile and every
  golden capital number — a behaviour change that needs its own ADR
  and explicit baseline regeneration. Promote as a follow-up once
  the deal committee asks for the interim factors in the standard
  output.
- **Per-cedant C-1 / C-3 calibration.** The uniform C-1 and the
  product-typed C-3 are committee-screening placeholders. A cedant
  that supplies asset portfolio composition could justify a finer
  C-1 (e.g. high-grade vs lower-grade weighted average) and a finer
  C-3 (e.g. KRD-weighted). That work belongs in the per-cedant
  calibration pipeline, not in the default schedule.
- **Phase 5.4 shock-based replacement.** This ADR explicitly stops at
  a factor placeholder. The OSFI 2024 LICAT interest-rate component
  is a parallel-shift + curve-twist shock applied to the discounted
  liability cash flows under multiple rate scenarios; implementing
  that is the Phase 5.4 asset / ALM engine and will deprecate the
  flat-factor C-3 here. The same holds for C-1 once a stochastic
  default-loss model is in place.
- **Diversification credit between C-1 / C-2 / C-3.** Capital is
  still the sum of components; LICAT's standard-formula
  diversification benefit between insurance and asset risks is a
  later refinement (already noted in ADR-065 Out of scope).

**Affected files.**
- `src/polaris_re/analytics/capital.py` (+`_C1_INTERIM_DEFAULT_BY_PRODUCT`
  and `_C3_INTERIM_DEFAULT_BY_PRODUCT` constants, +`for_product_interim`
  classmethod, module docstring refresh; ~+55 lines).
- `tests/test_analytics/test_capital.py` (+`TestForProductInterim` with
  4 parametrised + closed-form tests on the new factor schedule,
  +`TestForProductInterimBackwardCompat` with 12 parametrised tests
  confirming `for_product` and `for_product_extended` still produce
  zero C-1 / C-3, +`TestForProductInterimAppliesToCapital` with 4
  closed-form tests on the capital arithmetic; ~+170 lines).

**Impact on golden baselines.** None. The interim factors only affect
the capital number when the caller explicitly invokes
`for_product_interim`; every existing surface continues to use
`for_product(...)` and produces the same numbers as before.

---

## ADR-073: Dimension-outer transpose helpers on `PortfolioResult`

**Date:** 2026-06-07
**Status:** Accepted

**Context.** ADR-069 added `concentration_by_basis` and `hhi_by_basis`
to `PortfolioResult` keyed as `{basis: {dimension: {label: share}}}`
and `{basis: {dimension: hhi}}`. The basis-outer shape mirrors
`hhi: dict[dimension, value]` and enables iteration over the
`CONCENTRATION_BASES` tuple. PRODUCT_DIRECTION_2026-05-23 originally
proposed `concentration[dimension][weight_basis]` (dimension outer)
and the ADR-069 session log flagged the shape choice as a follow-up
for any consumer that needs to hold the dimension fixed and flip the
weight basis (e.g. a dashboard control comparing cedant concentration
under face / NAR / PV weights).

**Decision.** Add two helper methods to `PortfolioResult`:

- `concentration_by_dimension()` returns the dimension-outer transpose
  `{dimension: {basis: {label: share}}}`.
- `hhi_by_dimension()` returns the dimension-outer transpose
  `{dimension: {basis: hhi}}`.

Both are read-only helpers backed by a generic
`_transpose_basis_outer` function. The transposed mappings are
freshly constructed, but the innermost values (share dicts or HHI
floats) are returned by reference — no storage is duplicated, the
basis-outer fields remain the single source of truth.

**Rationale.** The basis-outer shape stays the canonical storage
because it matches the existing `hhi` field layout, lets
`Portfolio.run` iterate `CONCENTRATION_BASES` ergonomically, and is
what `to_dict()` and the API / Excel surfaces already emit. The
dimension-outer view is purely a consumer convenience — adding a
field would double the on-`PortfolioResult` footprint for zero
information gain and create two surfaces that could drift. A
read-only method that transposes on call is the ~5-line helper the
PRODUCT_DIRECTION follow-up scoped.

`to_dict()` is intentionally unchanged: the JSON surface remains
backward-compatible bit-for-bit, and downstream JSON consumers that
want the dimension-outer shape can run the same transpose locally
(the helper is ~3 lines of pure dict manipulation).

**Consequences.**

- `PortfolioResult` grows two methods; no new fields, no breaking
  changes. `PortfolioResultWithCapital` inherits them.
- `concentration_by_dimension()[dim][basis] is concentration_by_basis[basis][dim]`
  by reference, so callers that mutate the returned share dicts would
  also mutate the underlying field. The helper is documented as
  read-only; for callers that want an independent copy, a single-line
  `copy.deepcopy` at the call site is sufficient.
- The transposed view is well-defined even when
  `concentration_by_basis == {}` (the default for constructors that
  bypass `Portfolio.run`): it returns `{}` and matches the original.

**Impact on golden baselines.** None. `to_dict()` is untouched and
the new helpers are pure derivations from existing fields.

**Out of scope.**

- **Surfacing the transposed view in the CLI / dashboard.** ADR-070
  shipped a `--concentration-basis` flag on `polaris portfolio
  run` / `report` that picks a single basis; the dimension-outer view
  is more naturally consumed by a dashboard widget that fixes the
  dimension and flips the basis. The Streamlit dashboard portfolio
  page is itself a deferred multi-session item; the transpose helper
  will be wired in when that page lands.

**Affected files.**

- `src/polaris_re/analytics/portfolio.py` (+`_transpose_basis_outer`
  generic helper; +`concentration_by_dimension` and
  +`hhi_by_dimension` methods on `PortfolioResult`; ~+40 lines).
- `tests/test_analytics/test_portfolio.py`
  (+`TestPortfolioConcentrationByDimension` with 8 tests covering:
  top-level keys are dimensions, inner keys are bases (for both
  helpers), value preservation, round-trip via the basis-outer view,
  HHI value preservation, no storage duplication; ~+100 lines).

---

## ADR-074: Canonical valuation-date resolution — block-owned dates, no silent wall-clock fallback

**Date:** 2026-06-11
**Status:** Accepted

**Context.** The effective `ProjectionConfig.valuation_date` had three
intended sources — explicit config, the inforce block's own (validated,
uniform) policy `valuation_date`, and `date.today()` as a last resort —
but the chain was dead code everywhere: `DealConfig.valuation_date` was
declared with `default_factory=date.today`, so the field was never
`None` and every documented fallback to the block date was unreachable.
This held in `core.pipeline.build_pipeline` (docstring promised
deal → policy → today; step "policy" could never fire), in the
dashboard's `components/projection.build_projection_config` (docstring
promised "identical results on the same CSV" via the block date; the
branch was unreachable because session `deal_config` is seeded from
`DealConfig` defaults), and in the CLI parser (an omitted
`valuation_date` key became today at parse time). Only the REST API
resolved correctly (it builds `ProjectionConfig` from
`policies[0].valuation_date` directly).

Consequences observed in practice:

- **Non-reproducibility.** The same CSV + same saved assumptions priced
  differently on different calendar days, because the date-derived
  age/duration recomputation (`*_vec_at`) shifted with the wall clock.
  Measured on `data/inputs/portfolio_sample/`: +0.73% total PV drift
  between a pinned 2026-01-01 valuation and a 2026-06-10 run date.
- **Untestable by goldens.** The golden harness pins explicit dates, so
  the drifting branch was structurally outside test coverage.
- **Two notions of seasoning in one projection.** Rate lookups used
  date-derived `duration_inforce_vec_at(config.valuation_date)` /
  `attained_age_vec_at(...)` while the acquisition-cost gate used the
  stored CSV scalar `duration_inforce_vec == 0`. The stored
  `attained_age` / `duration_inforce` columns were otherwise decorative
  — editable with no effect on results — and nothing validated them
  against the dates they allegedly summarise.

**Decision.**

1. **`DealConfig.valuation_date: date | None = None`.** `None` means
   "defer to the inforce block". The wall-clock default is removed;
   every resolution chain below becomes live.
2. **One canonical resolution order, everywhere:** explicit caller
   override → deal config (CLI/YAML `deal.valuation_date`, dashboard
   widget) → the inforce block's validated uniform policy
   `valuation_date` → `date.today()`. The final fallback is reachable
   only when no block exists (e.g. generated demographic input such as
   `polaris rate-schedule demo` / the API rate-schedule endpoint),
   which is the one place a wall-clock date is semantically honest.
   `core.pipeline.build_projection_config` (no block access) keeps a
   terminal today fallback; `build_pipeline` (block access) inserts the
   block date before it. The CLI parser passes `None` through when the
   config omits the key instead of stamping today.
3. **Single notion of seasoning per projection.** The acquisition-cost
   new-business gate in `TermLife` / `WholeLife` now uses
   `duration_inforce_vec_at(config.valuation_date) == 0`, matching the
   rate-lookup arrays. For date-consistent data this is behaviour-
   identical; under re-valuation at a later date it now correctly
   treats seasoned policies as seasoned.
4. **Load-time consistency guard.** New
   `InforceBlock.validate_date_consistency()` checks, per policy, that
   the stored `duration_inforce` is within ±1 month of
   `months_between(issue_date, valuation_date)` and the stored
   `attained_age` is within ±1 year of
   `issue_age + derived_months // 12`, raising
   `PolarisValidationError` listing offending policy ids. Invoked from
   `InforceBlock.from_csv` (CLI CSV + dashboard upload path) and from
   `load_inforce`'s list-of-dicts branch. Tolerances absorb
   partial-month conventions and ANB/ALB age-rounding without letting
   real drift (months/years) through. The stored scalars are thereby
   demoted to validated ingestion provenance; projections derive both
   age and duration from `issue_date` + the resolved valuation date.

**Rationale.** Reproducibility is a precondition for auditability
(project principle #1): a pricing artifact must not depend on the day
the run button is pressed. Making the block own its valuation date
matches the existing `InforceBlock` validator (all policies must share
one date) and the API's existing behaviour, so this aligns CLI,
dashboard, and API on the strictest already-shipped semantics rather
than inventing new ones. Collapsing the seasoning notion removes the
silent disagreement between rate lookups and the expense gate. The
guard converts "decorative columns silently ignored" into a loud
ingestion failure, which is the cheapest place to catch bad CSVs.

**Consequences.**

- `polaris price` / `polaris portfolio run` on a config without
  `valuation_date` now project from the CSV's block date instead of
  the run date — results become stable across days. Configs that pin a
  date (including all golden configs) are unaffected.
- The canonical `data/inputs/portfolio_sample/` previously ran under
  `align="strict"` only because every deal silently got the run date;
  with block-date resolution its mixed CSV dates (2026-01-01 /
  2026-01-15) would make strict mode raise. The sample's DEAL_C /
  DEAL_D dates are unified to 2026-01-01 (durations preserved), making
  it an honest, reproducible strict-mode demo. The staggered sample
  (ADR-061 demo) is unaffected — its explicit YAML dates win at step 2.
- `data/inputs/demo.csv` had one internally inconsistent row
  (issue 2026-01-01, valuation 2026-04-06, stored duration 0); the
  stored duration is corrected to 3 to pass the guard.
- Test fixtures that paired `issue_date=2020-01-01` with
  `valuation_date=date.today()` and `duration_inforce=0` were
  internally inconsistent and clock-dependent; they are fixed to
  consistent, fixed dates (also making those tests deterministic).
- `st.session_state["deal_config"]["valuation_date"]` starts as `None`;
  the Assumptions-page date widget and the projection helper fall back
  to the block date exactly as their docstrings always claimed.

**Impact on golden baselines.** None. `golden_config_flat.json` pins
`valuation_date: 2026-04-01`; `data/qa/golden_inforce.csv` is
internally consistent (verified by full-tree scan) so the new guard
accepts it unchanged.

**Out of scope.**

- ~~**API-path guard.** The REST API constructs `Policy` objects
  directly (not via `load_inforce`); wiring
  `validate_date_consistency()` into the API needs an error-mapping
  decision (422 vs 500) and is deferred.~~ **Resolved same-day:** the
  guard is invoked in `_build_components`, the single `InforceBlock`
  construction site shared by every endpoint and the portfolio deal
  builder. No new error-mapping decision was needed — every endpoint
  already wraps engine work in ``except Exception →
  HTTPException(422)``, and 422 is the right status: it is what
  FastAPI emits for schema-invalid payloads, and inconsistent inforce
  data is the semantic half of the same request validation (400 stays
  reserved for malformed inputs such as unknown treaty types, 404 for
  not-found). Covered by `TestPriceDateConsistencyGuard` and
  `TestPortfolioDateConsistencyGuard`.
- **ANB vs ALB age convention.** `attained_age_vec_at` is
  age-last-birthday-flavoured (`months // 12`); the `Policy` docstring
  language and any table-convention implications are a separate
  decision. The ±1 year guard tolerance absorbs the discrepancy.
- **Re-valuation UX.** Projecting a block at a date other than its
  own valuation date remains supported via explicit config; a
  dedicated "as-of re-valuation" workflow (with re-derived durations
  surfaced to the user) is future work.

**Affected files.**

- `src/polaris_re/core/pipeline.py` (DealConfig default, resolution,
  guard call)
- `src/polaris_re/core/inforce.py` (`validate_date_consistency`,
  `from_csv` hook)
- `src/polaris_re/cli.py` (parser passes None when key absent)
- `src/polaris_re/products/term_life.py`,
  `src/polaris_re/products/whole_life.py` (derived new-business mask)
- `data/inputs/demo.csv`, `data/inputs/portfolio_sample/` (consistent
  dates), sample READMEs
- `tests/test_core/test_valuation_date.py` (resolution + guard tests),
  `tests/test_cli_streamlit_parity.py`, `tests/test_cli_config.py`
  (fixture consistency), `tests/qa/test_dashboard_flows.py`,
  `tests/test_dashboard/test_portfolio_loader.py` (QA-gap coverage)

## ADR-075: Config-driven tabular YRT rate table (`deal.yrt_rate_table_path`)

**Date:** 2026-06-13
**Status:** Accepted

**Context.** ADR-052 added tabular YRT pricing — billing ceded premiums
from a directory of `(age x duration)` rate CSVs instead of the flat /
mortality-derived rate. That table could only be reached two ways: the
`polaris price --yrt-rate-table DIR` CLI flag and the REST API's table
field. The YAML/JSON config schema (`deal` block, parsed by
`_parse_config_to_pipeline_inputs`) had no representation for it, so a
saved config could not pin a tabular YRT basis — the user had to remember
to pass the flag on every invocation, and the config was an incomplete
record of the deal. This was tracked as a promoted follow-up in
PRODUCT_DIRECTION_2026-05-23 ("`yrt_rate_table_path` field on `DealConfig`
for CLI YAML configs"; *Source: CONTINUATION_yrt_rate_table — follow-up #2*).

**Decision.** Add four optional fields to `DealConfig`, mirroring the CLI
flag set:

- `yrt_rate_table_path: Path | None = None` — directory of rate CSVs;
  `None` (default) preserves the flat-rate path.
- `yrt_rate_table_select_period: int = 3`
- `yrt_rate_table_label: str | None = None`
- `yrt_rate_table_smoker_distinct: bool = True`

`_parse_config_to_pipeline_inputs` reads these from the nested `deal`
block (the legacy flat schema is left untouched). In `price_cmd`, the
table is loaded through a new shared helper, `_load_yrt_rate_table_from_dir`,
which both the `--yrt-rate-table` flag and the config field call so the
two surfaces apply byte-identical validation, loading, and console
reporting. The flag is loaded eagerly (bad paths fail before any
projection work); the config field is resolved after config parse.

**Precedence.** When both are supplied the CLI flag wins and a one-line
`[dim]` notice is printed; the config path is not consulted. This keeps
the flag as an ad-hoc override of a saved config rather than a conflicting
second source.

**Rationale.**

- **Additive, zero behaviour change.** All four fields default to the
  flat-rate path / CLI-flag defaults, so every existing config and golden
  baseline is byte-identical. Verified by a closed-form test asserting the
  config-driven and flag-driven runs produce identical reinsurer
  `pv_premiums` / `pv_profits` and cedant `pv_profits`.
- **Path used as-is.** No relative-to-config resolution, following the
  existing `MortalityConfig.data_dir` precedent. (Relative-to-config
  resolution is a possible future refinement — see Out of scope.)
- **`DealConfig.to_dict()` intentionally unchanged.** That dict backs the
  dashboard `DEFAULTS` and the CLI/Streamlit parity surface; the dashboard
  manages its own table-upload state, so the new fields are deliberately
  omitted from it.

**Out of scope.** (1) Surfacing the field on `scenario` / `uq` CLI
commands — only `price` consumes a tabular table today; the other commands
parse the same config but would need their own loading wiring. (2)
Relative-to-config path resolution for portable config bundles. (3) A
matching YAML key on the dashboard upload flow. These are filed as
follow-ups.

**Affected files.**

- `src/polaris_re/core/pipeline.py` (`DealConfig` fields + `to_dict`
  docstring)
- `src/polaris_re/cli.py` (`_parse_config_to_pipeline_inputs` mapping,
  `_load_yrt_rate_table_from_dir` helper, `price_cmd` resolution +
  precedence)
- `tests/test_analytics/test_cli_yrt_rate_table_config.py` (parse unit
  tests + closed-form flag-vs-config equality + precedence + bad-path)

---

## ADR-076: Tabular YRT rate table in `scenario` / `uq` (`ScenarioRunner`, `MonteCarloUQ`)

**Date:** 2026-06-14
**Status:** Accepted

**Context.** ADR-075 added the `deal.yrt_rate_table_path` config field and
wired it into `polaris price` only. `polaris scenario` and `polaris uq`
parse the same `deal` config block (via `_build_pipeline_from_config`), so a
config carrying `yrt_rate_table_path` loaded cleanly there too — but the
field was then silently dropped: both commands built the treaty with
`_build_treaty_for_pipeline(inputs, gross, face_amount, inforce)`, passing
no `yrt_rate_table`. The analytics runners (`ScenarioRunner.run`,
`MonteCarloUQ._run_single`) projected at the aggregate level
(`engine.project()`) and applied the treaty without an `InforceBlock`. A
config that referenced a tabular YRT basis was therefore priced on the
*flat* mortality-derived rate instead — no error, just a wrong number.
Reproduced before the fix: the same config priced reinsurer
`pv_profits = 10645.36` under `price` (table honoured) but the `scenario`
BASE moved to a flat-rate value, confirming the silent drop. Tracked as
ADR-075 Out-of-scope follow-up #1.

**Scope correction.** The PRODUCT_DIRECTION entry for this follow-up listed
only `cli.py (scenario_cmd, uq_cmd), tests` as affected. That was
incomplete: the tabular YRT path requires a *seriatim* projection
(`gross.seriatim_lx` / `seriatim_reserves`) plus the `InforceBlock` passed
into `YRTTreaty.apply`, and the analytics runners did neither. The fix
therefore also touches `analytics/scenario.py` and `analytics/uq.py`. This
correction was verified by reproduction before any code was written.

**Decision.** Teach both runners to detect a tabular YRT treaty and switch
to the seriatim path — the exact pattern `cli._price_single_cohort` already
uses:

```python
needs_seriatim = getattr(self.treaty, "yrt_rate_table", None) is not None
gross = engine.project(seriatim=needs_seriatim)
net, _ = self.treaty.apply(gross, inforce=self.inforce) if needs_seriatim \
    else self.treaty.apply(gross)
```

`getattr` duck-typing means coinsurance / modco / flat-YRT treaties (no
`yrt_rate_table` attribute, or `None`) take `needs_seriatim = False`, so
`project(seriatim=False)` (the default) and `apply(gross)` are byte-identical
to the prior aggregate path. In the CLI, `scenario_cmd` / `uq_cmd` resolve
the config table through a new shared helper, `_resolve_config_yrt_rate_table`,
which calls the existing `_load_yrt_rate_table_from_dir` (same validation,
loading, and console reporting as `price`). The CLI-level `gross` used for
the parity-debug dump is projected seriatim when a table is present so the
diagnostic matches the real projection.

**Rationale.** This is a correctness fix — a saved deal config is meant to
be a complete record, and ADR-075 made `yrt_rate_table_path` part of that
record. Honouring it everywhere `price` honours it removes a silent
flat-vs-tabular discrepancy. Backward compatibility is total: the flat /
proportional path is unchanged byte-for-byte (golden regression exit 0;
1274 prior tests unchanged). The closed-form anchor is the BASE / base-case
identity: with unit stress multipliers the runner's first scenario
reproduces a direct seriatim projection + tabular apply + profit test to
`rtol=1e-12`.

**Out of scope (filed as follow-ups).** (1) A `--yrt-rate-table` CLI *flag*
on `scenario` / `uq` to match `price`'s flag-and-config parity (config-only
here closes the stated silent-drop gap; the flag is additive). (2) The
reinsurer-vs-cedant profit-test convention: `ScenarioRunner` / `MonteCarloUQ`
profit-test the cedant `net` position, whereas `price` reports the reinsurer
view — pre-existing and unchanged here, but worth a deliberate decision.
(3) Relative-to-config path resolution (carried from ADR-075).

**Affected files.**

- `src/polaris_re/analytics/scenario.py` (`ScenarioRunner.run` seriatim branch)
- `src/polaris_re/analytics/uq.py` (`MonteCarloUQ._run_single` seriatim branch)
- `src/polaris_re/cli.py` (`_resolve_config_yrt_rate_table` helper;
  `scenario_cmd` / `uq_cmd` table resolution + seriatim parity projection)
- `tests/test_analytics/test_scenario_uq_yrt_rate_table.py` (closed-form
  BASE / base-case identity + tabular-vs-flat differential + CLI config
  integration + bad-path)

## ADR-077: Reinsurer-vs-cedant profit-test perspective in `scenario` / `uq`

**Date:** 2026-06-14
**Status:** Accepted

**Context.** `ScenarioRunner.run` and `MonteCarloUQ._run_single` profit-test
the cedant `net` position: `treaty.apply()` returns `(net, ceded)` and both
runners took `net`. By contrast `polaris price` reports the *reinsurer* view
— the ceded cash flows re-viewed as NET via `ceded_to_reinsurer_view`
(ADR-039). On a reinsurer-facing pricing tool the scenario / UQ PV and IRR
therefore described the cedant's retained book, not the reinsurer's — a
surprise on the primary use case (flagged in ADR-076 Out-of-scope #2 and
promoted to PRODUCT_DIRECTION as an IMPORTANT follow-up). Reproduced before
the fix: an 80% coinsurance deal gave a `ScenarioRunner` BASE
`pv_profits = 5,716.78` (the cedant's retained 20%) while the reinsurer's
ceded 80% economics were `22,867.13` — ~4x apart. A 50% coinsurance is
degenerate (net == ceded), which is why the pre-existing
`test_base_matches_direct_profit_test` (50% cession) never surfaced the gap.

**Decision.** Add an additive `perspective: Literal["reinsurer", "cedant"]`
parameter to both runners, plus a shared `select_perspective_cashflows(perspective,
net, ceded)` helper. `"reinsurer"` profit-tests `ceded_to_reinsurer_view(ceded)`;
`"cedant"` profit-tests `net`. When `ceded is None` (UQ with no treaty) the
reinsurer view is undefined, so the gross cash flows are used for both. The
runner default is **`"cedant"`** — this keeps the library API byte-identical
for every existing programmatic caller and every existing test (no test
assertion was changed). The `scenario` / `uq` *CLI commands* default to
**`"reinsurer"`** via a new `--perspective` flag, so the opinionated product
surface agrees with `polaris price`. `ScenarioResult` / `UQResult` and the CLI
JSON now carry the `perspective` that produced them.

**Rationale.** The library stays a neutral primitive (cedant net is the
literal `treaty.apply()[0]`), while the CLI — like `price` — is the
reinsurer-facing surface and so defaults to the reinsurer view. Splitting the
defaults this way fixes the user-facing correctness gap (the CLI is where the
"surprise" actually manifests) while preserving total backward compatibility
at the library level, honouring the "never change existing test assertions"
guardrail. The closed-form anchors are the BASE / base-case identities:
`perspective="reinsurer"` reproduces `ProfitTester(ceded_to_reinsurer_view(ceded))`
and `perspective="cedant"` reproduces `ProfitTester(net)` to `rtol=1e-12`. No
golden / QA baseline moved — the golden suite pins only `price` outputs
(`golden_flat.json`, `golden_yrt.json`); scenario / uq are not numerically
pinned, and the one CLI scenario QA test asserts mixed-block rejection only.

**No-treaty handling.** `scenario` builds a zero-cession YRT fallback so the
runner always has a treaty; `uq` accepts `treaty=None` directly. In both, when
the config carries no real treaty a requested `reinsurer` perspective is
downgraded to `cedant` with a console notice ("reinsurer view not available"),
mirroring `price`. The effective perspective is always printed.

**Out of scope (filed as follow-ups).** (1) The FastAPI scenario / UQ
endpoints (`POST /api/v1/scenario`, `/uq`) and the Streamlit dashboard
scenario / UQ views still report the cedant `net` view — same correctness gap,
other surfaces. They can pass `perspective="reinsurer"` to the runners now;
deferred here to keep the PR to the harvested item's stated scope
(analytics + CLI). (2) `Portfolio.run_scenarios` aggregates per-deal `net`
positions and is unaffected by this change; whether portfolio scenario output
should also move to the reinsurer view is a separate question.

**Affected files.**

- `src/polaris_re/analytics/scenario.py` (`Perspective` alias,
  `select_perspective_cashflows`, `ScenarioRunner.perspective`,
  `ScenarioResult.perspective`)
- `src/polaris_re/analytics/uq.py` (`MonteCarloUQ.perspective`,
  `UQResult.perspective`)
- `src/polaris_re/cli.py` (`_resolve_cli_perspective` helper; `--perspective`
  flag + effective-perspective resolution on `scenario_cmd` / `uq_cmd`)
- `tests/test_analytics/test_scenario_uq_perspective.py` (closed-form
  reinsurer / cedant BASE identities + non-half-cession differential +
  no-treaty fallback + invalid-value + CLI integration)

---

## ADR-078: Reinsurer-vs-cedant perspective on the scenario / UQ API + dashboard surfaces

**Date:** 2026-06-15
**Status:** Accepted

**Context.** ADR-077 added the additive `perspective` parameter to
`ScenarioRunner` / `MonteCarloUQ` (library default `cedant`) and defaulted the
`scenario` / `uq` **CLI** commands to the reinsurer view so they agree with
`polaris price`. It deliberately left two other product surfaces on the old
cedant `net` view: the FastAPI endpoints `POST /api/v1/scenario` and
`/api/v1/uq`, and the Streamlit dashboard Scenario / Monte Carlo UQ pages.
Both constructed the runners without passing `perspective`, so they inherited
the library `cedant` default — the same primary-use-case correctness gap the
CLI fix addressed, on the other surfaces. Reproduced before the fix: an 80%
coinsurance deal returned `POST /api/v1/scenario` BASE `pv_profits = 897.03`
(the cedant's retained 20%) while the reinsurer's ceded 80% economics were
`3,588.14` — ~4x apart. (A 50% cession is degenerate, net == ceded.)

**Decision.** Surface the existing `perspective` mechanism on both surfaces,
defaulting to **`reinsurer`** to match `price`, the CLI, and the other product
frontends:

- **API** — add an optional `perspective: Literal["reinsurer", "cedant"]`
  field (default `"reinsurer"`) to `ScenarioRequest` and `UQRequest`, pass it
  to the runner, and echo the *effective* perspective on `ScenarioResponse` /
  `UQResponse` (new additive field). A shared `_resolve_api_perspective`
  helper downgrades `reinsurer → cedant` when no treaty is configured (the
  reinsurer view is undefined), mirroring `price` and the CLI. An invalid
  value is rejected by Pydantic as `422` before the handler runs.
- **Dashboard** — add a "Profit-test perspective" `st.selectbox` (default
  "Reinsurer (ceded economics)") to the Scenario and UQ pages, pass the mapped
  value to the runner, and print the effective perspective the result reports
  back as a caption above the results. The dashboard always builds a real YRT
  treaty (cession ≥ 50%), so no downgrade path is exercised there.

**Rationale.** The mechanism and its closed-form anchors already existed
(ADR-077); this ADR is pure surfacing. Defaulting both surfaces to `reinsurer`
makes every reinsurer-facing frontend (price, CLI scenario/uq, API, dashboard)
report the same economic view, removing the cross-surface inconsistency. The
library runner default stays `cedant`, so every programmatic caller and every
existing test is byte-identical (no test assertion changed). No golden / QA
baseline moved: the golden suite pins only `price`, and the existing API
scenario / uq tests assert schema and distribution ordering (var ≤ median,
cvar ≤ var, percentile monotonicity) — all of which still hold for the
reinsurer view — not pinned PV numbers.

**Backward-compatibility note.** This *is* a behaviour change on the API and
dashboard surfaces: a client that omits `perspective` now receives the
reinsurer view where it previously received the cedant view. The change is
deliberate (consistency with `price` / CLI) and is made discoverable by the
new `perspective` field echoed in every response and the dashboard caption. A
client wanting the prior numbers passes `perspective="cedant"`.

**Out of scope (filed as follow-ups).** `Portfolio.run_scenarios` and its CLI
/ API / dashboard surfaces still aggregate per-deal `net` — already tracked as
the NICE-TO-HAVE "Reinsurer-vs-cedant perspective on `Portfolio.run_scenarios`"
follow-up (ADR-077 Out of scope #2); unchanged here.

**Affected files.**

- `src/polaris_re/api/main.py` (`perspective` field on `ScenarioRequest` /
  `UQRequest` and `ScenarioResponse` / `UQResponse`; `_resolve_api_perspective`
  helper; wiring in the `scenario` / `uq` endpoints)
- `src/polaris_re/dashboard/views/scenario.py`,
  `src/polaris_re/dashboard/views/uq.py` (perspective selectbox + runner wiring
  + effective-perspective caption)
- `tests/test_api/test_scenario_uq_perspective.py` (default-reinsurer,
  cedant-vs-reinsurer differential at 80% cession, closed-form match to a
  direct runner, invalid-value `422`, no-treaty downgrade — for both endpoints)
- `tests/qa/test_dashboard_flows.py::TestScenarioUQPerspective` (selector
  present, default reinsurer, cedant selection threads through to the runner)

## ADR-079: Ad-hoc `--yrt-rate-table` flag on `scenario` / `uq`

**Date:** 2026-06-15
**Status:** Accepted

**Context.** `polaris price` exposes an ad-hoc `--yrt-rate-table DIR` flag (plus
`--yrt-rate-table-select-period`, `--yrt-rate-table-label`,
`--yrt-rate-table-smoker-distinct/--yrt-rate-table-aggregate`) for loading a
tabular age x duration YRT rate table without a config file, and applies a
flag-over-config precedence against the YAML/JSON `deal.yrt_rate_table_path`
field (ADR-075). ADR-076 wired the *config field* into `scenario` and `uq` (so a
config referencing a table is no longer silently dropped) but, unlike `price`,
neither command exposed the ad-hoc flag. A user wanting to run scenario / UQ
analysis on a tabular YRT basis therefore had to author a YAML config; passing
`--yrt-rate-table DIR` was rejected (`No such option: --yrt-rate-table`),
leaving the three table-capable commands with an inconsistent loading surface.

**Decision.** Add the same four `--yrt-rate-table*` options to `scenario_cmd`
and `uq_cmd`, mirroring `price` exactly (option names, defaults, help). The flag
is loaded eagerly via the shared `_load_yrt_rate_table_from_dir` helper before
any projection work (so a bad path fails fast with exit 1), and a new shared
helper `_resolve_yrt_rate_table_flag_over_config(flag_table, inputs)` applies the
flag-over-config precedence used by `price`: an explicitly supplied flag table
wins (with a console notice when `deal.yrt_rate_table_path` is also present),
otherwise it falls back to `_resolve_config_yrt_rate_table` (ADR-076).

**Rationale.** Purely additive surfacing of an existing mechanism — no new
loading, validation, or projection logic. It gives `price`, `scenario`, and `uq`
a uniform table-loading surface, which is the natural completion of the
ADR-075 / ADR-076 family. The default (no flag) path is byte-identical to the
ADR-076 behaviour: when the flag is omitted the commands resolve exactly the
config field as before, so every existing test and every config-only invocation
is unchanged. No core data contract is touched and no golden / QA baseline
moves (the golden suite pins only `price`).

**Out of scope (filed as follow-ups).** Relative-to-config path resolution for
`yrt_rate_table_path` (ADR-075 Out of scope, still open) and the dashboard
table-upload round-trip of `deal.yrt_rate_table_path` (ADR-075 Out of scope,
still open) are unchanged here.

**Affected files.**

- `src/polaris_re/cli.py` (`--yrt-rate-table*` options on `scenario_cmd` /
  `uq_cmd`; eager flag load; `_resolve_yrt_rate_table_flag_over_config` helper;
  precedence wiring replacing the bare `_resolve_config_yrt_rate_table` call in
  both commands)
- `tests/test_analytics/test_scenario_uq_yrt_rate_table.py`
  (`TestScenarioCommandTabularYRTFlag`, `TestUQCommandTabularYRTFlag`: flag
  loads the table, flag == config field closed-form `rtol=1e-12`, flag overrides
  config field, bad path exits 1 — for both commands)

## ADR-080: Gross / Ceded cash-flow sheets in the deal-pricing workbook

**Date:** 2026-06-15
**Status:** Accepted

**Context.** `write_deal_pricing_excel` (ADR-045) renders a single annual
cash-flow rollup sheet, "Cash Flows", from `DealPricingExport.net_cashflows` —
the NET (cedant-retained) basis. The `DealPricingExport` DTO already carried
optional `gross_cashflows` and `ceded_cashflows` fields, and the CLI already
populates them on every `polaris price` run (`cli.py` builds the export with
`gross_cashflows=cohort.gross_cashflows`, `ceded_cashflows=cohort.ceded_cashflows`),
but no sheet consumed them. A deal committee reviewing a ceded block wants the
gross business, the reinsurer's ceded share, and the cedant's retained net side
by side; only the net side was reaching the workbook. The follow-up offered a
binary choice: write the sheets, or drop the unused DTO fields
(`CONTINUATION_deal_pricing_excel` — Open Question #2).

**Decision.** Write the sheets. When `export.gross_cashflows` is populated, emit
a "Gross Cash Flows" sheet; when `export.ceded_cashflows` is populated, emit a
"Ceded Cash Flows" sheet. Both use the identical annual-rollup layout
(`_CASH_FLOW_COLUMNS`, via the shared `_aggregate_monthly_to_annual` helper) as
the NET "Cash Flows" sheet, so the three read consistently. `_write_cash_flows_sheet`
was refactored from `(_, export)` to `(_, cashflows, title)` so one builder
serves all three bases. Sheet order is Summary → Gross → Ceded → Cash Flows
(Net) → Assumptions → [Sensitivity] → [YRT Rate Table]: the committee reading
order is the Gross / Ceded / Net waterfall (Net = Gross − Ceded), and the NET
sheet keeps its canonical "Cash Flows" title.

**Rationale.** Additive surfacing of data already flowing into the export. Each
new sheet is suppressed when its DTO field is `None`, so a net-only export (the
synthetic-fixture path, and any caller that does not set the optional fields)
produces a byte-identical workbook — every existing exact-`sheetnames`
assertion in `tests/test_utils/test_excel_output.py` stays green. The golden CLI
workbook test (`tests/qa/test_cli_golden.py::TestCLIExcelOut`) asserts a superset
of sheet names, so the new sheets are tolerated there. No core data contract is
touched (the DTO fields already existed and are unchanged), no pricing math is
touched, and no golden / QA baseline moves (the golden suite pins only the
`price` JSON, which is unchanged).

**Behaviour change.** A real `polaris price --excel-out` run now emits "Gross
Cash Flows" and "Ceded Cash Flows" sheets in addition to the existing "Cash
Flows" (Net) sheet (Ceded only when the deal has a treaty). This is the intended
deal-committee-visible improvement; consumers that parse the workbook by sheet
name are unaffected (the "Cash Flows" sheet is unchanged in name, layout, and
contents).

**Out of scope (filed as follow-ups).** A per-sheet perspective caption /
title cell clarifying that "Net Cash Flow" on the Ceded sheet is the reinsurer's
ceded net (rather than adding a label, the sheet title carries the basis); and a
fourth combined sheet placing Gross / Ceded / Net columns side by side for direct
visual differencing. Neither is needed for the three-sheet deliverable.

**Affected files.**

- `src/polaris_re/utils/excel_output.py` (`write_deal_pricing_excel` dispatcher
  writes Gross / Ceded sheets when populated; `_write_cash_flows_sheet`
  refactored to `(wb, cashflows, title)`; module / DTO / writer docstrings)
- `tests/test_utils/test_excel_output.py` (`TestGrossCededCashFlowSheets`:
  sheets absent when fields None, present + ordered when populated, gross-only
  when ceded None, each sheet carries its own basis — parametrized closed-form
  check that no cross-wiring occurs, gross > net sanity; `_make_cashflows` gains
  a `scale` parameter and a `three_basis_export` fixture)

---

## ADR-081: Combined Gross / Ceded / Net cash-flow comparison sheet

**Date:** 2026-06-16
**Status:** Accepted

**Context.** ADR-080 added separate "Gross Cash Flows" / "Ceded Cash Flows"
sheets next to the NET "Cash Flows" sheet in the deal-pricing workbook. A
committee verifying the treaty waterfall (Net = Gross − Ceded per year) must
read three separate sheets and diff the corresponding rows by hand. ADR-080
filed the combined side-by-side sheet as an explicit out-of-scope follow-up,
which `PRODUCT_DIRECTION_2026-05-23.md` promoted as a NICE-TO-HAVE.

**Decision.** Add a "Cash Flow Comparison" sheet, written only when BOTH
`export.gross_cashflows` and `export.ceded_cashflows` are populated (a
comparison is meaningless with a missing basis). It places the per-year Net
Cash Flow of all three bases side by side — columns `Year | Gross | Ceded |
Net | Gross - Ceded` — where the trailing `Gross - Ceded` column is a visual
check that equals the `Net` column by construction (`treaty.apply` returns
`net = gross − ceded`). Annual rollups reuse the same
`_aggregate_monthly_to_annual` helper as the basis sheets, so the Year axis
and per-year values match those sheets exactly. The sheet follows the NET
"Cash Flows" sheet: Summary → Gross → Ceded → Cash Flows (Net) → Cash Flow
Comparison → Assumptions → [Sensitivity] → [YRT Rate Table].

**Rationale.** Purely additive surfacing of data already on the export; no
new DTO field, no core contract change, no pricing math, no CLI change. The
sheet is suppressed unless both ceded-side bases are present, so net-only and
gross-only exports stay byte-identical (every existing exact-`sheetnames`
assertion stays green). The golden CLI workbook test asserts a superset of
sheet names, so the new sheet is tolerated there; the golden suite pins only
the `price` JSON, which is unchanged. The closed-form `Gross - Ceded == Net`
identity is verified per year in the test suite, reproduced on the golden
config before implementation.

**Behaviour change.** A real `polaris price --excel-out` run on a deal with a
treaty (which populates both gross and ceded) now emits a "Cash Flow
Comparison" sheet in addition to the ADR-080 basis sheets. Consumers that
parse the workbook by sheet name are unaffected (existing sheets are unchanged
in name, layout, and contents).

**Out of scope (filed as follow-ups).** A richer comparison that breaks down
each cash-flow line item (premiums, claims, expenses, reserves) across the
three bases rather than only the Net Cash Flow waterfall; and the still-open
ADR-080 follow-up of a per-sheet perspective caption on the Ceded sheet.
Neither is needed for the Net = Gross − Ceded waterfall this sheet delivers.

**Affected files.**

- `src/polaris_re/utils/excel_output.py` (`write_deal_pricing_excel`
  dispatcher writes the comparison sheet when both ceded-side bases are
  populated; new `_write_cash_flow_comparison_sheet` builder and
  `_CASH_FLOW_COMPARISON_COLUMNS`; module / DTO / dispatcher docstrings)
- `tests/test_utils/test_excel_output.py` (`TestCashFlowComparisonSheet`:
  absent when net-only / ceded-missing, present when all three bases, exact
  column layout, row count, columns match the basis sheets, and the
  closed-form `Gross - Ceded == Net` identity; updated the ADR-080 ordering
  assertion to include the new sheet)

## ADR-082: Premium-sufficiency (gross-premium-adequacy) analyzer

**Date:** 2026-06-16
**Status:** Accepted

**Context.** `PRODUCT_DIRECTION_2026-05-23.md` carried "Premium sufficiency
testing" (a NICE-TO-HAVE from `PRODUCT_DIRECTION_2026-04-19`): *does the
cedant's premium cover expected claims + expenses + target margin?* — useful
for "is this deal pre-priced well" commentary at the screening stage. The
engine had no such analyzer. `ProfitTester` measures economic profit but
includes the reserve movement and discounts at a profit hurdle, so it answers
a different question; `CashFlowResult.loss_ratio()` exists but is undiscounted
and claims-only (it ignores surrenders, expenses, and the time value of
money). Reproduced before building: no `analytics/` module computes a
present-value loss / expense / combined ratio or a sufficiency verdict.

**Decision.** Add `analytics/premium_sufficiency.py` with a
`PremiumSufficiencyTester(cashflows, discount_rate, *, target_margin=0.0)` and
a `PremiumSufficiencyResult` dataclass. It compares the PV of premiums against
the PV of benefits + expenses, deliberately **excluding the reserve
movement**:

    sufficiency_margin = PV(premiums) - PV(benefits) - PV(expenses)

where `PV(benefits) = PV(death_claims + lapse_surrenders)`. It reports the
present-value loss / expense / combined ratios and the verdict
`is_sufficient ⇔ sufficiency_ratio (= 1 − combined_ratio) >= target_margin`.
Discounting uses the established monthly convention `v = (1+rate)**(-1/12)`,
factors `v ** [1..T]` — identical to `ProfitTester` and
`CashFlowResult.pv_premiums`.

**Rationale.**
- *Reserve exclusion.* A reserve increase is a balance-sheet timing item that
  reverses over the life of the block; it is not an economic cost of the
  coverage. Premium *adequacy* is a gross-premium-valuation comparison of
  premium against benefit + expense outflow, so the reserve line is excluded.
  This is what distinguishes the analyzer from `ProfitTester` (which keeps
  `ΔReserve` in `net_cash_flow`). A dedicated test asserts injecting a reserve
  movement leaves the sufficiency result unchanged.
- *Basis-agnostic.* Unlike `ProfitTester` (which rejects CEDED), the analyzer
  accepts any basis. On a GROSS result it asks "is the cedant's direct premium
  adequate"; on a reinsurer-view NET result (the basis `polaris price`
  reports) it asks "is the reinsurance premium adequate for the risk assumed"
  — both first-class questions on a reinsurer-facing tool.
- *Ratio None-guard.* Ratios are `None` when `pv_premiums <= 0` (mirrors the
  `ProfitTester.profit_margin` guardrail; a ratio with a non-positive premium
  denominator is not interpretable), and `is_sufficient` is `False` in that
  case.
- *`target_margin` validation.* Constrained to `[0, 1)` — it is a profit
  margin expressed as a fraction of premium. Default `0.0` tests bare cost
  coverage.

**Library-only (no surface wiring).** This slice ships the analytics primitive
fully tested. It is not yet wired into the CLI, REST API, Streamlit dashboard,
or the deal-pricing Excel workbook — surfacing is filed as a follow-up so the
primitive lands isolated and low-risk, with no golden / QA reference moved (the
golden suite pins only `polaris price`, whose output is byte-identical).

**Out of scope (filed as follow-ups).** Surfacing the sufficiency ratios on
the CLI (`price` summary / a dedicated command), the REST API, the dashboard
pricing page, and a panel on the Excel Summary sheet; and an optional
premium-deficiency reserve / loss-recognition extension (when the combined
ratio exceeds 1, the deficiency could feed a reserve floor). Neither is needed
for the screening-stage adequacy verdict this analyzer delivers.

**Affected files.**

- `src/polaris_re/analytics/premium_sufficiency.py` (new module:
  `PremiumSufficiencyTester`, `PremiumSufficiencyResult`)
- `src/polaris_re/analytics/__init__.py` (export both names in `__all__`)
- `tests/test_analytics/test_premium_sufficiency.py` (closed-form flat-block
  ratios at rate 0, exact `v**12` discounting, ratio identities
  `combined = loss + expense` and `sufficiency = 1 − combined`, parametrized
  `target_margin` verdict incl. boundary, insufficient-block negative margin,
  zero-premium None-guard, invalid-`target_margin` rejection, basis-agnostic
  CEDED input, reserve-exclusion invariance, and a TermLife GROSS integration
  coherence check)

## ADR-083: Surface premium-sufficiency across CLI / API / dashboard / Excel

**Date:** 2026-06-16
**Status:** Accepted

**Context.** ADR-082 shipped `PremiumSufficiencyTester` as a library primitive
only; no user-facing surface consumed it, so the deal-screening value ("is this
deal pre-priced well?") was not actually reachable. The ADR-082 follow-up
"Surface premium-sufficiency ratios on the product surfaces" was promoted into
`PRODUCT_DIRECTION_2026-05-23.md`. The maintainer asked to wire all four
surfaces.

**Decision.** Surface premium sufficiency on the deal-pricing path of every
consumer, computed from the cash flows the profit test already uses — no
re-projection:

- **CLI (`polaris price`)** — a "Premium Sufficiency" Rich table per cohort
  (cedant + reinsurer), a `premium_sufficiency` block in the JSON output
  (per-cohort, and top-level for single-cohort runs mirroring the existing
  `cedant`/`reinsurer` back-compat block), and a new
  `--sufficiency-target-margin` option.
- **REST API (`POST /api/v1/price`)** — an optional `sufficiency_target_margin`
  request field and always-populated `premium_sufficiency` /
  `reinsurer_premium_sufficiency` response blocks.
- **Dashboard (Deal Pricing page)** — "Premium Sufficiency" metric tiles
  (combined / loss ratio, sufficiency margin, verdict) under the cedant and
  reinsurer views, plus a target-margin number input.
- **Excel (deal-pricing workbook)** — a "Premium Sufficiency" panel appended to
  the Summary sheet (cedant column always; reinsurer column when a reinsurer
  result + sufficiency are present), driven by two optional
  `DealPricingExport` fields.

Both views are computed: the cedant view on the NET cash flows, the reinsurer
view on the ceded cash flows re-viewed as NET (`ceded_to_reinsurer_view`),
mirroring the established dual profit-test layout. With no treaty the reinsurer
view mirrors the cedant view (matching the existing API behaviour).

**Rationale.**
- *Discount rate = valuation rate, not the profit hurdle.* Each surface feeds
  the analyzer the deal's valuation `discount_rate` (CLI/dashboard:
  `config.discount_rate`; API: `request.discount_rate`), NOT the profit
  `hurdle_rate`. Premium adequacy is a gross-premium-valuation comparison of
  premium against benefit + expense outflow (ADR-082), not a cost-of-capital
  test, so the valuation rate is the correct basis. This is documented on every
  surface's help text / field description.
- *No golden regeneration.* The CLI/pipeline golden harness builds its own
  metric dict from pricing math (unchanged) and the CLI golden test is purely
  structural; the price JSON gains additive keys only. The golden suite pins
  only `polaris price` numeric pricing output, which is byte-identical
  (verified: reinsurer total PV $45,386 unchanged). No baseline was
  regenerated.
- *Backward compatible everywhere.* The API blocks are additive (existing
  schema tests use `issubset`); the Excel panel is suppressed when the new DTO
  fields are `None`, so pre-ADR-083 workbooks are byte-identical; the CLI JSON
  only gains keys; the dashboard tiles are additive. `target_margin` defaults
  to 0.0 (bare cost coverage) and is validated to `[0, 1)` on every surface
  (CLI → `typer.BadParameter`/exit 1; API → 422; analyzer → `ValueError`).

**Out of scope (filed as follow-ups).** Surfacing sufficiency on the
`scenario` / `uq` commands and on the portfolio surfaces; a per-line-item
(premiums / claims / expenses) sufficiency breakdown rather than the aggregate
ratios; and the premium-deficiency-reserve extension already filed under
ADR-082. None is needed for the deal-screening verdict this PR delivers.

**Affected files.**

- `src/polaris_re/cli.py` (`--sufficiency-target-margin` option;
  `_compute_cohort_sufficiency`, `_sufficiency_to_dict`,
  `_render_sufficiency_table`, `_render_cohort_sufficiency_tables`; JSON +
  Excel-export wiring)
- `src/polaris_re/api/main.py` (`sufficiency_target_margin` request field;
  `premium_sufficiency` / `reinsurer_premium_sufficiency` response fields;
  `_sufficiency_block`; handler wiring)
- `src/polaris_re/dashboard/views/pricing.py` (target-margin input;
  `CohortPricingData` fields; `_render_sufficiency_tiles`; run + render wiring)
- `src/polaris_re/utils/excel_output.py` (`DealPricingExport`
  `premium_sufficiency_cedant` / `_reinsurer` fields; `_SUFFICIENCY_METRICS`;
  `_write_sufficiency_cell`; Summary-sheet panel)
- Tests: `tests/test_api/test_price_sufficiency.py`,
  `tests/test_analytics/test_cli_premium_sufficiency.py`,
  `tests/test_utils/test_excel_output.py::TestPremiumSufficiencyPanel`,
  `tests/qa/test_dashboard_flows.py` (sufficiency tile + input tests)

---

## ADR-084: Per-line-item premium-sufficiency breakdown on Excel + dashboard

**Date:** 2026-06-17
**Status:** Accepted

**Context.** ADR-083 surfaced the aggregate premium-sufficiency ratios (loss /
expense / combined) plus the verdict on all four product surfaces, but reported
benefits only as the single `PV Benefits` line (Excel) or not at all (dashboard
tiles showed ratios + margin + verdict). A deal committee reading the combined
ratio cannot see *where* the cost concentrates — death claims versus lapse
surrenders versus expenses — without re-deriving it. The
`PremiumSufficiencyResult` (ADR-082) already carries every component
(`pv_premiums`, `pv_claims`, `pv_surrenders`, `pv_benefits`, `pv_expenses`), so
exposing the breakdown is presentation-only. Filed as the ADR-083 out-of-scope
follow-up "Per-line-item premium-sufficiency breakdown" in
`PRODUCT_DIRECTION_2026-05-23.md`.

**Decision.** Break the sufficiency benefit total out into its line items on the
two surfaces where the analyzer's components are not yet visible:

- *Excel Summary panel.* Insert `PV Claims` and `PV Surrenders` rows immediately
  before the existing `PV Benefits` row in `_SUFFICIENCY_METRICS`, with cell
  writers reading `result.pv_claims` / `result.pv_surrenders`. The two rows sum
  to `PV Benefits` by construction. `PV Premiums` and `PV Expenses` are already
  on the Summary sheet (the former from the profit-test block), so they are not
  duplicated — adding a second `PV Premiums` row would collide on the
  label-based row lookup.
- *Dashboard pricing tiles.* Add a second `st.columns(4)` row under the existing
  ratio/verdict row in `_render_sufficiency_tiles` showing `PV Premiums`,
  `PV Claims`, `PV Surrenders`, `PV Expenses` — the full premium-vs-cost
  decomposition, all at the valuation discount rate the analyzer used. The
  dashboard had no PV component tiles previously, so the premium tile is added
  here (no collision; tiles are scoped per cohort view).

**Consequences.**

- *Additive / backward compatible.* The Excel panel only gains rows and is still
  suppressed entirely when `premium_sufficiency_cedant` is `None`, so net-only
  pre-ADR-083 workbooks remain byte-identical. Existing panel tests find rows by
  label (`_find_row_with_label`), not by index, so the inserted rows do not
  shift any existing assertion. The dashboard change only adds tiles.
- *No pricing-math change.* Presentation-only; reads existing
  `PremiumSufficiencyResult` fields. The golden suite pins only `polaris price`
  numeric output, which is unchanged; no baseline regenerated.

**Out of scope (filed as follow-ups).** A matching per-line-item breakdown on
the CLI Rich table / JSON block and the API response (this PR covers the Excel
and dashboard surfaces, where the gap was visible); the per-line-item
Gross / Ceded / Net cash-flow comparison (separate ADR-081 follow-up); and
extending sufficiency to the `scenario` / `uq` / portfolio surfaces (separate
ADR-083 follow-up).

**Affected files.**

- `src/polaris_re/utils/excel_output.py` (`_SUFFICIENCY_METRICS`;
  `_write_sufficiency_cell` PV Claims / PV Surrenders branches)
- `src/polaris_re/dashboard/views/pricing.py` (`_render_sufficiency_tiles`
  second tile row)
- Tests: `tests/test_utils/test_excel_output.py::TestPremiumSufficiencyPanel`
  (breakdown rows + claims+surrenders=benefits identity);
  `tests/qa/test_dashboard_flows.py` (breakdown tiles render)

## ADR-085: Per-line-item premium-sufficiency breakdown on the CLI Rich table

**Date:** 2026-06-17
**Status:** Accepted

**Context.** ADR-084 broke `PV Benefits` into its `PV Claims` / `PV Surrenders`
line items on the Excel Summary panel and the dashboard pricing tiles, and filed
an out-of-scope follow-up for "a matching per-line-item breakdown on the CLI Rich
table / JSON block and the API response." That follow-up was promoted into
`PRODUCT_DIRECTION_2026-05-23.md` ("Per-line-item premium-sufficiency breakdown
on the CLI + API surfaces") with the stated premise that the CLI
`premium_sufficiency` JSON block and the API `premium_sufficiency` response block
"still report only the aggregate ratios + margin + verdict."

**Premise correction (verified before implementing, routine step 7b).** The
premise is factually wrong on two of its three claimed surfaces. The CLI JSON
block (`_sufficiency_to_dict`) and the API response block (`_sufficiency_block`)
*already* carry the full component breakdown — `pv_premiums`, `pv_claims`,
`pv_surrenders`, `pv_benefits`, `pv_expenses` — added back at ADR-083 (PR #75,
commit ad1ba89), not deferred. A live `polaris price -o` run confirms all five
component keys in `cohorts[].premium_sufficiency.cedant`. The ADR-084
out-of-scope note conflated the human-readable CLI **Rich table** with the JSON
block; only the Rich table (`_render_sufficiency_table`) was actually missing the
split — it rendered `PV Premiums` / `PV Benefits` / `PV Expenses` but never the
`PV Claims` / `PV Surrenders` components, inconsistent with the Excel panel and
dashboard tiles. Following the entry literally would have shipped a no-op on the
JSON and API surfaces.

**Decision.** Insert `PV Claims` and `PV Surrenders` rows immediately before the
existing `PV Benefits` row in `_render_sufficiency_table`, reading
`result.pv_claims` / `result.pv_surrenders`, formatted identically to the other
monetary rows (`${:,.0f}`). The two rows sum to `PV Benefits` by construction.
This brings the CLI Rich table into line with the Excel Summary panel (ADR-084)
and the dashboard tiles. No change to the JSON block or the API response — they
already carry the breakdown.

**Consequences.**

- *Additive / backward compatible.* The table only gains two rows; the JSON
  output, the API response, and every numeric value are unchanged. Existing CLI
  sufficiency tests assert on the JSON block (by key), not the table layout, so
  none are affected.
- *No pricing-math change.* Presentation-only; reads existing
  `PremiumSufficiencyResult` fields. The golden suite pins only `polaris price`
  numeric output, which is unchanged; no baseline regenerated.

**Out of scope (filed as follow-ups).** Extending sufficiency to the `scenario` /
`uq` / portfolio surfaces (separate ADR-083 follow-up, still open). No CLI/API
JSON follow-up remains — that gap did not exist.

**Affected files.**

- `src/polaris_re/cli.py` (`_render_sufficiency_table` PV Claims / PV Surrenders
  rows)
- Tests:
  `tests/test_analytics/test_cli_premium_sufficiency.py::TestCLISufficiencyTableBreakdown`
  (breakdown rows present, ordered before PV Benefits, claims+surrenders=benefits
  identity, existing rows preserved)

## ADR-086: Per-line-item Gross / Ceded / Net comparison sheet

**Date:** 2026-06-17
**Status:** Accepted

**Context.** ADR-081 added a "Cash Flow Comparison" sheet that places the
per-year *Net Cash Flow* of the Gross / Ceded / Net bases side by side with a
`Gross - Ceded` check column. It diffs only the bottom line, so a committee
asking *where* the ceded share concentrates — which line item (premiums,
claims, surrenders, expenses, reserve increase) the cession actually moves —
must still read the three separate basis sheets (ADR-080) and diff the
corresponding rows by hand. ADR-081 filed this richer per-line-item comparison
as an explicit out-of-scope follow-up, promoted as a NICE-TO-HAVE in
`PRODUCT_DIRECTION_2026-05-23.md` ("Per-line-item Gross / Ceded / Net
comparison").

**Premise (verified before implementing, routine step 7b).** A real
`polaris price --excel-out` on the golden inputs writes a "Cash Flow
Comparison" sheet whose columns are `Year | Gross | Ceded | Net | Gross -
Ceded`, each value the per-year *Net Cash Flow* of that basis — confirmed no
per-line-item breakdown sheet exists. The `net = gross − ceded` identity was
checked to hold component-by-component (max `|Gross − Ceded − Net|` ≈ 1e-12
across all five line items on the golden TERM cohort), so the per-line-item Net
column is a sound closed-form check, not only the bottom-line total.

**Decision.** Add a "Line Item Comparison" sheet, written under the same gate
as ADR-081's comparison sheet (only when BOTH `export.gross_cashflows` and
`export.ceded_cashflows` are populated). For each of the five component line
items it places a `(Gross, Ceded, Net)` triplet side by side — header
`Year | Gross Premiums (Gross) | Gross Premiums (Ceded) | Gross Premiums (Net)
| Death Claims (Gross) | …` — so each component's three bases sit together. The
bottom-line Net Cash Flow is deliberately *excluded* (ADR-081's comparison
sheet already diffs it). Flat per-basis column headers are used instead of
merged group-header cells to keep the layout trivially testable and
parser-friendly. Annual rollups reuse the same `_aggregate_monthly_to_annual`
helper as the basis sheets, so the Year axis and per-year values match those
sheets exactly. The sheet immediately follows "Cash Flow Comparison": Summary →
Gross → Ceded → Cash Flows (Net) → Cash Flow Comparison → Line Item Comparison
→ Assumptions → [Sensitivity] → [YRT Rate Table].

**Rationale.** Purely additive surfacing of data already on the export; no new
DTO field, no core contract change, no pricing math, no CLI change. The sheet
is suppressed unless both ceded-side bases are present, so net-only and
gross-only exports stay byte-identical (every existing exact-`sheetnames`
assertion stays green except the ADR-080 ordering assertion, which was updated
to include the new sheet). The golden CLI workbook test asserts a superset of
sheet names, so the new sheet is tolerated there; the golden suite pins only
the `price` JSON, which is unchanged. The closed-form `Net == Gross − Ceded`
identity is verified per line item and per year in the test suite.

**Behaviour change.** A real `polaris price --excel-out` run on a deal with a
treaty (which populates both gross and ceded) now emits a "Line Item
Comparison" sheet in addition to the ADR-080 / ADR-081 sheets. Consumers that
parse the workbook by sheet name are unaffected (existing sheets are unchanged
in name, layout, and contents).

**Out of scope (filed as follow-ups).** A per-sheet perspective caption on the
Ceded cash-flow sheet (the still-open ADR-080 follow-up); and grouped /
merged-cell two-level headers (line-item label spanning its three basis
columns) if a committee prefers that visual grouping over the flat
`{item} ({basis})` headers chosen here. Neither is needed for the
per-line-item comparison this sheet delivers.

**Affected files.**

- `src/polaris_re/utils/excel_output.py` (`write_deal_pricing_excel`
  dispatcher writes the line-item sheet alongside the ADR-081 comparison sheet
  when both ceded-side bases are populated; new
  `_write_line_item_comparison_sheet` builder,
  `_LINE_ITEM_COMPARISON_LINE_ITEMS` and `_LINE_ITEM_COMPARISON_COLUMNS`
  constants; module / dispatcher docstrings)
- `tests/test_utils/test_excel_output.py` (`TestLineItemComparisonSheet`:
  absent when net-only / ceded-missing, present and ordered after Cash Flow
  Comparison when all three bases, exact column layout, row count, columns
  match the basis sheets, and the closed-form `Net == Gross − Ceded` identity
  per line item; updated the ADR-080 ordering assertion to include the new
  sheet)

---

## ADR-087: ReserveBasis selector + dispatch (Epic 1, Slice 1)

**Date:** 2026-06-19
**Status:** Accepted

**Context.** A reinsurer pricing an inforce block must reproduce the *cedant's*
reserve, not just the engine's single net-premium reserve. The reserve drives
the Net Amount at Risk (YRT ceded premium), the proportional reserve transfer
(coinsurance / modco), and the profit signature, so a reinsurer that cannot
reproduce the cedant's statutory/accounting basis cannot trust the profit
number. `COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md` ranks reserve-basis
matching the #1 Tier-A epic (A1, ★★★★★, ~10 dev-days) and both
`PRODUCT_DIRECTION_2026-04-19` and `PRODUCT_DIRECTION_2026-06-18` carry it as a
long-standing IMPORTANT gap. This is the first slice of that epic (see
`docs/PLAN_reserve_basis.md` / `docs/CONTINUATION_reserve_basis.md`).

**Premise (verified before implementing, routine step 7b).** Inspected every
product's `compute_reserves()`: Term and Whole Life compute a net level
premium reserve via backward recursion on the *projection* mortality; UL
returns the account value; DI returns zero. There is no `reserve_basis`
selector anywhere and `ProjectionConfig` has no such field — confirmed the
engine cannot today produce a CRVM / VM-20 / GAAP reserve. The premise holds:
exactly one reserve method exists.

**Decision.** Add a `ReserveBasis` StrEnum (`core/reserve_basis.py`, exported
from `polaris_re.core`) with members NET_PREMIUM / CRVM / VM20 / GAAP, and a
`ProjectionConfig.reserve_basis` field defaulting to NET_PREMIUM. Add a
dispatch guard on `BaseProduct`: a `_supported_reserve_bases` frozenset
(NET_PREMIUM only at this layer) plus `_check_reserve_basis()`, which returns
the active basis and raises `PolarisComputationError` when the configured
basis is not in the engine's supported set. Each product's `compute_reserves()`
calls the guard first. Concrete actuarial bases (CRVM, VM-20, GAAP) are
implemented in Slices 2–3; this slice is plumbing only.

**Rationale.** A not-yet-implemented basis **raises** rather than silently
falling back to net premium, so a pricing run can never report a reserve on a
basis the engine did not actually compute (a silent fallback would be an
auditability failure — the cardinal sin per ARCHITECTURE §1). The guard lives
on `BaseProduct` via a per-engine `_supported_reserve_bases` set that concrete
engines widen as bases land, keeping the dispatch declarative. NET_PREMIUM is
the default, so the entire change is invisible unless a caller opts in: the
default reserve recursion bodies are untouched and the golden `price` JSON is
byte-identical (verified — no rebaseline).

**Behaviour change.** None on the default path. A caller that sets
`reserve_basis` to CRVM / VM20 / GAAP now gets a clear `PolarisComputationError`
naming the supported bases and pointing at the plan, instead of the field
being silently ignored.

**Out of scope (filed as follow-ups).** The concrete CRVM basis + the
whole-life terminal-reserve acceptance test (Slice 2); VM-20 simplified
deterministic reserve (Slice 3); CLI / API / Excel / notebook surfacing of the
selector (Slice 4); and statutory bases for UL (CRVM-for-UL) and DI (GAAP DI
reserves), which this epic deliberately does not address — those engines keep
raising on non-NET_PREMIUM bases. The valuation-mortality-table design (2001
CSO is distinct from the projection table) is deferred to Slice 2, where it is
a controlled core-contract change requiring its own ADR.

**Affected files.**

- `src/polaris_re/core/reserve_basis.py` (new — `ReserveBasis` StrEnum)
- `src/polaris_re/core/projection.py` (`ProjectionConfig.reserve_basis` field)
- `src/polaris_re/core/__init__.py` (export `ReserveBasis`)
- `src/polaris_re/products/base_product.py` (`_supported_reserve_bases`,
  `_check_reserve_basis()`)
- `src/polaris_re/products/{term_life,whole_life,universal_life,disability}.py`
  (call the guard at the top of `compute_reserves()`)
- `tests/test_core/test_reserve_basis.py` (enum + config plumbing,
  serialization round-trip)
- `tests/test_products/test_reserve_basis_dispatch.py` (default == explicit
  NET_PREMIUM byte-identical; unimplemented bases raise per product)

---

## ADR-088: CRVM reserve for TermLife via Full Preliminary Term (Epic 1, Slice 2a)

**Date:** 2026-06-19
**Status:** Accepted

**Context.** Slice 1 (ADR-087) added the `ReserveBasis` selector and a dispatch
guard; every concrete actuarial basis still raised. This slice lands the first
concrete basis — **CRVM** (Commissioners Reserve Valuation Method, US statutory)
— for **TermLife**. The planned Slice 2 also covered Whole Life and the
WL terminal-reserve acceptance test, but implementing those *correctly* entangles
two genuinely separate hard problems — the prospective WL terminal reserve to
omega and the 20-pay expense-allowance cap — so Slice 2 was decomposed into
**2a (TermLife CRVM, this ADR)** and **2b (WholeLife CRVM + terminal-reserve
artefact)** rather than guess on the WL pieces (CLAUDE.md: actuarial correctness
above all; routine guardrail: decompose, don't defer; don't guess).

**Premise (verified before implementing, routine step 7b).** With
`reserve_basis=CRVM`, `TermLife.compute_reserves()` raised
`PolarisComputationError` via the slice-1 guard — confirmed the engine could not
produce a CRVM reserve. The net-premium reserve was non-trivial and positive in
early durations, so a distinct CRVM (lower early reserve) is observable.

**Decision.** CRVM for level term is implemented as **Full Preliminary Term
(FPT)**. The valuation net premium is split into a first-year premium `alpha`
and a level renewal premium `beta`, each solved on the equivalence principle
over its segment (months 0–11 vs 12–T−1):

```
alpha = APV(year-1 benefits)  / APV(year-1 annuity-due)
beta  = APV(renewal benefits) / APV(renewal annuity-due)
```

The reserve uses the existing backward recursion, deducting `alpha` in the first
12 months and `beta` thereafter. Because `alpha·ä_year1 + beta·ä_renewal`
equals the APV of all benefits, the issue reserve `0V = 0`; FPT additionally
gives a zero first-year terminal reserve (`12V = 0`), and from month 12 the
reserve equals the net premium reserve of the otherwise-identical policy issued
one year later. `TermLife._supported_reserve_bases` gains CRVM; the
`compute_reserves()` dispatch routes CRVM to `_compute_reserves_crvm()` and
leaves the NET_PREMIUM body byte-identical (extracted unchanged into
`_compute_reserves_net_premium()`).

**Rationale.** For level term the renewal valuation premium stays well below the
20-pay-whole-life expense-allowance limit, so the Commissioners cap never binds
and **FPT is exact CRVM** — no cap arithmetic is needed (and the cap would in any
case require a whole-life annuity to omega that the truncated projection horizon
cannot supply reliably; that is the WL problem deferred to 2b). FPT reserves are
uniformly at or below the net premium reserve, correctly grading in the
first-year acquisition expense allowance, which raises the early-duration Net
Amount at Risk and therefore the YRT ceded premium — the treaty layer reprices
automatically with no change, because YRT consumes `compute_reserves()` output.

**Valuation mortality basis.** CRVM here values on the **projection
(best-estimate) mortality** the engine already builds, not a distinct statutory
table. Real US CRVM prescribes 2001 CSO; wiring a separate
`valuation_mortality` table (with the attendant select/improvement questions) is
a controlled core-contract change deferred to Slice 2b / a follow-up. Documenting
this as the current simplification keeps the slice complete and honest rather
than shipping a half-wired contract change.

**Behaviour change.** None on the default path (goldens byte-identical, no
rebaseline). A caller selecting `reserve_basis=CRVM` on a TermLife block now gets
the FPT/CRVM reserve instead of a `PolarisComputationError`. WholeLife / UL / DI
still raise on CRVM.

**Out of scope (filed as follow-ups).** WholeLife CRVM and the WL prospective
terminal-reserve artefact ($7.18M→$56k); the 20-pay expense-allowance cap
(needed only for high-premium / short-pay policies, not level term); the
distinct statutory valuation mortality table (2001 CSO); VM-20 simplified (Slice
3); and selector surfacing on CLI / API / Excel / notebook (Slice 4).

**Affected files.**

- `src/polaris_re/products/term_life.py` (`_supported_reserve_bases` widened;
  `compute_reserves()` dispatch; `_compute_reserves_net_premium()`,
  `_compute_reserves_crvm()`, `_compute_crvm_modified_premiums()`)
- `tests/test_products/test_term_crvm_reserve.py` (new — equivalence principle,
  FPT identities, independent-recursion match, YRT NAR integration)
- `tests/test_products/test_reserve_basis_dispatch.py` (Term no longer raises on
  CRVM; WL still raises on all non-NET_PREMIUM bases)

## ADR-089: CRVM reserve for WholeLife via prospective-to-omega FPT (Epic 1, Slice 2b)

**Date:** 2026-06-19
**Status:** Accepted

**Context.** Slice 2a (ADR-088) landed CRVM for TermLife as Full Preliminary
Term (FPT) on the truncated projection horizon, deferring WholeLife because two
WL-specific problems entangle: (1) the WL reserve is prospective to omega, so a
recursion seeded by the historical one-period terminal estimate
`V_T = face·q_T·v` collapses near the horizon (ARCHITECTURE §4 lists this as a
known limitation), and (2) the 20-payment-whole-life expense-allowance cap can
bind for short-pay WL. This slice lands WholeLife CRVM and, as the PLAN's
folded-in named acceptance test, closes the WL terminal-reserve artefact.

**Premise (verified before implementing, routine step 7b).** On the golden WL
block ($25.5M, 6 policies, SOA VBT 2015, 6% discount, 20-year horizon) the
net-premium `reserve_balance` measured **$7,171,356 at year 10 collapsing to
$56,433 at year 20** — reproducing the documented $7.18M→$56k artefact exactly.
The collapse is the one-period terminal estimate dragging the late durations
down through the backward recursion, not genuine reserve runoff (a whole-life
per-survivor reserve must grade monotonically toward face).

**Decision.** WholeLife CRVM is computed **prospectively to omega**, independent
of the projection horizon:

1. Build a mortality-only valuation grid `q_val` out to omega (max table age)
   for the youngest in-force policy — `_build_valuation_mortality(t_val)` —
   reusing the per-(sex, smoker) lookup, substandard rating, and max-age
   forcing of `_build_rate_arrays`, but with no lapse (a per-survivor valuation
   reserve is mortality-only). Over the projection horizon `q_val` equals the
   projection `q` exactly (regression-tested).
2. Split the modified net premium into a first-year `alpha` and level renewal
   `beta` on the equivalence principle, with benefits valued to omega and the
   renewal-premium annuity restricted to the premium-paying window (so
   limited-pay concentrates `beta` while still funding the to-omega benefit).
3. Form the reserve as the per-survivor prospective value
   `V_t = [Σ_{s≥t} f_s − Σ_{s≥t} P_s·g_s] / (v^t·tpx_t)` via reverse cumulative
   sums, where `f_s`/`g_s` are the time-0 PVs of the benefit/annuity and `P_s`
   is `alpha` (months 0–11) then `beta` over the premium window.

`WholeLife._supported_reserve_bases` gains CRVM; `compute_reserves()` dispatches
CRVM to `_compute_reserves_crvm()` and leaves the NET_PREMIUM body byte-identical
(extracted unchanged into `_compute_reserves_net_premium()`).

**Result.** The CRVM reserve grades monotonically toward face and does **not**
collapse at the horizon: on the golden WL block the year-20 aggregate
`reserve_balance` rises from the net-premium $56k to ~$2.35M (>40×), and the
per-survivor aggregate increases from year 10 to year 20 rather than collapsing.
FPT gives `0V = 0` and `12V = 0`, and the first-year CRVM reserve sits below the
net-premium reserve — the first-year expense allowance graded in. The YRT layer
reprices automatically (NAR moves) with no treaty change.

**20-pay expense-allowance cap.** For whole-life pay and limited-pay ≥ 20 years
the FPT expense allowance stays at or below the 20-payment-whole-life cap, so
FPT is **exact CRVM** and no cap arithmetic is needed (the same reasoning as
Term in 2a). For premium-paying periods **< 20 years** the cap binds and FPT
would overstate the allowance; rather than ship a knowingly-uncapped reserve
mislabelled CRVM, `_compute_reserves_crvm()` raises `PolarisComputationError`
for that narrow case. Implementing the cap is filed as a follow-up.

**Valuation mortality basis.** As in 2a, CRVM values on the **projection
(best-estimate) mortality**, not a distinct statutory table (2001 CSO). The
to-omega valuation needs mortality beyond the projection horizon, which the
projection table supplies; wiring a separate `valuation_mortality` slot remains
a deferred controlled core-contract change.

**Behaviour change.** None on the default path (NET_PREMIUM goldens
byte-identical, no rebaseline). A caller selecting `reserve_basis=CRVM` on a
WholeLife block now gets the prospective FPT/CRVM reserve instead of a
`PolarisComputationError` (except short-pay WL, which still raises). UL / DI
still raise on CRVM.

**Out of scope (filed as follow-ups).** The 20-pay expense-allowance cap for
short-pay WL (CRVM currently raises there); the distinct statutory valuation
mortality table (2001 CSO); closing the artefact on the **NET_PREMIUM** basis
itself (a separate rebaseline-bearing change — this slice closes it only under
CRVM, leaving NET_PREMIUM byte-identical per the epic's golden constraint);
VM-20 simplified (Slice 3); and selector surfacing on CLI / API / Excel /
notebook (Slice 4).

**Affected files.**

- `src/polaris_re/products/whole_life.py` (`_supported_reserve_bases` widened;
  `compute_reserves()` dispatch; `_compute_reserves_net_premium()` extracted;
  `_compute_reserves_crvm()`, `_compute_crvm_modified_premiums()`,
  `_build_valuation_mortality()`, `_valuation_months_to_omega()` added)
- `tests/test_products/test_whole_life_crvm_reserve.py` (new — FPT identities,
  no-collapse / monotonicity, expense-allowance grading, omega convergence, YRT
  NAR integration, short-pay raises, NET_PREMIUM byte-identical, and the named
  golden-WL terminal-reserve acceptance test pinning $7.18M→$56k)
- `tests/test_products/test_reserve_basis_dispatch.py` (WL no longer raises on
  CRVM)
- `ARCHITECTURE.md` (§4 note that CRVM values WL prospectively to omega)

## ADR-090: VM-20 simplified reserve for TermLife (Epic 1, Slice 3a)

**Date:** 2026-06-19
**Status:** Accepted

**Context.** Slices 1–2b landed the `ReserveBasis` selector (ADR-087) and the
CRVM concrete basis for TermLife (ADR-088) and WholeLife (ADR-089). The PLAN's
Slice 3 is **VM-20 simplified** — the deterministic path of the US
principle-based reserve (VM-20 of the NAIC Valuation Manual). VM-20 sets the
minimum reserve to the greatest of the Net Premium Reserve (NPR), the
Deterministic Reserve (DR), and the Stochastic Reserve (SR); the epic scope
(PLAN §2, CONTINUATION Slice 3) is the **deterministic path only** —
`max(NPR, DR)`, no stochastic scenarios.

Slice 3 is split (as Slice 2 was) into **3a TermLife** (this ADR) and **3b
WholeLife**. The WL deterministic reserve is prospective beyond the projection
horizon, so a DR computed over the truncated grid with terminal `DR_T = 0`
collapses at the horizon edge — the same problem ADR-089 solved for the WL CRVM
via a to-omega valuation. Term has a finite horizon (the projection covers the
whole policy), so the DR is exact there; shipping Term VM-20 now avoids guessing
on the WL to-omega DR, which 3b will handle by reusing the ADR-089 machinery.

**Premise (verified before implementing, routine step 7b).** Selecting
`reserve_basis=VM20` on a TermLife block raised `PolarisComputationError` (basis
not yet implemented). The net-level-premium reserve sits above CRVM everywhere
(the first-year expense allowance), confirming the floor relationships the VM-20
`max` relies on.

**Decision.** `TermLife._supported_reserve_bases` gains VM20;
`compute_reserves()` dispatches VM20 to `_compute_reserves_vm20(q, w, v)`, which
returns `max(NPR, DR)` floored at 0:

1. **NPR** is mapped to the CRVM reserve (`_compute_reserves_crvm`): a
   net-premium reserve with the first-year expense allowance graded in, which is
   the formulaic net-premium floor VM-20 prescribes for the NPR. This reuses the
   tested Slice-2a machinery.
2. **DR** is the deterministic gross-premium reserve
   (`_compute_deterministic_reserve`): the per-in-force prospective present value
   of future death benefits and maintenance expenses less future gross premiums,
   under **both** decrements (mortality `q` and lapse `w`), via the backward
   recursion
   `DR_t = (E_t − G_t) + v·[q_t·face + (1−q_t)(1−w_t)·DR_{t+1}]`, terminal
   `DR_T = 0`. `G_t` is the monthly gross premium; `E_t` is maintenance per
   in-force policy plus the one-time acquisition cost in month 0 for genuine new
   business — both zeroed after term expiry, matching the cash flows `project()`
   emits. Lapsing policies leave with no surrender value (term has no cash
   value), so survivors of both decrements carry the only continuation value.
   The DR is **not** floored: a well-priced block has DR < 0 early (the policy is
   an asset), which is exactly what makes `max(NPR, DR)` defer to the NPR floor.

**Result.** For a well-priced block the gross premium exceeds the net premium,
so DR < NPR while the reserve builds and VM20 coincides with the CRVM floor; for
an underpriced block the realistic DR exceeds the NPR floor across the durations
and drives the reserve above it — the deficiency signal a reinsurer relies on.
The DR is pinned closed-form by an independent forward prospective-PV sum
reproducing the backward recursion (with lapse and expenses on). The YRT layer
reprices automatically: a higher VM-20 reserve lowers the NAR and the ceded
premium, with no treaty-layer change.

**NPR := CRVM simplification.** The exact VM-20 NPR has term-specific
refinements (the mortality `X` factors / select-period grading, deficiency where
the gross premium falls below the net premium, and the prescribed valuation
table) that this slice does not reproduce; mapping NPR to the CRVM reserve is the
"simplified" in "VM-20 simplified" and is documented as a follow-up. The DR is
the realistic-projection component and is exact for term over its finite horizon.

**Final-coverage-month note.** The existing net-premium / CRVM recursions leave
the final projected month at `V_{T-1} = 0` (a terminal-truncation convention).
The DR values that last coverage month properly, so for a well-priced block VM20
can exceed CRVM by a small amount in the final months purely from this
convention difference. This is the more-correct value (the policy is still in
force that month); it does not affect any golden (VM20 is opt-in).

**Behaviour change.** None on the default path (NET_PREMIUM goldens
byte-identical, no rebaseline). A caller selecting `reserve_basis=VM20` on a
TermLife block now gets `max(NPR, DR)` instead of a `PolarisComputationError`.
WholeLife (to-omega DR, Slice 3b), UL, and DI still raise on VM20.

**Out of scope (filed as follow-ups).** WholeLife VM-20 (the to-omega DR, Slice
3b); the VM-20 stochastic reserve (SR — its own multi-session epic, explicitly
excluded by PLAN §2); the exact VM-20 NPR refinements (term `X` factors,
deficiency, the prescribed 2017 CSO valuation table — the NPR := CRVM
simplification); broader DR expense components (commissions, premium tax — the DR
models maintenance + acquisition only, the expenses the engine carries); and
selector surfacing on CLI / API / Excel / notebook (Slice 4).

**Affected files.**

- `src/polaris_re/products/term_life.py` (`_supported_reserve_bases` widened;
  `compute_reserves()` dispatch captures `w` and branches VM20;
  `_compute_reserves_vm20()`, `_compute_deterministic_reserve()` added)
- `tests/test_products/test_term_vm20_reserve.py` (new — independent forward-PV
  match, expense monotonicity, `max(NPR, DR)` semantics, well-priced floor-governs
  vs underpriced DR-governs regimes, NET_PREMIUM byte-identical, YRT NAR
  integration)
- `tests/test_products/test_reserve_basis_dispatch.py` (Term no longer raises on
  VM20; WL still raises on VM20/GAAP)

## ADR-091: VM-20 simplified reserve for WholeLife via to-omega DR (Epic 1, Slice 3b)

**Date:** 2026-06-19
**Status:** Accepted

**Context.** ADR-090 shipped VM-20 simplified (`max(NPR, DR)`, deterministic path
only) for TermLife as Slice 3a, deferring WholeLife to 3b because the WL
deterministic reserve is prospective beyond the projection horizon. A DR computed
over the truncated grid with terminal `DR_T = 0` collapses at the horizon edge —
the same artefact ADR-089 solved for the WL CRVM via a prospective-to-omega
valuation. Term has a finite horizon (the projection covers the whole policy), so
its DR is exact; WL needs the to-omega treatment. This ADR completes the WL VM-20
basis.

**Premise (verified before implementing, routine step 7b).** Selecting
`reserve_basis=VM20` on a WholeLife block raised `PolarisComputationError` (basis
not yet implemented; supported bases CRVM, NET_PREMIUM). The to-omega CRVM (NPR)
reserve grades monotonically toward face (191k at yr10 → 493k at yr20 on the
probe block), confirming the floor the VM-20 `max` builds on does not collapse.

**Decision.** `WholeLife._supported_reserve_bases` gains VM20;
`compute_reserves()` dispatches VM20 to `_compute_reserves_vm20()`, which returns
`max(NPR, DR)` floored at 0, with **both** components valued to omega:

1. **NPR** is the to-omega CRVM reserve (`_compute_reserves_crvm`, ADR-089),
   reusing the tested Slice-2b machinery. It raises for short limited-pay
   (< 20 years) via the CRVM 20-pay guard, so WL VM-20 inherits that limitation.
2. **DR** is the to-omega deterministic gross-premium reserve
   (`_compute_deterministic_reserve`): the per-in-force prospective present value
   of future death benefits and maintenance expenses less future gross premiums,
   under **both** decrements (mortality `q` and lapse `w`), via the backward
   recursion `DR_t = (E_t − G_t) + v·[q_t·face + (1−q_t)(1−w_t)·DR_{t+1}]`,
   terminal `DR_{omega} = 0`. The valuation grid runs to omega
   (`_valuation_months_to_omega`, ADR-089) and the result is sliced back to the
   projection horizon, so the DR grades toward face rather than collapsing. The
   mortality grid is the existing `_build_valuation_mortality`; lapse over the
   to-omega grid is supplied by a new `_build_valuation_lapse` (duration-based
   lookup, lapse zeroed at/after max age) that matches `_build_rate_arrays` over
   the projection horizon. `G_t` is the monthly gross premium (zeroed after the
   limited-pay period); `E_t` is maintenance per in-force policy plus the
   one-time month-0 acquisition cost for genuine new business — matching the cash
   flows `project()` emits. Whole life carries no surrender value here, so
   survivors of both decrements carry the only continuation value. The DR is
   **not** floored (a well-priced block has DR < NPR, which is what makes
   `max(NPR, DR)` defer to the floor).

**Result.** For a well-priced WL block the gross premium exceeds the net premium,
so DR < NPR while the reserve builds and VM20 coincides with the CRVM floor; for
an underpriced block the realistic DR exceeds the NPR floor across the durations
and drives the reserve above it — the deficiency signal. Because the NPR grades
to face, VM20 (≥ NPR) does **not** collapse at the horizon. The DR is pinned
closed-form by an independent forward prospective-PV sum (to omega) reproducing
the backward recursion with lapse and expenses on. The YRT layer reprices
automatically: a higher VM-20 reserve lowers the NAR and the ceded premium, with
no treaty-layer change.

**NPR := CRVM simplification.** As in ADR-090, mapping the NPR to the CRVM
reserve is the "simplified" in "VM-20 simplified"; the exact VM-20 NPR
refinements (mortality `X` factors / select grading, deficiency, the prescribed
valuation table) are not reproduced and remain follow-ups. The DR is the
realistic-projection component and is valued to omega (exact in the prospective
sense, modulo the modelled expense set).

**Behaviour change.** None on the default path (NET_PREMIUM goldens
byte-identical, no rebaseline). A caller selecting `reserve_basis=VM20` on a
WholeLife block now gets `max(NPR, DR)` instead of a `PolarisComputationError`.
Short limited-pay WL (< 20 years) still raises via the CRVM guard. UL and DI
still raise on VM20.

**Out of scope (filed as follow-ups).** The VM-20 stochastic reserve (SR — its
own multi-session epic, explicitly excluded by PLAN §2); the exact VM-20 NPR
refinements (the NPR := CRVM simplification, carried from ADR-090); broader DR
expense components (commissions, premium tax — the DR models maintenance +
acquisition only); the 20-pay expense-allowance cap for short limited-pay WL
(carried from ADR-089, still required before short-pay WL CRVM/VM-20); and
selector surfacing on CLI / API / Excel / notebook (Slice 4, the final slice).

**Affected files.**

- `src/polaris_re/products/whole_life.py` (`_supported_reserve_bases` widened;
  `compute_reserves()` dispatch branches VM20; `_compute_reserves_vm20()`,
  `_compute_deterministic_reserve()`, `_build_valuation_lapse()` added)
- `tests/test_products/test_whole_life_vm20_reserve.py` (new — independent
  to-omega forward-PV match, expense monotonicity, no-collapse, `max(NPR, DR)`
  semantics, well-priced floor-governs vs underpriced DR-governs regimes,
  NET_PREMIUM byte-identical, valuation-lapse-matches-projection, short
  limited-pay raises, YRT NAR integration)
- `tests/test_products/test_reserve_basis_dispatch.py` (WL no longer raises on
  VM20; only GAAP remains unimplemented on both engines)

## ADR-092: Surface the reserve-basis selector on CLI / API / Excel / notebook (Epic 1, Slice 4)

**Date:** 2026-06-19
**Status:** Accepted

**Context.** Slices 1–3b built the reserve-basis machinery: `ProjectionConfig.reserve_basis`
(ADR-087), CRVM for Term (ADR-088) and Whole Life (ADR-089), and VM-20 simplified
for Term (ADR-090) and Whole Life (ADR-091). All of it was reachable only by
constructing a `ProjectionConfig` in Python — the CLI, the REST API, the Excel
workbook, and the validation notebooks had no way to select or report the basis.
This final slice surfaces the selector so a reinsurer can actually price a deal on
the cedant's basis from the supported entry points, and closes the epic.

**Premise (verified before implementing, routine step 7b).** `polaris price --help`
showed no `--reserve-basis` flag; the API `PriceRequest` and the Excel
`DealMetaExport` had no `reserve_basis`; a golden run reported nothing about the
basis. Confirmed the gap was a surfacing gap, not a logic gap.

**Decision.**

1. **Config / pipeline.** `DealConfig` gains a `reserve_basis: str` field
   (default `"NET_PREMIUM"`); `build_projection_config` coerces it to the
   `ReserveBasis` enum via a new `_coerce_reserve_basis` helper that accepts the
   enum or a case-insensitive string and raises `PolarisValidationError` (listing
   the valid values) on an unknown one. No core-contract change — the
   `ProjectionConfig.reserve_basis` field already existed from Slice 1.
2. **CLI.** `polaris price` gains a `--reserve-basis` flag, validated eagerly
   (clean error + valid list, mirroring `--capital`). It is threaded into
   `_build_pipeline_from_config(..., reserve_basis_override=...)` and **overrides**
   any `deal.reserve_basis` in the config (flag-over-config precedence, matching
   the YRT-rate-table surfaces). The CLI JSON `summary` echoes the resolved basis.
   Both the nested and legacy config schemas parse `reserve_basis`.
3. **API.** `PriceRequest` gains `reserve_basis: ReserveBasis` (default
   NET_PREMIUM); it is threaded into `_build_components` and the `PriceResponse`
   echoes it. An unsupported basis for the product surfaces the
   `PolarisComputationError` as the endpoint's existing HTTP 422; an invalid enum
   string is rejected by Pydantic (also 422). Scoped to `/price` to mirror the CLI
   `polaris price` surface; `scenario` / `uq` are promoted follow-ups.
4. **Excel.** `DealMetaExport` gains `reserve_basis: str` (default NET_PREMIUM for
   backward compatibility) and the Assumptions sheet always labels "Reserve Basis"
   so a committee reviewer sees which basis drove the numbers.
5. **Notebook.** `notebooks/02_reserve_basis_comparison.ipynb` prices one WL block
   under NET_PREMIUM / CRVM / VM20, comparing the profit signature and showing the
   WL terminal-reserve artefact closing on the to-omega bases (NET_PREMIUM reserve
   stays ~flat to yr20; CRVM/VM20 grade ~28× higher).

**Behaviour change.** None on the default path: NET_PREMIUM is the default
everywhere, the priced numbers are byte-identical, and the only additive outputs
are the echoed-basis metadata (CLI summary key, API response field) and a single
"Reserve Basis: NET_PREMIUM" row on the Excel Assumptions sheet (no Excel
byte-golden exists; the label-based Excel tests are unaffected). Selecting a
non-default basis intentionally changes the reserve — and therefore the NAR, the
reserve transfer, and the profit numbers — as the epic intends.

**Out of scope (filed as follow-ups).** Reserve-basis selection on the
`scenario` / `uq` CLI commands and API endpoints (this slice covers `price`
only); the dashboard reserve-basis control (CLI/Streamlit parity); GAAP concrete
basis (only the enum + guard exist — selecting it raises). The deferred
actuarial-precision items (2001 CSO valuation table, 20-pay cap, exact VM-20 NPR
refinements, VM-20 stochastic reserve, NET_PREMIUM WL artefact closure) remain
promoted from ADR-088/089/090/091.

**Affected files.**

- `src/polaris_re/core/pipeline.py` (`DealConfig.reserve_basis` + `to_dict`;
  `_coerce_reserve_basis`; `build_projection_config` wiring)
- `src/polaris_re/cli.py` (`--reserve-basis` flag + eager validation;
  `_build_pipeline_from_config` override param; config parse both schemas;
  JSON summary echo; `DealMetaExport.reserve_basis` wiring)
- `src/polaris_re/api/main.py` (`PriceRequest.reserve_basis`,
  `PriceResponse.reserve_basis`, `_build_components` wiring, `/price` echo)
- `src/polaris_re/utils/excel_output.py` (`DealMetaExport.reserve_basis`;
  "Reserve Basis" row on the Assumptions sheet)
- `notebooks/02_reserve_basis_comparison.ipynb` (new — cross-basis profit
  signature + artefact-closure validation)
- `tests/test_cli_reserve_basis.py`, `tests/test_api/test_reserve_basis.py`,
  `tests/test_core/test_pipeline_reserve_basis.py` (new); Excel
  Assumptions-sheet reserve-basis tests added to
  `tests/test_utils/test_excel_output.py`

## ADR-093: IFRS 17 annual issue-year cohorts + locked-in rate (Epic 2, Slice 1)

**Date:** 2026-06-20
**Status:** Accepted

**Context.** `analytics/ifrs17.py` measures BEL / RA / CSM at a single point in
time (initial recognition, with prospective schedules) for one block. A
production IFRS 17 filer must publish a period-to-period **movement / analysis
of change** table, which requires two capabilities the point-in-time model does
not have: (1) grouping contracts into **annual issue-year cohorts**, and (2)
accreting each cohort's CSM at the **discount rate locked in at that cohort's
initial recognition** (IFRS 17 B72(b); cohorts cannot be netted against one
another). This is the first slice of Epic 2 (A2 in
`COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md`, ROADMAP 5.3); it builds the cohort
container the movement table (Slice 2) rolls forward.

**Premise (verified before implementing, routine step 7b).** `grep` confirmed
`analytics/ifrs17.py` exported only `IFRS17Measurement` / `IFRS17Result` with no
cohort or locked-in-rate-per-cohort concept; the existing tests measure a single
block at a single discount rate. The gap is real — there is no way today to
value two issue-year cohorts at two locked-in rates and aggregate them.

**Decision.**

1. **Types.** Add `IFRS17ContractInput` (frozen dataclass: GROSS `cashflows`,
   `issue_date`, `locked_in_rate`, `ra_factor`), `IFRS17Cohort` (the aggregated
   cohort: `issue_year`, `locked_in_rate`, `ra_factor`, `n_contracts`,
   aggregated `cashflows`, and the per-cohort `IFRS17Result`), and
   `IFRS17CohortManager`.
2. **Grouping.** The manager groups contracts by `issue_date.year`, sums the
   GROSS cash-flow lines within each cohort, and measures each cohort
   **BBA at its own `locked_in_rate`** by composing
   `IFRS17Measurement.measure_bba()` — it does NOT re-derive the BEL/RA/CSM
   recursions. Cohorts are ordered by issue year.
3. **Common projection grid.** All contracts must share `projection_months`,
   `valuation_date`, and `time_index`, so the aggregate balance-sheet schedules
   are the index-wise sum across cohorts. The intended usage is an inforce block
   valued at one common date, cohorted by historical issue year, each cohort
   carrying its issue-era locked-in rate. Heterogeneous-term calendar alignment
   (different policy terms issued the same year) is a promoted follow-up.
4. **Intra-cohort consistency.** Contracts within one cohort must agree on
   `locked_in_rate` and `ra_factor` (the cohort is recognised together); a
   mismatch raises `PolarisValidationError`, as do empty input, a non-GROSS
   contract, and a misaligned grid.
5. **Aggregate accessors.** `aggregate_bel/ra/csm/insurance_liability()` (Σ over
   cohorts) and `total_initial_liability()`.

**Closed-form / verification anchors.** (a) A single-contract cohort reproduces
a direct `IFRS17Measurement.measure_bba()` exactly (BEL/RA/CSM `allclose`). (b)
Cohort aggregation is linear: two identical profitable contracts give exactly
2× the BEL/RA/CSM of one. (c) Two cohorts at distinct locked-in rates produce
distinct CSM schedules (the locked-in rate genuinely drives accretion). (d) The
aggregate schedules equal the sum across cohorts.

**Behaviour change.** None. New additive types, nothing wired into the pricing
pipeline; the golden CLI/pipeline outputs are byte-identical (verified — 1482
passed incl. the QA golden suite, 72 passed).

**Out of scope (filed as follow-ups).** The opening→…→closing movement table
itself (Slice 2, `IFRS17MovementTable` + the additivity test); surfacing on
API/Excel/CLI (Slice 3); heterogeneous-term cohort calendar alignment; cohort
support for the PAA / VFA measurement models (Slice 1 cohorts measure BBA only);
the onerous-contract sub-grouping within an annual cohort (IFRS 17.16).

---

## ADR-094: IFRS 17 analysis-of-change (movement) table (Epic 2, Slice 2)

**Date:** 2026-06-20
**Status:** Accepted

**Context.** ADR-093 (Slice 1) built the cohort container: contracts grouped
into annual issue-year cohorts, each measured BBA at its own locked-in rate, with
per-cohort and aggregate point-in-time BEL/RA/CSM schedules. The disclosure a
filer must actually publish is the **analysis of change** (movement) table — for
each reporting period, a reconciliation of the *opening* insurance-liability
balance to the *closing* balance through named movements (new business,
unwinding/accretion, expected experience/release), per component (BEL / RA / CSM)
and in total. This slice rolls the Slice-1 schedules forward into that table.

**Premise (verified before implementing, routine step 7b).** With the baseline
suite green (1482 passed), `IFRS17CohortManager` exposed only point-in-time
schedules (`aggregate_bel/ra/csm`) — there was no opening→closing decomposition,
no `IFRS17MovementTable`, and no additivity guarantee. The gap is real; the
movement table IS the filing artefact and did not exist.

**Decision.**

1. **Types.** Add `IFRS17ComponentMovement` (one component's analysis of change:
   `opening`, `new_business`, `interest_accretion`, `release`, `closing`, plus a
   `footing_error()` and `__add__` for aggregation), `IFRS17MovementRow` (one
   reporting period across BEL / RA / CSM with a derived `total` column), and
   `IFRS17MovementTable` (the ordered rows + `max_footing_error()`).
2. **Builder.** A module-level `build_movement_table(result, locked_in_rate, *,
   months_per_period=12, issue_year=None)` rolls an `IFRS17Result` forward. It
   pads each start-of-month schedule with a terminal zero (full run-off) and
   derives the per-month movement primitives:
   - **BEL**: `interest_accretion = BEL[t]·((1+r)^(1/12)−1)` (unwinding of
     discount); `release = (BEL[t+1]−BEL[t]) − interest`, which equals `−FCF[t]`
     by the BEL recursion (the expected fulfilment cash flows running off).
   - **CSM**: `interest_accretion` and `release` taken straight from the engine's
     roll-forward (`result.csm_interest_accretion`, `−result.csm_release`) so the
     CSM accretes at the cohort's **locked-in** rate.
   - **RA**: under the simplified cost-of-capital RA (`ra_factor·|BEL|`) there is
     no separate finance line, so `interest_accretion = 0` and the whole period
     change is the risk `release`.
3. **Reporting-period granularity (the one real design choice).** Annual
   (`months_per_period=12`) by default — IFRS 17 cohorts are annual, the
   underlying schedules monthly. A reporting period aggregates the monthly
   movements over its months; opening is the start-of-period balance, closing the
   end-of-period balance. Because the per-month change telescopes
   (`BEL[t+1]−BEL[t] = interest − FCF`, `CSM[t+1]−CSM[t] = accretion − release`),
   the period movements foot to `closing − opening` **by construction**. A
   trailing partial period (T not a multiple of 12) is handled and still foots.
4. **New-business vs in-force opening.** The cohort's **first** reporting period
   opens at 0 (pre-recognition) and carries the initial-recognition balance in
   the `new_business` line; later periods open at the prior closing. This treats
   the projection as a from-recognition roll-forward (which is exactly what the
   Slice-1 cohort measurement computes — initial-recognition CSM at t=0). For a
   true mid-life in-force movement table, period-0 opening would instead be the
   current in-force balance with no new-business line; that variant is a filed
   follow-up.
5. **Aggregate table.** `IFRS17CohortManager.aggregate_movement_table()` is the
   per-period, per-component sum of the per-cohort tables (`cohort_movement_tables()`).
   The shared projection grid (ADR-093) aligns the reporting periods, so the
   aggregate movement equals Σ cohort movements; the aggregate table carries no
   single `locked_in_rate` (rates differ across cohorts).

**Closed-form / verification anchors.** (a) **Additivity (headline):**
`max_footing_error()` is 0 (`atol=1e-9`) for every cohort table and the aggregate
— `opening + Σ movements == closing` for BEL/RA/CSM/total in every period, at
both annual and monthly granularity. (b) BEL `release == −Σ FCF` and
`new_business == BEL[0]` for a constant-cash-flow contract. (c) CSM accretion is
strictly larger at a higher locked-in rate (identical cash flows, 0.08 vs 0.03),
and per-period CSM accretion/release tie out to the engine's monthly arrays. (d)
Every component exhausts to 0 at full run-off. (e) Each period's opening equals
the prior period's closing. (f) Aggregate == Σ cohorts, field by field.

**Behaviour change.** None. New additive analytics, nothing wired into the
pricing pipeline; the golden CLI/pipeline outputs are byte-identical (verified —
QA golden suite 72 passed; analytics suite 559 passed incl. 18 new movement
tests). No golden rebaseline.

**Out of scope (filed as follow-ups).** Surfacing the movement table on
API / Excel / CLI (Slice 3 — the only slice that may move goldens, and only for
runs that request the table); the mid-life in-force opening variant (period-0
opening = current in-force balance instead of 0 + new business); an explicit RA
finance/unwinding line (the simplified RA carries none); the insurance-finance
income/OCI split and the LRC/LIC reconciliation for PAA; movement tables for the
PAA / VFA measurement models (this slice rolls BBA results forward only).

## ADR-095: Surface the IFRS 17 movement table on the REST API (Epic 2, Slice 3a)

**Date:** 2026-06-20
**Status:** Accepted

**Context.** ADR-093/094 (Slices 1–2) built the IFRS 17 cohort layer and the
analysis-of-change (movement) table in `analytics/ifrs17.py`, fully tested and
footing by construction — but nothing consumes it. The disclosure is only useful
once a filer can pull it out of the engine. PLAN_ifrs17_movement Slice 3 is the
surfacing slice (API + Excel + CLI). Following the repo's sub-slicing convention
(e.g. reserve-basis Slice 4 / 2a / 2b), Slice 3 is decomposed into **3a (REST
API + serialiser)**, 3b (Excel sheet), 3c (CLI surface). 3a ships the serialiser
that all three surfaces consume, plus the first surface (the API).

**Premise (verified before implementing, routine step 7b).** With the baseline
suite green (1500 passed, 83 deselected), `grep` over `src/` confirmed there was
no `/api/v1/ifrs17/movement` route and no `to_dict` on any movement type — the
movement table existed only as in-process Python objects. The gap is real.

**Decision.**

1. **Serialiser.** Add `to_dict()` to `IFRS17ComponentMovement` (its five
   movement lines + `footing_error`, all plain `float`), `IFRS17MovementRow`
   (`period`, `start_month`, `end_month`, and the BEL / RA / CSM / total
   columns), and `IFRS17MovementTable` (table metadata — `months_per_period`,
   `issue_year`, `locked_in_rate`, `n_periods`, `max_footing_error` — plus the
   serialised rows). The output is plain-Python / JSON-serialisable with no
   custom encoder, and carries the footing residual so a consumer can assert the
   disclosure foots without re-deriving it.
2. **Endpoint.** `POST /api/v1/ifrs17/movement` (`IFRS17MovementRequest` →
   `IFRS17MovementResponse`). The request reuses the BBA/PAA policy + assumption
   fields and adds `months_per_period` (annual default) and an optional
   `locked_in_rates` map (issue year → rate). The handler groups the request's
   policies into annual issue-year cohorts by `issue_date.year`, projects each
   group GROSS on the shared calendar grid, builds one `IFRS17ContractInput` per
   cohort (each at its own locked-in rate, defaulting to `discount_rate`), and
   feeds them to `IFRS17CohortManager`. The response returns the aggregate table,
   the per-cohort tables (ordered by issue year), and the worst footing residual
   across the whole response.
3. **Alignment / errors.** Cohorts must share one valuation date (the cohort
   manager's existing ADR-093 alignment check enforces this); a mismatch raises
   `PolarisValidationError`, which the endpoint's catch-all maps to HTTP 422 — the
   same status the BBA/PAA endpoints use for semantic request errors.

**Closed-form / verification anchors.** API tests: two issue years → two cohorts
ordered `[2023, 2025]`; `max_footing_error < 1e-6` (the disclosure foots through
the serialised round-trip); aggregate carries null `issue_year` / `locked_in_rate`;
annual default gives `n_periods == horizon_years` and `months_per_period=6` gives
twice as many; `locked_in_rates` override is echoed per cohort; mixed valuation
dates → HTTP 422. Serialiser tests: field round-trip with plain floats; row total
== BEL + RA + CSM field-by-field; table metadata; aggregate null cohort metadata;
`json.dumps` round-trips without a custom encoder.

**Behaviour change.** None to existing endpoints or the pricing pipeline — a new
additive route plus new serialiser methods on existing types. Golden CLI /
pipeline outputs are byte-identical (verified — QA golden suite 72 passed, golden
`polaris price` run reproduced). No golden rebaseline.

**Out of scope (filed as follow-ups).** Slice 3b — the "IFRS 17 Movement" Excel
sheet in the deal-pricing workbook. Slice 3c — a CLI surface (`polaris price`
opt-in flag or a `polaris ifrs17` subcommand). The dashboard movement view
(the dashboard currently shows only point-in-time IFRS 17). Carried forward from
ADR-094: the mid-life in-force opening variant; an explicit RA finance line;
movement tables for PAA / VFA. Driving the cohorts' locked-in rates from real
issue-era rate curves rather than a flat per-year override.

---

## ADR-096: Surface the IFRS 17 movement table on the deal-pricing Excel workbook (Epic 2, Slice 3b)

**Date:** 2026-06-20
**Status:** Accepted

**Context.** ADR-093/094 built the IFRS 17 cohort layer and the analysis-of-change
(movement) table; ADR-095 (Slice 3a) shipped the `to_dict()` serialiser and the
`POST /api/v1/ifrs17/movement` REST surface. PLAN_ifrs17_movement Slice 3 is the
surfacing slice, sub-sliced into 3a (API), 3b (Excel), 3c (CLI). This ADR is
**Slice 3b** — the committee-grade deal-pricing workbook (ADR-045) is where a
deal actuary actually reads the numbers, so the analysis of change belongs there
as a sheet, not only on the JSON API.

**Premise (verified before implementing, routine step 7b).** With the baseline
suite green (1505 passed, 94 deselected), `grep` over `src/polaris_re/utils/`
confirmed `excel_output.py` had no IFRS 17 / movement sheet — the workbook
covered Summary / Cash Flows / Assumptions / Sensitivity / YRT Rate Table only.
The gap is real.

**Decision.**

1. **DTO.** Add `IFRS17MovementExport` (frozen dataclass) bundling the
   `aggregate: IFRS17MovementTable` and `cohorts: list[IFRS17MovementTable]`
   exactly as `IFRS17CohortManager.aggregate_movement_table()` /
   `.cohort_movement_tables()` produce them. Carrying the typed movement tables
   (not the serialised dict) follows the established `DealPricingExport`
   precedent — `PremiumSufficiencyResult` (ADR-083) and `YRTRateTable` (ADR-052)
   are likewise carried as typed objects — and gives the writer type-safe field
   access. The rendered fields are exactly those the 3a `to_dict()` serialiser /
   the API expose, so the Excel and JSON surfaces report identical numbers.
2. **Export field.** Add `ifrs17_movement: IFRS17MovementExport | None = None` to
   `DealPricingExport`. `None` (the default) suppresses the sheet, so every
   pre-ADR-096 export — and every current `polaris price` run, which does not yet
   populate the field — stays byte-identical.
3. **Sheet.** `write_deal_pricing_excel` appends an "IFRS 17 Movement" sheet
   **last** (so all other sheet positions are unchanged) when the field is
   populated. The sheet stacks the aggregate block first, then one block per
   issue-year cohort (ordered by issue year, each titled with its locked-in
   rate). Each block renders BEL / RA / CSM / total as a familiar Year x
   movement-line sub-table (`Opening`, `New Business`, `Interest Accretion`,
   `Release`, `Closing`), matching the IASB reconciliation layout and the repo's
   1-based Year axis. Each block also prints its `max_footing_error` so the
   disclosure's footing property is visible on the sheet.

**Closed-form / verification anchors.** Excel tests: sheet omitted when the
field is `None`; present and appended last when populated; aggregate + per-cohort
block titles carry the issue year and locked-in rate, ordered by year; the four
component labels present; **every rendered data row foots** —
`Opening + New Business + Interest Accretion + Release == Closing` to
`assert_allclose` across all 36 data rows (3 periods x 4 components x (aggregate +
2 cohorts)); Year axis is 1-based; the workbook re-opens.

**Behaviour change.** None to existing workbooks or the pricing pipeline — a new
optional DTO field and a sheet written only when it is populated. Golden CLI /
pipeline outputs are byte-identical (the CLI does not populate the field; that is
Slice 3c). No golden rebaseline.

**Out of scope (filed as follow-ups).** Slice 3c — the CLI surface (`polaris
price` opt-in flag or a `polaris ifrs17` subcommand) that actually populates
`ifrs17_movement` on a real run. Wiring the CLI's deal-pricing export to compute
the cohort manager from the priced block (the natural home for that is Slice 3c,
since it decides the cohorting inputs — issue-year grouping and per-year
locked-in rates — for the `polaris price` path). The dashboard movement view.
Carried forward from ADR-094/095: the mid-life in-force opening variant; an
explicit RA finance line; movement tables for PAA / VFA; issue-era rate-curve
locked-in rates.

## ADR-097: Surface the IFRS 17 movement table on the `polaris price` CLI (Epic 2, Slice 3c)

**Date:** 2026-06-21
**Status:** Accepted

**Context.** ADR-093/094 built the IFRS 17 cohort layer and the
analysis-of-change (movement) table; ADR-095 (Slice 3a) shipped the `to_dict()`
serialiser and the `POST /api/v1/ifrs17/movement` REST surface; ADR-096
(Slice 3b) wired the "IFRS 17 Movement" sheet into the deal-pricing workbook but
left it dormant — nothing populated `DealPricingExport.ifrs17_movement`. This
ADR is **Slice 3c**, the final surfacing slice of PLAN_ifrs17_movement: the CLI
is where a deal actuary runs a block, and it is also the path that owns
`--excel-out`, so wiring it here makes the movement table reachable end-to-end on
JSON, terminal, and Excel from one command — completing the epic.

**Premise (verified before implementing, routine step 7b).** With the baseline
suite green (1513 passed, 94 deselected), `polaris ifrs17 --help` exited
non-zero (no such command) and `polaris price --help` had no `ifrs17` / movement
flag — the movement table was unreachable from the CLI even though the API
(3a) and Excel writer (3b) were ready. The gap is real.

**Decision.**

1. **`polaris price` opt-in flag, not a new subcommand.** Add
   `--ifrs17-movement` (off by default) plus `--ifrs17-ra-factor` (default 0.05,
   range [0, 0.50]) and `--ifrs17-months-per-period` (default 12). The flag route
   is chosen over a dedicated `polaris ifrs17` subcommand because `price` already
   owns `--excel-out` and builds the `DealPricingExport`, so the same run
   surfaces JSON + Rich + the Excel sheet (3b) — the route PLAN/CONTINUATION 3c
   anticipated.
2. **Per-product-cohort movement, mirroring the API consumer.** The movement is
   built **per `iter_cohorts` product cohort**, not block-wide. Within a cohort
   the policies are grouped into annual issue-year cohorts, each issue-year
   sub-block is projected GROSS via the product dispatcher, and the groups feed
   `IFRS17CohortManager` (`aggregate_movement_table` + `cohort_movement_tables`).
   Per-product is required for correctness: TERM and WHOLE_LIFE project on
   different grids, so a block-wide aggregate would fail the cohort manager's
   alignment check; per-product also matches the per-cohort Excel workbook model
   (ADR-068) — each workbook carries its own cohort's movement sheet.
3. **Locked-in rate = `config.discount_rate` for every cohort.** A per-issue-year
   locked-in-rate override (already accepted by the REST API) is deferred as a
   follow-up, keeping the slice small.
4. **JSON shape mirrors the REST `IFRS17MovementResponse` (ADR-095)** —
   `{months_per_period, n_cohorts, max_footing_error, aggregate, cohorts}`,
   reusing the 3a `to_dict()` serialiser — added per cohort and (single-cohort
   case) at the top level. Rich renders two compact tables (total-liability
   reconciliation + closing balances by component); full detail is in JSON/Excel.

**Closed-form / verification anchors.** CLI tests (`CliRunner`): without the flag
no `ifrs17_movement` key appears (golden-baseline guarantee) and the workbook has
no IFRS 17 sheet; with the flag each cohort carries the movement block, the JSON
shape matches the REST keys, **every cohort's `max_footing_error < 1e-6`** (the
opening + Σ movements == closing disclosure property, surfaced), cohorts group
and order by issue year (golden TERM → [2021, 2026], WHOLE_LIFE → [2016, 2021,
2026]), the aggregate carries null cohort metadata, the locked-in rate equals the
config discount rate, `--ifrs17-months-per-period 6` doubles the period count and
still foots, out-of-range `--ifrs17-ra-factor` / `--ifrs17-months-per-period`
exit non-zero, and `--excel-out` appends the sheet to every per-cohort workbook.

**Behaviour change.** None unless `--ifrs17-movement` is passed: the flag is
off by default, so the CLI JSON, terminal, and Excel outputs are byte-identical
to prior runs (golden CLI / pipeline tests unchanged, no rebaseline).

**Out of scope (filed as follow-ups).** Per-issue-year locked-in-rate override
on the CLI (the REST API already has the `locked_in_rates` map). A dedicated
`polaris ifrs17` subcommand for movement-only output (no pricing). A
block-wide (cross-product) movement table on a common calendar grid
(needs heterogeneous-term alignment). The dashboard movement view. Carried
forward from ADR-094/095/096: the mid-life in-force opening variant; an explicit
RA finance line; movement tables for PAA / VFA; issue-era rate-curve locked-in
rates.

---

## ADR-098: US NAIC Life RBC capital module + shared `CapitalModel` protocol (Epic 3, Slice 1)

**Date:** 2026-06-21
**Status:** Accepted

**Context.** The capital layer (`analytics/capital.py`, ADR-047 / ADR-065 /
ADR-072) implements **LICAT** — the Canadian OSFI standard — only. A reinsurer
cannot evaluate a US deal on a return-on-capital basis (the primary decision
metric) because the US uses NAIC **Risk-Based Capital (RBC)**, a structurally
different standard: it splits risk into C-0 … C-4 components and aggregates them
with a **covariance square root**, not a simple sum. The 2026-04-19 baseline
rated US RBC a BLOCKER; `COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md` restored it
as Tier-A epic **A3** (Cross-jurisdiction capital — US RBC then Solvency II).
This ADR is **Slice 1** of `PLAN_cross_jurisdiction_capital.md`: the US RBC core
module plus the shared protocol that lets all three jurisdictions plug into the
same `ProfitTester` / surfaces.

**Decision.**

1. **Shared `CapitalModel` / `CapitalSchedule` protocols** (`analytics/capital_base.py`).
   Two structural (PEP 544) `Protocol`s capture the calculator/result contract
   `LICATCapital` / `CapitalResult` already established: a model exposes
   `required_capital(cashflows, nar=None) -> schedule`, and a schedule carries
   `capital_by_period` / `initial_capital` / `peak_capital` plus `pv_capital` /
   `capital_strain` / `pv_capital_strain`. Structural, so the pre-existing LICAT
   classes conform with **no modification** (tests assert it via `isinstance`),
   and new siblings only match the shape. Two small free helpers
   (`discount_stream`, `strain_of`) factor out the discount / period-change
   arithmetic so each schedule does not re-derive it.

2. **`RBCCapital` factor-based calculator** (`analytics/rbc.py`), the US analogue
   of `LICATCapital`. Each NAIC component is `factor * exposure` per month: C-1o
   (asset default) / C-3a (interest) / C-3b / C-3c / C-4a / C-4b / C-0 / C-1cs on
   `reserve_balance`, and **C-2 (insurance risk) on NAR**. `for_product` selects
   per-product defaults; only C-1o, C-2, C-3a are non-zero by default (a typical
   individual-life book), the rest are overridable zero stubs.

3. **NAIC covariance square-root aggregation** —
   `RBC = C0 + C4a + sqrt[(C1o+C3a)² + C1cs² + C2² + C3b² + C3c² + C4b²]`. C-0
   and C-4a sit outside the root (no diversification credit); C-1o pairs with
   C-3a inside it (asset / interest-rate correlation). This is the classic
   pre-2021 Life RBC grouping. The result is the **Company Action Level (CAL)**;
   `RBCResult.authorized_control_level` = ½ CAL is the RBC-ratio denominator, and
   `rbc_ratio(tac)` = TAC / ACL₀.

4. **Held-capital basis = CAL.** `capital_by_period` is the covariance result
   (CAL), matching the LICAT convention that `capital_by_period` is the required
   amount fed to return-on-capital. A configurable target multiple of ACL
   (reinsurers commonly hold 300–400% of ACL) is deferred to Slice 2/4.

**Factor calibration.** Like the LICAT module, these are **committee-stage
approximations**, documented and overridable, not a shock-based model: C-1o =
1.0% of reserves (blended investment-grade bond default); C-2 = 0.00150 of NAR
(NAIC individual-life first-tier factor); C-3a = 0.0077 / 0.0154 / 0.0231 of
reserves (NAIC C-3 Phase I low / medium / high categories by product). The
shock-based / 2021 NAIC bond-factor calibration is the Asset/ALM epic (CVR Tier
C, after the Tier-A epics).

**Closed-form / verification anchors.** Tests assert the covariance closed form
on the golden-flavour block (`sqrt[(C1o+C3a)² + C2²]` for the default factor
set, and the full nine-component formula), `ACL = ½ CAL`, the linear
(no-diversification) effect of C-0 / C-4a outside the root, `pv_capital` /
`capital_strain` against a manual discount, the RBC-ratio closed form, CEDED
rejection, NAR resolution / length validation, and that **both** `RBCResult` and
the unmodified `CapitalResult` satisfy `CapitalSchedule` (and both calculators
satisfy `CapitalModel`). A jurisdiction-difference test confirms RBC and LICAT
produce different capital on the same block (RBC is not a LICAT alias).

**Behaviour change.** None. `rbc.py` / `capital_base.py` are new modules imported
by nothing in the pricing path; `LICATCapital` / `CapitalResult` are untouched.
Goldens are byte-identical (no rebaseline). RoC integration is Slice 2.

**Out of scope (filed as follow-ups).** `ProfitTester.run_with_capital`
generalisation to the `CapitalModel` protocol and an RBC-ratio surface (Slice
2). Solvency II SCR (Slice 3). The CLI `--capital {licat,rbc,solvency2}` / API
`capital_model` / Excel / dashboard jurisdiction selector and the
three-standard validation notebook (Slice 4). A configurable held-capital
target multiple of ACL. The 2021+ NAIC designation-based bond factors and C-3
Phase II stochastic interest-rate requirement (Asset/ALM epic). Tax / DTA and
multi-currency books.

---

## ADR-099: Generalise `ProfitTester.run_with_capital` to the `CapitalModel` protocol (Epic 3, Slice 2)

**Date:** 2026-06-21
**Status:** Accepted

**Context.** Slice 1 (ADR-098) added the US `RBCCapital` calculator and the
shared `CapitalModel` / `CapitalSchedule` structural protocols, but
`ProfitTester.run_with_capital` was still hard-typed to the concrete Canadian
`LICATCapital` (and its result annotated `CapitalResult`). At runtime the method
already worked with any conforming model — its body only ever touches the
`CapitalSchedule` surface (`required_capital`, `pv_capital`,
`pv_capital_strain`, `capital_strain`, `capital_by_period`, `initial_capital`,
`peak_capital`) — so an `RBCCapital` produced correct return-on-capital by duck
typing, but the type contract rejected it and no test proved the US path.
Return-on-capital is the primary deal-pricing metric, so until the seam is
genuinely jurisdiction-agnostic a US deal cannot be priced on a RoC basis.

**Decision.** Widen the integration seam to the protocol, type-only:

1. Both RoC entry points — `ProfitTester.run_with_capital` (single deal) and
   `Portfolio.run_with_capital` (aggregate book) — take
   `capital_model: CapitalModel`, with the internal
   `capital: CapitalSchedule = capital_model.required_capital(…)`, replacing the
   concrete `LICATCapital` / `CapitalResult` annotations. Imports are re-pointed
   from `analytics.capital` to `analytics.capital_base`; the (now-unused)
   concrete imports are dropped. No statement in either body changes — both
   already depended solely on the protocol surface.

2. Any `CapitalModel` — Canadian `LICATCapital`, US `RBCCapital`, and (Slice 3)
   `SolvencyIICapital` — now feeds the same RoC / capital-strain /
   capital-adjusted-IRR machinery. The RoC denominator remains PV(capital stock)
   at the hurdle rate (ADR-048); only the capital number differs by jurisdiction.

3. **Jurisdiction-specific extras stay on the schedule, not the generic
   result.** `ProfitResultWithCapital` is deliberately left unchanged: RBC's
   Authorized Control Level and `rbc_ratio(tac)` (= TAC / ACL₀) live on the
   `RBCResult` the model returns, reachable via `capital_model.required_capital(cf)`.
   The RBC ratio needs an external Total Adjusted Capital input that
   `ProfitTester` does not hold, so a `ProfitResultWithCapital`-level RBC-ratio
   surface is deferred to the Slice 4 surfacing (where a TAC / target-multiple
   input is introduced).

**Closed-form / verification anchors.** New `TestProfitTesterWithRBCCapital`
asserts: `RBCCapital` satisfies `CapitalModel` and its schedule satisfies
`CapitalSchedule`; an `RBCCapital`-driven `run_with_capital` populates RoC /
PV-strain / capital-adjusted IRR; the RoC closed form against the NAIC
covariance square root (`sqrt[(C1o+C3a)² + C2²]` for TERM defaults) over a flat
reserve + NAR block; the RBC-ratio closed form (TAC / ACL with ACL = ½ CAL);
that LICAT and RBC feed the identical RoC formula (only the capital number
differs); the zero-factor → `None` RoC guard for RBC; and a regression that the
LICAT capital schedule is byte-for-byte unchanged by the widening (`0.15 × NAR`).

**Behaviour change.** None. The widening is type-only; the LICAT path is
identical (existing `TestProfitTesterWithCapital` green, plus an explicit
regression). Goldens are byte-identical (no rebaseline) — nothing in the
default pricing path selects a non-LICAT model yet (that is Slice 4).

**Out of scope (filed as follow-ups).** A `ProfitResultWithCapital`-level
RBC-ratio / solvency-ratio surface with a TAC or target-multiple input (Slice 4
surfacing). Solvency II SCR (Slice 3). The CLI `--capital {licat,rbc,solvency2}`
/ API `capital_model` / Excel / dashboard jurisdiction selector (Slice 4). A
configurable held-capital target multiple of ACL. The `Portfolio.run_with_capital`
aggregate path is widened to the protocol in the **same** way in this slice (its
body, like `ProfitTester`'s, already used only the `CapitalSchedule` surface), so
RBC drives both the single-deal and portfolio RoC entry points consistently.

---

## ADR-100: EU Solvency II SCR capital module (Epic 3, Slice 3)

**Date:** 2026-06-22
**Status:** Accepted

**Context.** Slices 1–2 (ADR-098 / ADR-099) added the US `RBCCapital` calculator
and widened both return-on-capital entry points to the `CapitalModel` /
`CapitalSchedule` protocols, so a new jurisdiction needs only to satisfy those
protocols to plug into RoC for free. The EU is the second-largest reinsurance
market and the third regulatory standard the engine must price under; without a
Solvency II SCR an EU deal cannot be quoted on a return-on-capital basis. This
slice adds the EU sibling of the Canadian LICAT and US RBC modules.

**Decision.** Add `analytics/solvency2.py` — `SolvencyIIFactors` (Pydantic),
`SolvencyIIResult` (dataclass schedule), `SolvencyIICapital` (calculator) —
implementing the Solvency II **standard-formula** SCR as a factor-based
committee-stage calculator, exactly the disposition LICAT (ADR-047/065/072) and
RBC (ADR-098) use:

1. **Two correlation-matrix aggregations.** The life-underwriting sub-modules
   (mortality, lapse, catastrophe) are aggregated by `LIFE_CORRELATION` into a
   life SCR; that, with market and counterparty-default risk, is aggregated by
   `TOP_LEVEL_CORRELATION` into the Basic SCR (BSCR). Both use the
   standard-formula quadratic-form square root `sqrt(rᵀ · Corr · r)`, evaluated
   per period via an `einsum` over the component index (vectorised, no per-period
   loop). This is the EU analogue of the NAIC covariance square root (ADR-098),
   generalised from a single asset/insurance pair to a full correlation matrix.

2. **Operational risk adds linearly outside the BSCR matrix** (no diversification
   credit), giving `SCR = BSCR + Op`. `capital_by_period` is the SCR — the
   held-capital basis fed to RoC via `pv_capital`, matching the LICAT/RBC
   convention.

3. **Correlation matrices are the standard-formula values** from Commission
   Delegated Regulation (EU) 2015/35, Annex IV: top-level market / counterparty /
   life all pairwise 0.25; within life, mortality-lapse 0, mortality-CAT and
   lapse-CAT 0.25. They live in documented module constants (`LIFE_CORRELATION`,
   `TOP_LEVEL_CORRELATION`), not inline in the calculation path.

4. **Cost-of-capital risk margin.** `SolvencyIIResult.risk_margin(rate, coc=6%)`
   applies the standard CoC method `RM = CoC · PV(future SCR)`, the monthly
   committee-stage analogue of the standard-formula risk margin.

5. **Factor exposures.** Mortality and catastrophe apply to NAR (capital-at-risk);
   lapse, market, counterparty, operational apply to reserves. The catastrophe
   default (0.0015 of NAR) is the citable standard-formula life-CAT shock
   (+1.5 per mille of capital-at-risk for one year); the rest are conservative
   committee-stage placeholders, overridable on `SolvencyIIFactors` and selected
   per product by `SolvencyIICapital.for_product`.

**Closed-form / verification anchors.** `test_solvency2.py` (34 tests) asserts:
the life SCR closed form `sqrt(m² + l² + c² + 0.5·m·c + 0.5·l·c)`; the BSCR
closed form `sqrt(M² + D² + L² + 0.5·(MD + ML + DL))`; correlation matrices are
symmetric with unit diagonal and the documented off-diagonals; operational risk
adds linearly outside the BSCR; the risk-margin CoC closed form and its linearity
in CoC; diversification credit (aggregate < linear sum); per-product factor
defaults; CEDED rejection and NAR resolution / length guards; and that
`SolvencyIICapital` / `SolvencyIIResult` satisfy `CapitalModel` /
`CapitalSchedule` and differ from LICAT on the same block.

**Behaviour change.** None. `solvency2.py` is a new additive module wired into
nothing in the pricing path; the `--capital solvency2` CLI/API selector is still
rejected (Slice 4 surfaces it). Goldens are byte-identical (no rebaseline).

**Out of scope (filed as follow-ups).** The CLI `--capital solvency2` / API
`capital_model="solvency2"` / Excel / dashboard jurisdiction selector and the
three-standard validation notebook (Slice 4). A `ProfitResultWithCapital`-level
solvency-ratio surface (own funds / SCR) needing an external own-funds input
(Slice 4, alongside the deferred RBC ratio). Longevity, expense, revision, and
disability/morbidity life sub-modules and the health/non-life top-level modules
(only mortality/lapse/catastrophe + market + counterparty are modelled here).
The shock-based standard-formula calibration that replaces the factor
approximations (C0 Asset/ALM epic, CVR Tier C).

## ADR-101: Surface the jurisdiction selector on the CLI and REST API (Epic 3, Slice 4a)

**Date:** 2026-06-22
**Status:** Accepted

**Context.** Slices 1–3 (ADR-098/099/100) shipped all three regulatory-capital
calculators — `LICATCapital` (Canada), `RBCCapital` (US), `SolvencyIICapital`
(EU) — each satisfying the shared `CapitalModel` / `CapitalSchedule` protocols,
and widened both return-on-capital entry points (`ProfitTester.run_with_capital`,
`Portfolio.run_with_capital`) to those protocols. But the only surface that
selects a model — the CLI `--capital` flag and the API `capital_model` field —
was still hard-wired to `licat`: both rejected `rbc` and `solvency2`. A reinsurer
therefore still could not actually *price* a US or EU deal on a return-on-capital
basis from either machine surface, despite the calculators existing. The planned
Slice 4 (CLI + API + Excel + dashboard + validation notebook + result-level ratio
surface) is LARGE; this ADR records the first sub-slice (4a), the two machine
surfaces, decomposed out so each ships as an independently mergeable, fully tested
PR.

**Decision.** Add one shared registry/resolver and route both surfaces through it.

1. **Single registry in `analytics/capital_base.py`.** A `SUPPORTED_CAPITAL_MODELS`
   tuple `("licat", "rbc", "solvency2")`, a `CapitalModelId` literal type alias,
   and a `capital_model_for(model_id, product_type) -> CapitalModel` factory. The
   factory normalises the id (strip + lower-case), then constructs the matching
   calculator via its `for_product`. The concrete-calculator imports are **deferred
   to call time** because `rbc` / `capital` / `solvency2` import `capital_base` for
   `discount_stream` / `strain_of` — a module-level import here would be circular.
   This is the one place a fourth jurisdiction will be added.

2. **CLI.** The `--capital` validation widens from `!= "licat"` to
   `not in SUPPORTED_CAPITAL_MODELS`; `_run_profit_tests` resolves the model via
   `capital_model_for` instead of constructing `LICATCapital` directly. The error
   message lists the supported ids.

3. **API.** The `capital_model` field type widens from `Literal["licat"]` to the
   shared `CapitalModelId`, so Pydantic accepts `rbc` / `solvency2` and still 422s
   on anything else; the price handler resolves via `capital_model_for`.

The capital output block (RoC, peak capital, PV strain, capital-adjusted IRR) is
already jurisdiction-agnostic — it reads only the `CapitalSchedule` surface — so
no output-shaping code changed; RBC and Solvency II render through the same JSON /
console path LICAT already used.

**Verification anchors.** New `test_capital_base.py` (13) locks the registry:
every supported id resolves to its calculator class and satisfies the
`CapitalModel` protocol; the id is case-insensitive / whitespace-tolerant; an
unknown id raises `ValueError` listing the supported ids; product type drives the
factor defaults. The CLI gains parametrised `rbc` / `solvency2` end-to-end JSON
tests plus a three-way "distinct peak capital" test proving the selector routes to
a genuinely different calculator (not a silent LICAT fallback); the API gains the
mirror parametrised acceptance tests. The two pre-existing rejection tests
(`test_capital_invalid_value_exits_non_zero`, `test_price_capital_model_invalid_value_returns_422`)
used `solvency2` as the *unknown* value — now that it is valid, they move to a
still-unknown id (`bogus`). This is the one place the surface contract legitimately
changed an existing assertion.

**Behaviour change.** Only for runs that explicitly request `--capital rbc` or
`--capital solvency2` (previously an error, now a priced result). The default
(no `--capital`) and `--capital licat` paths are byte-identical — QA golden suite
(72) green, no rebaseline.

**Out of scope (filed as follow-ups / planned Slice 4b).** The Excel capital-sheet
jurisdiction label + ratio, the dashboard `--capital` selector, and the
three-standard validation notebook on the golden block. The result-level
solvency/RBC-ratio surface (own funds-or-TAC ÷ SCR-or-ACL) needing an external
own-funds / TAC input the RoC entry points do not hold (Slice 4b, with the input).
The shock-based factor calibration (C0 Asset/ALM epic).

---

## ADR-102: Surface the jurisdiction selector on the dashboard and Excel (Epic 3, Slice 4b)

**Date:** 2026-06-23
**Status:** Accepted

**Context.** Slice 4a (ADR-101) routed the two *machine* surfaces (CLI `--capital`,
API `capital_model`) through the shared `capital_model_for` registry, so US RBC and
EU Solvency II could finally be priced from a script. But the two *presentation*
surfaces still hard-coded LICAT: the Streamlit Deal Pricing page ran capital ONLY
when `capital_model_id == "licat"` (its checkbox was literally "Compute LICAT
capital + RoC", and any other id silently dropped into the no-capital branch), and
the deal-pricing Excel workbook labelled the capital block "LICAT" regardless of
which calculator produced the numbers. A reinsurer driving the engine through the
dashboard — the primary interactive surface — therefore could not reach RBC or
Solvency II at all, and an Excel export gave no indication of the standard it was
computed under. The planned single Slice 4 proved LARGE, so it was decomposed into
4a (machine surfaces, shipped) and this 4b (presentation surfaces).

**Decision.** Route both presentation surfaces through the same registry, and add a
shared display-label map so the displayed standard always matches the calculator
that ran.

1. **Shared labels in `analytics/capital_base.py`.** A `CAPITAL_MODEL_LABELS`
   dict keyed by the same `SUPPORTED_CAPITAL_MODELS` ids (`licat → "LICAT
   (Canada)"`, `rbc → "US RBC"`, `solvency2 → "EU Solvency II"`) plus a
   `capital_model_label(model_id)` helper that normalises the id, defaults `None`
   to LICAT (every pre-ADR-098 capital schedule was LICAT by construction), and —
   because labels are a *display* concern, not a validation boundary — returns an
   unknown id upper-cased rather than raising. One place to label a fourth
   jurisdiction, co-located with the factory it mirrors.

2. **Dashboard.** The "Compute LICAT capital + RoC" checkbox becomes a
   "Regulatory capital basis (RoC)" selectbox (None / LICAT / US RBC / EU Solvency
   II) mapping to a registry id; `_run_pricing_for_cohort`'s `== "licat"` branch
   widens to `is not None` and resolves via `capital_model_for` (so the LICAT path
   is byte-identical — `capital_model_for("licat", …)` *is*
   `LICATCapital.for_product(…)`). The chosen id rides on `CohortPricingData`, and
   the cedant / reinsurer capital tiles caption the basis and drop "LICAT" from
   their help text in favour of the live label.

3. **Excel.** `DealPricingExport` gains a `capital_model_id: str | None = None`
   field (default preserves byte-identical pre-Slice-4b workbooks); the Summary
   capital block gains a "Regulatory Capital — {label}" header row directly above
   the metrics. The CLI threads its `--capital` id onto the export.

**Verification anchors.** `test_pricing_capital_jurisdiction.py` (6) drives
`_run_pricing_for_cohort` per jurisdiction: each of licat/rbc/solvency2 now yields a
`ProfitResultWithCapital`, `None` yields a plain result, and the three standards
give pairwise-distinct peak capital on the same block (the dashboard analogue of
4a's three-way CLI test — a guard against a silent collapse to one calculator).
`test_capital_base.py` gains a label-map class (every supported id labelled, known
ids mapped, `None → LICAT`, unknown upper-cased not raised).
`test_excel_output.py::TestCapitalJurisdictionHeader` (5) locks the header text per
jurisdiction, its position directly above "Peak Capital", the `None → LICAT`
default, and its absence when no capital ran.

**Behaviour change.** Dashboard runs can now select RBC / Solvency II (previously
unreachable); Excel capital blocks gain a jurisdiction header row. The default
(no capital) dashboard run and Excel workbook are unchanged, and the LICAT capital
path is byte-identical. Full fast suite 1634 green; QA golden suite green; the
`polaris price` golden run is structurally unchanged (no `--capital`, no header).

**Out of scope (filed as follow-ups / planned Slice 4c).** The result-level
solvency/RBC-ratio surface (own funds-or-TAC ÷ SCR-or-ACL) still needs an external
own-funds / target-multiple input the RoC entry points do not hold — deferred to
Slice 4c, which introduces that input. The three-standard validation notebook on
the golden block (deferred to 4c with the ratio so the notebook can demonstrate
both the three calculators and the ratio in one place). The shock-based factor
calibration remains the C0 Asset/ALM epic.

---

## ADR-103: Result-level regulatory solvency ratio surface (Epic 3, Slice 4c-1)

**Date:** 2026-06-23
**Status:** Accepted

**Context.** Slices 1–4b gave all three capital calculators (`LICATCapital`,
`RBCCapital`, `SolvencyIICapital`), both return-on-capital entry points
(`ProfitTester.run_with_capital`, `Portfolio.run_with_capital`), and the full
CLI / API / dashboard / Excel jurisdiction selector. One gap remained: the
*regulatory solvency ratio* — the headline number a committee reads (RBC ratio,
EU solvency ratio, LICAT total ratio) — was unreachable from
`ProfitResultWithCapital`. `RBCResult` exposed `rbc_ratio(tac)` on the raw
schedule, but `run_with_capital` returned a jurisdiction-agnostic result that
carried none of it, and there was no way to feed in the external numerator the
ratio needs. Slices 2–4b deferred the ratio precisely because it needs an
**available-capital input the RoC path does not hold**: RoC is driven entirely
by the projected cash flows and the capital *schedule*, whereas the ratio
divides a company-supplied available capital / TAC / own funds by the standard's
required-capital denominator. The planned Slice 4c (ratio surface across every
consumer + a three-standard validation notebook) proved LARGE once detailed, so
it was re-decomposed into **4c-1 (this ADR — the result-level ratio core, data
model first)** and **4c-2 (CLI flag + API field + Excel row + dashboard input +
validation notebook)**.

**Decision.** Add the solvency ratio as a jurisdiction-agnostic surface on the
`CapitalSchedule` protocol and thread a single optional input through
`run_with_capital`, keeping the per-jurisdiction denominator encapsulated on
each result.

1. **`CapitalSchedule.capital_ratio(available_capital)` (protocol method).**
   Returns the standard's solvency ratio at issue (a multiple): `available_capital
   / denominator₀`. The denominator is encapsulated per implementation —
   `CapitalResult` (LICAT) and `SolvencyIIResult` use `capital_by_period[0]`
   (required capital / SCR), `RBCResult` uses `authorized_control_level[0]`
   (ACL = ½ the Company Action Level it holds). All three raise
   `PolarisComputationError` on a non-positive t=0 denominator (an all-stub
   factor set). `RBCResult.rbc_ratio` is retained as a thin RBC-named alias of
   `capital_ratio`, so existing callers and tests are unaffected.

2. **`ProfitTester.run_with_capital(..., available_capital: float | None = None)`.**
   When supplied, the ratio is computed via `capital.capital_ratio(...)` and
   surfaced on the result; when omitted (the default), it is None. The new
   `ProfitResultWithCapital` fields `available_capital` and `capital_ratio` both
   default to None, so every existing caller and the entire RoC path are
   byte-identical.

**Why a protocol method, not a `ratio_denominator` attribute.** The numerator is
uniform across jurisdictions (available capital), but the *denominator* is the
genuine jurisdictional difference (ACL is half the held capital for RBC; the
held capital itself for LICAT / Solvency II). Encapsulating the whole ratio
behind one method keeps that choice in the result class that owns it, rather than
leaking the "RBC divides by half" rule into the consumer.

**Verification anchors.** `test_profit_test.py::TestRunWithCapitalRatio` (6):
ratio None when `available_capital` omitted; LICAT total ratio = available /
required₀; RBC ratio = TAC / ACL₀; EU solvency ratio = own funds / SCR₀;
supplying `available_capital` disturbs none of the RoC / base fields; a
zero-capital model raises. Per-result closed forms in
`test_capital.py::TestCapitalResult` (LICAT ratio + zero-denominator raise),
`test_rbc.py::TestRBCResultHelpers` (`capital_ratio` == `rbc_ratio`, ACL-zero
raise), and `test_solvency2.py::TestSolvencyRatio` (own-funds/SCR + SCR-zero
raise).

**Behaviour change.** None on any existing path — the protocol gains a method,
each result class gains it, and `run_with_capital` gains an optional keyword that
defaults to the prior behaviour. The two new result fields default to None.
Goldens byte-identical: no consumer supplies `available_capital` yet (that is
Slice 4c-2). Contract change (protocol + `ProfitResultWithCapital`) is additive
and backward-compatible; flagged for human review in the PR.

**Out of scope (Slice 4c-2).** Threading `available_capital` through the CLI
(`--available-capital` / target-multiple flag), the API request field, the Excel
capital block (a ratio row), and the dashboard (a number-input + tile), plus the
three-standard validation notebook comparing LICAT / RBC / Solvency II on the
golden block and demonstrating the ratio. The held-capital-basis question
(configurable target multiple of ACL vs fixed CAL) remains open and is the
natural companion to the CLI input in 4c-2. The shock-based factor calibration
remains the C0 Asset/ALM epic.

## ADR-104: Thread the available-capital numerator through the CLI and REST API (Epic 3, Slice 4c-2a)

**Date:** 2026-06-24
**Status:** Accepted

**Context.** Slice 4c-1 (ADR-103) added the result-level solvency ratio *core*:
`CapitalSchedule.capital_ratio(available_capital)` on all three result classes
and the optional `ProfitTester.run_with_capital(..., available_capital=...)`
keyword that surfaces `available_capital` / `capital_ratio` on
`ProfitResultWithCapital`. The computation is done, but **no consumer supplies
the numerator**, so the ratio is never visible: the CLI has no flag, the API
request has no field, and neither output emits the ratio. The planned Slice 4c-2
(thread the input through CLI + API + Excel + dashboard, plus a three-standard
validation notebook) proved LARGE once detailed — five surfaces, two of them
presentation rebuilds (an Excel ratio row, a dashboard number-input + tile) and
a notebook. Per the routine's allowance for a slice that proves larger than
expected (the same allowance that split 4 → 4a/4b/4c and 4c → 4c-1/4c-2), 4c-2
was re-decomposed into **4c-2a (this ADR — the machine surfaces: CLI flag + API
field)**, **4c-2b (presentation surfaces: Excel ratio row + dashboard input +
tile)**, and **4c-2c (three-standard validation notebook)** — mirroring the
machine-then-presentation split this epic used at 4a/4b.

**Decision.** Thread a single `available_capital` numerator through the two
machine surfaces and emit the resulting `capital_ratio` on each side.

1. **CLI `--available-capital FLOAT`.** Threaded through `_price_single_cohort`
   → `_run_profit_tests` → both sides' `run_with_capital(..., available_capital=)`.
   Each cohort's cedant and reinsurer results gain `available_capital` (echoed)
   and `capital_ratio` in the JSON capital block, plus a "Solvency Ratio" row on
   the Rich capital table. Validated eagerly: requires `--capital` (a ratio needs
   a jurisdictional denominator) and must be positive — either misuse exits 1 with
   a clear message rather than being silently ignored.

2. **API `available_capital` request field** (`gt=0`), with a `model_validator`
   that rejects (422) `available_capital` without `capital_model`. Threaded into
   both `run_with_capital` calls; the response gains `available_capital`,
   `capital_ratio` (cedant view) and `reinsurer_capital_ratio` (reinsurer view).

**Why apply the same numerator to both cedant and reinsurer.** The numerator
(available capital held) is a single supplied figure; each *perspective* divides
it by its own required-capital denominator (LICAT total / RBC ACL / EU SCR), so
the two ratios differ and are individually meaningful. This is symmetric with how
peak capital and RoC are already surfaced for both sides from the same model, and
it requires **no assumption about how to split capital between the parties** — the
user supplies the figure for the entity they are evaluating (typically the
reinsurer) and reads that side's ratio. A per-side numerator is a later
refinement, not a correctness gap here.

**Verification anchors.** `test_cli.py::TestPriceCommandAvailableCapital` (6):
ratio + echoed numerator in JSON; ratio linear in the numerator (double available
→ double ratio, denominator fixed); "Solvency Ratio" console row; `--available-capital`
without `--capital` exits 1; non-positive exits 1; `--capital` without
`--available-capital` leaves the ratio null. `test_main.py` (5): ratio populated
on both views; ratio linear in the numerator; 422 without `capital_model`; 422 on
non-positive; null ratio when the numerator is omitted.

**Behaviour change.** None on any path that does not pass the new input. The CLI
flag and API field default to None → `capital_ratio` is None and the JSON / Rich
/ response are byte-identical to ADR-103 (the `--capital`-only path already had
the capital block; the two new fields are additive nulls). The golden `polaris
price` run passes no `--capital`, so no capital block is emitted at all — goldens
byte-identical, QA golden suite (72) green.

**Out of scope (Slice 4c-2b / 4c-2c).** Rendering the ratio on the Excel capital
block (a ratio row under the 4b jurisdiction header) and the dashboard (a
number-input + tile) is 4c-2b; the three-standard validation notebook comparing
LICAT / RBC / Solvency II on the golden block and demonstrating the ratio is
4c-2c. The held-capital-basis question (a configurable target *multiple* of ACL
as an alternative numerator form, rather than an absolute figure) remains open
and is the natural companion to the dashboard input in 4c-2b. The shock-based
factor calibration remains the C0 Asset/ALM epic.

## ADR-105: Config-driven golden-regression harness (QA test infrastructure)

**Date:** 2026-06-24
**Status:** Accepted

**Context.** `data/qa/` ships four pricing configs (`golden_config_flat`,
`golden_config_yrt`, `golden_config_coins`, `golden_config_policy_cession`), but
`tests/qa/golden_outputs/` pinned byte-level baselines for only two (`flat`,
`yrt`). The `coins` and `policy_cession` pipeline paths were exercised end-to-end
only by CLI **smoke** tests (`test_cli_golden.py::TestCLIGoldenSmoke` — exit-0, no
value assertion), so a silent numeric regression in the coinsurance proportional
**reserve transfer** (CLAUDE.md §9 — actuarially subtle) or in policy-level
cession weighting would have passed the QA suite. Root cause: both the generator
(`generate_golden.py`) and the regression test (`test_pipeline_golden.py`)
hand-built `PipelineInputs` in Python for only `flat`/`yrt` and never read the
JSON configs, so the committed config set and the in-code baseline set could
drift independently. (PR #103 automated review, P2 finding; promoted to
`PRODUCT_DIRECTION_2026-06-18` as IMPORTANT.)

A latent inconsistency confirmed the gap: the hand-built `flat`/`yrt` inputs used
`LapseConfig()` (its default `DEFAULT_LAPSE_CURVE`), while the JSON configs carry
an explicit `duration_table`. They happen to be identical today
(`DEFAULT_LAPSE_CURVE` == the config table), so the baselines stayed valid — but
nothing enforced that the baseline was generated from the same inputs the CLI
consumes.

**Decision.** Make the four `data/qa/golden_config_*.json` files the single
source of truth for both the generator and the regression test.

1. **`tests/qa/golden_runner.py` (new, pytest-free).** Enumerates
   `golden_config_*.json` into `GoldenCase` records (baseline name, config path,
   `needs_soa`), loads each through the CLI's own parser
   (`_parse_config_to_pipeline_inputs`), and prices the shared golden inforce
   block through one `run_pricing` used by both the generator and the test — so a
   baseline can never disagree with what the test recomputes. Importing no pytest
   lets the standalone generator script import it directly.
2. **`generate_golden.py`** rewritten to iterate the discovered cases (skipping
   SOA-dependent configs under `--flat-only` or when the tables are absent). It
   reproduces the existing `flat`/`yrt` baselines **byte-identically** and adds
   `golden_coins.json` + `golden_policy_cession.json`.
3. **`test_pipeline_golden.py`** rewritten: a single regression parametrized over
   the discovered configs (per-config `@requires_soa`-style skip by mortality
   source — `flat` always runs, SOA configs gated), plus a **drift guard**
   (`test_every_config_has_committed_baseline`) that fails loudly when any
   `golden_config_*.json` lacks a committed baseline. Any future config is
   auto-covered by the regression and protected by the guard.

**Per-config SOA gating.** A config's `needs_soa` is derived from its
`mortality.source` (`flat` → always-on, CI-safe; anything else → requires the SOA
VBT 2015 tables). This replaces the per-test `@requires_soa_tables` decorator on
the two hard-coded classes with a data-driven decision that scales to new
configs.

**Verification.** The config-driven generator reproduces `golden_flat.json` and
`golden_yrt.json` byte-for-byte (git shows them unmodified); the two new
baselines are actuarially coherent (50/50 coinsurance yields near-equal
cedant/reinsurer profit PVs — the correct proportional split; policy-cession
yields divergent cedant/reinsurer PVs from the per-policy overrides). Full QA
suite 76 passed (was 72: +2 regression cases, +2 coverage/discovery guards). The
drift guard was confirmed to fail on a temporary unbaselined config and the
`--flat-only` path to skip the three SOA configs.

**Behaviour change.** None to the engine — pure test infrastructure. No
`src/polaris_re/` code changed. The two new baselines are additive; the existing
two are unchanged.

**Out of scope.** This pins the same per-cohort summary metrics the prior golden
captured (PV profits, margins, gross premiums/claims). A finer-grained
cash-flow-vector golden, and goldens for treaty types not yet represented by a
config (Modco, stop-loss), are future work — but any new
`data/qa/golden_config_*.json` is now auto-discovered and guarded, so adding one
is a one-file change plus a committed baseline.

---

## ADR-106: Surface the solvency ratio on the Excel block and dashboard (Epic 3, Slice 4c-2b)

**Date:** 2026-06-26
**Status:** Accepted

**Context.** Slice 4c-1 (ADR-103) added the result-level solvency-ratio *core*
(`CapitalSchedule.capital_ratio(available_capital)` and the optional
`ProfitTester.run_with_capital(..., available_capital=...)` keyword, which echoes
`available_capital` / `capital_ratio` onto `ProfitResultWithCapital`). Slice
4c-2a (ADR-104) threaded the numerator through the two **machine** surfaces — the
CLI `--available-capital` flag and the API `available_capital` field — so the
ratio is now reachable from the command line and the REST API. The two
**presentation** surfaces still ignored it: the Excel deal-pricing workbook's
capital block (ADR-049 / ADR-102) stopped at `Capital-Adjusted IRR`, and the
Streamlit Deal Pricing page called `run_with_capital` *without*
`available_capital`, so `result.capital_ratio` was always `None` and no ratio
tile could render. A reinsurer pricing a deal in the dashboard or handing a
counterparty the Excel workbook saw RoC and peak capital but not the regulatory
solvency ratio the CLI/API already computed.

**Decision.** Render the ratio on both presentation surfaces, reading the
numerator and ratio that **already ride on the result objects** (ADR-104) — no
new transport field is added to `DealPricingExport` or `CohortPricingData`.

1. **Excel (`utils/excel_output.py`).** Below the jurisdiction-labelled capital
   block, append two rows — `Available Capital` (`$#,##0`) and `Solvency Ratio`
   (`0.0%`) — **only when** a rendered result carries a non-`None`
   `capital_ratio`. A new `_CAPITAL_RATIO_METRICS` tuple drives the rows through
   the existing `_write_capital_cell` (extended with the two metric names);
   per-side `N/A` for a side that has no numerator (e.g. a plain reinsurer result
   in a mixed run), mirroring the existing capital-cell convention. The CLI
   already passes the numerator into `run_with_capital`, so the cohort results
   threaded onto the export carry the ratio with no further CLI change.

2. **Dashboard (`dashboard/views/pricing.py`).** A `number_input` "Available
   capital (solvency-ratio numerator, $)" appears under the capital-basis
   selectbox **only when** a basis is chosen; `> 0` threads
   `available_capital` through `_run_pricing_for_cohort` into both sides'
   `run_with_capital(..., available_capital=)`. When a result then carries a
   ratio, the cedant and reinsurer capital tile rows widen from three columns to
   four, adding a "Solvency Ratio" tile (the supplied numerator over that side's
   own required capital).

**Why no new export/cohort field.** The 4c-2b plan anticipated "threading the
numerator through `DealPricingExport` and `CohortPricingData`", but 4c-1 already
echoes `available_capital` and `capital_ratio` onto `ProfitResultWithCapital`,
and both surfaces already carry those result objects. Reading `result.capital_ratio`
/ `result.available_capital` directly is the same pattern used for every other
capital metric (peak, RoC, strain) and keeps a single source of truth for the
numerator — adding a parallel field on the export would risk the two drifting.

**Byte-identical guarantee.** Both surfaces gate the new output on
`capital_ratio is not None`. A capital run *without* a numerator (the common
case, and every pre-4c-2b run) renders neither Excel row and keeps the
three-tile dashboard layout — byte-identical to ADR-102 / pre-Slice-4c-2b. The
no-capital path is untouched.

**Verification anchors.** `test_excel_output.py::TestSummarySheetSolvencyRatio`
(6): rows absent on a capital run with no numerator and on a no-capital run; both
rows present when a numerator is supplied; the two rows sit directly below
`Capital-Adjusted IRR`; cedant ratio + numerator values match; reinsurer cell
`N/A` in a mixed run. `test_pricing_solvency_ratio.py` (8): numerator `None`
leaves the ratio `None`; supplying it populates a finite ratio for each
jurisdiction; the ratio scales linearly with the numerator (denominator fixed);
the three standards give distinct ratios on the same block.

**Out of scope (Slice 4c-2c and beyond).** The three-standard validation
notebook comparing LICAT / RBC / Solvency II on the golden block and
demonstrating the ratio is 4c-2c. The held-capital-basis question (a configurable
target *multiple* of ACL as an alternative numerator form, rather than an
absolute figure) remains open and is the natural companion to the dashboard
input; it is not implemented here. A per-side numerator (distinct available
capital for cedant vs reinsurer) remains the later refinement noted in ADR-104.

## ADR-107: Three-standard capital validation notebook (Epic 3, Slice 4c-2c)

**Date:** 2026-06-26
**Status:** Accepted

**Context.** Slices 1–4c-2b built the cross-jurisdiction capital stack: the three
calculators (`LICATCapital`, `RBCCapital`, `SolvencyIICapital`, ADR-098/100), the
shared `CapitalModel` / `CapitalSchedule` protocols and the `capital_model_for`
registry (ADR-101), the result-level solvency-ratio surface (ADR-103) and its
machine + presentation surfacing (ADR-104/106). The epic's plan reserved a final
slice for a **validation notebook** comparing the three standards on a single
block side by side — the demonstration artifact that closes the epic, mirroring
`02_reserve_basis_comparison.ipynb` for the reserve-basis epic. This slice adds no
`src/` code; it consumes the existing analytics surfaces.

**Decision.** Add `notebooks/03_capital_standards_comparison.ipynb`. It prices one
self-contained term block (flat synthetic mortality + lapse, no CSV load), derives
the Net Amount at Risk transparently (`max(face·inforce_ratio − reserve, 0)`, the
same formula the YRT treaty uses), and feeds the **identical** NAR to all three
standards via `capital_model_for(id, TERM)` + `ProfitTester.run_with_capital(...,
nar=, available_capital=)`. It tabulates, side by side: the required-capital
run-off (`capital_by_period` at issue / yr 1 / 5 / 10 / 15), peak and PV capital,
return on capital, and the regulatory solvency ratio.

**Honest presentation of un-calibrated standards.** The component factors are
committee-stage placeholders (ADR-098/100): LICAT's default C-2 is a **10%
mortality shock** on NAR, while RBC's C-2 (0.15% of NAR) and Solvency II's
mortality sub-factor (0.20% of NAR) are small ongoing factors (the aggregated EU
SCR runs a touch higher — ~0.28% of NAR at issue — once the +0.15% catastrophe
shock is folded in via the standard-formula correlation matrices), so the
required-capital *levels* differ by ~50–100x and are **not yet mutually
calibrated**. Rather than hide this behind hand-tuned factors, the
notebook surfaces it as the explicit teaching point: a leading calibration caveat,
and a demonstration that the solvency ratio is meaningful **within** a standard
(linear in available capital — double the held capital, double the ratio, the
property pinned by the 4c-1/4c-2 unit tests) but **not** comparable in level
across standards until the Asset/ALM calibration epic. The single $900,000
available-capital figure yields a realistic 120% LICAT ratio and deliberately
out-of-band RBC/EU ratios, which the narrative explains rather than masks.

**Why no dedicated test.** Notebooks are dev/demonstration artifacts (omitted from
coverage in `pyproject.toml`, launched via `make notebook`), exactly as
`01_term_life_yrt_pricing.ipynb` and `02_reserve_basis_comparison.ipynb`. The
notebook adds no new calculation — every surface it calls is already closed-form
tested (`TestRunWithCapitalRatio`, the per-result ratio tests, the linearity
tests). Its verification is that it executes top-to-bottom cleanly, which it does;
the committed file carries the executed outputs.

**Byte-identical guarantee.** No `src/`, `data/`, or test change — the QA golden
suite (76) and full fast suite (1664) are unaffected and no baseline is
regenerated.

**Out of scope.** The held-capital-basis question (a configurable target *multiple*
of ACL as an alternative numerator form), the per-side numerator (distinct
available capital for cedant vs reinsurer), and the cross-standard factor
calibration (the Asset/ALM epic that would make the required-capital *levels*
mutually comparable) all remain open; they are harvested to PRODUCT_DIRECTION as
this slice closes the epic.

---

## ADR-108: Bond cash-flow model and `AssetPortfolio` (Epic 4 / Asset-ALM, Slice 1)

**Date:** 2026-06-26
**Status:** Accepted

**Context.** With the three Tier-A credibility/market-access epics shipped
(reserve-basis matching, IFRS 17 movement, cross-jurisdiction capital — all
merged by 2026-06-26), the next epic in the recommended sequence of
`docs/COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md` (§4) is the **Asset / ALM
model** (Tier-C C0, ROADMAP Milestone 5.4). Until now the engine is
liability-only: `ModcoTreaty` prices its modco interest on a single flat
`modco_interest_rate`, there is no investment-income model, and no
duration/convexity or asset-liability duration-gap analysis exists — so a Modco
or coinsurance economic result is only as good as a hand-set yield. The epic is
decomposed in `docs/PLAN_asset_alm.md` into four slices; this ADR records
Slice 1, the asset-side data model.

**Decision.** Add `core/asset.py` with two frozen `PolarisBaseModel`s:

- **`Bond`** — a single fixed-income instrument valued on the monthly
  projection grid: `face_value`, `coupon_rate`, `coupon_frequency` (must divide
  12, so coupons land on integer months), `term_months`, and an optional
  `book_value` (resolved to par via a `carrying_value` property when unset).
  `cash_flow_vector(months)` projects coupon + principal to a `(months,)`
  float64 array (1-indexed, end-of-month: index `i` is month `i+1`), and
  `price(annual_yield)` discounts it.
- **`AssetPortfolio`** — a non-empty list of `Bond`s with `cash_flow_vector`
  (sum of constituents, defaulting to the longest term), `market_value`,
  `book_value`, and `total_face_value`.

**Discounting convention.** Bond pricing uses the **same** effective-annual
monthly discounting as `CashFlowResult.pv_*`: `v = (1 + annual_yield) ** (-1/12)`,
cash flow at month `t` discounted by `v ** t`. This is deliberate — it keeps a
bond PV and a projection PV on a single comparable basis, which the Slice 3
Modco integration and Slice 4 ALM duration-gap analysis rely on. The closed-form
par-bond test (annual-pay, coupon = yield → price = face) holds exactly under
this convention because the coupon-plus-redemption series telescopes to par.

**Verification.** 34 closed-form / validation tests: par-bond-to-par,
zero-coupon `face·(1+y)^(-N/12)`, premium/par/discount pricing, coupon timing
on the monthly grid (annual + semiannual), horizon truncation/padding,
portfolio aggregation = sum of constituents, and field validation
(`coupon_frequency` divides 12, positive face/term, non-negative coupon/book,
non-empty portfolio).

**Byte-identical guarantee.** Purely additive new module exported from
`polaris_re.core`; nothing is wired into any product, treaty, or pricing path,
so the QA golden suite and full fast suite are unaffected and no baseline is
regenerated. The Modco wiring is Slice 3.

**Out of scope (this slice).** Investment income and duration/convexity
(Slice 2), the Modco integration (Slice 3), the `analytics/alm.py` duration-gap
analysis and CLI/API/dashboard/Excel surfacing (Slice 4). Stochastic
reinvestment yields (Hull-White / CIR via `analytics/stochastic.py`),
non-fixed-income asset classes (equities, mortgages), and asset
default/credit-migration modelling (the C-1 capital component already owns
that) are out of scope for the whole epic and are harvested to
PRODUCT_DIRECTION as follow-ups.

## ADR-109: Book yield, investment income, duration / convexity (Epic 4 / Asset-ALM, Slice 2)

**Date:** 2026-06-27
**Status:** Accepted

**Context.** ADR-108 (Slice 1) gave `AssetPortfolio` its cash-flow vector and
pricing. Slice 2 of `docs/PLAN_asset_alm.md` adds the asset *measures* the rest
of the epic consumes: the **book yield** Slice 3 hands to the Modco treaty, the
**investment income** that yield throws off on a reserve balance, and the
**duration / convexity** Slice 4's duration-gap analysis compares to the
liability. Still purely additive — nothing is wired into pricing — so goldens
stay byte-identical.

**Decision.** Extend `AssetPortfolio` with:

- **`book_yield() -> float | None`** — the gross effective-annual IRR of the
  total carrying value vs the portfolio's projected cash flows. Solved with
  `scipy.optimize.brentq` over `[-0.99, 100.0]` (the same solver and bracket as
  `ProfitTester.irr`) and returns `None` when the bracket has no sign change,
  mirroring the profit tester's None-on-no-sign-change guard. It is a **flat
  scalar** held over the horizon (maintainer decision, PLAN §5) — not a
  weighted-average-coupon proxy and not a time-varying amortising earned rate.
- **`investment_income(reserve_vector, annual_yield=None) -> np.ndarray`** —
  `reserve_vector · y / 12` per month, where `y` is the supplied yield or
  `book_yield()`. This is exactly the modco-interest stream Slice 3 needs.
  Raises `PolarisComputationError` when no yield is supplied and `book_yield()`
  has no recoverable IRR.
- **`macaulay_duration(y)` / `modified_duration(y)` / `convexity(y)`** — the
  PV-weighted average time and its first/second sensitivities.

**Time-in-years convention.** All three risk measures discount the aggregate
cash-flow vector on the engine convention (`v = (1+y)^(-1/12)`, month `t`
discounted by `v**t`) but express time in **years** (`τ_t = t/12`). Under the
effective-annual yield `y` this gives the textbook forms: Macaulay
`= Σ τ·PV / Σ PV` (years), modified `= Macaulay / (1+y)`, and convexity
`= Σ τ(τ+1)·PV / (P·(1+y)²)` (years²). The `(1+y)` divisor on modified duration
(not a periodic-rate variant) is the correct sensitivity because the engine's
yield is effective-annual. For a zero maturing in `N` years this reduces to the
closed forms duration `= N` and convexity `= N(N+1)/(1+y)²`.

**Verification.** 17 new closed-form / property tests: par-book book yield
recovers the coupon; a zero carried at `face·(1+y₀)^(-N/12)` recovers `y₀`;
book yield `None` when carried at zero (no sign change); market value reconciles
to carrying value at the solved yield; investment income `= reserve·y/12` (both
explicit-yield and book-yield paths) and raises without a recoverable yield;
Macaulay duration of a zero `= N` years; modified `= Macaulay/(1+y)`; convexity
of a zero matches `N(N+1)/(1+y)²`; portfolio duration is the price-weighted
average of constituents'; coupon-bond duration `<` maturity; convexity rises
with maturity.

**Byte-identical guarantee.** Additive `AssetPortfolio` methods only; no
product, treaty, or pricing path touched. QA golden suite (76) and the
`polaris price` golden run are unchanged; no baseline regenerated.

**Out of scope (this slice).** Wiring the book yield into `ModcoTreaty`
(Slice 3) and the `analytics/alm.py` duration-gap analysis + CLI/API/
dashboard/Excel surfacing (Slice 4). A **net-of-spread** earned rate (net of an
investment-expense / default margin, kept distinct from the C-1 capital
component to avoid double-counting asset-default risk) and a **time-varying**
amortising earned rate were considered and deferred as NICE-TO-HAVE follow-ups
(maintainer decision, PLAN §5; already harvested to PRODUCT_DIRECTION). The
non-positive-price guard on the duration/convexity methods is defensive — it is
unreachable through the public API with valid bonds (positive cash flows
discounted at any `y > -1` give a positive price).

## ADR-110: Asset-driven modco interest (Epic 4 / Asset-ALM, Slice 3)

**Date:** 2026-06-27
**Status:** Accepted

**Context.** ADR-108/109 (Slices 1–2) built `AssetPortfolio` and the asset
measures — most importantly `book_yield()`, the gross effective-annual IRR of
the portfolio's carrying value vs its cash flows. Today `ModcoTreaty.apply()`
prices modco interest on a single flat `modco_interest_rate`, hand-set by the
analyst. Slice 3 of `docs/PLAN_asset_alm.md` lets the assets backing the ceded
reserve actually drive that interest, turning Modco from "approximate" (a
guessed credited rate) into "correct" (the rate the asset book earns). This is
the only behavioural payoff of the epic before the Slice 4 ALM surfacing.

**Decision.** `ModcoTreaty.apply()` gains an optional
`asset_portfolio: AssetPortfolio | None = None` argument. A new private helper
`_resolve_modco_rate(asset_portfolio)` returns the effective annual rate the
existing modco-interest formula multiplies by:

    modco_interest_t = ceded_reserve_balance_t * modco_rate / 12

The three resolved design decisions (PLAN §5, maintainer-confirmed 2026-06-26)
are now binding and recorded here:

- **Gross flat book yield.** `modco_rate` is the portfolio's `book_yield()` — a
  single scalar held flat over the horizon, gross of any spread. Not a
  weighted-average-coupon proxy and not (yet) a time-varying amortising earned
  rate.
- **Deterministic reinvestment.** Epic 4 is deterministic: the book yield *is*
  the (flat) reinvestment yield. Stochastic reinvestment (Hull-White / CIR via
  `analytics/stochastic.py`) stays an out-of-scope NICE-TO-HAVE follow-up.
- **Option A precedence.** When both an `AssetPortfolio` and a flat
  `modco_interest_rate` are supplied, the asset book yield **takes precedence**;
  the flat rate is the fallback, used only when `book_yield()` has no recoverable
  IRR (returns `None`). Omitting the portfolio (`None`, the default) returns the
  flat rate unchanged, so the existing path is byte-identical.

**Why a scalar rate, not `investment_income()`.** Slice 2 framed
`investment_income(reserve_vector)` as "the modco-interest stream Slice 3 needs",
and on a flat book yield it computes exactly `reserve · y / 12`. We resolve the
rate to a scalar and reuse the *existing* modco-interest line instead, for two
reasons: (1) the no-portfolio path then multiplies by `self.modco_interest_rate`
with the identical arithmetic it always has, guaranteeing byte-identical
goldens; and (2) `investment_income()` raises on an unrecoverable book yield,
whereas modco needs the flat rate as a graceful fallback. The two expressions
are numerically equal on the asset path.

**Additivity.** NCF additivity (ARCHITECTURE §5) is unchanged by the rate
source: `modco_interest` is added to the ceded side and subtracted from the net
side, so it cancels in `net + ceded` regardless of how `modco_rate` was
resolved. Verified with `verify_additivity` on the asset-driven path.

**Verification.** 6 new tests in `tests/test_reinsurance/test_modco.py`: a
closed-form check that an annual-pay par bond (carried at par) yields its coupon
and drives `modco_interest = ceded_reserve · 0.05 / 12`; precedence of the book
yield over a deliberately-different flat rate (matched against a flat treaty
pinned at the book yield); fallback to the flat rate when `book_yield()` is
`None` (bond carried at zero book value); byte-identical no-portfolio path
(`asset_portfolio=None` equals the default call, exact equality); additivity
with an asset-driven rate; and equal modco interest on both sides.

**Byte-identical guarantee.** The default (no-portfolio) path is unchanged
arithmetic; goldens are byte-identical. The asset path only activates when a
caller explicitly passes an `AssetPortfolio` — no CLI/API/dashboard surface
threads one through yet (that is Slice 4), so no golden run supplies one.

**Out of scope (this slice).** The `analytics/alm.py` duration-gap analysis and
the CLI/API/dashboard/Excel + notebook surfacing of an asset portfolio (Slice 4,
the only slice that may move goldens, and only when a portfolio is supplied).
The net-of-spread and time-varying amortising earned-rate refinements remain
NICE-TO-HAVE follow-ups (ADR-109; already harvested to PRODUCT_DIRECTION).

## ADR-111: Duration-gap analytics module (Epic 4 / Asset-ALM, Slice 4a)

**Date:** 2026-06-27
**Status:** Accepted

**Context.** Slices 1-3 (ADR-108/109/110) built the asset side and drove the
Modco treaty's modco interest from the asset book yield. The final planned slice
(`docs/PLAN_asset_alm.md` Slice 4) is "ALM analytics + surfacing": an
`analytics/alm.py` duration-gap analysis on the net reinsurer position, plus
CLI / API / dashboard / Excel + validation-notebook surfacing. That is the only
slice permitted to move goldens, and it spans a new analytics module *and* five
presentation surfaces — too much for one session. Following the "new module,
then integration" decomposition pattern (CLAUDE-routine step 7, Pattern B), this
sub-slice (**4a**) ships only the analytics core: the new module with closed-form
unit tests, wired into nothing in the pricing path, so goldens stay
byte-identical. The surfacing is sub-slice 4b.

**Decision.** Add `analytics/alm.py` with three primitives and two result
models:

- `duration_measures(cash_flows, annual_yield) -> DurationMeasures` — the
  reusable core. Present value, Macaulay duration (PV-weighted average time, in
  **years**), and modified duration (`Macaulay / (1 + y)`) of an arbitrary
  cash-flow vector, on the engine's effective-annual monthly discounting
  (`v = (1 + y) ** (-1/12)`, time in years `τ = t/12`). This is the same closed
  form the `AssetPortfolio` duration methods use, generalised to any stream —
  fed the portfolio's aggregate cash flows it reproduces them exactly (locked by
  a test). Raises `PolarisComputationError` on non-positive PV (duration is
  undefined for a stream that discounts to a net inflow).
- `liability_cash_flows(result) -> np.ndarray` — extracts the net benefit-outgo
  stream `death_claims + lapse_surrenders + expenses - gross_premiums` from a
  `CashFlowResult`. This is the obligation the backing assets must fund; its
  modified duration is the liability duration the assets should match. Reserve
  *movements* are excluded (an accounting transfer, not a cash obligation).
- `duration_gap(portfolio, liability_cash_flow_vector, valuation_yield) ->
  DurationGapResult` — the headline. Measures both sides at a single common
  `valuation_yield`, reports each side's market value / PV and Macaulay /
  modified duration, the **duration gap** (asset minus liability modified
  duration, years), and the **dollar-duration gap** (`modified · value`
  differenced — the net change in surplus per unit change in yield).

**Key decisions.**

- *Single common valuation yield, not each side at its own yield.* The asset
  side has a natural book yield and the liability a natural valuation rate, but
  discounting both at one flat yield isolates the *timing* mismatch (the gap)
  from any yield difference. This matches the epic's flat-yield scope (PLAN §5).
  A caller wanting the asset's own book yield simply passes
  `portfolio.book_yield()` as `valuation_yield`.
- *Asset measures come from the portfolio's own (tested) API*, not a re-derived
  formula in `alm.py` — the liability side uses the generic `duration_measures`,
  and a consistency test asserts the two agree on the same vector, so there is
  one closed form, not two that can drift.
- *Modified duration (not Macaulay) anchors the gap*, because the hedgeable
  quantity is the first-order price sensitivity; Macaulay is reported alongside
  for interpretation.

**Verification.** 21 closed-form tests in `tests/test_analytics/test_alm.py`: a
bullet cash flow at month N has Macaulay `= N/12` years and modified
`= (N/12)/(1+y)` (parametrised over horizon and yield); modified `= Macaulay /
(1+y)`; `duration_measures` reproduces the `AssetPortfolio` duration API exactly;
the liability extraction has the documented sign (early net inflow negative, late
outgo positive) and a benefit-heavy block discounts to a positive PV; the gap
differences the two modified durations and the dollar durations; a perfectly
matched block (assets == liability) has both gaps zero; the gap's sign flips when
the liability outlasts the assets; a non-positive PV raises
`PolarisComputationError` and a malformed (empty / non-1-D) input vector raises
`PolarisValidationError` (input-validation vs numerical failure, per CLAUDE.md §5).

**Byte-identical guarantee.** `analytics/alm.py` is imported by nothing in the
pricing path — no CLI / API / dashboard / Excel surface threads a portfolio or
calls `duration_gap` yet — so all golden baselines are byte-identical (QA golden
suite green, no rebaseline).

**Out of scope (this sub-slice).** The CLI / API / dashboard / Excel surfacing of
the duration gap and the ALM validation notebook are sub-slice 4b — the slice
that may move goldens, and only when an asset portfolio is supplied. The
canonical mapping from a full priced deal to "the" liability cash-flow stream
(net vs reinsurer-side, and which reserve basis) is settled there with the
surface; `liability_cash_flows` provides the documented default
(net benefit outgo) the surface will consume. Stochastic reinvestment and a
net-of-spread / amortising earned rate remain NICE-TO-HAVE follow-ups (ADR-109).

---

## ADR-112: CLI asset-portfolio input and duration-gap output (Epic 4 / Asset-ALM, Slice 4b-1)

**Date:** 2026-06-27
**Status:** Accepted

**Context.** ADR-111 (Slice 4a) shipped `analytics/alm.py` — `duration_gap`,
`liability_cash_flows`, `duration_measures` — wired into nothing. The planned
Slice 4b is "surface the duration gap on CLI / API / dashboard / Excel + a
validation notebook". That is five surfaces plus a notebook, each needing an
asset-portfolio input threaded through its config/request — too much for one
session. Mirroring how Epic 3's Slice 4c split into 4c-1 / 4c-2a / 4c-2b / 4c-2c,
Slice 4b is re-decomposed into surface-sized sub-slices, and this one (**4b-1**)
ships the **CLI machine surface** first: the config schema that says how an asset
portfolio is specified, and the duration-gap block in the JSON / console output.
The config-schema decision is load-bearing — the API (4b-2) and dashboard (4b-3)
mirror it — so settling it on the CLI first is the "config model first, then
consumers" decomposition (CLAUDE-routine Pattern A).

**Decision.**

- *Config input.* The deal config gains an optional `deal.asset_portfolio` block
  (the existing `AssetPortfolio` JSON shape `{"bonds": [...]}`, validated by the
  Pydantic model so a malformed bond raises before pricing) and an optional
  `deal.alm_valuation_yield`. Both land on `DealConfig` (`core/pipeline.py`) as
  `asset_portfolio: AssetPortfolio | None = None` and
  `alm_valuation_yield: float | None = None`. Defaults of `None` leave every
  existing config and priced number byte-identical.
- *Common valuation yield defaults to the deal discount rate.* When
  `alm_valuation_yield` is omitted, both sides are discounted at the deal
  `discount_rate` — a single rate isolates the asset-vs-liability *timing*
  mismatch (the gap) from any yield difference, consistent with ADR-111's
  single-common-yield decision and the epic's flat-yield scope. An explicit
  `alm_valuation_yield` overrides it.
- *Liability stream = the cohort's net benefit outgo.* The duration gap is
  measured against `liability_cash_flows(net)` — the net (post-treaty) cohort
  result — which is ADR-111's documented default. (Reinsurer-side / reserve-basis
  variants are deferred — see Out of scope.)
- *Purely additive, never aborts pricing.* The duration gap is computed only when
  an asset portfolio is supplied, and emitted as a new per-cohort
  `alm_duration_gap` key (mirrored at the top level for a single-cohort run, like
  `cedant` / `reinsurer`). Critically, a cohort whose net benefit-outgo discounts
  to a **non-positive** present value at the valuation yield (e.g. a premium-paying
  block still building reserves, where premiums dominate benefits in PV — the
  golden WHOLE_LIFE cohort does this even at 6%) has an *undefined* liability
  duration; `duration_measures` raises `PolarisComputationError`, which is caught
  per cohort, the block is skipped with a console warning, and pricing continues.
  A reporting add-on must never break a price run.

**Verification.** 12 tests in `tests/test_cli_alm.py`: the config round-trips the
portfolio + yield onto `DealConfig`; a malformed bond raises at parse; the TERM
cohort carries a block whose asset measures are the exact closed forms for a
10-year zero (Macaulay 10 yrs, modified `10/(1+y)`, market value `1e6·(1+y)^-10`);
the default valuation yield equals the deal discount rate; an explicit override is
honoured; the gap and dollar-duration-gap identities hold; supplying a portfolio
leaves the cedant / reinsurer / summary blocks byte-identical (the additive
guarantee); the WHOLE_LIFE cohort is skipped (non-positive liability PV) without
failing the run; and a single-cohort run mirrors the block at the top level.

**Out of scope (this sub-slice).** The API (4b-2), dashboard + Excel (4b-3), and
ALM validation notebook (4b-4) surfaces. The **canonical liability stream** is
the open question this slice surfaces concretely: the net benefit-outgo
convention has a non-positive PV for premium-paying / reserve-building blocks
(the golden WHOLE_LIFE cohort), so its duration gap is undefined and skipped. A
reserve-runoff or reinsurer-side liability stream would likely be defined there;
resolving the canonical mapping (with maintainer input) is carried into 4b-2/4b-3.
The result-level reinsurer-side duration gap is also deferred with that decision.

**Resolution of the canonical liability stream (maintainer, 2026-06-27).** The
open question above was settled and is implemented in Slice 4b-2 (the 4b-1
behaviour here is the placeholder it supersedes): (1) compute the gap on **both**
the ceded (reinsurer-view, **headline**) and cedant-retained sides; (2) **Option
B** — the liability is benefits + expenses − **net / valuation** premiums (not
gross), so PV ties to the **reserve**; (3) derive it on the deal's **`reserve_basis`**
(NET_PREMIUM / CRVM / VM20 / GAAP — assets back the held reserve); (4) keep the
single common valuation yield defaulting to `discount_rate`. This redefines
`liability_cash_flows` (an `analytics/alm.py` contract change) and rewires the
4b-1 CLI call site onto it; full rationale and the 4b-2 implementation plan live
in `docs/CONTINUATION_asset_alm.md` ("Canonical liability cash-flow stream —
RESOLVED") and `docs/PLAN_asset_alm.md` §5.

## ADR-113: Reserve-backed liability stream for the duration gap (Epic 4 / Asset-ALM, Slice 4b-2a)

**Date:** 2026-06-27
**Status:** Accepted

**Context.** ADR-112 (Slice 4b-1) measured the duration gap against
`liability_cash_flows(net)` — the net gross-premium benefit outgo
(`death_claims + lapse_surrenders + expenses − gross_premiums`). That stream
subtracts *gross* (loaded) premiums, which is a pricing/profit stream, not a
valuation liability: for a premium-paying / reserve-building block (the golden
WHOLE_LIFE cohort, even at 6%) it discounts to a **non-positive** present value,
so the liability duration is undefined and the block is skipped. The duration
gap therefore only produced output for run-off-shaped blocks (TERM). The
maintainer resolved the canonical-stream question on 2026-06-27 (recorded in
ADR-112's resolution footer and `docs/CONTINUATION_asset_alm.md`): the liability
must be **reserve-backed** (Option B) so its present value ties to the held
reserve. This sub-slice (**4b-2a**) implements the reserve-backed stream in
`analytics/alm.py` and rewires the 4b-1 CLI call site onto it; the REST API
surface and the explicit dual ceded/cedant headline are 4b-2b.

**Decision.**

- *Reserve run-off (release) stream.* New `reserve_liability_cash_flows(result,
  reserve_valuation_rate)` derives the liability directly from the held reserve
  series `reserve_balance` (the standard IFRS-17 / embedded-value "expected
  liability cash flow"). With `R_t = reserve_balance[t]` (the in-force-weighted
  reserve at the start of month `t`, `R_0` the opening reserve) and
  `a = (1 + reserve_valuation_rate)^(1/12)`:

      L_t = R_t * a − R_{t+1}   (months 1 .. T−1);   L_{T−1} = R_{T−1} * a

  This is the expected benefits-and-expenses-less-valuation-premiums cash flow on
  the valuation basis. Discounted at the reserve valuation rate it **telescopes
  exactly to `R_0`** — the present value ties to the held reserve by construction.

- *Basis-agnostic.* The telescoping identity is purely algebraic, so it holds for
  any reserve series regardless of how the reserve was computed — NET_PREMIUM,
  CRVM, VM20, GAAP alike. There is no per-basis valuation-premium reconstruction;
  the held `reserve_balance` (already on the deal's `reserve_basis`) is the only
  input. This is why the stream "follows the deal's reserve basis" without
  touching the product engines.

- *The stream uses the reserve's own valuation rate; the duration uses the common
  ALM yield.* `a` is built from `ProjectionConfig.effective_valuation_rate` (the
  rate the reserve was struck at) — the cash-flow stream is intrinsic to the held
  reserve. The subsequent `duration_measures` then discounts that fixed stream at
  the common ALM `valuation_yield` (ADR-111 / ADR-112 default = deal
  `discount_rate`), so the gap still isolates the asset-vs-liability timing
  mismatch. When the two rates coincide (the golden config sets no separate
  valuation rate), liability PV equals the opening reserve exactly.

- *CLI rewire.* `_price_single_cohort` now measures the gap against
  `reserve_liability_cash_flows(net, effective_valuation_rate)`. For the golden
  YRT path `net` carries the full reserve (YRT cedes none), so this is the
  retained reserve the assets back. Both golden cohorts (TERM and WHOLE_LIFE)
  carry a positive reserve, so **both now carry a duration-gap block** — the
  WHOLE_LIFE skip ADR-112 documented is resolved.

- *Graceful skip is now a true edge case.* Because liability PV equals the opening
  reserve, the skip fires only on a non-positive opening reserve (a brand-new
  block whose net-premium `0V` is zero, or a side carrying no reserve such as the
  YRT-ceded result). `PolarisComputationError` is still caught per cohort so a
  price run never aborts.

- *`liability_cash_flows` retained.* The gross-premium benefit-outgo function is
  kept (still exported) as a benefit-outgo view and for run-off analysis; it is
  superseded only as the *duration-gap* liability.

**Verification.** `tests/test_analytics/test_alm.py`: the run-off PV telescopes to
`reserve_balance[0]` at the reserve rate (parametrized over rates; purely
algebraic); a building reserve gives an early net inflow (negative) and a final
positive run-off; a single-period series runs off fully; an empty
`reserve_balance` raises `PolarisValidationError`; a non-positive opening reserve
raises `PolarisComputationError` through `duration_gap` (the skip trigger); and an
**end-to-end** TermLife projection on NET_PREMIUM / CRVM / VM20 (reserve rate
3.5% ≠ discount 5%) confirms `PV(run-off) == reserve_balance[0]` on each basis.
`tests/test_cli_alm.py`: the WHOLE_LIFE cohort now carries a block with positive
liability PV; both golden cohorts are priced; the additive guarantee and
single-cohort top-level mirror still hold.

**Out of scope (this sub-slice).** The REST `/api/v1/price` surface mirroring the
gap, and the **explicit dual ceded (reinsurer-view, headline) + cedant-retained**
duration gap, are 4b-2b: this slice keeps the existing single CLI block (measured
on the retained `net` reserve, correct for the golden YRT path) and lands the
load-bearing analytics-contract change. The dashboard + Excel surfaces (4b-3) and
the ALM validation notebook (4b-4) remain planned. GAAP reserves are recognised by
the enum but not implemented by any product engine, so the stream is exercised on
NET_PREMIUM / CRVM / VM20 only (the bases TermLife actually computes).

## ADR-114: Dual reinsurer/cedant duration gap + REST API surface (Epic 4 / Asset-ALM, Slice 4b-2b)

**Date:** 2026-06-28
**Status:** Accepted

**Context.** ADR-113 (Slice 4b-2a) landed the reserve-backed liability stream and
measured the duration gap on a **single** side — the cedant-retained (`net`)
reserve — which is correct for the golden YRT path (YRT cedes no reserve, so `net`
carries the full reserve) but is only half the picture. Polaris RE is a
*reinsurer* tool: the reinsurer's assets back the **ceded** reserves, so the
headline gap is the asset portfolio against the ceded liability. The maintainer
settled the canonical convention (2026-06-27, recorded in
`docs/CONTINUATION_asset_alm.md`): compute the gap on **both** the ceded
(reinsurer-view, headline) and cedant-retained sides, reinsurer-view as the
headline. This sub-slice (**4b-2b**) implements the dual gap and mirrors it on the
REST `/api/v1/price` surface (the API parity slice).

**Decision.**

- *`DualDurationGap` model + `dual_duration_gap` helper (`analytics/alm.py`).* A
  new frozen `PolarisBaseModel` carries a `reinsurer` and a `cedant`
  `DurationGapResult | None`. `dual_duration_gap(portfolio, net_result,
  ceded_result, valuation_yield, reserve_valuation_rate)` builds the
  reserve-backed run-off (ADR-113) from each side's `reserve_balance` and measures
  the same portfolio against each. The **same asset portfolio** backs both sides —
  the asset measures are identical; only the liability (and therefore the gap)
  differs. This answers "what is the duration gap if these assets backed the ceded
  vs. the retained reserve."

- *Reinsurer-view is the headline.* `DualDurationGap.headline` returns the
  reinsurer side when defined, else the cedant side. For a **YRT** treaty the ceded
  reserve telescopes to ~0, so the reinsurer-side liability has a non-positive PV
  and that side is `None`; the cedant side is then the only defined gap and stands
  in as the headline. A proportional treaty (coinsurance / modco) carries a
  meaningful ceded reserve, so both sides are defined.

- *Per-side graceful skip, never aborts.* Each side is computed independently;
  `_duration_gap_or_none` catches the `PolarisComputationError` a non-positive
  reserve raises and returns `None` for that side. The reinsurer side is also
  `None` for a gross / no-treaty run (`ceded_result is None`). `is_empty` (both
  sides `None`) lets the surfaces omit the block entirely rather than emit an empty
  shell — the additive reporting block still never aborts a price run.

- *CLI emits the dual block.* `CohortResult.alm_duration_gap` is now a
  `DualDurationGap`; `_price_single_cohort` calls `dual_duration_gap`. The Rich
  renderer prints the reinsurer (ceded) table first as the headline, then the
  cedant (retained) table, skipping a `None` side. The 4b-1/4b-2a single-block
  JSON shape (`alm_duration_gap` = a flat `DurationGapResult`) becomes
  `alm_duration_gap` = `{reinsurer, cedant}`. This is permitted because
  `alm_duration_gap` is a *new, non-golden* output that only appears when an asset
  portfolio is supplied — no golden baseline carries it, so the goldens stay
  byte-identical and the existing CLI ALM tests are updated to the dual shape.

- *REST API surface.* `PriceRequest` gains `asset_portfolio: AssetPortfolio | None`
  (the same JSON shape the CLI config accepts — a non-empty `bonds` list) and
  `alm_valuation_yield: float | None`. `PriceResponse` gains `alm_duration_gap:
  DualDurationGap | None`, populated only when a portfolio is supplied (else
  `null`). The endpoint reuses the **same** `dual_duration_gap` compute path and
  the `effective_valuation_rate` / `discount_rate` defaults as the CLI, so the two
  surfaces stay in parity. A malformed bond (e.g. a coupon frequency not dividing
  12) is rejected by the endpoint's catch-all as HTTP 422.

**Verification.** `tests/test_analytics/test_alm.py`: both sides defined when both
reserves are positive (asset measures identical across sides; each side reproduces
the single-side `duration_gap`; liability PV ties to each opening reserve at the
reserve rate); a YRT-like zero ceded reserve gives `reinsurer is None` with the
cedant defined; a `ceded_result=None` gross run has no reinsurer side; both
reserves non-positive gives `is_empty`; `headline` prefers the reinsurer side.
`tests/test_cli_alm.py`: the golden YRT run emits `{reinsurer: null, cedant: {...}}`
with closed-form asset measures on the cedant side, a Coinsurance run defines both
sides (identical asset MV, ceded liability PV > retained), and the additive
guarantee + single-cohort top-level mirror still hold.
`tests/test_api/test_main.py::TestPriceAlmDurationGap`: the block is `null` without
a portfolio, both sides on Coinsurance, reinsurer-`null` on YRT, closed-form asset
duration, `alm_valuation_yield` override, priced numbers unchanged by the asset
side, and HTTP 422 on a malformed bond.

**Out of scope (this sub-slice).** The dashboard asset-portfolio input widget +
duration-gap display and the Excel ALM block are 4b-3 (which also threads the two
new `DealConfig` fields through `DealConfig.to_dict()` — PR-#111 review carry-
forward); the ALM validation notebook is 4b-4. Both sides are still measured at one
common flat yield (ADR-111); a per-side valuation yield (e.g. the asset book yield
on the reinsurer side, the deal discount rate on the cedant side) is a possible
future refinement, not this slice. The single supplied portfolio is measured
against both liabilities; modelling distinct cedant-retained vs. reinsurer-held
asset portfolios is out of scope.

## ADR-115: ALM duration-gap sheet on the deal-pricing Excel workbook (Epic 4 / Asset-ALM, Slice 4b-3, Excel surface)

**Date:** 2026-06-28
**Status:** Accepted

**Context.** ADR-114 (Slice 4b-2b) made `alm_duration_gap` a dual
`DualDurationGap` (reinsurer-view / cedant-view) and surfaced it on the CLI JSON
and the REST `/api/v1/price` response, but the deal-pricing **committee workbook**
(`write_deal_pricing_excel`) still omitted it: a reviewer pricing a deal with an
asset portfolio saw the duration gap on the console and the API but not in the
Excel packet they circulate. Slice 4b-3 ("dashboard + Excel presentation
surfaces") is two distinct surfaces; consistent with how Slice 4b kept splitting
into surface-sized sub-slices (4b-1 CLI, 4b-2a/2b liability+API), this sub-slice
ships the **Excel** surface (a machine-style, self-contained, fully testable
deliverable) first; the interactive Streamlit dashboard widget — which also
carries the PR-#111 `DealConfig.to_dict()` carry-forward — is deferred to 4b-3b.

**Decision.**

- *Reuse `DualDurationGap`, no new DTO.* `DealPricingExport` gains an optional
  `alm_duration_gap: DualDurationGap | None = None` field. The CLI already computes
  the dual gap per cohort (`CohortResult.alm_duration_gap`); the
  `_cohort_to_deal_pricing_export` translation site threads it onto the export. No
  recompute and no new export DTO — the writer only renders.

- *"ALM Duration Gap" sheet, appended last.* `_write_alm_duration_gap_sheet`
  stacks the **reinsurer-view** (ceded reserve — headline) block first, then the
  **cedant-view** (retained reserve) block, mirroring the CLI Rich
  `_render_alm_duration_gap` order. Each block (`_write_alm_gap_block`) renders the
  four asset-vs-liability rows (value / Macaulay / modified / dollar duration) as an
  (Asset, Liability) column pair, then a net section (valuation yield, duration gap,
  dollar-duration gap) in the Asset column — the same layout and labels as the
  console table, so the workbook and the console show identical numbers.

- *Additive, byte-identical default.* The sheet is written only when
  `alm_duration_gap is not None and not …is_empty`, so every workbook priced without
  an asset portfolio (the overwhelming common path) is byte-identical to pre-ADR-115
  output. A side that is `None` (e.g. the YRT ceded reserve telescopes to ~0, so the
  reinsurer side is undefined) is omitted, exactly as the console does; when both
  sides are `None` the sheet is suppressed entirely rather than written empty.

**Verification.** `tests/test_utils/test_excel_output.py::TestAlmDurationGapSheet`:
the sheet is absent with no gap and with an empty dual gap, present when supplied,
omits the reinsurer block when only the cedant side is defined (the YRT path),
renders the reinsurer block first when both sides are defined, matches every
Asset/Liability and net-gap cell to the `DurationGapResult` fields, is appended
last without disturbing the existing sheet order, and round-trips through openpyxl.
`tests/test_cli_alm.py::TestExcelAlmSheet`: end-to-end `polaris price --excel-out`
emits the "ALM Duration Gap" sheet on every per-product workbook when an asset
portfolio is supplied, omits it when none is, and renders the cedant side (no
reinsurer block) for the golden YRT block.

**Out of scope (this sub-slice).** The Streamlit **dashboard** asset-portfolio
input widget + duration-gap display — and the PR-#111 carry-forward that threads
the two new `DealConfig` fields (`asset_portfolio`, `alm_valuation_yield`) through
`DealConfig.to_dict()` — are Slice 4b-3b. The ALM validation notebook is 4b-4. The
sheet renders the gap the CLI/API already compute; it does not change the analytics
(still one common flat valuation yield, ADR-111). A per-side number-format /
conditional-fill polish (e.g. red-flagging a large negative gap) is not attempted.


## ADR-116: Dashboard asset-portfolio input and duration-gap display (Epic 4 / Asset-ALM, Slice 4b-3b)

**Date:** 2026-06-29
**Status:** Accepted

**Context.** ADR-114 (Slice 4b-2b) surfaced the dual `DualDurationGap`
(reinsurer-view / cedant-view) on the CLI and the REST `/api/v1/price` response,
and ADR-115 (Slice 4b-3a) added the "ALM Duration Gap" sheet to the deal-pricing
Excel workbook. The interactive Streamlit **Deal Pricing** page was the last of
the four pricing surfaces still blind to the asset side: it had no way to supply an
`AssetPortfolio` and showed no duration gap. This sub-slice closes the surfacing
tail's interactive surface and discharges the PR-#111 review P2 carry-forward (the
two `DealConfig` ALM fields threaded through `DealConfig.to_dict()`).

**Decision.**

- *Asset side as an optional per-run input, parsed from JSON.* The Deal Pricing
  page gains an "Asset-Liability Duration Gap (optional asset side)" expander with
  an `AssetPortfolio` JSON text area (the same `{"bonds": [...]}` shape the CLI
  `deal.asset_portfolio` config accepts) and an "ALM valuation yield (%)" number
  input (0 → defer to the deal `discount_rate`, mirroring the CLI default). The
  payload is `AssetPortfolio.model_validate_json`-parsed; an invalid payload shows
  an error and is treated as "no asset side" — the block is simply not rendered and
  pricing never aborts. An empty input leaves every run byte-identical.

- *Reuse the analytics compute path, no recompute.* `_run_pricing_for_cohort`
  gains optional `asset_portfolio` / `alm_valuation_yield` parameters and, when a
  portfolio is supplied, calls `dual_duration_gap(asset_portfolio, net, ceded,
  gap_yield, config.effective_valuation_rate)` — the identical reserve-backed
  Option-B path the CLI/API use (ADR-113/114). The result is stored on a new
  `CohortPricingData.alm_duration_gap` field and rendered (reinsurer-view headline
  first, then cedant-view; a `None` side omitted) by `_render_alm_duration_gap`,
  mirroring the CLI Rich block's layout and labels. A test asserts the dashboard
  gap is byte-identical to a direct `dual_duration_gap` call on the cohort's own
  net/ceded results, locking the "wire, don't reimplement" contract.

- *PR-#111 carry-forward — `to_dict()` now carries the ALM fields.* With the
  dashboard consuming them, `DealConfig.to_dict()` adds `asset_portfolio` and
  `alm_valuation_yield` (default `None`), so the dashboard `DEFAULTS` / CLI↔Streamlit
  parity surface carries them. 4b-1 deliberately left them out until a dashboard
  surface used them (the `yrt_rate_table_*` precedent); that condition now holds.
  The parsed widget values are also written back onto the deal-config dict.

**Verification.** `tests/test_dashboard/test_pricing_alm.py`: a supplied portfolio
populates a non-empty `DualDurationGap` byte-identical to a direct
`dual_duration_gap` call; omitting it leaves the field `None`; the YRT path carries
the cedant side only (ceded reserve ~0 → reinsurer `None`) while a proportional
coinsurance treaty carries both; an explicit `alm_valuation_yield` overrides the
deal discount rate; and `DealConfig.to_dict()` now surfaces both ALM fields.

**Out of scope.** The ALM **validation notebook** is Slice 4b-4. The dashboard
input is per-run (it is not persisted to an uploaded-file widget like the YRT rate
table); a saved-portfolio / file-upload affordance is a possible follow-up. The
analytics are unchanged (one common flat valuation yield, ADR-111); a per-side
yield and a conditional highlight flagging a large negative gap remain
NICE-TO-HAVE polish, already harvested.

---

## ADR-117: ALM duration-gap validation notebook (Epic 4 / Asset-ALM, Slice 4b-4 — epic close)

**Date:** 2026-06-29
**Status:** Accepted

**Context.** Slices 4b-1 … 4b-3b surfaced the dual asset-liability duration gap
(`analytics.alm.dual_duration_gap`) on the CLI (ADR-112/113/114), the REST
`/api/v1/price` response (ADR-114), the deal-pricing Excel workbook (ADR-115), and
the Streamlit dashboard (ADR-116). The final planned slice of the Asset/ALM epic
(`docs/PLAN_asset_alm.md`, Milestone 5.4) is the end-to-end **validation notebook**
— the auditable worked example behind those surfaces, matching the per-epic
notebook precedent (`01_term_life_yrt_pricing`, `02_reserve_basis_comparison`,
`03_capital_standards_comparison`). This slice closes the epic.

**Decision.**

- *`notebooks/04_alm_duration_gap.ipynb` — one end-to-end run plus four closed-form
  reconciliations.* The notebook builds a seasoned whole-life block, cedes 50% on
  coinsurance (so the reinsurer inherits a real ceded reserve and **both**
  `DualDurationGap` sides are defined — more illustrative than the golden YRT path,
  whose reinsurer side is `None`), sizes a backing bond portfolio to the ceded
  reserve, and reports the dual gap via the **same** `dual_duration_gap` path the
  four surfaces use (the notebook reads the analytics, it does not reimplement
  them). It then reconciles the engine against four closed forms: (1) the
  reserve-backed run-off telescopes to the opening reserve at the reserve valuation
  rate (ADR-113); (2) a zero-coupon bond's Macaulay duration is its term in years,
  modified is `N/(1+y)`, convexity is `N(N+1)/(1+y)²`; (3) `duration_measures` on
  the portfolio's own cash flows reproduces the portfolio's duration API exactly
  (the gap wires one primitive, not two); (4) a block whose liability equals the
  assets' own cash flows has an exactly-zero gap. A closing section demonstrates
  immunisation — lengthening the assets shrinks the reinsurer-side gap by ~10×.

- *Self-contained synthetic Gompertz mortality, no data-file dependency.* Flat
  mortality builds essentially no whole-life reserve (a level net premium funds a
  constant hazard each period), so the notebook uses a synthetic increasing curve
  `q_x = 0.0004·1.09^(x-18)` rather than a converted SOA/CIA table. This keeps the
  notebook runnable wherever the package imports (the same self-contained pattern as
  notebooks 01–03) and insulates it from the standing SOA-conversion failure.

- *The notebook IS its own test — executed by a pytest guard.* `nbclient`/
  `nbconvert` are not project dependencies, so rather than spin up a Jupyter kernel,
  `tests/test_notebooks/test_alm_duration_gap_notebook.py` reads the `.ipynb` with
  `nbformat` and `exec`s its code cells in one shared namespace (the notebook is
  magic-free, so this reproduces a top-to-bottom kernel run). The closed-form
  reconciliations are embedded in the cells as `np.testing.assert_allclose` /
  `assert`, so executing the notebook end to end IS the verification — any drift in
  the duration/run-off math fails CI, not just the notebook.

**Verification.** `tests/test_notebooks/test_alm_duration_gap_notebook.py` (3
tests): the notebook file exists, has the expected code cells, and executes top to
bottom with every embedded reconciliation passing; a defensive spot-check confirms
the coinsurance run binds a `DualDurationGap` with both reinsurer and cedant sides
defined. Purely additive — no `src/` change, goldens byte-identical (`polaris
price` on the golden block is unchanged: Total PV Profits Reinsurer $45,386).

**Out of scope.** This slice closes the Asset/ALM epic; the remaining asset-side
ambitions are already harvested follow-ups and are *not* implemented here: a
net-of-spread / time-varying amortising book yield, stochastic reinvestment
(Hull-White / CIR via `analytics/stochastic.py`, ROADMAP 5.4), distinct
cedant-held vs reinsurer-held asset portfolios, a per-side valuation yield, and a
modco-interest driven directly from the asset book yield in a worked notebook
example. A generic "execute every notebook" CI sweep (this guard covers only
notebook 04) is a possible future consolidation.

## ADR-118: ExpenseAllowance model + computation primitive (Tier-B B3 / Expense-allowance epic, Slice 1)

**Date:** 2026-06-29
**Status:** Accepted

**Context.** The four recommended epics from
`docs/COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md` — A1 reserve-basis, A2 IFRS 17
movement, A3 cross-jurisdiction capital, and the post-ladder C0 Asset/ALM — are all
COMPLETE. Per the daily-dev ACTIVE-EPIC track the routine must always advance one
epic; with the Tier-A ladder exhausted, the highest value × effort epic-sized item
remaining is Tier-B **B3 — sliding-scale expense allowances / experience refunds**
(★★★★☆, ~3 dev-days, "standard in large YRT deals"). Today the engine has no
explicit expense-allowance mechanism at all: `CoinsuranceTreaty` carries only a
boolean `include_expense_allowance` that, when true, shares the cedant's expenses
proportionally (`ceded_expense_t = gross_expense_t × c`); YRT and Modco model no
allowance. A real proportional treaty pays the cedant an allowance quoted as a
percentage of **ceded premium**, with a high first-year rate and a lower renewal
rate, frequently on a **sliding scale** keyed to loss experience. This slice (the
data-model-first slice of a 3-slice epic, `docs/PLAN_expense_allowance.md`) adds the
contract and computation primitive without wiring it into any treaty, so all goldens
stay byte-identical.

**Decision.**

- *`reinsurance/expense_allowance.py` — `ExpenseAllowance` + `ExpenseAllowanceBand`
  Pydantic models and a pure `compute_allowance()` primitive.* The allowance is a
  fraction of ceded premium: `first_year_pct` on the first `months_per_year` periods
  (duration year 1), the renewal rate thereafter. With no sliding scale the renewal
  rate is the flat `renewal_pct`; with a sliding scale the renewal rate is selected
  from loss-ratio bands by the realized loss ratio
  (`ceded_claims.sum() / ceded_premiums.sum()`), where the first band whose
  `max_loss_ratio` the loss ratio does not exceed wins (a loss ratio above every band
  falls to the last/lowest band).

- *The sliding scale is validated monotone non-increasing in loss ratio.* A band set
  must be ascending and distinct in threshold, and its `allowance_pct` must not rise
  as the loss ratio rises — better experience must pay at least as much as worse
  experience. A mis-ordered scale raises `PolarisValidationError` rather than
  silently inverting the incentive the sliding scale exists to create.

- *Not wired into any treaty in this slice.* The primitive is standalone; Slice 2
  consumes it inside `CoinsuranceTreaty`/`YRTTreaty` as a reinsurer→cedant transfer
  (`+allowance` on the ceded expense line, `−allowance` on the net expense line) that
  preserves the `net + ceded == gross` additivity invariant. Keeping the wiring out
  of this slice means goldens are byte-identical here.

**Verification.** `tests/test_reinsurance/test_expense_allowance.py` (26 tests):
closed-form first-year/renewal amounts ($1,000/mo premium at 100% FY + 10% renewal →
$12,000 yr 1, $1,200/yr after); linearity in premium; first-year boundary across
`months_per_year` values; sliding-scale rate selection at every band boundary; the
realized-loss-ratio closed form (60k/100k → 10% band → $500 renewal); better
experience pays strictly more; and the ascending / distinct / monotone-non-increasing
validators. `polaris price` on the golden block is unchanged (Total PV Profits
Reinsurer $45,386, Cedant $3,513,563); the full reinsurance + QA suites pass.

**Out of scope.** Wiring the allowance into the treaty engines (Slice 2); the
experience-refund (profit-sharing) mechanism and CLI/API/Excel surfacing (Slice 3);
a dedicated allowance cash-flow line on `CashFlowResult` (a contract change — the
allowance is folded into the existing `expenses` line); reinsurance commissions
modelled distinctly from expense allowances; and gross- vs ceded-basis loss-ratio
selection (Slice 2 passes the ceded figures — the reinsurer's own experience drives
its allowance).

---

## ADR-119: Wire ExpenseAllowance into CoinsuranceTreaty + YRTTreaty (Tier-B B3 / Expense-allowance epic, Slice 2)

**Date:** 2026-06-29
**Status:** Accepted

**Context.** ADR-118 (Slice 1) added the `ExpenseAllowance` model and the pure
`compute_allowance()` primitive but wired it into no treaty, so goldens stayed
byte-identical. Slice 2 consumes the primitive inside the two proportional treaty
engines so a real YRT/coinsurance treaty's expense-allowance cash flows can be
reproduced. A reinsurer pays the cedant an allowance — a high first-year rate
reimbursing acquisition cost, a lower renewal rate — quoted as a % of ceded
premium, optionally on a loss-ratio sliding scale.

The Slice-1 primitive defines "first year" as the first `months_per_year`
*projection* periods. That is correct only for new business projected from
inception. The primary use case is an **inforce block** where most policies are
mid-duration: their acquisition cost is sunk and the renewal rate — not the
first-year rate — applies going forward. Feeding a mid-duration renewal stream to
the naive primitive overstates the allowance (verified: a flat $1,000/period
renewal stream at 80% FY / 10% renewal is overstated by $8,400 over the first
policy year). This was flagged as the binding Slice-2 design requirement (PR #117
automated review, P2).

**Decision.**

- *`expense_allowance: ExpenseAllowance | None = None` on both `CoinsuranceTreaty`
  and `YRTTreaty`.* Default `None` reproduces current behaviour exactly → goldens
  byte-identical. When set, the per-period allowance is computed on the treaty's
  own **ceded** premium stream (the reinsurer's premium income) and, for a sliding
  scale, keyed off the treaty's own ceded loss ratio.

- *The allowance is folded into the expense line as a reinsurer→cedant transfer*
  (`+allowance` on ceded `expenses`, `−allowance` on net `expenses`), then both
  NCFs are recomputed. Because the transfer nets to zero across the (net, ceded)
  pair, `net + ceded == gross` holds on premiums, claims, expenses, and NCF — no
  `CashFlowResult` contract change. The shared logic lives in
  `BaseTreaty._expense_allowance_transfer()` so both engines apply it identically.

- *Projection month → policy duration mapping (option (a)).* `ExpenseAllowance`
  gains `first_year_fraction_for_block(inforce, n_periods, valuation_date)`, which
  returns the face-weighted fraction `f[t] ∈ [0,1]` of the block still in policy
  year one at each projection step (`duration_in_force_months + t < months_per_year`).
  `compute_allowance()` gains an optional `first_year_fraction` argument that blends
  `rate[t] = f[t]·first_year_pct + (1−f[t])·renewal_rate`. When a treaty is applied
  with an `InforceBlock`, the treaty computes `f` from the block; new business yields
  `f[t]=1` for the first policy year and `0` after (recovering the default), while a
  mid-duration block yields `f[t]=0` everywhere (renewal rate throughout). Without an
  `InforceBlock` the allowance falls back to the new-business projection-month basis,
  documented on `compute_allowance()`.

- *Independent of the legacy proportional layer.* `CoinsuranceTreaty.include_expense_allowance`
  (the boolean that splits the cedant's own expenses proportionally) and the new
  `expense_allowance` are independent layers that compose; a test asserts the
  sliding-scale delta is identical whether the proportional split is on or off.

**Verification.** `tests/test_reinsurance/test_expense_allowance.py` gains 13
primitive tests (explicit `first_year_fraction` blend; new-business-shaped fraction
recovers the default; shape/range validation; block-fraction mapping for new,
mid-duration, equal-face-mixed, and unequal-face blocks; and the
inforce-overstatement-fix closed form). `tests/test_reinsurance/test_expense_allowance_treaty.py`
(9 tests) covers both engines: default byte-identical; additivity incl. the expense
line; the closed-form transfer and the ±A NCF shift; mid-duration block charged the
renewal rate only; mid-duration < new-business allowance; sliding-scale band
selection through the treaty; and proportional-layer independence. `polaris price`
on the golden block is unchanged (Total PV Profits Reinsurer $45,386). Full fast
suite: 1847 passed.

**Out of scope.** The experience-refund (profit-sharing) mechanism and the
allowance/refund surfacing on `DealConfig` / CLI / API / Excel (Slice 3); a
dedicated allowance line on `CashFlowResult` (a contract change — still folded into
`expenses`); survivorship-weighting the first-year fraction (it is face-weighted,
ignoring decrements between valuation and projection month `t` — exact at the
all-new / all-renewal boundaries, a small blend only across the year-one transition
of a mixed-duration block); and per-policy (seriatim) allowance allocation analogous
to the YRT seriatim premium path (the aggregate face-weighted fraction is used).

---

## ADR-120: ExperienceRefund model + computation primitive (Tier-B B3 / Expense-allowance epic, Slice 3a)

**Date:** 2026-06-30
**Status:** Accepted

**Context.** ADR-118/119 (Slices 1–2) added the `ExpenseAllowance` model and wired
it into `CoinsuranceTreaty`/`YRTTreaty` as a reinsurer→cedant transfer. The B3 epic's
remaining planned scope (`docs/PLAN_expense_allowance.md`, Slice 3) is the
**experience refund** (profit sharing) plus surfacing the allowance + refund on the
deal-pricing path (`DealConfig` / CLI / API / Excel). Surfacing across four consumers
is a session of its own, so Slice 3 is split data-model-first (the Slice-1 precedent):
this slice (**3a**) adds the `ExperienceRefund` contract and computation primitive,
wired into no treaty → goldens byte-identical; Slice **3b** wires it in and surfaces
the terms. A large YRT/coinsurance deal refunds the cedant a share of accumulated
favourable experience when the ceded business runs better than expected — the
standard mechanism (alongside the sliding-scale allowance) for aligning both parties
to good experience. The engine had no experience-refund mechanism at all (verified:
no `ExperienceRefund` / profit-sharing symbol anywhere in `src/`).

**Decision.**

- *`reinsurance/experience_refund.py` — `ExperienceRefund` Pydantic model + pure
  `experience_balance()` / `compute_refund()` primitives.* The experience account
  accumulates a per-period contribution
  `premium − claims − allowance − reinsurer_margin_pct · premium`, where `allowance`
  is the expense allowance already paid to the cedant (optional, default zeros) and
  `reinsurer_margin_pct · premium` is the reinsurer's retained risk/expense charge.
  A positive balance is favourable to the reinsurer; the refund is
  `refund_pct · max(0, balance − retention)` — a share of the favourable balance in
  excess of a retention the reinsurer keeps first.

- *Accumulation basis: optional flat interest, default off.* This resolves the
  PLAN open question ("with vs without interest"). With `interest_rate = 0` (default)
  the balance is the simple undiscounted contribution sum; otherwise each period's
  contribution is accumulated forward to the final/settlement period at the per-period
  factor `(1 + interest_rate)^(1 / months_per_year)` — an experience fund rolled to
  the settlement point. Keeping the default at zero means the simplest deal needs no
  interest assumption and the primitive stays auditable.

- *Refund is non-negative; the cedant never pays into the fund.* An unfavourable
  (negative) or below-retention balance refunds nothing. Deficit carryforward (a
  loss carried into the next experience period) is deliberately out of scope.

- *Not wired into any treaty in this slice.* The primitive is standalone; Slice 3b
  consumes it as a terminal reinsurer→cedant transfer preserving `net + ceded == gross`
  (the refund moves money between the two parties; it is not a new external flow),
  exactly as the allowance does. Keeping the wiring out of this slice means goldens
  are byte-identical here.

**Verification.** `tests/test_reinsurance/test_experience_refund.py` (25 tests):
closed-form balances (12,000 premium − 7,200 claims → 4,800 favourable; allowance +
10% margin net to 4,200; two annual 100 contributions at 10% → 210 with interest);
refund as a share of the favourable balance (0.5·4,800 → 2,400), the retention applied
first (0.5·(4,800 − 1,000) → 1,900), zero below the retention, zero on unfavourable
experience, linearity in `refund_pct`, the interest closed form (→ 105), and a margin
sensitivity sweep; plus shape-mismatch / non-1-D guards and field-range validators.
No treaty consumes the model → `polaris price` on the golden block is unchanged
(Total PV Profits Reinsurer $45,386); full fast suite green.

**Out of scope.** Wiring the refund into the treaty engines and surfacing allowance +
refund on `DealConfig` / CLI / API / Excel (Slice 3b); per-period or annual refund
**settlement timing** (this slice computes a single end-of-horizon scalar — a real
treaty may settle the refund annually); deficit carryforward across experience
periods; and a stochastic / experience-driven re-rating of the refund across
scenarios (the balance keys off the projected base run).

## ADR-121: Wire ExperienceRefund into CoinsuranceTreaty + YRTTreaty (Tier-B B3 / Expense-allowance epic, Slice 3b-1)

**Date:** 2026-06-30
**Status:** Accepted

**Context.** ADR-120 (Slice 3a) added the standalone `ExperienceRefund` model +
`compute_refund()` primitive, consumed by no treaty. The B3 epic's remaining planned
scope (`docs/PLAN_expense_allowance.md`, Slice 3b) is two distinct chunks: (1) wire
the refund into the treaty engines as a terminal transfer, and (2) surface the
allowance + refund terms across the four deal-pricing consumers (`DealConfig` / CLI /
API / Excel). Surveying the surfacing path found that neither the Slice-2
`expense_allowance` nor the Slice-3a refund is yet on the deal path — `pipeline.py`
and `api/main.py` only set the legacy `include_expense_allowance` boolean — so the
surfacing is a session of its own across four consumers. Following the Slice-1/3a
data-model-first precedent, Slice 3b is split: **3b-1 (this slice)** wires the refund
into both treaties (goldens byte-identical, off by default); **3b-2** surfaces both
terms on the deal-pricing path.

**Decision.**

- *`experience_refund: ExperienceRefund | None = None` field on both
  `CoinsuranceTreaty` and `YRTTreaty`.* The field name mirrors the model class
  (`ExperienceRefund`), as `expense_allowance` mirrors `ExpenseAllowance`. (The PLAN
  uses the shorthand `expense_refund` for the eventual deal-path naming; the treaty
  field is named `experience_refund` for semantic accuracy — it is an *experience*
  refund, not an expense refund. 3b-2 maps the deal-path name to this field.) Default
  `None` reproduces current behaviour → goldens byte-identical.

- *The refund is a single terminal reinsurer→cedant transfer at the final projection
  period.* `BaseTreaty._experience_refund_transfer()` computes the scalar
  `compute_refund(ceded_premiums, ceded_claims, allowances)` and returns a zeros array
  with the refund placed at index `-1`. The caller folds it into the expense line
  (`ceded.expenses += R`, `net.expenses -= R`), mirroring `_expense_allowance_transfer`.
  The transfer nets to zero across the `(net, ceded)` pair, so `net + ceded == gross`
  holds and no `CashFlowResult` contract changes. Placing the whole refund at the final
  period (vs spreading it) matches the "single end-of-horizon settlement" basis decided
  in ADR-120; per-period/annual settlement timing remains a future refinement.

- *The refund is computed net of the expense allowance already paid.* When a treaty
  carries both an `expense_allowance` and an `experience_refund`, the allowance array
  the treaty already computed is passed into the refund so the sharable experience
  balance is `premium − claims − allowance − margin·premium` — the allowance is not
  double-counted. The two transfers compose additively on the expense line (the
  allowance per-period + the refund at the terminal period).

**Verification.** `tests/test_reinsurance/test_experience_refund_treaty.py` (13 tests):
default (no refund) byte-identical on both treaties; `net + ceded == gross` plus
explicit expense-line additivity with a refund on both treaties; closed-form refund
landing **solely** on the final period and shifting net/ceded NCF by exactly `R` there;
linearity in `refund_pct` (parametrized); allowance + refund composing additively with
the refund computed net of the allowance (and strictly smaller than the refund without
it); and below-retention / unfavourable experience refunding nothing (byte-identical).
`polaris price` on the golden block is byte-identical (Total PV Profits Reinsurer
$45,386); full fast suite green.

**Out of scope.** Surfacing the allowance + refund terms on `DealConfig` / CLI / API /
Excel (Slice 3b-2 — the next slice); per-period or annual refund **settlement timing**
(still a single end-of-horizon scalar); deficit carryforward across experience periods.

---

## ADR-122: Surface expense-allowance / experience-refund terms on the CLI config deal path (Tier-B B3 / Expense-allowance epic, Slice 3b-2a)

**Date:** 2026-06-30
**Status:** Accepted

**Context.** ADR-119 (Slice 2) and ADR-121 (Slice 3b-1) made `expense_allowance`
and `experience_refund` optional fields on `CoinsuranceTreaty` / `YRTTreaty`, each
applied as a reinsurer→cedant transfer preserving `net + ceded == gross`. But neither
term reached the deal-pricing path: a user supplying `deal.expense_allowance` in a
`polaris price --config` file had it silently dropped — `DealConfig` had no such field
and `_parse_config_to_pipeline_inputs` never read the key, so `build_treaty` constructed
the treaty without it. Slice 3b-2 (surface both terms across `DealConfig` / CLI / API /
Excel) proved larger than one quality session once surveyed: the API alone constructs
treaties at four call sites across four request models, plus the Excel writer. Following
the epic's established "decompose, don't defer" pattern, Slice 3b-2 is split:
**3b-2a (this slice)** surfaces both terms on the CLI config / pipeline deal path so the
feature is usable end-to-end via `polaris price --config`; **3b-2b** surfaces them on the
API request models and the deal-pricing Excel export.

**Decision.**

- *Two optional fields on `DealConfig`:* `expense_allowance: ExpenseAllowance | None`
  and `experience_refund: ExperienceRefund | None`, both default `None`. Default `None`
  → `build_treaty` constructs the treaty exactly as before, so every existing config and
  priced number is byte-identical. The annotations are imported under `TYPE_CHECKING`
  so this `core/` module keeps the reinsurance package out of its runtime import graph —
  the same layering intent as `build_treaty`'s lazy treaty imports (core/ orchestrates
  the reinsurance layer without importing it at module load).

- *`build_treaty` gains `expense_allowance` / `experience_refund` kwargs* threaded onto
  the constructed `YRTTreaty` / `CoinsuranceTreaty` (the only treaties that carry the
  fields). They are silently ignored for `Modco` / gross, which have no such field — a
  config that sets them on a Modco deal is a no-op, not an error, mirroring how
  `yrt_rate_per_1000` is ignored off the YRT path.

- *`_parse_config_to_pipeline_inputs` parses the `deal.expense_allowance` /
  `deal.experience_refund` JSON blocks* via `ExpenseAllowance.model_validate` /
  `ExperienceRefund.model_validate` (new nested schema only — the legacy flat schema is
  deprecated and unchanged). The models' own validators (`extra="forbid"`, the
  monotone-non-increasing sliding-scale check) raise `PolarisValidationError` on a
  malformed block *before* pricing, so a mis-ordered scale fails loudly at parse time.
  `_build_treaty_for_pipeline` then threads `deal.expense_allowance` /
  `deal.experience_refund` into `build_treaty` (both the flat-rate and tabular-YRT
  construction paths).

- *`DealConfig.to_dict()` deliberately omits both fields* this slice. `to_dict` is the
  CLI↔dashboard parity surface; no dashboard surface consumes these terms yet, so they
  are omitted exactly as the `yrt_rate_table_*` fields are (added only when a dashboard
  slice uses them — the ALM precedent).

**Verification.** `tests/test_cli_config_expense_allowance.py` (13 tests): both terms
parse from a nested-schema config onto `DealConfig` (incl. a sliding scale); absent →
both `None`; a non-monotone scale raises `PolarisValidationError` at parse time;
`build_treaty` threads both onto YRT / Coinsurance, leaves them `None` by default, and
ignores them for Modco; `_build_treaty_for_pipeline` carries the deal terms onto the
built treaty; end-to-end, a config-supplied allowance shifts the net/ceded expense line
while preserving `net + ceded == gross`, and an absent term applies byte-identically.
`polaris price` on the golden block is byte-identical (Total PV Profits Reinsurer
$45,386, Cedant $3,513,563); full fast suite (1899) + qa suite (76) green.

**Out of scope.** Surfacing both terms on the API request models (`PriceRequest`,
`ScenarioRequest`, `UQRequest`, `PortfolioDealRequest` — four `_build_treaty` call sites)
and the deal-pricing Excel export (Slice 3b-2b — the next slice); the dashboard input +
`to_dict` parity surface (deferred with 3b-2b's dashboard consideration); auto-forcing
`use_policy_cession` so the allowance's block-aware first-year duration mapping engages
on inforce blocks when an `expense_allowance` is supplied (today the allowance falls back
to the new-business projection-month basis unless `use_policy_cession` is set — a
correctness refinement, harvested as a follow-up).


## ADR-123: Surface expense-allowance / experience-refund terms on the REST API (Tier-B B3 / Expense-allowance epic, Slice 3b-2b-1)

**Date:** 2026-06-30
**Status:** Accepted

**Context.** ADR-122 (Slice 3b-2a) surfaced `expense_allowance` / `experience_refund` on
the CLI config / pipeline deal path, but left the REST API blind to both: a client POSTing
`expense_allowance` to `/api/v1/price` had it silently dropped — the request models carried
no such field and Pydantic's default `extra="ignore"` discarded the key, so `_build_treaty`
constructed the treaty without it (premise reproduced: `PriceRequest.model_validate({...,
"expense_allowance": {...}})` yields `model_extra is None` and no attribute). ADR-122 framed
the remaining surfacing as Slice 3b-2b (API + Excel), but the two are independent consumers
and, per the epic's "decompose, don't defer" pattern (the same reason 3b-2 split into 3b-2a /
3b-2b), 3b-2b is split again: **3b-2b-1 (this slice)** does the four API request models;
**3b-2b-2** does the deal-pricing Excel export.

**Decision.**

- *Two optional fields on each of the four deal-pricing request models* — `PriceRequest`,
  `ScenarioRequest`, `UQRequest`, `PortfolioDealRequest` — `expense_allowance:
  ExpenseAllowance | None` and `experience_refund: ExperienceRefund | None`, both default
  `None`. The API already imports from the `reinsurance` package (`BaseTreaty`, `YRTTreaty`),
  so the models are imported directly (no `TYPE_CHECKING` layering dance — that guard exists
  in `core/pipeline.py` only to keep `core/` from importing `reinsurance/`). Default `None`
  → every existing response is byte-identical.

- *`_build_treaty` gains matching kwargs* threaded onto the constructed `YRTTreaty`
  (both the flat-rate and tabular-rate-table paths) / `CoinsuranceTreaty`. Silently ignored
  for `Modco` / gross — mirrors `build_treaty` in `core/pipeline.py` (ADR-122). The four call
  sites (`price`, `scenario`, `uq`, `_portfolio_from_request_deals`) pass `request.*` /
  `deal_req.*` through.

- *App-level `PolarisValidationError` → HTTP 422 handler.* The nested `ExpenseAllowance`
  validators (the monotone-non-increasing sliding-scale check, ADR-119) raise
  `PolarisValidationError` during FastAPI's request-body parsing — *before* any endpoint
  body runs, so the per-endpoint `except` blocks that already map this error to 422 never
  see it, and it would surface as an unhandled 500. A single `@app.exception_handler`
  registration maps it app-wide to 422, the same status the ADR-074 date-consistency guard
  uses for the semantic half of request validation. This closes a 500-on-malformed-body gap
  the new model-validated request fields would otherwise introduce.

**Verification.** `tests/test_api/test_expense_allowance_api.py` (14 tests, FastAPI
`TestClient`): absent terms → byte-identical response (price / scenario / uq / portfolio);
a config allowance reaches the Coinsurance and YRT treaties and lowers reinsurer profit; the
allowance is a zero-sum reinsurer→cedant transfer (cedant's undiscounted profit rises by
exactly what the reinsurer's falls); a refund lowers reinsurer profit; a loss-ratio sliding
scale parses and applies; Modco ignores both terms (byte-identical); a non-monotone scale
returns 422 (not 500). `polaris price` on the golden block is byte-identical (Total PV
Profits Reinsurer $45,386); full fast suite + qa suite green.

**Out of scope.** The deal-pricing **Excel** export (Slice 3b-2b-2 — the next slice); the
dashboard input + `DealConfig.to_dict()` parity surface (still deferred until a dashboard
surface consumes the terms); the `use_policy_cession` block-aware duration-mapping follow-up
(ADR-122 Out of scope, already harvested as IMPORTANT). No response-schema field is added —
the terms are inputs that move the existing priced numbers, not new outputs.

## ADR-124: Surface expense-allowance / experience-refund terms on the deal-pricing Excel export (Tier-B B3 / Expense-allowance epic, Slice 3b-2b-2)

**Date:** 2026-07-03
**Status:** Accepted

**Context.** ADR-122 (Slice 3b-2a) surfaced `expense_allowance` / `experience_refund` on
the CLI config / pipeline deal path and ADR-123 (Slice 3b-2b-1) on the four REST API request
models, but the deal-pricing **Excel** committee workbook — the packet a reviewer circulates
when pricing a deal — still rendered neither term. A deal priced with a 55%/12% sliding-scale
allowance and a 50%-above-retention refund produced a workbook whose Assumptions sheet named
the reserve basis, mortality, and rated-block composition but was silent on the two treaty
terms that moved the priced numbers (premise reproduced: `grep` of `utils/excel_output.py`
for `expense_allowance` / `experience_refund` returned nothing; no panel, no sheet). This is
the final slice of the B3 epic — with it, the allowance/refund terms are consistent across
all four deal-pricing consumers (config, CLI, API, Excel).

**Decision.**

- *Two optional fields on `DealPricingExport`* — `expense_allowance: ExpenseAllowance | None`
  and `experience_refund: ExperienceRefund | None`, both default `None`. Imported under
  `TYPE_CHECKING` (mirroring the existing `YRTRateTable` annotation in the same module): the
  writer only reads attributes off the models, never constructs or `isinstance`-checks them,
  so a type-only import keeps `utils/excel_output.py` importable without the `[tables]` extra
  and avoids widening the module's runtime import graph. Default `None` for both → every
  workbook priced without these terms is byte-identical.

- *A "Treaty Terms" panel appended to the Assumptions sheet* (not a new sheet). This follows
  the rated-block-panel precedent (ADR-068): the allowance/refund are deal *terms*, kin to the
  metadata already on that sheet, and a standalone sheet for a handful of scalars would be
  heavier than the content warrants. `_write_treaty_terms_panel` renders two independent
  sub-sections — either may appear without the other:
  - **Expense Allowance** — first-year %, renewal %, months/year, plus (when a sliding scale
    is configured) one `≤ loss ratio {threshold}` → allowance-% row per band, mirroring
    `reinsurance/expense_allowance.py`.
  - **Experience Refund** — refund %, retention ($), reinsurer margin %, interest rate,
    mirroring `reinsurance/experience_refund.py`.
  The panel is suppressed entirely when both fields are `None`. To append cleanly after the
  optional rated-block panel, `_write_rated_block_panel` now returns the next free row and
  `_write_assumptions_sheet` threads it into the treaty-terms panel's `start_row` (the
  rated-block output itself is unchanged — same cells, same values — so all-standard
  workbooks stay byte-identical).

- *CLI threads the deal's own terms.* `_cohort_to_deal_pricing_export` passes
  `inputs.deal.expense_allowance` / `inputs.deal.experience_refund` (the `DealConfig` fields
  ADR-122 added) onto the export, so `polaris price --config <cfg> --excel-out` renders the
  panel end-to-end. `None` on the deal (the common path) → no panel.

**Verification.** `tests/test_utils/test_excel_output.py::TestTreatyTermsPanel` (10 tests):
panel absent by default (Assumptions sheet has no "Treaty Terms" label → byte-identical);
allowance first-year/renewal rows carry the supplied rates; sliding-scale bands render one
row per band with the band rate in column B; no sliding-scale rows when the scale is flat;
refund rows carry refund %, retention, margin, interest; allowance-only omits the refund
section and vice-versa; both sections present and ordered (allowance before refund); the
panel coexists with the rated-block panel without clobbering its metrics; no extra sheet is
added. `tests/test_cli_config_expense_allowance.py::TestExcelTreatyTermsPanel` (2 tests):
`polaris price --config --excel-out` renders the panel when the config carries the terms and
omits it when it does not. `polaris price` on the golden block is byte-identical (Total PV
Profits Reinsurer $45,386, Cedant $3,513,563; before/after JSON `diff` empty). Full fast
suite + qa suite green.

**Out of scope.** The dashboard input surface + `DealConfig.to_dict()` parity (still deferred
until a dashboard surface actually consumes the terms — the `yrt_rate_table_*` omission
precedent); per-period / annual refund settlement timing and deficit carryforward (already
in the NICE-TO-HAVE queue from Slice 3a); the `use_policy_cession` block-aware allowance
duration-mapping follow-up (ADR-122 Out of scope, already harvested as IMPORTANT). No
`CashFlowResult` or response-schema field is added — the terms are pricing inputs surfaced
for the reviewer, not new computed outputs.

## ADR-125: Statutory valuation mortality table for CRVM / VM-20 NPR (`AssumptionSet.valuation_mortality`) — Reserve-Basis Exactness epic, Slice 1

**Date:** 2026-07-03
**Status:** Accepted

**Context.** The reserve-basis epic (ADR-087–092) shipped CRVM and VM-20 for Term and Whole
Life, but both value on the **projection best-estimate mortality** — TermLife's CRVM receives
the projection `q` (improvement scale and all) and WholeLife's `_build_valuation_mortality`
hardcodes `self.assumptions.mortality` (premise reproduced by code inspection: `AssumptionSet`
had no valuation-table slot at all). Exact reproduction of a cedant's US statutory CRVM
reserve — the point of the epic — requires valuing on the **prescribed** statutory table
(2001 CSO), which is a different table from the pricing basis. This was harvested as
IMPORTANT in PRODUCT_DIRECTION_2026-06-18 (ADR-089 Out of scope) and is Slice 1 of the
Reserve-Basis Exactness epic (`docs/PLAN_reserve_basis_exactness.md`), started per the
active-epic rule with the Tier-A ladder exhausted.

**Decision.**

- *One new optional contract slot* — `AssumptionSet.valuation_mortality: MortalityTable |
  None = None`. `AssumptionSet` (not `ProjectionConfig`) is the home because the slot is a
  table-valued actuarial assumption and `AssumptionSet` is the versioned audit carrier.
  Default `None` → every statutory basis values on the projection table exactly as before
  (byte-identical; TermLife passes the projection `q` object through unchanged, WholeLife
  falls back inside `_build_valuation_mortality`).

- *The statutory valuation q is static.* The mortality-improvement scale is **never** applied
  to the valuation table — prescribed statutory tables (2001 CSO) are published without a
  projection improvement scale. Per-policy substandard rating (multiplier + flat extra) **is**
  applied, mirroring rated statutory valuation practice and the engine's existing rated
  valuation behaviour (ADR-042).

- *Scope of the slot: CRVM and the VM-20 NPR floor only.* `NET_PREMIUM` (the engine's
  historical pricing-basis reserve) ignores it, and the VM-20 **deterministic reserve** is
  anticipated-experience by definition, so it always stays on the projection (best-estimate)
  assumptions: `VM20 = max(NPR_statutory, DR_best_estimate)`.

- *TermLife* gains `_valuation_q()` (projection `q` when the slot is unset, else
  `_build_statutory_valuation_q()` — the same masked mortality lookup as
  `_build_rate_arrays` with the valuation-table lookup, no improvement, rating applied,
  rates zeroed post-expiry, ages capped at the valuation table's max age). *WholeLife*'s
  `_build_valuation_mortality` and `_valuation_months_to_omega` take an optional
  table/max-age, so the CRVM valuation runs to the **valuation table's omega**
  (certain-death forcing at its max age) while the VM-20 DR keeps the projection table's
  omega.

- *Shared mortality-lookup helper (PR #124 review P2, folded in at maintainer direction).*
  The per-(sex, smoker) masked `get_qx_vector` lookup existed as six near-identical copies
  (TermLife projection + statutory builders, WholeLife projection + valuation builders,
  UniversalLife and Disability mortality builders), and every new reserve basis would have
  added another. It is now single-source: `BaseProduct._lookup_qx_column(table, ages,
  durations)` with per-engine cached `_sex_smoker_masks` (the masks depend only on the
  immutable inforce block, so they are built once instead of per month per combo). Callers
  keep everything that legitimately differs by product/basis — age capping, improvement,
  substandard rating, max-age forcing, expiry masks. Pure refactor: identical float
  operations on disjoint masks; verified byte-identical below. New mortality paths (GAAP,
  Slices 3–4) must call the helper, not copy the loop.

**Verification.** `tests/test_products/test_statutory_valuation_table.py` (15 tests): default
`None` and same-table consistency (slot = projection table reproduces baseline CRVM exactly
when no improvement is configured — Term and WL); improvement isolation (a configured Scale AA
moves the projection-q CRVM but never the valuation-table CRVM); NET_PREMIUM ignores the slot
(Term and WL); VM-20 composition `max(NPR_stat, DR_best_estimate)` pinned on both products;
a 1.5×-scaled conservative table raises the mid-duration Term CRVM reserve and the
early-duration WL CRVM reserve (late-duration WL dominance deliberately not asserted — both
bases grade to face at omega and the higher-q basis carries a higher renewal valuation
premium, so the curves cross, empirically around month 147); an independent numpy FPT
recomputation fed an independently built statutory q (rated block) reproduces the engine
reserve to 1e-10; projection cash flows (claims/premiums) unchanged — only reserves move.
Full fast suite 1940 passed; QA suite 76 passed; golden `flat` config byte-identical (Total
PV Profits Reinsurer $45,386, Cedant $3,513,563). The shared-lookup refactor was verified
byte-identical separately: full fast suite + QA suite green post-refactor and the golden
`flat` JSON output is byte-for-byte identical (empty `diff`) against the pre-refactor run.

**Out of scope.** Surfacing the slot on config/CLI/API and the 2001 CSO integration test
(Slice 2); GAAP FAS 60 (Slices 3–4); a CSV-path escape hatch for arbitrary cedant valuation
tables (Slice-2 open question, `yrt_rate_table_path` precedent); sex/smoker-distinct
statutory table composition helper and a prescribed valuation-interest helper (epic
refinement backlog); the 20-pay expense-allowance cap and exact VM-20 NPR X-factors
(already-tracked NICE-TO-HAVEs).

## ADR-126: Surface `valuation_mortality` on the config / CLI / API deal path — Reserve-Basis Exactness epic, Slice 2

**Date:** 2026-07-03
**Status:** Accepted

**Context.** Slice 1 (ADR-125) added `AssumptionSet.valuation_mortality` and wired CRVM /
the VM-20 NPR floor to value on it, but nothing outside a hand-built `AssumptionSet` could
set the slot: the config parser dropped `deal.valuation_mortality` silently, and neither the
CLI nor the REST API exposed it (premise reproduced before coding — a `golden_config_flat`
config carrying `deal.valuation_mortality: "CSO_2001"` left `assumptions.valuation_mortality`
`None` and `DealConfig` had no such attribute). A reinsurer cannot select the prescribed
statutory table on the deal path, so the epic's headline capability is unreachable end-to-end.

**Decision.**

- *One named-source config field, not a table object.* `DealConfig.valuation_mortality: str |
  None = None` carries a **mortality source id** (`"CSO_2001"` / `"SOA_VBT_2015"` /
  `"CIA_2014"` / `"flat"`), the config/CLI/API-friendly equivalent of the `MortalityTable`
  object on `AssumptionSet`. This mirrors `MortalityConfig.source` (the projection table is
  already selected by name), so a config selects the prescribed table with a single string.

- *One shared loader.* `load_valuation_mortality(source, data_dir)` (new public export in
  `core/pipeline.py`) reuses the projection-table source resolution (`_load_mortality`) but
  applies **no** pricing multiplier and **no** improvement — the valuation table is prescribed
  and static (ADR-125). `build_assumption_set` calls it when `deal.valuation_mortality` is
  set (else leaves the slot `None`); the REST API calls the same helper directly. Single
  source of truth → the CLI/dashboard pipeline and the API resolve the table identically.

- *The pricing multiplier is not applied to the valuation table.* `build_assumption_set`
  scales only the projection mortality by `MortalityConfig.multiplier`; the valuation table
  is loaded raw. A pinned test (`multiplier=2.0` → projection q 0.002, valuation q 0.001)
  guards this — the prescribed table must not inherit the best-estimate loading.

- *CLI: `--valuation-mortality` with flag-over-config precedence.* The `polaris price` flag
  overrides `deal.valuation_mortality` exactly as `--reserve-basis` overrides
  `deal.reserve_basis` (and the YRT-rate-table surfaces). Threaded through
  `_build_pipeline_from_config(valuation_mortality_override=...)`. The prescribed table is
  echoed in the JSON `summary` **only when set** — a run without it carries no
  `valuation_mortality` key, so existing output stays byte-identical (no always-present
  `null`).

- *API: `valuation_mortality` request field, loaded server-side.* `PriceRequest` gains a
  named-source field resolved from `$POLARIS_DATA_DIR/mortality_tables`; an unknown id raises
  `PolarisValidationError`, mapped to HTTP 422 by the endpoint's catch-all. The response is
  unchanged (no echo field) — a follow-up if audit visibility on the API is wanted.

- *Notebook.* `notebooks/02_reserve_basis_comparison.ipynb` gains a section pricing CRVM on a
  conservative **prescribed** table vs the best-estimate table, with embedded asserts (the
  prescribed table moves CRVM; `NET_PREMIUM` ignores it). It uses a synthetic table so the
  notebook runs without the converted CSVs.

**Verification.** `tests/test_core/test_pipeline_valuation_mortality.py` (7 tests: loader,
default `None`, attachment, multiplier isolation, unknown-source raise);
`tests/test_cli_valuation_mortality.py` (8 tests: no key by default, flag echo,
CRVM-on-CSO ≠ CRVM-on-projection-table on the WL cohort, `NET_PREMIUM` ignores the slot,
unknown-source non-zero exit, config-field honoured, flag-over-config, default has no field);
`tests/test_api/test_valuation_mortality.py` (5 tests: omitted accepted, omitted ≡ explicit
null, CRVM-on-CSO moves the number, `NET_PREMIUM` ignores the slot, unknown-source 422);
`tests/test_notebooks/test_reserve_basis_notebook.py` (execution guard). CSO-dependent tests
are skipped when the converted 2001 CSO CSVs are absent (CI-safe); the multiplier-isolation,
byte-identity, and unknown-source paths use the synthetic `"flat"` source and always run.
Omitting the field is byte-identical on all four golden configs (none set it).

**Out of scope.** A CSV-path escape hatch for an arbitrary cedant valuation table (named
source id only for now — the `yrt_rate_table_path` precedent, Slice-2 open question); echoing
the prescribed table in the API response and on the Excel/dashboard surfaces; GAAP FAS 60
(Slices 3–4); the sex/smoker-distinct statutory-table composition helper and the prescribed
valuation-interest helper (epic refinement backlog).

**Design boundary & guidance for Slices 3–4 (recorded after the PR #125 review flagged the
statutory-basis choice for a human glance).** The commercial thesis this serves is inforce-block
reinsurance: a reinsurer reproducing a cedant's held statutory reserve (to price coinsurance /
modco, quantify the cedant's reserve/capital relief, produce a profit signature that reports on
the statutory ledger, and defend it to auditors/regulators) must value on the **prescribed**
table, not its pricing best-estimate table — that is why CRVM / the VM-20 NPR value on
`valuation_mortality`. Two boundaries constrain the work that builds on this:

- *"Static / no-improvement" is a property of the US-statutory bases, NOT a global default.*
  CRVM and the VM-20 NPR are prescribed regulatory formulas (published CSO table fixed by issue
  year, conservatism in the table's own margins, no generational-improvement overlay); the VM-20
  **DR** deliberately stays best-estimate *with* improvement (`VM20 = max(NPR_prescribed,
  DR_best_estimate)`). **GAAP (FAS 60), Slices 3–4, must define its own basis** — a locked-in
  best-estimate net-premium reserve plus explicit PADs, where the best estimate legitimately
  includes the improvement scale locked in at issue. GAAP therefore does **not** read
  `valuation_mortality` and does **not** suppress improvement the way
  `_build_statutory_valuation_q` does; it reuses `load_valuation_mortality` / `_lookup_qx_column`
  as plumbing only. The same caution applies to any future non-US path (e.g. CIA / IFRS 17),
  where valuation mortality *does* carry improvement in some regimes. (This supersedes the
  earlier PLAN note that "GAAP should honour `valuation_mortality` resolution order from day
  one," which conflated the statutory basis rule with GAAP.)

- *Mortality-basis exactness is only half of "reproduce the cedant's reserve."* CRVM / the
  VM-20 NPR also use a **prescribed maximum valuation interest rate** by issue year / product;
  the engine still takes a single manual `valuation_interest_rate`. So Slices 1–2 reproduce the
  statutory reserve *directionally*, not to the penny. The issue-year → prescribed-rate helper
  (and, secondarily, an issue-year → CSO-version selector for 2001-vs-2017 applicability) is the
  gating item for penny-exact reproduction and should be sequenced before "exact CRVM
  reproduction" is positioned as complete. Recorded in the CONTINUATION Refinement Backlog and
  PRODUCT_DIRECTION_2026-06-18.

## ADR-127: GAAP (FAS 60) net-premium benefit reserve for TermLife — Reserve-Basis Exactness epic, Slice 3

**Date:** 2026-07-04
**Status:** Accepted

**Context.** `ReserveBasis.GAAP` has existed in the enum since the original reserve-basis epic
(ADR-092 surfaced the selector everywhere), but selecting it raised `PolarisComputationError`
via `BaseProduct._check_reserve_basis` — no engine computed it (premise reproduced before
coding: the baseline-green `test_reserve_basis_dispatch` asserted GAAP raises for TermLife, and
`polaris price --reserve-basis GAAP` on a term block exited non-zero on the guard). US GAAP
(FAS 60 / ASC 944) is the benefit-reserve basis a US cedant commonly reports on for traditional
(non-participating) life business, and it is the second of the two IMPORTANT residuals the
Reserve-Basis Exactness epic exists to close (`docs/PLAN_reserve_basis_exactness.md`, Slice 3).

**Decision.**

- *GAAP is the net premium reserve on a margined best-estimate basis.* FAS 60 values the
  benefit reserve as a net level premium reserve on **locked-in best-estimate assumptions plus
  explicit provisions for adverse deviation (PADs)**. `TermLife._compute_reserves_gaap` reuses
  the existing net-premium machinery (`_compute_reserves_net_premium` — the equivalence-principle
  level net premium and its backward recursion) but feeds it a PAD-adjusted mortality and a
  PAD-adjusted discount rate. GAAP is added to `TermLife._supported_reserve_bases`, so selecting
  it stops raising for term.

- *Two PADs, on `ProjectionConfig`.* `gaap_mortality_pad: float = 1.0` (ge 1.0) is a
  multiplicative margin applied to the projection best-estimate `q` (capped at 1.0);
  `gaap_interest_margin: float = 0.0` (ge 0, le 1) is an absolute haircut subtracted from the
  valuation interest rate, exposed as the `ProjectionConfig.gaap_valuation_rate` property
  (`max(effective_valuation_rate - gaap_interest_margin, 0.0)`). Both default neutral, so a
  GAAP run with no explicit PAD reduces **exactly** to the locked-in best-estimate net premium
  reserve (the closed-form identity pinned in the tests) and every existing config/priced number
  stays byte-identical (no golden selects GAAP).

- *GUARDRAIL — GAAP defines its OWN basis; it does NOT inherit the statutory static /
  no-improvement rule.* This is the key design boundary carried from ADR-125/126. The statutory
  bases (CRVM / VM-20 NPR) value on a **prescribed, static, no-improvement** table
  (`assumptions.valuation_mortality`) because they are prescribed regulatory formulas. FAS 60 is
  a different animal — a locked-in **best-estimate** reserve plus explicit margins — and the best
  estimate legitimately includes the mortality-improvement scale (part of the projection
  assumptions, locked at issue). So `_compute_reserves_gaap` uses the projection `q` from
  `_build_rate_arrays` (improvement and substandard rating already applied) and **never** reads
  `assumptions.valuation_mortality` nor suppresses improvement. Two tests pin this: a wildly
  different prescribed valuation table does not move GAAP (byte-identical), and a configured
  Scale AA improvement DOES move GAAP (unlike a static statutory basis).

- *Interest-margin direction is not uniform across duration.* A lower locked-in discount rate
  raises the reserve through the accumulation phase but can flip sign in the late run-off
  durations (the higher net premium pulls the tail down). The property test asserts the
  unambiguous accumulation-phase direction, not a whole-horizon inequality — documenting the
  actuarial behaviour rather than over-constraining it.

**Verification.** `tests/test_products/test_term_gaap_reserve.py` (12 tests): GAAP is supported
and produces a real reserve; neutral PADs equal NET_PREMIUM to 1e-9 (with and without a
configured improvement scale); a mortality PAD (1.10) and an interest margin (0.01) each raise
the accumulation-phase reserve, mortality-PAD reserve monotonic in the margin; an independent
numpy recomputation of the FAS 60 net premium reserve on the PAD-adjusted basis
(pad 1.15, margin 0.0075) reproduces the engine reserve to 1e-10; GAAP ignores
`valuation_mortality` (guardrail) and reflects mortality improvement (guardrail). The
dispatch/API tests that asserted GAAP raises for TermLife were updated to exercise WholeLife
(GAAP still unimplemented there until Slice 4). Full fast suite 1973 passed / 1 skipped; QA
suite 76 passed; golden `flat` byte-identical (GAAP unset everywhere; end-to-end `polaris price
--reserve-basis GAAP` on a term-only block equals NET_PREMIUM with neutral PADs, confirming the
identity on the deal path).

**Out of scope.** GAAP for WholeLife (Slice 4 — WL still raises). Surfacing the two PAD knobs on
the deal path (`DealConfig` / CLI flags / REST API) — this slice puts them on `ProjectionConfig`
(the config object the notebooks/analytics build directly); the deal-path surfacing mirrors the
dedicated surfacing slice `valuation_mortality` got (ADR-126 after ADR-125) and is harvested as
a 1st-order follow-up. FAS 60 deferred acquisition cost (DAC) amortisation and the loss-recognition
/ premium-deficiency test are not modelled — this is the benefit reserve only. Duration-varying
or select-period PAD structures (a single flat mortality multiplier + flat interest haircut here).

---

## ADR-128: GAAP (FAS 60) net level premium reserve for WholeLife — Reserve-Basis Exactness epic, Slice 4

**Status.** Accepted (2026-07-04).

**Context.** ADR-127 implemented GAAP (FAS 60) for `TermLife`; `WholeLife` still raised on the
GAAP basis via the dispatch guard. This is the final residual of the Reserve-Basis Exactness
epic (`docs/PLAN_reserve_basis_exactness.md`, Slice 4). US GAAP is a basis a US cedant commonly
reports whole life on, so a reinsurer reproducing the cedant's reserve needs it for WholeLife as
well as TermLife.

**Decision.**

- *GAAP is the net LEVEL premium benefit reserve on a margined best-estimate basis, valued
  prospectively to omega.* Like the TermLife GAAP (ADR-127) it is a net premium reserve on
  **locked-in best-estimate assumptions plus explicit provisions for adverse deviation (PADs)**,
  reusing the same two `ProjectionConfig` knobs (`gaap_mortality_pad`, `gaap_interest_margin`).
  Unlike TermLife (a finite-horizon backward recursion with terminal `V_T = 0`), WholeLife
  `_compute_reserves_gaap` values **prospectively to omega** — the same to-omega valuation grid
  the CRVM / VM-20 paths use (`_valuation_months_to_omega`, `_build_valuation_mortality`) — so
  the reserve does **not** collapse at the projection horizon the way the WL net-premium
  one-period terminal estimate does (the ADR-089 artefact). GAAP is added to
  `WholeLife._supported_reserve_bases`, so selecting it stops raising for whole life.

- *Net LEVEL premium, not Full Preliminary Term.* WholeLife CRVM uses an FPT (year-1 alpha /
  renewal beta) split to grade in the first-year expense allowance — a **statutory** device.
  FAS 60 uses a single net **level** valuation premium (the equivalence-principle premium over
  the premium-paying window, funding the to-omega benefit), so `_compute_reserves_gaap` computes
  one `P = APV(benefits to omega) / APV(premium annuity)` per policy rather than reusing the
  FPT modified premiums. The prospective-reserve reverse-cumsum machinery is otherwise identical
  to the CRVM path.

- *Margined best-estimate basis.* Mortality is the projection valuation q built to omega on the
  **projection** table (mortality-only, per-(sex, smoker) `_lookup_qx_column`, substandard rating
  and max-age certain-death forcing already applied) scaled by `gaap_mortality_pad` and capped at
  1.0; interest is the locked-in `gaap_valuation_rate`. With both PADs neutral this reduces to
  the locked-in best-estimate net level premium reserve valued to omega (the closed-form identity
  pinned in the tests). No golden selects GAAP, so every priced number stays byte-identical.

- *GUARDRAIL — WL GAAP defines its OWN basis; it does NOT read `assumptions.valuation_mortality`.*
  Same boundary as ADR-127: FAS 60 is a best-estimate + PAD basis, not a prescribed static
  statutory one, so `_compute_reserves_gaap` passes `table=None` to the valuation-q builder (the
  projection table, not the prescribed statutory table). A test pins that a wildly different
  prescribed valuation table does not move WL GAAP. WholeLife does not model mortality improvement
  on any basis (it is not applied in `_build_rate_arrays`), so — unlike TermLife GAAP — there is
  no improvement half to the guardrail here; the valuation-table independence is the operative
  property, and WL improvement modelling is a separate pre-existing gap (harvested follow-up).

- *Mortality-PAD direction is not uniform across duration.* As with the TermLife interest-margin
  case, a higher mortality PAD raises the reserve through the early/mid accumulation phase but can
  flip sign in the late run-off durations (the higher net level premium pulls the tail down). The
  property test asserts the unambiguous early/mid-accumulation direction, not a whole-horizon
  inequality. The interest margin raises the reserve monotonically through the checked horizon.

**Verification.** `tests/test_products/test_wl_gaap_reserve.py` (17 tests): GAAP is supported
(whole-life pay and limited-pay) and produces a real reserve; neutral-PAD, PAD-adjusted, and
limited-pay reserves each reproduce an independent numpy recomputation of the net-level-premium-
to-omega reserve (the closed-form verification); GAAP differs materially from WL NET_PREMIUM at
the horizon edge (the to-omega vs one-period-terminal distinction); a mortality PAD and an
interest margin each raise the accumulation-phase reserve, mortality-PAD reserve monotonic in the
margin at month 120; GAAP ignores `valuation_mortality` (guardrail). Per the PR #127 review (P2),
the closed-form recomputation uses a **different reserve formulation** than the engine — a
per-survivor backward recursion (`V_t = (q_t*face + (1-q_t)*V_{t+1})*v - P_t`, terminal
`V_omega = 0`) vs the engine's reverse-cumulative-PV — so the two agree to ~2e-9 (checked at
1e-8) and catch a shared *conceptual* error, not merely a transcription slip; a
formulation-independent equivalence-principle identity (`V_0 = APV(benefits) - P*APV(annuity) = 0`
at issue, neutral and padded) backs it. The `test_reserve_basis_dispatch` and
`test_api/test_reserve_basis` GAAP-raises cases moved off WholeLife to UniversalLife (which still
supports NET_PREMIUM only); a new API test pins that WL GAAP now prices successfully and echoes
the basis. Full fast suite green; QA suite 76 passed; golden `flat` byte-identical (GAAP unset
everywhere).

**Out of scope.** WholeLife mortality-improvement modelling (a pre-existing gap: WL does not apply
the improvement scale on any basis, so WL GAAP inherits the improvement-blind best estimate —
harvested as an IMPORTANT follow-up). Surfacing the two PAD knobs on the deal path
(`DealConfig` / CLI flags / REST API) remains the ADR-127 harvested follow-up and now covers both
products. FAS 60 DAC amortisation and the loss-recognition / premium-deficiency test are not
modelled (benefit reserve only). Duration-varying / select-period PAD structures (a single flat
mortality multiplier + flat interest haircut here). This ADR closes the Reserve-Basis Exactness
epic (`CONTINUATION_reserve_basis_exactness.md` → COMPLETE).
