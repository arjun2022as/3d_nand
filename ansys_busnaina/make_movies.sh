#!/bin/bash
# Make contaminant pictures, GIFs and montages with Fluent's off-screen driver (no display needed).
# Needs a compute node (for `module`): an `interactive` session, an OOD desktop terminal, or a job:
#   bash make_movies.sh fig4 --log --min 1e-3 --cavity-only
#   sbatch -A krishna -p standard -t 02:00:00 -c 2 --mem=8G -o logs/movies_%j.out \
#          make_movies.sh fig4 --max 0.1 --cavity-only
set -euo pipefail
# run from the project folder (sbatch runs a spooled copy of this script, so fall back to the submit dir)
if [[ -f "$(dirname "$0")/make_movies.py" ]]; then cd "$(dirname "$0")"; else cd "${SLURM_SUBMIT_DIR:?}"; fi

if ! type module >/dev/null 2>&1; then
    for f in /etc/profile.d/modules.sh /usr/share/lmod/lmod/init/bash; do
        [[ -f "$f" ]] && source "$f" && break
    done
fi
if ! type module >/dev/null 2>&1; then
    echo "ERROR: no 'module' command: you are on a login node." >&2
    echo "       Start a compute-node session first:  interactive -a krishna -t 01:00:00" >&2
    exit 1
fi

module purge
module load "${ANSYS_MODULE:-ansys/24.1}"
FLUENT_EXE=$(readlink -f "$(command -v fluent)")
export AWP_ROOT241=${AWP_ROOT241:-$(dirname "$(dirname "$(dirname "$FLUENT_EXE")")")}
export PYFLUENT_FLUENT_ROOT="$AWP_ROOT241/fluent"
source "${VENV:-$HOME/venvs/pyfluent241}/bin/activate"

# PyFluent would otherwise ssh-spawn Fluent processes inside a SLURM job (see run_case.py)
for v in $(env | grep -o '^SLURM_[A-Z_]*'); do unset "$v"; done

python make_movies.py "$@"
