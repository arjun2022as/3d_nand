#!/bin/bash
# One-time setup on a Puma LOGIN node (needs internet for pip):
#     bash setup_env.sh
# Creates ~/venvs/pyfluent241 with PyFluent (<0.38 = last series supporting Fluent 2024 R1).
set -euo pipefail

ANSYS_MODULE=${ANSYS_MODULE:-ansys/2024R1}
VENV=${VENV:-$HOME/venvs/pyfluent241}

module purge
module load "$ANSYS_MODULE" || { echo "module $ANSYS_MODULE not found; pick one from: module avail ansys" >&2; exit 1; }

FLUENT_EXE=$(readlink -f "$(command -v fluent)")
AWP_ROOT241=${AWP_ROOT241:-$(dirname "$(dirname "$(dirname "$FLUENT_EXE")")")}
echo "Fluent      : $FLUENT_EXE"
echo "AWP_ROOT241 : $AWP_ROOT241"

# Prefer the Python that ships with Ansys 2024 R1, else a cluster Python >= 3.10
PY="$AWP_ROOT241/commonfiles/CPython/3_10/linx64/Release/python/bin/python3"
if [[ ! -x "$PY" ]]; then
    for m in python/3.11 python/3.10 python/3.12; do
        if module load "$m" 2>/dev/null; then PY=$(command -v python3); break; fi
    done
fi
"$PY" -c 'import sys; assert sys.version_info >= (3, 10), sys.version' \
    || { echo "need Python >= 3.10 (found $PY)" >&2; exit 1; }
echo "Python      : $PY ($("$PY" --version))"

"$PY" -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install "ansys-fluent-core>=0.26,<0.38" matplotlib
"$VENV/bin/python" -c "import ansys.fluent.core as p; print('PyFluent', p.__version__)"
echo "Done. Environment: $VENV"
