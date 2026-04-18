"""Generate golden output baselines.

Run this script when the golden inputs or the projection engine change.
Outputs are written to tests/qa/golden_outputs/ and should be committed.

Usage:
    uv run python tests/qa/generate_golden.py
    uv run python tests/qa/generate_golden.py --flat-only  # CI mode
"""

import argparse
import json
from datetime import date
from pathlib import Path

from polaris_re.analytics.profit_test import ProfitTester
from polaris_re.core.pipeline import (
    DealConfig,
    LapseConfig,
    MortalityConfig,
    PipelineInputs,
    build_pipeline,
    build_treaty,
    ceded_to_reinsurer_view,
    derive_yrt_rate,
    iter_cohorts,
    load_inforce,
)
from polaris_re.products.dispatch import get_product_engine

GOLDEN_CSV = Path("data/qa/golden_inforce.csv")
OUTPUT_DIR = Path("tests/qa/golden_outputs")


def run_and_save(inputs: PipelineInputs, name: str) -> None:
    """Run pricing pipeline and save golden output."""
    inforce = load_inforce(csv_path=GOLDEN_CSV)
    inf, assumptions, config = build_pipeline(inforce, inputs)
    cohorts = iter_cohorts(inf)
    results = {}

    for product_type, cohort_inforce in cohorts:
        gross = get_product_engine(
            inforce=cohort_inforce, assumptions=assumptions, config=config
        ).project()
        face_amount = cohort_inforce.total_face_amount()
        yrt_rate = derive_yrt_rate(gross, face_amount, inputs.deal.yrt_loading)
        treaty = build_treaty(
            treaty_type=inputs.deal.treaty_type,
            cession_pct=inputs.deal.cession_pct,
            face_amount=face_amount,
            yrt_rate_per_1000=yrt_rate,
        )
        if treaty is not None:
            use_pc = inputs.deal.use_policy_cession
            inf_arg = cohort_inforce if use_pc else None
            net, ceded = treaty.apply(gross, inforce=inf_arg)
        else:
            net, ceded = gross, None

        cedant = ProfitTester(cashflows=net, hurdle_rate=inputs.deal.hurdle_rate).run()
        reinsurer = None
        if ceded is not None:
            reinsurer = ProfitTester(
                cashflows=ceded_to_reinsurer_view(ceded),
                hurdle_rate=inputs.deal.hurdle_rate,
            ).run()

        results[product_type.value] = {
            "n_policies": cohort_inforce.n_policies,
            "face_amount": face_amount,
            "cedant_pv_profits": cedant.pv_profits,
            "cedant_profit_margin": cedant.profit_margin,
            "cedant_irr": cedant.irr,
            "cedant_breakeven": cedant.breakeven_year,
            "reinsurer_pv_profits": reinsurer.pv_profits if reinsurer else None,
            "reinsurer_profit_margin": reinsurer.profit_margin if reinsurer else None,
            "gross_total_premiums": float(gross.gross_premiums.sum()),
            "gross_total_claims": float(gross.death_claims.sum()),
            "projection_months": gross.projection_months,
        }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{name}.json"
    path.write_text(json.dumps(results, indent=2, default=str))
    print(f"OK {name}: {len(results)} cohorts -> {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--flat-only",
        action="store_true",
        help="Only generate flat-mortality baseline (no SOA tables)",
    )
    args = parser.parse_args()

    val_date = date(2026, 4, 1)

    # Always generate the flat baseline
    flat_inputs = PipelineInputs(
        mortality=MortalityConfig(source="flat", flat_qx=0.003),
        lapse=LapseConfig(),
        deal=DealConfig(
            treaty_type="YRT",
            cession_pct=0.90,
            yrt_loading=0.10,
            discount_rate=0.06,
            hurdle_rate=0.10,
            projection_years=20,
            valuation_date=val_date,
        ),
    )
    run_and_save(flat_inputs, "golden_flat")

    if not args.flat_only:
        yrt_inputs = PipelineInputs(
            mortality=MortalityConfig(source="SOA_VBT_2015"),
            lapse=LapseConfig(),
            deal=DealConfig(
                treaty_type="YRT",
                cession_pct=0.90,
                yrt_loading=0.10,
                discount_rate=0.06,
                hurdle_rate=0.10,
                projection_years=20,
                valuation_date=val_date,
            ),
        )
        run_and_save(yrt_inputs, "golden_yrt")

    print("\nDone. Commit the files in tests/qa/golden_outputs/.")


if __name__ == "__main__":
    main()
