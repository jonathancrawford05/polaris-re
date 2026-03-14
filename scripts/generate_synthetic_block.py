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
) -> pl.DataFrame:
    """
    Generate a synthetic inforce block with realistic distributions.

    Distributions are approximate representations of a typical North American
    individual term life portfolio. Not calibrated to any specific real portfolio.

    Age distribution: roughly normal around 45 with std 10, clipped [25, 70]
    Sex split: 60% male, 40% female
    Smoker split: 15% smoker, 85% non-smoker
    Face amount: lognormal centred on $500k
    Policy term: mix of 10/20/30 year (20% / 60% / 20%)
    Duration: uniform over [0, term_months - 1]
    """
    rng = np.random.default_rng(seed)
    n = n_policies

    # Ages (ANB)
    issue_ages = np.clip(rng.normal(40, 8, n).astype(int), 20, 65)

    # Duration in force (months) — uniform over policy's life, capped at remaining term
    policy_terms = rng.choice([10, 20, 30], size=n, p=[0.20, 0.60, 0.20])
    max_durations = (policy_terms * 12 - 1).astype(int)
    durations = np.array([rng.integers(0, max_dur + 1) for max_dur in max_durations])

    # Attained ages
    attained_ages = issue_ages + (durations // 12)

    # Sex
    sexes = rng.choice(["M", "F"], size=n, p=[0.60, 0.40])

    # Smoker status
    smokers = rng.choice(["NS", "S", "U"], size=n, p=[0.80, 0.15, 0.05])

    # Underwriting class
    uw_classes = rng.choice(
        ["PREF_PLUS", "PREFERRED", "STANDARD", "SUBSTANDARD"],
        size=n,
        p=[0.15, 0.35, 0.40, 0.10],
    )

    # Face amounts (lognormal: median $500k, significant spread)
    face_amounts = np.exp(rng.normal(np.log(500_000), 0.8, n)).astype(int)
    face_amounts = np.clip(face_amounts, 100_000, 5_000_000)
    # Round to nearest $50k
    face_amounts = (face_amounts / 50_000).round() * 50_000

    # Annual premiums (rough approximation: age-based rate per $1000)
    base_rate_per_1000 = 0.8 + issue_ages * 0.05  # illustrative
    smoker_multiplier = np.where(smokers == "S", 2.5, 1.0)
    annual_premiums = (face_amounts / 1000) * base_rate_per_1000 * smoker_multiplier

    # Issue dates (back-calculate from duration)
    issue_dates = [
        (valuation_date - timedelta(days=int(dur * 30.44))).replace(day=1)
        for dur in durations
    ]

    df = pl.DataFrame({
        "policy_id": [f"SYN_{i:06d}" for i in range(n)],
        "issue_age": issue_ages.tolist(),
        "attained_age": attained_ages.tolist(),
        "sex": sexes.tolist(),
        "smoker_status": smokers.tolist(),
        "underwriting_class": uw_classes.tolist(),
        "face_amount": face_amounts.tolist(),
        "annual_premium": annual_premiums.round(2).tolist(),
        "product_type": ["TERM"] * n,
        "policy_term": policy_terms.tolist(),
        "duration_inforce": durations.tolist(),
        "reinsurance_cession_pct": [0.50] * n,
        "issue_date": [d.isoformat() for d in issue_dates],
        "valuation_date": [valuation_date.isoformat()] * n,
    })

    return df


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a synthetic inforce block CSV for Polaris RE testing."
    )
    parser.add_argument("--n-policies", type=int, default=1000, help="Number of policies to generate")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument(
        "--output", type=Path,
        default=Path("data/synthetic_block.csv"),
        help="Output CSV file path",
    )
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Generating {args.n_policies:,} synthetic policies (seed={args.seed})...")
    df = generate_synthetic_block(n_policies=args.n_policies, seed=args.seed)
    df.write_csv(args.output)

    print(f"Written to {args.output}")
    print(f"\nSummary:")
    print(f"  Total face amount: ${df['face_amount'].sum():,.0f}")
    print(f"  Mean age: {df['attained_age'].mean():.1f}")
    print(f"  Sex split: {df.filter(pl.col('sex') == 'M').height / len(df):.0%} male")
    print(f"  Smoker split: {df.filter(pl.col('smoker_status') == 'S').height / len(df):.0%} smoker")


if __name__ == "__main__":
    main()
