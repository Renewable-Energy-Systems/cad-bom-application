"""Local JSON store for ingest jobs.

Layout:  data/jobs/<job_id>/result.json   (+ sources/ holds the uploaded files)
Store-agnostic: swap this module for a DB-backed one without touching callers.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

from .. import config
from ..schemas import IngestResult


def _job_dir(job_id: str) -> Path:
    return config.JOBS_DIR / job_id


def sources_dir(job_id: str) -> Path:
    d = _job_dir(job_id) / "sources"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save(result: IngestResult) -> None:
    d = _job_dir(result.job_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "result.json").write_text(
        result.model_dump_json(indent=2), encoding="utf-8"
    )


def load(job_id: str) -> Optional[IngestResult]:
    f = _job_dir(job_id) / "result.json"
    if not f.exists():
        return None
    return IngestResult.model_validate_json(f.read_text(encoding="utf-8"))


def list_jobs() -> list[dict]:
    out: list[dict] = []
    if not config.JOBS_DIR.exists():
        return out
    for d in sorted(config.JOBS_DIR.iterdir(), reverse=True):
        f = d / "result.json"
        if not f.exists():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append(
            {
                "job_id": data.get("job_id"),
                "battery_name": data.get("battery_name"),
                "created_at": data.get("created_at"),
                "sources": [s.get("role") for s in data.get("sources", [])],
                "warnings": len(data.get("warnings", [])),
            }
        )
    return out


def delete(job_id: str) -> bool:
    d = _job_dir(job_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
        return True
    return False
