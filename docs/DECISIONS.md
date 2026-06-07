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
