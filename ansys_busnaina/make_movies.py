#!/usr/bin/env python3
"""Render the contaminant field of saved runs as pictures, an animated GIF per case,
and one montage (rows = cases, columns = time) for presentations.

For every case matching the pattern it reads <case>-t0, each snapshot <case>-<step>.dat.h5
and <case>-final, draws a filled contour of the contaminant mass fraction on a fixed
0-1 scale, and saves results/movies/<case>/frame_XX.png, results/movies/<case>.gif and
results/movies/montage_<pattern>.png.

Fluent needs a display to draw pictures, so run it from an OOD Interactive Desktop
terminal (not a batch job):
    bash make_movies.sh fig4
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_case import first_ok, log, read_case_data, setv  # noqa: E402

RES = HERE / "results"
OUT = RES / "movies"


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


def read_data(solver, path):
    s = getattr(solver, "settings", solver)
    first_ok(f"read {path.name}",
             lambda: s.file.read_data(file_name=str(path)),
             lambda: s.file.read(file_type="data", file_name=str(path)),
             lambda: solver.tui.file.read_data(str(path)))


def make_contour(solver, field):
    s = getattr(solver, "settings", solver)
    g = s.results.graphics
    g.contour["contaminant"] = {}
    c = g.contour["contaminant"]
    setv(c.field, field)
    setv(c.filled, True)
    surfaces = list(c.surfaces_list.allowed_values())
    setv(c.surfaces_list, surfaces)
    log("contour surfaces:", surfaces)
    try:   # same 0-1 colour scale in every frame, so frames are comparable
        setv(c.range_option.option, "auto-range-off")
        setv(c.range_option.auto_range_off.minimum, 0.0)
        setv(c.range_option.auto_range_off.maximum, 1.0)
    except Exception as e:  # noqa: BLE001
        log("fixed 0-1 range not set (auto range used):", e)
    try:
        pic = g.picture
        setv(pic.use_window_resolution, False)
        setv(pic.x_resolution, 1400)
        setv(pic.y_resolution, 800)
    except Exception as e:  # noqa: BLE001
        log("picture resolution left at default:", e)
    return c


def save_picture(solver, path):
    s = getattr(solver, "settings", solver)
    first_ok(f"save {path.name}",
             lambda: s.results.graphics.picture.save_picture(file_name=str(path)),
             lambda: solver.tui.display.save_picture(str(path)))


def assemble(case_frames, pattern):
    """Animated GIF per case and one labelled montage."""
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.load_default(size=26)
    except TypeError:   # Pillow < 10.1
        font = ImageFont.load_default()

    for case, frames in case_frames.items():
        imgs = [Image.open(f).convert("RGB") for _, f in frames]
        imgs[0].save(OUT / f"{case}.gif", save_all=True, append_images=imgs[1:],
                     duration=900, loop=0)
        log("wrote", OUT / f"{case}.gif")

    thumb_w = 360
    first = Image.open(next(iter(case_frames.values()))[0][1])
    thumb_h = round(first.height * thumb_w / first.width)
    label_w, label_h = 230, 48
    ncol = max(len(f) for f in case_frames.values())
    sheet = Image.new("RGB", (label_w + ncol * thumb_w, label_h + len(case_frames) * thumb_h), "white")
    draw = ImageDraw.Draw(sheet)
    for r, (case, frames) in enumerate(case_frames.items()):
        y = label_h + r * thumb_h
        draw.text((10, y + thumb_h // 2 - 14), case, fill="black", font=font)
        for c, (t, f) in enumerate(frames):
            x = label_w + c * thumb_w
            sheet.paste(Image.open(f).convert("RGB").resize((thumb_w, thumb_h)), (x, y))
            if r == 0:
                draw.text((x + thumb_w // 2 - 70, 10), f"t = {t * 1e3:.3g} ms", fill="black", font=font)
    out = OUT / f"montage_{re.sub(r'[^A-Za-z0-9_]+', '_', pattern)}.png"
    sheet.save(out)
    log("wrote", out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pattern", help="regex for case folders, e.g. fig4 or 'fig3_w1mm_ar1'")
    ap.add_argument("--field", default="h2o", help="contour field (h2o = contaminant tracer)")
    ap.add_argument("--procs", type=int, default=2)
    a = ap.parse_args()

    cases = sorted(d.name for d in RES.iterdir()
                   if d.is_dir() and re.search(a.pattern, d.name) and (d / "summary.json").exists())
    if not cases:
        raise SystemExit(f"no finished cases match '{a.pattern}'")
    log("cases:", cases)

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
            (OUT / case).mkdir(parents=True, exist_ok=True)
            read_case_data(solver, str(RES / case / f"{case}-t0.cas.h5"))
            contour = make_contour(solver, a.field)
            pics = []
            for i, (t, dat) in enumerate(frames):
                if i:
                    read_data(solver, dat)
                contour.display()
                png = OUT / case / f"frame_{i:02d}.png"
                save_picture(solver, png)
                pics.append((t, png))
            case_frames[case] = pics
    finally:
        solver.exit()
    if case_frames:
        assemble(case_frames, a.pattern)


if __name__ == "__main__":
    main()
