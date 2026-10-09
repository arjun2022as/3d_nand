#!/bin/bash
# Iterations per time step from each case's Fluent transcript (.trn).
# Shows whether time steps converged or hit the iteration cap (default 20).
#   bash iter_stats.sh tight        # cases matching a pattern
#   CAP=50 bash iter_stats.sh conv  # if runs used --iters 50
cd "$(dirname "$0")"
PATTERN=${1:-.}
CAP=${CAP:-20}

printf "%-24s %8s %8s %6s %14s\n" CASE STEPS MEAN_IT MAX_IT "STEPS_AT_CAP"
for dir in results/*/; do
    case=$(basename "$dir")
    [[ "$case" =~ $PATTERN ]] || continue
    trn=$(ls -t "$dir"/*.trn 2>/dev/null | head -1)
    [[ -n "$trn" ]] || { printf "%-24s %s\n" "$case" "no .trn transcript"; continue; }
    # residual rows look like "   1234  1.2e-04  3.4e-05 ..."; a step ends at "Flow time = ..."
    awk -v cap="$CAP" -v name="$case" '
        /^[ \t]*[0-9]+[ \t]+[0-9.]+e[-+][0-9]+/ { n++ }
        /Flow time = / { if (n > 0) { steps++; tot += n; if (n > mx) mx = n; if (n >= cap) capped++ } n = 0 }
        END {
            if (steps == 0) { printf "%-24s %s\n", name, "no time steps found in transcript"; exit }
            printf "%-24s %8d %8.1f %6d %8d (%3.0f%%)\n", name, steps, tot / steps, mx, capped, 100 * capped / steps
        }' "$trn"
done
