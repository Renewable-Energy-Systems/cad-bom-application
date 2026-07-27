"""Design lookup tables for CAD generation."""
from __future__ import annotations

from typing import Optional

# Table 2 — Container Wall Thickness.
# (od_low, od_high, deep_drawn_wall, flange_wall, wall_tolerance, (min, max))
TABLE2_CONTAINER_WALL = [
    (30, 50, 0.70, 0.70, "+0.15 / -0.05", (0.65, 0.85)),
    (50, 100, 1.10, 1.00, "±0.10", (0.90, 1.10)),
    (100, 150, 1.30, 1.30, "+0.15 / -0.10", (1.20, 1.45)),
]


# Table 3 — Width and Depth of Groove (lid blank), by container OD.
# (od_low, od_high, depth, width)
TABLE3_GROOVE = [
    (30, 45, 0.80, 0.70),
    (46, 100, 1.00, 1.00),
    (101, 150, 1.30, 1.30),
]

# Table 4(b) — Lid Blank Thickness, by container OD.
TABLE4B_LID_THICKNESS = [
    (30, 50, 2.5),
    (51, 80, 4.0),
    (81, 110, 5.0),
    (111, 150, 6.5),
]


def _band(od: float, table):
    for row in table:
        lo, hi = row[0], row[1]
        in_band = (lo <= od <= hi) if lo == table[0][0] else (lo < od <= hi)
        if in_band:
            return row
    return None


def groove_dims(od: float) -> dict:
    """Table 3 groove depth & width by container OD."""
    row = _band(od, TABLE3_GROOVE)
    if not row:
        return {"depth": 1.0, "width": 1.0, "band": "?"}
    return {"depth": row[2], "width": row[3], "band": f"{row[0]}-{row[1]}"}


def lid_blank_thickness(od: float) -> Optional[float]:
    """Table 4(b) lid blank thickness by container OD."""
    row = _band(od, TABLE4B_LID_THICKNESS)
    return row[2] if row else None


def lid_blank_od(container_id: float) -> float:
    """Table 4(a): Lid BLANK OD = Container ID - 0.05 (±0.05)."""
    return round(container_id - 0.05, 2)


def lid_finished_od(container_id: float) -> float:
    """Table 4(a): finished Lid OD = Container ID - 0.15 (±0.05)."""
    return round(container_id - 0.15, 2)


# Tie-wire width by container OD.  (od_low, od_high, width)
TIE_WIRE_WIDTH = [
    (30, 70, 3.0),
    (70, 10 ** 9, 6.0),
]

# Teflon disc: value subtracted for the inner-most circle, by pellet/cathode dia.
TEFLON_INNER_SPACE = [
    (20, 30, 3.0),
    (31, 60, 5.0),
    (61, 90, 7.0),
]


def tie_wire_width(od: float) -> float:
    """Tie-wire width by container OD (30-70 -> 3, >70 -> 6)."""
    for lo, hi, w in TIE_WIRE_WIDTH:
        if (lo <= od <= hi) if lo == 30 else (lo < od <= hi):
            return w
    return 3.0


def teflon_inner_space(pellet_dia: float) -> float:
    """Inner-most-circle offset for the Teflon disc, by pellet/cathode dia."""
    for lo, hi, s in TEFLON_INNER_SPACE:
        if lo <= pellet_dia <= hi:
            return s
    return 5.0


def container_wall(od: float, container_type: str) -> Optional[dict]:
    """Wall thickness from Table 2 by container OD range and type.

    container_type: 'deep_drawn' or 'flanged'. Boundary ODs (50, 100) fall in the
    upper band (e.g. 50 -> 50-100).
    """
    for lo, hi, dd, fl, tol, (mn, mx) in TABLE2_CONTAINER_WALL:
        in_band = (lo < od <= hi) if lo != 30 else (lo <= od <= hi)
        if in_band:
            wall = dd if container_type == "deep_drawn" else fl
            return {"wall": wall, "tolerance": tol, "min": mn, "max": mx,
                    "od_band": f"{lo}-{hi}"}
    return None  # OD out of the 30-150 mm table range


def pyro_wick_dims(container_od: Optional[float]) -> dict:
    """Pyro Wick-01 width & thickness by container OD (guideline table)."""
    if container_od is not None and container_od > 70:
        return {"width": 6.0, "thickness": 0.7}
    return {"width": 3.0, "thickness": 0.3}   # 30 - 70 (and default)


def fiberfrax_thickness(container_od: Optional[float]) -> float:
    """FiberFrax sheet thickness by container OD (guideline table)."""
    return 1.6 if (container_od is not None and container_od > 70) else 1.0
