"""Cross-validate the PID against the Design document.

Only unambiguous, same-quantity overlaps are compared (battery code, series/
parallel config, anode/cathode diameters, the six electrode weights and six
thicknesses). Every comparable pair must match; any mismatch is flagged. Also
applies the domain rule: Stack Diameter = Cathode Diameter.
"""
from __future__ import annotations

import re
from typing import Optional

from ..schemas import (
    CompareRow,
    DesignDocExtraction,
    PIDExtraction,
    ValidationReport,
)

_NUM = re.compile(r"-?\d+(?:\.\d+)?")
_EPS = 1e-3


def _num(v) -> Optional[float]:
    if v is None:
        return None
    m = _NUM.search(str(v).replace(",", ""))
    return float(m.group()) if m else None


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _electrode(pid: PIDExtraction, *needles: str):
    """Find the electrode row whose name contains all needles (normalized)."""
    for row in pid.electrode_table:
        n = _norm(row.electrode)
        if all(_norm(x) in n for x in needles):
            return row
    return None


def _design(design: DesignDocExtraction, name: str) -> Optional[str]:
    key = _norm(name)
    for p in design.params:
        if _norm(p.parameter) == key:
            return p.value
    # fall back to "contains"
    for p in design.params:
        if key in _norm(p.parameter):
            return p.value
    return None


def _series_parallel(config: Optional[str]):
    if not config:
        return None, None
    m = re.search(r"(\d+)\s*S\s*(\d+)\s*P", config, re.IGNORECASE)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def _cmp(param: str, pid_val, design_val, rows: list, counters: dict):
    pv = None if pid_val is None else str(pid_val)
    dv = None if design_val is None else str(design_val)
    if pid_val is None or design_val is None:
        status = "missing"
    else:
        a, b = _num(pid_val), _num(design_val)
        if a is not None and b is not None:
            status = "match" if abs(a - b) <= _EPS else "mismatch"
        else:
            status = "match" if _norm(pv) == _norm(dv) else "mismatch"
    counters[status] = counters.get(status, 0) + 1
    rows.append(CompareRow(parameter=param, pid_value=pv, design_value=dv, status=status))


def compare_pid_design(
    pid: Optional[PIDExtraction], design: Optional[DesignDocExtraction]
) -> ValidationReport:
    rows: list[CompareRow] = []
    counters: dict[str, int] = {}
    report = ValidationReport()

    if pid is None or design is None:
        missing = "PID" if pid is None else "Design document"
        report.flags.append(f"{missing} not provided — PID/Design cross-check skipped.")
        return report

    # identity + configuration
    _cmp("Battery Code", pid.battery_code, design.battery_code, rows, counters)
    s, p = _series_parallel(pid.battery_configuration)
    _cmp("Cells in Series", s, _design(design, "Cells in Series"), rows, counters)
    _cmp("Stacks in Parallel", p, _design(design, "Stacks in Parallel"), rows, counters)

    anode = _electrode(pid, "anode")
    cathode = _electrode(pid, "cathode")
    electro = _electrode(pid, "electrolyte")
    hp1 = _electrode(pid, "heatpellet", "1") or _electrode(pid, "heat", "1")
    hp2 = _electrode(pid, "heatpellet", "2") or _electrode(pid, "heat", "2")
    hp3 = _electrode(pid, "heatpellet", "3") or _electrode(pid, "heat", "3")

    def dia(e):
        return e.dia_mm if e else None

    def wt(e):
        return e.weight_g if e else None

    def thk(e):
        return e.thickness_mm if e else None

    # diameters
    _cmp("Anode Dia", dia(anode), _design(design, "Anode Dia"), rows, counters)
    _cmp("Cathode Dia", dia(cathode), _design(design, "Cathode Dia"), rows, counters)

    # electrode weights
    _cmp("Anode Weight/Electrode", wt(anode), _design(design, "Anode Weight per Electrode"), rows, counters)
    _cmp("Cathode Weight/Electrode", wt(cathode), _design(design, "Cathode Weight per Electrode"), rows, counters)
    _cmp("Electrolyte Weight/Electrode", wt(electro), _design(design, "Electrolyte Weight per Electrode"), rows, counters)
    _cmp("Heat Pellet-1 Weight", wt(hp1), _design(design, "Heat Pellet-1 Weight"), rows, counters)
    _cmp("Heat Pellet-2 Weight", wt(hp2), _design(design, "Heat Pellet-2 Weight"), rows, counters)
    _cmp("Heat Pellet-3 Weight", wt(hp3), _design(design, "Heat Pellet-3 Weight"), rows, counters)

    # electrode thicknesses
    _cmp("Anode Thickness", thk(anode), _design(design, "Anode Avg Thickness"), rows, counters)
    _cmp("Cathode Thickness", thk(cathode), _design(design, "Cathode Avg Thickness"), rows, counters)
    _cmp("Electrolyte Thickness", thk(electro), _design(design, "Electrolyte Avg Thickness"), rows, counters)
    _cmp("Heat Pellet-1 Thickness", thk(hp1), _design(design, "HP-1 Avg Thickness"), rows, counters)
    _cmp("Heat Pellet-2 Thickness", thk(hp2), _design(design, "HP-2 Avg Thickness"), rows, counters)
    _cmp("Heat Pellet-3 Thickness", thk(hp3), _design(design, "HP-3 Avg Thickness"), rows, counters)

    # rule check: Stack Diameter = Cathode Diameter
    stack_dia = _design(design, "Total Stack Diameter")
    if stack_dia is not None and dia(cathode) is not None:
        a, b = _num(stack_dia), _num(dia(cathode))
        if a is not None and b is not None and abs(a - b) > _EPS:
            report.flags.append(
                f"Rule (Stack Diameter = Cathode Diameter): design Stack Diameter {stack_dia} "
                f"≠ Cathode Diameter {dia(cathode)}."
            )

    report.comparison = rows
    report.matched = counters.get("match", 0)
    report.mismatched = counters.get("mismatch", 0)
    report.missing = counters.get("missing", 0)
    report.all_matched = report.mismatched == 0
    for r in rows:
        if r.status == "mismatch":
            report.flags.append(
                f"PID vs Design mismatch — {r.parameter}: PID={r.pid_value} / Design={r.design_value}"
            )
    return report
