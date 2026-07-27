"""General tolerances per IS 2102 (Medium class 'm').

IS 2102-1 mirrors ISO 2768-1. We default to the MEDIUM class, which also happens
to match the RES house-drawing default block (0.5-6:+/-0.1, 6-30:+/-0.2,
30-120:+/-0.3, 120-315:+/-0.5). Applied to every dimension/feature UNLESS the
drawing already states a specific tolerance.
"""
from __future__ import annotations

import re
from typing import Optional

STANDARD = "IS 2102 medium"

# Linear dimensions — permissible deviation +/- (mm) by nominal size range (mm).
# range = (over, up_to_inclusive, deviation)
_LINEAR_MEDIUM = [
    (0.5, 3, 0.1),
    (3, 6, 0.1),
    (6, 30, 0.2),
    (30, 120, 0.3),
    (120, 400, 0.5),
    (400, 1000, 0.8),
    (1000, 2000, 1.2),
    (2000, 4000, 2.0),
]

# Angular tolerance by length of shorter side of the angle (mm) -> deviation.
# We rarely know the side length, so default to the small-feature band.
_ANGULAR_MEDIUM = [
    (0, 10, "1°"),
    (10, 50, "0°30'"),
    (50, 120, "0°20'"),
    (120, 400, "0°10'"),
    (400, 10**9, "0°5'"),
]

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
# explicit tolerance already on the value string (±, +/-, +0.05/-0.10, etc.)
_EXPLICIT_TOL_RE = re.compile(r"(±|\+/-|\+\s*/\s*-|\+\s*0|\-\s*0|\+\s*\.\d|\bH\d|\bh\d|\bg\d|\bIT\d)")


def nominal_of(value: Optional[str]) -> Optional[float]:
    """First numeric token in a value string (strips leading Ø, R, etc.)."""
    if value is None:
        return None
    m = _NUM_RE.search(str(value).replace(",", ""))
    return float(m.group()) if m else None


def has_explicit_tolerance(value: Optional[str]) -> bool:
    if value is None:
        return False
    return bool(_EXPLICIT_TOL_RE.search(str(value)))


def linear_tolerance(nominal: float) -> Optional[str]:
    n = abs(nominal)
    if n < 0.5:
        return None  # dimensions <= 0.5 mm are toleranced individually per IS 2102
    for over, up_to, dev in _LINEAR_MEDIUM:
        if over < n <= up_to or (over == 0.5 and n == 0.5):
            return f"±{dev} ({STANDARD})"
    return None  # out of table range


def angular_tolerance(side_len_mm: Optional[float] = None) -> str:
    n = side_len_mm if side_len_mm is not None else 30.0  # small pin-scale default
    for over, up_to, dev in _ANGULAR_MEDIUM:
        if over <= n <= up_to:
            return f"±{dev} ({STANDARD})"
    return f"±0°30' ({STANDARD})"


def apply_general_tolerance(value: Optional[str], kind: str) -> Optional[str]:
    """Return the tolerance string to attach to a value.

    - If the drawing already specifies a tolerance -> "as specified on drawing".
    - count / spec kinds -> no general tolerance.
    - linear / angular -> IS 2102 medium.
    """
    if value in (None, ""):
        return None
    if kind in ("count", "spec"):
        return None
    if has_explicit_tolerance(value):
        return "as specified on drawing"
    if kind == "angular":
        return angular_tolerance()
    nominal = nominal_of(value)
    if nominal is None:
        return None
    return linear_tolerance(nominal)
