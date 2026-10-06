#!/bin/bash
# Submit cases from cases.csv whose name matches a pattern, each with its own walltime.
#   bash submit_cases.sh fig4            # all Fig. 4 cases
#   bash submit_cases.sh 'fig3_w100um'   # a subset
#   bash submit_cases.sh fig4_f2000k --setup-only
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p logs

PATTERN=${1:?usage: bash submit_cases.sh <pattern> [run_case.py args]}
shift

tail -n +2 cases.csv | while IFS=, read -r case _ _ _ _ _ _ _ walltime _; do
    [[ "$case" =~ $PATTERN ]] || continue
    if [[ " $* " == *" --setup-only "* ]]; then walltime=01:00:00; fi
    sbatch --job-name="$case" --time="$walltime" run_case.slurm "$case" "$@"
done
