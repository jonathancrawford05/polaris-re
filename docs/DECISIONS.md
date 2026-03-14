# Architecture Decision Records — Polaris RE

This document records significant architecture and design decisions made during development. Each entry explains the context, the options considered, and the rationale for the choice made.

---

## ADR-001: Pydantic v2 as the primary data validation layer

**Date:** Project inception  
**Status:** Accepted

**Context:** Policy data, assumption sets, and cash flow results all require structured validation. Options considered: dataclasses, attrs, Pydantic v1, Pydantic v2.

**Decision:** Pydantic v2 throughout.

**Rationale:** Pydantic v2 (Rust-based core) is significantly faster than v1. The `model_validator` and `field_validator` API is more explicit. JSON serialization is built-in, which matters when results need to be stored or transmitted. The `model_config` system allows enforcing immutability (`frozen=True`) on assumption objects — critical for ensuring assumption sets are not mutated mid-projection.

---

## ADR-002: Polars over pandas as the primary DataFrame library

**Date:** Project inception  
**Status:** Accepted

**Context:** Inforce block data manipulations — filtering, grouping, aggregating policy attributes — require a DataFrame abstraction. Options: pandas, Polars, cuDF.

**Decision:** Polars by default; pandas only for interoperability (e.g., reading AXIS output formats, matplotlib integration).

**Rationale:** Polars is 5–10x faster than pandas on typical actuarial workloads (group-bys on policy data, rolling aggregations). The lazy evaluation API is valuable for large inforce blocks. The stricter type system catches errors earlier. The main downside is a smaller ecosystem — addressed by providing pandas conversion utilities in `utils/`.

---

## ADR-003: NumPy arrays (not DataFrames) as the projection compute layer

**Date:** Project inception  
**Status:** Accepted

**Context:** The projection engine needs to run vectorized calculations across N policies × T time steps. Options: nested DataFrames, xarray, numpy arrays, torch tensors.

**Decision:** Raw NumPy arrays with shape `(N, T)` for all projection intermediates.

**Rationale:** NumPy is the lowest-overhead option with the most predictable memory layout. `xarray` adds useful labeling but also overhead and complexity that isn't needed for the core projection loop. PyTorch tensors would enable GPU acceleration (a Phase 3 option) but introduce a heavy dependency. The `(N, T)` layout allows efficient column-wise (time-step) operations and row-wise (policy) operations equally.

---

## ADR-004: Monthly time step for projections

**Date:** Project inception  
**Status:** Accepted

**Context:** Life insurance cash flows can be modeled at annual, quarterly, or monthly granularity.

**Decision:** Monthly time step throughout.

**Rationale:** Monthly is the industry standard for individual life reinsurance cash flow modeling. It captures seasonal mortality patterns and mid-year policy anniversary effects that annual models miss. The performance cost of 12× more time steps is negligible given vectorization. Annual summary outputs are trivially produced by summing monthly arrays.

---

## ADR-005: Net premium reserves for Phase 1, not gross premium or IFRS 17

**Date:** Project inception  
**Status:** Accepted, reviewed in Phase 3

**Context:** Multiple reserve bases exist: net premium reserves (NP), gross premium reserves (GP), IFRS 17 BBA/PAA, US GAAP LDTI. IFRS 17 is the regulatory standard for Munich Re and most international reinsurers.

**Decision:** Net premium reserves for Phase 1.

**Rationale:** NP reserves are the simplest auditable basis — fully deterministic given a mortality table and valuation interest rate. They are well-understood by any credentialed actuary. The reserve recursion is clean and easy to verify by hand. IFRS 17 (with CSM and RA calculations) is added in Phase 3 once the projection engine is proven correct. The architecture is designed so that reserves are pluggable — the `BaseProduct.compute_reserves()` method can be overridden for different bases.

---

## ADR-006: CSV-based mortality table storage (not database)

**Date:** Project inception  
**Status:** Accepted

**Context:** Mortality tables could be stored in SQLite, a dedicated database, binary formats (parquet, HDF5), or CSV.

**Decision:** CSV with a standardized column schema, loaded at `AssumptionSet` construction time.

**Rationale:** CSV is auditable — an actuary can open it in Excel and verify values. It has no binary dependencies. Tables change rarely (new industry studies every 5–10 years). The performance cost of CSV loading is amortized by caching the loaded table in the `MortalityTable` object. A future `parquet` option can be added as an alternative loader without changing the API.

---

## ADR-007: Separation of product logic from treaty logic

**Date:** Project inception  
**Status:** Accepted

**Context:** Should treaty calculations be embedded in product code, or applied as a post-processing step?

**Decision:** Treaties are transformations applied to `CashFlowResult` objects after projection. Product code knows nothing about treaties.

**Rationale:** This enables modeling the same inforce block under multiple treaty structures without re-running the projection. It also enables stacking treaties (e.g., a quota share on top of a YRT arrangement). The clean separation makes each component independently testable. The main risk is that some treaty structures (e.g., experience refund arrangements) require access to projected reserves in ways that may need a callback — handled by passing the full `CashFlowResult` including reserves to the treaty `apply()` method.
