#!/usr/bin/env python3
"""Render the contaminant field of saved runs as pictures, an animated GIF per case,
a montage (rows = cases, columns = time) and a final-state comparison (one row).

For every case matching the pattern it reads <case>-t0, each snapshot <case>-<step>.dat.h5
and <case>-final and draws a filled contour of the contaminant (C/C0). All frames and all
cases use the same colour range, so they can be compared directly.

Fluent needs a display to draw pictures, so run it from an OOD Interactive Desktop terminal:
    bash make_movies.sh fig4                                  # 0-1 scale, whole domain
    bash make_movies.sh fig4 --max 0.1 --cavity-only          # residual contaminant, trench zoom
    bash make_movies.sh fig4 --log --min 1e-3 --cavity-only   # log scale: every stage visible
Output goes to results/movies/<tag>/ (tag from the options, or --tag NAME).
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_case import first_ok, log, read_case_data, setv  # noqa: E402

RES = HERE / "results"


def frames_for(case):
    """[(label_time_s, data_file)] in time order: t0, snapshots, final."""
    d = RES / case
    summary = json.loads((d / "summary.json").read_text())
    dt, n_steps = summary["dt"], summary["steps_run"]
    snaps = sorted(d.glob(f"{case}-[0-9]*.dat.h5"),
                   key=lambda f: int(re.search(r"-(\d+)\.dat\.h5$", f.name).group(1)))
    items = [(0.0, d / f"{case}-t0.dat.h5")]
    items += [(int(re.search(r"-(\d+)\.dat\.h5$", f.name).group(1)) * dt, f) for f in snaps]
    items.append((n_steps * dt, d / f"{case}-final.dat.h5"))
    return items


def case_labels():
    """case -> short label (frequency for oscillating cases) and sort key, from cases.csv."""
    out = {}
    with open(HERE / "cases.csv", newline="") as f:
        for row in csv.DictReader(f):
            fq = float(row["freq_Hz"])
            lab = (f"{fq / 1e6:g} MHz" if fq >= 1e6 else f"{fq / 1e3:g} kHz" if fq >= 1e3
                   else f"{fq:g} Hz" if fq else "steady")
            out[row["case"]] = (lab, fq)
    return out


def read_data(solver, path):
    s = getattr(solver, "settings", solver)
    first_ok(f"read {path.name}",
             lambda: s.file.read_data(file_name=str(path)),
             lambda: s.file.read(file_type="data", file_name=str(path)),
             lambda: solver.tui.file.read_data(str(path)))


def make_contour(solver, a):
    s = getattr(solver, "settings", solver)
    g = s.results.graphics
    g.contour["contaminant"] = {}
    c = g.contour["contaminant"]
    setv(c.field, a.field)
    setv(c.filled, True)
    surfaces = list(c.surfaces_list.allowed_values())
    if a.cavity_only:
        surfaces = [x for x in surfaces if re.search(r"cavity|mouth|trench", x)]
    setv(c.surfaces_list, surfaces)
    log("contour surfaces:", surfaces)
    for name, value in (("node_values", True), ("draw_mesh", False)):
        try:
            setv(getattr(c, name), value)
        except Exception as e:  # noqa: BLE001
            log(f"{name} not set: {e}")

    # same colour range in every frame and every case
    setv(c.range_option.option, "auto-range-off")
    setv(c.range_option.auto_range_off.minimum, a.min)
    setv(c.range_option.auto_range_off.maximum, a.max)
    log(f"colour range {a.min:g} - {a.max:g}{' (log scale)' if a.log else ''}")
    cm = c.color_map
    if a.log:
        setv(cm.log_scale, True)
    for name, value in (("font_size", 0.12), ("format", "%0.2e" if a.log else "%0.3f")):
        try:
            setv(getattr(cm, name), value)
        except Exception as e:  # noqa: BLE001
            log(f"colour map {name} not set: {e}")

    try:
        pic = g.picture
        setv(pic.use_window_resolution, False)
        setv(pic.x_resolution, 1400)
        setv(pic.y_resolution, 900 if a.cavity_only else 800)
    except Exception as e:  # noqa: BLE001
        log("picture resolution left at default:", e)
    return c


def fit_view(solver):
    """Zoom to what is drawn (needed after restricting the contour to the trench)."""
    s = getattr(solver, "settings", solver)
    try:
        first_ok("fit view",
                 lambda: s.results.graphics.views.auto_scale(),
                 lambda: solver.tui.display.views.auto_scale())
    except RuntimeError as e:
        log(e)


def save_picture(solver, path):
    s = getattr(solver, "settings", solver)
    first_ok(f"save {path.name}",
             lambda: s.results.graphics.picture.save_picture(file_name=str(path)),
             lambda: solver.tui.display.save_picture(str(path)))


def assemble(case_frames, labels, out_dir, title):
    """Animated GIF per case, montage (cases x time) and final-state row."""
    from PIL import Image, ImageDraw, ImageFont

    def font(size):
        try:
            return ImageFont.load_default(size=size)
        except TypeError:   # Pillow < 10.1
            return ImageFont.load_default()

    for case, frames in case_frames.items():
        imgs = [Image.open(f).convert("RGB") for _, f in frames]
        imgs[0].save(out_dir / f"{case}.gif", save_all=True, append_images=imgs[1:],
                     duration=900, loop=0)
        log("wrote", out_dir / f"{case}.gif")

    first = Image.open(next(iter(case_frames.values()))[0][1])

    # montage: rows = cases, columns = time
    tw = 360
    th = round(first.height * tw / first.width)
    lw, lh = 170, 90
    ncol = max(len(f) for f in case_frames.values())
    sheet = Image.new("RGB", (lw + ncol * tw, lh + len(case_frames) * th), "white")
    d = ImageDraw.Draw(sheet)
    d.text((10, 8), title, fill="black", font=font(28))
    for r, (case, frames) in enumerate(case_frames.items()):
        y = lh + r * th
        d.text((10, y + th // 2 - 14), labels.get(case, (case,))[0], fill="black", font=font(30))
        for c, (t, f) in enumerate(frames):
            x = lw + c * tw
            sheet.paste(Image.open(f).convert("RGB").resize((tw, th)), (x, y))
            if r == 0:
                d.text((x + tw // 2 - 70, 52), f"t = {t * 1e3:.3g} ms", fill="black", font=font(26))
    sheet.save(out_dir / "montage.png")
    log("wrote", out_dir / "montage.png")

    # final state of every case, side by side and larger
    fw = 560
    fh = round(first.height * fw / first.width)
    row = Image.new("RGB", (len(case_frames) * fw, fh + 130), "white")
    d = ImageDraw.Draw(row)
    d.text((10, 8), f"Final state (t = {next(iter(case_frames.values()))[-1][0] * 1e3:.3g} ms), {title}",
           fill="black", font=font(28))
    for i, (case, frames) in enumerate(case_frames.items()):
        row.paste(Image.open(frames[-1][1]).convert("RGB").resize((fw, fh)), (i * fw, 120))
        d.text((i * fw + fw // 2 - 60, 66), labels.get(case, (case,))[0], fill="black", font=font(34))
    row.save(out_dir / "final_comparison.png")
    log("wrote", out_dir / "final_comparison.png")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pattern", help="regex for case folders, e.g. fig4 or 'fig3_w1mm_ar1'")
    ap.add_argument("--field", default="h2o", help="contour field (h2o = contaminant tracer)")
    ap.add_argument("--min", type=float, default=None, help="colour scale minimum (default 0, log: 1e-3)")
    ap.add_argument("--max", type=float, default=1.0, help="colour scale maximum (C/C0)")
    ap.add_argument("--log", action="store_true", help="logarithmic colour scale")
    ap.add_argument("--cavity-only", action="store_true", help="draw only the trench, zoomed in")
    ap.add_argument("--tag", default=None, help="output subfolder name (default from the options)")
    ap.add_argument("--procs", type=int, default=2)
    a = ap.parse_args()
    if a.min is None:
        a.min = 1e-3 if a.log else 0.0
    if a.log and a.min <= 0:
        raise SystemExit("--log needs --min > 0 (e.g. 1e-3)")

    tag = a.tag or "_".join(filter(None, [
        re.sub(r"[^A-Za-z0-9]+", "_", a.pattern).strip("_"),
        "log" if a.log else f"0-{a.max:g}",
        "cavity" if a.cavity_only else ""]))
    out_dir = RES / "movies" / tag
    title = (f"C/C0, log scale {a.min:g} - {a.max:g}" if a.log else f"C/C0, scale {a.min:g} - {a.max:g}")

    labels = case_labels()
    cases = [d.name for d in RES.iterdir()
             if d.is_dir() and re.search(a.pattern, d.name) and (d / "summary.json").exists()]
    cases.sort(key=lambda c: (labels.get(c, ("", 0))[1], c))
    if not cases:
        raise SystemExit(f"no finished cases match '{a.pattern}'")
    log("cases:", cases, "->", out_dir)

    import ansys.fluent.core as pyfluent
    solver = pyfluent.launch_fluent(
        product_version=pyfluent.FluentVersion.v241,
        dimension=pyfluent.Dimension.TWO,
        precision=pyfluent.Precision.DOUBLE,
        processor_count=a.procs,
        ui_mode=pyfluent.UIMode.NO_GUI,   # no Fluent window, but graphics for pictures
        cwd=str(RES),
        start_timeout=900,
    )
    case_frames = {}
    try:
        for case in cases:
            frames = frames_for(case)
            missing = [f.name for _, f in frames if not f.exists()]
            if missing:
                log(f"{case}: skipped, missing {missing}")
                continue
            (out_dir / case).mkdir(parents=True, exist_ok=True)
            read_case_data(solver, str(RES / case / f"{case}-t0.cas.h5"))
            contour = make_contour(solver, a)
            pics = []
            for i, (t, dat) in enumerate(frames):
                if i:
                    read_data(solver, dat)
                contour.display()
                if i == 0:
                    fit_view(solver)
                png = out_dir / case / f"frame_{i:02d}.png"
                save_picture(solver, png)
                pics.append((t, png))
            case_frames[case] = pics
    finally:
        solver.exit()
    if case_frames:
        assemble(case_frames, labels, out_dir, title)


if __name__ == "__main__":
    main()
