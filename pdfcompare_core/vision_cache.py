"""Shared cache storage and source validation, independent of provider or frontend policy."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from .pdf_io import find_pages_dir, find_summary_json_path


def read_cache(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def input_fingerprint(run_dir: Path, seq: int, pair_name: str = "", *, version: str) -> str:
    digest = hashlib.sha256(version.encode())
    pages = find_pages_dir(run_dir)
    try:
        rows = read_cache(find_summary_json_path(run_dir)).get("pairs", [])
        row: dict[str, Any] = next((item for item in rows if int(item["seq"]) == seq), {})
    except (OSError, ValueError, KeyError):
        row = {}
    digest.update(json.dumps(row, ensure_ascii=False, sort_keys=True).encode())
    if not pair_name:
        pair_name = str(row.get("pair_dir") or f"{seq:03d}")
    for name in ("a.png", "b.png", "overlay.png", "bboxes.json"):
        path = pages / pair_name / name
        digest.update(name.encode())
        if path.is_file():
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
    return digest.hexdigest()
