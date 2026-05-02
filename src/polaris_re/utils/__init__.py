"""
Utility functions for Polaris RE.

Provides table I/O, age/date helpers, and interpolation utilities
used across the projection and assumption modules.
"""

from polaris_re.utils.date_utils import age_nearest_birthday, months_between, projection_date_index
from polaris_re.utils.interpolation import linear_interpolate_rates
from polaris_re.utils.table_io import load_lapse_csv, load_mortality_csv

# NOTE: ``yrt_rate_table_io`` is intentionally NOT re-exported here. It
# imports ``YRTRateTable`` from the reinsurance package, which would
# trigger a circular import via ``utils.table_io`` if loaded as the very
# first ``polaris_re.utils`` symbol. Callers import it directly:
#   ``from polaris_re.utils.yrt_rate_table_io import parse_uploaded_yrt_rate_table``

__all__ = [
    "age_nearest_birthday",
    "linear_interpolate_rates",
    "load_lapse_csv",
    "load_mortality_csv",
    "months_between",
    "projection_date_index",
]
