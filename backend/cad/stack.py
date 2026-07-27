"""Stack drawing (RES format).

The single cells arranged into a stack: CELL-N at the top down to CELL-01 at the
bottom, each cell drawn as a small banded 'building block', staggered left/right.
For a tall stack only the top two and bottom two cells are drawn with a vertical
ellipsis in between. `num_stacks` (stacks in parallel) draws that many columns
(STACK-1, STACK-2, ...). Each shown cell gets a "CELL-<n>" leader.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .container import (PW, PH, AREA, THICK, MED, THIN, _n, line, rect, circle,
                        text, arrow, _header, _footer)

_CELL_SHADES = ["#cfcfcf", "#a3a3a3", "#484848", "#8d8d8d", "#bebebe", "#6f6f6f"]


@dataclass
class StackParams:
    num_cells: int
    num_stacks: int = 1
    component_name: str = "STACK"
    material: str = "—"
    project: str = ""
    drawing_no: str = "RES-__-__"
    battery_code: str = ""
    weight: str = ""
    quantity: str = "01"
    date: str = ""
    show_bom: bool = False
    revisions: list = field(default_factory=list)


@dataclass
class StackGeom:
    num_cells: int
    num_stacks: int
    warnings: list = field(default_factory=list)


def compute_stack(p: StackParams) -> StackGeom:
    return StackGeom(num_cells=max(int(p.num_cells), 1),
                     num_stacks=max(int(p.num_stacks), 1), warnings=[])


def _cell_block(x0, y0, w, h):
    n = len(_CELL_SHADES)
    bh = h / n
    out = []
    for i, sh in enumerate(_CELL_SHADES):
        out.append(rect(x0, y0 + i * bh, w, bh, MED, fill=sh))
    out.append(rect(x0, y0, w, h, THICK))
    return out


def _views(g: StackGeom, p: StackParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    N, S = g.num_cells, g.num_stacks
    colw = (ax1 - ax0) / S
    cbw = min(colw * 0.42, 32.0)
    stag = cbw * 0.32
    cbh = 13.0
    step = cbh * 0.86
    y_top = ay0 + 10
    y_lbl = ay1 - 4
    y_bot = y_lbl - 10 - cbh                      # bottom cell top-y

    for si in range(S):
        cxc = ax0 + colw * (si + 0.5)
        tx = min(cxc + cbw * 0.5 + 12, ax1 - 15)  # leader text x (clamped in column)

        def cell(cell_no, yc):
            off = -stag if cell_no % 2 == 0 else stag       # even left, odd right
            x0 = cxc + off - cbw / 2
            s.extend(_cell_block(x0, yc, cbw, cbh))
            yl = yc + cbh * 0.42
            s.append(line(x0 + cbw, yl, tx - 1, yl, THIN))
            s.append(arrow(x0 + cbw, yl, -1, 0))
            s.append(text(tx, yl + 0.9, f"CELL-{cell_no:02d}", 1.9, anchor="start"))

        if N <= 4:
            for i, cno in enumerate(range(N, 0, -1)):
                cell(cno, y_top + i * step)
        else:
            cell(N, y_top)
            cell(N - 1, y_top + step)
            cell(2, y_bot - step)
            cell(1, y_bot)
            # vertical ellipsis between
            d0 = y_top + 2 * step + 6
            d1 = y_bot - step - 6
            for k in range(6):
                cy = d0 + (d1 - d0) * k / 5
                s.append(circle(cxc, cy, 1.1, THIN, fill="#111"))

        s.append(text(cxc, y_lbl, f"STACK -{si + 1}", 2.8, weight="bold"))
        if si < S - 1:                            # divider between columns
            xd = ax0 + colw * (si + 1)
            s.append(line(xd, ay0 + 2, xd, ay1, THIN))
    return s


def render_stack_svg(g: StackGeom, p: StackParams) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(PW)} {int(PH)}" '
             f'font-family="Arial, sans-serif">',
             '<rect x="0" y="0" width="210" height="297" fill="#fff"/>']
    parts += _header(g, p)
    parts += _views(g, p)
    parts += _footer(g, p)
    parts.append("</svg>")
    return "".join(parts)
