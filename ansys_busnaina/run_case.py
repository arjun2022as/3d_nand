#!/usr/bin/env python3
"""Build and run one Fluent 2024 R1 case reproducing Lin, Busnaina & Suni (2002),
"Cleaning of high aspect ratio submicron trenches".

Model (paper section "Physical definition of the model"):
  * 2D, laminar, incompressible, Newtonian DI water (rho = 998.2 kg/m3, mu = 1.003e-3 Pa s)
  * Contaminant (K+ ions) as a passive species, mass diffusivity D = 6e-9 m2/s
    (back-calculated from the paper's Table 1: Pe = W * 0.1*Up / D = 2.5 for W = 1 um)
  * Cavity initially filled with contaminant (mass fraction 1), channel clean
  * Inlet velocity
        steady:       u = u_avg
        oscillating:  u = Us                                  0   <= t/T < 0.5
                      u = Us + Up sin(2 pi (t/T - 0.5))       0.5 <= t/T <= 1
    with Us = 0, Up = pi * u_avg (same mean velocity as the steady case).
    Check: Fig. 4 lists St = W f / Up = 4.244 at f = 2 MHz, W = 1 um -> Up = 0.471 m/s = pi * 0.15.
  * Cleaning efficiency = 1 - C_cavity(t) / C_cavity(0)

Deviation from the paper: the paper uses periodic inlet/outlet over a single cavity.
Here a velocity inlet (2W upstream) and pressure outlet (3W downstream) are used, so the
removed contaminant leaves the domain instead of re-entering it.

Usage (on Puma, inside the SLURM job):
    python run_case.py --case fig4_f2000k --procs 4
    python run_case.py --case fig4_f2000k --procs 4 --setup-only   # quick check, 5 time steps
"""
import argparse
import csv
import json
import math
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_trench_mesh  # noqa: E402

RHO, MU, DIFF = 998.2, 1.003e-3, 6e-9
TRACER = "h2o"   # species of mixture-template used as the contaminant (props overridden to water)


def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)


# ---------------------------------------------------------------- settings helpers
def pick(obj, *names):
    """Return the first existing child among `names` (settings names differ between versions)."""
    for n in names:
        try:
            return getattr(obj, n)
        except (AttributeError, RuntimeError):
            continue
    raise AttributeError(f"none of {names} under {getattr(obj, 'path', obj)}; "
                         f"available: {getattr(obj, 'child_names', '?')}")


def setv(obj, value):
    obj.set_state(value)
    return obj


def option(obj, *candidates):
    """First candidate that this option object allows (raises with the allowed list)."""
    allowed = list(obj.allowed_values())
    for c in candidates:
        if c in allowed:
            return c
    raise ValueError(f"none of {candidates} allowed; allowed: {allowed}")


def first_ok(label, *attempts):
    """Run callables in order until one succeeds; raise with all errors otherwise."""
    errors = []
    for fn in attempts:
        try:
            out = fn()
            log(f"{label}: ok")
            return out
        except Exception as e:  # noqa: BLE001 - want every failure reported
            errors.append(f"{type(e).__name__}: {e}")
    raise RuntimeError(f"{label} failed:\n  " + "\n  ".join(errors))


def scalar(res):
    """Pull the first number out of a report_definitions.compute() result."""
    if isinstance(res, (int, float)):
        return float(res)
    items = res.values() if isinstance(res, dict) else res if isinstance(res, (list, tuple)) else []
    for v in items:
        try:
            return scalar(v)
        except ValueError:
            continue
    raise ValueError(f"no number in {res!r}")


# ---------------------------------------------------------------- case parameters
def load_case(name):
    with open(HERE / "cases.csv", newline="") as f:
        for row in csv.DictReader(f):
            if row["case"] == name:
                return row
    raise SystemExit(f"case '{name}' not in cases.csv")


def plan(row, steps_per_period, min_steps, cfl):
    W, AR, n = float(row["W_m"]), float(row["AR"]), int(row["n_per_w"])
    u_avg, f, t_end = float(row["u_avg_m_s"]), float(row["freq_Hz"]), float(row["t_end_s"])
    h = W / n
    if row["mode"] == "osc":
        Us, Up = 0.0, math.pi * u_avg
        w = 2 * math.pi * f
        expr = (f"{Us} [m/s] + {Up:.6g} [m/s] * 0.5 * "
                f"(abs(sin({w:.10g} [s^-1] * t)) - sin({w:.10g} [s^-1] * t))")
        dt = min(t_end / min_steps, cfl * h / (Us + Up), 1.0 / f / steps_per_period)
        St = W * f / Up
    else:
        Us, Up, St = u_avg, 0.0, None
        expr = f"{u_avg} [m/s]"
        dt = min(t_end / min_steps, cfl * h / u_avg)
    n_steps = math.ceil(t_end / dt)
    dt = t_end / n_steps
    return dict(W=W, AR=AR, n_per_w=n, h=h, u_avg=u_avg, Us=Us, Up=Up, freq=f, St=St,
                t_end=t_end, dt=dt, n_steps=n_steps, inlet_expr=expr,
                Re=RHO * u_avg * W / MU, Pe_table1=W * 0.1 * u_avg / DIFF)


# ---------------------------------------------------------------- Fluent setup
def launch(procs, workdir):
    import ansys.fluent.core as pyfluent
    log(f"PyFluent {pyfluent.__version__}, launching Fluent 2D double precision on {procs} cores")
    # Inside a SLURM job PyFluent builds a host list and Fluent then spawns its
    # processes over ssh to the same node ("Host key verification failed").
    # Hiding SLURM variables makes it start all processes locally instead.
    for k in [k for k in os.environ if k.startswith("SLURM_")]:
        os.environ.pop(k)
    return pyfluent.launch_fluent(
        product_version=pyfluent.FluentVersion.v241,
        dimension=pyfluent.Dimension.TWO,
        precision=pyfluent.Precision.DOUBLE,
        processor_count=procs,
        ui_mode=pyfluent.UIMode.NO_GUI_OR_GRAPHICS,
        cwd=str(workdir),
        start_timeout=900,
    )


def setup(solver, msh, p):
    s = getattr(solver, "settings", solver)

    first_ok("read mesh",
             lambda: s.file.read_mesh(file_name=msh),
             lambda: s.file.read(file_type="mesh", file_name=msh),
             lambda: solver.tui.file.read_case(msh))
    try:
        s.mesh.check()
    except Exception as e:  # noqa: BLE001
        log("mesh check call failed (continuing):", e)
    try:
        solver.tui.file.confirm_overwrite("no")
    except Exception:  # noqa: BLE001
        pass

    gen = s.setup.general
    first_ok("transient 2nd order",
             lambda: setv(pick(gen.solver, "time"), "unsteady-2nd-order"))
    first_ok("laminar",
             lambda: setv(pick(s.setup.models.viscous, "model"), "laminar"))

    sp = s.setup.models.species
    first_ok("species transport",
             lambda: (setv(sp.model.option, "species-transport"),
                      setv(sp.model.material, "mixture-template")),
             lambda: solver.tui.define.models.species.species_transport("yes", "mixture-template"))

    # Fluent 24.1 has no "constant" density for a mixture: give every species
    # constant water properties and mix them volume-weighted (= RHO exactly).
    mix = s.setup.materials.mixture["mixture-template"]
    vs = mix.species.volumetric_species
    species = list(vs.get_object_names())
    log("mixture species (solved in this order):", species)
    global TRACER
    TRACER = species[0]   # first species = species-0, always solved (the last is the bulk)
    log("contaminant tracer species:", TRACER)
    # Mixture rules first: per-species properties are inactive until the mixture
    # uses a mixing law for that property.
    setv(mix.density.option, option(mix.density.option, "constant", "volume-weighted-mixing-law"))
    setv(mix.viscosity.option, option(mix.viscosity.option, "constant", "mass-weighted-mixing-law"))
    log("mixture density rule:", mix.density.option(), "| viscosity rule:", mix.viscosity.option())
    if mix.density.option() == "constant":
        setv(mix.density.value, RHO)
    if mix.viscosity.option() == "constant":
        setv(mix.viscosity.value, MU)

    for name in species:
        sp_ = vs[name]
        for prop, val in (("density", RHO), ("viscosity", MU)):
            obj = getattr(sp_, prop)
            if not obj.is_active():
                continue   # mixture uses a constant for this property
            setv(obj.option, option(obj.option, "constant"))
            setv(obj.value, val)
            log(f"species {name}: {prop} = {obj()}")
    try:
        setv(s.setup.models.energy.enabled, False)
        log("energy equation: off (isothermal)")
    except Exception as e:  # noqa: BLE001
        log("energy equation left on:", e)
    md = mix.mass_diffusivity
    first_ok("mass diffusivity",
             lambda: (setv(md.option, "constant-dilute-appx"), setv(pick(md, "value"), DIFF)),
             lambda: (setv(md.option, "constant-dilute-appx"),
                      setv(pick(md, "constant_dilute_appx", "constant"), DIFF)))
    log("mixture density:", mix.density())
    log("mixture viscosity:", mix.viscosity())
    log("mixture mass diffusivity:", md())

    ne = s.setup.named_expressions
    ne["u_in"] = {"definition": p["inlet_expr"]}
    log("u_in =", ne["u_in"].definition())

    vi = s.setup.boundary_conditions.velocity_inlet["inlet"]
    mom = vi.momentum if "momentum" in getattr(vi, "child_names", []) else vi
    vel = pick(mom, "velocity_magnitude", "velocity", "vmag")
    first_ok("inlet velocity = u_in",
             lambda: setv(vel.value, "u_in"),
             lambda: setv(vel, "u_in"),
             lambda: setv(vel, {"option": "expression", "expression": "u_in"}))
    log("inlet velocity:", vel())

    try:
        s.solution.methods.p_v_coupling.flow_scheme = "PISO"
        log("pressure-velocity coupling: PISO")
    except Exception as e:  # noqa: BLE001
        log("PISO not set, keeping default:", e)

    # contaminant inventory in the cavity
    vol = s.solution.report_definitions.volume
    vol["c_cavity"] = {}
    r = vol["c_cavity"]
    setv(r.report_type, "volume-average")
    setv(r.field, TRACER)
    setv(r.cell_zones, ["cavity"])
    # sanity check that the mixture really is water
    vol["rho_avg"] = {}
    r = vol["rho_avg"]
    setv(r.report_type, "volume-average")
    setv(r.field, "density")
    setv(r.cell_zones, ["channel", "cavity"])

    try:
        s.solution.monitor.report_files["c_cavity_rfile"] = {
            "report_defs": ["c_cavity"], "file_name": "c_cavity.out",
            "frequency_of": "time-step", "frequency": 1}
        log("report file: c_cavity.out (every time step)")
    except Exception as e:  # noqa: BLE001
        log("report file not created (history.csv still written):", e)

    tc = s.solution.run_calculation.transient_controls
    setv(tc.time_step_size, p["dt"])


def report(solver, name="c_cavity"):
    s = getattr(solver, "settings", solver)
    return scalar(s.solution.report_definitions.compute(report_defs=[name]))


def initialize(solver):
    s = getattr(solver, "settings", solver)
    ini = s.solution.initialization
    first_ok("standard initialization",
             lambda: ini.standard_initialize(),
             lambda: ini.initialize())
    rho = report(solver, "rho_avg")
    log(f"mixture density check: {rho} kg/m3")
    if abs(rho - RHO) > 1e-3 * RHO:
        raise RuntimeError(f"mixture density is {rho}, expected {RHO}: species properties not applied")
    c = report(solver)
    if abs(c) > 1e-12:
        raise RuntimeError(f"cavity concentration after initialization is {c}, expected 0")

    # patch variables are named species-0, species-1 (solve order), not by species name
    for var in ("species-0", "species-1", TRACER):
        try:
            ini.patch.calculate_patch(cell_zones=["cavity"], variable=var, value=1.0)
        except Exception as e:  # noqa: BLE001
            log(f"patch {var}: {type(e).__name__}: {e}")
            continue
        c = report(solver)
        log(f"patch {var}: cavity {TRACER} = {c}")
        if abs(c - 1.0) < 1e-6:
            return
        ini.patch.calculate_patch(cell_zones=["cavity"], variable=var, value=0.0)  # undo
    raise RuntimeError("could not patch contaminant into the cavity; see attempts above")


def iterate(solver, n, iters):
    s = getattr(solver, "settings", solver)
    rc = s.solution.run_calculation
    first_ok(f"advance {n} steps",
             lambda: rc.dual_time_iterate(time_step_count=n, max_iter_per_step=iters),
             lambda: (setv(rc.transient_controls.time_step_count, n),
                      setv(rc.transient_controls.max_iter_per_time_step, iters),
                      rc.calculate()),
             lambda: solver.tui.solve.dual_time_iterate(n, iters))


def write(solver, kind, name):
    s = getattr(solver, "settings", solver)
    tui = {"case": "write_case", "data": "write_data", "case-data": "write_case_data"}[kind]
    first_ok(f"write {name}",
             lambda: s.file.write(file_type=kind, file_name=name),
             lambda: getattr(solver.tui.file, tui)(name))


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", required=True, help="row name in cases.csv")
    ap.add_argument("--procs", type=int, default=int(os.environ.get("SLURM_CPUS_PER_TASK", 4)))
    ap.add_argument("--out", default=None, help="output folder (default results/<case>)")
    ap.add_argument("--steps-per-period", type=int, default=20)
    ap.add_argument("--min-steps", type=int, default=2000, help="minimum time steps over t_end")
    ap.add_argument("--cfl", type=float, default=1.0, help="max convective Courant number")
    ap.add_argument("--iters", type=int, default=20, help="max iterations per time step")
    ap.add_argument("--log-points", type=int, default=200, help="history samples over the run")
    ap.add_argument("--snapshots", type=int, default=5, help="data files saved during the run")
    ap.add_argument("--setup-only", action="store_true", help="build the case, run 5 steps, stop")
    ap.add_argument("--plan-only", action="store_true", help="print time step plan and exit")
    a = ap.parse_args()

    row = load_case(a.case)
    p = plan(row, a.steps_per_period, a.min_steps, a.cfl)
    log("case", a.case, json.dumps(p, indent=1))
    if a.plan_only:
        return

    out = Path(a.out or HERE / "results" / a.case).resolve()
    out.mkdir(parents=True, exist_ok=True)
    msh = out / f"{a.case}.msh"
    info = make_trench_mesh.main(["--W", str(p["W"]), "--AR", str(p["AR"]),
                                  "--n-per-w", str(p["n_per_w"]), "-o", str(msh)])
    p["mesh"] = info

    solver = launch(a.procs, out)
    try:
        setup(solver, msh.name, p)
        initialize(solver)
        write(solver, "case-data", f"{a.case}-t0.cas.h5")

        n_total = 5 if a.setup_only else p["n_steps"]
        chunk = max(1, n_total // a.log_points)
        snap_every = max(1, n_total // max(1, a.snapshots))
        hist = out / "history.csv"
        with open(hist, "w", newline="") as f:
            wr = csv.writer(f)
            wr.writerow(["step", "time_s", "c_cavity", "cleaning_efficiency"])
            wr.writerow([0, 0.0, 1.0, 0.0])
            done, next_snap, t0 = 0, snap_every, time.time()
            while done < n_total:
                n = min(chunk, n_total - done)
                iterate(solver, n, a.iters)
                done += n
                c = report(solver)
                wr.writerow([done, done * p["dt"], c, 1.0 - c])
                f.flush()
                if done >= next_snap and done < n_total:
                    write(solver, "data", f"{a.case}-{done:08d}.dat.h5")
                    next_snap += snap_every
                rate = (time.time() - t0) / done
                log(f"step {done}/{n_total}  t={done * p['dt']:.4e} s  C/C0={c:.6f}  "
                    f"eta={1 - c:.4f}  ETA {rate * (n_total - done) / 3600:.2f} h")

        write(solver, "case-data", f"{a.case}-final.cas.h5")
        p.update(c_final=c, cleaning_efficiency=1.0 - c, steps_run=done,
                 setup_only=a.setup_only, wall_s=time.time() - t0)
        (out / "summary.json").write_text(json.dumps(p, indent=1))
        log("done:", json.dumps({k: p[k] for k in ("c_final", "cleaning_efficiency", "steps_run")}))
    finally:
        solver.exit()


if __name__ == "__main__":
    main()
