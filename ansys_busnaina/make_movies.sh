#!/bin/bash
# Make contaminant pictures, GIFs and a montage. Run in an OOD Interactive Desktop terminal:
#   bash make_movies.sh fig4                 # the 5 frequencies of Fig. 4
#   bash make_movies.sh 'fig3_w1mm_.*0.133'  # any regex of case names
set -euo pipefail
cd "$(dirname "$0")"

if ! type module >/dev/null 2>&1 || [[ -z "${DISPLAY:-}" ]]; then
    echo "ERROR: run this in an OOD Interactive Desktop terminal (needs a compute node and a display)," >&2
    echo "       not in the login-node shell: ood.hpc.arizona.edu -> Interactive Apps -> Interactive Desktop" >&2
    exit 1
fi

module purge
module load "${ANSYS_MODULE:-ansys/24.1}"
FLUENT_EXE=$(readlink -f "$(command -v fluent)")
export AWP_ROOT241=${AWP_ROOT241:-$(dirname "$(dirname "$(dirname "$FLUENT_EXE")")")}
export PYFLUENT_FLUENT_ROOT="$AWP_ROOT241/fluent"
source "${VENV:-$HOME/venvs/pyfluent241}/bin/activate"

if [[ -z "${DISPLAY:-}" ]]; then
    echo "ERROR: no display. Run this in an OOD Interactive Desktop terminal, not the shell." >&2
    exit 1
fi
python make_movies.py "$@"
