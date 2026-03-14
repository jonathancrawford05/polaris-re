"""
Utility functions for Polaris RE.

Provides table I/O, age/date helpers, and interpolation utilities
used across the projection and assumption modules.
"""

from polaris_re.utils.date_utils import age_nearest_birthday, months_between, projection_date_index
from polaris_re.utils.interpolation import linear_interpolate_rates
from polaris_re.utils.table_io import load_mortality_csv

__all__ = [
    "age_nearest_birthday",
    "linear_interpolate_rates",
    "load_mortality_csv",
    "months_between",
    "projection_date_index",
]
