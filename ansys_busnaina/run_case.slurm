#!/bin/bash
#SBATCH --job-name=busnaina
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4         # Fluent processes; >4 usually needs ANSYS HPC licenses
#SBATCH --mem=16G
#SBATCH --time=08:00:00           # overridden per case by submit_cases.sh
#SBATCH --partition=standard
#SBATCH --account=krishna
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err

# Usage: sbatch run_case.slurm <case> [extra run_case.py args, e.g. --setup-only]
set -euo pipefail

CASE=${1:?usage: sbatch run_case.slurm <case> [args]}
shift
ANSYS_MODULE=${ANSYS_MODULE:-ansys/24.1}
VENV=${VENV:-$HOME/venvs/pyfluent241}

module purge
module load "$ANSYS_MODULE"

FLUENT_EXE=$(readlink -f "$(command -v fluent)")
export AWP_ROOT241=${AWP_ROOT241:-$(dirname "$(dirname "$(dirname "$FLUENT_EXE")")")}
export PYFLUENT_FLUENT_ROOT="$AWP_ROOT241/fluent"
# Uncomment if the license server is not set by the module
# export ANSYSLMD_LICENSE_FILE=1055@license.server

source "$VENV/bin/activate"
cd "$SLURM_SUBMIT_DIR"

PART=${CHAIN_PART:-1}
MAX_PARTS=${MAX_PARTS:-10}
TIME_LEFT=$(squeue -h -j "$SLURM_JOB_ID" -o %L 2>/dev/null || true)
TIME_LIMIT=$(squeue -h -j "$SLURM_JOB_ID" -o %l 2>/dev/null || true)

echo "Job $SLURM_JOB_ID on $(hostname), case $CASE, $SLURM_CPUS_PER_TASK cores, part $PART"
echo "Fluent root: $AWP_ROOT241   time left: ${TIME_LEFT:-unknown}"
rc=0
python run_case.py --case "$CASE" --procs "$SLURM_CPUS_PER_TASK" --time-left "$TIME_LEFT" "$@" || rc=$?

# exit code 99: run_case.py checkpointed before the time limit -> submit the next part
if [[ $rc -eq 99 ]]; then
    if (( PART >= MAX_PARTS )); then
        echo "ERROR: $CASE reached $MAX_PARTS parts; resume by hand: sbatch run_case.slurm $CASE --resume" >&2
        exit 1
    fi
    next=(--resume)
    for arg in "$@"; do
        [[ "$arg" == "--force" || "$arg" == "--resume" ]] || next+=("$arg")
    done
    sbatch --job-name="$CASE" --time="${TIME_LIMIT:-24:00:00}" --export=ALL,CHAIN_PART=$((PART + 1)) \
        run_case.slurm "$CASE" "${next[@]}"
    echo "submitted part $((PART + 1)) of $CASE"
    exit 0
fi
exit $rc
