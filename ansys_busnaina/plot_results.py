#!/usr/bin/env python3
"""Plot results/<case>/history.csv in the layout of the paper's Figs. 2-4.

    python plot_results.py            # writes fig2.png, fig3.png, fig4.png in results/
"""
import csv
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
RES = HERE / "results"
# cases overlaid on their fig4 baseline in conv.png (the mesh study has its own plot)
CONV_PLOT = {"conv_f20k_n80", "conv_f200k_n80", "conv_f20k_n40dt", "conv_f20k_n80mesh", "conv_f20k_n40tight"}


def history(case):
    f = RES / case / "history.csv"
    if not f.exists():
        return None
    t, c = [], []
    with open(f, newline="") as fh:
        for row in csv.DictReader(fh):
            t.append(float(row["time_s"]))
            c.append(float(row["c_cavity"]))
    if len(t) < 2:
        print(f"{case}: history.csv has no data (run incomplete or overwritten)")
        return None
    return t, c


def cases():
    with open(HERE / "cases.csv", newline="") as fh:
        return list(csv.DictReader(fh))


def fig2(rows):
    fig, ax = plt.subplots(figsize=(6, 4.5))
    for r in rows:
        if r["case"].startswith("fig2") and (h := history(r["case"])):
            ax.plot(*h, label=r["figure_note"].replace("Fig 2 ", ""))
    ax.set(xlabel="Time (s)", ylabel="C / C0 in cavity",
           title="Fig. 2: W = 1 mm, u_avg = 15 cm/s", ylim=(0, 1.05))
    if ax.lines:
        ax.legend(fontsize=8)
    return fig


def fig3(rows):
    series = {}
    for r in rows:
        m = re.match(r"fig3_(.+)_st([\d.]+)$", r["case"])
        if m and (h := history(r["case"])):
            series.setdefault(r["figure_note"].replace("Fig 3 ", ""), []).append(
                (float(m.group(2)), 100 * (1 - h[1][-1])))
    fig, ax = plt.subplots(figsize=(6, 4.5))
    for label, pts in series.items():
        pts.sort()
        ax.semilogx(*zip(*pts), "o-", label=label)
    ax.set(xlabel="St = W f / Up", ylabel="Cleaning efficiency (%)",
           title="Fig. 3: effect of Strouhal number", ylim=(0, 100))
    if ax.lines:
        ax.legend(fontsize=8)
    return fig


def fig4(rows):
    fig, ax = plt.subplots(figsize=(6, 4.5))
    for r in rows:
        if r["case"].startswith("fig4") and (h := history(r["case"])):
            ax.semilogy([t * 1e3 for t in h[0]], h[1], label=r["figure_note"].replace("Fig 4 W=D=1um ", f"f={float(r['freq_Hz'])/1e3:g} kHz, "))
    ax.set(xlabel="Time (ms)", ylabel="C / C0 in cavity",
           title="Fig. 4: W = D = 1 um, u_avg = 15 cm/s")
    if ax.lines:
        ax.legend(fontsize=8)
    return fig


def conv(rows):
    """Convergence cases conv_<freq>_* overlaid on the matching fig4_<freq> run."""
    fig, ax = plt.subplots(figsize=(6.5, 4.8))
    colors = {}
    for r in rows:
        if r["case"] not in CONV_PLOT:
            continue
        freq = r["case"].split("_")[1]
        base, fine = history(f"fig4_{freq}"), history(r["case"])
        if not (base and fine):
            continue
        if freq not in colors:
            line, = ax.semilogy([t * 1e3 for t in base[0]], base[1], lw=2.5,
                                label=f"{freq}: baseline (40 cells/W)")
            colors[freq] = line.get_color()
        label = r["figure_note"].split(" with ")[-1]
        ax.semilogy([t * 1e3 for t in fine[0]], fine[1], "--", label=f"{freq}: {label}")
        diff = 100 * abs(fine[1][-1] - base[1][-1]) / base[1][-1]
        print(f"{r['case']:24s} final C/C0 = {fine[1][-1]:.4f}  vs baseline {base[1][-1]:.4f}"
              f"  ({diff:.1f} % difference)")
    ax.set(xlabel="Time (ms)", ylabel="C / C0 in cavity",
           title="Convergence: thick = baseline, dashed = refined")
    if ax.lines:
        ax.legend(fontsize=7)
    return fig


def extrapolate(pts):
    """Fit C(n) = C_inf + K n^-p through the three finest points (p by bisection); None if not monotonic."""
    (n1, c1), (n2, c2), (n3, c3) = pts[-3:]

    def ratio(p):
        return (n2 ** -p - n1 ** -p) / (n3 ** -p - n2 ** -p)

    if c3 == c2:
        return None
    target = (c2 - c1) / (c3 - c2)
    lo, hi = 0.05, 10.0
    if (ratio(lo) - target) * (ratio(hi) - target) >= 0:
        return None
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if (ratio(lo) - target) * (ratio(mid) - target) > 0 else (lo, mid)
    p = 0.5 * (lo + hi)
    return p, c3 - (c3 - c2) / (n3 ** -p - n2 ** -p) * n3 ** -p


def meshstudy(rows):
    """Final C/C0 vs cells/W at 20 kHz: fixed time step vs time step refined with the mesh."""
    finals = {r["case"]: h[1][-1] for r in rows
              if r["case"].startswith("conv_f20k_") and (h := history(r["case"]))}

    def pick(suffix):
        return [(int(m.group(1)), v) for k, v in finals.items()
                if (m := re.match(rf"conv_f20k_n(\d+){suffix}$", k))]

    series = {
        "fixed time step (Courant 1-4)": pick("tight"),
        # 40 cells/W at Courant 1 is the shared starting point of both series
        "time step refined with mesh (Courant 1)": pick("cfl1") + [p for p in pick("tight") if p[0] == 40],
    }
    fig, ax = plt.subplots(figsize=(6.5, 4.8))
    for label, pts in series.items():
        pts.sort()
        if len(pts) < 2:
            continue
        n, c = zip(*pts)
        line, = ax.plot(n, c, "o-", label=label)
        print(f"mesh study, {label}:")
        for i, (ni, ci) in enumerate(pts):
            change = "" if i == 0 else f"  change {100 * abs(ci - pts[i - 1][1]) / ci:.1f} %"
            print(f"    {ni:4d} cells/W  final C/C0 = {ci:.5f}{change}")
        if len(pts) >= 3:
            ext = extrapolate(pts)
            if ext:
                p, c_ext = ext
                ax.axhline(c_ext, ls=":", color=line.get_color(),
                           label=f"extrapolated {c_ext:.4f} (order {p:.1f})")
                print(f"    observed order p = {p:.2f}, extrapolated C/C0 = {c_ext:.5f}, "
                      f"finest-mesh error = {100 * abs(pts[-1][1] - c_ext) / c_ext:.1f} %")
            else:
                print("    not converging monotonically: no extrapolation")
    if "conv_f20k_n40it50" in finals and "conv_f20k_n40tight" in finals:
        a, b = finals["conv_f20k_n40tight"], finals["conv_f20k_n40it50"]
        print(f"iteration check (40 cells/W): 20 it/step C/C0 = {a:.5f}, 50 it/step = {b:.5f}"
              f"  ({100 * abs(b - a) / b:.1f} % difference)")
    ax.set(xlabel="Cells across trench width", ylabel="Final C/C0 (t = 0.4 ms)",
           title="Mesh study: W = D = 1 um, f = 20 kHz, residuals 1e-6")
    if ax.lines:
        ax.legend(fontsize=7)
    return fig


def main():
    rows = cases()
    for name, fn in (("fig2", fig2), ("fig3", fig3), ("fig4", fig4), ("conv", conv),
                     ("meshstudy", meshstudy)):
        fig = fn(rows)
        if fig.axes[0].lines:
            fig.tight_layout()
            fig.savefig(RES / f"{name}.png", dpi=150)
            print("wrote", RES / f"{name}.png")
        else:
            print(f"{name}: no finished cases yet")
        plt.close(fig)


if __name__ == "__main__":
    RES.mkdir(exist_ok=True)
    main()
