"""Check every generated drawing for unreadable dimensioning.

    python tools/audit_dimensions.py

Renders all 47 components from fixtures held here — no battery data is read or
written — then parses each SVG and reports three faults:

  text on text      two labels overlapping, so a value cannot be read
  text on geometry  a label printed over the part itself. Dimension and
                    extension lines are thin (0.16) and a value may sit on one;
                    the part is drawn heavy (>= 0.22), so a hit there is real
  text off sheet    a label pushed outside the drawing area, usually a long
                    callout on a large part

A clean run prints zeros. Add a fixture here whenever a component is added, or
it simply will not be checked.

Note when reading the code: SVG attributes must be pulled out one at a time.
Matching them in a single pattern with an optional `transform` group lets the
engine skip the rotation, which measures every rotated label as horizontal and
invents overlaps that are not there.
"""
import math
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend import main as M

# drawing area (backend/cad/container.py AREA) — ignore header/title block text
AX0, AY0, AX1, AY1 = 8.0, 26.0, 202.0, 203.0

OD, HT, CATH = 57.0, 69.0, 37.0

FIX = [
    ("container", M.ContainerRequest, dict(od=OD, height=HT)),
    ("lid_blank", M.LidRequest, dict(container_od=OD, cathode_dia=CATH, pcd=32.0,
                                     num_holes=4, pin_diameter=1.6)),
    ("deliver_pin", M.DeliverPinRequest, dict(pin_dia=1.6, upper_part=3.0,
                                              lid_thickness=4.0, bottom_side=2.0)),
    ("squib", M.SquibRequest, dict(squib_type="single_head")),
    ("squib_wired", M.SquibRequest, dict(squib_type="single_head_wired")),
    ("tie_wire", M.TieWireRequest, dict(container_od=OD, container_height=HT)),
    ("teflon_disc", M.TeflonRequest, dict(lid_diameter=54.75, cathode_dia=CATH,
                                          pcd=32.0, num_holes=4, num_wires=3)),
    ("mica_disc_holes", M.MicaHolesRequest, dict(dia=CATH, pcd=32.0, num_holes=6,
                                                 hole_dia=2.0)),
    ("housing_a", M.HousingARequest, dict(outer_dia=CATH, inner_dia=34.0)),
    ("housing_b", M.HousingBRequest, dict(outer_dia=53.8, inner_dia=35.0)),
    ("silicon_ring_a", M.SiliconRingARequest, dict(outer_dia=CATH, inner_dia=34.0)),
    ("silicon_ring_b", M.SiliconRingBRequest, dict(outer_dia=53.8, inner_dia=35.0)),
    ("mica_ring", M.MicaRingRequest, dict(outer_dia=CATH, inner_dia=34.0)),
    ("pyro_wick", M.PyroWickRequest, dict(length=47.0, width=3.0, thickness=0.3)),
    ("pyro_wick_02", M.PyroWick02Request, dict(length=89.0, width=3.0, thickness=0.3)),
    ("samica_strip", M.StripRequest, dict(length=89.0, width=6.0, thickness=0.1)),
    ("mica_strip", M.StripRequest, dict(length=89.0, width=10.0, thickness=0.15)),
    ("glass_cloth_tape", M.GlassClothTapeRequest, dict(length=420.0, width=25.0, thickness=0.2)),
    ("adhesive_tape", M.AdhesiveTapeRequest, dict(length=100.0, width=12.5, thickness=0.2)),
    ("samica_wrap", M.SamicaWrapRequest, dict(length=133.0, width=66.0, thickness=0.1)),
    ("mica_wrap", M.MicaWrapRequest, dict(length=182.0, width=66.0, thickness=0.1)),
    ("fiberfrax_stack_wrap", M.FiberfraxSheetRequest, dict(base_length=116.0, width=66.0, thickness=1.0)),
    ("fiberfrax_container_insulation", M.FiberfraxSheetRequest, dict(base_length=172.0, width=66.0, thickness=1.0)),
    ("squib_terminal", M.SquibTerminalRequest, dict(length=50.0, width=3.0, thickness=0.2)),
    ("mica_disc_cuts", M.MicaDiscCutsRequest, dict(disc_dia=CATH, cut_length=14.5, cut_width=5.8)),
    ("fiberfrax_disc_cuts", M.MicaDiscCutsRequest, dict(disc_dia=CATH, cut_length=14.5, cut_width=5.8)),
    ("lid_tie_wire", M.LidTieWireRequest, dict(lid_od=54.75, lid_thickness=4.0, pcd=32.0,
                                               num_holes=4, hole_dia=4.0, stack_dia=CATH,
                                               num_tie_wires=3, wire_width=3.0, wire_thickness=0.3)),
    ("current_collector_anode", M.CurrentCollectorRequest, dict(disc_dia=CATH)),
    ("current_collector_cathode", M.CurrentCollectorRequest, dict(disc_dia=CATH)),
    ("brace_plate", M.BracePlateRequest, dict(cathode_dia=CATH)),
    ("lid_assembly", M.LidAssemblyRequest, dict(lid_od=54.75, lid_thickness=4.0, pcd=32.0,
                                                num_holes=4, hole_dia=4.0, pin_dia=1.6,
                                                upper_part=3.0, bottom_side=2.0)),
    ("stack", M.StackRequest, dict(num_cells=10, num_stacks=1)),
    ("stack_assembly", M.StackAssemblyRequest, dict(stack_type="one_stack")),
]
for k in M.PELLET_SPECS:
    FIX.append((k, M.PelletRequest, dict(ctype=k, dia=CATH, thickness=1.0)))

FN = {
    "container": M.cad_container, "lid_blank": M.cad_lid, "deliver_pin": M.cad_deliver_pin,
    "squib": M.cad_squib, "squib_wired": M.cad_squib, "tie_wire": M.cad_tie_wire,
    "teflon_disc": M.cad_teflon, "mica_disc_holes": M.cad_mica_holes,
    "housing_a": M.cad_housing_a, "housing_b": M.cad_housing_b,
    "silicon_ring_a": M.cad_silicon_ring_a, "silicon_ring_b": M.cad_silicon_ring_b,
    "mica_ring": M.cad_mica_ring, "pyro_wick": M.cad_pyro_wick,
    "pyro_wick_02": M.cad_pyro_wick_02, "samica_strip": M.cad_samica_strip,
    "mica_strip": M.cad_mica_strip, "glass_cloth_tape": M.cad_glass_cloth_tape,
    "adhesive_tape": M.cad_adhesive_tape, "samica_wrap": M.cad_samica_wrap,
    "mica_wrap": M.cad_mica_wrap, "fiberfrax_stack_wrap": M.cad_fiberfrax_stack_wrap,
    "fiberfrax_container_insulation": M.cad_fiberfrax_container_insulation,
    "squib_terminal": M.cad_squib_terminal, "mica_disc_cuts": M.cad_mica_disc_cuts,
    "fiberfrax_disc_cuts": M.cad_fiberfrax_disc_cuts, "lid_tie_wire": M.cad_lid_tie_wire,
    "current_collector_anode": M.cad_current_collector_anode,
    "current_collector_cathode": M.cad_current_collector_cathode,
    "brace_plate": M.cad_brace_plate, "lid_assembly": M.cad_lid_assembly,
    "stack": M.cad_stack, "stack_assembly": M.cad_stack_assembly,
}
for k in M.PELLET_SPECS:
    FN[k] = M.cad_pellet

# Parse the whole tag then pull each attribute out separately. Matching them in
# one pattern with an optional transform group silently skips the rotation,
# which measures every rotated label as though it were horizontal.
TEXT = re.compile(r"<text ([^>]*)>(.*?)</text>", re.S)
ATTR = {k: re.compile(rf'{k}="([^"]*)"') for k in
        ("x", "y", "font-size", "text-anchor", "transform")}

# Arial: average glyph advance is ~0.52 em, cap height ~0.72 em
ADV, CAP = 0.52, 0.72


def boxes(svg):
    out = []
    for m in TEXT.finditer(svg):
        attrs, body = m.group(1), m.group(2)
        txt = re.sub(r"<[^>]+>", "", body).strip()
        if not txt:
            continue
        g = {k: (r.search(attrs).group(1) if r.search(attrs) else None)
             for k, r in ATTR.items()}
        x, y, size = float(g["x"]), float(g["y"]), float(g["font-size"])
        anchor = g["text-anchor"] or "start"
        rot = 0.0
        if g["transform"]:
            mr = re.search(r"rotate\(([-\d.]+)", g["transform"])
            if mr:
                rot = float(mr.group(1))
        w, h = len(txt) * size * ADV, size * CAP
        x0 = x if anchor == "start" else (x - w if anchor == "end" else x - w / 2)
        cx, cy = x0 + w / 2, y - h / 2
        if rot:                       # rotate the box centre about the anchor
            a = math.radians(rot)
            dx, dy = cx - x, cy - y
            cx = x + dx * math.cos(a) - dy * math.sin(a)
            cy = y + dx * math.sin(a) + dy * math.cos(a)
            if abs(abs(rot) - 90) < 45:
                w, h = h, w
        out.append((cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, txt, size))
    return out


def overlap(a, b, pad=0.0):
    return not (a[2] + pad <= b[0] or b[2] + pad <= a[0]
                or a[3] + pad <= b[1] or b[3] + pad <= a[1])


def area(a, b):
    return (max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
            * max(0.0, min(a[3], b[3]) - max(a[1], b[1])))


# Component outlines are drawn heavy (THICK .45 / MED .28); dimension and
# extension lines are THIN (.16). Text may sit on a thin line — that is how a
# dimension line is broken for its value — but never on the part itself.
HEAVY = 0.22
LINE = re.compile(r'<line x1="([-\d.]+)" y1="([-\d.]+)" x2="([-\d.]+)" y2="([-\d.]+)"[^>]*?stroke-width="([\d.]+)"')
POLY = re.compile(r'<poly(?:line|gon) points="([^"]+)"[^>]*?stroke-width="([\d.]+)"')


def segments(svg):
    segs = []
    for m in LINE.finditer(svg):
        x1, y1, x2, y2, w = (float(v) for v in m.groups())
        if w >= HEAVY:
            segs.append((x1, y1, x2, y2))
    for m in POLY.finditer(svg):
        pts, w = m.group(1), float(m.group(2))
        if w < HEAVY:
            continue
        p = [tuple(float(v) for v in q.split(",")) for q in pts.split() if "," in q]
        segs += [(p[i][0], p[i][1], p[i+1][0], p[i+1][1]) for i in range(len(p) - 1)]
    return segs


def seg_hits_box(seg, b, pad=0.25):
    """Cohen–Sutherland style clip of a segment against the padded text box."""
    x0, y0, x1, y1 = b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad
    ax, ay, bx, by = seg
    t0, t1 = 0.0, 1.0
    dx, dy = bx - ax, by - ay
    for p, q in ((-dx, ax - x0), (dx, x1 - ax), (-dy, ay - y0), (dy, y1 - ay)):
        if p == 0:
            if q < 0:
                return False
            continue
        r = q / p
        if p < 0:
            if r > t1:
                return False
            t0 = max(t0, r)
        else:
            if r < t0:
                return False
            t1 = min(t1, r)
    return t0 <= t1


TOL = re.compile(r"^[±+\-]|^\+?\d*\.?\d*\s*/\s*[-−]")
VAL = re.compile(r"\d")

print(f"{'drawing':<32} {'texts':>6} {'txt/txt':>8} {'on part':>8} {'lone tol':>9}")
print("-" * 68)
tt = tg = tl = 0
detail = []
for key, Model, kw in FIX:
    try:
        out = FN[key](Model(**kw), user="audit")
    except Exception as e:
        print(f"{key:<32} RENDER FAILED: {type(e).__name__}: {str(e)[:50]}")
        continue
    svg = out["svg"]
    allb = boxes(svg)
    bs = [b for b in allb
          if AX0 <= b[0] and b[2] <= AX1 and AY0 <= b[1] and b[3] <= AY1]
    # anything that ran off the drawing area (but is not header/footer text)
    oob = [b[4] for b in allb
           if AY0 - 2 <= (b[1] + b[3]) / 2 <= AY1 + 2
           and (b[0] < AX0 - 0.5 or b[2] > AX1 + 0.5)]
    segs = segments(svg)

    hits, onpart, lone = [], [], []
    for i in range(len(bs)):
        for j in range(i + 1, len(bs)):
            if overlap(bs[i], bs[j]) and area(bs[i], bs[j]) > 0.12:
                hits.append((bs[i][4], bs[j][4], round(area(bs[i], bs[j]), 2)))
    for b in bs:
        if any(seg_hits_box(s, b) for s in segs):
            onpart.append(b[4])
    # a tolerance on its own must sit right beside a value; more than ~4 mm away
    # and it reads as a separate note
    for b in bs:
        if TOL.match(b[4]) and not VAL.search(b[4].lstrip("±+-−")[:1] or "x"):
            pass
        if TOL.match(b[4]) and len(b[4]) <= 9:
            near = min((math.hypot((b[0]+b[2])/2 - (o[0]+o[2])/2,
                                   (b[1]+b[3])/2 - (o[1]+o[3])/2)
                        for o in bs if o is not b and VAL.search(o[4]) and not TOL.match(o[4])),
                       default=99.0)
            if near > 4.5:
                lone.append((b[4], round(near, 1)))

    tt += len(hits); tg += len(onpart); tl += len(oob)
    print(f"{key:<32} {len(bs):>6} {len(hits):>8} {len(onpart):>8} {len(oob):>9}")
    if hits or onpart or oob:
        detail.append((key, hits, onpart, oob))

print(f"\nTOTALS  text-on-text {tt}   text-on-geometry {tg}   text off-sheet {tl}\n")
for key, hits, onpart, oob in detail:
    print(f"  {key}")
    for a, b, ar in sorted(hits, key=lambda h: -h[2])[:6]:
        print(f"     overlap   {ar:>6} mm²  {a!r} x {b!r}")
    for t in onpart[:6]:
        print(f"     on part   {t!r}")
    for t in oob[:6]:
        print(f"     off sheet {t!r}")
