#!/bin/bash
# Submit the same model at several core counts with both solvers.
# Each job appends one line to scaling.csv; compare solve_s to pick the fastest setup.
#
# Usage:  bash scaling_study.sh            (default NDIV=80, ~1.5M DOF)
#         NDIV=100 bash scaling_study.sh
#
# Keep CORES <= cores per node (the job script requests --nodes=1).

NDIV=${NDIV:-80}
CORES="1 2 4 8 16 32"
SOLVERS="1 2"

for s in $SOLVERS; do
    for n in $CORES; do
        sbatch --ntasks="$n" --job-name="scal_s${s}_n${n}" \
               --export=ALL,SOLVER="$s",NDIV="$NDIV" run_ansys_test.slurm
    done
done
