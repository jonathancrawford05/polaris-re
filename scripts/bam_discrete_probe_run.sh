#!/bin/sh
# bam_discrete_probe_run.sh -- run ONE method for ONE cell in its own process and report peak RSS.
#
# USAGE: scripts/bam_discrete_probe_run.sh <cell_dir> <gam|bam>
#   e.g. scripts/bam_discrete_probe_run.sh "$WORK/T1_mid" gam
#        scripts/bam_discrete_probe_run.sh "$WORK/T1_mid" bam
# Writes <cell_dir>/probe_<method>.json and <cell_dir>/probe_<method>.time.
# Uses macOS /usr/bin/time -l, whose "maximum resident set size" is in BYTES.
# Set OPENBLAS_NUM_THREADS / OMP_NUM_THREADS the same for both runs (the comparison is internal).
set -eu
CELL_DIR="$1"; METHOD="$2"
HERE=$(cd "$(dirname "$0")" && pwd)
/usr/bin/time -l Rscript "$HERE/bam_discrete_probe.R" \
  "$CELL_DIR/cells.csv" "$CELL_DIR/spec.json" "$METHOD" "$CELL_DIR/probe_$METHOD.json" \
  > "$CELL_DIR/probe_$METHOD.out" 2> "$CELL_DIR/probe_$METHOD.time"
RSS_BYTES=$(awk '/maximum resident set size/ {print $1}' "$CELL_DIR/probe_$METHOD.time")
echo "$METHOD $(cat "$CELL_DIR/probe_$METHOD.out") peak_rss_mb=$(python3 -c "print(round($RSS_BYTES/1048576,1))")"
