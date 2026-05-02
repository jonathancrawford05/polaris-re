"""Upload helpers for the YRT rate table dashboard flow (ADR-055).

The CLI / API path constructs ``YRTRateTable`` via ``YRTRateTable.load(...)``
which reads a directory of per-cohort CSV files. The Streamlit dashboard
cannot accept a directory through ``st.file_uploader`` — it accepts one or
more uploaded files instead — so we provide a parallel construction path
that consumes a list of ``(filename, content_bytes)`` tuples.

ADR-055 picks the **multi-file** upload UX (option b in the
``CONTINUATION_yrt_rate_table.md`` plan): users upload 1-4 CSVs whose
filenames carry the ``_{sex}_{smoker}.csv`` suffix used by the on-disk
``YRTRateTable.load`` convention (ADR-052). The schema inside each CSV is
unchanged — ``age,dur_1,...,dur_N,ultimate`` — so the same fixtures that
back the CLI work on the dashboard with no conversion.

This module exposes two helpers:

* ``parse_yrt_rate_filename(filename)`` — extract the ``(Sex, SmokerStatus)``
  cohort key from a filename suffix. Used by tests and the dashboard upload
  handler. Raises ``PolarisValidationError`` on unrecognised names so the
  user sees a clear message rather than a silent skip.
* ``parse_uploaded_yrt_rate_table(uploads, ...)`` — full multi-file packer
  that returns a validated ``YRTRateTable``.

CSV-loaded tables (whether from disk or upload) carry no ``solved_mask``
because every cell is authoritative (ADR-054). Renderers therefore fall
back to the pre-ADR-054 layout for uploaded data.
"""

from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.policy import Sex, SmokerStatus
from polaris_re.reinsurance.yrt_rate_table import YRTRateTable, YRTRateTableArray
from polaris_re.utils.table_io import load_yrt_rate_csv_from_buffer

__all__ = [
    "find_uncovered_cohorts",
    "parse_uploaded_yrt_rate_table",
    "parse_yrt_rate_filename",
]


_SEX_TOKENS: dict[str, Sex] = {"male": Sex.MALE, "female": Sex.FEMALE}
_SMOKER_TOKENS: dict[str, SmokerStatus] = {
    "smoker": SmokerStatus.SMOKER,
    "ns": SmokerStatus.NON_SMOKER,
    "unknown": SmokerStatus.UNKNOWN,
}


def parse_yrt_rate_filename(filename: str) -> tuple[Sex, SmokerStatus]:
    """Extract the ``(sex, smoker)`` cohort key from a YRT rate CSV filename.

    Mirrors the on-disk convention used by ``YRTRateTable.load`` — the
    filename must end with ``_{sex}_{smoker}.csv`` where ``sex`` is one of
    ``male`` / ``female`` and ``smoker`` is one of ``smoker`` / ``ns`` /
    ``unknown``. The case is normalised to lower; any directory components
    in the path are stripped before parsing.

    Examples:
        >>> parse_yrt_rate_filename("synthetic_male_ns.csv")
        (<Sex.MALE: 'M'>, <SmokerStatus.NON_SMOKER: 'NS'>)
        >>> parse_yrt_rate_filename("yrt_FEMALE_Smoker.CSV")
        (<Sex.FEMALE: 'F'>, <SmokerStatus.SMOKER: 'S'>)

    Raises:
        PolarisValidationError: filename does not match the expected
            ``..._{sex}_{smoker}.csv`` convention.
    """
    name = filename.replace("\\", "/").rsplit("/", maxsplit=1)[-1].lower()
    if not name.endswith(".csv"):
        raise PolarisValidationError(f"YRT rate upload {filename!r} must be a .csv file.")
    stem = name[:-4]
    parts = stem.split("_")
    if len(parts) < 3:
        raise PolarisValidationError(
            f"YRT rate upload {filename!r} must end with "
            "'_{sex}_{smoker}.csv' (e.g. 'mytable_male_ns.csv')."
        )
    smoker_token = parts[-1]
    sex_token = parts[-2]
    if sex_token not in _SEX_TOKENS or smoker_token not in _SMOKER_TOKENS:
        raise PolarisValidationError(
            f"YRT rate upload {filename!r}: cannot extract (sex, smoker) "
            f"from suffix '_{sex_token}_{smoker_token}'. "
            f"Expected sex in {sorted(_SEX_TOKENS)} and "
            f"smoker in {sorted(_SMOKER_TOKENS)}."
        )
    return _SEX_TOKENS[sex_token], _SMOKER_TOKENS[smoker_token]


def parse_uploaded_yrt_rate_table(
    uploads: list[tuple[str, bytes]],
    table_name: str,
    select_period: int,
    min_age: int | None = None,
    max_age: int | None = None,
) -> YRTRateTable:
    """Pack a multi-file upload into a validated ``YRTRateTable``.

    The dashboard upload flow (ADR-055) hands this helper a list of
    ``(filename, content_bytes)`` tuples — typically two (smoker-aggregate)
    or four (smoker-distinct), one per (sex, smoker) cohort. Filenames are
    parsed via ``parse_yrt_rate_filename`` so the on-disk convention
    (ADR-052) and the upload UX are interchangeable.

    Args:
        uploads:        ``[(filename, content), ...]``. At least one entry.
                        Duplicate cohort keys (e.g. two ``_male_ns.csv``
                        uploads) raise ``PolarisValidationError``.
        table_name:     Human-readable identifier recorded on the table.
        select_period:  Number of select-period columns in each CSV.
        min_age:        Optional shared minimum age. Auto-detected if None.
        max_age:        Optional shared maximum age. Auto-detected if None.

    Returns:
        A validated ``YRTRateTable`` with no ``solved_mask`` on any
        underlying array (uploaded data is always authoritative,
        per ADR-054).

    Raises:
        PolarisValidationError: empty uploads, unrecognised filename,
            duplicate cohort, or any per-CSV validation failure.

    Caller responsibility — inforce coverage check:
        Successful construction does NOT guarantee that every
        ``(sex, smoker)`` cohort present in a downstream
        ``InforceBlock`` is resolvable against the table. The
        dashboard uploader cross-checks the loaded table against
        ``st.session_state["inforce_block"]`` via
        ``find_uncovered_cohorts`` and surfaces a UX warning before
        the user clicks "Save All Assumptions"; CLI / API / scripted
        callers should perform the equivalent check before invoking
        ``YRTTreaty.apply()``, otherwise treaty application raises
        ``PolarisValidationError`` from inside the per-cohort lookup
        loop with no actionable context.
    """
    if not uploads:
        raise PolarisValidationError(
            "parse_uploaded_yrt_rate_table requires at least one uploaded file."
        )

    arrays: dict[tuple[Sex, SmokerStatus], YRTRateTableArray] = {}
    for filename, content in uploads:
        sex, smoker = parse_yrt_rate_filename(filename)
        if (sex, smoker) in arrays:
            raise PolarisValidationError(
                f"Duplicate YRT rate cohort uploaded: sex={sex.value}, "
                f"smoker={smoker.value} appears in more than one filename "
                f"(latest: {filename!r})."
            )
        arrays[(sex, smoker)] = load_yrt_rate_csv_from_buffer(
            content=content,
            source_name=filename,
            select_period=select_period,
            min_age=min_age,
            max_age=max_age,
        )

    return YRTRateTable.from_arrays(table_name=table_name, arrays=arrays)


def find_uncovered_cohorts(
    table: YRTRateTable,
    inforce: object,
) -> list[str]:
    """Return inforce cohort keys that the YRT rate table cannot resolve.

    Cross-checks every distinct ``(sex, smoker)`` combination present in
    the inforce block against ``YRTRateTable._resolve_key`` (which
    handles the smoker → UNKNOWN aggregate fallback). A missing cohort
    means ``YRTTreaty.apply()`` would raise ``PolarisValidationError``
    deep inside the per-cohort lookup loop at pricing time — surfacing
    the gap up-front lets callers (dashboard uploader, CLI smoke
    checks, API request handlers) present an actionable message.

    Args:
        table:    The candidate ``YRTRateTable`` (typically just-loaded
                  from a multi-file upload).
        inforce:  An ``InforceBlock`` whose ``policies`` list will be
                  iterated for ``(sex, smoker_status)`` pairs. Typed as
                  ``object`` to avoid a hard ``polaris_re.core.inforce``
                  import from this utility module — the call site
                  already owns that dependency.

    Returns:
        Sorted list of distinct ``"{sex}_{smoker}"`` keys present in
        ``inforce`` but NOT resolvable by ``table``. Empty list when
        the table covers every cohort the block needs (the happy path
        the caller can treat as "OK to price").
    """
    policies = getattr(inforce, "policies", None)
    if not policies:
        return []
    seen: set[tuple[Sex, SmokerStatus]] = set()
    missing: set[str] = set()
    for policy in policies:
        sex = policy.sex
        smoker = policy.smoker_status
        if (sex, smoker) in seen:
            continue
        seen.add((sex, smoker))
        try:
            table._resolve_key(sex, smoker)
        except PolarisValidationError:
            missing.add(f"{sex.value}_{smoker.value}")
    return sorted(missing)
