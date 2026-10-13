#!/usr/bin/env python3
"""Compare the Fig. 4 frequencies: which one cleans the 1 um trench the most?

Reads results/fig4_*/history.csv (and, if present, the last frame from make_movies.sh) and writes
    results/fig4_comparison.png   4-panel slide figure
    results/fig4_comparison.csv   ranking table
Run on a compute node or OOD desktop (needs matplotlib from the venv):
    source ~/venvs/pyfluent241/bin/activate && python compare_fig4.py
"""
import csv
import math
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
RES = HERE / "results"
UNCERTAINTY = 0.10   # ~10 % on C/C0 from the mesh study (40/80/120 cells/W at Courant 1)


def load():
    runs = []
    with open(HERE / "cases.csv", newline="") as f:
        for row in csv.DictReader(f):
            if not re.fullmatch(r"fig4_f\d+k", row["case"]):
                continue
            h = RES / row["case"] / "history.csv"
            if not h.exists():
                print(f"{row['case']}: no history.csv, skipped")
                continue
            with open(h, newline="") as fh:
                data = [(float(r["time_s"]), float(r["c_cavity"])) for r in csv.DictReader(fh)]
            if len(data) < 2:
                print(f"{row['case']}: history.csv empty, skipped")
                continue
            f_hz = float(row["freq_Hz"])
            up = math.pi * float(row["u_avg_m_s"])
            runs.append(dict(case=row["case"], f_khz=f_hz / 1e3, St=float(row["W_m"]) * f_hz / up,
                             t=[d[0] for d in data], c=[d[1] for d in data]))
    runs.sort(key=lambda r: r["f_khz"])
    for r in runs:
        r["c_end"] = r["c"][-1]
        r["eff"] = 100 * (1 - r["c_end"])
        r["t90_ms"] = time_to(r, 0.10)
    return runs


def time_to(r, level):
    """First time C/C0 drops to `level` (linear interpolation), in ms; None if never."""
    for (t0, c0), (t1, c1) in zip(zip(r["t"], r["c"]), zip(r["t"][1:], r["c"][1:])):
        if c1 <= level < c0:
            return 1e3 * (t0 + (c0 - level) / (c0 - c1) * (t1 - t0))
    return None


def last_frame(case):
    frames = sorted((RES / "movies" / case).glob("frame_*.png"))
    return frames[-1] if frames else None


def label(r):
    f = r["f_khz"]
    return f"{f / 1e3:g} MHz" if f >= 1000 else f"{f:g} kHz"


def main():
    runs = load()
    if not runs:
        raise SystemExit("no finished fig4_* runs found")
    best = min(runs, key=lambda r: r["c_end"])
    # runs whose result overlaps the best one within the numerical uncertainty count as tied
    tied = [r for r in runs if r["c_end"] * (1 - UNCERTAINTY) <= best["c_end"] * (1 + UNCERTAINTY)]
    colors = plt.cm.viridis([i / max(1, len(runs) - 1) for i in range(len(runs))])
    frames = [last_frame(r["case"]) for r in runs]
    have_frames = all(frames)

    # 3 panels on top; optional row of final contour images below (one per frequency)
    ncol = 3 * len(runs)
    fig = plt.figure(figsize=(16, 8.6 if have_frames else 5.4))
    gs = fig.add_gridspec(2 if have_frames else 1, ncol, height_ratios=[1.6, 1] if have_frames else [1])
    third = ncol // 3
    ax_a = fig.add_subplot(gs[0, :third])
    ax_b = fig.add_subplot(gs[0, third:2 * third])
    ax_c = fig.add_subplot(gs[0, 2 * third:])

    # (a) decay curves
    for r, col in zip(runs, colors):
        ax_a.semilogy([t * 1e3 for t in r["t"]], r["c"], color=col, lw=2.5 if r is best else 1.6,
                      label=f"{label(r)} (St={r['St']:.3g})")
    ax_a.axhline(0.10, ls=":", color="gray")
    ax_a.text(0.01, 0.105, "90 % removed", color="gray", fontsize=8)
    ax_a.set(xlabel="Time (ms)", ylabel="Contaminant left in trench, C/C0",
             title="(a) Cleaning over time")
    ax_a.legend(fontsize=8)

    # (b) contaminant left at the end, with ~10 % numerical uncertainty
    names = [label(r) for r in runs]
    left = [100 * r["c_end"] for r in runs]
    bars = ax_b.bar(names, left, color=colors, yerr=[UNCERTAINTY * v for v in left], capsize=4,
                    edgecolor=["black" if r in tied else "none" for r in runs], linewidth=2)
    for b, r in zip(bars, runs):
        ax_b.text(b.get_x() + b.get_width() / 2, b.get_height() * 1.12, f"{r['eff']:.1f} %\ncleaned",
                  ha="center", fontsize=8, fontweight="bold" if r in tied else "normal")
    if len(tied) > 1:
        title_b = (f"(b) Most effective: {label(tied[0])} to {label(tied[-1])}\n"
                   f"(lowest {label(best)}; outlined bars tied within +/-{UNCERTAINTY:.0%})")
    else:
        title_b = f"(b) Most effective: {label(best)}"
    ax_b.set(ylabel="Contaminant left at t = 0.4 ms (%)", ylim=(0, max(left) * 1.45), title=title_b)

    # (c) time to remove 90 %
    t90 = [r["t90_ms"] if r["t90_ms"] is not None else float("nan") for r in runs]
    bars = ax_c.bar(names, t90, color=colors)
    for b, v in zip(bars, t90):
        if not math.isnan(v):
            ax_c.text(b.get_x() + b.get_width() / 2, v * 1.02, f"{v:.3f}", ha="center", fontsize=8)
    ax_c.set(ylabel="Time to remove 90 % (ms)", title="(c) Speed of cleaning (lower = faster)")

    # (d) final contaminant field per frequency
    if have_frames:
        from PIL import Image
        for i, (r, fr) in enumerate(zip(runs, frames)):
            ax = fig.add_subplot(gs[1, 3 * i:3 * i + 3])
            ax.imshow(Image.open(fr))
            ax.set_title(f"{label(r)}: final field", fontsize=9)
            ax.axis("off")

    fig.suptitle("Fig. 4 comparison: W = D = 1 um trench, mean rinse velocity 15 cm/s, t = 0.4 ms",
                 fontsize=13)
    fig.text(0.5, 0.005, "Error bars: ~10 % numerical uncertainty from the mesh/time-step study. "
             "Differences smaller than that are not significant.", ha="center", fontsize=8, color="gray")
    fig.tight_layout(rect=(0, 0.02, 1, 0.96))
    out = RES / "fig4_comparison.png"
    fig.savefig(out, dpi=150)
    print("wrote", out)

    ranked = sorted(runs, key=lambda r: r["c_end"])
    with open(RES / "fig4_comparison.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank", "frequency", "St", "C/C0 at 0.4 ms", "cleaning efficiency %", "time to 90 % (ms)"])
        for i, r in enumerate(ranked, 1):
            w.writerow([i, label(r), f"{r['St']:.4g}", f"{r['c_end']:.4f}", f"{r['eff']:.2f}",
                        "" if r["t90_ms"] is None else f"{r['t90_ms']:.4f}"])
    print(f"\n{'rank':>4}  {'frequency':>10}  {'St':>7}  {'C/C0':>7}  {'cleaned':>8}  {'t90 (ms)':>9}")
    for i, r in enumerate(ranked, 1):
        t90s = "-" if r["t90_ms"] is None else f"{r['t90_ms']:.4f}"
        print(f"{i:>4}  {label(r):>10}  {r['St']:7.3g}  {r['c_end']:7.4f}  {r['eff']:7.2f}%  {t90s:>9}")
    print("\ntied with the best within the ~10 % uncertainty:", ", ".join(label(r) for r in tied))
    worst = max(runs, key=lambda r: r["c_end"])
    spread = (worst["c_end"] - best["c_end"]) / best["c_end"]
    print(f"\nbest {label(best)}, worst {label(worst)}: {100 * spread:.0f} % more contaminant left at the worst "
          f"({'beyond' if spread > 2 * UNCERTAINTY else 'within'} the ~10 % numerical uncertainty)")


if __name__ == "__main__":
    main()
