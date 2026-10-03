#!/bin/bash
#SBATCH --job-name=ansys_test
#SBATCH --nodes=1
#SBATCH --ntasks=8                # MPI ranks for distributed MAPDL
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --partition=compute       # <-- change to your cluster's partition
##SBATCH --account=my_account     # <-- uncomment if your cluster needs one
#SBATCH --output=%x_%j.out
#SBATCH --error=%x_%j.err

set -euo pipefail

# ---- environment (check `module avail ansys` on your cluster) ----
module purge
module load ansys                 # e.g. ansys/2024R1

# Uncomment if the license server is not set by the module
# export ANSYSLMD_LICENSE_FILE=1055@license.myuniversity.edu

cd "$SLURM_SUBMIT_DIR"

# ---- find the MAPDL executable (name differs by version/site) ----
ANSYS_EXE=""
for exe in mapdl ansys251 ansys242 ansys241 ansys232 ansys231 ansys222; do
    if command -v "$exe" >/dev/null 2>&1; then ANSYS_EXE="$exe"; break; fi
done
if [[ -z "$ANSYS_EXE" ]]; then
    echo "ERROR: no MAPDL executable found in PATH after module load" >&2
    exit 1
fi

# ---- host list for distributed (DMP) runs: host1:n1:host2:n2 ----
MACHINES=$(srun hostname | sort | uniq -c | awk '{print $2":"$1}' | paste -sd:)

echo "Job ID     : $SLURM_JOB_ID"
echo "Executable : $(command -v "$ANSYS_EXE")"
echo "Nodes      : $SLURM_JOB_NODELIST"
echo "Ranks      : $SLURM_NTASKS"
echo "Machines   : $MACHINES"
echo "Start      : $(date)"

"$ANSYS_EXE" -b -dis -np "$SLURM_NTASKS" -machines "$MACHINES" \
    -i ansys_test.inp -o ansys_test.out -j ansys_test

echo "End        : $(date)"
echo "---------------- results.txt ----------------"
cat results.txt
