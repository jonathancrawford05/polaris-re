"""A SYNTHETIC ILEC-2012-19-shaped flat file for the trial tests. No licensed data."""

from pathlib import Path

import numpy as np
import polars as pl


def write_synthetic_ilec(
    path: Path,
    *,
    seed: int = 11,
    ages: range = range(30, 70),
    years: range = range(2014, 2017),
    sexes: tuple[str, ...] = ("Male",),
) -> Path:
    rng = np.random.default_rng(seed)
    rows = []
    for issue_age in ages:
        for duration in (1, 2, 3, 4, 6, 8, 11, 14, 17, 21, 24, 27):
            attained = issue_age + duration - 1
            for year in years:
                for sex in sexes:
                    for smoker in ("NS", "S", "U"):
                        for band in ("1-9999", "10000-24999", "25000+"):
                            expo = float(rng.uniform(5, 120))
                            q = np.exp(
                                -9.5
                                + 0.085 * attained
                                - 0.0009 * (attained - 50) ** 2
                                - 0.9 * np.exp(-duration / 4.0)
                                + 0.02 * np.sin(year / 1.7)
                                + 0.012 * (attained - 50) * np.exp(-duration / 5.0)
                            )
                            q *= 1.6 if smoker == "S" else 1.0
                            rows.append(
                                {
                                    "Observation_Year": year,
                                    "Attained_Age": attained,
                                    "Issue_Age": issue_age,
                                    "Duration": duration,
                                    "Sex": sex,
                                    "Smoker_Status": smoker,
                                    "Insurance_Plan": "Term",
                                    "Face_Amount_Band": band,
                                    "Preferred_Class": "NA",
                                    "Number_of_Pfd_Classes": "NA",
                                    "Policies_Exposed": expo,
                                    "Death_Count": int(rng.poisson(expo * q * 2.0)),
                                    "Amount_Exposed": expo * 50000.0,
                                    "Death_Claim_Amount": 0.0,
                                }
                            )
    pl.DataFrame(rows).write_csv(path, separator="\t")
    return path
