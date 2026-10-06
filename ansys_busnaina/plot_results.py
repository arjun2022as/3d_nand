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
    ax.legend(fontsize=8)
    return fig


def fig4(rows):
    fig, ax = plt.subplots(figsize=(6, 4.5))
    for r in rows:
        if r["case"].startswith("fig4") and (h := history(r["case"])):
            ax.semilogy(*h, label=r["figure_note"].replace("Fig 4 W=D=1um ", f"f={float(r['freq_Hz'])/1e3:g} kHz, "))
    ax.set(xlabel="Time (s)", ylabel="C / C0 in cavity",
           title="Fig. 4: W = D = 1 um, u_avg = 15 cm/s")
    ax.legend(fontsize=8)
    return fig


def main():
    rows = cases()
    for name, fn in (("fig2", fig2), ("fig3", fig3), ("fig4", fig4)):
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
