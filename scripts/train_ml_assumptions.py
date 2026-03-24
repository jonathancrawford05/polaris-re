#!/usr/bin/env python3
"""
train_ml_assumptions.py — End-to-end ML assumption training script.

Loads normalised inforce CSV, engineers features, trains an XGBoost or
sklearn model for mortality/lapse prediction, reports feature importance
and A/E metrics, and saves the trained model via joblib.

Usage:
    python scripts/train_ml_assumptions.py --type mortality --input data/training_data.csv --output models/ml_mortality.joblib
    python scripts/train_ml_assumptions.py --type lapse --input data/training_data.csv --output models/ml_lapse.joblib
"""

import argparse
import sys
from pathlib import Path

import numpy as np

try:
    import polars as pl
    from rich.console import Console
    from rich.table import Table
except ImportError:
    print("polars and rich required. Run: uv sync")
    sys.exit(1)

console = Console()


def _generate_synthetic_training_data(
    n: int = 5000,
    target: str = "mortality",
    seed: int = 42,
) -> tuple[pl.DataFrame, np.ndarray]:
    """
    Generate synthetic training data for demonstration.

    Creates a DataFrame of policy features and corresponding target rates
    with a realistic relationship between features and rates.
    """
    rng = np.random.default_rng(seed)

    ages = rng.integers(20, 80, size=n)
    sexes = rng.choice(["M", "F"], size=n, p=[0.6, 0.4])
    smokers = rng.choice(["S", "NS"], size=n, p=[0.15, 0.85])
    durations = rng.integers(0, 360, size=n)
    face_amounts = np.exp(rng.normal(np.log(500_000), 0.8, n)).clip(100_000, 5_000_000)

    from polaris_re.utils.features import build_feature_matrix

    features = build_feature_matrix(
        ages=ages.astype(np.int32),
        sexes=sexes,
        smoker_statuses=smokers,
        durations_months=durations.astype(np.int32),
        face_amounts=face_amounts,
    )

    if target == "mortality":
        # Synthetic q_x: exponential in age, higher for smokers, lower for females
        base_qx = np.exp(-10.0 + 0.08 * ages) * (1 + 0.002 * rng.normal(0, 1, n))
        smoker_mult = np.where(smokers == "S", 2.0, 1.0)
        sex_mult = np.where(sexes == "F", 0.6, 1.0)
        y = np.clip(base_qx * smoker_mult * sex_mult, 0.0001, 0.5)
    else:
        # Synthetic lapse: higher in early durations, lower later
        dur_years = durations / 12
        base_lapse = 0.12 * np.exp(-0.15 * dur_years) + 0.025
        noise = 1 + 0.05 * rng.normal(0, 1, n)
        y = np.clip(base_lapse * noise, 0.001, 0.30)

    return features, y.astype(np.float64)


def main() -> None:
    """CLI entry point for ML assumption training."""
    parser = argparse.ArgumentParser(description="Train ML assumptions for Polaris RE.")
    parser.add_argument(
        "--type",
        choices=["mortality", "lapse"],
        default="mortality",
        help="Type of assumption to train.",
    )
    parser.add_argument("--input", type=Path, default=None, help="Training data CSV.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("models/ml_model.joblib"),
        help="Output model file.",
    )
    parser.add_argument(
        "--model", choices=["gradient_boosting", "xgboost"], default="gradient_boosting"
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument(
        "--n-synthetic", type=int, default=5000, help="Synthetic data size (demo mode)."
    )
    args = parser.parse_args()

    console.print("[bold]Polaris RE — ML Assumption Training[/bold]\n")

    # Generate or load training data
    if args.input is None:
        console.print(
            f"[yellow]No --input provided. Using synthetic training data (n={args.n_synthetic}).[/yellow]\n"
        )
        features, y = _generate_synthetic_training_data(
            n=args.n_synthetic, target=args.type, seed=args.seed
        )
    else:
        console.print(f"Loading training data: {args.input}")
        df = pl.read_csv(args.input)
        # Expect last column to be the target
        feature_cols = df.columns[:-1]
        target_col = df.columns[-1]
        features = df.select(feature_cols)
        y = df[target_col].to_numpy().astype(np.float64)

    console.print(f"Training {args.type} model ({args.model}) on {len(y)} samples...")

    if args.type == "mortality":
        from polaris_re.assumptions.ml_mortality import MLMortalityAssumption

        ml_model = MLMortalityAssumption.fit(
            features, y, model_type=args.model, n_estimators=100, random_state=args.seed
        )
    else:
        from polaris_re.assumptions.ml_lapse import MLLapseAssumption

        ml_model = MLLapseAssumption.fit(
            features, y, model_type=args.model, n_estimators=100, random_state=args.seed
        )

    # Feature importance
    if hasattr(ml_model.model, "feature_importances_"):
        imp = ml_model.model.feature_importances_  # type: ignore[union-attr]
        imp_table = Table(title="Feature Importance")
        imp_table.add_column("Feature")
        imp_table.add_column("Importance", justify="right")
        for name, importance in sorted(zip(ml_model.feature_names, imp), key=lambda x: -x[1]):
            imp_table.add_row(name, f"{importance:.4f}")
        console.print(imp_table)

    # A/E metric
    x_np = features.to_numpy().astype(np.float64)
    y_pred = np.clip(ml_model.model.predict(x_np), 0.0, 1.0)  # type: ignore[union-attr]
    ae_ratio = float(y.sum() / y_pred.sum()) if y_pred.sum() > 0 else float("inf")
    console.print(f"\nA/E ratio (actual/expected): {ae_ratio:.4f}")

    # Save
    args.output.parent.mkdir(parents=True, exist_ok=True)
    ml_model.save(args.output)
    console.print(f"\n[green]Model saved to {args.output}[/green]")


if __name__ == "__main__":
    main()
