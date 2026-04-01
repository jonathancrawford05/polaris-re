# Task: Calibrated Premium Generation (ADR-037)

## Summary

Replace the illustrative premium formula in `generate_synthetic_block.py` with a mortality-table-calibrated premium calculation driven by a target loss ratio. Update the dashboard accordingly.

**Problem:** The current synthetic block generator uses `base_rate_per_1000 = 0.8 + issue_ages * 0.05`, which produces premiums that are actuarially inadequate when paired with real mortality tables (SOA VBT 2015, CIA 2014). The premium formula underprices policies above age ~45, causing every IFRS 17 BBA measurement to show a fully onerous contract with zero CSM. The premium formula must be calibrated to the chosen mortality basis.

**Solution:** Compute level annual premiums from the average expected annual mortality across the policy term, scaled by a target loss ratio. The loss ratio replaces the manual premium input throughout the dashboard.

---

## ADR-037: Mortality-Calibrated Premium Formula

Add this to `docs/DECISIONS.md`:

```
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
  2. Derive annual premium = (face_amount × avg_annual_qx) / target_loss_ratio.
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
```

---

## File Changes

### 1. `scripts/generate_synthetic_block.py`

**Goal:** Accept a mortality table source and target loss ratio. Use them to compute adequate premiums.

**Changes to `generate_synthetic_block()`:**

Add new parameters:
```python
def generate_synthetic_block(
    n_policies: int,
    seed: int = 42,
    valuation_date: date = date(2025, 1, 1),
    *,
    mean_age: int = 40,
    age_std: int = 8,
    male_pct: int = 60,
    smoker_pct: int = 15,
    face_median: int = 500_000,
    term_10_pct: int = 20,
    term_20_pct: int = 60,
    mortality_table_source: str = "SOA_VBT_2015",  # NEW
    target_loss_ratio: float = 0.60,                # NEW
    data_dir: str | None = None,                    # NEW
) -> pl.DataFrame:
```

**Premium computation logic** (replaces the `base_rate_per_1000` block):

```python
# --- Compute mortality-calibrated premiums ---
# Load mortality table
from pathlib import Path
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource

table_source = MortalityTableSource(mortality_table_source)
mort_data_dir = Path(data_dir) if data_dir else Path(
    os.environ.get("POLARIS_DATA_DIR", "data")
) / "mortality_tables"
mortality_table = MortalityTable.load(source=table_source, data_dir=mort_data_dir)

# For each policy, compute average annual q_x over the policy term
# using the ultimate column (conservative, ignores select-period discounts)
annual_premiums = np.zeros(n, dtype=np.float64)
for i in range(n):
    age = int(issue_ages[i])
    term = int(policy_terms[i])
    sex_enum = Sex.MALE if sexes[i] == "M" else Sex.FEMALE
    smoker_enum = SmokerStatus.SMOKER if smokers[i] == "S" else SmokerStatus.NON_SMOKER

    # Average q_x across ages [issue_age, issue_age + term - 1]
    ages_over_term = np.arange(age, min(age + term, mortality_table.max_age + 1), dtype=np.int32)
    # Use ultimate durations (duration >> select period) for conservative pricing
    durations_ult = np.full_like(ages_over_term, mortality_table.select_period_years * 12 + 12)

    qx_annual_vec = mortality_table.get_qx_vector(ages_over_term, sex_enum, smoker_enum, durations_ult)
    # get_qx_vector returns monthly rates — convert back to annual
    qx_annual = 1.0 - (1.0 - qx_annual_vec) ** 12

    avg_annual_qx = float(qx_annual.mean())
    annual_premiums[i] = (face_amounts[i] * avg_annual_qx) / target_loss_ratio
```

**Important:** Remove the old `base_rate_per_1000` and `smoker_multiplier` lines entirely. The smoker loading is now implicit — smoker policies look up smoker-specific mortality rates which are naturally higher.

**Also add** `import os` to imports and add `Sex, SmokerStatus` imports:
```python
from polaris_re.core.policy import Sex, SmokerStatus
```

**Update `main()` CLI arguments:**
```python
parser.add_argument(
    "--mortality-source",
    type=str,
    default="SOA_VBT_2015",
    choices=["SOA_VBT_2015", "CIA_2014", "CSO_2001"],
    help="Mortality table source for premium calibration",
)
parser.add_argument(
    "--target-loss-ratio",
    type=float,
    default=0.60,
    help="Target loss ratio (0.0-1.0). Premium = expected_claims / loss_ratio",
)
parser.add_argument(
    "--data-dir",
    type=str,
    default=None,
    help="Directory containing mortality table CSVs",
)
```

And pass them through:
```python
df = generate_synthetic_block(
    n_policies=args.n_policies,
    seed=args.seed,
    mortality_table_source=args.mortality_source,
    target_loss_ratio=args.target_loss_ratio,
    data_dir=args.data_dir,
)
```

**Note on the vectorized loop:** The loop over policies is needed because each policy may have a different (sex, smoker, age, term) combination. This is acceptable for a generation script. If performance is a concern for very large blocks (>50k), consider grouping by (sex, smoker, term) and vectorizing within groups — but this is not required for this task.

---

### 2. `src/polaris_re/dashboard/views/inforce.py`

**Goal:** Add mortality table source and target loss ratio controls to the synthetic generation tab.

**Changes to `_synthetic_tab()`:**

Add a new row of controls below the existing demographic sliders:

```python
st.subheader("Premium Calibration")
pc1, pc2 = st.columns(2)
with pc1:
    mortality_source = st.selectbox(
        "Mortality Table for Pricing",
        ["SOA_VBT_2015", "CIA_2014", "CSO_2001"],
        index=0,
        help="Premiums are calibrated to expected mortality from this table.",
    )
with pc2:
    target_loss_ratio = st.slider(
        "Target Loss Ratio",
        min_value=0.30,
        max_value=0.90,
        value=0.60,
        step=0.05,
        format="%.0f%%",  # NOTE: Streamlit formats the raw float, so display will need adjustment
        help=(
            "Ratio of expected claims to premiums. "
            "Lower = more profitable. 0.60 means 60% of premium covers expected claims."
        ),
    )
```

**Note on format:** Streamlit's `format` applies to the raw float value. Since the slider returns 0.30-0.90, use `format="%.2f"` and label the slider "Target Loss Ratio (0=low claims, 1=all claims)". Alternatively, use an integer percentage slider (30-90) and divide by 100.

Pass the new params to `generate_synthetic_block()`:

```python
df = generate_synthetic_block(
    n_policies=n_policies,
    mean_age=mean_age,
    age_std=age_std,
    male_pct=male_pct,
    smoker_pct=smoker_pct,
    face_median=face_median,
    term_10_pct=term_10,
    term_20_pct=term_20,
    mortality_table_source=mortality_source,
    target_loss_ratio=target_loss_ratio,
)
```

---

### 3. `src/polaris_re/dashboard/views/pricing.py`

**Goal:** Replace the manual "Annual Premium" input in the fallback section with a "Target Loss Ratio" slider, and derive premiums from mortality and loss ratio.

**Changes to the fallback slider section** (the `if not use_session:` block):

Replace:
```python
annual_premium = float(
    st.number_input(
        "Annual Premium ($)", min_value=100, max_value=50_000, value=1_200, step=100
    )
)
```

With:
```python
target_loss_ratio = st.slider(
    "Target Loss Ratio",
    min_value=0.30,
    max_value=0.90,
    value=0.60,
    step=0.05,
    help="Ratio of expected claims to premiums. Lower = more profitable.",
)
```

**Changes to `_build_fallback_block()`:**

Update signature — replace `annual_premium` param with `target_loss_ratio` and `flat_qx`:
```python
def _build_fallback_block(
    n_policies: int,
    attained_age: int,
    face_amount: float,
    flat_qx: float,
    target_loss_ratio: float,
    term_years: int,
    valuation_date: date,
) -> object:
```

Compute premium inside the function:
```python
# Calibrate premium to mortality and loss ratio
# flat_qx is annual; premium = face × qx / loss_ratio
annual_premium = (face_amount * flat_qx) / target_loss_ratio
```

**Update the call site** in `page_pricing()` under the `if st.button("Run Pricing")` block:
```python
inforce = _build_fallback_block(
    n_policies,
    attained_age,
    face_amount,
    flat_qx,
    target_loss_ratio,
    projection_years,
    valuation_date,
)
```

---

### 4. Tests

**Add/update tests in `tests/`:**

#### `tests/test_synthetic_block.py` (new file)

```python
"""Tests for the calibrated premium generation in generate_synthetic_block."""

import sys
from pathlib import Path

import numpy as np
import pytest

# Add scripts dir to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from generate_synthetic_block import generate_synthetic_block


@pytest.fixture
def data_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "mortality_tables"


class TestCalibratedPremiums:
    """Verify that premiums are calibrated to mortality and loss ratio."""

    def test_premiums_scale_with_loss_ratio(self, data_dir: Path) -> None:
        """Lower loss ratio → higher premiums (more margin)."""
        df_60 = generate_synthetic_block(
            n_policies=50,
            seed=42,
            target_loss_ratio=0.60,
            data_dir=str(data_dir),
        )
        df_40 = generate_synthetic_block(
            n_policies=50,
            seed=42,
            target_loss_ratio=0.40,
            data_dir=str(data_dir),
        )
        # Same policies, different loss ratios
        assert df_40["annual_premium"].sum() > df_60["annual_premium"].sum()
        # Ratio should be approximately 0.60/0.40 = 1.5
        ratio = df_40["annual_premium"].sum() / df_60["annual_premium"].sum()
        assert 1.4 < ratio < 1.6

    def test_smokers_pay_more(self, data_dir: Path) -> None:
        """Smoker policies should have higher premiums due to higher mortality."""
        df = generate_synthetic_block(
            n_policies=500,
            seed=42,
            smoker_pct=50,  # 50/50 split for statistical power
            target_loss_ratio=0.60,
            data_dir=str(data_dir),
        )
        smoker_avg = df.filter(df["smoker_status"] == "S")["annual_premium"].mean()
        ns_avg = df.filter(df["smoker_status"] == "NS")["annual_premium"].mean()
        assert smoker_avg > ns_avg

    def test_premiums_positive(self, data_dir: Path) -> None:
        """All generated premiums must be positive."""
        df = generate_synthetic_block(
            n_policies=100,
            seed=42,
            target_loss_ratio=0.60,
            data_dir=str(data_dir),
        )
        assert (df["annual_premium"] > 0).all()

    def test_loss_ratio_sanity(self, data_dir: Path) -> None:
        """
        Rough check: for a single-age cohort, the ratio of
        (avg_qx * face) / premium should approximate the target loss ratio.
        """
        df = generate_synthetic_block(
            n_policies=200,
            seed=42,
            mean_age=40,
            age_std=1,  # tight age distribution
            target_loss_ratio=0.60,
            data_dir=str(data_dir),
        )
        # This is an approximate check — the generated premiums use
        # average q_x over the term, so the ratio won't be exact
        avg_premium = df["annual_premium"].mean()
        avg_face = df["face_amount"].mean()
        # Premium should be in a reasonable range relative to face amount
        assert avg_premium > 0
        assert avg_premium < avg_face * 0.10  # premium < 10% of face
```

#### Update `tests/test_analytics/test_ifrs17.py`

If the existing IFRS 17 tests use the old pricing formula or hardcoded premium values, verify they still pass. The IFRS 17 module itself doesn't change — it consumes `CashFlowResult` which is upstream. No changes expected here, but run the full test suite to confirm.

---

## Verification Steps

After implementing, verify:

1. **`make test`** (or `pytest`) passes with all existing + new tests.
2. **`ruff check src/ scripts/ tests/`** passes (no lint errors).
3. **Dashboard flow:**
   - Navigate to Inforce Block → Generate Synthetic tab
   - Set target loss ratio to 0.60, mortality source SOA VBT 2015, generate 1000 policies
   - Navigate to Assumptions → select SOA VBT 2015 (same table) → Save Assumptions
   - Navigate to Deal Pricing → Run Pricing → verify positive PV Profits
   - Navigate to IFRS 17 → Run BBA → verify CSM > 0 (contract is profitable)
   - Try loss ratio = 0.90 → should produce a thinner margin or onerous contract
   - Try loss ratio = 0.40 → should produce a very large CSM

4. **CLI test:**
   ```bash
   python scripts/generate_synthetic_block.py \
     --n-policies 100 \
     --mortality-source SOA_VBT_2015 \
     --target-loss-ratio 0.60 \
     --output data/test_calibrated.csv
   ```
   Inspect the CSV — premiums should vary by age, sex, and smoker status.

---

## Scope Boundaries

**In scope:**
- `scripts/generate_synthetic_block.py` — calibrated premium formula
- `src/polaris_re/dashboard/views/inforce.py` — loss ratio + table selector in synthetic tab
- `src/polaris_re/dashboard/views/pricing.py` — replace manual premium with loss ratio in fallback
- `docs/DECISIONS.md` — append ADR-037
- New test file `tests/test_synthetic_block.py`

**Out of scope:**
- No changes to core projection engine (`TermLife`, `CashFlowResult`)
- No changes to IFRS 17 measurement logic
- No changes to mortality table loading or lapse assumptions
- No changes to reinsurance treaty logic
- No full APV/net premium calculation — the average q_x approach is sufficient
