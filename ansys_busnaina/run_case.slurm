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

echo "Job $SLURM_JOB_ID on $(hostname), case $CASE, $SLURM_CPUS_PER_TASK cores"
echo "Fluent root: $AWP_ROOT241"
python run_case.py --case "$CASE" --procs "$SLURM_CPUS_PER_TASK" "$@"
