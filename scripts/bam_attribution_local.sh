#!/bin/sh
# bam_attribution_local.sh -- the local ILEC probe for ADR-260 amendment 1 (maintainer's Mac).
#
# Question it answers on REAL cells: is bam(discrete=TRUE)'s gap from gam the ALGORITHM (as the
# synthetic cell says) and is NOTHING binned (every covariate <= 1000 unique values)?
# It runs gam, bam(discrete=TRUE) and bam(discrete=FALSE) on the same cell, each in its own
# process, then prints SCALARS ONLY. Per-row eta lives in $WORK/<cell>/probe_*.json: local, never
# committed.
#
# USAGE: WORK=$HOME/polaris_trial_scratch scripts/bam_attribution_local.sh T1_mid [S2_mid ...]
# Needs: native Rscript with mgcv + jsonlite, python3, and the cell directories that
# gam_real_data_trial.py run-cell wrote ($WORK/<cell>/cells.csv and spec.json).
# Set the thread count once; the same value applies to all three runs.
set -u
: "${WORK:?set WORK to the trial scratch directory}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}" OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
HERE=$(cd "$(dirname "$0")" && pwd)
[ $# -ge 1 ] || { echo "usage: $0 <cell> [<cell> ...]   e.g. T1_mid" >&2; exit 2; }
Rscript -e 'cat("R", R.version.string, "mgcv", as.character(packageVersion("mgcv")), "\n")' || exit 1
echo "threads=$OPENBLAS_NUM_THREADS machine=$(uname -m)"
for CELL in "$@"; do
  DIR="$WORK/$CELL"
  if [ ! -f "$DIR/cells.csv" ] || [ ! -f "$DIR/spec.json" ]; then
    echo "MISSING $DIR/cells.csv or spec.json. Recreate it with (see docs/RUNBOOK_gam_real_data_trial.md):" >&2
    echo "  uv run python scripts/gam_real_data_trial.py run-cell --work \"\$WORK\" --formula <T1|S2|...> --granularity <mid> --repeats 1 --no-profile  (plus the runbook's other flags)" >&2
    exit 1
  fi
  echo "=== $CELL ==="
  # cheapest first, so a failure in the slow gam run does not hide the bam readings
  for METHOD in bam bam_nodisc gam; do
    "$HERE/bam_discrete_probe_run.sh" "$DIR" "$METHOD" || { echo "STOP: $METHOD failed on $CELL" >&2; exit 1; }
  done
  python3 "$HERE/bam_discrete_probe_compare.py" "$DIR"
done
echo "Paste everything above (scalars only) back to the session. Delete \$WORK/*/probe_*.json when done."
