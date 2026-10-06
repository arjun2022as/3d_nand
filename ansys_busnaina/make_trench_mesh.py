#!/usr/bin/env python3
"""Write a 2D Fluent ASCII mesh (.msh) of a rinse channel over one rectangular trench.

Geometry follows Lin, Busnaina & Suni (2002), Fig. 1. y = 0 is the wafer surface.

     y=H  +------------------ top (symmetry = free surface) -----------------+
          |                                                                  |
   inlet  |                    fluid zone "channel"                          |  outlet
          |                                                                  |
     y=0  +------ wafer (wall) ------+-- mouth --+------ wafer (wall) -------+
                                     |           |
                                     |  "cavity" |  trench-walls (wall)
                                     |           |
    y=-D                             +-----------+
         x=-Lu                      x=0         x=W                       x=W+Ld

Uniform square cells of size h = W / n_per_w. Pure Python, no dependencies.

Fluent 2D face convention (ASCII format, section 13): each face is "n0 n1 c0 c1"
with c0 on the LEFT of the direction n0 -> n1, and c1 = 0 on boundaries. This is
the opposite of the 3D right-hand rule; the mesh is checked against it before writing.
"""
import argparse
import json
import sys

# Fluent bc-type codes (section 13) and zone type names (section 45)
BC = {"interior": 2, "wall": 3, "pressure-outlet": 5, "symmetry": 7, "velocity-inlet": 10}

FACE_ZONES = [  # (id, name, type) - written in this order, ids contiguous per zone
    (4, "interior-channel", "interior"),
    (5, "interior-cavity", "interior"),
    (6, "mouth", "interior"),
    (7, "inlet", "velocity-inlet"),
    (8, "outlet", "pressure-outlet"),
    (9, "top", "symmetry"),
    (10, "wafer", "wall"),
    (11, "trench-walls", "wall"),
]
CELL_ZONES = [(2, "channel"), (3, "cavity")]
NODE_ZONE_ID = 1


def build(W, D, H, Lu, Ld, n_per_w):
    h = W / n_per_w
    nu, nw, nd = max(1, round(Lu / h)), n_per_w, max(1, round(Ld / h))
    nh, ndp = max(1, round(H / h)), max(1, round(D / h))
    NX = nu + nw + nd

    xs = ([-Lu + Lu * i / nu for i in range(nu)]
          + [W * i / nw for i in range(nw)]
          + [W + Ld * i / nd for i in range(nd + 1)])
    ys = [-D + D * j / ndp for j in range(ndp)] + [H * j / nh for j in range(nh + 1)]

    # cells as lattice (i, j) of their lower-left corner; channel first, then cavity
    cells = [(i, j, 2) for j in range(ndp, ndp + nh) for i in range(NX)]
    cells += [(i, j, 3) for j in range(ndp) for i in range(nu, nu + nw)]

    used = set()
    for i, j, _ in cells:
        used.update({(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)})
    node_id, nodes = {}, []
    for ij in sorted(used, key=lambda t: (t[1], t[0])):
        node_id[ij] = len(nodes) + 1
        nodes.append((xs[ij[0]], ys[ij[1]]))

    # faces: walk each cell counter-clockwise, so the cell is on the left of p -> q (= c0)
    faces = {}
    for c, (i, j, _) in enumerate(cells, start=1):
        corners = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
        for k in range(4):
            p, q = node_id[corners[k]], node_id[corners[(k + 1) % 4]]
            key = (min(p, q), max(p, q))
            if key in faces:
                if faces[key][3]:
                    raise RuntimeError(f"face {key} shared by more than two cells")
                faces[key][3] = c
            else:
                faces[key] = [p, q, c, 0]

    zone_of_cell = [None] + [z for _, _, z in cells]
    tol = h * 1e-6
    by_zone = {zid: [] for zid, _, _ in FACE_ZONES}
    for f in faces.values():
        p, q, c0, c1 = f
        if c1:
            z0, z1 = zone_of_cell[c0], zone_of_cell[c1]
            by_zone[4 if z0 == z1 == 2 else 5 if z0 == z1 == 3 else 6].append(f)
            continue
        xm = 0.5 * (nodes[p - 1][0] + nodes[q - 1][0])
        ym = 0.5 * (nodes[p - 1][1] + nodes[q - 1][1])
        if abs(xm + Lu) < tol:
            by_zone[7].append(f)
        elif abs(xm - (W + Ld)) < tol:
            by_zone[8].append(f)
        elif abs(ym - H) < tol:
            by_zone[9].append(f)
        elif abs(ym) < tol:
            by_zone[10].append(f)
        else:
            by_zone[11].append(f)

    info = dict(h=h, n_cells=len(cells), n_nodes=len(nodes), n_faces=len(faces),
                n_channel=sum(1 for c in cells if c[2] == 2),
                n_cavity=sum(1 for c in cells if c[2] == 3),
                cells_x=[nu, nw, nd], cells_y=[ndp, nh])
    return nodes, cells, xs, ys, by_zone, info


def check(nodes, cells, xs, ys, by_zone, W, D, H, Lu, Ld):
    """Verify orientation, connectivity, boundary lengths and area before writing."""
    def centroid(c):
        i, j, _ = cells[c - 1]
        return 0.5 * (xs[i] + xs[i + 1]), 0.5 * (ys[j] + ys[j + 1])

    refs = [0] * (len(cells) + 1)
    for flist in by_zone.values():
        for p, q, c0, c1 in flist:
            (px, py), (qx, qy) = nodes[p - 1], nodes[q - 1]
            for c, sign in ((c0, 1), (c1, -1)):
                if not c:
                    continue
                cx, cy = centroid(c)
                cross = (qx - px) * (cy - py) - (qy - py) * (cx - px)
                if sign * cross <= 0:
                    raise RuntimeError(f"bad orientation: face {p}-{q}, cell {c}")
                refs[c] += 1
    if any(r != 4 for r in refs[1:]):
        raise RuntimeError("a cell does not have exactly 4 faces")

    def length(zid):
        return sum(abs(nodes[q - 1][0] - nodes[p - 1][0]) + abs(nodes[q - 1][1] - nodes[p - 1][1])
                   for p, q, _, _ in by_zone[zid])
    expect = {6: W, 7: H, 8: H, 9: Lu + W + Ld, 10: Lu + Ld, 11: 2 * D + W}
    for zid, L in expect.items():
        if abs(length(zid) - L) > 1e-9 * L:
            raise RuntimeError(f"zone {zid} length {length(zid)} != {L}")

    area = sum((xs[i + 1] - xs[i]) * (ys[j + 1] - ys[j]) for i, j, _ in cells)
    expect_area = (Lu + W + Ld) * H + W * D
    if abs(area - expect_area) > 1e-9 * expect_area:
        raise RuntimeError(f"area {area} != {expect_area}")


def write_msh(path, nodes, cells, by_zone, title):
    nn, nc = len(nodes), len(cells)
    nf = sum(len(v) for v in by_zone.values())
    nch = sum(1 for c in cells if c[2] == 2)
    with open(path, "w", newline="\n") as f:
        f.write(f'(0 "{title}")\n(2 2)\n')
        f.write(f"(10 (0 1 {nn:x} 0 2))\n(12 (0 1 {nc:x} 0))\n(13 (0 1 {nf:x} 0))\n")

        f.write(f"(10 ({NODE_ZONE_ID:x} 1 {nn:x} 1 2)(\n")
        f.writelines(f"{x:.15e} {y:.15e}\n" for x, y in nodes)
        f.write("))\n")

        f.write(f"(12 (2 1 {nch:x} 1 3))\n")
        f.write(f"(12 (3 {nch + 1:x} {nc:x} 1 3))\n")

        first = 1
        for zid, _, ztype in FACE_ZONES:
            flist = by_zone[zid]
            last = first + len(flist) - 1
            f.write(f"(13 ({zid:x} {first:x} {last:x} {BC[ztype]:x} 2)(\n")
            f.writelines(f"{p:x} {q:x} {c0:x} {c1:x}\n" for p, q, c0, c1 in flist)
            f.write("))\n")
            first = last + 1

        for zid, name in CELL_ZONES:
            f.write(f"(45 ({zid} fluid {name})())\n")
        for zid, name, ztype in FACE_ZONES:
            f.write(f"(45 ({zid} {ztype} {name})())\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--W", type=float, required=True, help="trench width [m]")
    ap.add_argument("--AR", type=float, default=1.0, help="aspect ratio D/W")
    ap.add_argument("--H", type=float, default=2.5, help="channel height / W")
    ap.add_argument("--Lu", type=float, default=2.0, help="upstream length / W")
    ap.add_argument("--Ld", type=float, default=3.0, help="downstream length / W")
    ap.add_argument("--n-per-w", type=int, default=40, help="cells across the trench width")
    ap.add_argument("-o", "--out", required=True, help="output .msh path")
    a = ap.parse_args(argv)

    W = a.W
    D, H, Lu, Ld = a.AR * W, a.H * W, a.Lu * W, a.Ld * W
    nodes, cells, xs, ys, by_zone, info = build(W, D, H, Lu, Ld, a.n_per_w)
    check(nodes, cells, xs, ys, by_zone, W, D, H, Lu, Ld)
    title = f"Trench W={W:g} m D={D:g} m H={H:g} m, {a.n_per_w} cells/W"
    write_msh(a.out, nodes, cells, by_zone, title)
    info.update(W=W, D=D, H=H, Lu=Lu, Ld=Ld, msh=a.out)
    print(json.dumps(info))
    return info


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
