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
