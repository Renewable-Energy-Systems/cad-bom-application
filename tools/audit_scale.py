"""Report how much of the drawing area each sheet actually uses.

    python tools/audit_scale.py

A drawing that fills only half the sheet is drawn smaller than it needs to be:
the dimensions crowd together and the part reads as less important than it is.
This measures the bounding box of everything drawn — geometry and labels — as a
percentage of the drawing area, and lists the sheets from smallest to largest.

Anything under about 62% is worth looking at. Strips and pins are narrow by
nature, so judge them on the long axis (the `fill%` column) rather than on width.
Above 99% the sheet is full and a label may be about to run off the edge — check
it against tools/audit_dimensions.py, which is the authority on that.

Both tools share the fixtures in audit_dimensions.py; no battery data is read.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from audit_dimensions import FIX, FN, AX0, AY0, AX1, AY1, boxes   # noqa: E402

NUM = r"-?\d+(?:\.\d+)?"
RE_LINE = re.compile(rf'<line x1="({NUM})" y1="({NUM})" x2="({NUM})" y2="({NUM})"')
RE_RECT = re.compile(rf'<rect x="({NUM})" y="({NUM})" width="({NUM})" height="({NUM})"')
RE_CIRC = re.compile(rf'<circle cx="({NUM})" cy="({NUM})" r="({NUM})"')
RE_ELL = re.compile(rf'<ellipse cx="({NUM})" cy="({NUM})" rx="({NUM})" ry="({NUM})"')
RE_PTS = re.compile(r'<poly(?:line|gon) points="([^"]+)"')
RE_PATH = re.compile(r'<path d="([^"]+)"')
RE_IMG = re.compile(rf'<image x="({NUM})" y="({NUM})" width="({NUM})" height="({NUM})"')


def geom_bbox(svg):
    xs, ys = [], []

    # Strictly inside the drawing area. The page border and the header/footer
    # furniture span the whole sheet, and counting them makes every drawing look
    # like it fills 100%.
    def add(x, y):
        if AX0 <= x <= AX1 and AY0 <= y <= AY1:
            xs.append(x)
            ys.append(y)

    for m in RE_LINE.finditer(svg):
        x1, y1, x2, y2 = map(float, m.groups())
        add(x1, y1)
        add(x2, y2)
    for r in (RE_RECT, RE_IMG):
        for m in r.finditer(svg):
            x, y, w, h = map(float, m.groups())
            add(x, y)
            add(x + w, y + h)
    for m in RE_CIRC.finditer(svg):
        cx, cy, rad = map(float, m.groups())
        add(cx - rad, cy - rad)
        add(cx + rad, cy + rad)
    for m in RE_ELL.finditer(svg):
        cx, cy, rx, ry = map(float, m.groups())
        add(cx - rx, cy - ry)
        add(cx + rx, cy + ry)
    for m in RE_PTS.finditer(svg):
        for q in m.group(1).split():
            if "," in q:
                a, b = q.split(",")
                add(float(a), float(b))
    for m in RE_PATH.finditer(svg):
        vals = [float(v) for v in re.findall(NUM, m.group(1))]
        for i in range(0, len(vals) - 1, 2):
            add(vals[i], vals[i + 1])
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def main():
    aw, ah = AX1 - AX0, AY1 - AY0
    rows = []
    for key, Model, kw in FIX:
        try:
            svg = FN[key](Model(**kw), user="scale")["svg"]
        except Exception as e:                                  # noqa: BLE001
            print(f"{key:<32} FAILED {type(e).__name__}: {e}")
            continue
        gb = geom_bbox(svg)
        if not gb:
            continue
        tb = [b for b in boxes(svg)
              if AY0 <= (b[1] + b[3]) / 2 <= AY1 and AX0 <= (b[0] + b[2]) / 2 <= AX1]
        if tb:                       # the sheet has to hold the labels too
            gb = (min([gb[0]] + [b[0] for b in tb]), min([gb[1]] + [b[1] for b in tb]),
                  max([gb[2]] + [b[2] for b in tb]), max([gb[3]] + [b[3] for b in tb]))
        w, h = gb[2] - gb[0], gb[3] - gb[1]
        rows.append((key, w / aw * 100, h / ah * 100, max(w / aw, h / ah) * 100))

    rows.sort(key=lambda r: r[3])
    print(f"{'drawing':<32} {'width%':>7} {'height%':>8} {'fill%':>7}")
    print("-" * 58)
    for k, pw, ph, f in rows:
        flag = "  <- small" if f < 62 else ("  <- full" if f > 99 else "")
        print(f"{k:<32} {pw:>7.0f} {ph:>8.0f} {f:>7.0f}{flag}")
    fills = sorted(r[3] for r in rows)
    print(f"\nmedian fill {fills[len(fills) // 2]:.0f}%   "
          f"under 62%: {sum(1 for r in rows if r[3] < 62)} of {len(rows)}")


if __name__ == "__main__":
    main()
