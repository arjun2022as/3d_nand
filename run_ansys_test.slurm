#!/bin/bash
#SBATCH --job-name=ansys_test
#SBATCH --nodes=1
#SBATCH --ntasks=8                # MPI ranks for distributed MAPDL
#SBATCH --cpus-per-task=1
#SBATCH --hint=nomultithread      # one rank per physical core (no hyperthreads)
#SBATCH --exclusive               # whole node -> clean timings; drop if queue wait is long
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --partition=compute       # <-- change to your cluster's partition
##SBATCH --account=krishna     # <-- uncomment if your cluster needs one
#SBATCH --output=%x_%j.out
#SBATCH --error=%x_%j.err

set -euo pipefail

# ---- run settings (override: sbatch --export=ALL,SOLVER=1,NDIV=80 run_ansys_test.slurm) ----
SOLVER=${SOLVER:-2}               # 1 = sparse direct, 2 = PCG iterative
NDIV=${NDIV:-60}                  # elements per cube edge
MPI_FLAG=${MPI_FLAG:-}            # e.g. "-mpi intelmpi" or "-mpi openmpi" if the default MPI misbehaves
KEEP_RST=${KEEP_RST:-0}           # 1 = copy the (large) .rst file back

# ---- environment (check `module avail ansys` on your cluster) ----
module purge
module load ansys                 # e.g. ansys/2024R1

# Uncomment if the license server is not set by the module
# export ANSYSLMD_LICENSE_FILE=1055@license.myuniversity.edu

SUBMIT_DIR="$SLURM_SUBMIT_DIR"

# ---- find the MAPDL executable (name differs by version/site) ----
ANSYS_EXE=""
for exe in mapdl ansys251 ansys242 ansys241 ansys232 ansys231 ansys222; do
    if command -v "$exe" >/dev/null 2>&1; then ANSYS_EXE="$exe"; break; fi
done
if [[ -z "$ANSYS_EXE" ]]; then
    echo "ERROR: no MAPDL executable found in PATH after module load" >&2
    exit 1
fi

# ---- run on node-local scratch: MAPDL is I/O heavy, shared filesystems are slow ----
WORKDIR="${TMPDIR:-/tmp}/ansys_${SLURM_JOB_ID}"
srun --nodes="$SLURM_NNODES" --ntasks="$SLURM_NNODES" mkdir -p "$WORKDIR"
cp "$SUBMIT_DIR/ansys_test.inp" "$WORKDIR/"
cd "$WORKDIR"

copy_back() {
    cp -f ansys_test.out "$SUBMIT_DIR/ansys_test_${SLURM_JOB_ID}.out" 2>/dev/null || true
    cp -f results.txt    "$SUBMIT_DIR/results_${SLURM_JOB_ID}.txt"    2>/dev/null || true
    for f in ansys_test*.err; do
        [[ -e "$f" ]] && cp -f "$f" "$SUBMIT_DIR/${f%.err}_${SLURM_JOB_ID}.err"
    done
    if [[ "$KEEP_RST" == "1" ]]; then
        cp -f ansys_test.rst "$SUBMIT_DIR/ansys_test_${SLURM_JOB_ID}.rst" 2>/dev/null || true
    fi
    srun --nodes="$SLURM_NNODES" --ntasks="$SLURM_NNODES" rm -rf "$WORKDIR" || true
}
trap copy_back EXIT

# ---- host list for distributed (DMP) runs: host1:n1:host2:n2 ----
MACHINES=$(srun hostname | sort | uniq -c | awk '{print $2":"$1}' | paste -sd:)

echo "Job ID     : $SLURM_JOB_ID"
echo "Executable : $(command -v "$ANSYS_EXE")"
echo "Nodes      : $SLURM_JOB_NODELIST"
echo "Ranks      : $SLURM_NTASKS"
echo "Machines   : $MACHINES"
echo "Solver     : $SOLVER (1=sparse, 2=PCG)   NDIV: $NDIV"
echo "Workdir    : $WORKDIR"
echo "Start      : $(date)"

# Note: more than 4 cores usually needs ANSYS HPC licenses (add e.g. -ppf anshpc if your site requires it)
T_START=$SECONDS
# shellcheck disable=SC2086
"$ANSYS_EXE" -b -dis -np "$SLURM_NTASKS" -machines "$MACHINES" $MPI_FLAG -s noread \
    -i ansys_test.inp -o ansys_test.out -j ansys_test \
    -SOLVER "$SOLVER" -NDIV "$NDIV"
WALL=$((SECONDS - T_START))

# Solver-only time reported by MAPDL (excludes startup, meshing, licensing)
SOLVE_T=$(grep -i -m1 "elapsed time spent computing solution" ansys_test.out | awk '{print $(NF-1)}' || true)

echo "End        : $(date)"
echo "Wall time  : ${WALL} s   Solve time: ${SOLVE_T:-NA} s"
echo "---------------- results.txt ----------------"
cat results.txt

# ---- append to scaling log ----
CSV="$SUBMIT_DIR/scaling.csv"
[[ -f "$CSV" ]] || echo "jobid,nodes,ranks,solver,ndiv,wall_s,solve_s" > "$CSV"
echo "$SLURM_JOB_ID,$SLURM_NNODES,$SLURM_NTASKS,$SOLVER,$NDIV,$WALL,${SOLVE_T:-NA}" >> "$CSV"
