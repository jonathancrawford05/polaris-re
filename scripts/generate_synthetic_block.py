#!/usr/bin/env python3
"""
generate_synthetic_block.py — Generate a synthetic inforce block for testing.

Creates a CSV of synthetic policies with realistic distributions of
age, sex, smoker status, face amount, and duration for use in
development and testing when real inforce data is not available.

Usage:
    python scripts/generate_synthetic_block.py --n-policies 10000 --output data/test_block.csv
    python scripts/generate_synthetic_block.py --n-policies 100 --seed 42
"""

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

try:
    import polars as pl
except ImportError:
    print("polars not installed. Run: pip install polars")
    sys.exit(1)


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
    whole_life_pct: int = 0,
    mortality_table_source: str = "SOA_VBT_2015",
    target_loss_ratio: float = 0.60,
    data_dir: str | None = None,
) -> pl.DataFrame:
    """
    Generate a synthetic inforce block with realistic distributions.

    Distributions are approximate representations of a typical North American
    individual life portfolio. Not calibrated to any specific real portfolio.

    Parameters
    ----------
    n_policies : int
        Number of policies to generate.
    seed : int
        Random seed for reproducibility.
    valuation_date : date
        Valuation date for all policies.
    mean_age : int
        Mean issue age (default 40).
    age_std : int
        Std dev of issue age distribution (default 8).
    male_pct : int
        Percentage of male policies, 0-100 (default 60).
    smoker_pct : int
        Percentage of smoker policies, 0-100 (default 15).
    face_median : int
        Median face amount in dollars (default 500,000).
    term_10_pct : int
        Percentage of 10-year term policies within the TERM portion, 0-100 (default 20).
    term_20_pct : int
        Percentage of 20-year term policies within the TERM portion, 0-100 (default 60).
        The remainder (100 - term_10_pct - term_20_pct) is 30-year term.
    whole_life_pct : int
        Percentage of whole life policies in the block, 0-100 (default 0).
        The remaining (100 - whole_life_pct) % are term policies.
    """
    rng = np.random.default_rng(seed)
    n = n_policies

    # --- Product type assignment ---
    n_wl = round(n * whole_life_pct / 100)
    n_term = n - n_wl
    product_types = np.array(["TERM"] * n_term + ["WHOLE_LIFE"] * n_wl)
    rng.shuffle(product_types)
    is_term = product_types == "TERM"

    # Ages (ANB)
    issue_ages = np.clip(rng.normal(mean_age, age_std, n).astype(int), 20, 65)

    # --- Policy terms and durations ---
    # TERM policies: 10/20/30-year mix
    term_30_pct = 100 - term_10_pct - term_20_pct
    term_probs = [term_10_pct / 100, term_20_pct / 100, max(0, term_30_pct) / 100]
    # Allocate terms for all policies; WL entries will be overwritten
    policy_terms_int = rng.choice([10, 20, 30], size=n, p=term_probs)

    # Durations: TERM capped at (term*12 - 1); WL capped at 30 years
    max_durations = np.where(
        is_term,
        policy_terms_int * 12 - 1,
        30 * 12 - 1,
    ).astype(int)
    durations = np.array([rng.integers(0, max_dur + 1) for max_dur in max_durations])

    # Attained ages
    attained_ages = issue_ages + (durations // 12)

    # Sex
    male_frac = male_pct / 100
    sexes = rng.choice(["M", "F"], size=n, p=[male_frac, 1 - male_frac])

    # Smoker status — only S and NS (no UNKNOWN, to ensure mortality table compatibility)
    smoker_frac = smoker_pct / 100
    smokers = rng.choice(["NS", "S"], size=n, p=[1 - smoker_frac, smoker_frac])

    # Underwriting class
    uw_classes = rng.choice(
        ["PREF_PLUS", "PREFERRED", "STANDARD", "SUBSTANDARD"],
        size=n,
        p=[0.15, 0.35, 0.40, 0.10],
    )

    # Face amounts (lognormal: median at face_median, significant spread)
    face_amounts = np.exp(rng.normal(np.log(face_median), 0.8, n)).astype(int)
    face_amounts = np.clip(face_amounts, 100_000, 5_000_000)
    # Round to nearest $50k
    face_amounts = (face_amounts / 50_000).round() * 50_000

    # --- Compute mortality-calibrated premiums ---
    from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
    from polaris_re.core.policy import Sex, SmokerStatus

    table_source = MortalityTableSource(mortality_table_source)
    mort_data_dir = (
        Path(data_dir)
        if data_dir
        else Path(os.environ.get("POLARIS_DATA_DIR", "data")) / "mortality_tables"
    )
    mortality_table = MortalityTable.load(source=table_source, data_dir=mort_data_dir)

    # Omega for WL premium averaging (cap at table max age)
    omega = min(120, mortality_table.max_age)

    annual_premiums = np.zeros(n, dtype=np.float64)
    for i in range(n):
        age = int(issue_ages[i])
        sex_enum = Sex.MALE if sexes[i] == "M" else Sex.FEMALE
        smoker_enum = SmokerStatus.SMOKER if smokers[i] == "S" else SmokerStatus.NON_SMOKER

        # TERM: average q_x over [issue_age, issue_age + term)
        # WL:   average q_x over [issue_age, omega) — produces higher premiums
        term = int(policy_terms_int[i]) if is_term[i] else max(omega - age, 1)

        ages_over_term = np.arange(
            age, min(age + term, mortality_table.max_age + 1), dtype=np.int32
        )
        # Use ultimate durations (duration >> select period) for conservative pricing
        durations_ult = np.full_like(ages_over_term, mortality_table.select_period_years * 12 + 12)

        qx_monthly_vec = mortality_table.get_qx_vector(
            ages_over_term, sex_enum, smoker_enum, durations_ult
        )
        # get_qx_vector returns monthly rates — convert back to annual
        qx_annual = 1.0 - (1.0 - qx_monthly_vec) ** 12

        avg_annual_qx = float(qx_annual.mean())
        annual_premiums[i] = (face_amounts[i] * avg_annual_qx) / target_loss_ratio

    # Issue dates (back-calculate from duration)
    issue_dates = [
        (valuation_date - timedelta(days=int(dur * 30.44))).replace(day=1) for dur in durations
    ]

    # Build output columns — WL policies have None for policy_term
    policy_term_col: list[int | None] = [
        int(policy_terms_int[i]) if is_term[i] else None for i in range(n)
    ]

    df = pl.DataFrame(
        {
            "policy_id": [f"SYN_{i:06d}" for i in range(n)],
            "issue_age": issue_ages.tolist(),
            "attained_age": attained_ages.tolist(),
            "sex": sexes.tolist(),
            "smoker_status": smokers.tolist(),
            "underwriting_class": uw_classes.tolist(),
            "face_amount": face_amounts.tolist(),
            "annual_premium": annual_premiums.round(2).tolist(),
            "product_type": product_types.tolist(),
            "policy_term": policy_term_col,
            "duration_inforce": durations.tolist(),
            "reinsurance_cession_pct": [0.50] * n,
            "issue_date": [d.isoformat() for d in issue_dates],
            "valuation_date": [valuation_date.isoformat()] * n,
        }
    )

    return df


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a synthetic inforce block CSV for Polaris RE testing."
    )
    parser.add_argument(
        "--n-policies", type=int, default=1000, help="Number of policies to generate"
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/synthetic_block.csv"),
        help="Output CSV file path",
    )
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
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Generating {args.n_policies:,} synthetic policies (seed={args.seed})...")
    df = generate_synthetic_block(
        n_policies=args.n_policies,
        seed=args.seed,
        mortality_table_source=args.mortality_source,
        target_loss_ratio=args.target_loss_ratio,
        data_dir=args.data_dir,
    )
    df.write_csv(args.output)

    print(f"Written to {args.output}")
    print("\nSummary:")
    print(f"  Total face amount: ${df['face_amount'].sum():,.0f}")
    print(f"  Mean age: {df['attained_age'].mean():.1f}")
    print(f"  Sex split: {df.filter(pl.col('sex') == 'M').height / len(df):.0%} male")
    print(
        f"  Smoker split: {df.filter(pl.col('smoker_status') == 'S').height / len(df):.0%} smoker"
    )


if __name__ == "__main__":
    main()
