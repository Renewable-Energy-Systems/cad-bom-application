"""Build Table 1 (Extracted From Customer Drawings).

13 fixed component rows, in order, each populated from the customer-drawing
extraction and stamped with an IS 2102 general tolerance (unless the drawing
already states one). Users can append extra rows via the API/UI.
"""
from __future__ import annotations

from typing import Optional

from ..schemas import DrawingTable1, Table1Row
from .tolerances import apply_general_tolerance

# (s_no, display name, DrawingTable1 field, kind, default unit)
TABLE1_SPEC = [
    (1, "Height of Container (Battery Height/Shoulder)", "height_of_container", "linear", "mm"),
    (2, "Diameter of Battery", "diameter_of_battery", "linear", "mm"),
    (3, "Pin PCD", "pin_pcd", "linear", "mm"),
    (4, "Diameter of the Pin", "diameter_of_pin", "linear", "mm"),
    (5, "Number of Holes (+ve, -ve, EI1, EI2)", "number_of_holes", "count", ""),
    (6, "Angle between the Holes", "angle_between_holes", "angular", "deg"),
    (7, "Mounting Holes PCD", "mounting_holes_pcd", "linear", "mm"),
    (8, "Upper Part of the Pin", "upper_part_of_pin", "linear", "mm"),
    (9, "Mounting Hole Spacing (Horizontal and Vertical)", "mounting_hole_spacing", "linear", "mm"),
    (10, "Flange Width", "flange_width", "linear", "mm"),
    (11, "Flange Thickness", "flange_thickness", "linear", "mm"),
    (12, "Pin Hole Spec", "pin_hole_spec", "spec", ""),
    (13, "Mounting Hole Spec", "mounting_hole_spec", "spec", ""),
]

# Rows that only exist when the battery has a mounting flange.
FLANGE_ROWS = {7, 9, 10, 11, 13}
_NO_FLANGE_NOTE = "N/A — no flange on this battery"

# Rows always left blank for manual entry (never auto-filled from the drawing).
BLANK_ROWS = {4}  # Diameter of the Pin


def build_table1(t: Optional[DrawingTable1]) -> list[Table1Row]:
    t = t or DrawingTable1()
    has_flange = t.has_flange  # None = unknown, True/False = detected
    rows: list[Table1Row] = []
    for s_no, name, field, kind, unit in TABLE1_SPEC:
        value = getattr(t, field, None)
        note = None
        # Always-blank rows (e.g. Pin Diameter) are left empty for manual entry.
        if s_no in BLANK_ROWS:
            value = None
        # Flange rows apply ONLY when a flange is actually present. Unknown or
        # absent => blank the value (never show a mounting/flange dimension).
        if s_no in FLANGE_ROWS and has_flange is not True:
            value, note = None, _NO_FLANGE_NOTE  # flange fields don't apply
        rows.append(
            Table1Row(
                s_no=s_no,
                component=name,
                value=value,
                unit=unit if value not in (None, "") and kind in ("linear", "angular") else (unit or None),
                tolerance=apply_general_tolerance(value, kind),
                kind=kind,
                source="customer_drawing",
                note=note,
            )
        )
    return rows


def add_row(rows: list[Table1Row], component: str, value: Optional[str],
            unit: Optional[str] = "mm", kind: str = "linear") -> list[Table1Row]:
    next_no = (max((r.s_no for r in rows), default=0)) + 1
    rows.append(
        Table1Row(
            s_no=next_no,
            component=component,
            value=value,
            unit=unit,
            tolerance=apply_general_tolerance(value, kind),
            kind=kind,
            source="user",
        )
    )
    return rows
