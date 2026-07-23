"""
experience_loaders.py — fetch-and-cache loaders for public mortality-experience
data, mapping each source into the canonical grouped-cell contract consumed by
the experience GAM (see :mod:`polaris_re.analytics.experience_gam`).

Two public sources are supported (PLAN_experience_gam "Data Sources & Strategy"):

- **Human Mortality Database (HMD, mortality.org)** — free population Deaths and
  Exposures published as age x calendar-year matrices by sex, the exact
  ``(attained_age, calendar_year)`` Lexis structure ``te(age, calendar_year)``
  consumes. The primary *real-data* engineering/regression fixture for the tensor
  MI surface. :func:`load_hmd` joins a Deaths_1x1 and an Exposures_1x1 file into
  canonical cells.
- **SOA ILEC** — the insured Individual Life Experience grouped exposed-and-deaths
  flat file, carrying all three Lexis axes plus gender / smoker / plan / band /
  preferred class with both policy- and amount-exposure. The insured *validation*
  source (Slice 4c-2). :func:`load_ilec` maps and aggregates it into canonical
  cells.

**Loaders, not data (Design Anchor 6 / the #61/#66 trap).** No large or licensed
data file ships in the repo, the Docker image, or CI. The parsers
(:func:`parse_hmd_1x1`, :func:`load_hmd`, :func:`load_ilec`) take a *local cached
path* and return the canonical grouped-cell frame — hermetic and unit-tested on
small synthetic fixtures. The network fetch (:func:`fetch_hmd`) is a thin,
dependency-injected helper: it downloads to a cache directory and is never
exercised in CI (the ``downloader`` is injectable so tests stub the transport).

The canonical grouped-cell columns produced here (a subset of
:data:`polaris_re.analytics.experience_gam.CANONICAL_KEY_COLUMNS` plus the measure
pairs) feed :func:`~polaris_re.analytics.experience_gam.attach_base_rate` and the
tensor MI models directly. ``sex``/``smoker`` are emitted as the Polaris enum
*values* (``"M"``/``"F"``, ``"S"``/``"NS"``/``"U"``) so downstream base-rate
lookups resolve without re-mapping.
"""

import os
from collections.abc import Callable
from pathlib import Path

import polars as pl

from polaris_re.analytics.experience_gam import (
    AMOUNT_MEASURES,
    CANONICAL_KEY_COLUMNS,
    COUNT_MEASURES,
)
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError
from polaris_re.core.policy import Sex, SmokerStatus

__all__ = [
    "HMD_1X1_KINDS",
    "HMD_BASE_URL",
    "HMD_SEX_LABELS",
    "ILEC_COLUMN_MAP",
    "ILEC_SEX_LABELS",
    "ILEC_SMOKER_LABELS",
    "default_experience_cache_dir",
    "fetch_hmd",
    "hmd_1x1_url",
    "load_hmd",
    "load_ilec",
    "parse_hmd_1x1",
]


# --- HMD (Human Mortality Database) --------------------------------------------

HMD_BASE_URL = "https://www.mortality.org/File/GetDocument/hmd.v6"
"""Base of the HMD authenticated file tree. A 1x1 file for a country lives at
``{HMD_BASE_URL}/{country}/STATS/{kind}_1x1.txt`` (auth required — see
:func:`fetch_hmd`)."""

HMD_1X1_KINDS: dict[str, str] = {
    "deaths": "Deaths",
    "exposures": "Exposures",
}
"""Map from the loader's measure keyword to the HMD 1x1 file stem."""

HMD_SEX_LABELS: dict[str, str] = {
    "Female": Sex.FEMALE.value,
    "Male": Sex.MALE.value,
}
"""HMD wide-column header → canonical ``sex`` code. ``Total`` is intentionally
excluded (it is the sum, not a modelled cell)."""

# The open age interval "110+" is a half-open group, not a single-age cell; its
# integer age used when it is *kept* (drop_open_age=False).
_HMD_OPEN_AGE = 110


def default_experience_cache_dir() -> Path:
    """Resolve the on-disk cache for fetched experience files.

    ``$POLARIS_EXPERIENCE_CACHE_DIR`` wins; else ``$POLARIS_DATA_DIR/experience_cache``;
    else ``./data/experience_cache``. This is a *cache* of fetched public/licensed
    files — it is deliberately kept out of the Docker image and CI (loaders, not
    data).
    """
    override = os.environ.get("POLARIS_EXPERIENCE_CACHE_DIR")
    if override:
        return Path(override)
    data_dir = os.environ.get("POLARIS_DATA_DIR")
    root = Path(data_dir) if data_dir else Path("data")
    return root / "experience_cache"


def hmd_1x1_url(country: str, kind: str) -> str:
    """Build the HMD authenticated URL for a country's ``{kind}_1x1.txt`` file.

    Args:
        country: HMD country code (e.g. ``"USA"``, ``"CAN"``, ``"FRATNP"``).
        kind:    ``"deaths"`` or ``"exposures"`` (see :data:`HMD_1X1_KINDS`).

    Raises:
        PolarisValidationError: If ``kind`` is not a recognised 1x1 kind.
    """
    if kind not in HMD_1X1_KINDS:
        raise PolarisValidationError(
            f"Unknown HMD 1x1 kind {kind!r}; expected one of {sorted(HMD_1X1_KINDS)}."
        )
    stem = HMD_1X1_KINDS[kind]
    return f"{HMD_BASE_URL}/{country}/STATS/{stem}_1x1.txt"


def parse_hmd_1x1(path: str | Path, *, value_name: str) -> pl.DataFrame:
    """Parse a single HMD 1x1 text file into a long-format frame.

    HMD 1x1 files are whitespace-delimited with a two-line title, a
    ``Year Age Female Male Total`` header, then one row per (year, age). Ages run
    ``0..109`` plus the open ``110+`` group; missing values are ``.``.

    Args:
        path:       Path to a local ``Deaths_1x1.txt`` / ``Exposures_1x1.txt``.
        value_name: Output column name for the measure (e.g. ``"death_count"``).

    Returns:
        Long-format frame with columns ``calendar_year`` (Int32), ``attained_age``
        (Int32, ``110`` for the open group), ``sex`` (canonical ``"M"``/``"F"``),
        and ``value_name`` (Float64). ``Total`` and ``.``-valued rows are dropped.

    Raises:
        PolarisValidationError: If the file is missing or has no recognisable
            ``Year Age ...`` header.
    """
    path = Path(path)
    if not path.exists():
        raise PolarisValidationError(f"HMD 1x1 file not found: {path}")

    lines = path.read_text().splitlines()
    header_idx = _find_hmd_header(lines)
    header = lines[header_idx].split()
    # header is: Year Age Female Male Total  (sex columns after Year, Age)
    sex_cols = header[2:]

    years: list[int] = []
    ages: list[int] = []
    sexes: list[str] = []
    values: list[float] = []
    for raw in lines[header_idx + 1 :]:
        fields = raw.split()
        if len(fields) != len(header):
            # blank line or a malformed trailer — skip defensively.
            continue
        year = int(fields[0])
        age = _parse_hmd_age(fields[1])
        for col_label, cell in zip(sex_cols, fields[2:], strict=True):
            canonical_sex = HMD_SEX_LABELS.get(col_label)
            if canonical_sex is None:
                continue  # Total (or any non-sex column)
            if cell == ".":
                continue  # HMD missing marker
            years.append(year)
            ages.append(age)
            sexes.append(canonical_sex)
            values.append(float(cell))

    if not years:
        raise PolarisValidationError(f"HMD 1x1 file {path} yielded no parseable data rows.")

    return pl.DataFrame(
        {
            "calendar_year": pl.Series(years, dtype=pl.Int32),
            "attained_age": pl.Series(ages, dtype=pl.Int32),
            "sex": pl.Series(sexes, dtype=pl.Utf8),
            value_name: pl.Series(values, dtype=pl.Float64),
        }
    )


def _find_hmd_header(lines: list[str]) -> int:
    """Index of the ``Year Age ...`` header line in an HMD 1x1 file."""
    for i, raw in enumerate(lines):
        fields = raw.split()
        if len(fields) >= 3 and fields[0] == "Year" and fields[1] == "Age":
            return i
    raise PolarisValidationError(
        "HMD 1x1 file has no 'Year Age ...' header line — not a recognised 1x1 file."
    )


def _parse_hmd_age(token: str) -> int:
    """Parse an HMD age token (``"0".."109"`` or the open ``"110+"``)."""
    if token.endswith("+"):
        return int(token[:-1])
    return int(token)


def load_hmd(
    deaths_path: str | Path,
    exposures_path: str | Path,
    *,
    min_year: int | None = None,
    max_year: int | None = None,
    min_age: int | None = None,
    max_age: int | None = None,
    sexes: tuple[str, ...] | None = None,
    drop_open_age: bool = True,
) -> pl.DataFrame:
    """Load an HMD country into the canonical grouped-cell contract.

    Joins a Deaths_1x1 and an Exposures_1x1 file on ``(calendar_year,
    attained_age, sex)`` and emits ``central_exposure`` / ``death_count`` cells —
    the by-count population experience basis. Population data has no select/duration
    or insured factors, so the result carries only ``attained_age``,
    ``calendar_year``, ``sex`` and the by-count measure pair: exactly what the
    tensor MI surface (``te(attained_age, calendar_year)``) consumes.

    Args:
        deaths_path:    Local ``Deaths_1x1.txt``.
        exposures_path: Local ``Exposures_1x1.txt``.
        min_year/max_year: Inclusive calendar-year window (``None`` = unbounded).
        min_age/max_age:   Inclusive attained-age window (``None`` = unbounded).
        sexes:          Canonical sex codes to keep (e.g. ``("M",)``); ``None`` = both.
        drop_open_age:  Drop the open ``110+`` group (default True — it is not a
                        single-age cell).

    Returns:
        Canonical cells with ``attained_age`` (Int32), ``calendar_year`` (Int32),
        ``sex`` (Utf8), ``central_exposure`` (Float64), ``death_count`` (Float64),
        sorted by ``(calendar_year, attained_age, sex)`` for deterministic output.

    Raises:
        PolarisValidationError: If the join yields no overlapping cells, or a
            requested ``sexes`` code is not a valid Polaris ``Sex`` value.
    """
    if sexes is not None:
        valid = {s.value for s in Sex}
        bad = set(sexes) - valid
        if bad:
            raise PolarisValidationError(
                f"Unknown sex code(s) {sorted(bad)}; expected a subset of {sorted(valid)}."
            )

    deaths = parse_hmd_1x1(deaths_path, value_name=COUNT_MEASURES[1])  # death_count
    exposures = parse_hmd_1x1(exposures_path, value_name=COUNT_MEASURES[0])  # central_exposure

    cells = deaths.join(exposures, on=["calendar_year", "attained_age", "sex"], how="inner")
    if cells.height == 0:
        raise PolarisValidationError(
            "HMD Deaths and Exposures files share no (year, age, sex) cells — "
            "check they are the same country and 1x1 resolution."
        )

    predicates: list[pl.Expr] = []
    if drop_open_age:
        predicates.append(pl.col("attained_age") < _HMD_OPEN_AGE)
    if min_year is not None:
        predicates.append(pl.col("calendar_year") >= min_year)
    if max_year is not None:
        predicates.append(pl.col("calendar_year") <= max_year)
    if min_age is not None:
        predicates.append(pl.col("attained_age") >= min_age)
    if max_age is not None:
        predicates.append(pl.col("attained_age") <= max_age)
    if sexes is not None:
        predicates.append(pl.col("sex").is_in(list(sexes)))
    for pred in predicates:
        cells = cells.filter(pred)

    if cells.height == 0:
        raise PolarisValidationError(
            "HMD load yielded no cells after applying the year/age/sex filters."
        )

    return cells.select("attained_age", "calendar_year", "sex", *COUNT_MEASURES).sort(
        ["calendar_year", "attained_age", "sex"]
    )


# --- SOA ILEC ------------------------------------------------------------------

ILEC_COLUMN_MAP: dict[str, str] = {
    "Observation Year": "calendar_year",
    "Attained Age": "attained_age",
    "Issue Age": "issue_age",
    "Duration": "duration",  # 1-based policy year → duration_months = (d-1)*12
    "Gender": "sex",
    "Smoker Status": "smoker",
    "Insurance Plan": "product",
    "Face Amount Band": "band",
    "Preferred Class": "uw_class",
    "Distribution Channel": "channel",
    "Policies Exposed": COUNT_MEASURES[0],  # central_exposure
    "Death Count": COUNT_MEASURES[1],  # death_count
    "Amount Exposed": AMOUNT_MEASURES[0],  # amount_exposed
    "Death Claim Amount": AMOUNT_MEASURES[1],  # death_amount
}
"""Default SOA-ILEC source-column → canonical-column map. Override per-vintage via
``load_ilec(column_map=...)`` — ILEC header spellings differ between releases."""

ILEC_SEX_LABELS: dict[str, str] = {
    "MALE": Sex.MALE.value,
    "M": Sex.MALE.value,
    "FEMALE": Sex.FEMALE.value,
    "F": Sex.FEMALE.value,
}
"""ILEC gender label (upper-cased) → canonical ``sex`` code."""

ILEC_SMOKER_LABELS: dict[str, str] = {
    "NONSMOKER": SmokerStatus.NON_SMOKER.value,
    "NON-SMOKER": SmokerStatus.NON_SMOKER.value,
    "NS": SmokerStatus.NON_SMOKER.value,
    "SMOKER": SmokerStatus.SMOKER.value,
    "S": SmokerStatus.SMOKER.value,
    "UNISMOKE": SmokerStatus.UNKNOWN.value,
    "UNKNOWN": SmokerStatus.UNKNOWN.value,
    "U": SmokerStatus.UNKNOWN.value,
}
"""ILEC smoker label (upper-cased) → canonical ``smoker`` code."""

# Measure columns selected per basis.
_ILEC_BASIS_MEASURES: dict[str, tuple[str, ...]] = {
    "count": COUNT_MEASURES,
    "amount": AMOUNT_MEASURES,
    "both": (*COUNT_MEASURES, *AMOUNT_MEASURES),
}


def _canonicalise_label(
    frame: pl.DataFrame,
    column: str,
    mapping: dict[str, str],
    label_kind: str,
) -> pl.DataFrame:
    """Strip/upper-case ``column`` and map it to canonical codes, raising on any
    unmapped label.

    Polars ``replace`` passes an unrecognised value through unchanged, which would
    silently flow a non-canonical ``sex``/``smoker`` value downstream. This guard
    checks the distinct (non-null) labels against ``mapping`` first and raises a
    clear :class:`PolarisValidationError` naming the offenders — consistent with
    :func:`load_hmd`'s explicit sex-code guard.
    """
    normalised = frame.get_column(column).cast(pl.Utf8).str.strip_chars().str.to_uppercase()
    present = {v for v in normalised.unique().to_list() if v is not None}
    unmapped = sorted(present - set(mapping))
    if unmapped:
        raise PolarisValidationError(
            f"ILEC {label_kind} column has unmapped label(s) {unmapped}; "
            f"expected a subset of {sorted(mapping)}. Supply a canonicalised "
            f"column or extend the label map."
        )
    return frame.with_columns(normalised.replace(mapping).alias(column))


def load_ilec(
    path: str | Path,
    *,
    basis: str = "count",
    column_map: dict[str, str] | None = None,
    aggregate: bool = True,
) -> pl.DataFrame:
    """Load a SOA-ILEC grouped flat file into the canonical grouped-cell contract.

    Renames source columns via ``column_map`` (default :data:`ILEC_COLUMN_MAP`),
    maps gender/smoker labels to canonical codes, converts the 1-based policy-year
    ``Duration`` to ``duration_months`` (``(duration-1)*12`` — duration 1 → months
    0..11, matching the select base-rate lookup), and — when ``aggregate`` — sums
    the measure pair over the canonical key columns (so a file finer than the
    canonical keys collapses to one row per covariate combination, per Anchor 7).

    Args:
        path:       Local ILEC flat file (CSV).
        basis:      ``"count"`` (policy-count), ``"amount"`` (face-weighted), or
                    ``"both"``. Selects the measure pair(s) carried through.
        column_map: Source→canonical rename map; defaults to :data:`ILEC_COLUMN_MAP`.
                    Only mapped columns present in the file are used.
        aggregate:  Group-and-sum over the present canonical key columns (default
                    True). Set False to keep the file's native row grain.

    Returns:
        Canonical cells: the present key columns (``attained_age``,
        ``calendar_year``, and any of the optional Lexis/factor keys) plus the
        selected measure column(s), sorted by the present keys.

    Raises:
        PolarisValidationError: If the file is missing, ``basis`` is unknown, or
            the required ``attained_age``/measure columns are absent after mapping.
    """
    path = Path(path)
    if not path.exists():
        raise PolarisValidationError(f"ILEC file not found: {path}")
    if basis not in _ILEC_BASIS_MEASURES:
        raise PolarisValidationError(
            f"Unknown ILEC basis {basis!r}; expected one of {sorted(_ILEC_BASIS_MEASURES)}."
        )

    cmap = column_map if column_map is not None else ILEC_COLUMN_MAP
    try:
        frame = pl.read_csv(path)
    except Exception as exc:
        raise PolarisComputationError(f"Failed to read ILEC CSV {path}: {exc}") from exc

    # Rename only the mapped columns that are present.
    rename = {src: dst for src, dst in cmap.items() if src in frame.columns}
    frame = frame.rename(rename)

    measures = _ILEC_BASIS_MEASURES[basis]
    missing_measures = [m for m in measures if m not in frame.columns]
    if missing_measures:
        raise PolarisValidationError(
            f"ILEC file is missing measure column(s) {missing_measures} for basis "
            f"{basis!r} after mapping. Present columns: {frame.columns}."
        )
    if "attained_age" not in frame.columns:
        raise PolarisValidationError(
            "ILEC file has no 'attained_age' column after mapping — supply a "
            "column_map that maps the source attained-age column."
        )

    # Canonicalise gender/smoker labels — fail loud on an unmapped label (mirrors
    # load_hmd's explicit sex-code guard) so a real vintage with an unrecognised
    # spelling surfaces here, not later as an opaque base-rate-lookup failure.
    if "sex" in frame.columns:
        frame = _canonicalise_label(frame, "sex", ILEC_SEX_LABELS, "gender")
    if "smoker" in frame.columns:
        frame = _canonicalise_label(frame, "smoker", ILEC_SMOKER_LABELS, "smoker")

    # 1-based policy-year duration → select duration in months.
    if "duration" in frame.columns:
        frame = frame.with_columns(
            (((pl.col("duration").cast(pl.Int32) - 1) * 12).clip(lower_bound=0))
            .cast(pl.Int32)
            .alias("duration_months")
        ).drop("duration")

    # Integer-cast the age/year keys.
    for int_col in ("attained_age", "issue_age", "calendar_year"):
        if int_col in frame.columns:
            frame = frame.with_columns(pl.col(int_col).cast(pl.Int32).alias(int_col))
    # Float64-cast the measures.
    frame = frame.with_columns([pl.col(m).cast(pl.Float64).alias(m) for m in measures])

    key_cols = [c for c in CANONICAL_KEY_COLUMNS if c in frame.columns]

    if aggregate:
        frame = frame.group_by(key_cols).agg([pl.col(m).sum().alias(m) for m in measures])

    return frame.select(*key_cols, *measures).sort(key_cols)


# --- Network fetch (dependency-injected; never exercised in CI) -----------------


def _urllib_downloader(url: str, dest: Path) -> None:  # pragma: no cover - network
    """Default HMD transport: stream ``url`` to ``dest`` via ``urllib``.

    Not exercised in CI (network + HMD account). Wrapped so :func:`fetch_hmd`
    surfaces a clean :class:`PolarisComputationError` on any transport failure.
    """
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response:
        dest.write_bytes(response.read())


def fetch_hmd(
    country: str,
    *,
    cache_dir: str | Path | None = None,
    downloader: Callable[[str, Path], None] | None = None,
    overwrite: bool = False,
) -> dict[str, Path]:
    """Fetch a country's HMD Deaths_1x1 and Exposures_1x1 into the cache.

    Loaders, not data: files land in :func:`default_experience_cache_dir` (kept
    out of the image + CI), never in the repo tree. The ``downloader`` transport
    is injectable so tests exercise the URL/cache-path logic without any network;
    the default (:func:`_urllib_downloader`) requires an HMD account/session on
    the caller's machine.

    Args:
        country:    HMD country code (e.g. ``"USA"``).
        cache_dir:  Override the cache root (default
                    :func:`default_experience_cache_dir`).
        downloader: ``(url, dest) -> None`` transport. Defaults to the urllib one.
        overwrite:  Re-download even if the cached file already exists.

    Returns:
        ``{"deaths": <path>, "exposures": <path>}`` — the cached local paths,
        ready to pass to :func:`load_hmd`.

    Raises:
        PolarisComputationError: If a download fails.
    """
    root = Path(cache_dir) if cache_dir is not None else default_experience_cache_dir()
    country_dir = root / "hmd" / country
    transport = downloader if downloader is not None else _urllib_downloader

    paths: dict[str, Path] = {}
    for kind, stem in HMD_1X1_KINDS.items():
        dest = country_dir / f"{stem}_1x1.txt"
        if overwrite or not dest.exists():
            url = hmd_1x1_url(country, kind)
            try:
                transport(url, dest)
            except Exception as exc:
                raise PolarisComputationError(
                    f"Failed to fetch HMD {kind} for {country} from {url}: {exc}"
                ) from exc
        paths[kind] = dest
    return paths
