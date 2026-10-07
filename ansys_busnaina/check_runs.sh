#!/bin/bash
# Show which cases finished all their time steps. Works on the login node.
#   bash check_runs.sh            # all cases that have a results folder
#   bash check_runs.sh fig4       # only cases matching a pattern
cd "$(dirname "$0")"
PATTERN=${1:-.}

printf "%-26s %-10s %15s %10s %s\n" CASE STATUS STEPS EFFICIENCY NOTE
tail -n +2 cases.csv | while IFS=, read -r case _; do
    [[ "$case" =~ $PATTERN ]] || continue
    dir="results/$case"
    [[ -d "$dir" ]] || continue
    running=$(squeue -u "$USER" -h -n "$case" -o %T 2>/dev/null | head -1)
    hist_rows=$(($(wc -l < "$dir/history.csv" 2>/dev/null || echo 1) - 1))
    if [[ -f "$dir/summary.json" ]]; then
        run=$(grep -o '"steps_run": [0-9]*' "$dir/summary.json" | grep -o '[0-9]*$')
        tot=$(grep -o '"n_steps": [0-9]*' "$dir/summary.json" | grep -o '[0-9]*$')
        eff=$(grep -o '"cleaning_efficiency": [0-9.e-]*' "$dir/summary.json" | grep -o '[0-9.e-]*$')
        eff=$(awk -v e="$eff" 'BEGIN{printf "%.2f %%", 100*e}')
        if [[ "$run" == "$tot" && "$hist_rows" -gt 1 ]]; then status=DONE; note=""
        elif [[ "$hist_rows" -le 1 ]]; then status=BROKEN; note="history.csv empty: rerun with --force"
        else status=PARTIAL; note="stopped early: rerun with --force"; fi
        printf "%-26s %-10s %15s %10s %s\n" "$case" "$status" "$run/$tot" "$eff" "$note"
    elif [[ -n "$running" ]]; then
        printf "%-26s %-10s %15s %10s %s\n" "$case" "$running" "$hist_rows samples" "-" "in progress"
    else
        printf "%-26s %-10s %15s %10s %s\n" "$case" "FAILED" "-" "-" "no summary.json: check logs/${case}_*.err"
    fi
done
