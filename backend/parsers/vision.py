"""Shared Gemini-vision helpers: render source files to images and run a
structured (pydantic-schema) extraction call.

Used by the PID parser and the customer-package parser. The design-document
parser does NOT use this (it is deterministic Excel).
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Type, TypeVar

import fitz  # PyMuPDF
from google import genai
from google.genai import types
from pydantic import BaseModel

from .. import config

T = TypeVar("T", bound=BaseModel)

_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


def _client() -> genai.Client:
    if not config.has_api_key():
        raise RuntimeError(
            "GOOGLE_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    return genai.Client(api_key=config.GOOGLE_API_KEY)


def file_to_image_parts(path: str | Path) -> list[types.Part]:
    """Render a source file (PDF or image) into a list of PNG image Parts."""
    path = Path(path)
    parts: list[types.Part] = []
    if path.suffix.lower() == ".pdf":
        doc = fitz.open(path)
        mat = fitz.Matrix(config.RENDER_ZOOM, config.RENDER_ZOOM)
        for page in doc:
            png = page.get_pixmap(matrix=mat).tobytes("png")
            parts.append(types.Part.from_bytes(data=png, mime_type="image/png"))
        doc.close()
    elif path.suffix.lower() in _IMAGE_EXT:
        data = path.read_bytes()
        mime = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
        parts.append(types.Part.from_bytes(data=data, mime_type=mime))
    else:
        raise ValueError(f"Unsupported file type for vision extraction: {path.name}")
    return parts


def extract_structured(
    prompt: str,
    files: list[str | Path],
    schema: Type[T],
    *,
    retries: int = 3,
    timeout_s: int = 180,
) -> T:
    """Send prompt + rendered images to Gemini, force JSON matching `schema`."""
    client = _client()
    image_parts: list[types.Part] = []
    for f in files:
        image_parts.extend(file_to_image_parts(f))

    contents = [types.Content(role="user", parts=[types.Part(text=prompt), *image_parts])]
    cfg = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema,
        temperature=0.0,
        http_options=types.HttpOptions(timeout=timeout_s * 1000),
    )

    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            resp = client.models.generate_content(
                model=config.EXTRACTION_MODEL, contents=contents, config=cfg
            )
            parsed = resp.parsed
            if isinstance(parsed, schema):
                return parsed
            return schema.model_validate_json(resp.text)
        except Exception as e:  # transient httpx drops, 5xx, parse hiccups
            last_err = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Gemini extraction failed after {retries} attempts: {last_err}")
