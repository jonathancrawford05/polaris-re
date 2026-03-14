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
