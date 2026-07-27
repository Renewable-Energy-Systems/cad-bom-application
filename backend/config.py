"""Central configuration for the V1 CAD-BOM app.

Loads a local .env (without extra deps) and exposes settings. The .env values
override any pre-existing shell environment so a developer's local key wins.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
JOBS_DIR = DATA_DIR / "jobs"
FRONTEND_DIR = ROOT / "frontend"


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no python-dotenv dependency)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ[key.strip()] = val.strip().strip('"').strip("'")


_load_dotenv(ROOT / ".env")

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "").strip()
EXTRACTION_MODEL = os.environ.get("EXTRACTION_MODEL", "gemini-2.5-pro").strip()
PORT = int(os.environ.get("PORT", "8020"))

# PDF -> image render zoom for vision extraction (higher = sharper, larger payload)
RENDER_ZOOM = float(os.environ.get("RENDER_ZOOM", "3.0"))

JOBS_DIR.mkdir(parents=True, exist_ok=True)


def has_api_key() -> bool:
    return bool(GOOGLE_API_KEY and GOOGLE_API_KEY != "your-gemini-api-key")
