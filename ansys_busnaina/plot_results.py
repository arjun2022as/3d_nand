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
        if not r["case"].startswith("conv_") or "tight" in r["case"] and "n40" not in r["case"]:
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


def meshstudy(rows):
    """Final C/C0 vs cells across the trench for conv_f20k_n<N>tight, with Richardson extrapolation."""
    pts = []
    for r in rows:
        m = re.match(r"conv_f20k_n(\d+)tight$", r["case"])
        if m and (h := history(r["case"])):
            pts.append((int(m.group(1)), h[1][-1]))
    pts.sort()
    fig, ax = plt.subplots(figsize=(6, 4.5))
    if not pts:
        return fig
    n, c = zip(*pts)
    ax.plot(n, c, "o-", label="20 kHz, residuals 1e-6")
    for ni, ci in pts:
        print(f"mesh study: {ni:4d} cells/W  final C/C0 = {ci:.5f}")
    for i in range(1, len(pts)):
        print(f"            {n[i-1]} -> {n[i]} cells/W: change {100 * abs(c[i] - c[i-1]) / c[i]:.1f} %")
    if len(pts) >= 3:
        # fit C(n) = C_inf + K * n**-p through the three finest meshes (p by bisection)
        (n1, c1), (n2, c2), (n3, c3) = pts[-3:]

        def ratio(p):
            return (n2 ** -p - n1 ** -p) / (n3 ** -p - n2 ** -p)

        target = (c2 - c1) / (c3 - c2) if c3 != c2 else float("inf")
        lo, hi = 0.05, 10.0
        if (ratio(lo) - target) * (ratio(hi) - target) < 0:
            for _ in range(200):
                mid = 0.5 * (lo + hi)
                lo, hi = (mid, hi) if (ratio(lo) - target) * (ratio(mid) - target) > 0 else (lo, mid)
            p = 0.5 * (lo + hi)
            K = (c3 - c2) / (n3 ** -p - n2 ** -p)
            c_ext = c3 - K * n3 ** -p
            ax.axhline(c_ext, ls=":", color="gray", label=f"extrapolated ({c_ext:.4f})")
            print(f"            observed order p = {p:.2f}, extrapolated C/C0 = {c_ext:.5f}, "
                  f"finest-mesh error = {100 * abs(c3 - c_ext) / c_ext:.1f} %")
        else:
            print("            not converging monotonically: no extrapolation")
    ax.set(xlabel="Cells across trench width", ylabel="Final C/C0 (t = 0.4 ms)",
           title="Mesh study: W = D = 1 um, f = 20 kHz")
    ax.legend(fontsize=8)
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
