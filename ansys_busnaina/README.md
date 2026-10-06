# Busnaina 2002 trench cleaning in Fluent 2024 R1

Reproduces Lin, Busnaina & Suni, *Cleaning of High Aspect Ratio Submicron Trenches*
(IEEE/SEMI ASMC 2002), Figs. 2–4, with ANSYS Fluent 2024 R1 on UA HPC (Puma).

## Model

| Item | Value | Source |
|---|---|---|
| Geometry | 2D channel over one trench, width W, depth D = AR·W; channel height 2.5W, inlet 2W upstream, outlet 3W downstream | Fig. 1, Fig. 5 |
| Fluid | DI water, laminar, incompressible: ρ = 998.2 kg/m³, μ = 1.003e-3 Pa·s | paper §Model |
| Contaminant | passive species, D = 6e-9 m²/s, cavity mass fraction 1 at t = 0 | D from Table 1 (Pe = 2.5 at W = 1 µm) |
| Steady inlet | u = 0.15 m/s | Fig. 2 |
| Pulsating inlet | u = Us for t/T < 0.5, Us + Up·sin(2π(t/T−0.5)) after; Us = 0, Up = π·0.15 = 0.471 m/s | BC eq.; Up confirmed by the St values in Fig. 4 |
| Top | symmetry (free surface) | paper §BC |
| Output | C/C0 in the cavity vs time; cleaning efficiency = 1 − C/C0 | Figs. 2–4 |

**Differences from the paper.** The paper uses periodic inlet/outlet boundaries; here there's a velocity inlet and a pressure outlet, so removed contaminant leaves the domain and doesn't re-enter. The paper used the GENFLO code; this uses Fluent. Expect the same trends, not identical numbers.

## Files

| File | Purpose |
|---|---|
| `make_trench_mesh.py` | writes the 2D Fluent `.msh` (zones: `channel`, `cavity`, `inlet`, `outlet`, `top`, `wafer`, `trench-walls`, `mouth`) |
| `cases.csv` | the 25 cases (Fig. 2: 4, Fig. 3: 16, Fig. 4: 5) with walltimes |
| `run_case.py` | PyFluent: builds the case, patches the contaminant, runs, logs `history.csv`, writes `.cas.h5` / `.dat.h5` |
| `run_case.slurm` | one case per job (4 cores, standard partition, account krishna) |
| `submit_cases.sh` | submits all cases matching a pattern |
| `setup_env.sh` | one-time Python + PyFluent install |
| `plot_results.py` | makes `results/fig2.png`, `fig3.png`, `fig4.png` |

## Run on Puma

```bash
# once: login nodes have no `module`, so do the setup on a compute node
interactive -a krishna -t 01:00:00
cd ~/3d_nand/ansys_busnaina
module avail ansys                     # if not "ansys/24.1": export ANSYS_MODULE=<name>
bash setup_env.sh
exit                                   # back to the login node

cd ~/3d_nand/ansys_busnaina

bash submit_cases.sh fig4_f2000k --setup-only     # 1) quick test: builds case, 5 time steps
cat logs/fig4_f2000k_*.out                        #    check for "ok" lines and C/C0 values

bash submit_cases.sh fig4              # 2) Fig. 4 (5 cases, cheapest: 1 um trench)
bash submit_cases.sh fig3              # 3) Fig. 3 (16 cases)
bash submit_cases.sh fig2              # 4) Fig. 2 (the 20 kHz cases take 400k time steps)

squeue -u $USER
source ~/venvs/pyfluent241/bin/activate && python plot_results.py
```

Preview the time-step plan without Fluent: `python run_case.py --case fig2_ar5_osc20k --plan-only`.

## Results per case (`results/<case>/`)

- `history.csv`: step, time, C/C0, cleaning efficiency
- `<case>-t0.cas.h5` / `.dat.h5`: set-up case at t = 0
- `<case>-final.cas.h5` / `.dat.h5`: final state (velocity and contaminant fields)
- `<case>-<step>.dat.h5`: intermediate snapshots (read them after the matching case file)
- `summary.json`: parameters, time step, final efficiency

To open in Fluent 2024 R1 on your PC: download a `.cas.h5` and its `.dat.h5`, then use **File → Read → Case & Data**. In Workbench, add a Fluent system and import the case. The contaminant field is **Species → Mass fraction of h2o** (the mixture template's `h2o` species is used as the tracer, with its properties set to water).
