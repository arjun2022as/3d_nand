#!/bin/bash
# One-time setup. UA HPC login nodes have no `module` command, so run this
# inside an interactive session on a compute node:
#     interactive -a krishna -t 01:00:00
#     cd ~/3d_nand/ansys_busnaina && bash setup_env.sh
# Creates ~/venvs/pyfluent241 with PyFluent (<0.38 = last series supporting Fluent 2024 R1).
set -euo pipefail

ANSYS_MODULE=${ANSYS_MODULE:-ansys/24.1}
VENV=${VENV:-$HOME/venvs/pyfluent241}

if ! type module >/dev/null 2>&1; then
    for f in /etc/profile.d/modules.sh /usr/share/lmod/lmod/init/bash; do
        [[ -f "$f" ]] && source "$f" && break
    done
fi
if ! type module >/dev/null 2>&1; then
    echo "ERROR: 'module' is not available here (login node?)." >&2
    echo "Start a compute-node session first:  interactive -a krishna -t 01:00:00" >&2
    exit 1
fi

module purge
module load "$ANSYS_MODULE" || { echo "module $ANSYS_MODULE not found; pick one from: module avail ansys" >&2; exit 1; }

FLUENT_EXE=$(readlink -f "$(command -v fluent)")
AWP_ROOT241=${AWP_ROOT241:-$(dirname "$(dirname "$(dirname "$FLUENT_EXE")")")}
echo "Fluent      : $FLUENT_EXE"
echo "AWP_ROOT241 : $AWP_ROOT241"

# Use the Python 3.10 that ships with Ansys 2024 R1 (needs its lib dir on LD_LIBRARY_PATH)
PYHOME="$AWP_ROOT241/commonfiles/CPython/3_10/linx64/Release/python"
PY="$PYHOME/bin/python3"
export LD_LIBRARY_PATH="$PYHOME/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
"$PY" -c 'import sys; assert sys.version_info >= (3, 10), sys.version' \
    || { echo "need Python >= 3.10 (found $PY)" >&2; exit 1; }
echo "Python      : $PY ($("$PY" --version))"

rm -rf "$VENV"
"$PY" -m venv "$VENV"
# make every `source $VENV/bin/activate` (incl. batch jobs) find libpython3.10.so
cat >> "$VENV/bin/activate" <<EOF

# added by setup_env.sh: Ansys bundled Python shared library
export LD_LIBRARY_PATH="$PYHOME/lib\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"
EOF
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install "ansys-fluent-core>=0.26,<0.38" matplotlib
"$VENV/bin/python" -c "import ansys.fluent.core as p; print('PyFluent', p.__version__)"
echo "Done. Environment: $VENV"
