"""Per-merge performance history log — creep detection over a committed series.

This module is the *long-baseline companion* to the same-job head-vs-main perf
gate (ADR-176, :mod:`polaris_re.analytics.perf_harness`). The head-vs-main gate
compares the current worktree against ``origin/main`` **in one CI job**, so it
catches a single PR that makes the engine structurally slower or start allocating
more. What it *structurally cannot* catch is **slow multi-month creep**: because
its baseline is always the moving ``main`` tip, a series of merges that each add a
fraction of a percent — every one of them individually under the per-PR alert
band — walks the engine steadily slower without any single comparison ever
firing. This module closes that gap by appending **one deterministic-first row
per merged commit** to a committed append-only log (``perf/history.jsonl``) and
running **creep detection over the whole series**: the earliest window versus the
most recent window.

**What creeps, and how it is judged.** The same maintainer design rule that
governs the head-vs-main gate (2026-07-12) governs this one: *deterministic /
noise-normalized metrics may gate or alert; raw wall-time only informs.* Across a
history series the situation is even starker than in one job — every row is
recorded on a potentially different CI machine, so absolute wall-time drifts with
the hardware, not only the code. Therefore:

- **``peak_mib`` creep is the gate-worthy signal.** The ``tracemalloc`` peak
  rounded to whole MiB is deterministic for a ``(code, input)`` pair and portable
  across machines (an extra ``N x T`` float64 array on the default block is
  ~6 MiB — well above the ±1 MiB rounding jitter). A sustained rise in the
  MiB-rounded peak across the series is a real, machine-independent allocation
  regression that accumulated below the per-PR radar.
- **Wall-time creep is advisory only.** A rising head/baseline wall-time ratio is
  surfaced as an informational alert (with the explicit cross-machine-noise
  caveat) and **never** contributes to the gate signal.
- **Config drift is advisory.** If the probe's *inputs* (``n_policies``,
  ``projection_months``, ``n_cells``) vary across the compared windows the series
  is not apples-to-apples; this is flagged so a spurious creep reading is not
  mistaken for a regression.

The row is a compact, deterministic-first projection of a
:class:`~polaris_re.analytics.perf_harness.PerfReport` plus the commit it was
recorded for. The commit date is taken from the commit itself (``git show -s
--format=%cI``), never ``date.today()`` (ADR-074) — the whole point of a
per-merge log is that a row is pinned to a commit, not to the wall clock.

Nothing here is on the pricing/import hot path — it is a sibling diagnostic to
:mod:`polaris_re.analytics.perf_harness`, which produces the reports this module
records. Seeding the log with historical commits (a one-off backfill) and wiring
an automatic per-merge CI append are separate follow-ups; this module supplies
the record + creep-detection capability those build on.
"""

from pathlib import Path
from statistics import median

from pydantic import Field

from polaris_re.analytics.perf_harness import PerfReport
from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.exceptions import PolarisValidationError

__all__ = [
    "CreepVerdict",
    "PerfHistoryRow",
    "ProbeCreep",
    "ProbeHistoryEntry",
    "append_history_row",
    "detect_creep",
    "load_history",
]


class ProbeHistoryEntry(PolarisBaseModel):
    """One hot-path's metrics inside a history row, deterministic fields first.

    Field order is deliberate — the exactly-deterministic block (counts +
    fingerprint) precedes the coarse ``peak_mib`` and the informational timing —
    so a serialized row reads gate-relevant metrics before wall-time, mirroring
    :meth:`PerfReport.to_perf_dict`.
    """

    probe: str = Field(description="Hot-path name (e.g. 'project').")
    n_policies: int = Field(gt=0, description="Block size projected (deterministic input).")
    projection_months: int = Field(
        gt=0, description="Projection horizon T in months (deterministic)."
    )
    n_cells: int = Field(gt=0, description="N x T array-cell count — work volume (deterministic).")
    output_fingerprint: str = Field(
        description="blake2b digest of the rounded core cash-flow arrays (deterministic tripwire)."
    )
    peak_mib: int = Field(
        ge=0, description="tracemalloc peak rounded to whole MiB. Coarse — the creep GATE signal."
    )
    best_of_k_seconds: float = Field(
        ge=0.0, description="Best-of-k wall-clock seconds. INFORMATIONAL — creep on it only alerts."
    )
    k: int = Field(gt=0, description="Number of timing samples behind best_of_k_seconds.")


class PerfHistoryRow(PolarisBaseModel):
    """One append-only history record: a perf probe pinned to a merged commit.

    A row is the compact, deterministic-first projection of a
    :class:`~polaris_re.analytics.perf_harness.PerfReport` for a single commit. It
    is serialized one-per-line into ``perf/history.jsonl`` (see
    :func:`append_history_row`) and the series is analysed by
    :func:`detect_creep`.
    """

    commit: str = Field(description="Git commit the probe was recorded for (sha, short or full).")
    commit_date: str = Field(
        description="ISO-8601 commit date, pinned to the commit (ADR-074) — never the wall clock."
    )
    engine_label: str = Field(description="Human label for the projected engine (e.g. 'TermLife').")
    projection_years: int = Field(gt=0, description="Projection horizon in years (config).")
    discount_rate: float = Field(description="Discount rate used for the timed projection.")
    n_policies: int = Field(gt=0, description="Fixed block size the probes ran on.")
    probes: list[ProbeHistoryEntry] = Field(description="One entry per timed hot path.")

    @classmethod
    def from_report(cls, report: PerfReport, *, commit: str, commit_date: str) -> "PerfHistoryRow":
        """Project a :class:`PerfReport` plus its commit metadata into a history row.

        Args:
            report: The perf report to record (typically ``run_perf_probe(...)``).
            commit: The git sha the report was measured on.
            commit_date: The commit's ISO-8601 date (``git show -s --format=%cI``);
                pinned to the commit, never ``date.today()`` (ADR-074).
        """
        return cls(
            commit=commit,
            commit_date=commit_date,
            engine_label=report.engine_label,
            projection_years=report.projection_years,
            discount_rate=report.discount_rate,
            n_policies=report.n_policies,
            probes=[
                ProbeHistoryEntry(
                    probe=p.probe,
                    n_policies=p.n_policies,
                    projection_months=p.projection_months,
                    n_cells=p.n_cells,
                    output_fingerprint=p.output_fingerprint,
                    peak_mib=p.peak_mib,
                    best_of_k_seconds=p.best_of_k_seconds,
                    k=p.k,
                )
                for p in report.probes
            ],
        )


class ProbeCreep(PolarisBaseModel):
    """Earliest-window vs recent-window comparison of one hot-path across the log.

    The ``peak_mib`` delta is the **gate-worthy** signal (deterministic, portable
    across machines); the wall-time ratio is **advisory only** (cross-machine
    hardware drift). ``config_drift`` flags a series whose probe inputs changed
    between the windows, so it is not apples-to-apples.
    """

    probe: str = Field(description="Hot-path name compared across the series.")
    n_baseline: int = Field(gt=0, description="Rows in the earliest (baseline) window.")
    n_recent: int = Field(gt=0, description="Rows in the most-recent window.")
    peak_mib_baseline: float = Field(
        ge=0.0, description="Median peak MiB over the baseline window."
    )
    peak_mib_recent: float = Field(ge=0.0, description="Median peak MiB over the recent window.")
    peak_mib_delta: float = Field(
        description="recent - baseline median peak MiB. Positive => allocation crept up (GATE)."
    )
    peak_mib_creep: bool = Field(
        description="True iff peak_mib_delta exceeds mib_creep_delta — the creep GATE signal."
    )
    wall_time_baseline_seconds: float = Field(
        ge=0.0, description="Median best-of-k over the baseline window (informational)."
    )
    wall_time_recent_seconds: float = Field(
        ge=0.0, description="Median best-of-k over the recent window (informational)."
    )
    wall_time_ratio: float | None = Field(
        description="recent / baseline median best-of-k; None if the baseline median is zero."
    )
    wall_time_creep: bool = Field(
        description="True iff wall_time_ratio exceeds the band. ADVISORY — never gates."
    )
    config_drift: bool = Field(
        description="True iff n_policies/projection_months/n_cells differ across the windows."
    )


class CreepVerdict(PolarisBaseModel):
    """The creep verdict over a whole ``perf/history.jsonl`` series.

    :attr:`has_structural_creep` is the single boolean a gate reads: it is True
    iff any hot-path's MiB-peak crept beyond the threshold. Wall-time creep is
    reported for information only via :attr:`has_wall_time_creep` and never
    contributes to the gate.
    """

    window: int = Field(gt=0, description="Rows per comparison window (earliest N vs latest N).")
    mib_creep_delta: int = Field(
        ge=0, description="Median peak-MiB rise (recent over baseline) above which creep gates."
    )
    band: float = Field(
        gt=0.0, description="Wall-time recent/baseline ratio above which an advisory alert fires."
    )
    insufficient_data: bool = Field(
        description="True iff no probe had >= 2*window rows — a verdict cannot be formed yet."
    )
    n_rows: int = Field(ge=0, description="Total rows in the analysed series.")
    probe_creeps: list[ProbeCreep] = Field(
        default_factory=list, description="Per-probe creep comparison for probes with enough rows."
    )

    @property
    def has_structural_creep(self) -> bool:
        """The gate signal: any hot-path's median MiB-peak crept beyond the threshold."""
        return any(p.peak_mib_creep for p in self.probe_creeps)

    @property
    def has_wall_time_creep(self) -> bool:
        """Advisory: any hot-path's wall-time recent/baseline ratio exceeded the band."""
        return any(p.wall_time_creep for p in self.probe_creeps)

    @property
    def has_config_drift(self) -> bool:
        """Advisory: any hot-path's probe inputs changed across the compared windows."""
        return any(p.config_drift for p in self.probe_creeps)

    def to_verdict_dict(self) -> dict[str, object]:
        """The verdict payload — gate signal first, then advisories, then per-probe detail."""
        return {
            "verdict": {
                "has_structural_creep": self.has_structural_creep,
                "has_wall_time_creep": self.has_wall_time_creep,
                "has_config_drift": self.has_config_drift,
            },
            "window": self.window,
            "mib_creep_delta": self.mib_creep_delta,
            "band": self.band,
            "insufficient_data": self.insufficient_data,
            "n_rows": self.n_rows,
            "probes": [
                {
                    "probe": p.probe,
                    "peak_mib": {
                        "baseline": p.peak_mib_baseline,
                        "recent": p.peak_mib_recent,
                        "delta": p.peak_mib_delta,
                        "creep": p.peak_mib_creep,
                    },
                    "wall_time": {
                        "baseline_seconds": p.wall_time_baseline_seconds,
                        "recent_seconds": p.wall_time_recent_seconds,
                        "ratio": p.wall_time_ratio,
                        "creep": p.wall_time_creep,
                    },
                    "config_drift": p.config_drift,
                    "n_baseline": p.n_baseline,
                    "n_recent": p.n_recent,
                }
                for p in self.probe_creeps
            ],
        }


def append_history_row(row: PerfHistoryRow, path: Path) -> None:
    """Append one history row as a single JSON line to ``path`` (creating it).

    The parent directory and the file are created if missing, so the very first
    ``record`` on a fresh checkout materialises ``perf/history.jsonl``. The row is
    serialized via ``model_dump_json`` (compact, one physical line) so
    :func:`load_history` round-trips it exactly.

    Args:
        row: The record to append.
        path: The ``perf/history.jsonl`` file (created with parents if absent).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(row.model_dump_json() + "\n")


def load_history(path: Path) -> list[PerfHistoryRow]:
    """Read a ``perf/history.jsonl`` series, in file (chronological) order.

    Blank lines are skipped so a hand-edited or trailing-newline file loads
    cleanly. A missing file is treated as an empty series (no rows recorded yet).

    Args:
        path: The ``perf/history.jsonl`` file.

    Returns:
        The parsed rows, oldest first (append order).

    Raises:
        PolarisComputationError is not raised here; a malformed line raises the
        underlying Pydantic ``ValidationError`` so a corrupt log fails loudly
        rather than silently dropping history.
    """
    if not path.exists():
        return []
    rows: list[PerfHistoryRow] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(PerfHistoryRow.model_validate_json(line))
    return rows


def detect_creep(
    rows: list[PerfHistoryRow],
    *,
    window: int = 3,
    mib_creep_delta: int = 4,
    band: float = 1.25,
) -> CreepVerdict:
    """Compare each hot-path's earliest ``window`` rows against its latest ``window``.

    For every probe present in enough rows, the median ``peak_mib`` and median
    best-of-k wall-time are taken over the earliest ``window`` rows (the
    historical baseline) and the latest ``window`` rows (the recent state). The
    **median** is used, not the mean, so a single machine-noise outlier at either
    end does not swing the verdict. A probe needs at least ``2 * window`` rows so
    the two windows do not overlap; probes with fewer rows are omitted, and if no
    probe qualifies the verdict is :attr:`CreepVerdict.insufficient_data`.

    The MiB-peak delta is the **gate** signal (deterministic, machine-portable);
    the wall-time ratio and any config drift are **advisory** and never gate, per
    the maintainer design rule (deterministic metrics gate, raw wall-time
    informs).

    Args:
        rows: The history series, oldest first (as :func:`load_history` returns).
        window: Rows per comparison window. Positive.
        mib_creep_delta: Median peak-MiB rise (recent over baseline) above which
            the probe is flagged as structural creep. Non-negative — a coarse
            guard above the ±1 MiB rounding jitter.
        band: Wall-time recent/baseline median ratio above which an advisory
            wall-time alert fires. Positive.

    Returns:
        A :class:`CreepVerdict`; read :attr:`CreepVerdict.has_structural_creep` to
        gate.

    Raises:
        PolarisValidationError: if ``window`` is not positive, ``mib_creep_delta``
            is negative, or ``band`` is not positive.
    """
    if window <= 0:
        raise PolarisValidationError(f"window must be positive, got {window}.")
    if mib_creep_delta < 0:
        raise PolarisValidationError(
            f"mib_creep_delta must be non-negative, got {mib_creep_delta}."
        )
    if band <= 0.0:
        raise PolarisValidationError(f"band must be positive, got {band}.")

    # Gather each probe's entries in chronological order across the series.
    series: dict[str, list[ProbeHistoryEntry]] = {}
    for row in rows:
        for entry in row.probes:
            series.setdefault(entry.probe, []).append(entry)

    probe_creeps: list[ProbeCreep] = []
    for probe in sorted(series):
        entries = series[probe]
        if len(entries) < 2 * window:
            continue
        baseline = entries[:window]
        recent = entries[-window:]

        peak_baseline = median(e.peak_mib for e in baseline)
        peak_recent = median(e.peak_mib for e in recent)
        peak_delta = peak_recent - peak_baseline

        wall_baseline = median(e.best_of_k_seconds for e in baseline)
        wall_recent = median(e.best_of_k_seconds for e in recent)
        wall_ratio = wall_recent / wall_baseline if wall_baseline > 0.0 else None

        # Config drift: the probe's inputs must be identical across both windows
        # for the comparison to be apples-to-apples.
        configs = {(e.n_policies, e.projection_months, e.n_cells) for e in (*baseline, *recent)}
        config_drift = len(configs) > 1

        probe_creeps.append(
            ProbeCreep(
                probe=probe,
                n_baseline=len(baseline),
                n_recent=len(recent),
                peak_mib_baseline=peak_baseline,
                peak_mib_recent=peak_recent,
                peak_mib_delta=peak_delta,
                peak_mib_creep=peak_delta > mib_creep_delta,
                wall_time_baseline_seconds=wall_baseline,
                wall_time_recent_seconds=wall_recent,
                wall_time_ratio=wall_ratio,
                wall_time_creep=wall_ratio is not None and wall_ratio > band,
                config_drift=config_drift,
            )
        )

    return CreepVerdict(
        window=window,
        mib_creep_delta=mib_creep_delta,
        band=band,
        insufficient_data=not probe_creeps,
        n_rows=len(rows),
        probe_creeps=probe_creeps,
    )
